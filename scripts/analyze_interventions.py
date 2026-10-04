"""Generate the nine CSV analysis outputs for the new harness."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROUND_INTERVENTIONS = {"self_refine", "execution_feedback", "self_debugging"}
COMPARE_INTERVENTIONS = ROUND_INTERVENTIONS | {"preventive_spec"}


def _load(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _mean(values):
    return sum(values) / len(values) if values else None


def _stage(row: dict[str, Any]) -> int:
    if not row.get("L0"): return 0
    if not row.get("L1"): return 1
    if not row.get("L2"): return 2
    if not row.get("structure_match"): return 3
    return 4


def _write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _summary(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k, "") for k in keys)].append(row)
    result = []
    for group_key, items in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        item = dict(zip(keys, group_key))
        item["n"] = len(items)
        for metric in ("L0", "L1", "L2", "structure_match", "L3", "final_success", "timeout_flag"):
            item[f"{metric}_rate"] = _mean([int(bool(x.get(metric))) for x in items])
        for metric in ("tokens_in", "tokens_out", "total_tokens", "elapsed_sec", "code_lines", "gate_count", "circuit_depth", "L2_distance"):
            values = [float(x[metric]) for x in items if isinstance(x.get(metric), (int, float)) and x[metric] == x[metric]]
            item[f"avg_{metric}"] = _mean(values)
        first_success = [int(x["first_success_round"]) for x in items if int(x.get("first_success_round", -1)) >= 0]
        item["avg_first_success_round"] = _mean(first_success)
        costs = [x.get("estimated_cost_usd") for x in items if x.get("estimated_cost_usd") is not None]
        item["avg_estimated_cost_usd"] = _mean(costs) if costs else "null"
        result.append(item)
    return result


def analyze(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    outputs: dict[str, list[dict[str, Any]]] = {
        "summary_by_condition": _summary(rows, ("condition_id", "intervention", "model_spec", "task_difficulty")),
        "summary_by_model": _summary(rows, ("model_spec", "condition_id", "intervention", "task_difficulty")),
        "summary_by_task": _summary(rows, ("task_id", "task_difficulty", "model_spec", "condition_id", "intervention")),
        "summary_by_difficulty": _summary(rows, ("task_difficulty", "model_spec", "condition_id", "intervention")),
    }

    by_pair = defaultdict(dict)
    for row in rows:
        key = (row.get("model_spec", ""), row.get("task_id", ""), int(row.get("seed", 0)))
        by_pair[key][row.get("intervention", row.get("condition_id", ""))] = row

    rescue_groups = defaultdict(list)
    degradation, regressions = [], []
    for (model, task, seed), conds in by_pair.items():
        baseline = conds.get("baseline")
        if baseline is None:
            continue
        for intervention, row in conds.items():
            if intervention not in COMPARE_INTERVENTIONS:
                continue
            if not baseline.get("L2"):
                rescue_groups[(intervention, model, task, baseline.get("task_difficulty", row.get("task_difficulty", "")), baseline.get("error_category", "unknown_error"))].append((seed, row))
            if intervention in ROUND_INTERVENTIONS:
                rounds = row.get("rounds") or []
                if len(rounds) > 1 and _stage(rounds[-1]) < _stage(rounds[0]):
                    degradation.append({"model_spec": model, "task_id": task, "task_difficulty": row.get("task_difficulty", ""),
                                       "seed": seed, "intervention": intervention,
                                       "initial_stage_score": _stage(rounds[0]), "final_stage_score": _stage(rounds[-1]),
                                       "initial_error_category": rounds[0].get("error_category", ""),
                                       "final_error_category": rounds[-1].get("error_category", ""),
                                       "code_diff_round0_final": row.get("code_diff_round0_final", "")})
            if baseline.get("L2") and not row.get("L2"):
                regressions.append({"model_spec": model, "task_id": task, "task_difficulty": row.get("task_difficulty", ""),
                                    "seed": seed, "intervention": intervention,
                                    "baseline_error_category": baseline.get("error_category", ""),
                                    "intervention_error_category": row.get("error_category", ""),
                                    "baseline_L2": baseline.get("L2"), "intervention_L2": row.get("L2"),
                                    "code_diff_round0_final": row.get("code_diff_round0_final", "")})

    rescue = []
    for (intervention, model, task, difficulty, error), samples in sorted(rescue_groups.items()):
        rescue.append({"intervention": intervention, "model_spec": model, "task_id": task,
                       "task_difficulty": difficulty, "baseline_error_category": error,
                       "n_baseline_failures": len(samples), "rescued": sum(bool(row.get("L2")) for _, row in samples),
                       "rescue_rate": sum(bool(row.get("L2")) for _, row in samples) / len(samples)})
    outputs["rescue_rates_by_error"] = rescue
    outputs["degradation_cases"] = degradation
    outputs["baseline_regressions"] = regressions

    timeout_groups = defaultdict(list)
    for row in rows:
        timeout_groups[(row.get("intervention", ""), row.get("model_spec", ""), row.get("task_id", ""), row.get("task_difficulty", ""))].append(row)
    outputs["timeout_summary"] = [
        {"intervention": k[0], "model_spec": k[1], "task_id": k[2], "task_difficulty": k[3],
         "n": len(v), "timeout_count": sum(bool(x.get("timeout_flag")) for x in v),
         "timeout_rate": _mean([int(bool(x.get("timeout_flag"))) for x in v]),
         "timeout_elapsed_sec": _mean([float(x.get("elapsed_sec", 0)) for x in v if x.get("timeout_flag")])}
        for k, v in sorted(timeout_groups.items())]

    runtime_groups = defaultdict(list)
    for row in rows:
        runtime_groups[(row.get("intervention", ""), row.get("model_spec", ""))].append(row)
    outputs["cost_runtime_summary"] = []
    for (intervention, model), items in sorted(runtime_groups.items()):
        item = {"intervention": intervention, "model_spec": model, "n": len(items)}
        for field in ("tokens_in", "tokens_out", "total_tokens", "elapsed_sec", "code_lines", "gate_count", "circuit_depth"):
            item[f"avg_{field}"] = _mean([float(x.get(field, 0)) for x in items])
        costs = [x["estimated_cost_usd"] for x in items if x.get("estimated_cost_usd") is not None]
        item["total_estimated_cost_usd"] = sum(costs) if costs else "null"
        outputs["cost_runtime_summary"].append(item)
    return outputs


def write_analysis_outputs(raw_path: str | Path, output_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = analyze(_load(raw_path))
    schemas = {
        "summary_by_condition": ["condition_id", "intervention", "model_spec", "task_difficulty", "n", "L0_rate", "L1_rate", "L2_rate", "structure_match_rate", "L3_rate", "final_success_rate", "timeout_flag_rate", "avg_first_success_round", "avg_tokens_in", "avg_tokens_out", "avg_total_tokens", "avg_elapsed_sec", "avg_code_lines", "avg_gate_count", "avg_circuit_depth", "avg_L2_distance", "avg_estimated_cost_usd"],
        "summary_by_model": ["model_spec", "condition_id", "intervention", "task_difficulty", "n", "L0_rate", "L1_rate", "L2_rate", "structure_match_rate", "L3_rate", "final_success_rate", "timeout_flag_rate", "avg_first_success_round", "avg_tokens_in", "avg_tokens_out", "avg_total_tokens", "avg_elapsed_sec", "avg_code_lines", "avg_gate_count", "avg_circuit_depth", "avg_L2_distance", "avg_estimated_cost_usd"],
        "summary_by_task": ["task_id", "task_difficulty", "model_spec", "condition_id", "intervention", "n", "L0_rate", "L1_rate", "L2_rate", "structure_match_rate", "L3_rate", "final_success_rate", "timeout_flag_rate", "avg_first_success_round", "avg_tokens_in", "avg_tokens_out", "avg_total_tokens", "avg_elapsed_sec", "avg_code_lines", "avg_gate_count", "avg_circuit_depth", "avg_L2_distance", "avg_estimated_cost_usd"],
        "summary_by_difficulty": ["task_difficulty", "model_spec", "condition_id", "intervention", "n", "L0_rate", "L1_rate", "L2_rate", "structure_match_rate", "L3_rate", "final_success_rate", "timeout_flag_rate", "avg_first_success_round", "avg_tokens_in", "avg_tokens_out", "avg_total_tokens", "avg_elapsed_sec", "avg_code_lines", "avg_gate_count", "avg_circuit_depth", "avg_L2_distance", "avg_estimated_cost_usd"],
        "rescue_rates_by_error": ["intervention", "model_spec", "task_id", "task_difficulty", "baseline_error_category", "n_baseline_failures", "rescued", "rescue_rate"],
        "degradation_cases": ["model_spec", "task_id", "task_difficulty", "seed", "intervention", "initial_stage_score", "final_stage_score", "initial_error_category", "final_error_category", "code_diff_round0_final"],
        "baseline_regressions": ["model_spec", "task_id", "task_difficulty", "seed", "intervention", "baseline_error_category", "intervention_error_category", "baseline_L2", "intervention_L2", "code_diff_round0_final"],
        "timeout_summary": ["intervention", "model_spec", "task_id", "task_difficulty", "n", "timeout_count", "timeout_rate", "timeout_elapsed_sec"],
        "cost_runtime_summary": ["intervention", "model_spec", "n", "avg_tokens_in", "avg_tokens_out", "avg_total_tokens", "avg_elapsed_sec", "avg_code_lines", "avg_gate_count", "avg_circuit_depth", "total_estimated_cost_usd"],
    }
    for name, fields in schemas.items():
        _write(out / f"{name}.csv", result[name], fields)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze new harness JSONL results")
    parser.add_argument("path")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()
    out = Path(args.out_dir) if args.out_dir else Path(args.path).parent
    results = write_analysis_outputs(args.path, out)
    print(f"Wrote {len(results)} CSV files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
