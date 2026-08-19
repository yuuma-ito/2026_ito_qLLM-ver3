"""T2: GHZ state (3-qubit)。"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Construct the GHZ state (|000⟩ + |111⟩) / √2 on 3 qubits.

Expected behavior:
- Apply H to qubit 0, then CNOT(0, 1), then CNOT(1, 2).
- After execution, measuring all qubits should yield "000" with probability 0.5 and "111" with probability 0.5.

Number of qubits: 3
"""

EXPECTED = {"000": 0.5, "111": 0.5}

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    # Missing CNOT(1, 2) — only Bell state on q0,q1
    return qc
'''

TASK = Task(
    id="T2_GHZ",
    name="GHZ state (3-qubit)",
    n_qubits=3,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED,
    threshold=0.05,
    expected_gate_count_range=(3, 6),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
