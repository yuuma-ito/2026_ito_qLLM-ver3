import json

from harness.reevaluation_plan import build_plan
from scripts.reevaluate_saved import run_full, summarize
from tests.test_reevaluation_completion import fixture_source


def test_full_driver_synthetic_completion_export_and_no_execution_resume(tmp_path):
    path, snapshot, rows, refresh = fixture_source(tmp_path)
    plan = build_plan(snapshot)
    before = path.read_bytes()
    output, cp = tmp_path/"output", tmp_path/"cp"
    result = run_full(output, cp, plan=plan)
    assert cp.stat().st_mode & 0o777 == 0o700
    assert result["status"] == "completed"
    assert result["complete_records"] == 2 and result["missing_rounds"] == 0
    assert result["new_final_successes"] == 2
    assert path.read_bytes() == before
    assert (output/"final"/"record_comparison.csv").exists()
    assert (output/"final"/"artifact_manifest.json").exists()
    def forbid(*args): raise AssertionError("completed results must not execute")
    resumed = run_full(output, cp, plan=plan, executor=forbid)
    assert resumed == result


def test_full_driver_runtime_failure_stops_and_preserves_partial(tmp_path):
    path, snapshot, rows, refresh = fixture_source(tmp_path)
    plan = build_plan(snapshot)
    calls = []
    def timeout(*args):
        calls.append(1); return {"runtime_status":"wall_timeout"}
    output, cp = tmp_path/"output", tmp_path/"cp"
    result = run_full(output, cp, plan=plan, executor=timeout)
    assert len(calls) == 1 and result["runtime_failures"] == 1
    assert result["complete_records"] == 0 and result["new_final_successes"] == 0
    assert result["missing_rounds"] == 1
    assert (output/"partial"/"summary.json").exists()
    repeated = run_full(output, cp, plan=plan, executor=timeout)
    assert repeated == result and len(calls) == 1


def test_summary_separates_first_ever_final_and_regression():
    common = {"record_key":"rec","source_dir":"fixture","model_spec":"fixture","task_id":"T1_Bell", "base_seed":0,"condition_id":"self_refine","code_sha256":"a"*64}
    cases = [{**common,"key":str(i),"round":i,"is_final":i==2,"old_primary":{k:False for k in ("L0","L1","L2","L3","structure_match")}|{"error_category":"wrong_output"}} for i in range(3)]
    outcomes = {}
    for i, success in enumerate((False,True,False)):
        outcomes[str(i)] = {"runtime_status":"completed","primary":{"L0":True,"L1":True,"L2":success,"structure_match":True,"L3":success,"error_category":"ok" if success else "wrong_output"},"auxiliary":{"status":"not_applicable"}}
    summary, rounds, records, groups, paired = summarize({"records":1,"cases":cases},outcomes)
    assert records[0]["new_first_success_round"] == 1
    assert records[0]["new_ever_success"]
    assert not records[0]["new_final_success"]
    assert records[0]["new_regression_observed"]
    assert summary["new_ever_successes"] == 1 and summary["new_final_successes"] == 0
