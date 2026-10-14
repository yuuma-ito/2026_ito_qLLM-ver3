import json
import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.circuit.library import StatePreparation
from qiskit.quantum_info import Statevector,DensityMatrix
from harness.evaluator import _run_statevector,evaluate
from harness.readout import ReadoutError
from harness.experiment import load_existing
from scripts.audit_literature_reliability import overlap_fidelity,wilson_interval,summarize_history
from tests.test_repair_costs import records


@pytest.mark.parametrize('operation',['reset','initialize','nested_reset'])
def test_primary_does_not_compare_a_sampled_nonunitary_branch(operation):
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1)
    if operation=='reset':qc.reset(0)
    elif operation=='initialize':qc.initialize([1,0],0)
    else:
        sub=QuantumCircuit(1);sub.reset(0);qc.append(sub.to_instruction(),[0])
    with pytest.raises(ReadoutError):_run_statevector(qc)


def test_reset_ensemble_matches_independent_density_matrix():
    qc=QuantumCircuit(2);qc.h(0);qc.cx(0,1);qc.reset(0)
    assert np.allclose(DensityMatrix.from_instruction(qc).data,np.diag([0.5,0,0.5,0]))


def test_unitary_preparation_and_global_phase_are_supported():
    target=np.array([1,0,0,1])/np.sqrt(2)
    qc=QuantumCircuit(2);qc.append(StatePreparation(target),[0,1]);qc.global_phase=np.pi/3
    assert abs(overlap_fidelity(_run_statevector(qc),target)-1)<1e-12


def test_per_column_phase_passes_basis_but_fails_coherent_input():
    unitary=np.diag([1,-1])
    assert all(overlap_fidelity(unitary@state,state)==1 for state in np.eye(2))
    state=np.array([1,1])/np.sqrt(2)
    assert overlap_fidelity(unitary@state,state)<1e-12


def test_history_distinguishes_first_ever_final_and_regression():
    result=summarize_history([dict(round=i,L3=success) for i,success in enumerate([False,True,False])])
    assert result['first_success_round']==1 and result['ever_success'] and not result['final_success']
    assert result['transitions_to_failure']==1 and not result['final_rescue']
    assert summarize_history([dict(round=0,L3=True),dict(round=1,L3=False)])['final_regression']
    with pytest.raises(ValueError):summarize_history([dict(round=0,L3=False),dict(round=2,L3=True)])


def test_wilson_interval_handles_extremes_and_invalid_denominators():
    low,high=wilson_interval(0,100);assert abs(low)<1e-12 and 0.03<high<0.04
    low,high=wilson_interval(100,100);assert 0.96<low<0.97 and abs(high-1)<1e-12
    with pytest.raises(ValueError):wilson_interval(1,0)


@pytest.mark.parametrize('corruption',['duplicate','truncated'])
def test_resume_rejects_corrupt_file_without_rewriting(tmp_path,corruption):
    row=records()[0];data=json.dumps(row)+'\n'
    data+=json.dumps(row)+'\n' if corruption=='duplicate' else '{"broken":'
    path=tmp_path/'raw.jsonl';path.write_text(data)
    with pytest.raises(ValueError):load_existing(path)
    assert path.read_text()==data


def test_valid_resume_preserves_existing_records(tmp_path):
    rows=records()
    for row in rows:row['condition_id']=row['intervention']
    path=tmp_path/'raw.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    restored,keys=load_existing(path)
    assert len(restored)==len(keys)==len(rows)


def test_pool_signature_separates_evaluator_versions_and_sampling():
    from copy import deepcopy
    from pathlib import Path
    from harness.experiment import build_manifest
    from scripts.pool_experiments import signature
    config=json.loads(Path('configs/shared_five_models_full.json').read_text())
    manifest=build_manifest(config,Path.cwd());old=deepcopy(manifest)
    old.pop('evaluator_version')
    assert signature(config,old)!=signature(config,manifest)
    other=deepcopy(manifest);other['evaluation_sampling']['shots']=1024
    assert signature(config,other)!=signature(config,manifest)
