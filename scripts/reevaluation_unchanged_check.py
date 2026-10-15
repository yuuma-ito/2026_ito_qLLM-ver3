"""Execute the frozen stratified unchanged sample, without any generation."""
from collections import Counter
import csv
import json
from pathlib import Path

from harness.interventions import build_intervention_prompt
from harness.isolated_evaluation import isolated_evaluate, profile
from harness.reevaluation_checkpoint import canonical
from harness.run_state import atomic_json, file_lock
from scripts.pilot_reevaluation import sha
from scripts.reevaluate_saved import write_csv
from scripts.reevaluation_followup_validation import ROOT, SOURCE, WORK, PRIVATE, read_db, sha_text
from scripts.reevaluation_impact_audit import event


def run():
    cache = PRIVATE / "unchanged"
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    with file_lock(cache / "driver.lock", nonblocking=True):
        manifest = json.loads((WORK / "settings_manifest.json").read_text())
        if sha(WORK / "unchanged_sample.csv") != manifest["unchanged_sample_sha256"]:
            raise ValueError("frozen sample changed")
        samples = list(csv.DictReader((WORK / "unchanged_sample.csv").open()))
        selected = {r["record_key"] for r in samples}
        source_status = json.loads((SOURCE / "run_status.json").read_text())
        plan, stored = read_db(Path(source_status["checkpoint_dir"]) / "checkpoint.sqlite3")
        if profile() != plan["evaluator_profile"]:
            raise ValueError("sample evaluator profile mismatch")
        old = {k: json.loads(t) for k, _, _, t, _ in stored}
        audit = {r["key"]: r for r in csv.DictReader((WORK / "round_impact_audit.csv").open())}
        sources = {}
        for source in manifest["sources"]:
            raw = ROOT / source["source_dir"] / "raw.jsonl"
            if sha(raw) != source["raw_sha256"]:
                raise ValueError("sample source changed")
            sources[source["source_dir"]] = [json.loads(line) for line in raw.read_text().splitlines()]
        outputs, used = [], set()
        for case in plan["cases"]:
            if case["record_key"] not in selected:
                continue
            code = sources[case["source_dir"]][case["line_number"] - 1]["rounds"][case["round"]]["extracted_code"]
            if sha_text(code) != case["code_sha256"]:
                raise ValueError("sample code hash mismatch")
            # Reuse only identical code/task within this selected sample; all 387
            # selected rounds remain represented. This is not a 5000-case rerun.
            key = case["task_id"] + "_" + case["code_sha256"]
            file = cache / (key + ".json")
            if file.exists():
                result = json.loads(file.read_text())
                if sha(file) != file.with_suffix(".sha256").read_text().strip():
                    raise ValueError("sample checkpoint hash mismatch")
            else:
                marker = file.with_suffix(".started")
                if marker.exists():
                    raise ValueError("sample evaluation interrupted; no automatic retry")
                marker.write_text(case["key"])
                result = isolated_evaluate(code, case["task_id"])
                atomic_json(file, result)
                file.with_suffix(".sha256").write_text(sha(file) + "\n")
            used.add(key)
            if result["runtime_status"] != "completed":
                raise ValueError("sample infrastructure failure; preserved separately")
            primary = json.loads(canonical(result))["primary"]
            saved = old[case["key"]]["primary"]
            keys = ("L0", "L1", "L2", "L3", "structure_match", "error_category", "exception_type", "error_message", "actual_distribution")
            if any(primary.get(k) != saved.get(k) for k in keys):
                raise ValueError("sample primary replay disagreement: " + case["key"])
            row = audit[case["key"]]
            prompt_equal = True
            if row["new_prompt_sha256"]:
                from tasks import get_task
                prompt = build_intervention_prompt(case["condition_id"], get_task(case["task_id"]), code, event(primary))
                prompt_equal = sha_text(prompt) == row["new_prompt_sha256"]
            if not prompt_equal:
                raise ValueError("sample feedback replay disagreement")
            auxiliary = result["auxiliary"]
            outputs.append({k: case[k] for k in ("key", "record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id", "round", "code_sha256")} | {
                "runtime_status": result["runtime_status"], "primary_replay_equal": True,
                "feedback_replay_equal": prompt_equal, "new_L3": primary["L3"],
                "auxiliary_status": auxiliary["status"], "primary_pass_auxiliary_fail": bool(primary["L3"] and auxiliary["status"] == "fail"),
                "auxiliary_changes_primary": False, "sample_execution_key": key})
            atomic_json(cache / "progress.json", {"completed_rounds": len(outputs), "planned_rounds": sum(c["record_key"] in selected for c in plan["cases"]),
                                                  "independent_executions": len(used)})
        groups = [r for r in samples if r["condition_id"] == "baseline"]
        if len(groups) > 50 or len(groups) != manifest["sample_groups"] or len(selected) != 4 * len(groups):
            raise ValueError("sample group count mismatch")
        write_csv(WORK / "unchanged_validation.csv", outputs)
        report = {"status": "passed", "selection_seed": 20261015, "groups": len(groups), "records": len(selected),
                  "rounds": len(outputs), "independent_code_task_executions": len(used), "llm_requests": 0,
                  "primary_disagreements": 0, "feedback_disagreements": 0, "stop_disagreements": 0,
                  "auxiliary_statuses": dict(Counter(r["auxiliary_status"] for r in outputs)),
                  "primary_pass_auxiliary_fail": sum(r["primary_pass_auxiliary_fail"] for r in outputs),
                  "source_group_counts": dict(Counter(r["source_dir"] for r in groups)),
                  "seed_group_counts": dict(Counter(r["base_seed"] for r in groups)),
                  "sample_sha256": manifest["unchanged_sample_sha256"],
                  "limitations": "存在する50モデル×task層で各1共有初期。出典・seedは均等でない。補助判定は独立オラクルだが同じQPY再構築回路を用いる。抽出確認を全件の妥当性証明と扱わない。"}
        atomic_json(WORK / "unchanged_sanity_report.json", report)
        return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
