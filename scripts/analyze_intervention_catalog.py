"""Read saved records and write only the three additional intervention catalogs.

Baseline categories are used verbatim (no legacy reclassification). Successful
baseline strata remain as reference rows for regressions, with an empty rescue
rate. Best flags compare repair interventions only and describe observed rates,
not statistical superiority; strata below MIN_BEST_COUNT are reference only.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.analyze_interventions import ROUND_INTERVENTIONS, _stage, _write

INTERVENTIONS = ("self_refine", "execution_feedback", "self_debugging", "preventive_spec")
MIN_BEST_COUNT = 10
FIELDS = ["baseline_error_category", "intervention", "baseline_failure_count",
          "rescued_count", "rescue_rate", "regression_count", "degradation_count", "timeout_count"]


def analyze_catalog(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Require complete unique pairs, so missing interventions cannot bias rates."""
    pairs: dict[tuple, dict[str, dict]] = defaultdict(dict)
    experiment_ids = {row.get("experiment_id") for row in records}
    if len(experiment_ids) > 1:
        raise ValueError("Catalog requires records from one experiment")
    for row in records:
        intervention = row["intervention"]
        if intervention not in ("baseline", *INTERVENTIONS):
            raise ValueError(f"Unexpected intervention: {intervention}")
        key = (row["model_spec"], row["task_id"], row["seed"])
        if intervention in pairs[key]:
            raise ValueError(f"Duplicate pair/condition: {key}, {intervention}")
        if type(row["L2"]) is not bool:
            raise ValueError(f"L2 must be boolean: {key}, {intervention}")
        pairs[key][intervention] = row

    groups: dict[str, dict[tuple, dict]] = {
        name: {} for name in ("error", "error_model", "error_difficulty")
    }
    for key, conditions in pairs.items():
        if set(conditions) != {"baseline", *INTERVENTIONS}:
            raise ValueError(f"Incomplete pair: {key}")
        baseline = conditions["baseline"]
        category = baseline["error_category"]
        difficulty = baseline["task_difficulty"]
        for intervention in INTERVENTIONS:
            row = conditions[intervention]
            if row["task_difficulty"] != difficulty:
                raise ValueError(f"Difficulty mismatch: {key}, {intervention}")
            failed = not baseline["L2"]
            rounds = row.get("rounds") or []
            degraded = (intervention in ROUND_INTERVENTIONS and len(rounds) > 1
                        and _stage(rounds[-1]) < _stage(rounds[0]))
            # Count a record once even if multiple rounds timed out or recovered.
            timed_out = any(r.get("timeout_flag") or r.get("error_category") == "api_timeout"
                            for r in [row, *rounds])
            counts = dict(baseline_failure_count=int(failed),
                          rescued_count=int(failed and row["L2"]),
                          regression_count=int(not failed and not row["L2"]),
                          degradation_count=int(degraded), timeout_count=int(timed_out))
            for name, prefix in (("error", {}), ("error_model", {"model_spec": key[0]}),
                                 ("error_difficulty", {"task_difficulty": difficulty})):
                group_key = (*prefix.values(), category, intervention)
                if group_key not in groups[name]:
                    groups[name][group_key] = dict(prefix, baseline_error_category=category,
                                                  intervention=intervention,
                                                  **dict.fromkeys(counts, 0))
                aggregate = groups[name][group_key]
                for field, value in counts.items():
                    aggregate[field] += value

    outputs = {}
    for name, grouped in groups.items():
        rows = [grouped[key] for key in sorted(grouped)]
        for row in rows:
            n = row["baseline_failure_count"]
            row["rescue_rate"] = row["rescued_count"] / n if n else ""
        outputs[f"intervention_catalog_by_{name}"] = rows

    overall = outputs["intervention_catalog_by_error"]
    for row in overall:
        n = row["baseline_failure_count"]
        if not n:
            flag = "対象外（baseline L2成功）"
        elif row["intervention"] == "preventive_spec":
            flag = "参考（生成前介入）"
        elif n < MIN_BEST_COUNT:
            flag = "参考"
        else:
            peers = [r for r in overall if r["baseline_error_category"] == row["baseline_error_category"]
                     and r["intervention"] in ROUND_INTERVENTIONS]
            best = max(r["rescued_count"] for r in peers)
            if best == 0:
                flag = "救出なし"
            elif row["rescued_count"] != best:
                flag = "最多以外"
            elif sum(r["rescued_count"] == best for r in peers) > 1:
                flag = "観測最多（同率）"
            else:
                flag = "観測最多"
        row["best_intervention_flag"] = flag
    return outputs


def write_catalog(raw_path: str | Path, output_dir: str | Path) -> dict[str, list[dict[str, Any]]]:
    with Path(raw_path).open(encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    outputs = analyze_catalog(records)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    schemas = {"error": FIELDS + ["best_intervention_flag"],
               "error_model": ["model_spec", *FIELDS],
               "error_difficulty": ["task_difficulty", *FIELDS]}
    for suffix, fields in schemas.items():
        name = f"intervention_catalog_by_{suffix}"
        _write(out / f"{name}.csv", outputs[name], fields)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args()
    outputs = write_catalog(args.path, args.out_dir or args.path.parent)
    print(f"Wrote {len(outputs)} additional catalog CSVs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
