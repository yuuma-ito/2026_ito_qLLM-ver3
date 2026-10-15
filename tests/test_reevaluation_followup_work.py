import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.reevaluation_followup_validation import cause, validate_rows
from scripts.reevaluation_impact_audit import archived_functions, decide, event
from scripts.reevaluation_partial_rerun import run_case, check_models, validate_cases
from tasks import get_task


def test_stop_before_old_path_influence():
    assert decide([0, 1], [(False, True, False, True), (True, False, True, True)], "execution_feedback") == (0, None, "initial_new_pass_stop")


def test_later_saved_success_is_unreachable_after_feedback_divergence():
    assert decide([0, 1], [(False, False, False, True), (False, True, True, True)], "execution_feedback") == (None, 1, "first_feedback_divergence")


def test_unverified_history_restarts_from_shared_initial():
    assert decide([0, 1], [(False, False, True, True), (False, False, True, False)], "self_debugging") == (None, 1, "historical_prompt_unverified_restart_shared_initial")


def test_missing_continuation_and_limit():
    assert decide([0], [(True, False, True, True)], "self_refine")[1:] == (1, "old_pass_new_fail_missing_continuation")
    assert decide([0, 1, 2, 3], [(False, False, True, True)] * 4, "self_refine") == (3, None, "correction_limit")


def test_archived_prompt_uses_original_failure_not_reclassified_label():
    function, hashes = archived_functions("9c1833eba6020369247358c04e462e0dc1982705")
    prompt = function("execution_feedback", get_task("T1_Bell"), "x", event({"L0": False, "error_category": "unknown_error", "error_message": "NameError: missing"}))
    assert "種別: unknown_error\n  NameError: missing" in prompt
    assert hashes["harness/interventions/prompts.py"] == "ea630da1c7051c0b9cd36163d19cf8d56746dad074408a7d8bd7e2002e6b4ec4"


def test_checkpoint_rejects_changed_hash_missing_or_extra():
    text = '{"runtime_status":"completed"}'
    plan = {"cases": [{"key": "k", "code_sha256": "c"}]}
    row = ("k", "c", "completed", text, hashlib.sha256(text.encode()).hexdigest())
    validate_rows(plan, [row])
    for rows in ([], [row, row], [("extra", *row[1:])], [(*row[:4], "wrong")]):
        with pytest.raises(ValueError):
            validate_rows(plan, rows)


def test_cause_does_not_hide_unrecognized_exception():
    with pytest.raises(ValueError):
        cause({"failure_stage": "evaluate", "exception_type": "MemoryError"})


def test_reviewed_partial_Aer_name_error_is_annotated_without_reclassification():
    primary = {"failure_stage": "exec", "L0": False, "L3": False, "exception_type": "NameError",
               "error_category": "unknown_error", "error_message": "NameError: name 'Aer' is not defined"}
    assert cause(primary) == "model_top_level_undefined_Aer"
    assert primary["error_category"] == "unknown_error" and primary["L3"] is False
    with pytest.raises(ValueError):
        cause(primary | {"error_message": "NameError: name 'unreviewed' is not defined"})


def fixture_case():
    code = "# original failed code"
    c = {"record_key": "a", "source_dir": "source", "model_spec": "ollama:test", "task_id": "T1_Bell", "base_seed": 7,
         "condition_id": "execution_feedback", "branch_input_round": 1, "generation_cap": 3,
         "prefix_code_hashes": [hashlib.sha256(code.encode()).hexdigest()]}
    row = {"rounds": [{"round": 0, "round_seed": 7, "extracted_code": code}]}
    prior = {"a:0": {"primary": {"L0": False, "L3": False, "error_category": "syntax", "error_message": "bad"}}}
    return c, row, prior


def test_partial_path_uses_new_output_and_stops_then_skips_completed(tmp_path):
    c, row, prior = fixture_case()
    requested = []
    def request(client, prompt, seed, temp):
        requested.append((prompt, seed))
        return {"status": "received", "text": "```python\n# new code " + str(seed) + "\n```", "tokens_in": 4, "tokens_out": 5, "elapsed_sec": 1}
    seen = []
    def evaluate(code, task):
        seen.append(code)
        return {"runtime_status": "completed", "primary": {"L0": True, "L1": True, "L2": len(seen) == 2,
                "L3": len(seen) == 2, "structure_match": True, "error_category": "ok" if len(seen) == 2 else "wrong_output", "L2_distance": 1}}
    result = run_case(c, row, prior, {"temperature": .7}, None, tmp_path, executor=evaluate, request=request)
    assert result["success"] and result["stop_round"] == 2 and len(requested) == 2
    assert "# new code 8" in requested[1][0] and [x[1] for x in requested] == [8, 9]
    assert run_case(c, row, prior, {"temperature": .7}, None, tmp_path, executor=evaluate, request=request) == result
    assert len(requested) == 2


def test_final_audit_checks_actual_new_feedback_and_original_prefix(tmp_path):
    from scripts.reevaluation_followup_report import verify_partial_inputs
    c, row, prior = fixture_case()
    def request(client, prompt, seed, temp):
        text = "```python\n# fresh " + str(seed) + "\n```"
        return {"status": "received", "text": text, "tokens_in": 1, "tokens_out": 2, "elapsed_sec": 1,
                "response": {"choices": [{"message": {"content": text}}]}}
    count = []
    def evaluate(*args):
        count.append(True)
        return {"runtime_status": "completed", "primary": {"L0": True, "L1": True, "L3": len(count) == 2,
                "L2_distance": 1, "error_category": "wrong_output"}}
    result = run_case(c, row, prior, {"temperature": .7}, None, tmp_path, executor=evaluate, request=request)
    verify_partial_inputs(result, row, prior, {"temperature": .7}, tmp_path)
    path = tmp_path / "round_2_request.json"
    saved = json.loads(path.read_text()); altered = deepcopy(saved)
    altered["request"]["user"] = "feedback from the old saved path"
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="new-feedback chain"):
        verify_partial_inputs(result, row, prior, {"temperature": .7}, tmp_path)
    path.write_text(json.dumps(saved))
    changed = deepcopy(row); changed["rounds"][0]["extracted_code"] = "different origin"
    with pytest.raises(ValueError, match="original raw"):
        verify_partial_inputs(result, changed, prior, {"temperature": .7}, tmp_path)


def test_ambiguous_request_and_api_failure_never_retried(tmp_path):
    c, row, prior = fixture_case()
    calls = []
    def request(*args):
        calls.append(True)
        return {"status": "api_failure", "exception_type": "APITimeoutError"}
    for _ in range(2):
        with pytest.raises(ValueError, match="生成API障害"):
            run_case(c, row, prior, {"temperature": .7}, None, tmp_path, request=request)
    assert len(calls) == 1
    (tmp_path / "round_1_response.json").unlink()
    with pytest.raises(ValueError, match="自動再送しない"):
        run_case(c, row, prior, {"temperature": .7}, None, tmp_path, request=request)
    assert len(calls) == 1


def test_infrastructure_failure_saved_and_never_counted_as_wrong_output(tmp_path):
    c, row, prior = fixture_case()
    req = lambda *args: {"status": "received", "text": "```python\npass\n```", "tokens_in": 1, "tokens_out": 1, "elapsed_sec": 1}
    with pytest.raises(ValueError, match="基盤障害"):
        run_case(c, row, prior, {"temperature": .7}, None, tmp_path, request=req,
                 executor=lambda *args: {"runtime_status": "wall_timeout"})
    assert not (tmp_path / "completed.json").exists()
    assert json.loads((tmp_path / "round_1_evaluation.json").read_text())["runtime_status"] == "wall_timeout"


def test_model_mismatch_and_cap_are_blocking():
    settings = {"max_tokens": 1024, "parallel_requests": 1, "reasoning_effort": "none", "timeout_sec": 600}
    manifest = {"sources": [{"model_digests": {"ollama:test": "old"}, "generation_settings": settings, "max_rounds": 3,
                             "initial_prompt_source_verified": True}]}
    with pytest.raises(ValueError, match="digest"):
        check_models(manifest, {"models": [{"name": "test", "digest": "new"}]})
    c, _, _ = fixture_case()
    validate_cases([c], {"cases_count": 1, "generation_cap": 3})
    with pytest.raises(ValueError):
        validate_cases([c], {"cases_count": 1, "generation_cap": 4})


@pytest.mark.parametrize("task_id", ["T1_Bell", "T6_QFT_001"])
def test_real_isolated_partial_path_integration(tmp_path, task_id):
    from harness.isolated_evaluation import isolated_evaluate
    c, row, prior = fixture_case()
    c["task_id"] = task_id
    task = get_task(task_id)
    def request(*args):
        return {"status": "received", "text": "```python\n" + task.mock_correct_code + "\n```",
                "tokens_in": 0, "tokens_out": 0, "elapsed_sec": 0}
    result = run_case(c, row, prior, {"temperature": .7}, None, tmp_path,
                      request=request, executor=isolated_evaluate)
    assert result["success"] and result["stop_round"] == 1
    assert result["suffix"][0]["evaluation"]["isolation"]["seccomp"] is True


def test_comparison_keeps_unresolved_reconstruction_out_of_denominator():
    from scripts.reevaluation_followup_report import summarize
    common = {"source_dir": "s", "model_spec": "m", "condition_id": "execution_feedback"}
    rows = [common | {"success": value} for value in (True, False, None)]
    summary = summarize(rows, "reconstructed")[0]
    assert summary["records"] == 3 and summary["resolved_records"] == 2
    assert summary["successes"] == 1 and summary["failures"] == 1 and summary["unresolved_records"] == 1


def test_partial_summary_rejects_continuation_after_success(tmp_path, monkeypatch):
    import scripts.reevaluation_followup_report as report
    from scripts.pilot_reevaluation import sha
    monkeypatch.setattr(report, "CHECKPOINT", tmp_path)
    c, _, _ = fixture_case()
    manifest = {"cases": [c], "cases_count": 1, "generation_cap": 3}
    directory = tmp_path / "a"; directory.mkdir()
    result = {"case": c, "record_key": "a", "stop_round": 2, "success": True,
              "suffix": [{"round": 1, "seed": 8, "evaluation": {"runtime_status": "completed", "primary": {"L3": True}}},
                         {"round": 2, "seed": 9, "evaluation": {"runtime_status": "completed", "primary": {"L3": True}}}]}
    file = directory / "completed.json"; file.write_text(json.dumps(result))
    file.with_suffix(".sha256").write_text(sha(file))
    with pytest.raises(ValueError, match="failed to stop"):
        report.load_partial(manifest)


def test_completed_partial_export_checks_raw_response_identity(tmp_path, monkeypatch):
    import scripts.reevaluation_followup_report as report
    from scripts.pilot_reevaluation import sha
    monkeypatch.setattr(report, "CHECKPOINT", tmp_path)
    c, _, _ = fixture_case()
    manifest = {"cases": [c], "cases_count": 1, "generation_cap": 3}
    d = tmp_path / "a"; d.mkdir()
    ev = {"runtime_status": "completed", "primary": {"L3": True}}
    response = {"status": "received", "text": "```python\npass\n```"}
    result = {"case": c, "record_key": "a", "stop_round": 1, "success": True,
              "suffix": [{"round": 1, "seed": 8, "code": "pass", "code_sha256": hashlib.sha256(b"pass").hexdigest(), "evaluation": ev}]}
    (d / "round_1_evaluation.json").write_text(json.dumps(ev))
    (d / "round_1_response.json").write_text(json.dumps(response))
    (d / "round_1_request.json").write_text(json.dumps({"request": {"round": 1}}))
    file = d / "completed.json"; file.write_text(json.dumps(result))
    file.with_suffix(".sha256").write_text(sha(file))
    completed, requests = report.load_partial(manifest)
    assert list(completed) == ["a"] and requests == [("a", 1)]
    (d / "round_1_response.json").write_text(json.dumps(response | {"text": "changed"}))
    with pytest.raises(ValueError, match="identity mismatch"):
        report.load_partial(manifest)


def test_independent_monitor_uses_lock_not_pid(tmp_path):
    from scripts.reevaluation_followup_finish import driver_active
    from harness.run_state import file_lock
    path = tmp_path / "driver.lock"
    assert not driver_active(path)
    with file_lock(path):
        assert driver_active(path)
    assert not driver_active(path)


def test_monitor_does_not_complete_an_interrupted_worker(tmp_path, monkeypatch):
    import scripts.reevaluation_followup_finish as finish
    private = tmp_path / "private"; private.mkdir()
    (private / "partial").mkdir()
    (private / "partial/progress.json").write_text(json.dumps({"status": "running", "completed": 2, "planned": 3}))
    monkeypatch.setattr(finish, "PRIVATE", private)
    monkeypatch.setattr(finish, "driver_active", lambda *args: False)
    assert finish.run() == 1
    state = json.loads((private / "finish_status.json").read_text())
    assert state["status"] == "needs_investigation" and state["completed"] == 2


def test_monitor_refreshes_snapshot_and_only_finishes_after_worker(tmp_path, monkeypatch):
    import scripts.reevaluation_followup_finish as finish
    import scripts.reevaluation_followup_report as report
    private = tmp_path / "private"; private.mkdir()
    (private / "partial").mkdir()
    work = tmp_path / "docs/analysis/work"; work.mkdir(parents=True)
    (work.parent.parent / "experiment_report_snapshot.json").write_text("{}")
    (work / "unchanged_sanity_report.json").write_text(json.dumps({"status": "passed", "groups": 50}))
    progress_path = private / "partial/progress.json"
    progress_path.write_text(json.dumps({"status": "running", "completed": 0, "planned": 1}))
    (private / "progress.json").write_text(json.dumps({"stage": "partial_rerun", "updated_at_utc": "2026-01-01T00:00:00+00:00"}))
    monkeypatch.setattr(finish, "PRIVATE", private)
    monkeypatch.setattr(finish, "WORK", work)
    active = iter([True, False])
    monkeypatch.setattr(finish, "driver_active", lambda *args: next(active))
    def sleep(*args):
        progress_path.write_text(json.dumps({"status": "completed", "completed": 1, "planned": 1}))
    monkeypatch.setattr(finish.time, "sleep", sleep)
    transitions, snapshots = [], []
    monkeypatch.setattr(finish, "publish", lambda *args: transitions.append(args[1:]))
    monkeypatch.setattr(report, "refresh_report", lambda value: snapshots.append(value))
    monkeypatch.setattr(report, "run", lambda: {"status": "completed"})
    assert finish.run() == 0
    assert snapshots[0]["partial_completed"] == 0
    assert transitions[-1] == ("reporting", "completed", 1, 1)


def test_reconstructed_stop_is_verified_against_pinned_rounds():
    from scripts.reevaluation_followup_report import verify_reconstruction
    case = {"key": "r:0", "record_key": "r", "condition_id": "baseline", "old_primary": {"L3": True}}
    plan = {"cases": [case]}
    results = {"r:0": {"primary": {"L3": True}}}
    audit = {"r:0": {"old_L3": "True", "new_L3": "True", "feedback_equal": "", "historical_prompt_evidence": "archived_reconstruction"}}
    rows = [{"record_key": "r", "status": "reconstructed", "stop_round": "0", "success": "True"}]
    verify_reconstruction(rows, {"cases": []}, plan, results, audit)
    with pytest.raises(ValueError, match="outcome mismatch"):
        verify_reconstruction([rows[0] | {"success": "False"}], {"cases": []}, plan, results, audit)
    with pytest.raises(ValueError, match="missing/duplicate"):
        verify_reconstruction([], {"cases": []}, plan, results, audit)


def test_mixed_path_cost_separates_saved_allocation_from_new_usage():
    from scripts.reevaluation_followup_report import mixed_record
    row = {"success": "False", "new_generation_tokens": 0,
           "status": "reconstructed", "stop_round": "3",
           "reconstructed_tokens_in": "7", "reconstructed_tokens_out": "3", "reconstructed_elapsed_sec": "2"}
    saved = mixed_record(row, None)
    assert saved["new_generation_tokens"] == 0 and saved["saved_prefix_allocated_tokens_in"] == 7
    partial = {"success": True, "stop_round": 1, "prefix": [{"tokens_in": 7, "tokens_out": 3, "elapsed_sec": 2}],
               "suffix": [{"tokens_in": 11, "tokens_out": 5, "elapsed_sec": 4}]}
    mixed = mixed_record(row | {"status": "requires_partial_rerun", "stop_round": ""}, partial)
    assert mixed["new_generation_tokens"] == 16 and mixed["new_tokens_in"] == 11 and mixed["new_tokens_out"] == 5
    assert mixed["saved_prefix_allocated_tokens_in"] == 7 and mixed["new_elapsed_sec"] == 4
    assert mixed["status"] == "completed_mixed_path" and mixed["stop_round"] == 1
    assert mixed["reconstruction_status"] == "requires_partial_rerun" and mixed["reconstructed_saved_stop_round"] == ""


def test_inventory_rejects_missing_or_ambiguous_historical_fields():
    from scripts.reevaluation_feedback_inventory import require_historical_fields
    entry = {"L0": True, "L1": True, "error_category": "wrong_output", "error_message": "bad",
             "L2_distance": .5, "actual_distribution": {"00": 1}, "extracted_code": "pass"}
    require_historical_fields(entry)
    with pytest.raises(ValueError, match="ambiguous"):
        require_historical_fields(entry | {"L2_distance": None})
    missing = dict(entry); missing.pop("error_message")
    with pytest.raises(ValueError, match="missing"):
        require_historical_fields(missing)


def test_new_auxiliary_disagreement_needs_spec_review_without_score_changes():
    from scripts.reevaluation_followup_report import verify_partial_auxiliary_reviews
    row = {"record_key": "r", "round": 2, "new_L3": True, "auxiliary_status": "fail", "new_code_sha256": "hash"}
    with pytest.raises(ValueError, match="separate task-specification review"):
        verify_partial_auxiliary_reviews([row], {})
    review = {"code_sha256": "hash", "task_specification_rationale": "固定入力と全ユニタリの被覆の違いを確認", "changes_primary_or_selection": False}
    assert verify_partial_auxiliary_reviews([row], {"r:2": review}) == [row]
    with pytest.raises(ValueError, match="preserve"):
        verify_partial_auxiliary_reviews([row], {"r:2": review | {"changes_primary_or_selection": True}})
    assert verify_partial_auxiliary_reviews([row | {"auxiliary_status": "not_applicable"}], {}) == []


def test_actual_api_model_and_usage_are_required_for_cost_reporting():
    from scripts.reevaluation_followup_report import verify_api_metadata
    case = {"model_spec": "ollama:test"}
    round_ = {"tokens_in": 5, "tokens_out": 7}
    response = {"model": "test", "usage": {"prompt_tokens": 5, "completion_tokens": 7}, "choices": [{"finish_reason": "length"}]}
    assert verify_api_metadata(case, round_, response) == ("test", "length")
    with pytest.raises(ValueError, match="model differs"):
        verify_api_metadata(case, round_, response | {"model": "other"})
    with pytest.raises(ValueError, match="default zero"):
        verify_api_metadata(case, round_, response | {"usage": None})
    with pytest.raises(ValueError, match="usage mismatch"):
        verify_api_metadata(case, {"tokens_in": 0, "tokens_out": 0}, response)
