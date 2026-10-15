from datetime import datetime
import json
from zoneinfo import ZoneInfo

import pytest

from scripts.overnight_rescue_work import next_slot, notify_once, completion_status, read_progress

JST = ZoneInfo('Asia/Tokyo')


@pytest.mark.parametrize('given,expected', [
    ('2026-10-16T00:07:00', '2026-10-16T03:00:00'),
    ('2026-10-16T02:59:59', '2026-10-16T03:00:00'),
    ('2026-10-16T03:00:00', '2026-10-16T06:00:00'),
    ('2026-10-16T23:30:00', '2026-10-17T00:00:00'),
])
def test_reports_align_to_wall_clock(given, expected):
    assert next_slot(datetime.fromisoformat(given).replace(tzinfo=JST)) == datetime.fromisoformat(expected).replace(tzinfo=JST)


def test_duplicate_event_does_not_send_twice(tmp_path):
    sent = []
    sender = lambda *args: sent.append(args)
    assert notify_once(tmp_path, 'event', 'report', sender=sender) == 'smtp_accepted'
    assert notify_once(tmp_path, 'event', 'report', sender=sender) == 'smtp_accepted'
    assert len(sent) == 1


def test_uncertain_delivery_not_retried_and_secrets_not_logged(tmp_path):
    calls = []
    def sender(*args):
        calls.append(args)
        raise OSError('secret-like SMTP response')
    assert notify_once(tmp_path, 'event', 'report', sender=sender) == 'delivery_unconfirmed'
    assert notify_once(tmp_path, 'event', 'report', sender=sender) == 'delivery_unconfirmed'
    assert len(calls) == 1
    assert 'secret-like' not in (tmp_path / 'notifications/event.json').read_text()


def test_no_completion_claim_on_zero_exit_without_validation(tmp_path):
    assert completion_status(0, tmp_path) == 'needs_review'
    (tmp_path / 'completion.json').write_text(json.dumps({'status': 'completed', 'validation_passed': True, 'required_artifacts': []}))
    assert completion_status(0, tmp_path) == 'needs_review'
    assert completion_status(1, tmp_path) == 'failed'


def test_read_progress_handles_partial_write(tmp_path):
    (tmp_path / 'progress.json').write_text('{')
    assert 'current_step' in read_progress(tmp_path)
