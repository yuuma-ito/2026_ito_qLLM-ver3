"""Audit every saved round, with archived prompt source and pre-migration raw.

Prompt reconstruction is distinguished from a captured request. Missing evidence
forces a restart at shared round zero, never an assumed unchanged feedback path.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
from dataclasses import fields
import json
import random
import subprocess
from types import SimpleNamespace

from harness.evaluator import EvalResult
from harness.interventions import build_intervention_prompt
from harness.interventions import build_initial_prompt
from harness.reevaluation_checkpoint import digest
from scripts.pilot_reevaluation import sha
from scripts.reevaluate_saved import write_csv
from scripts.reevaluation_followup_validation import ROOT, SOURCE, WORK, PRIVATE, PLAN_HASH, read_db, sha_text
from tasks import get_task

CORRECTIONS = {"self_refine", "execution_feedback", "self_debugging"}
IDENTITY = ("model_spec", "task_id", "base_seed", "condition_id")


def identity(row):
    return tuple(row[k] for k in IDENTITY)


def event(primary):
    names = {f.name for f in fields(EvalResult)}
    values = {k: v for k, v in primary.items() if k in names}
    if values.get("L2_distance") is None:
        values["L2_distance"] = float("nan")
    return EvalResult(**values)


def archived_functions(commit):
    namespace = {"EvalResult": EvalResult, "Task": object}
    sources = {}
    for path, wanted in (("harness/refine.py", {"_fmt_dist", "diagnose"}),
                         ("harness/interventions/prompts.py", {"build_intervention_prompt"})):
        code = subprocess.check_output(["git", "show", f"{commit}:{path}"], text=True)
        sources[path] = sha_text(code)
        tree = ast.parse(code)
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
        if len(selected) != len(wanted):
            raise ValueError("archived prompt schema missing")
        # Only trusted repository functions, never generated code, run here.
        module = ast.Module(body=selected, type_ignores=[])
        exec(compile(module, f"git:{commit}:{path}", "exec"), namespace)
    return namespace["build_intervention_prompt"], sources


def decide(history, checks, condition, max_rounds=3):
    """Return reachable stop, branch input round, and reason (without selection)."""
    for i, (old, new, feedback_equal, verified) in enumerate(checks):
        if new:
            return i, None, "initial_new_pass_stop" if i == 0 and not old else "reachable_saved_stop"
        if condition not in CORRECTIONS:
            return i, None, "single_generation_condition"
        if i >= max_rounds:
            return i, None, "correction_limit"
        if old:
            return None, i + 1, "old_pass_new_fail_missing_continuation"
        if not verified:
            return None, 1, "historical_prompt_unverified_restart_shared_initial"
        if not feedback_equal:
            return None, i + 1, "first_feedback_divergence"
    return None, len(history), "missing_saved_continuation"


def run():
    validation = json.loads((WORK / "validation_report.json").read_text())
    if validation["status"] != "passed" or validation["unknown_causes_unresolved"]:
        raise ValueError("validation gate closed")
    status = json.loads((SOURCE / "run_status.json").read_text())
    plan, stored = read_db(__import__('pathlib').Path(status["checkpoint_dir"]) / "checkpoint.sqlite3")
    if digest(plan) != PLAN_HASH:
        raise ValueError("wrong source plan")
    results = {k: json.loads(t) for k, _, _, t, _ in stored}
    public_rounds, impacts, reconstructed, manifests, candidates = [], [], [], [], []
    private_prompts = []
    unchanged = defaultdict(dict)
    groups = defaultdict(list)
    for case in plan["cases"]:
        groups[case["record_key"]].append(case)
    raw_sources, original_sources, historical = {}, {}, {}
    for source in plan["sources"]:
        path = ROOT / source
        manifest = json.loads((path / "manifest.json").read_text())
        config = json.loads((path / "experiment_config.json").read_text())
        original = {}
        backup_info = []
        backup_hashes = {}
        legacy_report = path / "reclassification_report.json"
        if legacy_report.exists():
            report = json.loads(legacy_report.read_text())
            backup_hashes[report["input_file"]] = report["input_sha256"]
        for report_path in (ROOT / "docs/additional_nameerror_reclassification.json", ROOT / "docs/additional_remaining_reclassification.json"):
            report = json.loads(report_path.read_text())
            if report["experiment_id"] == config["experiment_id"]:
                backup_hashes[__import__('pathlib').Path(report["backup"]).name] = report["backup_sha256"]
        # Earliest backups win for a matching record; later rows may not exist yet.
        for backup in sorted(path.glob("raw.*.jsonl"), key=lambda p: p.stat().st_mtime_ns):
            if backup.name not in backup_hashes or sha(backup) != backup_hashes[backup.name]:
                raise ValueError("historical raw backup lacks matching recorded hash")
            backup_info.append({"path": str(backup.relative_to(ROOT)), "sha256": sha(backup)})
            for line in backup.read_text().splitlines():
                row = json.loads(line)
                original.setdefault(identity(row), row)
        raw_sources[source] = {identity(r): r for r in map(json.loads, (path / "raw.jsonl").read_text().splitlines())}
        for key, row in raw_sources[source].items():
            if row["condition_id"] in CORRECTIONS:
                baseline = raw_sources[source][(*key[:3], "baseline")]
                if row["rounds"][0]["extracted_code"] != baseline["rounds"][0]["extracted_code"]:
                    raise ValueError("baseline/R/F/D shared initial code mismatch")
        original_sources[source] = original
        function, source_hashes = archived_functions(manifest["git_commit"])
        task_hashes = {}
        tasks_same = True
        for file in sorted((ROOT / "tasks").glob("*.py")):
            old = subprocess.check_output(["git", "show", f"{manifest['git_commit']}:{file.relative_to(ROOT)}"])
            task_hashes[str(file.relative_to(ROOT))] = __import__('hashlib').sha256(old).hexdigest()
            tasks_same &= old == file.read_bytes()
        system = subprocess.check_output(["git", "show", f"{manifest['git_commit']}:prompts/system.txt"])
        fingerprints = manifest["prompt_fingerprints"]
        verified = (tasks_same and source_hashes["harness/interventions/prompts.py"] == fingerprints["interventions_py_sha256"]
                    and sha_text(system.decode()) == fingerprints["system_txt_sha256"])
        historical[source] = function, verified, config
        auto = json.loads((path / "automation_report.json").read_text())
        manifests.append({"source_dir": source, "source_manifest_sha256": sha(path / "manifest.json"),
                          "raw_sha256": sha(path / "raw.jsonl"), "config_sha256": sha(path / "experiment_config.json"),
                          "automation_sha256": sha(path / "automation_report.json"),
                          "git_commit": manifest["git_commit"], "schema_version": manifest["schema_version"],
                          "archived_prompt_functions": source_hashes, "archived_tasks": task_hashes,
                          "initial_prompt_source_verified": verified, "pre_migration_backups": backup_info,
                          "model_digests": {"ollama:" + m["name"]: m["digest"] for m in auto.get("shared_server", {}).get("models", [])},
                          "generation_settings": config["generation_settings"], "temperature": config["temperature"],
                          "max_rounds": config["max_rounds"], "actual_request_log_available": False})
    for record_key, history in groups.items():
        first = history[0]
        source = first["source_dir"]
        row = raw_sources[source][identity(first)]
        original = original_sources[source].get(identity(first), row)
        function, prompt_source_verified, config = historical[source]
        condition, task = first["condition_id"], get_task(first["task_id"])
        checks, per_round = [], []
        for c in history:
            index = c["round"]
            entry = row["rounds"][index]
            old = original["rounds"][index] if index < len(original["rounds"]) else entry
            verified = prompt_source_verified and old["extracted_code"] == entry["extracted_code"]
            if entry.get("original_error_category") and original is row:
                verified = False  # A read-time migration is not historical feedback.
            new = results[c["key"]]["primary"]
            old_prompt = new_prompt = ""
            comparable = condition in CORRECTIONS and index < config["max_rounds"] and not old["L3"] and not new["L3"]
            if comparable:
                try:
                    old_prompt = function(condition, task, old["extracted_code"], event(old))
                    new_prompt = build_intervention_prompt(condition, task, entry["extracted_code"], event(new))
                except (KeyError, ValueError, TypeError, AttributeError):
                    verified = False
                private_prompts.append({"key": c["key"], "old_reconstructed_prompt": old_prompt,
                                        "new_prompt": new_prompt, "verified": verified,
                                        "actually_consumed_old": index < len(history) - 1,
                                        "evidence": "archived_functions_and_original_saved_evaluation; not_request_capture"})
            equal = old_prompt == new_prompt
            # No input is sent after terminal or successful rounds.
            checks.append((bool(old["L3"]), bool(new["L3"]), equal, verified))
            detail = {k: c[k] for k in ("key", "record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id", "round", "code_sha256")}
            detail.update(old_L3=old["L3"], new_L3=new["L3"],
                          old_error_category=old["error_category"], new_error_category=new["error_category"],
                          historical_prompt_evidence="archived_reconstruction" if verified else "unverified",
                          old_feedback_actually_consumed=index < len(history) - 1,
                          feedback_comparable=comparable, feedback_equal=equal if comparable and verified else "",
                          old_prompt_sha256=sha_text(old_prompt) if old_prompt else "",
                          new_prompt_sha256=sha_text(new_prompt) if new_prompt else "",
                          old_stop=bool(old["L3"] or condition not in CORRECTIONS or index == config["max_rounds"]),
                          new_stop=bool(new["L3"] or condition not in CORRECTIONS or index == config["max_rounds"]))
            public_rounds.append(detail); per_round.append(detail)
        stop, branch, reason = decide(history, checks, condition, config["max_rounds"])
        changed = any(r["old_L3"] != r["new_L3"] or r["old_stop"] != r["new_stop"] or
                      r["feedback_equal"] is False or r["historical_prompt_evidence"] == "unverified" for r in per_round)
        common = {"record_key": record_key, **{k: first[k] for k in ("source_dir", "model_spec", "task_id", "base_seed", "condition_id")}}
        old_cost = {f"old_{k}": sum(r.get(k, 0) for r in row["rounds"]) for k in ("tokens_in", "tokens_out", "elapsed_sec")}
        impacts.append(common | {"initial_code_sha256": first["code_sha256"], "affected": changed,
                                 "branch_input_round": branch if branch is not None else "", "reason": reason,
                                 "reachable_saved_stop_round": stop if stop is not None else "",
                                 "generation_cap": config["max_rounds"] - branch + 1 if branch is not None else 0,
                                 "prefix_rounds": branch if branch is not None else len(history), **old_cost})
        if branch is not None:
            # Prefix inputs are retained privately with explicit reconstruction provenance.
            candidates.append(common | {"branch_input_round": branch, "generation_cap": config["max_rounds"] - branch + 1,
                                        "initial_code_sha256": first["code_sha256"], "reason": reason,
                                        "prefix_code_hashes": [c["code_sha256"] for c in history[:branch]],
                                        "prefix_input_prompt_sha256": [sha_text(build_initial_prompt("baseline", task))] +
                                            [r["old_prompt_sha256"] for r in per_round[:branch - 1]],
                                        "required_conditions": "saved_digest+generation_parameters+verified_prefix+isolated_primary_v4",
                                        "max_correction_round": config["max_rounds"]})
        reconstructed.append(common | {"status": "requires_partial_rerun" if branch is not None else "reconstructed",
                                       "stop_round": stop if stop is not None else "", "success": checks[stop][1] if stop is not None else "",
                                       "old_final_success": checks[-1][0], "saved_rescored_final_success": checks[-1][1],
                                       "saved_first_success_round": next((i for i, x in enumerate(checks) if x[1]), ""),
                                       "earlier_divergence_blocks_saved_success": branch is not None and any(x[1] for x in checks[branch:]),
                                       **old_cost,
                                       **{f"reconstructed_{k}": sum(r.get(k, 0) for r in row["rounds"][:stop + 1]) if stop is not None else ""
                                          for k in ("tokens_in", "tokens_out", "elapsed_sec")},
                                       "new_generation_tokens": 0})
        if not changed and condition != "preventive_spec":
            unchanged[(source, first["model_spec"], first["task_id"], first["base_seed"])][condition] = record_key
    eligible = defaultdict(list)
    for group, conditions in unchanged.items():
        if set(conditions) == {"baseline", *CORRECTIONS}:
            eligible[(group[1], group[2])].append((group, conditions))
    rng = random.Random(20261015)
    sample = []
    for stratum in sorted(eligible):
        group, conditions = rng.choice(sorted(eligible[stratum]))
        for condition, record_key in sorted(conditions.items()):
            sample.append({"source_dir": group[0], "model_spec": group[1], "task_id": group[2],
                           "base_seed": group[3], "condition_id": condition, "record_key": record_key,
                           "stratum_eligible_groups": len(eligible[stratum]), "selection_seed": 20261015})
    for name, data in (("round_impact_audit.csv", public_rounds), ("impact_cases.csv", impacts),
                       ("reconstructed_stops.csv", reconstructed), ("unchanged_sample.csv", sample)):
        write_csv(WORK / name, data)
    manifest = {"schema": "partial_followup_v1", "source_plan_sha256": PLAN_HASH,
                "selection_rule": "all_stop_or_feedback_divergences_or_unverified_history; no_outcome_selection",
                "sources": manifests, "cases": candidates, "generation_cap": sum(c["generation_cap"] for c in candidates),
                "cases_count": len(candidates), "shared_initial": "baseline/R/F/D", "independent_initial": "P",
                "sample_selection_seed": 20261015, "sample_groups": len(sample) // 4,
                "impact_csv_sha256": sha(WORK / "impact_cases.csv"), "round_audit_sha256": sha(WORK / "round_impact_audit.csv"),
                "unchanged_sample_sha256": sha(WORK / "unchanged_sample.csv"),
                "prompt_provenance": "archived git functions + original evaluation and saved code; not network request logs",
                "initial_prompt_provenance": "archived task/system text and saved shared initial code; never regenerated"}
    (WORK / "settings_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (PRIVATE / "prompt_reconstructions.json").write_text(json.dumps(private_prompts, ensure_ascii=False, indent=2))
    report = {"records": len(impacts), "rounds": len(public_rounds), "affected_records": sum(r["affected"] for r in impacts),
              "partial_cases": len(candidates), "generation_cap": manifest["generation_cap"],
              "reasons": dict(Counter(r["reason"] for r in impacts)), "sample_groups": len(sample) // 4,
              "unverified_rounds": sum(r["historical_prompt_evidence"] == "unverified" for r in public_rounds),
              "same_L3_feedback_changed_rounds": sum(r["old_L3"] == r["new_L3"] and r["feedback_equal"] is False for r in public_rounds),
              "manifest_sha256": sha(WORK / "settings_manifest.json"), "llm_requests": 0}
    (WORK / "impact_sanity_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
