from copy import deepcopy
import hashlib
import json

import pytest

from scripts.analyze_reach_levels import INTERVENTIONS, LEVELS, analyze_levels
from scripts.analyze_stratified_effects import analyze_strata, verify_aggregates, write_analysis


def attempt(level, code="initial"):
    index = LEVELS.index(level)
    return dict(L0=index >= 1, L1=index >= 2, L2=index >= 3,
                L3=index == 4, structure_match=index == 4, code_sha256=code)


def records():
    rows = []
    for source, seed, start, end, difficulty in [
        ("a", 0, "unattained", "L0", "easy"),
        ("a", 1, "L0", "unattained", "hard"),
        ("b", 10, "L1", "L2", "easy"),
        ("b", 11, "L3", "L3", "hard"),
    ]:
        for condition in ("baseline", *INTERVENTIONS):
            first = attempt(start)
            final = first if condition == "baseline" else attempt(end, "changed")
            if condition == "preventive_spec":
                final = attempt("unattained" if start == "L3" else "L3", "preventive")
                rounds = [final]
            else:
                rounds = [first] if condition == "baseline" or start == "L3" else [first, final]
                if start == "L3":
                    final = first
            rows.append(dict(experiment_id=source, model_spec="model", task_id="task",
                seed=seed, base_seed=seed, intervention=condition, task_difficulty=difficulty,
                failure_stage="unknown", error_category="ok" if final["L3"] else "wrong_output",
                rounds=rounds, raw_output="PRIVATE GENERATED CODE", **final))
    return rows


def test_sources_partitions_and_partial_improvements_reconcile():
    result = analyze_strata(records())
    assert verify_aggregates(result)
    row = next(r for r in result["effects"] if r["scope"] == "pooled"
               and r["grouping"] == "overall" and r["intervention"] == "self_refine")
    assert (row["n_pairs"], row["baseline_L3_failure"], row["L2_rescued"], row["L3_rescued"]) == (4,3,1,0)
    assert (row["stage_improved"],row["stage_unchanged"],row["stage_worsened"],row["partial_improvement"]) == (2,1,1,2)
    assert row["L2_rescue_rate"] == 1/3 and row["L3_rescue_rate"] == 0
    assert row["partial_improvement_rate"] == 2/3
    seed = next(r for r in result["effects"] if r["scope"] == "pooled" and r["grouping"] == "seed"
                and r["base_seed"] == 11 and r["intervention"] == "self_refine")
    assert seed["L3_rescue_rate"] == "" and seed["initial_L3_success_unmodified"] == 1
    assert seed["small_L3_failure_denominator"]
    preventive = next(r for r in result["effects"] if r["scope"] == "pooled" and r["grouping"] == "overall"
                      and r["intervention"] == "preventive_spec")
    assert preventive["comparison_kind"] == "pre_generation"
    assert preventive["L3_rescued"] == 3 and preventive["L3_regressed"] == 1
    assert preventive["repair_attempted"] == 0
    assert sum(r["n"] for r in result["final_error_counts"] if r["scope"] == "pooled") == 20


@pytest.mark.parametrize("problem", ["overlap", "missing", "difficulty", "initial", "seed"])
def test_invalid_inputs_rejected(problem):
    rows = records()
    if problem == "overlap": rows.append(dict(rows[0],experiment_id="other"))
    elif problem == "missing": rows.pop()
    elif problem == "difficulty": rows[1]["task_difficulty"] = "hard"
    elif problem == "initial": rows[1]["rounds"][0] = attempt("L3")
    else:
        for row in rows:
            if row["seed"] == 0: row.update(seed=20,base_seed=20)
    with pytest.raises(ValueError): analyze_strata(rows)


def test_aggregate_tampering_is_rejected():
    result = analyze_strata(records())
    row = next(r for r in result["effects"] if r["grouping"] == "seed")
    row["repair_attempted"] += 1
    with pytest.raises(ValueError,match="partition"): verify_aggregates(result)


def test_feedback_debugging_rescue_overlap_tracks_discordant_pairs():
    rows = records()
    row = next(r for r in rows if r['seed']==0 and r['intervention']=='execution_feedback')
    row.update(attempt('L3','feedback'))
    row['rounds'][-1]=attempt('L3','feedback')
    result=analyze_strata(rows)
    assert verify_aggregates(result)
    overlap=next(r for r in result['feedback_debug_overlap'] if r['scope']=='pooled' and r['grouping']=='overall')
    assert (overlap['both_rescued'],overlap['feedback_only'],overlap['debugging_only'],overlap['neither_rescued'])==(0,1,0,2)


def test_no_baseline_failures_have_blank_rates_and_no_overlap_rows():
    rows=records()
    for row in rows:
        row.update(attempt('L3'))
        row['rounds']=[attempt('L3')]
    result=analyze_strata(rows)
    assert verify_aggregates(result)
    assert not result['feedback_debug_overlap']
    assert all(r['L3_rescue_rate']=='' for r in result['effects'])


def test_fixed_source_guard_and_public_outputs(tmp_path, monkeypatch):
    rows = records()
    runs = []
    for source in ("a","b"):
        selected = [r for r in rows if r["experiment_id"] == source]
        p = tmp_path/"results"/source
        p.mkdir(parents=True)
        config = dict(experiment_id=source)
        (p/"raw.jsonl").write_text(''.join(json.dumps(r)+'\n' for r in selected))
        (p/"experiment_config.json").write_text(json.dumps(config))
        (p/"manifest.json").write_text('{"schema_version":"2.1"}')
        (p/"automation_report.json").write_text('{"passed":true}')
        runs.append(dict(experiment_id=source,source_dir="results/"+source,config=config,records=len(selected),
                         raw_sha256=hashlib.sha256((p/"raw.jsonl").read_bytes()).hexdigest(),**analyze_levels(selected)))
    snapshot = dict(runs=runs,pooled=dict(experiment_id="pooled",verified=True,records=len(rows),
                   **analyze_levels([dict(r,experiment_id="pooled") for r in rows])))
    path=tmp_path/"snapshot.json";path.write_text(json.dumps(snapshot))
    monkeypatch.setattr("scripts.analyze_stratified_effects.verify",lambda *args:dict(passed=True))
    output=tmp_path/"analysis"
    write_analysis(path,output,root=tmp_path)
    assert json.loads((output/"sanity_report.json").read_text())["passed"]
    assert all("PRIVATE GENERATED CODE" not in p.read_text() for p in output.iterdir())
    before=deepcopy(snapshot)
    (tmp_path/"results/a/raw.jsonl").write_text('{}\n')
    with pytest.raises(ValueError,match="fixed snapshot"):
        write_analysis(path,tmp_path/"rejected",root=tmp_path)
    assert not (tmp_path/"rejected").exists()
    assert json.loads(path.read_text()) == before
