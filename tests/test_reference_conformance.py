"""Handwritten/task fixtures only. No saved model outputs or API calls."""
import numpy as np
import pytest
from qiskit import QuantumCircuit
from harness.reference_conformance import check_reference, operator_distance
from tasks import all_tasks


@pytest.mark.parametrize('task', all_tasks(), ids=lambda t:t.id)
def test_all_ten_authored_reference_fixtures(task):
    namespace = {}
    exec(task.mock_correct_code, namespace)  # Repository-authored test fixture.
    result = check_reference(namespace['build_circuit'](), task.id)
    assert result['status'] == 'pass', result


@pytest.mark.parametrize('width,task', [(2,'T1_Bell'), (3,'T2_GHZ')])
def test_opposite_relative_phase_fails_even_with_same_distribution(width,task):
    qc=QuantumCircuit(width)
    qc.h(0)
    for q in range(1,width):qc.cx(0,q)
    qc.z(0)
    assert check_reference(qc,task)['status']=='fail'


def test_direct_answer_with_padding_is_not_grover():
    qc=QuantumCircuit(2)
    qc.x(0);qc.x(1)
    for _ in range(6):qc.id(0)
    assert check_reference(qc,'T5_Grover_11')['status']=='fail'


def test_correct_composite_gate_is_not_rejected_by_gate_count():
    inner=QuantumCircuit(2);inner.h(0);inner.cx(0,1)
    qc=QuantumCircuit(2);qc.append(inner.to_gate(),[0,1])
    assert check_reference(qc,'T1_Bell')['status']=='pass'
    qc.measure_all()
    assert check_reference(qc,'T1_Bell')['reason']=='measurement_forbidden'


def test_nested_measurement_is_also_forbidden():
    inner=QuantumCircuit(2,2);inner.h(0);inner.cx(0,1);inner.measure([0,1],[0,1])
    qc=QuantumCircuit(2,2);qc.append(inner.to_instruction(),[0,1],[0,1])
    assert check_reference(qc,'T1_Bell')['reason']=='measurement_forbidden'


def test_fixed_input_agreement_does_not_hide_wrong_whole_operator():
    from qiskit.circuit.library import QFT
    qc=QuantumCircuit(3);qc.x(0);qc.z(1);qc.z(2)
    qc.compose(QFT(3,inverse=True,do_swaps=True),inplace=True)
    assert check_reference(qc,'T7_IQFT_001')['status']=='fail'


def test_global_phase_and_worst_input_bound():
    assert operator_distance(np.eye(2)*1j,np.eye(2))<1e-12
    altered=np.diag([1,np.exp(.2j)])
    assert operator_distance(altered,np.eye(2))>.05
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1);qc.global_phase=.7
    assert check_reference(qc,'T1_Bell')['status']=='pass'


def test_nonunitary_and_invalid_contract():
    qc=QuantumCircuit(2);qc.reset(0)
    assert check_reference(qc,'T1_Bell')['reason']=='unitary_circuit_required'
    with pytest.raises(ValueError):check_reference(qc,'unknown')
    with pytest.raises(ValueError):check_reference(qc,'T1_Bell',float('nan'))


@pytest.mark.parametrize('width,task',[(2,'T1_Bell'),(3,'T2_GHZ'),(2,'T5_Grover_11')])
def test_operator_matrix_must_be_unitary_even_when_prepared_state_matches(width,task):
    from qiskit.circuit import Gate
    class Projection(Gate):
        def __init__(self):super().__init__('projection',1,[])
        def to_matrix(self):return np.diag([1.,0.])
    qc=QuantumCircuit(width);qc.append(Projection(),[0]);qc.h(0)
    for q in range(1,width):qc.cx(0,q)
    assert check_reference(qc,task)['reason']=='unitary_circuit_required'


def test_invalid_composite_definition_returns_a_failed_contract():
    from qiskit.circuit.library import UnitaryGate
    qc=QuantumCircuit(2)
    qc.append(UnitaryGate(np.diag([1.,0.]),check_input=False),[0])
    assert check_reference(qc,'T1_Bell')['reason']=='unitary_circuit_required'
