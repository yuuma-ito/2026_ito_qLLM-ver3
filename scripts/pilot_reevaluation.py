"""Only a small saved-code pilot. There is deliberately no full-run option."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from harness.isolated_evaluation import ROOT, Limits, isolated_evaluate, profile
from harness.reevaluation_checkpoint import Checkpoint, canonical, digest

SNAPSHOT = ROOT / "docs/presentation_sources/20261013T_pooled_verified/results_snapshot.json"
SNAPSHOT_HASH = "cb7e9532a4dea52e763f43eb7d366707bcb37c67eb5e29d094a1e3fd872008f0"
MAX_RECORDS = 12
MAX_ROUNDS = 48


def immutable_report(path, value):
    """Atomic publish with exclusive creation, including concurrent writers."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ValueError("public pilot report is immutable") from None
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_cases(selection, snapshot=SNAPSHOT):
    if not 1 <= len(selection) <= MAX_RECORDS:
        raise ValueError("pilot is limited to 1--12 explicitly selected records")
    if snapshot == SNAPSHOT and sha(snapshot) != SNAPSHOT_HASH:
        raise ValueError("fixed historical snapshot hash mismatch")
    frozen = json.loads(Path(snapshot).read_text())
    sources = {}
    records = []
    seen = set()
    for selected in selection:
        identity = canonical(selected)
        if identity in seen:
            raise ValueError("duplicate pilot selection")
        seen.add(identity)
        run = next((r for r in frozen["runs"] if r["source_dir"] == selected["source_dir"]), None)
        if run is None:
            raise ValueError("source is not in fixed snapshot")
        path = ROOT / run["source_dir"] / "raw.jsonl"
        if sha(path) != run["raw_sha256"]:
            raise ValueError("historical raw hash mismatch")
        config_path = path.parent / "experiment_config.json"
        sources[run["source_dir"]] = {"raw_sha256": run["raw_sha256"], "config_sha256": sha(config_path)}
        matches = []
        source_keys = set()
        for line in path.read_text().splitlines():
            row = json.loads(line)
            key = (row["model_spec"], row["task_id"], row["base_seed"], row["condition_id"])
            if key in source_keys:
                raise ValueError("duplicate historical record")
            source_keys.add(key)
            if all(row[k] == selected[k] for k in ("model_spec", "task_id", "base_seed", "condition_id")):
                matches.append(row)
        if len(matches) != 1:
            raise ValueError("pilot selection must match exactly one saved record")
        records.append((selected, matches[0]))
    cases, codes = [], {}
    for selected, row in records:
        rounds = row["rounds"]
        if not rounds or len(rounds) > 4:
            raise ValueError("invalid historical round count")
        indices = [entry["round"] for entry in rounds]
        if indices != list(range(len(rounds))):
            raise ValueError("missing or duplicate historical rounds")
        record_key = digest(selected)
        for entry in rounds:
            code = entry["extracted_code"]
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            if entry.get("code_sha256") != code_hash:
                raise ValueError("saved code hash mismatch")
            key = record_key + ":" + str(entry["round"])
            cases.append({"key": key, "record_key": record_key, **selected, "round": entry["round"],
                          "is_final": entry["round"] == len(rounds) - 1, "code_sha256": code_hash,
                          "old_primary": {k: entry.get(k) for k in ("L0", "L1", "L2", "structure_match", "L3", "error_category")}})
            codes[key] = code
    if len(cases) > MAX_ROUNDS:
        raise ValueError("pilot round cap exceeded")
    return {"schema": "saved_code_reevaluation_v1", "purpose": "pilot_only", "snapshot_sha256": sha(snapshot),
            "sources": sources, "selection": selection, "cases": cases}, codes


def run_pilot(selection, checkpoint_dir, report_path, limits=Limits(), executor=isolated_evaluate, *, snapshot=SNAPSHOT):
    destination = Path(report_path)
    if destination.exists():
        raise ValueError("public pilot report is immutable; use a new report path")
    # Source/scope/hash validation must finish before any code is executed.
    manifest, codes = collect_cases(selection, snapshot)
    manifest["evaluator_profile"] = profile(limits)
    start = time.monotonic()
    executed = 0
    with Checkpoint(checkpoint_dir, manifest) as checkpoint:
        for case in manifest["cases"]:
            if checkpoint.claim(case["key"]):
                result = executor(codes[case["key"]], case["task_id"], limits)
                checkpoint.finish(case["key"], result)
                executed += 1
        outputs = []
        for case in manifest["cases"]:
            result = checkpoint.completed(case["key"])
            primary, auxiliary = result.get("primary", {}), result.get("auxiliary", {})
            outputs.append({**case, "runtime_status": result["runtime_status"],
                            "primary": {k: primary.get(k) for k in ("L0", "L1", "L2", "structure_match", "L3", "L2_distance", "error_category", "failure_stage", "exception_type")},
                            "auxiliary": auxiliary, "isolation": result.get("isolation"),
                            "build_seconds": result.get("build_seconds", 0), "oracle_or_failure_seconds": result.get("seconds", 0)})
            outputs[-1]["cpu_seconds"] = result.get("cpu_seconds", 0) + result.get("build_cpu_seconds", 0)
        sanity = checkpoint.sanity()
    for source, hashes in manifest["sources"].items():
        if sha(ROOT / source / "raw.jsonl") != hashes["raw_sha256"] or sha(ROOT / source / "experiment_config.json") != hashes["config_sha256"]:
            raise ValueError("historical sources changed during pilot")
    if profile(limits) != manifest["evaluator_profile"]:
        raise ValueError("evaluator files changed during pilot; new checkpoint required")
    failures = [row["key"] for row in outputs if row["runtime_status"] != "completed"]
    histories = []
    for record_key in dict.fromkeys(row["record_key"] for row in outputs):
        history = [row for row in outputs if row["record_key"] == record_key]
        old = [row["old_primary"]["L3"] for row in history]
        new = [row["primary"]["L3"] for row in history]
        complete = all(row["runtime_status"] == "completed" for row in history)
        histories.append({"record_key": record_key, "recorded_rounds": len(history), "reevaluation_complete": complete,
                          "old_first_success_round": next((i for i, ok in enumerate(old) if ok), None),
                          "old_ever_success": any(old), "old_final_success": old[-1],
                          "new_first_success_round": next((i for i, ok in enumerate(new) if ok), None) if complete else None,
                          "new_ever_success": any(new) if complete else None, "new_final_success": new[-1] if complete else None,
                          "new_regression_observed": any(new[i-1] and not new[i] for i in range(1, len(new))) if complete else None})
    report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "manifest": manifest, "sanity": sanity,
              "executed_this_invocation": executed, "elapsed_seconds_this_invocation": time.monotonic() - start,
              "runtime_failures": failures, "outputs": outputs, "llm_requests": 0, "estimated_llm_cost_usd": 0,
              "histories": histories,
              "historical_feedback_policy": "saved codes only; no new feedback or unobserved rounds",
              "full_5000_started": False}
    immutable_report(destination, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    if not checkpoint.is_relative_to(ROOT / ".cache" / "reevaluation"):
        parser.error("checkpoint must be inside .cache/reevaluation")
    report = run_pilot(json.loads(args.selection.read_text()), checkpoint, args.report)
    print(json.dumps({"sanity": report["sanity"], "executed": report["executed_this_invocation"], "runtime_failures": len(report["runtime_failures"]), "report": str(args.report)}, ensure_ascii=False))
    return 0 if not report["runtime_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
