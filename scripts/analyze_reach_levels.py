"""Freeze verified results as cumulative levels, exclusive stages and paired changes.

Reads saved evaluations only; never generates or executes model code.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from harness.experiment import has_api_failure
from scripts.analyze_intervention_catalog import verify_catalog
from scripts.analyze_interventions import _write
from scripts.sanity_check import _load_rows, check_results
from tasks import get_task

LEVELS = ("unattained", "L0", "L1", "L2", "L3")
REPAIRS = ("self_refine", "execution_feedback", "self_debugging")
INTERVENTIONS = (*REPAIRS, "preventive_spec")


def reached(row):
    """Return an ordered category, not an additive quality score."""
    for field in ("L0", "L1", "L2", "L3", "structure_match"):
        if type(row.get(field)) is not bool:
            raise ValueError(f"Non-boolean level: {field}")
    if row["L1"] and not row["L0"] or row["L2"] and not row["L1"]:
        raise ValueError("Non-cumulative levels")
    if row["L3"] != (row["L0"] and row["L1"] and row["L2"] and row["structure_match"]):
        raise ValueError("L3 formula mismatch")
    return next((level for level in reversed(LEVELS[1:]) if row[level]), "unattained")


def analyze_levels(rows):
    if len({row["experiment_id"] for row in rows}) != 1:
        raise ValueError("Analyze each source separately")
    groups, pairs = defaultdict(list), defaultdict(dict)
    for row in rows:
        reached(row)
        for attempt in row.get("rounds", []):
            reached(attempt)
        key = (row["model_spec"], row["task_id"], row.get("base_seed", row["seed"]))
        condition = row["intervention"]
        if condition in pairs[key]:
            raise ValueError("Duplicate pair/condition")
        pairs[key][condition] = row
        groups[(row["model_spec"], condition)].append(row)

    summaries = []
    for (model, condition), items in sorted(groups.items()):
        counts = Counter(reached(row) for row in items)
        entry = dict(model_spec=model, intervention=condition, n=len(items))
        for level in LEVELS:
            entry[f"{level}_only_count"] = counts[level]
        for level in LEVELS[1:]:
            entry[f"{level}_count"] = sum(row[level] for row in items)
            entry[f"{level}_rate"] = entry[f"{level}_count"] / len(items)
        summaries.append(entry)

    transitions, effects = Counter(), defaultdict(Counter)
    for (model, task, seed), conditions in pairs.items():
        if set(conditions) != {"baseline", *INTERVENTIONS}:
            raise ValueError("Incomplete pair")
        baseline = conditions["baseline"]
        start = reached(baseline)
        for condition in INTERVENTIONS:
            row = conditions[condition]
            repair = condition in REPAIRS
            if repair:
                first = row.get("rounds", [])[0]
                base_first = baseline.get("rounds", [])[0]
                fields = ("L0", "L1", "L2", "L3", "structure_match", "code_sha256")
                if any(first.get(field) != base_first.get(field) for field in fields):
                    raise ValueError("Shared initial generation mismatch")
            end = reached(row)
            transitions[(model, condition, start, end)] += 1
            counts = effects[(model, condition)]
            counts["n_pairs"] += 1
            counts["baseline_L3_success"] += baseline["L3"]
            counts["baseline_L3_failure"] += not baseline["L3"]
            counts["baseline_L2_failure"] += not baseline["L2"]
            counts["final_L3_success"] += row["L3"]
            counts["L3_rescued"] += not baseline["L3"] and row["L3"]
            counts["L2_rescued"] += not baseline["L2"] and row["L2"]
            counts["L3_regressed"] += baseline["L3"] and not row["L3"]
            counts["improved"] += LEVELS.index(end) > LEVELS.index(start)
            counts["unchanged"] += end == start
            counts["worsened"] += LEVELS.index(end) < LEVELS.index(start)
            counts["initial_L3_success_unmodified"] += repair and baseline["L3"] and len(row["rounds"]) == 1
            counts["repair_attempted"] += repair and len(row["rounds"]) > 1
            counts["failure_improved"] += not baseline["L3"] and LEVELS.index(end) > LEVELS.index(start)
            counts["partial_improvement"] += not baseline["L3"] and not row["L3"] and LEVELS.index(end) > LEVELS.index(start)

    transition_rows, effect_rows = [], []
    for (model, condition), counts in sorted(effects.items()):
        effect = dict(model_spec=model, intervention=condition,
                      comparison_kind="repair" if condition in REPAIRS else "pre_generation", **counts)
        for name, numerator, denominator in (
            ("L3_rescue_rate", "L3_rescued", "baseline_L3_failure"),
            ("L2_rescue_rate", "L2_rescued", "baseline_L2_failure"),
            ("failure_improvement_rate", "failure_improved", "baseline_L3_failure"),
        ):
            effect[name] = counts[numerator] / counts[denominator] if counts[denominator] else ""
        effect_rows.append(effect)
        for start in LEVELS:
            denominator = sum(transitions[(model, condition, start, end)] for end in LEVELS)
            for end in LEVELS:
                n = transitions[(model, condition, start, end)]
                transition_rows.append(dict(model_spec=model, intervention=condition,
                    comparison_kind=effect["comparison_kind"], baseline_level=start, final_level=end,
                    n=n, baseline_level_count=denominator, rate=n / denominator if denominator else ""))
    return dict(level_summary=summaries, level_transitions=transition_rows, intervention_effects=effect_rows)


def freeze_sources(source_dirs, output, root=Path.cwd()):
    output = Path(output)
    if output.exists():
        raise ValueError("Use a new fixed snapshot directory")
    captured = datetime.now(timezone.utc).isoformat()
    prepared = []
    for source in source_dirs:
        source = (root / source).resolve()
        if not source.is_relative_to((root / "results").resolve()):
            raise ValueError("Source must be under results/")
        config = json.loads((source / "experiment_config.json").read_text())
        data = (source / "raw.jsonl").read_bytes()
        if data and not data.endswith(b"\n"):
            raise ValueError("Pending record write")
        rows = _load_rows(source / "raw.jsonl")
        report = check_results(config, source / "raw.jsonl")
        saved = json.loads((source / "automation_report.json").read_text())
        saved_sanity = json.loads((source / "sanity_report.json").read_text())
        if (not report["passed"] or report["warnings"] or saved.get("passed") is not True
                or saved_sanity.get("passed") is not True
                or saved_sanity.get("experiment_id") != config["experiment_id"]):
            raise ValueError("Unverified source")
        if any(row["experiment_id"] != config["experiment_id"] for row in rows):
            raise ValueError("Foreign experiment records")
        if any(has_api_failure(row) for row in rows) or not verify_catalog(rows, source):
            raise ValueError("API failure or catalog mismatch")
        manifest = json.loads((source / "manifest.json").read_text())
        requirements = []
        for task_id in config["tasks"]:
            task = get_task(task_id)
            module = next(path for path in (root / "tasks").glob("t*.py") if f'id="{task_id}"' in path.read_text())
            # Structural claims must refer to the definition used by this run.
            for path in (module, root / "tasks/__init__.py"):
                historical = subprocess.check_output(["git", "show", f"{manifest['git_commit']}:{path.relative_to(root)}"], cwd=root)
                if historical != path.read_bytes():
                    raise ValueError(f"Task definition changed: {task_id}")
            requirements.append(dict(task_id=task_id, n_qubits=task.n_qubits,
                expected_gate_count_range=task.expected_gate_count_range,
                measurement_required=task.measurement_required,
                expected_measurement_count=task.expected_measurement_count,
                expected_classical_bits=task.expected_classical_bits,
                expected_kind=task.expected_kind, threshold=task.threshold,
                task_file=str(module.relative_to(root)), task_sha256=hashlib.sha256(module.read_bytes()).hexdigest()))
        analysis = analyze_levels(rows)
        if data != (source / "raw.jsonl").read_bytes():
            raise ValueError("Source changed during capture")
        prepared.append((source, config, report, analysis, requirements, data))

    snapshot = dict(captured_at_utc=captured, analysis_version="reach_levels_v1", level_order=list(LEVELS), runs=[])
    file_manifest = []
    for source, config, report, analysis, requirements, data in prepared:
        dest = output / config["experiment_id"]
        dest.mkdir(parents=True)
        # Copy only public metadata and aggregate files; never raw or code diffs.
        for filename in ("experiment_config.json", "manifest.json", "sanity_report.json", "automation_report.json",
                         "summary_by_condition.csv", "intervention_catalog_by_error.csv",
                         "intervention_catalog_by_error_model.csv", "intervention_catalog_by_error_difficulty.csv"):
            origin = source / filename
            shutil.copyfile(origin, dest / filename)
            file_manifest.append(dict(source=str(origin.relative_to(root)),
                copy=str((dest / filename).relative_to(output)), sha256=hashlib.sha256(origin.read_bytes()).hexdigest()))
        (dest / "rechecked_sanity_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        for name, values in analysis.items():
            _write(dest / f"{name}.csv", values, list(values[0]))
        snapshot["runs"].append(dict(experiment_id=config["experiment_id"], source_dir=str(source.relative_to(root)),
            config=config, records=len(data.splitlines()), raw_sha256=hashlib.sha256(data).hexdigest(),
            verified=True, catalog_verified=True, sanity=report, task_requirements=requirements, **analysis))
    (output / "results_snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    (output / "source_manifest.json").write_text(json.dumps(dict(captured_at_utc=captured, files=file_manifest), ensure_ascii=False, indent=2) + "\n")
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", action="append", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    snapshot = freeze_sources(args.source_dir, args.out_dir)
    print(f"Frozen {len(snapshot['runs'])} verified sources at {snapshot['captured_at_utc']}")


if __name__ == "__main__":
    main()
