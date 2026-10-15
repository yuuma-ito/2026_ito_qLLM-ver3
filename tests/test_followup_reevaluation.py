from datetime import datetime, timezone, timedelta
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.followup_reevaluation import (CHECKS, WORKSPACE, launch_once, notify,
                                         heartbeat, paths, publish, readiness)
from tests.test_notify_reevaluation import terminal_run


def test_followup_waits_for_full_completion_and_rejects_corrupt_artifacts(tmp_path):
    out = terminal_run(tmp_path)
    state = json.loads((out / "run_status.json").read_text())
    state["status"] = "running"
    (out / "run_status.json").write_text(json.dumps(state))
    assert readiness(out, root=tmp_path) == "waiting"
    state["status"] = "completed"
    (out / "run_status.json").write_text(json.dumps(state))
    assert readiness(out, root=tmp_path) == "ready"
    (out / "final/summary.json").write_text('{}')
    with pytest.raises(ValueError, match="artifact mismatch"):
        readiness(out, root=tmp_path)


def test_attention_can_start_audit_but_not_claim_clean_results(tmp_path):
    out = terminal_run(tmp_path, attention=1)
    assert readiness(out, root=tmp_path) == "audit_only"


def test_completed_status_still_waits_for_driver_lock_release(tmp_path):
    out = terminal_run(tmp_path)
    state = json.loads((out / 'run_status.json').read_text())
    with (Path(state['checkpoint_dir']) / 'driver.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert readiness(out, root=tmp_path) == 'waiting'
    assert readiness(out, root=tmp_path) == 'ready'


def test_persistent_notification_ambiguity_has_no_retry_and_no_secret(tmp_path):
    out = terminal_run(tmp_path); calls = []
    def fail(*args):
        calls.append(1)
        raise RuntimeError("private credentials")
    assert notify(out, "configured", "safe", root=tmp_path, sender=fail) == "delivery_unconfirmed"
    assert notify(out, "configured", "safe", root=tmp_path, sender=fail) == "delivery_unconfirmed"
    assert len(calls) == 1
    _, private = paths(out, tmp_path)
    assert "private credentials" not in (private / "notification_configured.json").read_text()


def test_stage_journal_preserves_fast_transitions_without_immediate_mail(tmp_path):
    out = terminal_run(tmp_path)
    publish(out, "validation", "running", 0, 2, root=tmp_path)
    publish(out, "validation", "completed", 2, 2, root=tmp_path)
    _, private = paths(out, tmp_path)
    events = [json.loads(p.read_text()) for p in sorted(private.glob('event_*.json'))]
    assert len(events) == 2
    assert events[0]['status'] == 'running' and events[1]['status'] == 'completed'
    assert not list(private.glob('notification_*.json'))


def test_reporting_completion_requires_all_checks(tmp_path):
    out = terminal_run(tmp_path)
    with pytest.raises(FileNotFoundError):
        publish(out, "reporting", "completed", 1, 1, root=tmp_path)
    work = tmp_path / WORKSPACE; work.mkdir()
    (work / "README.md").write_text("報告")
    (work / "completion_checks.json").write_text(json.dumps({k: True for k in CHECKS}))
    assert publish(out, "reporting", "completed", 1, 1, root=tmp_path)["status"] == "completed"


def test_launch_once_requires_work_completion_not_only_zero_exit(tmp_path):
    out = terminal_run(tmp_path); (out / "followup_plan.md").write_text("作業指示")
    calls = []; sent = []
    def fake(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(pid=123, poll=lambda: 0, returncode=0)
    assert launch_once(out, root=tmp_path, popen=fake, sender=lambda text, _:sent.append(text)) == "blocked"
    assert launch_once(out, root=tmp_path, popen=fake, sender=lambda *args:None) == "blocked"
    assert len(calls) == 1
    assert "--sandbox" in calls[0] and "workspace-write" in calls[0]
    assert "--dangerously-bypass-approvals-and-sandbox" not in calls[0]


def test_successful_job_and_its_notifications_are_not_repeated(tmp_path):
    out = terminal_run(tmp_path); (out / "followup_plan.md").write_text("作業指示")
    work = tmp_path / WORKSPACE; work.mkdir()
    (work / "README.md").write_text("検証済み報告")
    (work / "completion_checks.json").write_text(json.dumps({k: True for k in CHECKS}))
    calls = []
    def fake(*args, **kwargs):
        calls.append(1)
        publish(out, "reporting", "completed", 2, 2, root=tmp_path)
        return SimpleNamespace(pid=123, poll=lambda: 0, returncode=0)
    assert launch_once(out, root=tmp_path, popen=fake, sender=lambda *a:None) == "completed"
    assert launch_once(out, root=tmp_path, popen=fake, sender=lambda *a:None) == "completed"
    assert len(calls) == 1


def test_runtime_failure_cannot_launch_followup(tmp_path):
    out = terminal_run(tmp_path, status="blocked_runtime_failure")
    def forbidden(*args, **kwargs):
        raise AssertionError("must not start")
    assert launch_once(out, root=tmp_path, popen=forbidden) == "blocked"


def test_heartbeat_reports_latest_stage_counts_without_duplicate_send(tmp_path):
    out = terminal_run(tmp_path); sent = []
    publish(out, "partial_rerun", "running", 3, 10, root=tmp_path)
    sender = lambda text, _: sent.append(text)
    heartbeat(out, root=tmp_path, sender=sender)
    heartbeat(out, root=tmp_path, sender=sender)
    assert len(sent) == 1
    assert "部分再実験" in sent[0] and "3／10" in sent[0]


def test_periodic_mail_waits_three_hours_after_previous_notice(tmp_path):
    out = terminal_run(tmp_path); sent = []
    sender = lambda text, _: sent.append(text)
    notify(out, 'configured', 'setup', root=tmp_path, sender=sender)
    start = datetime.now(timezone.utc)
    assert heartbeat(out, root=tmp_path, sender=sender, at=start+timedelta(hours=2, minutes=59)) == 'not_due'
    assert len(sent) == 1
    assert heartbeat(out, root=tmp_path, sender=sender, at=start+timedelta(hours=3, seconds=1)) == 'smtp_accepted'
    assert len(sent) == 2
