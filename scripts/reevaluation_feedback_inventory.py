"""Exhaustive historical feedback inventory, including changed-stop rows.

Supplement the frozen selection audit without changing it or its generation
budget. New prompts derived from saved code are hypothetical, never attributed
to an unobserved new suffix. Full prompt bodies remain private.
"""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from harness.interventions import build_intervention_prompt
from harness.reevaluation_checkpoint import digest
from harness.run_state import atomic_json
from scripts.pilot_reevaluation import sha
from scripts.reevaluate_saved import write_csv
from scripts.reevaluation_impact_audit import archived_functions, event, identity, CORRECTIONS
from scripts.reevaluation_followup_validation import ROOT, SOURCE, WORK, PRIVATE, PLAN_HASH, read_db, sha_text
from tasks import get_task


def require_historical_fields(entry):
    required = {"L0", "L1", "error_category", "error_message", "L2_distance", "actual_distribution", "extracted_code"}
    if not required.issubset(entry) or (entry["L1"] and entry["L2_distance"] is None):
        raise ValueError("historical diagnostic fields missing or ambiguous; do not assert exact reconstruction")


def run():
    manifest = json.loads((WORK / "settings_manifest.json").read_text())
    if sha(WORK / "round_impact_audit.csv") != manifest["round_audit_sha256"]:
        raise ValueError("frozen selection audit changed")
    frozen = {r["key"]: r for r in csv.DictReader((WORK / "round_impact_audit.csv").open())}
    impacts = {r["record_key"]: r for r in csv.DictReader((WORK / "impact_cases.csv").open())}
    status = json.loads((SOURCE / "run_status.json").read_text())
    plan, stored = read_db(Path(status["checkpoint_dir"]) / "checkpoint.sqlite3")
    if digest(plan) != PLAN_HASH:
        raise ValueError("source identity mismatch")
    scored = {k: json.loads(t) for k, _, _, t, _ in stored}
    raw, originals, functions = {}, {}, {}
    for source in manifest["sources"]:
        directory = ROOT / source["source_dir"]
        if sha(directory / "raw.jsonl") != source["raw_sha256"]:
            raise ValueError("historical source changed")
        raw[source["source_dir"]] = [json.loads(line) for line in (directory / "raw.jsonl").read_text().splitlines()]
        original = {}
        for backup in source["pre_migration_backups"]:
            path = ROOT / backup["path"]
            if sha(path) != backup["sha256"]:
                raise ValueError("original feedback backup changed")
            for line in path.read_text().splitlines():
                r = json.loads(line); original.setdefault(identity(r), r)
        originals[source["source_dir"]] = original
        function, hashes = archived_functions(source["git_commit"])
        if hashes != source["archived_prompt_functions"]:
            raise ValueError("archived prompt function identity mismatch")
        for file, hashed in source["archived_tasks"].items():
            if sha(ROOT / file) != hashed:
                raise ValueError("task source differs from historical prompt source")
        functions[source["source_dir"]] = function
    public, private = [], []
    filled = 0
    for case in plan["cases"]:
        row = raw[case["source_dir"]][case["line_number"] - 1]
        original = originals[case["source_dir"]].get(identity(row), row)
        index, condition = case["round"], case["condition_id"]
        entry, old = row["rounds"][index], original["rounds"][index]
        if entry["extracted_code"] != old["extracted_code"] or sha_text(entry["extracted_code"]) != case["code_sha256"]:
            raise ValueError("historical input code mismatch")
        new = scored[case["key"]]["primary"]
        old_consumed = condition in CORRECTIONS and index < len(row["rounds"]) - 1
        new_hypothetical = condition in CORRECTIONS and index < 3 and not new["L3"]
        old_prompt = new_prompt = ""
        task = get_task(case["task_id"])
        if old_consumed:
            if old["L3"]:
                raise ValueError("historical continuation after primary success")
            require_historical_fields(old)
            old_prompt = functions[case["source_dir"]](condition, task, old["extracted_code"], event(old))
        if new_hypothetical:
            new_prompt = build_intervention_prompt(condition, task, entry["extracted_code"], event(new))
        previous = frozen[case["key"]]
        for name, prompt in (("old_prompt_sha256", old_prompt), ("new_prompt_sha256", new_prompt)):
            if previous[name] and sha_text(prompt) != previous[name]:
                raise ValueError("supplement contradicts the frozen audit")
        if old_consumed and not previous["old_prompt_sha256"]:
            if bool(old["L3"]) == bool(new["L3"]):
                raise ValueError("new feedback divergence outside the fixed selection")
            filled += 1
        impact = impacts[case["record_key"]]
        branch = int(impact["branch_input_round"]) if impact["branch_input_round"] else None
        stop = int(impact["reachable_saved_stop_round"]) if impact["reachable_saved_stop_round"] else None
        unreachable = index >= branch if branch is not None else index > stop
        public.append({k: case[k] for k in ("key", "record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id", "round", "code_sha256")} | {
            "old_feedback_actually_consumed": old_consumed,
            "old_consumed_prompt_reconstructed_sha256": sha_text(old_prompt) if old_prompt else "",
            "new_saved_code_hypothetical_prompt_sha256": sha_text(new_prompt) if new_prompt else "",
            "saved_code_unreachable_in_new_path": unreachable,
            "old_prompt_evidence": "archived_function_and_original_saved_values; not_packet_capture" if old_consumed else "none_consumed",
            "new_prompt_evidence": "hypothetical_saved_code_feedback; actual_new_API_inputs_are_private" if new_prompt else "no_continuation_at_this_saved_output"})
        if old_prompt or new_prompt:
            private.append({"key": case["key"], "old_consumed_reconstructed_input": old_prompt,
                            "new_hypothetical_saved_code_input": new_prompt, "saved_code_unreachable_in_new_path": unreachable})
    old_count = sum(r["old_feedback_actually_consumed"] for r in public)
    if len(public) != 9517 or old_count != 4517:
        raise ValueError("feedback inventory count mismatch")
    write_csv(WORK / "saved_feedback_inventory.csv", public)
    atomic_json(PRIVATE / "exhaustive_feedback_inputs.json", {"prompts": private})
    result = {"status": "passed", "captured_at_utc": datetime.now(timezone.utc).isoformat(), "rounds": len(public),
              "historical_consumed_feedback_inputs": old_count, "missing_historical_fields": 0,
              "ambiguous_historical_null_distances": 0, "historical_prompts_added_at_changed_stops": filled,
              "frozen_selection_hashes_verified": True, "case_selection_unchanged": True, "generation_cap_unchanged": 773,
              "frozen_manifest_sha256": sha(WORK / "settings_manifest.json"), "inventory_sha256": sha(WORK / "saved_feedback_inventory.csv"),
              "llm_requests": 0, "raw_published": False, "generated_code_published": False}
    atomic_json(WORK / "saved_feedback_inventory_sanity.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
