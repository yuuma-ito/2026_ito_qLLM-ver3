"""Paired catalog semantics without generation or code evaluation."""
import copy

import pytest

from scripts.analyze_intervention_catalog import INTERVENTIONS, analyze_catalog, write_catalog


def pair(seed, *, baseline_l2=False, category="wrong_output", model="model-a", difficulty="hard"):
    return [dict(experiment_id="test", model_spec=model, task_id="task", seed=seed,
                 task_difficulty=difficulty, intervention=intervention,
                 L2=baseline_l2, error_category=category, rounds=[])
            for intervention in ("baseline", *INTERVENTIONS)]


def test_baseline_category_rescue_regression_degradation_and_timeout_are_distinct():
    records = pair(0, category="unknown_error")
    records[0]["error_message"] = "No module named qiskit"  # must not reclassify baseline
    records[1].update(L2=True, error_category="ok")
    records[2].update(error_category="syntax", rounds=[
        dict(L0=True, L1=True, L2=False), dict(L0=False, L1=False, L2=False)])
    records[3].update(rounds=[dict(error_category="api_timeout", timeout_flag=True),
                              dict(error_category="api_timeout", timeout_flag=True)])
    records[4].update(L2=True, error_category="ok", rounds=[
        dict(L0=True, L1=True, L2=True), dict(L0=False)])  # preventive is not repair
    successful = pair(1, baseline_l2=True, category="ok")
    successful[2].update(L2=False, error_category="wrong_output")
    records.extend(successful)
    result = analyze_catalog(records)
    overall = {(r["baseline_error_category"], r["intervention"]): r
               for r in result["intervention_catalog_by_error"]}
    rescue = overall["unknown_error", "self_refine"]
    assert rescue["baseline_failure_count"] == rescue["rescued_count"] == 1
    assert rescue["rescue_rate"] == 1
    assert rescue["regression_count"] == 0
    assert rescue["best_intervention_flag"] == "参考"
    assert overall["unknown_error", "execution_feedback"]["degradation_count"] == 1
    assert overall["unknown_error", "self_debugging"]["timeout_count"] == 1
    assert overall["unknown_error", "preventive_spec"]["degradation_count"] == 0
    regression = overall["ok", "execution_feedback"]
    assert regression["baseline_failure_count"] == regression["rescued_count"] == 0
    assert regression["rescue_rate"] == ""
    assert regression["regression_count"] == 1
    for name in ("error_model", "error_difficulty"):
        rows = result[f"intervention_catalog_by_{name}"]
        assert sum(r["rescued_count"] for r in rows) == 2
        assert sum(r["regression_count"] for r in rows) == 1


def test_best_is_observed_repair_only_and_ties_and_zero_rescues_are_explicit():
    records = []
    for seed in range(10):
        sample = pair(seed)
        sample[4]["L2"] = True  # preventive highest but excluded from repair ranking
        if seed < 3:
            sample[1]["L2"] = sample[2]["L2"] = True
        records.extend(sample)
    rows = analyze_catalog(records)["intervention_catalog_by_error"]
    flags = {r["intervention"]: r["best_intervention_flag"] for r in rows}
    assert flags["self_refine"] == flags["execution_feedback"] == "観測最多（同率）"
    assert flags["self_debugging"] == "最多以外"
    assert flags["preventive_spec"] == "参考（生成前介入）"
    for record in records:
        record["L2"] = False
    rows = analyze_catalog(records)["intervention_catalog_by_error"]
    assert all(r["best_intervention_flag"] == "救出なし" for r in rows
               if r["intervention"] != "preventive_spec")


@pytest.mark.parametrize("problem", ["duplicate", "missing", "difficulty", "experiment", "nonboolean"])
def test_rejects_invalid_pairing(problem):
    records = pair(0)
    if problem == "duplicate":
        records.append(copy.deepcopy(records[0]))
    elif problem == "missing":
        records.pop()
    elif problem == "difficulty":
        records[-1]["task_difficulty"] = "easy"
    elif problem == "experiment":
        records[-1]["experiment_id"] = "other"
    else:
        records[-1]["L2"] = "False"
    with pytest.raises(ValueError):
        analyze_catalog(records)


def test_write_only_additional_csvs_without_touching_source(tmp_path):
    import json
    raw = tmp_path / "raw.jsonl"
    raw.write_text("\n".join(json.dumps(r) for r in pair(0)), encoding="utf-8")
    existing = tmp_path / "rescue_rates_by_error.csv"
    existing.write_bytes(b"existing CSV\n")
    before = raw.read_bytes()
    write_catalog(raw, tmp_path)
    assert raw.read_bytes() == before
    assert existing.read_bytes() == b"existing CSV\n"
    assert len(list(tmp_path.glob("intervention_catalog_*.csv"))) == 3
