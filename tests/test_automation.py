"""Verify publication gates, locking and resume without external requests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import automate_experiment as automation
from scripts import run_experiment


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    root = tmp_path_factory.mktemp("experiment")
    config = {
        "experiment_id": "automation_test", "models": ["mock-mixed"],
        "tasks": ["T1_Bell"], "seeds": [0, 1], "max_rounds": 1,
        "conditions": ["baseline", "self_refine", "execution_feedback", "self_debugging", "preventive_spec"],
        "output_dir": str(root / "output"),
    }
    path = root / "config.json"
    path.write_text(json.dumps(config))
    subprocess.run([sys.executable, "-m", "scripts.run_experiment", "--config", str(path)],
                   cwd=automation.ROOT, env=dict(os.environ, OMP_NUM_THREADS="1"), check=True,
                   capture_output=True, text=True)
    return config, root / "output", path


def test_code_failures_are_publishable(completed):
    config, output, _ = completed
    report = automation.verify(config, output)
    assert report["passed"]
    assert report["sanity"]["actual_records"] == 10
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
    assert any(not row["L2"] for row in rows)


@pytest.mark.parametrize("failure", ["generation_error", "missing", "duplicate", "unknown_error"])
def test_invalid_runs_cannot_publish(completed, tmp_path, failure):
    config, original, _ = completed
    output = tmp_path / "output"
    shutil.copytree(original, output)
    path = output / "raw.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if failure == "generation_error":
        rows[0]["rounds"][0]["generation_error"] = "Connection refused"
    elif failure == "unknown_error":
        rows[0]["rounds"][0]["error_category"] = "unknown_error"
    elif failure == "missing":
        rows.pop()
    else:
        rows.append(rows[0])
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert not automation.verify(config, output)["passed"]


def test_lock_rejects_overlapping_run(tmp_path):
    with automation.experiment_lock(tmp_path):
        with pytest.raises(RuntimeError, match="Another"):
            with automation.experiment_lock(tmp_path):
                pytest.fail("Second experiment acquired the lock")
    with automation.experiment_lock(tmp_path):
        pass


def test_completed_resume_preserves_manifest_and_makes_no_calls(completed, monkeypatch):
    config, output, path = completed
    before = json.loads((output / "manifest.json").read_text())
    raw_before = (output / "raw.jsonl").read_bytes()
    def forbidden(**kwargs):
        pytest.fail("Completed resume must not generate again")
    monkeypatch.setattr(run_experiment, "make_client", lambda _: SimpleNamespace(generate=forbidden))
    monkeypatch.setattr(sys, "argv", ["run_experiment", "--config", str(path)])
    assert run_experiment.main() == 0
    after = json.loads((output / "manifest.json").read_text())
    assert before["created_at_utc"] == after["created_at_utc"]
    assert after["elapsed_sec"] >= before["elapsed_sec"]
    assert after["records_written_this_run"] == 0
    assert (output / "raw.jsonl").read_bytes() == raw_before


def test_publication_excludes_raw_and_pushes_to_local_remote(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    monkeypatch.setattr(automation, "ROOT", repo)
    (repo / ".gitignore").write_text("results/\n.cache/\n")
    automation.git("add", ".gitignore")
    automation.git("-c", "user.name=test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial")
    automation.git("remote", "add", "origin", str(remote))
    output = repo / "results" / "test"
    output.mkdir(parents=True)
    for name in automation.ARTIFACTS:
        (output / name).write_text("{}\n")
    (output / "raw.jsonl").write_text("private input\n")
    branch = automation.require_clean_checkout(output)
    (repo / "unrelated.txt").write_text("user work")
    with pytest.raises(RuntimeError, match="Unrelated"):
        automation.publish(output, "test", branch)
    (repo / "unrelated.txt").unlink()
    automation.publish(output, "test", branch)
    files = automation.git("ls-files").splitlines()
    assert "results/test/automation_report.json" in files
    assert "results/test/raw.jsonl" not in files
    remote_head = subprocess.check_output(["git", "--git-dir", str(remote), "rev-parse", "main"], text=True).strip()
    assert automation.git("rev-parse", "HEAD") == remote_head
    # Existing reports may be updated by a resumed experiment.
    (output / "automation_report.json").write_text('{"resumed": true}\n')
    assert automation.require_clean_checkout(output) == "main"


def test_finalizer_waits_for_original_process(completed, monkeypatch, tmp_path):
    from scripts import finalize_completed_experiment as finalizer
    config, output, _ = completed
    monkeypatch.setattr(finalizer, 'read_state', lambda *args: dict(experiment_id=config['experiment_id'], pid=123, process_identity='original'))
    monkeypatch.setattr(finalizer, 'process_identity', lambda pid: 'original')
    assert finalizer.completion_gate(config, output, tmp_path)[0] == 'waiting'


def test_finalizer_only_accepts_complete_healthy_records(completed, monkeypatch, tmp_path):
    from scripts import finalize_completed_experiment as finalizer
    config, original, _ = completed
    output = tmp_path / 'output'
    shutil.copytree(original, output)
    monkeypatch.setattr(finalizer, 'read_state', lambda *args: dict(experiment_id=config['experiment_id'], pid=123, process_identity='original'))
    monkeypatch.setattr(finalizer, 'process_identity', lambda pid: None)
    assert finalizer.completion_gate(config, output, tmp_path)[0] == 'ready'
    path = output / 'raw.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['rounds'][0]['generation_error'] = 'Connection refused'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert finalizer.completion_gate(config, output, tmp_path)[0] == 'blocked'
    rows.pop()
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert finalizer.completion_gate(config, output, tmp_path)[0] == 'blocked'


def test_finalizer_waits_for_child_holding_lock(completed, monkeypatch, tmp_path):
    from scripts import finalize_completed_experiment as finalizer
    config, output, _ = completed
    monkeypatch.setattr(finalizer, 'read_state', lambda *args: dict(experiment_id=config['experiment_id'], pid=123, process_identity='original'))
    monkeypatch.setattr(finalizer, 'process_identity', lambda pid: None)
    with automation.experiment_lock(tmp_path):
        assert finalizer.completion_gate(config, output, tmp_path)[0] == 'waiting'


def test_finalizer_invokes_saved_resume_without_new_run(tmp_path, monkeypatch):
    from scripts import finalize_completed_experiment as finalizer
    output = tmp_path / 'results/existing'
    output.mkdir(parents=True)
    source = output / 'experiment_config.json'
    source.write_text(json.dumps({'experiment_id': 'existing'}))
    monkeypatch.setattr(finalizer, 'ROOT', tmp_path)
    monkeypatch.setattr(finalizer, 'output_path', lambda config: output)
    monkeypatch.setattr(finalizer, 'completion_gate', lambda *args: ('ready', 'checked'))
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(finalizer.subprocess, 'run', run)
    assert finalizer.main(['--config', str(source)]) == 0
    assert len(commands) == 1
    assert commands[0][commands[0].index('--config') + 1] == str(source)
    assert '--new-run' not in commands[0]
    assert commands[0][-2:] == ['--notify', 'none']
    status = json.loads(next((tmp_path / '.cache/finalizers').glob('*.json')).read_text())
    assert status['status'] == 'completed'
