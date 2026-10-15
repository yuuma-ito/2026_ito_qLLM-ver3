from copy import deepcopy
import json

import pytest

from scripts.analyze_verified_rescues import REPAIRS, P, analyze, build_paths, refresh_report


def cohort():
    rows, paths = [], {}
    for seed, passed in ((0, False), (1, True)):
        for condition in ('baseline', *REPAIRS, P):
            key = f'{seed}:{condition}'
            success = (not passed if condition == P else
                       passed or condition == 'execution_feedback')
            stop = (0 if passed or condition not in REPAIRS else 1 if success else 3)
            row = dict(record_key=key, source_dir='source', model_spec='model', task_id='task',
                       base_seed=str(seed), condition_id=condition, success=str(success), stop_round=str(stop),
                       path_origin='saved_path_reconstruction')
            rows.append(row)
            paths[key] = [dict(code_sha256=f'initial-{seed}' if i == 0 else f'{key}-{i}',
                               new_L0='True', new_L1='True', new_L2=str(passed),
                               new_L3=str(success if i == stop else passed),
                               new_error_category='ok' if (success if i == stop else passed) else 'wrong_output')
                          for i in range(stop + 1)]
    return rows, paths


def test_shared_failure_denominator_and_independent_P_regression():
    rows, paths = cohort()
    ledger, summary, _, overlaps = analyze(rows, paths, {'task': 'easy'})
    overall = {r['condition_id']: r for r in summary if r['scope'] == 'pooled' and r['grouping'] == 'overall'}
    f = overall['execution_feedback']
    assert f['pairs'] == 2 and f['initial_failures'] == 1
    assert f['rescued'] == 1 and f['rescue_rate'] == 1
    assert f['round_1_rescues'] == 1 and f['preserved'] == 1
    assert overall[P]['regressed'] == 1 and overall[P]['rescued'] == 1
    assert overall[P]['comparison_kind'] == 'independent_generation'
    assert overall['self_refine']['rescued'] == 0
    assert len(ledger) == 8
    assert next(r for r in overlaps if r['scope'] == 'pooled' and r['grouping'] == 'overall')['F_only'] == 1


def test_zero_failure_strata_have_no_rescue_rate():
    rows, paths = cohort()
    _, summary, _, _ = analyze(rows, paths, {'task': 'easy'})
    successful = [r for r in summary if r['grouping'] == 'seed' and r['base_seed'] == 1]
    assert successful and all(r['rescue_rate'] == '' for r in successful)


def test_rejects_missing_condition_and_overlapping_source():
    rows, paths = cohort()
    with pytest.raises(ValueError, match='Missing paired'):
        analyze(rows[:-1], paths, {'task': 'easy'})
    with pytest.raises(ValueError, match='Overlapping'):
        analyze(rows + [rows[0] | {'source_dir': 'other'}], paths, {'task': 'easy'})


def test_rejects_initial_code_and_judgment_mismatch():
    rows, paths = cohort()
    for field, value in (('code_sha256', 'different'), ('new_L2', 'True')):
        broken = deepcopy(paths)
        broken['0:self_refine'][0][field] = value
        with pytest.raises(ValueError, match='Shared initial'):
            analyze(rows, broken, {'task': 'easy'})


def branch_fixture():
    row = dict(record_key='key', source_dir='source', model_spec='model', task_id='task',
               base_seed='0', condition_id='execution_feedback', stop_round='3', success='False',
               path_origin='saved_prefix_new_suffix')
    def round_(index, success):
        return {**row, 'round': str(index), 'new_L3': str(success), 'runtime_status': 'completed'}
    # The old suffix passed at round 1; it must be discarded after branching there.
    saved = [round_(0, False), round_(1, True)]
    partial = [{**row, 'branch_input_round': '1', 'new_generations': '3'}]
    suffix = [round_(i, False) for i in (1, 2, 3)]
    return [row], saved, partial, suffix


def test_unreachable_saved_success_is_not_used():
    mixed, saved, partial, suffix = branch_fixture()
    paths = build_paths(mixed, saved, partial, suffix)
    assert len(paths['key']) == 4
    assert all(r['new_L3'] == 'False' for r in paths['key'])


def test_rejects_early_success_continuation_and_missing_suffix():
    mixed, saved, partial, suffix = branch_fixture()
    with pytest.raises(KeyError):
        build_paths(mixed, saved, partial, suffix[:-1])
    suffix[0]['new_L3'] = 'True'
    with pytest.raises(ValueError, match='continues after success'):
        build_paths(mixed, saved, partial, suffix)


def test_report_refresh_preserves_historical_sections_and_snapshot(tmp_path):
    rows, paths = cohort()
    _, summaries, _, overlaps = analyze(rows, paths, {'task': 'easy'})
    summary = dict(captured_at_utc='fixed', overall=[r for r in summaries if r['scope'] == 'pooled'
                   and r['grouping'] == 'overall'], fd_overlap=next(r for r in overlaps
                   if r['scope'] == 'pooled' and r['grouping'] == 'overall'))
    docs = tmp_path / 'docs'
    docs.mkdir()
    report = docs / 'experiment_report_draft.md'
    original = '# 手書きの目的\n\n<!-- auto:status:start -->\n旧実験の表\n<!-- auto:status:end -->\n'
    report.write_text(original)
    snapshot = docs / 'experiment_report_snapshot.json'
    snapshot.write_text(json.dumps({'runs': [{'id': 'original'}], 'manual': '維持'}))
    refresh_report(summary, root=tmp_path)
    first = report.read_text()
    refresh_report(summary, root=tmp_path)
    assert report.read_text() == first
    assert first.startswith('# 手書きの目的\n')
    assert first.endswith(original[original.index('<!-- auto:status:start -->'):])
    assert first.count('<!-- intervention-rescues:20261015:start -->') == 1
    saved = json.loads(snapshot.read_text())
    assert saved['runs'] == [{'id': 'original'}] and saved['manual'] == '維持'
    assert 'primary_intervention_rescues' in saved
