import copy

import pytest

from harness.evaluator import evaluate
from harness.failure_metadata import normalize_record
from harness.llm_clients import Generation
from harness.runner import run_one
from scripts.analyze_interventions import analyze
from tasks.t1_bell import TASK


@pytest.mark.parametrize('code,stage,cause,exception', [
    ('def build_circuit(:', 'parse', 'syntax', 'SyntaxError'),
    ('import nonexistent_qllm_module', 'import', 'import_error', 'ModuleNotFoundError'),
    ('result = object()\nresult.counts', 'exec', 'interface_mismatch', 'AttributeError'),
    ('result = object()\nresult.missing_method()', 'exec', 'interface_mismatch', 'AttributeError'),
    ('raise RuntimeError("broken")', 'exec', 'unknown_error', 'RuntimeError'),
    ('def build_circuit():\n    return object().counts', 'build', 'build_error', 'AttributeError'),
    ('def build_circuit():\n    raise TypeError("missing argument")', 'build', 'build_error', 'TypeError'),
    ('def build_circuit():\n    import nonexistent_qllm_module', 'build', 'build_error', 'ModuleNotFoundError'),
    ('def build_circuit():\n    return object().counts\nbuild_circuit()', 'build', 'build_error', 'AttributeError'),
    ('def build_circuit():\n    return 42', 'build', 'interface_mismatch', ''),
    ('x = 1', 'exec', 'interface_mismatch', ''),
])
def test_stage_and_cause(code, stage, cause, exception):
    result = evaluate(code, TASK)
    assert (result.failure_stage, result.error_category, result.exception_type) == (stage, cause, exception)
    assert result.error_message
    assert not result.L3


def test_evaluation_exception(monkeypatch):
    def fail(qc):
        raise RuntimeError('simulator failure')
    monkeypatch.setattr('harness.evaluator._run_distribution', fail)
    result = evaluate(TASK.mock_correct_code, TASK)
    assert (result.failure_stage, result.error_category, result.exception_type) == ('evaluate', 'unknown_error', 'RuntimeError')


def test_ghz_legacy_classification_is_nondestructive():
    row = dict(model_spec='qwen3.5:4b', condition_id='self_debugging', task_id='T2_GHZ', seed=6,
               L0=False, L1=False, error_category='unknown_error',
               error_message="AttributeError: 'AerJob' object has no attribute 'counts'", rounds=[])
    row['rounds'] = [dict(row, rounds=[])]
    original = copy.deepcopy(row)
    normalized = normalize_record(row)
    assert row == original
    for attempt in [normalized, *normalized['rounds']]:
        assert (attempt['failure_stage'], attempt['error_category'], attempt['exception_type']) == ('exec', 'interface_mismatch', 'AttributeError')
        assert attempt['original_error_category'] == 'unknown_error'
    counts = analyze([row])['failure_stage_summary']
    assert counts[0]['n'] == 1
    assert counts[0]['failure_stage'] == 'exec'
    assert counts[0]['error_category'] == 'interface_mismatch'


def test_record_and_round_preserve_exception():
    class Client:
        model_id = 'test'
        def generate(self, **kwargs):
            return Generation(raw_text='object().counts', tokens_in=0, tokens_out=0, elapsed_sec=0, model_id='test', error='', timeout_flag=False)
    record = run_one(Client(), TASK, 6).to_dict()
    for attempt in [record, *record['rounds']]:
        assert attempt['failure_stage'] == 'exec'
        assert attempt['error_category'] == 'interface_mismatch'
        assert attempt['exception_type'] == 'AttributeError'
        assert 'counts' in attempt['error_message']


def test_native_build_attribute_error_not_reclassified():
    row = dict(failure_stage='build', error_category='build_error', exception_type='AttributeError', error_message='AttributeError: missing', rounds=[])
    assert normalize_record(row) == row


def test_api_exception_type_is_saved_without_guessing():
    class Client:
        model_id = 'test'
        def generate(self, **kwargs):
            return Generation(raw_text='', error='TimeoutExpired: command timed out', timeout_flag=True, exception_type='TimeoutExpired')
    record = run_one(Client(), TASK, 0).to_dict()
    for attempt in [record, *record['rounds']]:
        assert attempt['failure_stage'] == 'api_call'
        assert attempt['error_category'] == 'api_timeout'
        assert attempt['exception_type'] == 'TimeoutExpired'


def test_legacy_interface_error_does_not_block_as_api_failure():
    from harness.experiment import has_api_failure
    row = dict(L0=False, error_category='unknown_error', error_message='AttributeError: Attribute counts is not defined', rounds=[])
    assert not has_api_failure(row)
    row['rounds'] = [dict(generation_error='Connection refused')]
    assert has_api_failure(row)
