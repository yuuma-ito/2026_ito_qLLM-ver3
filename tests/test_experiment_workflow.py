"""Operational workflows with mock generation and local files; no live notifications."""
import csv
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from harness.experiment import expected_keys, validate_config
from harness.run_state import RunTracker, atomic_json, observation, read_state, state_path
from scripts import automate_experiment, compare_experiments, monitor_experiments, notify_progress
from scripts import prepare_retry, run_experiment, run_queue
from scripts.experiment_events import emit_event
from scripts.sanity_check import check_results


def config(output="results/test", experiment_id="test"):
    return {"experiment_id": experiment_id, "models": ["mock-correct"], "tasks": ["T1_Bell"],
            "seeds": [0], "conditions": ["baseline"], "max_rounds": 0, "output_dir": str(output)}


def test_runtime_tracks_borrowed_progress_and_terminal_status(tmp_path):
    output = tmp_path / "results/test"
    with RunTracker(output, "test", root=tmp_path, heartbeat_interval=.01) as owner:
        owner.update(phase="generating")
        before = read_state(output, tmp_path)
        with RunTracker(output, "test", root=tmp_path, borrowed_token=owner.token) as child:
            child.update(recorded=3)
        time.sleep(.04)
        current = read_state(output, tmp_path)
        assert current["pid"] == os.getpid()
        assert current["recorded"] == 3
        assert current["heartbeat_at"] > before["heartbeat_at"]
        assert observation(current) == "running"
        with pytest.raises(RuntimeError):
            with RunTracker(output, "test", root=tmp_path):
                pytest.fail("Concurrent owner acquired the same run")
        owner.finish(phase="completed", published=True)
    assert observation(read_state(output, tmp_path)) == "completed"


def test_runtime_distinguishes_crash_heartbeat_and_stall(tmp_path):
    output = tmp_path / "results/test"
    with RunTracker(output, "test", root=tmp_path) as tracker:
        state = read_state(output, tmp_path)
        now = time.time()
        assert observation(dict(state, progress_at=now - 7200, heartbeat_at=now), now=now) == "stalled"
        assert observation(dict(state, heartbeat_at=now - 100), now=now) == "heartbeat_stale"
        assert observation(dict(state, pid=999999999), now=now) == "interrupted"
    with pytest.raises(ValueError):
        with RunTracker(output, "test", root=tmp_path):
            raise ValueError("private error")
    state = read_state(output, tmp_path)
    assert state["status"] == "failed"
    assert state["failure_type"] == "ValueError"
    assert "private error" not in json.dumps(state)


def test_monitor_detects_disappeared_process_and_notifies_once(tmp_path, monkeypatch):
    output = tmp_path / "results/test"
    with RunTracker(output, "test", root=tmp_path) as tracker:
        tracker.update(notification_transport="email")
    state = read_state(output, tmp_path)
    state.update(status="running", pid=999999999)
    atomic_json(state_path(output, tmp_path), state)
    sent = []
    monkeypatch.setattr(notify_progress, "deliver", lambda *args: sent.append(args))
    before = state_path(output, tmp_path).read_bytes()
    assert monitor_experiments.inspect_runs(tmp_path, dry_run=True)[0]["status"] == "interrupted"
    assert state_path(output, tmp_path).read_bytes() == before
    for _ in range(2):
        assert monitor_experiments.inspect_runs(tmp_path)[0]["status"] == "interrupted"
    assert len(sent) == 1
    assert read_state(output, tmp_path)["status"] == "interrupted"


def test_notification_failure_does_not_fail_run_or_repeat(tmp_path, monkeypatch):
    output = tmp_path / "results/test"
    attempts = []
    def unavailable(*args):
        attempts.append(args)
        raise RuntimeError("private SMTP details")
    monkeypatch.setattr(notify_progress, "deliver", unavailable)
    with RunTracker(output, "test", root=tmp_path) as tracker:
        tracker.finish(phase="completed")
        assert not emit_event(output, "completed", "email", root=tmp_path)
        assert not emit_event(output, "completed", "email", root=tmp_path)
    assert len(attempts) == 1
    assert read_state(output, tmp_path)["status"] == "completed"
    ledgers = list((tmp_path / ".cache/notification_events").glob("*.json"))
    assert len(ledgers) == 1
    assert "private SMTP details" not in ledgers[0].read_text()


def test_sparse_api_retry_preserves_original_and_shared_condition_sets(tmp_path, monkeypatch):
    original = dict(config(), models=["mock-correct", "mock-wrong"], tasks=["T1_Bell", "T3a_DJ_constant"],
                    seeds=[0, 1], conditions=["baseline", "self_refine"], max_rounds=1)
    def record(model, task, seed, **extra):
        return {"experiment_id": "test", "model_spec": model, "task_id": task,
                "base_seed": seed, "condition_id": "baseline", **extra}
    rows = [record("mock-correct", "T1_Bell", 0, rounds=[{"generation_error": "connection failure"}]),
            record("mock-wrong", "T3a_DJ_constant", 1, timeout_flag=True),
            record("mock-wrong", "T1_Bell", 1, error_category="wrong_output"),
            record("mock-correct", "T3a_DJ_constant", 0, error_category="unknown_error")]
    raw = tmp_path / "source.jsonl"
    raw.write_text("".join(json.dumps(row) + "\n" for row in rows))
    before = raw.read_bytes()
    retry = prepare_retry.prepare_retry(original, raw, stamp="test_stamp")
    plan = validate_config(retry)
    assert len(plan["pair_keys"]) == 2
    assert plan["planned_records"] == 4
    assert len(expected_keys(plan)) == 4
    retry["output_dir"] = str(tmp_path / "retry_output")
    path = tmp_path / "retry.json"
    path.write_text(json.dumps(retry))
    monkeypatch.delenv("QLLM_RUN_TOKEN", raising=False)
    monkeypatch.setenv("QLLM_EVENT_TRANSPORT", "none")
    assert run_experiment.main(["--config", str(path)]) == 0
    assert check_results(retry, Path(retry["output_dir"]) / "raw.jsonl")["passed"]
    assert raw.read_bytes() == before
    assert retry["conditions"] == original["conditions"]
    assert retry["retry_of"]["experiment_id"] == original["experiment_id"]


def test_evaluation_failure_alone_is_not_a_retry_target(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps({"experiment_id": "test", "model_spec": "mock-correct", "task_id": "T1_Bell",
                               "base_seed": 0, "condition_id": "baseline", "error_category": "wrong_output"}) + "\n")
    with pytest.raises(ValueError, match="No API transport"):
        prepare_retry.prepare_retry(config(), raw)


def test_resume_refreshes_records_after_taking_generation_lock(tmp_path, monkeypatch):
    cfg = config(tmp_path / "output")
    source = tmp_path / "config.json"
    source.write_text(json.dumps(cfg))
    monkeypatch.delenv("QLLM_RUN_TOKEN", raising=False)
    monkeypatch.setenv("QLLM_EVENT_TRANSPORT", "none")
    assert run_experiment.main(["--config", str(source)]) == 0
    raw = tmp_path / "output/raw.jsonl"
    before = raw.read_bytes()
    real_load = run_experiment.load_existing
    reads = []
    def raced_load(path):
        reads.append(path)
        return ([], set()) if len(reads) == 1 else real_load(path)
    monkeypatch.setattr(run_experiment, "load_existing", raced_load)
    monkeypatch.setattr(run_experiment, "generate_initial", lambda *_a, **_k: pytest.fail("Completed pair generated again"))
    assert run_experiment.main(["--config", str(source)]) == 0
    assert len(reads) == 2
    assert raw.read_bytes() == before


def make_queue(tmp_path):
    source = tmp_path / "config.json"
    source.write_text(json.dumps(config()))
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps({"queue_id": "test_queue", "notify": "none", "jobs": [
        {"id": "first", "config": "config.json", "new_run": True},
        {"id": "second", "config": "config.json", "new_run": True}]}))
    return source, queue, tmp_path / ".cache/queues/test_queue/state.json"


def test_queue_failure_resume_keeps_materialized_ids_and_completed_jobs(tmp_path):
    _, queue, state_path = make_queue(tmp_path)
    calls = []
    def job(command):
        calls.append(command)
        return 0 if len(calls) == 1 else 1
    assert run_queue.execute_queue(queue, root=tmp_path, run_job=job) == 1
    before = json.loads(state_path.read_text())
    assert [j["status"] for j in before["jobs"]] == ["completed", "failed"]
    assert run_queue.execute_queue(queue, root=tmp_path, run_job=job) == 1
    assert len(calls) == 2
    assert run_queue.execute_queue(queue, root=tmp_path, retry_failed=True, run_job=lambda command: calls.append(command) or 0) == 0
    after = json.loads(state_path.read_text())
    assert len(calls) == 3
    assert [j["experiment_id"] for j in after["jobs"]] == [j["experiment_id"] for j in before["jobs"]]
    assert run_queue.execute_queue(queue, root=tmp_path, run_job=lambda _: pytest.fail("Completed queue reran")) == 0


def test_queue_dry_run_writes_nothing_and_config_changes_require_new_id(tmp_path):
    source, queue, state_path = make_queue(tmp_path)
    assert run_queue.execute_queue(queue, root=tmp_path, dry_run=True) == 0
    assert not state_path.exists()
    assert run_queue.execute_queue(queue, root=tmp_path, run_job=lambda _: 0) == 0
    source.write_text(json.dumps(dict(config(), seeds=[0, 1])))
    with pytest.raises(ValueError, match="changed"):
        run_queue.execute_queue(queue, root=tmp_path, run_job=lambda _: pytest.fail("Changed queue ran"))


def test_queue_does_not_restart_a_live_or_published_orphan(tmp_path):
    _, queue, queue_state = make_queue(tmp_path)
    # Materialize but stop the first job, then simulate losing its queue supervisor.
    assert run_queue.execute_queue(queue, root=tmp_path, run_job=lambda _: 1) == 1
    saved = json.loads(queue_state.read_text())
    saved["jobs"][0]["status"] = "running"
    atomic_json(queue_state, saved)
    first = saved["jobs"][0]
    with RunTracker(Path(first["output"]), first["experiment_id"], root=tmp_path) as tracker:
        assert run_queue.execute_queue(queue, root=tmp_path, run_job=lambda _: pytest.fail("Live job reran")) == 1
        tracker.finish(published=True)
    calls = []
    assert run_queue.execute_queue(queue, root=tmp_path, run_job=lambda command: calls.append(command) or 0) == 0
    assert len(calls) == 1  # Only the second job starts.


def test_comparison_weights_groups_and_never_subtracts_different_cohorts(tmp_path):
    outputs = []
    for name, seed, rates in [("old", 0, [.0, .5]), ("new", 0, [.5, 1.0]), ("different", 1, [1.0, 1.0])]:
        output = tmp_path / name
        output.mkdir()
        cfg = dict(config(experiment_id=name), seeds=list(range(seed, seed + 4)))
        manifest = {"experiment_id": name, "config": cfg, "schema_version": "2.0", "sanity_passed": True,
                    "created_at_utc": "2026-01-01T00:00:00+00:00", "completed_at_utc": f"2026-01-0{len(outputs) + 1}T00:00:00+00:00"}
        (output / "manifest.json").write_text(json.dumps(manifest))
        (output / "automation_report.json").write_text('{"passed": true}')
        with (output / "summary_by_condition.csv").open("w", newline="") as handle:
            fields = ["model_spec", "condition_id", "intervention", "n", "L2_rate", "avg_elapsed_sec", "avg_total_tokens"]
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for n, rate in zip([1, 3], rates):
                writer.writerow(dict(zip(fields, ["mock-correct", "baseline", "baseline", n, rate, 2, 10])))
        (output / "rescue_rates_by_error.csv").write_text("model_spec,intervention,rescued,n_baseline_failures\n")
        outputs.append(output)
    rows = compare_experiments.write_comparison(outputs, tmp_path / "comparison")
    by_id = {row["experiment_id"]: row for row in rows}
    assert by_id["old"]["L2_rate"] == .375
    assert by_id["new"]["L2_change_pp"] == 50
    assert by_id["new"]["previous_experiment_id"] == "old"
    assert by_id["different"]["L2_change_pp"] == ""
    assert (tmp_path / "comparison/comparison_report.md").exists()


@pytest.mark.parametrize("push_failure", [False, True])
def test_automation_manages_child_state_and_records_push_outcome(tmp_path, monkeypatch, push_failure):
    monkeypatch.setattr(automate_experiment, "ROOT", tmp_path)
    monkeypatch.setattr(run_experiment, "ROOT", tmp_path)
    monkeypatch.setattr(automate_experiment, "require_clean_checkout", lambda _: "main")
    source = tmp_path / "config.json"
    source.write_text(json.dumps(config()))
    calls = []
    def run(command, *, env=None, **kwargs):
        calls.append(command)
        if "pytest" in command:
            assert "QLLM_RUN_TOKEN" not in env
        else:
            assert kwargs.get("pass_fds")
            with monkeypatch.context() as isolated:
                isolated.setenv("QLLM_RUN_TOKEN", env["QLLM_RUN_TOKEN"])
                isolated.setenv("QLLM_EVENT_TRANSPORT", "none")
                assert run_experiment.main(["--config", command[-1]]) == 0
    def publish(*args):
        if push_failure:
            raise subprocess.CalledProcessError(1, ["git", "push"])
    monkeypatch.setattr(automate_experiment, "run", run)
    monkeypatch.setattr(automate_experiment, "publish", publish)
    assert automate_experiment.main(["--config", str(source), "--notify", "none"]) == int(push_failure)
    state = read_state(tmp_path / "results/test", tmp_path)
    assert state["status"] == ("failed" if push_failure else "completed")
    if push_failure:
        assert state["terminal_event"] == "publish_failed"
    else:
        assert state["published"]
    assert len(calls) == 2
    assert automate_experiment.verify(config(), tmp_path / "results/test")["passed"]
