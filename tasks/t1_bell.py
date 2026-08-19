"""T1: Bell state (2-qubit)。"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Construct the Bell state (|00⟩ + |11⟩) / √2 on 2 qubits.

Expected behavior:
- Apply H to qubit 0, then CNOT with qubit 0 as control and qubit 1 as target.
- After execution, measuring all qubits should yield "00" with probability 0.5 and "11" with probability 0.5.

Number of qubits: 2
"""

# Bit string convention (Qiskit measure_all): "q1 q0"
EXPECTED = {"00": 0.5, "11": 0.5}

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    # Forgot the CNOT — wrong output
    return qc
'''

TASK = Task(
    id="T1_Bell",
    name="Bell state (2-qubit)",
    n_qubits=2,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED,
    threshold=0.05,
    expected_gate_count_range=(2, 5),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
