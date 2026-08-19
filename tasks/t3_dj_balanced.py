"""T3b: Deutsch-Jozsa for balanced function f(x1,x2)=x1 XOR x2 (n=2 input qubits)。

Convention: 3 total qubits (q0, q1 = input; q2 = ancilla in |1⟩→|−⟩).
Qiskit measure_all returns bit string "q2 q1 q0".
For balanced oracle CNOT(q0,q2)+CNOT(q1,q2), inputs collapse to |11⟩, ancilla measures 50/50.
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Implement the Deutsch-Jozsa algorithm for the balanced function f(x1, x2) = x1 XOR x2.

Setup:
- 3 total qubits: q0 and q1 are input qubits, q2 is the ancilla.
- Initialize ancilla q2 to |1⟩ (X gate first).
- Apply H to all 3 qubits.
- Oracle for f = x1 XOR x2: CNOT(q0, q2), CNOT(q1, q2).
- Apply final H on input qubits q0 and q1 only.

Expected: input qubits q0, q1 deterministically measure as "11" (balanced detected).
The ancilla measurement is 50/50.

Number of qubits: 3
"""

# Bit order: "q2 q1 q0". Inputs are |11⟩ → q1=1, q0=1. Ancilla 0/1.
EXPECTED = {"011": 0.5, "111": 0.5}

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.x(2)
    qc.h(0)
    qc.h(1)
    qc.h(2)
    qc.cx(0, 2)
    qc.cx(1, 2)
    qc.h(0)
    qc.h(1)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.h(1)
    # Wrong oracle: only CNOT(0,2)
    qc.cx(0, 2)
    qc.h(0)
    qc.h(1)
    return qc
'''

TASK = Task(
    id="T3b_DJ_balanced",
    name="Deutsch-Jozsa (balanced x1 XOR x2)",
    n_qubits=3,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED,
    threshold=0.05,
    expected_gate_count_range=(7, 14),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
