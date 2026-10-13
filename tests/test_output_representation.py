import pytest
from qiskit import QuantumCircuit
from scripts.check_output_representation import prepare_readout,project_counts


def test_added_measurement_uses_only_new_bits_without_mutating_original():
    qc=QuantumCircuit(2,3);qc.x(1)
    circuit,mapping=prepare_readout(qc)
    assert qc.num_clbits==3 and len(qc.data)==1
    assert circuit.num_clbits==5 and mapping=={0:3,1:4}
    assert project_counts({'10 000':8},mapping,5)=={'10':1.0}


def test_projection_respects_mapping_and_merges_unused_bits():
    assert project_counts({'01':8},{0:1,1:0},2)=={'10':1.0}
    assert project_counts({'10001':3,'10101':5},{0:1,1:4},5)=={'10':1.0}
    # Wrong quantum output remains wrong; no automatic bit reversal.
    assert project_counts({'01':8},{0:0,1:1},2)=={'01':1.0}


@pytest.mark.parametrize('case',['partial','overwrite','repeated','midcircuit'])
def test_ambiguous_measurements_rejected(case):
    qc=QuantumCircuit(2,2);qc.measure(0,0)
    if case=='overwrite':qc.measure(1,0)
    elif case=='repeated':qc.measure(0,1)
    elif case=='midcircuit':qc.x(1);qc.measure(1,1)
    with pytest.raises(ValueError):prepare_readout(qc)


def test_classical_control_rejected():
    qc=QuantumCircuit(2,2)
    with qc.if_test((qc.clbits[0],True)):qc.x(1)
    with pytest.raises(ValueError):prepare_readout(qc)


@pytest.mark.parametrize('counts',[{'0x2':8},{'1':8}])
def test_invalid_keys_rejected(counts):
    with pytest.raises(ValueError):project_counts(counts,{0:0,1:1},2)
