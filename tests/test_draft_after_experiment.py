"""Completion gates and one-shot AI/notification behavior, without external calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from harness.run_state import atomic_json, state_path
from scripts import draft_after_experiment as drafts
from scripts.automate_experiment import experiment_lock


@pytest.fixture
def finished(tmp_path):
    output = tmp_path / 'results' / 'draft_test'
    config = dict(experiment_id='draft_test', models=['mock-mixed'], tasks=['T1_Bell'],
                  seeds=[0, 1], max_rounds=1,
                  conditions=['baseline', 'self_refine', 'execution_feedback',
                              'self_debugging', 'preventive_spec'], output_dir=str(output))
    source = tmp_path / 'config.json'
    source.write_text(json.dumps(config))
    subprocess.run([sys.executable, '-m', 'scripts.run_experiment', '--config', str(source)],
                   cwd=drafts.ROOT, env=dict(os.environ, OMP_NUM_THREADS='1'),
                   capture_output=True, check=True)
    atomic_json(state_path(output, tmp_path), dict(experiment_id='draft_test', pid=99999999,
                                                  process_identity=None, status='completed'))
    atomic_json(output / 'automation_report.json', dict(passed=True))
    docs = tmp_path / 'docs'
    for name in ('midterm2026', 'winf2026'):
        (docs / name).mkdir(parents=True)
        (docs / name / 'paper.tex').write_text('reference source')
        (docs / name / 'paper.pdf').write_bytes(b'%PDF-reference')
        (docs / name / 'winf-paper.sty').write_text('style')
    (docs / 'experiment_report_draft.md').write_text('reference report')
    atomic_json(docs / 'experiment_report_snapshot.json', dict(runs=[dict(
        experiment_id='draft_test', source_dir='results/draft_test', recorded=10)]))
    return config, output, tmp_path


def test_waits_for_process_and_shared_lock(finished, monkeypatch):
    config, output, root = finished
    path = state_path(output, root)
    state = json.loads(path.read_text())
    atomic_json(path, dict(state, process_identity='live'))
    monkeypatch.setattr(drafts, 'process_identity', lambda _: 'live')
    assert drafts.gate(config, root)[0] == 'waiting'
    atomic_json(path, state)
    with experiment_lock(root):
        assert drafts.gate(config, root)[0] == 'waiting'
    assert drafts.gate(config, root)[0] == 'ready'


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'mixed', 'partial'])
def test_incomplete_or_inconsistent_data_never_starts_ai(finished, monkeypatch, problem):
    config, output, root = finished
    path = output / 'raw.jsonl'
    rows = path.read_text().splitlines()
    if problem == 'missing':
        rows.pop()
    elif problem == 'duplicate':
        rows.append(rows[0])
    elif problem == 'mixed':
        row = json.loads(rows[0])
        row['experiment_id'] = 'other'
        rows[0] = json.dumps(row)
    path.write_text('\n'.join(rows) + ('' if problem == 'partial' else '\n'))
    monkeypatch.setattr(drafts.subprocess, 'run', lambda *a, **k: pytest.fail('AI started'))
    assert drafts.launch(config, root=root, transport='none')['status'] in {'waiting', 'blocked'}


def test_api_errors_and_missing_verification_produce_provisional_gate(finished):
    config, output, root = finished
    (output / 'automation_report.json').unlink()
    assert drafts.gate(config, root)[0] == 'ready_provisional'
    atomic_json(output / 'automation_report.json', dict(passed=True))
    path = output / 'raw.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['rounds'][0]['generation_error'] = 'Connection refused'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert drafts.gate(config, root)[0] == 'ready_provisional'


def fake_ai(command, **kwargs):
    workspace = Path(command[command.index('--cd') + 1])
    assert '--sandbox' in command and 'workspace-write' in command
    assert 'Git操作' in kwargs['input']
    for name in drafts.REQUIRED:
        path = workspace / name
        path.write_bytes(b'%PDF-new' if path.suffix == '.pdf' else b'new draft')
    response = Path(command[command.index('--output-last-message') + 1])
    atomic_json(response, dict(status='completed', summary='created'))
    return subprocess.CompletedProcess(command, 0)


def test_creates_new_drafts_once_and_does_not_replace_reference(finished, monkeypatch):
    config, output, root = finished
    calls, deliveries = [], []
    def run(command, **kwargs):
        calls.append(command)
        return fake_ai(command, **kwargs)
    monkeypatch.setattr(drafts.subprocess, 'run', run)
    monkeypatch.setattr(drafts, 'notify', lambda *args: deliveries.append(args))
    state = drafts.launch(config, root=root)
    assert state['status'] == 'completed'
    assert state['notification'] == 'accepted'
    assert len(state['files']) == len(drafts.REQUIRED)
    workspace = Path(state['workspace'])
    assert json.loads((workspace / 'results_snapshot.json').read_text())['runs'][0]['recorded'] == 10
    assert (workspace / 'reference/midterm2026/paper.tex').read_text() == 'reference source'
    assert (root / 'docs/midterm2026/paper.pdf').read_bytes() == b'%PDF-reference'
    assert drafts.launch(config, root=root)['status'] == 'completed'
    assert len(calls) == len(deliveries) == 1


def test_timeout_does_not_retry_and_explicit_retry_recovers(finished, monkeypatch):
    config, _, root = finished
    calls = []
    def timeout(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, 1)
    monkeypatch.setattr(drafts.subprocess, 'run', timeout)
    assert drafts.launch(config, root=root, transport='none')['status'] == 'failed'
    assert drafts.launch(config, root=root, transport='none')['status'] == 'failed'
    assert len(calls) == 1
    monkeypatch.setattr(drafts.subprocess, 'run', fake_ai)
    assert drafts.launch(config, root=root, transport='none', retry=True)['status'] == 'completed'


def test_exit_zero_without_artifacts_is_failure(finished, monkeypatch):
    config, _, root = finished
    def empty(command, **kwargs):
        response = Path(command[command.index('--output-last-message') + 1])
        atomic_json(response, dict(status='completed', summary='no files'))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(drafts.subprocess, 'run', empty)
    assert drafts.launch(config, root=root, transport='none')['status'] == 'failed'


def test_delivery_failure_does_not_regenerate_or_resend(finished, monkeypatch):
    config, _, root = finished
    calls = []
    monkeypatch.setattr(drafts.subprocess, 'run', fake_ai)
    def failed(*args):
        calls.append(args)
        raise RuntimeError('SMTP connection failed')
    monkeypatch.setattr(drafts, 'notify', failed)
    assert drafts.launch(config, root=root)['notification'] == 'failed'
    assert drafts.launch(config, root=root)['notification'] == 'failed'
    assert len(calls) == 1


def test_dry_run_does_not_prepare_workspace_or_record_attempt(finished, monkeypatch):
    config, _, root = finished
    monkeypatch.setattr(drafts.subprocess, 'run', lambda *a, **k: pytest.fail('AI started'))
    assert drafts.launch(config, root=root, dry_run=True)['status'] == 'ready'
    assert not (root / 'docs/completion_drafts').exists()
    assert not list((root / '.cache/draft_jobs').glob('*.json'))
