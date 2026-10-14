import numpy as np
from scripts.audit_evaluation_methods import aligned_distance,analytic_checks,sampling_checks


def test_independent_distance_ignores_global_but_preserves_relative_phase():
    state=np.array([1,1],complex)/np.sqrt(2)
    assert aligned_distance(1j*state,state)<1e-7
    assert aligned_distance(np.array([1,-1])/np.sqrt(2),state)>1


def test_analytic_references_match_three_task_oracles():
    assert len(analytic_checks())==3


def test_sampling_boundary_has_both_outcomes():
    rows=sampling_checks()
    boundary=next(r for r in rows if r['probability']==0.55)
    assert 0.4<boundary['accept_rate']<0.6
    assert rows[0]['accept_rate']==1
    assert rows[-1]['accept_rate']<0.05


def test_production_phase_alignment_matches_independent_formula():
    from harness.evaluator import _statevector_distance
    state=np.array([1,1j],complex)/np.sqrt(2)
    for phase in [0,np.pi/4,np.pi/2,np.pi,-np.pi/3]:
        actual=np.exp(1j*phase)*state
        assert _statevector_distance(actual,state)<1e-12
    different=np.array([1,-1j],complex)/np.sqrt(2)
    assert abs(_statevector_distance(different,state)-aligned_distance(different,state))<1e-12


def test_distribution_simulation_is_reproducible():
    from harness.evaluator import _run_distribution
    from qiskit import QuantumCircuit
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1)
    assert _run_distribution(qc)==_run_distribution(qc)


def test_unsupported_parameter_and_measurement_are_classified():
    from harness.evaluator import evaluate
    from tasks import get_task
    from scripts.audit_evaluation_methods import modified_code
    bell=get_task('T1_Bell')
    code=modified_code(bell.mock_correct_code,"from qiskit.circuit import Parameter; qc.ry(Parameter('theta'),0)")
    result=evaluate(code,bell)
    assert result.error_category=='interface_mismatch' and result.failure_stage=='build'
    qft=get_task('T6_QFT_001')
    result=evaluate(modified_code(qft.mock_correct_code,'qc.measure_all()'),qft)
    assert result.error_category=='interface_mismatch' and result.failure_stage=='evaluate'


def test_barriers_do_not_violate_gate_count_bounds():
    from harness.evaluator import evaluate
    from tasks import get_task
    from scripts.audit_evaluation_methods import modified_code
    task=get_task('T1_Bell')
    result=evaluate(modified_code(task.mock_correct_code,'[qc.barrier() for _ in range(6)]'),task)
    assert result.L3
