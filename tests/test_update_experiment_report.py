"""Report refreshes use local records and preserve authored prose."""
import json
from pathlib import Path

import pytest

from scripts import update_experiment_report as report


@pytest.fixture
def draft(tmp_path):
    output = tmp_path / 'results/full'
    output.mkdir(parents=True)
    config = {'experiment_id': 'shared_three_models_full_test', 'models': ['mock'],
              'tasks': ['T1_Bell'], 'seeds': [0, 1], 'conditions': ['baseline'],
              'output_dir': 'results/full'}
    (output / 'experiment_config.json').write_text(json.dumps(config))
    (output / 'raw.jsonl').write_text('')
    (tmp_path / 'docs').mkdir()
    snapshot = {'captured_at': 'before', 'runs': [{'experiment_id': config['experiment_id'],
                                                'source_dir': 'results/full', 'recorded': 0}]}
    (tmp_path / report.SNAPSHOT).write_text(json.dumps(snapshot))
    text = '\n\n'.join(f'<!-- auto:{name}:start -->\nold\n<!-- auto:{name}:end -->'
                       for name in ('status', 'capture', 'full-results'))
    (tmp_path / report.REPORT).write_text(text + '\n\n## 考察\n手書きの考察を保持する。\n')
    return tmp_path, output, config


def row(config, seed, **extra):
    return {'experiment_id': config['experiment_id'], 'model_spec': 'mock',
            'task_id': 'T1_Bell', 'condition_id': 'baseline', 'base_seed': seed,
            'L2': True, 'L3': True, 'error_category': 'ok', 'rounds': [], **extra}


def write_rows(output, rows):
    (output / 'raw.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))


def test_refresh_partial_records_and_complete_preserves_prose(draft):
    root, output, config = draft
    write_rows(output, [row(config, 0)])
    with (output / 'raw.jsonl').open('a') as handle:
        handle.write('{')
    first = report.update_report(root)
    assert first['runs'][0]['recorded'] == 1
    assert first['runs'][0]['pending_write']
    text = (root / report.REPORT).read_text()
    assert '50.0%' in text and '書き込み途中' in text and '未検証' in text
    assert '手書きの考察を保持する。' in text
    write_rows(output, [row(config, 0), row(config, 1)])
    (output / 'automation_report.json').write_text('{"passed": true}')
    (output / 'sanity_report.json').write_text(json.dumps({'passed': True, 'experiment_id': config['experiment_id']}))
    current = report.update_report(root)
    assert current['runs'][0]['automation_verified']
    text = (root / report.REPORT).read_text()
    assert '検証済み結果' in text and '100.0%' in text
    assert '手書きの考察を保持する。' in text
    assert json.loads((root / report.SNAPSHOT).read_text()) == current


def test_api_failure_prevents_verified_result(draft):
    root, output, config = draft
    write_rows(output, [row(config, 0, rounds=[{'generation_error': 'private details'}]), row(config, 1)])
    (output / 'automation_report.json').write_text('{"passed": true}')
    (output / 'sanity_report.json').write_text(json.dumps({'passed': True, 'experiment_id': config['experiment_id']}))
    result = report.update_report(root)
    assert not result['runs'][0]['automation_verified']
    assert result['runs'][0]['api_failure_records'] == 1
    assert 'private details' not in (root / report.SNAPSHOT).read_text()
    assert 'private details' not in (root / report.REPORT).read_text()


def test_explicit_primary_full_run_replaces_old_run_in_result_table(draft):
    root, output, config = draft
    write_rows(output, [row(config, 0)])
    report.update_report(root)
    new_output = root / 'results/new_full'
    new_output.mkdir()
    new = dict(config, experiment_id='shared_three_models_full_new', output_dir='results/new_full')
    (new_output / 'experiment_config.json').write_text(json.dumps(new))
    (new_output / 'raw.jsonl').write_text('')
    snapshot = json.loads((root / report.SNAPSHOT).read_text())
    snapshot['primary_full_experiment_id'] = new['experiment_id']
    snapshot['runs'].append({'experiment_id': new['experiment_id'], 'source_dir': new['output_dir'], 'recorded': 0})
    (root / report.SNAPSHOT).write_text(json.dumps(snapshot))
    result = report.update_report(root)
    assert result['runs'][0]['recorded'] == 1
    assert result['runs'][1]['recorded'] == 0
    assert '0件（0.0%）' in (root / report.REPORT).read_text()


@pytest.mark.parametrize('tamper', [None, 'prose', 'snapshot', 'auto_block'])
def test_publication_allows_only_recomputed_report_changes(draft, monkeypatch, tamper):
    from scripts import automate_experiment as automation
    root, output, config = draft
    report.update_report(root)
    head = {str(path): (root / path).read_text() for path in (report.REPORT, report.SNAPSHOT)}
    monkeypatch.setattr(automation, 'ROOT', root)
    monkeypatch.setattr(automation, 'git', lambda command, revision: head[revision.removeprefix('HEAD:')])
    write_rows(output, [row(config, 0)])
    report.update_report(root)
    if tamper in {'prose', 'auto_block'}:
        path = root / report.REPORT
        text = path.read_text()
        path.write_text(text + 'unrelated edit' if tamper == 'prose' else text.replace('50.0%', 'secret'))
    elif tamper == 'snapshot':
        path = root / report.SNAPSHOT
        data = json.loads(path.read_text())
        data['runs'][0]['L2_success'] = 'secret'
        path.write_text(json.dumps(data))
    if tamper:
        with pytest.raises(RuntimeError, match='not generated'):
            automation.report_artifacts()
    else:
        assert automation.report_artifacts() == [str(report.REPORT), str(report.SNAPSHOT)]


@pytest.mark.parametrize('problem', ['duplicate', 'unexpected', 'corrupt', 'markers', 'decreased'])
def test_invalid_input_preserves_both_files(draft, problem):
    root, output, config = draft
    write_rows(output, [row(config, 0)])
    report.update_report(root)
    if problem == 'duplicate':
        write_rows(output, [row(config, 0), row(config, 0)])
    elif problem == 'unexpected':
        write_rows(output, [row(config, 9)])
    elif problem == 'corrupt':
        (output / 'raw.jsonl').write_text('invalid json\n')
    elif problem == 'decreased':
        (output / 'raw.jsonl').write_text('')
    else:
        path = root / report.REPORT
        path.write_text(path.read_text().replace('<!-- auto:status:end -->', ''))
    before = {p: (root / p).read_bytes() for p in (report.REPORT, report.SNAPSHOT)}
    with pytest.raises(ValueError):
        report.update_report(root)
    assert all((root / p).read_bytes() == value for p, value in before.items())
