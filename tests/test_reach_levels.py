"""Check cumulative, exclusive and paired statistics with known transitions."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil

import pytest

from scripts.analyze_reach_levels import LEVELS, REPAIRS, analyze_levels, freeze_sources, reached


def attempt(level, code="initial"):
    index = LEVELS.index(level)
    return dict(L0=index >= 1, L1=index >= 2, L2=index >= 3,
                L3=index == 4, structure_match=index == 4, code_sha256=code)


def records():
    rows = []
    starts = ("unattained", "L0", "L1", "L3")
    ends = ("L0", "unattained", "L2", "L3")
    for seed, (start, end) in enumerate(zip(starts, ends)):
        for condition in ("baseline", *REPAIRS, "preventive_spec"):
            first = attempt(start)
            final = first if condition == "baseline" else attempt(end, "changed")
            if condition in REPAIRS and start == "L3":
                final = first
            rounds = [first] if condition == "baseline" or condition in REPAIRS and start == "L3" else [first, final]
            if condition == "preventive_spec":
                rounds = [final]
            rows.append(dict(experiment_id="test", model_spec="model", task_id="task",
                             seed=seed, base_seed=seed, intervention=condition, rounds=rounds, **final))
    return rows


def test_levels_are_cumulative_and_exclusive_counts_partition_all_records():
    result = analyze_levels(records())
    for row in result["level_summary"]:
        assert sum(row[f"{level}_only_count"] for level in LEVELS) == row["n"] == 4
        assert row["L0_count"] >= row["L1_count"] >= row["L2_count"] >= row["L3_count"]
    repaired = next(row for row in result["level_summary"] if row["intervention"] == "self_refine")
    assert [repaired[f"{level}_count"] for level in LEVELS[1:]] == [3, 2, 2, 1]
    assert repaired["L2_only_count"] == 1  # Correct output with structural failure.


def test_paired_improvement_counts_include_partial_progress_and_worsening():
    result = analyze_levels(records())
    repair = next(row for row in result["intervention_effects"] if row["intervention"] == "self_refine")
    assert (repair["improved"], repair["unchanged"], repair["worsened"]) == (2, 1, 1)
    assert repair["initial_L3_success_unmodified"] == 1
    assert repair["repair_attempted"] == repair["baseline_L3_failure"] == 3
    assert repair["partial_improvement"] == 2
    assert repair["L2_rescued"] == 1 and repair["L3_rescued"] == 0
    assert repair["failure_improvement_rate"] == 2 / 3
    preventive = next(row for row in result["intervention_effects"] if row["intervention"] == "preventive_spec")
    assert preventive["comparison_kind"] == "pre_generation"
    assert preventive["repair_attempted"] == preventive["initial_L3_success_unmodified"] == 0
    selected = [row for row in result["level_transitions"] if row["intervention"] == "self_refine"]
    assert len(selected) == 25 and sum(row["n"] for row in selected) == 4
    assert all(row["rate"] == "" for row in selected if row["baseline_level"] == "L2")


@pytest.mark.parametrize("invalid", [dict(L1=True, L0=False), dict(L2=True, L1=False),
                                     dict(L3=True, structure_match=False), dict(L0=1)])
def test_inconsistent_levels_are_rejected(invalid):
    row = attempt("L3")
    row.update(invalid)
    with pytest.raises(ValueError):
        reached(row)


@pytest.mark.parametrize("problem", ["duplicate", "missing", "mixed", "initial", "history"])
def test_invalid_pairing_and_history_are_rejected(problem):
    rows = deepcopy(records())
    if problem == "duplicate":
        rows.append(rows[0])
    elif problem == "missing":
        rows.pop()
    elif problem == "mixed":
        rows[0]["experiment_id"] = "other"
    elif problem == "initial":
        rows[1]["rounds"][0]["code_sha256"] = "different"
    else:
        rows[1]["rounds"][0]["L2"] = True
    with pytest.raises(ValueError):
        analyze_levels(rows)


def test_fixed_snapshot_serializes_csv_and_excludes_raw_and_code(tmp_path, monkeypatch):
    source = tmp_path / "results/test"
    source.mkdir(parents=True)
    (source / "raw.jsonl").write_text("".join(json.dumps(dict(row, raw_output="PRIVATE CODE")) + "\n" for row in records()))
    (source / "experiment_config.json").write_text(json.dumps(dict(experiment_id="test", tasks=["T1_Bell"])))
    (source / "manifest.json").write_text('{"git_commit": "test"}')
    (source / "automation_report.json").write_text('{"passed": true}')
    (source / "sanity_report.json").write_text('{"passed": true, "experiment_id": "test"}')
    for name in ("summary_by_condition.csv", "intervention_catalog_by_error.csv",
                 "intervention_catalog_by_error_model.csv", "intervention_catalog_by_error_difficulty.csv"):
        (source / name).write_text("{}" if name.endswith("json") else "header\n")
    (tmp_path / "tasks").mkdir()
    for name in ("t1_bell.py", "__init__.py"):
        shutil.copyfile(Path("tasks") / name, tmp_path / "tasks" / name)
    # Isolate serialization from source validators, which are tested separately.
    monkeypatch.setattr("scripts.analyze_reach_levels.check_results", lambda *args: dict(passed=True, warnings=[]))
    monkeypatch.setattr("scripts.analyze_reach_levels.verify_catalog", lambda *args: True)
    monkeypatch.setattr("scripts.analyze_reach_levels.subprocess.check_output",
                        lambda args, **kwargs: (tmp_path / args[-1].split(":", 1)[1]).read_bytes())
    output = tmp_path / "snapshot"
    freeze_sources(["results/test"], output, root=tmp_path)
    with (output / "test/level_summary.csv").open(encoding="utf-8-sig") as handle:
        parsed = list(csv.DictReader(handle))
    assert len(parsed) == 5 and parsed[0]["n"] == "4"
    assert json.loads((output / "results_snapshot.json").read_text())["runs"][0]["records"] == 20
    assert not list(output.rglob("*.jsonl"))
    assert all("PRIVATE CODE" not in path.read_text() for path in output.rglob("*") if path.is_file())
    with pytest.raises(ValueError, match="new fixed snapshot"):
        freeze_sources(["results/test"], output, root=tmp_path)
    (source / "automation_report.json").write_text('{"passed": false}')
    with pytest.raises(ValueError, match="Unverified source"):
        freeze_sources(["results/test"], tmp_path / "rejected", root=tmp_path)
    assert not (tmp_path / "rejected").exists()
