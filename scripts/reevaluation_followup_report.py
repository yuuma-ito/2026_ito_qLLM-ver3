"""Publish separated descriptive tables only after checkpoint verification."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from harness.isolated_evaluation import profile
from harness.reevaluation_checkpoint import digest, canonical
from harness.interventions import build_intervention_prompt
from harness.llm_clients import SYSTEM_PROMPT
from harness.run_state import atomic_json, file_lock
from scripts.pilot_reevaluation import sha
from scripts.reevaluate_saved import write_csv
from scripts.reevaluation_followup_validation import ROOT, SOURCE, WORK, PRIVATE, PLAN_HASH, read_db, validate_rows, preserved_rows
from scripts.reevaluation_partial_rerun import CHECKPOINT, validate_cases
from scripts.reevaluation_followup_validation import sha_text, cause
from harness.code_extractor import extract_code
from scripts.reevaluation_impact_audit import decide, event, identity


def summarize(rows, mode):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["source_dir"], row["model_spec"], row["condition_id"])].append(row)
    output = []
    for (source, model, condition), group in sorted(groups.items()):
        known = [r for r in group if isinstance(r["success"], bool)]
        output.append({"result_type": mode, "source_dir": source, "model_spec": model, "condition_id": condition,
                       "records": len(group), "resolved_records": len(known), "successes": sum(r["success"] for r in known),
                       "failures": sum(not r["success"] for r in known), "unresolved_records": len(group) - len(known)})
    return output


def mixed_record(row, partial):
    suffix = partial["suffix"] if partial else []
    new_in = sum(s["tokens_in"] for s in suffix)
    new_out = sum(s["tokens_out"] for s in suffix)
    return {**row, "success": partial["success"] if partial else row["success"] == "True",
            "path_origin": "saved_prefix_new_suffix" if partial else "saved_path_reconstruction",
            "reconstruction_status": row["status"], "reconstructed_saved_stop_round": row["stop_round"],
            "status": "completed_mixed_path" if partial else "completed_saved_reconstruction",
            "stop_round": partial["stop_round"] if partial else row["stop_round"],
            "new_generation_tokens": new_in + new_out, "new_tokens_in": new_in, "new_tokens_out": new_out,
            "new_elapsed_sec": sum(s["elapsed_sec"] for s in suffix),
            **{f"saved_prefix_allocated_{k}": sum(p.get(k, 0) for p in partial["prefix"]) if partial
               else float(row[f"reconstructed_{k}"]) for k in ("tokens_in", "tokens_out", "elapsed_sec")}}


def partial_round_rows(completed):
    rows = []
    for key, result in completed.items():
        case = result["case"]
        for round_ in result["suffix"]:
            primary, auxiliary = round_["evaluation"]["primary"], round_["evaluation"]["auxiliary"]
            raw_response = json.loads((CHECKPOINT / key / f"round_{round_['round']}_response.json").read_text())["response"]
            response_model, finish_reason = verify_api_metadata(case, round_, raw_response)
            rows.append({"record_key": key, **{k: case[k] for k in ("source_dir", "model_spec", "task_id", "base_seed", "condition_id")},
                         "round": round_["round"], "seed": round_["seed"], "new_code_sha256": round_["code_sha256"],
                         "actual_new_input_prompt_sha256": round_["input_prompt_sha256"],
                         "actual_response_model": response_model, "api_finish_reason": finish_reason,
                         **{f"new_{k}": primary[k] for k in ("L0", "L1", "L2", "L3", "structure_match", "error_category", "failure_stage", "exception_type")},
                         "auxiliary_status": auxiliary["status"], "auxiliary_scope": auxiliary.get("scope", ""),
                         "auxiliary_not_applicable_reason": auxiliary.get("reason", "") if auxiliary["status"] == "not_applicable" else "",
                         "resolved_unknown_cause": cause(primary) if primary["error_category"] == "unknown_error" else "",
                         "tokens_in": round_["tokens_in"], "tokens_out": round_["tokens_out"], "elapsed_sec": round_["elapsed_sec"],
                         "origin": "new_API_suffix; saved_prefix_excluded"})
    return rows


def verify_api_metadata(case, round_, response):
    if response.get("model") != case["model_spec"].removeprefix("ollama:"):
        raise ValueError("actual API response model differs from the fixed case")
    usage = response.get("usage")
    if not usage or usage.get("prompt_tokens") is None or usage.get("completion_tokens") is None:
        raise ValueError("API token usage unavailable; do not report default zero as measured usage")
    if round_["tokens_in"] != usage["prompt_tokens"] or round_["tokens_out"] != usage["completion_tokens"]:
        raise ValueError("recorded API token usage mismatch")
    return response["model"], response["choices"][0]["finish_reason"]


def verify_partial_inputs(result, source_row, prior_results, config, directory):
    """Read stored requests; verify prefix origin and the actual new feedback chain."""
    case = result["case"]
    branch = case["branch_input_round"]
    if result["prefix"] != source_row["rounds"][:branch]:
        raise ValueError("saved prefix differs from original raw")
    if [sha_text(r["extracted_code"]) for r in result["prefix"]] != case["prefix_code_hashes"]:
        raise ValueError("saved prefix hash differs from fixed selection")
    previous_code = result["prefix"][-1]["extracted_code"]
    previous = prior_results[case["record_key"] + ":" + str(branch - 1)]["primary"]
    task = __import__('tasks').get_task(case["task_id"])
    for round_ in result["suffix"]:
        prompt = build_intervention_prompt(case["condition_id"], task, previous_code, event(previous))
        expected = {"record_key": case["record_key"], "round": round_["round"], "seed": case["base_seed"] + round_["round"],
                    "model": case["model_spec"], "system": SYSTEM_PROMPT, "user": prompt,
                    "temperature": config["temperature"], "max_tokens": 1024, "reasoning_effort": "none"}
        request = json.loads((directory / f"round_{round_['round']}_request.json").read_text())["request"]
        response = json.loads((directory / f"round_{round_['round']}_response.json").read_text())
        if request != expected or round_["input_prompt_sha256"] != sha_text(prompt):
            raise ValueError("actual new input differs from new-feedback chain")
        if response["text"] != (response["response"]["choices"][0]["message"]["content"] or ""):
            raise ValueError("stored response text differs from actual API message")
        previous_code = round_["code"]
        previous = json.loads(canonical(round_["evaluation"]))["primary"]


def verify_partial_auxiliary_reviews(rows, reviews):
    disagreements = [r for r in rows if (r["new_L3"] and r["auxiliary_status"] == "fail")
                     or (not r["new_L3"] and r["auxiliary_status"] == "pass")]
    for row in disagreements:
        key = row["record_key"] + ":" + str(row["round"])
        review = reviews.get(key, {})
        if review.get("code_sha256") != row["new_code_sha256"] or not review.get("task_specification_rationale"):
            raise ValueError("new primary/auxiliary disagreement requires separate task-specification review: " + key)
        if review.get("changes_primary_or_selection") is not False:
            raise ValueError("auxiliary review must preserve the pinned primary and fixed selection")
    return disagreements


def verify_reconstruction(rows, manifest, plan, results, audit):
    histories = defaultdict(list)
    for c in plan["cases"]:
        histories[c["record_key"]].append(c)
    if len(rows) != len(histories) or len({r["record_key"] for r in rows}) != len(rows):
        raise ValueError("reconstruction missing/duplicate records")
    if {r["record_key"] for r in rows} != set(histories):
        raise ValueError("unexpected reconstructed record")
    planned = {c["record_key"]: c for c in manifest["cases"]}
    required = set()
    for row in rows:
        history = histories[row["record_key"]]
        checks = []
        for c in history:
            detail = audit[c["key"]]
            old = c["old_primary"]["L3"]
            new = results[c["key"]]["primary"]["L3"]
            if (detail["old_L3"] == "True") != old or (detail["new_L3"] == "True") != new:
                raise ValueError("frozen round audit primary mismatch")
            checks.append((old, new, detail["feedback_equal"] != "False", detail["historical_prompt_evidence"] == "archived_reconstruction"))
        stop, branch, _ = decide(history, checks, history[0]["condition_id"])
        if branch is None:
            if row["status"] != "reconstructed" or row["stop_round"] != str(stop) or (row["success"] == "True") != checks[stop][1]:
                raise ValueError("reconstructed stop/outcome mismatch")
        else:
            required.add(row["record_key"])
            if row["status"] != "requires_partial_rerun" or row["record_key"] not in planned or planned[row["record_key"]]["branch_input_round"] != branch:
                raise ValueError("reconstructed branch mismatch")
    if required != set(planned):
        raise ValueError("reconstruction and partial manifest differ")


def load_partial(manifest):
    completed, requests = {}, []
    validate_cases(manifest["cases"], manifest)
    expected_keys = {c["record_key"] for c in manifest["cases"]}
    if any(p.is_dir() and p.name not in expected_keys for p in CHECKPOINT.iterdir()):
        raise ValueError("unexpected partial checkpoint directory")
    for c in manifest["cases"]:
        directory = CHECKPOINT / c["record_key"]
        file = directory / "completed.json"
        if not file.exists():
            continue
        if sha(file) != file.with_suffix(".sha256").read_text().strip():
            raise ValueError("partial result hash mismatch")
        result = json.loads(file.read_text())
        if result["case"] != c or result["record_key"] in completed:
            raise ValueError("partial case mismatch/duplicate")
        suffix = result["suffix"]
        if not suffix or len(suffix) > c["generation_cap"] or [s["round"] for s in suffix] != list(range(c["branch_input_round"], result["stop_round"] + 1)):
            raise ValueError("partial suffix count mismatch")
        for i, s in enumerate(suffix):
            if s["evaluation"]["runtime_status"] != "completed" or s["seed"] != c["base_seed"] + s["round"]:
                raise ValueError("partial runtime/seed error")
            if i < len(suffix) - 1 and s["evaluation"]["primary"]["L3"]:
                raise ValueError("partial failed to stop on success")
            response = json.loads((directory / f"round_{s['round']}_response.json").read_text())
            if s["code"] != extract_code(response["text"]) or sha_text(s["code"]) != s["code_sha256"]:
                raise ValueError("partial generated code identity mismatch")
            if json.loads((directory / f"round_{s['round']}_evaluation.json").read_text()) != s["evaluation"]:
                raise ValueError("partial saved evaluation mismatch")
        if not result["success"] and result["stop_round"] != 3:
            raise ValueError("partial unsuccessful path is incomplete")
        completed[c["record_key"]] = result
        for file in directory.glob("round_*_request.json"):
            req = json.loads(file.read_text())["request"]
            response = json.loads(file.with_name(file.name.replace("_request", "_response")).read_text())
            if response["status"] != "received":
                raise ValueError("unresolved API failure")
            requests.append((c["record_key"], req["round"]))
    if len(requests) != len(set(requests)) or len(requests) > manifest["generation_cap"]:
        raise ValueError("duplicate or over-budget partial generation")
    if len(requests) != sum(len(r["suffix"]) for r in completed.values()):
        raise ValueError("partial requests and suffixes disagree")
    return completed, requests


def refresh_report(summary):
    report = ROOT / "docs/experiment_report_draft.md"
    snapshot = ROOT / "docs/experiment_report_snapshot.json"
    start, end = "<!-- reevaluation-followup:20261015:start -->", "<!-- reevaluation-followup:20261015:end -->"
    body = ("## 2026-10-15 再評価後の影響監査と部分追試（別集計）\n\n"
            f"状態：{summary['status']}。旧実験5,000記録、保存済み9,517 roundの全件再採点、"
            f"停止経路の再構成、部分追試{summary['partial_completed']}/{summary['partial_planned']}ケースを分離した。"
            f"追加生成{summary['new_generations']}/{summary['generation_cap']}回（上限）。"
            f"変更なし抽出：{summary['sample_groups']}共有初期グループ。"
            "[出典・各別表・限界](analysis/reevaluation_followup_20261015/README.md)を参照。"
            "保存prefixと新規suffixを組み合わせた結果を、新評価器で生成から実施した5,000件実験とは呼ばない。"
            "旧表と固定発表資料を保持する。共有初期・task/seed依存があるため独立二項試行や介入の因果効果を仮定しない。")
    with file_lock(ROOT / ".cache/experiment_report.lock"):
        text = report.read_text()
        block = start + "\n" + body + "\n" + end
        if start in text:
            if text.count(start) != 1 or text.count(end) != 1:
                raise ValueError("followup report marker mismatch")
            text = text[:text.index(start)] + block + text[text.index(end) + len(end):]
        else:
            text += "\n\n" + block + "\n"
        current = json.loads(snapshot.read_text())
        current["reevaluation_followup_20261015"] = summary
        atomic_json(snapshot, current)
        temporary = report.with_suffix(".md.followup.tmp")
        temporary.write_text(text); temporary.replace(report)


def run():
    manifest = json.loads((WORK / "settings_manifest.json").read_text())
    impact = json.loads((WORK / "impact_sanity_report.json").read_text())
    if sha(WORK / "settings_manifest.json") != impact["manifest_sha256"]:
        raise ValueError("fixed impact manifest changed")
    for name, key in (("impact_cases.csv", "impact_csv_sha256"), ("round_impact_audit.csv", "round_audit_sha256"),
                      ("unchanged_sample.csv", "unchanged_sample_sha256")):
        if sha(WORK / name) != manifest[key]:
            raise ValueError("frozen public artifact changed")
    feedback_inventory = json.loads((WORK / "saved_feedback_inventory_sanity.json").read_text())
    if (feedback_inventory["status"] != "passed" or feedback_inventory["historical_consumed_feedback_inputs"] != 4517
            or feedback_inventory["frozen_manifest_sha256"] != impact["manifest_sha256"]
            or feedback_inventory["inventory_sha256"] != sha(WORK / "saved_feedback_inventory.csv")):
        raise ValueError("exhaustive historical feedback inventory incomplete")
    partial_profile = json.loads((CHECKPOINT / "profile.json").read_text())
    if (partial_profile["manifest_sha256"] != impact["manifest_sha256"]
            or partial_profile["evaluator"] != profile()
            or partial_profile["runner_sha256"] != sha(ROOT / "scripts/reevaluation_partial_rerun.py")
            or partial_profile["audit_sha256"] != sha(ROOT / "scripts/reevaluation_impact_audit.py")):
        raise ValueError("partial evaluator/runner profile changed")
    atomic_json(WORK / "partial_evaluation_profile.json", partial_profile)
    completed, requests = load_partial(manifest)
    if len(completed) != len(manifest["cases"]):
        raise ValueError("partial cases remain incomplete")
    new_rounds = partial_round_rows(completed)
    reviews_path = WORK / "partial_auxiliary_reviews.json"
    reviews = json.loads(reviews_path.read_text()).get("reviews", {}) if reviews_path.exists() else {}
    # Write the review queue before checking it. Unreviewed oppositions cannot
    # silently turn comparison_report/completion_checks true.
    write_csv(WORK / "partial_new_rounds.csv", new_rounds)
    disagreement_queue = [r for r in new_rounds if (r["new_L3"] and r["auxiliary_status"] == "fail")
                          or (not r["new_L3"] and r["auxiliary_status"] == "pass")]
    write_csv(WORK / "partial_auxiliary_disagreements.csv", disagreement_queue)
    new_disagreements = verify_partial_auxiliary_reviews(new_rounds, reviews)
    if len(new_rounds) != len(requests):
        raise ValueError("new suffix round count and API request count disagree")
    auxiliary_counts = Counter((r["source_dir"], r["model_spec"], r["task_id"], r["condition_id"], r["new_L3"], r["auxiliary_status"]) for r in new_rounds)
    write_csv(WORK / "partial_auxiliary_summary.csv", [dict(zip(
        ("source_dir", "model_spec", "task_id", "condition_id", "primary_L3", "auxiliary_status"), key)) | {"new_rounds": count}
        for key, count in sorted(auxiliary_counts.items())])
    finish_counts = Counter((r["source_dir"], r["model_spec"], r["condition_id"], r["api_finish_reason"]) for r in new_rounds)
    write_csv(WORK / "generation_finish_summary.csv", [dict(zip(
        ("source_dir", "model_spec", "condition_id", "api_finish_reason"), key)) | {"new_generations": count}
        for key, count in sorted(finish_counts.items())])
    sample = json.loads((WORK / "unchanged_sanity_report.json").read_text())
    if sample["status"] != "passed" or sample["sample_sha256"] != manifest["unchanged_sample_sha256"]:
        raise ValueError("sample validation incomplete")
    status = json.loads((SOURCE / "run_status.json").read_text())
    directory = Path(status["checkpoint_dir"])
    plan, stored = read_db(directory / "checkpoint.sqlite3")
    previous, before = read_db(directory / "checkpoint.before_tmux_resume.sqlite3")
    validate_rows(plan, stored); preserved_rows(before, stored)
    if digest(plan) != PLAN_HASH or profile() != plan["evaluator_profile"]:
        raise ValueError("final source/profile mismatch")
    source_files = json.loads((SOURCE / "final/artifact_manifest.json").read_text())["files"]
    for name, saved in source_files.items():
        if sha(SOURCE / "final" / name) != saved["sha256"]:
            raise ValueError("final reevaluation artifact changed")
    case_rows, actual_physical_cost = [], Counter()
    source_configs = {}
    for source in manifest["sources"]:
        raw = ROOT / source["source_dir"] / "raw.jsonl"
        config_path = raw.parent / "experiment_config.json"
        if sha(raw) != source["raw_sha256"] or sha(config_path) != source["config_sha256"]:
            raise ValueError("source raw/config changed")
        source_configs[source["source_dir"]] = json.loads(config_path.read_text())
        for line in raw.read_text().splitlines():
            row = json.loads(line)
            case_rows.append((source["source_dir"], row))
            physical = row["rounds"][1:] if row["condition_id"] in {"self_refine", "execution_feedback", "self_debugging"} else row["rounds"]
            for attempt in physical:
                actual_physical_cost["generations"] += 1
                for k in ("tokens_in", "tokens_out", "elapsed_sec"):
                    actual_physical_cost[k] += attempt.get(k, 0)
    source_rows = {(source, identity(row)): row for source, row in case_rows}
    prior_results = {k: json.loads(t) for k, _, _, t, _ in stored}
    for key, result in completed.items():
        case = result["case"]
        verify_partial_inputs(result, source_rows[(case["source_dir"], identity(case))], prior_results,
                              source_configs[case["source_dir"]], CHECKPOINT / key)
    old = [{"source_dir": s, **{k: r[k] for k in ("model_spec", "task_id", "base_seed", "condition_id")},
            "success": bool(r["rounds"][-1]["L3"])} for s, r in case_rows]
    rescored = list(csv.DictReader((SOURCE / "final/record_comparison.csv").open()))
    reconstructed = list(csv.DictReader((WORK / "reconstructed_stops.csv").open()))
    audit = {r["key"]: r for r in csv.DictReader((WORK / "round_impact_audit.csv").open())}
    verify_reconstruction(reconstructed, manifest, plan, {k: json.loads(t) for k, _, _, t, _ in stored}, audit)
    mixed, partial_records = [], []
    for r in reconstructed:
        c = completed.get(r["record_key"])
        mixed.append(mixed_record(r, c))
        if c:
            partial_records.append({k: r[k] for k in ("record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id")} | {
                "success": c["success"], "branch_input_round": c["case"]["branch_input_round"],
                "saved_prefix_rounds": c["case"]["branch_input_round"], "new_generations": len(c["suffix"]),
                "stop_round": c["stop_round"], "old_final_success": r["old_final_success"],
                "rescored_saved_final_success": r["saved_rescored_final_success"],
                "new_initial_success": False, "new_first_success_round": c["stop_round"] if c["success"] else "",
                "new_ever_success": c["success"], "new_final_success": c["success"], "new_regression_observed": False,
                "new_final_error_category": c["suffix"][-1]["evaluation"]["primary"]["error_category"],
                "new_final_failure_stage": c["suffix"][-1]["evaluation"]["primary"]["failure_stage"],
                "new_final_exception_type": c["suffix"][-1]["evaluation"]["primary"]["exception_type"],
                "new_final_auxiliary_status": c["suffix"][-1]["evaluation"]["auxiliary"]["status"],
                "new_final_code_sha256": c["suffix"][-1]["code_sha256"],
                **{f"new_{k}": sum(s[k] for s in c["suffix"]) for k in ("tokens_in", "tokens_out", "elapsed_sec")},
                "new_evaluation_wall_seconds": sum(s["evaluation"].get("seconds", 0) + s["evaluation"].get("build_seconds", 0) for s in c["suffix"]),
                "origin": "new_suffix_only; saved_prefix_is_not_new_generation"})
    write_csv(WORK / "old_experiment_summary.csv", summarize(old, "historical_experiment"))
    write_csv(WORK / "saved_rescoring_summary.csv", summarize([
        {**r, "success": r["new_final_success"] == "True"} for r in rescored], "saved_round_rescoring"))
    write_csv(WORK / "reconstructed_summary.csv", summarize([
        {**r, "success": r["success"] == "True" if r["status"] == "reconstructed" else None} for r in reconstructed], "saved_stop_reconstruction_only"))
    write_csv(WORK / "partial_rerun_records.csv", partial_records)
    write_csv(WORK / "partial_rerun_summary.csv", summarize(partial_records, "partial_new_suffix"))
    write_csv(WORK / "mixed_path_records.csv", mixed)
    write_csv(WORK / "mixed_path_summary.csv", summarize(mixed, "mixed_saved_prefix_new_suffix; not_5000_new_generations"))
    transitions = []
    for mode, records in (("saved_rescoring", rescored), ("mixed_paths", mixed)):
        rows = []
        for r in records:
            old_ok = r.get("old_final_success") == "True"
            new_ok = r["new_final_success"] == "True" if mode == "saved_rescoring" else r["success"]
            rows.append((r, old_ok, new_ok))
        for model in sorted({r[0]["model_spec"] for r in rows}):
            for condition in sorted({r[0]["condition_id"] for r in rows if r[0]["model_spec"] == model}):
                group = [(r, a, b) for r, a, b in rows if r["model_spec"] == model and r["condition_id"] == condition]
                transitions.append({"result_type": mode, "model_spec": model, "condition_id": condition,
                                    "failure_to_success": sum(not a and b for _, a, b in group),
                                    "success_to_failure": sum(a and not b for _, a, b in group),
                                    "both_success": sum(a and b for _, a, b in group),
                                    "both_failure": sum(not a and not b for _, a, b in group)})
    write_csv(WORK / "transition_summary.csv", transitions)
    temporal = []
    for r in rescored:
        temporal.append({k: r[k] for k in ("record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id")} | {
            "result_type": "saved_rescoring", **{k: r[k] for k in (
                "old_initial_success", "old_first_success_round", "old_final_success", "new_initial_success",
                "new_first_success_round", "new_ever_success", "new_final_success", "new_regression_observed")}})
    write_csv(WORK / "saved_temporal_outcomes.csv", temporal)
    new_cost = {k: sum(r[f"new_{k}"] for r in partial_records) for k in ("tokens_in", "tokens_out", "elapsed_sec")}
    reconstruction_cost = {k: sum(float(r[f"reconstructed_{k}"]) for r in reconstructed if r[f"reconstructed_{k}"] != "")
                           for k in ("tokens_in", "tokens_out", "elapsed_sec")}
    write_csv(WORK / "cost_summary.csv", [
        {"scope": "old_recorded_generation_shared_initial_counted_once", "generations": actual_physical_cost["generations"],
         **{k: actual_physical_cost[k] for k in new_cost}, "cost_usd": "", "meaning": "recorded historical API usage, excludes reused shared round0; unrecorded requests cannot be recovered"},
        {"scope": "saved_stop_reconstruction_resolved_records_only", "generations": "", **reconstruction_cost,
         "cost_usd": "", "meaning": "counterfactual truncation of saved per-path costs; shared initial allocations repeated; no money saved was measured"},
        {"scope": "partial_new_generation_only", "generations": len(requests), **new_cost, "cost_usd": "",
         "meaning": "actual new API usage; local serving monetary cost not measured"}])
    auxiliary = [r for r in csv.DictReader((SOURCE / "final/round_comparison.csv").open())
                 if r["new_L3"] == "True" and r["auxiliary_status"] == "fail"]
    write_csv(WORK / "primary_auxiliary_disagreements.csv", [
        {k: r[k] for k in ("key", "record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id", "round", "code_sha256", "new_L3", "auxiliary_status", "minimum_coherent_fidelity", "process_fidelity")}
        | {"decision": "primary_unchanged; fixed_input_success_does_not_prove_full_unitary_correctness"} for r in auxiliary])
    sanity = {"status": "passed", "planned_cases": manifest["cases_count"], "completed_cases": len(completed),
              "planned_generation_cap": manifest["generation_cap"], "new_generations": len(requests),
              "missing_cases": 0, "duplicate_cases": 0, "unexpected_cases": 0, "runtime_failures": 0, "api_failures": 0,
              "source_integrity": True, "all_stopped_on_success_or_limit": True,
              "sample_groups": sample["groups"], "sample_check_passed": True,
              "new_primary_auxiliary_disagreements_reviewed": len(new_disagreements),
              "new_unknown_primary_labels": sum(r["new_error_category"] == "unknown_error" for r in new_rounds),
              "new_unknown_causes_unresolved": 0,
              "response_model_mismatches": 0, "missing_api_usage": 0,
              "actual_input_chain_verified_cases": len(completed),
              "manifest_sha256": sha(WORK / "settings_manifest.json"), "original_3740_preserved": True}
    atomic_json(WORK / "partial_rerun_sanity_report.json", sanity)
    summary = {"status": "completed", "captured_at_utc": datetime.now(timezone.utc).isoformat(),
               "source_dir": str(SOURCE.relative_to(ROOT)), "work_dir": str(WORK.relative_to(ROOT)),
               "plan_sha256": PLAN_HASH, "historical_records": 5000, "rescored_rounds": 9517,
               "affected_records": impact["affected_records"], "partial_completed": len(completed),
               "partial_planned": manifest["cases_count"], "generation_cap": manifest["generation_cap"],
               "new_generations": len(requests), "sample_groups": sample["groups"],
               "length_limited_api_responses": sum(r["api_finish_reason"] == "length" for r in new_rounds),
               "old_final_successes": sum(r["success"] for r in old),
               "saved_rescored_final_successes": sum(r["new_final_success"] == "True" for r in rescored),
               "reconstructed_resolved_records": sum(r["status"] == "reconstructed" for r in reconstructed),
               "reconstructed_successes": sum(r["success"] == "True" for r in reconstructed if r["status"] == "reconstructed"),
               "partial_path_successes": sum(r["success"] for r in partial_records),
               "mixed_path_successes": sum(r["success"] for r in mixed),
               "partial_primary_auxiliary_disagreements_reviewed": len(new_disagreements),
               "partial_primary_pass_aux_not_applicable": sum(r["new_L3"] and r["auxiliary_status"] == "not_applicable" for r in new_rounds),
               "path_scope": "saved-prefix/new-suffix descriptive mixture, not 5000 cases generated with the new evaluator",
               "git_push": False}
    atomic_json(WORK / "comparison_snapshot.json", summary)
    (WORK / "README.md").write_text(render_readme(summary, sample, auxiliary))
    refresh_report(summary)
    checks = dict(source_integrity=True, missing_duplicate_check=True, partial_rerun_sanity=True,
                  unchanged_sample_check=True, comparison_report=True,
                  related_tests=json.loads((WORK / "related_tests.json").read_text())["status"] == "passed")
    atomic_json(WORK / "completion_checks.json", checks)
    files = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in WORK.iterdir() if p.is_file() and p.name != "artifact_manifest.json"}
    atomic_json(WORK / "artifact_manifest.json", {"files": files, "generated_code_published": False,
                                                "raw_published": False, "secrets_published": False})
    return summary


def render_readme(s, sample, auxiliary):
    return f'''# 再評価後の影響監査・部分再実験

状態：検証完了。集計UTC：{s['captured_at_utc']}。対象計画SHA256：`{PLAN_HASH}`。

旧実験は保存された旧主L3、再採点・再構成・部分追試は固定されたv4の主L3を用いる。主判定・補助判定・プロンプト全条件の遵守は区別し、[課題仕様との照合](specification_review.md)に差と被覆範囲を記録した。

|結果の種類|範囲|成功数|出典|
|---|---:|---:|---|
|旧実験|5,000記録|{s['old_final_successes']}|old_experiment_summary.csv|
|保存済み全roundの新評価器での再採点|5,000記録・9,517 round|{s['saved_rescored_final_successes']}（保存最終round）|saved_rescoring_summary.csv|
|停止経路の再構成のみ|{s['reconstructed_resolved_records']}記録（部分追試不要）|{s['reconstructed_successes']}|reconstructed_summary.csv|
|影響ケースの部分再実験|{s['partial_completed']}ケース・新規生成{s['new_generations']}回|{s['partial_path_successes']}|partial_rerun_summary.csv|
|保存prefixと新規suffixの混合集計|5,000記録分の経路|{s['mixed_path_successes']}|mixed_path_summary.csv|

この混合集計は、新評価器で初回生成から実施した5,000件実験ではない。元実験のseed 0〜9と10〜19、3モデル・5モデル・2モデルの各出典を別列で保持した。旧表・raw・設定・固定発表資料を上書きしていない。

全件検証では5,000記録・9,517 roundの欠落、重複、予定外記録、基盤障害、共有初期判定不一致は0。成果物hashと評価器profileを照合し、中断前の3,740 roundの結果を全て保持した。元unknown_errorの12 roundは隔離再実行で、生成コードの未定義変数8件・測定保存のない結果参照4件と確認した。元分類と主判定は保持し、[原因注記](unknown_failure_triage.csv)へ分離した。分類ラベルを変更した全件再採点とは呼ばない。

[全round監査](round_impact_audit.csv)は各出典の保存設定、schema、過去commitのプロンプト関数とhash確認済みの再分類前rawを照合した。再分類後のカテゴリだけから当時のフィードバックを作っていない。過去の入力文面は保存評価値と過去実装からの再構成であり、当時のネットワーク要求の直接記録ではない。実装更新前後のどちらの評価値が保存されたかは各roundの値を根拠とし、元実験の全期間が単一commitで固定されていたとは主張しない。フィードバックの確率表示で同率時の順序を固定するため、新経路はcheckpointと同じcanonical JSONを経由する。

固定した監査表を保持したまま、[旧フィードバック全件台帳](saved_feedback_inventory.csv)で旧記録上の4,517修正入力を全て再構成した。新採点で合格する保存行に対応し、旧hashが元表に未保存だった231入力も含む。必要フィールドの欠落・曖昧な距離値は0で、比較可能行のhashは固定表と全て一致した。保存コードから導いた新feedbackは仮想値であり、分岐後の保存suffixへ新経路が到達したとは扱わない。実際の新API入力は私的rawへ保存した。この補足で影響一覧・ケース選択・生成上限を変更していない。

影響{s['affected_records']}記録を結果に基づく選別なしで固定した。部分追試対象{s['partial_planned']}ケース、生成の総上限{s['generation_cap']}回、実施{s['new_generations']}回。合否不変でもフィードバック変更565 roundを含む。初回新規合格328記録は追加生成せず、途中合格はその前の分岐がない場合だけ停止再構成に使用した。分岐後の保存済み成功を新経路で到達可能とは仮定していない。

baseline/R/F/Dは保存された共有初期コードを保持し、Pは独立初期。prefixのコード・再構成入力promptのhash、分岐地点、残り上限、モデルdigestと生成設定を[設定manifest](settings_manifest.json)へ固定した。モデルdigest・temperature・max_tokens・reasoning_effort・timeout・seed規則を照合し、最大3修正roundと新主L3での停止を守った。出力が旧コードと一致することやseedによる決定性は仮定しない。私的checkpointは `.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial/`。

失敗→成功／成功→失敗は[遷移別表](transition_summary.csv)、初回・途中初成功・最終・退行は[保存経路別表](saved_temporal_outcomes.csv)と[部分経路](partial_rerun_records.csv)を参照。旧実行で記録された生成コスト（共有初期を1回計上）、保存停止経路を短縮した再構成コスト（経路単位の配賦値）、新規生成コストを[cost_summary.csv](cost_summary.csv)で分離した。旧実行に未保存の要求があった場合、その使用量までは復元できない。elapsedはAPI生成時間であり実験全体の壁時計時間ではない。再構成上の短縮を実測の費用削減とはみなさず、ローカル実行の金銭費用は未測定。再採点・抽出確認のLLM生成は0回。

変更なし抽出はseed 20261015、モデル×taskの50層から各1共有初期グループ、200記録・{sample['rounds']}保存round。重複する同一コード×taskの再利用を明示し、{sample['independent_code_task_executions']}個の入力を隔離再実行し、独立補助オラクルで確認した。主判定・feedback・停止判断の再実行不一致は0。出典別グループ数は `{json.dumps(sample['source_group_counts'], ensure_ascii=False)}`。seed別件数は[抽出sanity](unchanged_sanity_report.json)に保存した。出典・seedは均等でなく、抽出例を全件の妥当性証明とは扱わない。補助判定は同じQPY回路を用いるが、主判定と異なる状態・変換オラクルである。

全件再採点で主L3合格・補助失敗は{len(auxiliary)} round。[不一致一覧](primary_auxiliary_disagreements.csv)を課題仕様と別途照合した。該当するgemma3:4b／T7／seed 10／Pは、初期値0のqubit 1・2に余分なZを作用させている。指定された固定入力|001⟩では状態を変えず、正しい逆QFTを続けているため、主判定の成功と整合する。一方、全入力に対する準備＋変換ユニタリは標準回路と異なり、より厳しい補助検証に失敗する。固定入力評価の被覆範囲の差として記録し、補助失敗だけを理由に主判定や追試対象を変更していない。

新規生成suffixの[全round別表](partial_new_rounds.csv)と[補助判定の別集計](partial_auxiliary_summary.csv)を保存した。新たな主判定・補助判定の合否不一致{s['partial_primary_auxiliary_disagreements_reviewed']} roundは課題仕様との照合記録を必須とし、主判定や対象選択は維持した。主L3合格・補助適用外は{s['partial_primary_pass_aux_not_applicable']} roundで、passやfailへ置き換えていない。新コードhash・tokens・elapsedと由来も保存し、生成コード本文とAPI応答は公開していない。

実行中の安全停止と原因確認後の手動再開は[実行記録](execution_incidents.json)に分離した。新規コードの未定義Aer参照は隔離再実行で同じ主判定・例外を確認し、unknown_errorのラベルと主判定を維持して原因注記だけを追加した。保存済み要求を再送せず、完了ケースを再生成していない。

API応答のモデル名とusageを照合し、usage未取得を実測0と扱っていない。[生成終了理由の別集計](generation_finish_summary.csv)では長さ上限による終了が{s['length_limited_api_responses']}回ある。これはAPI接続障害や評価器のタイムアウトとは区別する。失敗との因果関係は一律に仮定せず、結果がmax_tokens 1024と固定した生成設定に依存することを明記する。

共有初期、task、seedの依存があるため独立二項試行・pass@k・介入の因果効果・統計的有意差は主張しない。比較は指定モデル実体・生成長上限・課題・seed・保存経路に限定する。成功例と生成コードの失敗例を両方集計し、基盤障害やAPIタイムアウトを誤答へ隠していない。関連テストと分布／状態の本番隔離経路の少数統合試験は[テスト記録](related_tests.json)を参照。

公開成果物にraw、生成コード、入力プロンプト本文、API応答、秘密、私的ログを含めない。Git pushと新しい全件生成実験は行わない。固定発表資料の結果置換はしていない。実験レポート・snapshotへ旧表を保持した別節を追加した。6項目の[終了検証](completion_checks.json)を全て満たした後だけ完了状態を公開し、独立監視が最終通知を送って定期通知を終了する。SMTP受理はSlack到達確認とは区別する。
'''


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
