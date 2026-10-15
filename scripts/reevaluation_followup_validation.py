"""Read-only validation of the pinned reevaluation; never repairs its checkpoint."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3

from harness.isolated_evaluation import ROOT, Limits, isolated_evaluate, profile
from harness.reevaluation_checkpoint import canonical, digest
from harness.reevaluation_plan import build_plan
from scripts.pilot_reevaluation import sha

SOURCE = ROOT / "docs/analysis/reevaluation_full_20261014T141718Z"
WORK = ROOT / "docs/analysis/reevaluation_followup_20261015"
PRIVATE = ROOT / ".cache/reevaluation_followup/reevaluation_full_20261014T141718Z"
PLAN_HASH = "df7dc9a5adf303d22b97e34ec03b85dba10c32f7fba456bd19746a5bcf496b51"


def read_db(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("checkpoint integrity failure")
        plan = json.loads(db.execute("SELECT manifest FROM metadata").fetchone()[0])
        rows = db.execute("SELECT key,code_hash,state,result,result_hash FROM results ORDER BY key").fetchall()
    return plan, rows


def validate_rows(plan, rows):
    expected = {c["key"]: c for c in plan["cases"]}
    if len(expected) != len(plan["cases"]):
        raise ValueError("duplicate planned round")
    seen = set()
    for key, code, state, text, hashed in rows:
        if key in seen or key not in expected or code != expected[key]["code_sha256"]:
            raise ValueError("unexpected/duplicate/mismatched round")
        seen.add(key)
        if state != "completed" or not text or hashlib.sha256(text.encode()).hexdigest() != hashed:
            raise ValueError("incomplete or damaged result")
        if canonical(json.loads(text)) != text:
            raise ValueError("noncanonical result")
    if seen != set(expected):
        raise ValueError("missing round")


def preserved_rows(before, after):
    old = {r[0]: r for r in before if r[2] == "completed"}
    new = {r[0]: r for r in after}
    if len(old) != 3740 or any(new.get(k) != v for k, v in old.items()):
        raise ValueError("original 3740 results changed")
    original_digest = digest(sorted((r[0], r[4]) for r in old.values()))
    if original_digest != "0baca45b8adfd66c4e5cae0fa90190af78bf876c5b3af818140904b862bce533":
        raise ValueError("documented pre-interruption result digest mismatch")
    return len(old)


def cause(primary):
    if primary.get("failure_stage") != "exec" or primary.get("L0") is not False:
        raise ValueError("unresolved unknown failure stage")
    if primary.get("exception_type") == "NameError" and primary.get("error_message") == "NameError: name 'sim' is not defined":
        return "model_top_level_undefined_sim"
    # Reviewed after partial case 216 stopped: AST has an Aer load without an
    # import/definition; isolated replay reproduces the identical primary error.
    # Annotation only: the frozen evaluator and its unknown_error label remain.
    if primary.get("exception_type") == "NameError" and primary.get("error_message") == "NameError: name 'Aer' is not defined":
        return "model_top_level_undefined_Aer"
    if primary.get("exception_type") == "QiskitError" and primary.get("error_message") in {
        "QiskitError: 'Data for experiment \"\" could not be found.'",
        "QiskitError: 'Data for experiment \"0\" could not be found.'",
    }:
        return "model_top_level_result_lookup_without_saved_measurements"
    raise ValueError("unresolved unknown failure")


def run():
    from scripts.reevaluate_saved import write_csv
    WORK.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    status = json.loads((SOURCE / "run_status.json").read_text())
    if status["status"] != "completed" or status["plan_sha256"] != PLAN_HASH:
        raise ValueError("source not complete or identity mismatch")
    directory = Path(status["checkpoint_dir"])
    with (directory / "driver.lock").open("r") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, rows = read_db(directory / "checkpoint.sqlite3")
        if digest(plan) != PLAN_HASH or len(rows) != 9517 or plan["records"] != 5000:
            raise ValueError("pinned count or hash mismatch")
        validate_rows(plan, rows)
        if profile() != plan["evaluator_profile"] or sha(ROOT / "scripts/reevaluate_saved.py") != plan["driver_sha256"]:
            raise ValueError("profile or driver changed")
        rebuilt = build_plan()
        for field in ("cases", "sources", "records", "static_checks", "snapshot_sha256"):
            if rebuilt[field] != plan[field]:
                raise ValueError("source catalog changed: " + field)
        previous_plan, before = read_db(directory / "checkpoint.before_tmux_resume.sqlite3")
        if previous_plan != plan:
            raise ValueError("backup plan mismatch")
        preserved = preserved_rows(before, rows)
        artifacts = json.loads((SOURCE / "final/artifact_manifest.json").read_text())
        for name, identity in artifacts["files"].items():
            file = SOURCE / "final" / name
            if Path(name).name != name or sha(file) != identity["sha256"] or file.stat().st_size != identity["bytes"]:
                raise ValueError("artifact mismatch")
        summary = json.loads((SOURCE / "final/summary.json").read_text())
        if summary["shared_initial_judgment_mismatches"] or summary["runtime_failures"]:
            raise ValueError("unresolved mismatch/runtime failure")
        cases = {c["key"]: c for c in plan["cases"]}
        triage, replays = [], []
        for key, _, _, text, _ in rows:
            result = json.loads(text)
            if result["runtime_status"] != "completed":
                raise ValueError("runtime failure")
            p = result["primary"]
            if p["L3"] != bool(p["L0"] and p["L1"] and p["L2"] and p["structure_match"]):
                raise ValueError("inconsistent primary")
            if p["error_category"] != "unknown_error":
                continue
            reason = cause(p)
            c = cases[key]
            raw = json.loads((ROOT / c["source_dir"] / "raw.jsonl").read_text().splitlines()[c["line_number"] - 1])
            code = raw["rounds"][c["round"]]["extracted_code"]
            if sha_text(code) != c["code_sha256"]:
                raise ValueError("replay input mismatch")
            replay = isolated_evaluate(code, c["task_id"], Limits())
            replays.append({"key": key, "result": replay})
            if replay["runtime_status"] != "completed" or any(replay["primary"].get(k) != p.get(k) for k in (
                "L0", "L1", "L2", "L3", "structure_match", "error_category", "failure_stage", "exception_type", "error_message")):
                raise ValueError("unknown failure replay mismatch")
            triage.append({k: c[k] for k in ("key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id", "round", "code_sha256")} | {
                "original_category": p["error_category"], "cause": reason,
                "failure_stage": p["failure_stage"], "exception_type": p["exception_type"],
                "replay_confirmed": True, "primary_changed": False, "resolved_for_analysis": True})
        if len(triage) != 12:
            raise ValueError("unexpected unknown scope")
        write_csv(WORK / "unknown_failure_triage.csv", triage)
        (PRIVATE / "validation_replays.json").write_text(json.dumps(replays, ensure_ascii=False, indent=2))
        report = dict(captured_at_utc=datetime.now(timezone.utc).isoformat(), status="passed",
                      plan_sha256=PLAN_HASH, records=5000, rounds=9517, missing=0, duplicates=0, unexpected=0,
                      sources_unchanged=True, artifact_hashes_verified=True, driver_lock_released=True,
                      evaluator_profile_verified=True, mixed_profiles=False, original_completed_rounds_preserved=preserved,
                      original_results_digest="0baca45b8adfd66c4e5cae0fa90190af78bf876c5b3af818140904b862bce533",
                      runtime_failures=0, shared_initial_mismatches=0, unknown_primary_labels_preserved=12,
                      unknown_causes_resolved=12, unknown_causes_unresolved=0,
                      cause_counts=dict(Counter(r["cause"] for r in triage)), llm_requests=0,
                      limits="原因注記は別表。元unknown_error分類と主判定を保持し、再分類版の全件再採点と呼ばない。")
        (WORK / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
