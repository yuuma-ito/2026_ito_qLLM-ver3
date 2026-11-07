"""Status aggregation and notification observations without model/network calls."""
import json

import pytest

from harness.run_state import RunTracker
from scripts import notify_progress as notify
from scripts import research_status as status


def experiment(root, name='test'):
    config = dict(experiment_id=name, models=['mock'], tasks=['T1_Bell'],
                  seeds=[0, 1], conditions=['baseline'], output_dir=f'results/{name}')
    output = root / config['output_dir']
    output.mkdir(parents=True)
    (output / 'experiment_config.json').write_text(json.dumps(config))
    row = dict(experiment_id=name, condition_id='baseline', model_spec='mock',
               task_id='T1_Bell', base_seed=0, L2=False, rounds=[])
    (output / 'raw.jsonl').write_text(json.dumps(row) + '\n')
    return config, output


def test_rate_and_eta_require_same_run_and_observed_progress():
    p = dict(identity='a', recorded=25, planned=100, runtime_status='running', issues=[])
    old = dict(identity='a', recorded=10, observed_at=100)
    result = status.trend(p, old, 3700)
    assert result['delta'] == 15
    assert result['records_per_hour'] == 15
    assert result['eta_hours'] == 5
    for change in (dict(identity='new'), dict(recorded=5)):
        assert status.trend({**p, **change}, old, 3700)['delta'] is None
    for change in (dict(runtime_status='interrupted'), dict(runtime_status='stalled'),
                   dict(issues=['API障害']), dict(planned_is_upper_bound=True), dict(recorded=10)):
        assert status.trend({**p, **change}, old, 3700)['eta_hours'] is None
    assert status.trend(p, old, 120)['eta_hours'] is None


def test_bad_record_is_isolated_and_private_data_not_copied(tmp_path):
    experiment(tmp_path, 'good')
    _, bad = experiment(tmp_path, 'bad')
    (bad / 'raw.jsonl').write_text('private-generated-code\n')
    items = status.collect(tmp_path)
    assert len(items) == 2
    good = next(p for p in items if p['experiment_id'] == 'good')
    assert good['recorded'] == 1
    bad_item = next(p for p in items if p['experiment_id'] == 'bad')
    assert bad_item['issues'] and bad_item['identity'] is None
    text = json.dumps(status.serializable(items)) + status.markdown(items, 100, tmp_path)
    assert 'private-generated-code' not in text
    assert '未確認' in text


def test_restart_does_not_reuse_old_speed(tmp_path):
    config, output = experiment(tmp_path)
    with RunTracker(output, config['experiment_id'], root=tmp_path):
        before = status.collect(tmp_path, now=100)
        status.save_history(before, tmp_path, 'dashboard')
        previous = status.read_history(tmp_path, 'dashboard')
        assert status.collect(tmp_path, previous=previous, now=3700)[0]['delta'] == 0
    with RunTracker(output, config['experiment_id'], root=tmp_path):
        assert status.collect(tmp_path, previous=previous, now=7300)[0]['delta'] is None


def test_completion_does_not_imply_verification_or_publication(tmp_path):
    config, output = experiment(tmp_path)
    with RunTracker(output, config['experiment_id'], root=tmp_path) as tracker:
        tracker.finish('completed')
    p = status.collect(tmp_path)[0]
    assert p['verification'] == {}
    assert p['issues']
    (output / 'automation_report.json').write_text('{"passed": false}')
    p = status.collect(tmp_path)[0]
    assert p['verification']['automation_report.json'] == '失敗'
    assert 'プッシュ成功' not in p['state']


@pytest.mark.parametrize('schema', ['notification_ablation_v1', 'factorial_pilot_v1'])
def test_request_budget_is_not_presented_as_exact_record_count(tmp_path, schema):
    output = tmp_path / 'results/pilot'
    output.mkdir(parents=True)
    (output / 'experiment_config.json').write_text(json.dumps(dict(
        schema=schema, run_id='pilot', output_dir='results/pilot', max_total_requests=90)))
    (output / 'progress.json').write_text('{"completed_requests": 15}')
    p = status.collect(tmp_path)[0]
    assert p['recorded'] == 15 and p['planned_is_upper_bound']
    assert '要求（上限）' in status.markdown([p], 100, tmp_path)
    assert p['eta_hours'] is None


def test_verified_early_stopping_is_not_reported_as_missing_records(tmp_path):
    output = tmp_path / 'results/pilot'
    output.mkdir(parents=True)
    analysis = tmp_path / 'docs/analysis/pilot/final'
    analysis.mkdir(parents=True)
    (analysis / 'validation_report.json').write_text('{"passed": true}')
    (output / 'experiment_config.json').write_text(json.dumps(dict(
        schema='factorial_pilot_v1', run_id='pilot', output_dir='results/pilot',
        max_total_requests=90, analysis_dir='docs/analysis/pilot')))
    (output / 'progress.json').write_text('{"actual_requests": 15}')
    with RunTracker(output, 'pilot', root=tmp_path) as tracker:
        tracker.finish('completed')
    p = status.collect(tmp_path)[0]
    assert p['recorded'] == 15 and p['planned'] == 90
    assert p['verification']['final/validation_report.json'] == '成功'
    assert not p['issues']


def test_only_accepted_delivery_updates_notification_baseline(tmp_path, monkeypatch):
    experiment(tmp_path)
    monkeypatch.setattr(notify, 'ROOT', tmp_path)
    monkeypatch.setattr(notify, 'load_dotenv', lambda *_: None)
    calls = []
    monkeypatch.setattr(notify, 'deliver', lambda *args: calls.append(args))
    args = ['--overview', '--transport', 'email']
    assert notify.main(args + ['--dry-run']) == 0
    assert not calls and not status.history_path(tmp_path, 'notifications').exists()
    assert notify.main(args) == 0
    path = status.history_path(tmp_path, 'notifications')
    old = path.read_bytes()
    def fail(*args):
        raise RuntimeError('SMTP failure')
    monkeypatch.setattr(notify, 'deliver', fail)
    assert notify.main(args) == 1
    assert path.read_bytes() == old


def test_dashboard_dry_run_preserves_observations(tmp_path, monkeypatch):
    experiment(tmp_path)
    monkeypatch.setattr(status, 'ROOT', tmp_path)
    target = tmp_path / 'view'
    assert status.main(['--output-dir', str(target)]) == 0
    path = status.history_path(tmp_path, 'dashboard')
    old = path.read_bytes()
    assert (target / 'status.md').exists() and (target / 'status.json').exists()
    assert status.main(['--output-dir', str(target), '--dry-run']) == 0
    assert path.read_bytes() == old


def test_broken_runtime_does_not_hide_another_live_run(tmp_path):
    config, output = experiment(tmp_path)
    with RunTracker(output, config['experiment_id'], root=tmp_path):
        directory = tmp_path / '.cache/run_states'
        (directory / 'broken.json').write_text('{broken')
        assert notify.has_active_experiments(tmp_path)
        items = status.collect(tmp_path)
        assert any(p['runtime_status'] == 'running' for p in items)
        assert any(p['state'] == '実行状態の読取失敗' for p in items)


def test_corrupt_observation_cache_disables_comparison_without_losing_status(tmp_path):
    experiment(tmp_path)
    path = status.history_path(tmp_path, 'dashboard')
    path.parent.mkdir(parents=True)
    path.write_text('{broken')
    previous = status.read_history(tmp_path, 'dashboard')
    assert previous == {}
    assert status.collect(tmp_path, previous=previous)[0]['recorded'] == 1
