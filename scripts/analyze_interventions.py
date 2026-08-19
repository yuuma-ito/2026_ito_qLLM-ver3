"""ver2 の介入比較集計。

出力:
- summary.csv: condition/model/task 別の成功率・token・cost
- rescue_rates.csv: 初期 failure category 別の救出率
- success_by_round.csv: round k までの累積成功率
- paired_effects.csv: baseline との paired gain / rescue / regression
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _load(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def _stage(round_meta: dict[str, Any]) -> int:
    if not round_meta.get("L0"):
        return 0
    if not round_meta.get("L1"):
        return 1
    if not round_meta.get("L2"):
        return 2
    return 3


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def analyze(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    # summary
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("condition_id", r.get("mode", "baseline")), r.get("model_spec", r.get("model", "")), r["task_id"])].append(r)
    summary = []
    for (condition, model, task), rs in sorted(groups.items()):
        costs = [x["estimated_cost_usd"] for x in rs if x.get("estimated_cost_usd") is not None]
        summary.append({
            "condition_id": condition,
            "intervention": rs[0].get("intervention", condition),
            "model_spec": model,
            "task_id": task,
            "n": len(rs),
            "L0_rate": _mean([int(x["L0"]) for x in rs]),
            "L1_rate": _mean([int(x["L1"]) for x in rs]),
            "L2_rate": _mean([int(x["L2"]) for x in rs]),
            "L3_rate": _mean([int(x["L3"]) for x in rs]),
            "avg_first_success_round": _mean([x["first_success_round"] for x in rs if x.get("first_success_round", -1) >= 0]),
            "avg_total_tokens": _mean([int(x.get("total_tokens", 0)) for x in rs]),
            "avg_elapsed_sec": _mean([float(x.get("elapsed_sec", 0.0)) for x in rs]),
            "avg_estimated_cost_usd": _mean(costs) if costs else "",
        })

    # Failure-mode rescue rate, using round0 failure category.
    rescue_group = defaultdict(list)
    for r in rows:
        intervention = r.get("intervention", r.get("mode", "baseline"))
        if intervention == "baseline":
            continue
        rounds = r.get("rounds") or []
        if not rounds or rounds[0].get("L2"):
            continue
        initial_cat = rounds[0].get("error_category", "unknown")
        rescue_group[(r.get("condition_id", intervention), r.get("model_spec", r.get("model", "")), initial_cat)].append(r)
    rescue = []
    for (condition, model, cat), rs in sorted(rescue_group.items()):
        rescued = sum(1 for x in rs if x.get("L2"))
        rescue.append({
            "condition_id": condition,
            "model_spec": model,
            "initial_failure_mode": cat,
            "n_initial_failures": len(rs),
            "rescued": rescued,
            "rescue_rate": rescued / len(rs),
        })

    # success by round k, denominator is all samples in condition.
    success_group = defaultdict(list)
    for r in rows:
        success_group[(r.get("condition_id", r.get("mode", "baseline")), r.get("model_spec", r.get("model", "")))].append(r)
    success_by_round = []
    for (condition, model), rs in sorted(success_group.items()):
        max_round = max((max([int(x.get("round", 0)) for x in (r.get("rounds") or [{}])]) for r in rs), default=0)
        for k in range(max_round + 1):
            success = sum(1 for r in rs if 0 <= int(r.get("first_success_round", -1)) <= k)
            success_by_round.append({
                "condition_id": condition,
                "model_spec": model,
                "round": k,
                "n": len(rs),
                "success_by_round": success,
                "success_by_round_rate": success / len(rs),
            })

    # Paired effects by model/task/seed. Baseline is paired to each intervention.
    by_pair = defaultdict(dict)
    for r in rows:
        key = (r.get("model_spec", r.get("model", "")), r["task_id"], int(r.get("base_seed", r.get("seed", 0))))
        by_pair[key][r.get("condition_id", r.get("mode", "baseline"))] = r
    baseline_ids = set()
    for _, conds in by_pair.items():
        for cid, r in conds.items():
            if r.get("intervention", r.get("mode")) == "baseline":
                baseline_ids.add(cid)
    baseline_id = sorted(baseline_ids)[0] if baseline_ids else "baseline"

    pair_agg = defaultdict(lambda: {"n": 0, "base_ok": 0, "int_ok": 0, "initial_fail": 0, "rescued": 0, "regressed": 0})
    for key, conds in by_pair.items():
        base = conds.get(baseline_id)
        if base is None:
            continue
        for cid, r in conds.items():
            if cid == baseline_id:
                continue
            a = pair_agg[(cid, key[0])]
            a["n"] += 1
            a["base_ok"] += int(bool(base.get("L2")))
            a["int_ok"] += int(bool(r.get("L2")))
            rr = r.get("rounds") or []
            if rr:
                initial = rr[0]
                if not initial.get("L2"):
                    a["initial_fail"] += 1
                    a["rescued"] += int(bool(r.get("L2")))
                    final_meta = rr[-1]
                    a["regressed"] += int(_stage(final_meta) < _stage(initial))
    paired = []
    for (cid, model), a in sorted(pair_agg.items()):
        paired.append({
            "condition_id": cid,
            "model_spec": model,
            "n_pairs": a["n"],
            "baseline_L2_rate": a["base_ok"] / a["n"] if a["n"] else float("nan"),
            "intervention_L2_rate": a["int_ok"] / a["n"] if a["n"] else float("nan"),
            "paired_gain": (a["int_ok"] - a["base_ok"]) / a["n"] if a["n"] else float("nan"),
            "n_initial_failures": a["initial_fail"],
            "rescued": a["rescued"],
            "rescue_rate": a["rescued"] / a["initial_fail"] if a["initial_fail"] else float("nan"),
            "regressed": a["regressed"],
            "regression_rate": a["regressed"] / a["initial_fail"] if a["initial_fail"] else float("nan"),
        })

    return {
        "summary": summary,
        "rescue_rates": rescue,
        "success_by_round": success_by_round,
        "paired_effects": paired,
    }


def write_analysis_outputs(raw_path: str | Path, output_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = analyze(_load(raw_path))
    _write_csv(out / "summary.csv", result["summary"], [
        "condition_id", "intervention", "model_spec", "task_id", "n", "L0_rate", "L1_rate", "L2_rate", "L3_rate", "avg_first_success_round", "avg_total_tokens", "avg_elapsed_sec", "avg_estimated_cost_usd"
    ])
    _write_csv(out / "rescue_rates.csv", result["rescue_rates"], [
        "condition_id", "model_spec", "initial_failure_mode", "n_initial_failures", "rescued", "rescue_rate"
    ])
    _write_csv(out / "success_by_round.csv", result["success_by_round"], [
        "condition_id", "model_spec", "round", "n", "success_by_round", "success_by_round_rate"
    ])
    _write_csv(out / "paired_effects.csv", result["paired_effects"], [
        "condition_id", "model_spec", "n_pairs", "baseline_L2_rate", "intervention_L2_rate", "paired_gain", "n_initial_failures", "rescued", "rescue_rate", "regressed", "regression_rate"
    ])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze ver2 intervention results")
    parser.add_argument("path")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()
    out = Path(args.out_dir) if args.out_dir else Path(args.path).parent
    result = write_analysis_outputs(args.path, out)
    print(f"Wrote summary.csv, rescue_rates.csv, success_by_round.csv, paired_effects.csv to {out}")
    print(f"records grouped: summary={len(result['summary'])}, paired={len(result['paired_effects'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
