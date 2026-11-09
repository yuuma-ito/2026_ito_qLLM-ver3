"""Check analysis distinctions that can otherwise misstate why R failed."""
import hashlib
import pytest

from scripts.analyze_r_failure_paths import failure_pattern, summarize, request_diagnostic


def path(*codes, success=False):
    return [{'code': code, 'hash': hashlib.sha256(code.encode()).hexdigest(),
             'success': success and i == len(codes)-1} for i, code in enumerate(codes)]


@pytest.mark.parametrize('codes,expected', [
    (('x = 1', 'x = 1'), 'unchanged_text'),
    (('x = 1', '# changed comment\nx=1'), 'unchanged_ast_only'),
    (('x = 1', 'x = 2', 'x = 1'), 'changed_ast_still_failed'),
    (('x = ', 'x = 1'), 'ast_incomplete'),
    (('x = ', 'x = '), 'unchanged_text'),
])
def test_repetition_and_failed_changes_are_distinguished(codes, expected):
    assert failure_pattern(path(*codes)) == expected


def test_success_is_not_counted_as_a_failure_pattern():
    assert failure_pattern(path('x = 1', 'x = 2', success=True)) == 'rescued'


def test_absent_historical_prompt_is_not_reconstructed():
    assert request_diagnostic({'origin': 'saved_prefix'}, {}) is None


def test_summary_reconciles_partitions_and_keeps_counterexamples():
    rows = [dict(model_spec='a', r_pattern='rescued', R_success=True, F_success=False,
                 D_success=False, B4_success=False),
            dict(model_spec='b', r_pattern='unchanged_text', R_success=False, F_success=True,
                 D_success=True, B4_success=True)]
    total = summarize(rows, [])[0]
    parts = summarize(rows, ['model_spec'])
    assert total['R_successes'] == total['F_successes'] == 1
    for key in ('initial_failures', 'R_successes', 'F_successes', 'rescued', 'unchanged_text'):
        assert total[key] == sum(row[key] for row in parts)
