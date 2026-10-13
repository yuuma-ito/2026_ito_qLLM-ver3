from dataclasses import replace
from types import SimpleNamespace
import pytest
from harness.evaluator import evaluate,EVALUATOR_VERSION
from harness.readout import prepare_readout,project_counts,ReadoutError
from tasks import get_task,Task
from scripts.run_experiment import _check_evaluator_resume


@pytest.mark.parametrize('wrong',[False,True])
def test_qpe_unused_register_does_not_change_correctness(wrong):
    task=get_task('T8_QPE_001')
    code=(task.mock_wrong_code if wrong else task.mock_correct_code).replace('QuantumCircuit(4)','QuantumCircuit(4, 3)')
    result=evaluate(code,task)
    assert result.L0 and result.L1
    assert result.L2 is (not wrong) and result.L3 is (not wrong)
    assert all(len(k)==4 for k in result.actual_distribution)
    if not wrong:assert result.actual_distribution=={'1010':1.0}


TASK=Task(id='readout',name='readout',n_qubits=2,prompt_text='',expected_kind='distribution',expected_distribution={'10':1.0})
CODE='''from qiskit import QuantumCircuit
def build_circuit():
    qc=QuantumCircuit(2,5)
    qc.x(1)
    qc.measure(0,1)
    qc.measure(1,4)
    return qc
'''


def test_explicit_readout_mapping_and_structural_constraints():
    result=evaluate(CODE,TASK)
    assert result.L3 and result.actual_distribution=={'10':1.0}
    result=evaluate(CODE,replace(TASK,expected_classical_bits=2))
    assert result.L2 and not result.L3 and not result.structure_match
    result=evaluate(CODE.replace('qc.x(1)','qc.x(0)'),TASK)
    assert not result.L2 and result.error_category=='bit_order_error'


def test_partial_readout_is_model_interface_failure():
    result=evaluate(CODE.replace('    qc.measure(1,4)\n',''),TASK)
    assert result.L0 and not result.L1 and not result.L3
    assert result.failure_stage=='evaluate' and result.error_category=='interface_mismatch'
    assert result.exception_type=='ReadoutError'


def test_production_and_audit_projection_agree():
    from scripts.check_output_representation import fixtures,prepare_readout as audit_prepare,project_counts as audit_project
    for label,qc,_,expected in fixtures():
        if expected is None:
            with pytest.raises(ReadoutError):prepare_readout(qc)
        else:
            prepared,mapping=prepare_readout(qc);other,other_mapping=audit_prepare(qc)
            assert prepared==other and mapping==other_mapping
    counts={'10001':3,'10101':5};mapping={0:1,1:4}
    assert project_counts(counts,mapping,5)==audit_project(counts,mapping,5)


def test_resume_does_not_mix_evaluator_versions():
    v=dict(experiment_id='test',pair_keys={('model','task',0)},conditions=[SimpleNamespace(id='baseline'),SimpleNamespace(id='self_refine')])
    initial={('test','baseline','model','task',0)}
    with pytest.raises(ValueError,match='different evaluator'):_check_evaluator_resume({},v,initial)
    _check_evaluator_resume({'evaluator_version':EVALUATOR_VERSION},v,initial)
    _check_evaluator_resume({},v,set())
    _check_evaluator_resume({},v,initial|{('test','self_refine','model','task',0)})
