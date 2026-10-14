"""Validate the full historical catalog without executing generated code.

Execution is deliberately bounded to at most 48 explicitly selected rounds.
Infrastructure failures stop the batch and block resumption in this checkpoint.
"""
import ast
import hashlib
from itertools import product
import json
from pathlib import Path

from harness.isolated_evaluation import ROOT, Limits, isolated_evaluate, profile
from harness.reevaluation_checkpoint import Checkpoint, digest
from scripts.pilot_reevaluation import SNAPSHOT, SNAPSHOT_HASH, sha

MAX_BATCH_ROUNDS = 48


def build_plan(snapshot=SNAPSHOT, limits=Limits()):
    if snapshot == SNAPSHOT and sha(snapshot) != SNAPSHOT_HASH:
        raise ValueError("snapshot mismatch")
    frozen = json.loads(Path(snapshot).read_text())
    cases, sources, records = [], {}, 0
    lengths, syntax_failures, legacy_empty_hashes = [], 0, 0
    for run in frozen["runs"]:
        directory = run["source_dir"]
        path = ROOT / directory / "raw.jsonl"
        config_path = path.parent / "experiment_config.json"
        if sha(path) != run["raw_sha256"]:
            raise ValueError("source hash mismatch")
        config = json.loads(config_path.read_text())
        if config != run["config"]:
            raise ValueError("saved config differs from snapshot")
        conditions = config["conditions"]
        seeds = range(config["seeds"]["start"], config["seeds"]["stop"])
        expected = set(product(config["models"], config["tasks"], seeds, conditions))
        seen = set()
        with path.open() as handle:
            for line_number, line in enumerate(handle, 1):
                row = json.loads(line)
                identity = (row["model_spec"], row["task_id"], row["base_seed"], row["condition_id"])
                if identity in seen or identity not in expected:
                    raise ValueError("duplicate or unexpected historical record")
                seen.add(identity)
                selector = {"source_dir": directory, **dict(zip(("model_spec", "task_id", "base_seed", "condition_id"), identity))}
                record_key = digest(selector)
                rounds = row["rounds"]
                if not rounds or len(rounds) > config["max_rounds"] + 1 or [r["round"] for r in rounds] != list(range(len(rounds))):
                    raise ValueError("invalid historical rounds")
                if row["extracted_code"] != rounds[-1]["extracted_code"]:
                    raise ValueError("final code differs from last round")
                for entry in rounds:
                    code = entry["extracted_code"]
                    code_hash = hashlib.sha256(code.encode()).hexdigest()
                    if entry["code_sha256"] != code_hash:
                        if code == "" and entry["code_sha256"] == "":
                            legacy_empty_hashes += 1
                        else:
                            raise ValueError("historical code hash mismatch")
                    size = len(code.encode())
                    if size > 1024 ** 2:
                        raise ValueError("code exceeds sandbox input cap")
                    try:
                        ast.parse(code)
                    except SyntaxError:
                        syntax_failures += 1  # Model result, not a corrupt catalog.
                    lengths.append(size)
                    cases.append({"key": record_key + ":" + str(entry["round"]), "record_key": record_key,
                                  **selector, "round": entry["round"], "line_number": line_number,
                                  "is_final": entry["round"] == len(rounds) - 1, "code_sha256": code_hash,
                                  "stored_code_sha256": entry["code_sha256"],
                                  "code_bytes": size, "old_primary": {k: entry[k] for k in ("L0", "L1", "L2", "L3", "structure_match", "error_category")}})
        if seen != expected or len(seen) != run["records"]:
            raise ValueError("missing historical records")
        records += len(seen)
        sources[directory] = {"raw_sha256": run["raw_sha256"], "config_sha256": sha(config_path), "records": len(seen)}
    if len({c["key"] for c in cases}) != len(cases):
        raise ValueError("duplicate full-plan round key")
    return {"schema": "full_saved_code_plan_v1", "purpose": "preflight_only", "snapshot_sha256": sha(snapshot),
            "evaluator_profile": profile(limits), "sources": sources, "records": records, "cases": cases,
            "static_checks": {"rounds": len(cases), "max_code_bytes": max(lengths), "total_code_bytes": sum(lengths),
                              "model_syntax_failures": syntax_failures, "legacy_empty_code_hashes": legacy_empty_hashes,
                              "missing_records": 0, "duplicate_keys": 0},
            "stop_on_runtime_failure": True}


def verify_plan(plan, limits):
    if profile(limits) != plan["evaluator_profile"]:
        raise ValueError("evaluator profile mismatch")
    for source, hashes in plan["sources"].items():
        if sha(ROOT / source / "raw.jsonl") != hashes["raw_sha256"] or sha(ROOT / source / "experiment_config.json") != hashes["config_sha256"]:
            raise ValueError("source changed")


def execute_bounded_batch(plan, keys, checkpoint_dir, limits=Limits(), executor=isolated_evaluate):
    """No full-run loop; callers must explicitly choose at most 48 round keys."""
    if not 1 <= len(keys) <= MAX_BATCH_ROUNDS or len(set(keys)) != len(keys):
        raise ValueError("explicit unique batch of 1--48 rounds required")
    cases = {case["key"]: case for case in plan["cases"]}
    if any(key not in cases for key in keys):
        raise ValueError("unknown planned case")
    verify_plan(plan, limits)
    executed = 0
    with Checkpoint(checkpoint_dir, plan) as checkpoint:
        # A previously persisted infrastructure failure must never be skipped
        # while silently carrying on with later records.
        for key, result_text in checkpoint.db.execute("SELECT key,result FROM results WHERE state='completed'"):
            if json.loads(result_text)["runtime_status"] != "completed":
                return {"status": "blocked_runtime_failure", "failed_key": key, "executed": 0, "sanity": checkpoint.sanity()}
        for key in keys:
            case = cases[key]
            if not checkpoint.claim(key):
                continue
            source = ROOT / case["source_dir"] / "raw.jsonl"
            with source.open() as handle:
                line = next(line for number, line in enumerate(handle, 1) if number == case["line_number"])
            row = json.loads(line)
            code = row["rounds"][case["round"]]["extracted_code"]
            if hashlib.sha256(code.encode()).hexdigest() != case["code_sha256"]:
                raise ValueError("code changed")
            result = executor(code, case["task_id"], limits)
            checkpoint.finish(key, result)
            executed += 1
            verify_plan(plan, limits)
            if result["runtime_status"] != "completed":
                return {"status": "blocked_runtime_failure", "failed_key": key, "executed": executed, "sanity": checkpoint.sanity()}
        return {"status": "batch_completed", "executed": executed, "sanity": checkpoint.sanity()}
