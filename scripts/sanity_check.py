"""ver2 実験結果の sanity check。"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from harness.experiment import load_config, parse_conditions, record_key, resolve_seeds, resolve_tasks, validate_config


def _load_rows(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def check_results(config: dict[str, Any], path: str | Path) -> dict[str, Any]:
    v = validate_config(config)
    all_rows = _load_rows(path) if Path(path).exists() else []
    rows = [r for r in all_rows if r.get("experiment_id") == v["experiment_id"]]
    errors: list[str] = []
    warnings: list[str] = []

    expected = {
        (v["experiment_id"], c.id, m, t.id, s)
        for c in v["conditions"]
        for m in v["models"]
        for t in v["tasks"]
        for s in v["seeds"]
    }
    keys = [record_key(r) for r in rows]
    counts = Counter(keys)
    duplicates = [k for k, n in counts.items() if n > 1]
    actual = set(keys)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)

    if duplicates:
        errors.append(f"duplicate records: {len(duplicates)}")
    if missing:
        errors.append(f"missing records: {len(missing)}")
    if unexpected:
        warnings.append(f"unexpected records: {len(unexpected)}")

    # Paired condition completeness by (model, task, seed)
    expected_conditions = {c.id for c in v["conditions"]}
    paired: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    for r in rows:
        paired[(r.get("model_spec", r.get("model", "")), r["task_id"], int(r.get("base_seed", r["seed"])))].add(r.get("condition_id", r.get("mode", "baseline")))
    incomplete_pairs = [k for k, s in paired.items() if s != expected_conditions]
    if incomplete_pairs:
        errors.append(f"incomplete condition sets: {len(incomplete_pairs)}")

    # Record-level consistency
    bad_rounds = []
    bad_first = []
    bad_baseline = []
    missing_fields = []
    required = [
        "model_spec", "task_id", "base_seed", "condition_id", "intervention",
        "L0", "L1", "L2", "L3", "error_category", "n_rounds",
        "first_success_round", "tokens_in", "tokens_out", "total_tokens", "rounds",
    ]
    cond_rounds = {c.id: c.max_rounds for c in v["conditions"]}

    for i, r in enumerate(rows):
        miss = [k for k in required if k not in r]
        if miss:
            missing_fields.append((i, miss))
            continue
        rounds = r.get("rounds", [])
        if len(rounds) != int(r.get("n_rounds", -1)):
            bad_rounds.append(i)
        cid = r["condition_id"]
        max_corrections = cond_rounds.get(cid, 0)
        if len(rounds) > max_corrections + 1:
            bad_rounds.append(i)
        successful_rounds = [int(x["round"]) for x in rounds if x.get("L2")]
        expected_first = min(successful_rounds) if successful_rounds else -1
        if int(r.get("first_success_round", -1)) != expected_first:
            bad_first.append(i)
        if r["intervention"] == "baseline" and len(rounds) != 1:
            bad_baseline.append(i)
        if int(r.get("total_tokens", 0)) != int(r.get("tokens_in", 0)) + int(r.get("tokens_out", 0)):
            warnings.append(f"token total mismatch at row {i}")

    if missing_fields:
        errors.append(f"records with missing required fields: {len(missing_fields)}")
    if bad_rounds:
        errors.append(f"round consistency failures: {len(set(bad_rounds))}")
    if bad_first:
        errors.append(f"first_success_round mismatches: {len(bad_first)}")
    if bad_baseline:
        errors.append(f"baseline records with correction rounds: {len(bad_baseline)}")

    # Initial round equality across conditions: same seed/code/evaluation metadata.
    by_base: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for r in rows:
        by_base[(r["model_spec"], r["task_id"], int(r["base_seed"]))].append(r)
    initial_mismatch = 0
    for _, group in by_base.items():
        sigs = set()
        for r in group:
            rr = r.get("rounds") or []
            if not rr:
                continue
            r0 = rr[0]
            sigs.add((r0.get("code_sha256", ""), r0.get("L0"), r0.get("L1"), r0.get("L2"), r0.get("error_category")))
        if len(sigs) > 1:
            initial_mismatch += 1
    if initial_mismatch:
        errors.append(f"initial round metric mismatches across conditions: {initial_mismatch}")

    return {
        "experiment_id": v["experiment_id"],
        "passed": not errors,
        "expected_records": len(expected),
        "actual_records": len(rows),
        "unique_records": len(actual),
        "errors": errors,
        "warnings": warnings,
        "details": {
            "duplicate_count": len(duplicates),
            "missing_count": len(missing),
            "unexpected_count": len(unexpected),
            "incomplete_pair_count": len(incomplete_pairs),
            "initial_mismatch_count": initial_mismatch,
            "missing_examples": [list(x) for x in missing[:10]],
        },
    }


def write_sanity_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanity check ver2 experiment results")
    parser.add_argument("--config", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = check_results(load_config(args.config), args.results)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        write_sanity_report(report, args.out)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
