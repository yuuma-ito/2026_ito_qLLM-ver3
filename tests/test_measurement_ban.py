"""Only the original measurement ban changes; handwritten fixtures, no API."""
from dataclasses import asdict
import pytest
from qiskit import QuantumCircuit
from tasks import all_tasks, get_task
from harness.evaluator import evaluate_circuit as legacy
from harness.measurement_evaluator import (evaluate_circuit, count_measurements,
    apply_measurement_ban, MeasurementInspectionError, EVALUATOR_VERSION)
from harness.refine import diagnose


@pytest.mark.parametrize('task',all_tasks(),ids=lambda t:t.id)
def test_every_authored_correct_task_keeps_exact_v4_result(task):
    ns={};exec(task.mock_correct_code,ns)  # Authored mock, never saved model code.
    qc=ns['build_circuit']()
    old,new=legacy(qc,task),evaluate_circuit(qc,task)
    assert old.L3 and new.L3
    assert asdict(old)==asdict(new)


def test_matching_output_with_measurements_fails_and_old_result_is_immutable():
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1);qc.measure_all()
    task=get_task('T1_Bell');old=legacy(qc,task)
    assert old.L3
    new=apply_measurement_ban(old,count_measurements(qc))
    assert old.L3 and not new.L3 and not new.structure_match
    assert (old.L0,old.L1,old.L2,old.L2_distance)==(new.L0,new.L1,new.L2,new.L2_distance)
    assert new.error_category=='interface_mismatch'
    assert '測定' in diagnose(task,new) and '出力が期待値と一致しません' not in diagnose(task,new)


def test_evaluator_readout_and_unused_classical_bits_are_not_banned():
    qc=QuantumCircuit(2,5);qc.h(0);qc.cx(0,1)
    assert evaluate_circuit(qc,get_task('T1_Bell')).L3
    assert len(qc.data)==2 and count_measurements(qc)==0


def test_nested_and_control_flow_measurements_are_counted():
    inner=QuantumCircuit(2,2);inner.h(0);inner.cx(0,1);inner.measure([0,1],[0,1])
    outer=QuantumCircuit(2,2);outer.append(inner.to_instruction(),[0,1],[0,1])
    assert count_measurements(outer)==2
    qc=QuantumCircuit(1,1)
    with qc.if_test((qc.clbits[0],0)):qc.measure(0,0)
    assert count_measurements(qc)==1


def test_no_stronger_phase_or_whole_unitary_requirements_are_added():
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1);qc.z(0)
    assert legacy(qc,get_task('T1_Bell')).L3
    assert evaluate_circuit(qc,get_task('T1_Bell')).L3
    from qiskit.circuit.library import QFT
    qc=QuantumCircuit(3);qc.x(0);qc.z(1);qc.z(2)
    qc.compose(QFT(3,inverse=True,do_swaps=True),inplace=True)
    assert legacy(qc,get_task('T7_IQFT_001')).L3
    assert evaluate_circuit(qc,get_task('T7_IQFT_001')).L3


def test_inspection_limit_is_not_silent_compliance():
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1)
    with pytest.raises(MeasurementInspectionError):count_measurements(qc,max_nodes=1)


def test_existing_failed_feedback_is_unchanged():
    from harness.interventions import build_intervention_prompt
    qc=QuantumCircuit(2);qc.x(0);qc.measure_all()
    task=get_task('T1_Bell');old=legacy(qc,task)
    assert not old.L3
    new=evaluate_circuit(qc,task)
    assert not new.L3 and not new.structure_match
    for c in ['self_refine','execution_feedback','self_debugging']:
        assert build_intervention_prompt(c,task,'fixture',old)==build_intervention_prompt(c,task,'fixture',new)


def test_new_generation_and_manifest_use_revision_not_frozen_v4():
    from harness import runner,experiment
    from scripts import run_experiment
    assert runner.evaluate.__module__=='harness.measurement_evaluator'
    assert experiment.EVALUATOR_VERSION==run_experiment.EVALUATOR_VERSION==EVALUATOR_VERSION


def test_isolated_revision_agrees_and_records_both_versions():
    from harness.measurement_isolation import isolated_evaluate
    task=get_task('T1_Bell')
    source=task.mock_correct_code.replace('    return qc','    qc.measure_all()\n    return qc')
    result=isolated_evaluate(source,task.id)
    assert result['runtime_status']=='completed',result
    assert result['old_primary']['L3'] and not result['primary']['L3']
    assert result['measurement_count']==2 and result['measurement_violation']
