"""Diagnostic regression and reachability tests. No model/API requests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from harness.diagnostic_policy import diagnose,diagnose_legacy_v1,DIAGNOSTIC_VERSION
from harness.diagnostic_prompts import build_intervention_prompt as corrected
from harness.interventions import build_intervention_prompt as frozen
from harness.evaluator import EvalResult
from harness.measurement_evaluator import evaluate,EVALUATOR_VERSION
from harness.runner import InitialAttempt,run_intervention
from harness.llm_clients import Generation,MockClient
from scripts.run_experiment import _check_evaluator_resume
from scripts.audit_diagnostic_policy_impact import classify_path
from tasks import get_task

TASK=get_task('T1_Bell')

def structure_failure():
    return EvalResult(L0=True,L1=True,L2=True,L3=False,structure_match=False,L2_distance=0.0,
                      error_category='interface_mismatch',error_message='circuit structure is outside the accepted bounds')

def test_structure_only_failure_never_claims_output_mismatch_and_does_not_rescore():
    ev=structure_failure();before=deepcopy(ev)
    message=diagnose(TASK,ev)
    assert '出力は一致' in message and '構造要件' in message
    assert '出力が期待値と一致しません' not in message and '0.0000 >' not in message
    assert ev==before and ev.L2 and not ev.L3
    assert '0.0000 >' in diagnose_legacy_v1(TASK,ev)


def test_canonical_qubit_category_has_specific_diagnostic():
    ev=EvalResult(L0=True,L1=True,L2=False,error_category='qubit_count_mismatch',
                  error_message='expected 2 qubits, got 3',L2_distance=1.0)
    assert 'expected 2 qubits, got 3' in diagnose(TASK,ev)
    assert 'qubit 数が要求と異なります' in diagnose(TASK,ev)
    assert '出力が期待値と一致しません' not in diagnose(TASK,ev)
    ev.error_category='wrong_n_qubits'
    assert diagnose(TASK,ev)==diagnose_legacy_v1(TASK,ev)


@pytest.mark.parametrize('ev',[
    EvalResult(error_category='syntax',error_message='SyntaxError: authored'),
    EvalResult(error_category='import_error',error_message='ImportError: authored'),
    EvalResult(L0=True,error_category='build_error',error_message='TypeError: authored'),
    EvalResult(L0=True,L1=False,error_category='interface_mismatch',error_message='unsupported operation'),
    EvalResult(L0=True,L1=True,L2=False,structure_match=True,L2_distance=.5,error_category='wrong_output',actual_distribution={'01':1.0}),
    EvalResult(L0=True,L1=True,L2=True,L3=False,error_category='interface_mismatch',error_message='in-circuit measurements are forbidden by the common system instruction (count=2)'),
])
@pytest.mark.parametrize('condition',['self_refine','execution_feedback','self_debugging'])
def test_unaffected_prompt_bytes_remain_identical(ev,condition):
    code='# authored fixture\ndef build_circuit(): pass'
    assert corrected(condition,TASK,code,ev)==frozen(condition,TASK,code,ev)


@pytest.mark.parametrize('condition',['execution_feedback','self_debugging'])
def test_active_runner_uses_correct_diagnostic_and_records_input_identity(condition):
    # Authored circuit, deliberately too many gates while preserving Bell output.
    code='from qiskit import QuantumCircuit\ndef build_circuit():\n    q=QuantumCircuit(2)\n    q.h(0)\n    q.cx(0,1)\n    for _ in range(30): q.id(0)\n    return q\n'
    ev=evaluate(code,TASK)
    assert ev.L2 and not ev.structure_match and not ev.L3
    class CapturingClient(MockClient):
        def generate(self,**kwargs):
            self.prompt=kwargs['user_prompt']
            return super().generate(**kwargs)
    client=CapturingClient('mock-correct')
    initial=InitialAttempt(Generation(raw_text=code),code,ev,0)
    result=run_intervention(client,TASK,0,condition,initial=initial)
    assert '出力は一致' in client.prompt and '出力が期待値と一致しません' not in client.prompt
    assert result.final_success and result.first_success_round==1
    assert result.rounds[1]['diagnostic_policy_version']==DIAGNOSTIC_VERSION
    assert result.rounds[1]['input_prompt_sha256']==hashlib.sha256(client.prompt.encode()).hexdigest()


def test_resume_cannot_mix_diagnostic_versions_but_completed_run_needs_no_generation():
    v={'experiment_id':'e','pair_keys':{('model','task',0)},'conditions':[SimpleNamespace(id=c,intervention=c) for c in ['baseline','execution_feedback']]}
    old={'evaluator_version':EVALUATOR_VERSION};existing={('e','baseline','model','task',0)}
    with pytest.raises(ValueError,match='different diagnostic'):_check_evaluator_resume(old,v,existing)
    _check_evaluator_resume({**old,'diagnostic_policy_version':DIAGNOSTIC_VERSION},v,existing)
    _check_evaluator_resume(old,v,existing|{('e','execution_feedback','model','task',0)})
    _check_evaluator_resume(old,v,set())


def test_terminal_diagnostic_changes_do_not_create_generation_and_first_branch_controls_budget():
    rr=[{'round':i,'prompt_changed':i in [1,2,3],'has_next':i<3} for i in range(4)]
    result=classify_path(rr)
    assert result=={'branch_generation_round':2,'requires_generation':True,'minimum_new_requests':1,'maximum_new_requests':2,'saved_suffix_rounds_not_reusable':2}
    for r in rr:r['prompt_changed']=r['round']==3
    assert classify_path(rr)['requires_generation'] is False


def test_manifest_identifies_diagnostic_source_and_empty_run_adopts_current_policy(tmp_path,monkeypatch):
    from harness.experiment import build_manifest
    from scripts import run_experiment
    root=Path(__file__).resolve().parents[1]
    cfg={'experiment_id':'diagnostic_fixture','models':['mock-correct'],'tasks':['T1_Bell'],
         'seeds':[0],'conditions':['baseline','execution_feedback'],'max_rounds':1,
         'output_dir':str(tmp_path/'output')}
    manifest=build_manifest(cfg,root)
    assert manifest['diagnostic_policy_version']==DIAGNOSTIC_VERSION
    for name in ['diagnostic_policy','diagnostic_prompts']:
        assert manifest['prompt_fingerprints'][name+'_py_sha256']==hashlib.sha256((root/'harness'/f'{name}.py').read_bytes()).hexdigest()
    manifest.pop('diagnostic_policy_version')
    output=tmp_path/'output';output.mkdir()
    (output/'manifest.json').write_text(json.dumps(manifest))
    config_path=tmp_path/'config.json';config_path.write_text(json.dumps(cfg))
    monkeypatch.setattr(run_experiment,'ROOT',tmp_path)
    monkeypatch.setenv('QLLM_EVENT_TRANSPORT','none')
    monkeypatch.delenv('QLLM_RUN_TOKEN',raising=False)
    assert run_experiment.main(['--config',str(config_path)])==0
    assert json.loads((output/'manifest.json').read_text())['diagnostic_policy_version']==DIAGNOSTIC_VERSION
