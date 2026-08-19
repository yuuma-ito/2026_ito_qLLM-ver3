"""T3a: Deutsch-Jozsa for constant function f(x1,x2)=0 (n=2 input qubits)。

Convention: 3 total qubits (q0, q1 = input; q2 = ancilla in |1⟩→|−⟩).
Qiskit measure_all returns bit string "q2 q1 q0".
For constant oracle (identity), inputs return to |00⟩, ancilla measures 50/50.
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Implement the Deutsch-Jozsa algorithm for the constant function f(x1, x2) = 0 (the all-zero function).

Setup:
- 3 total qubits: q0 and q1 are input qubits, q2 is the ancilla.
- The ancilla q2 must be initialized to |1⟩ (apply X gate before the H gates).
- After Hadamards, apply the oracle for f (identity for constant 0; do nothing).
- Apply Hadamards on the input qubits q0 and q1 only (NOT the ancilla).

Expected: input qubits q0, q1 deterministically measure as "00" (constant detected).
The ancilla measurement is 50/50 between 0 and 1.

Number of qubits: 3
"""

# Bit order: "q2 q1 q0". Inputs are |00⟩ → q1=0, q0=0. Ancilla is |−⟩ → 50/50.
EXPECTED = {"000": 0.5, "100": 0.5}

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    # Initialize ancilla q2 to |1>, then H all
    qc.x(2)
    qc.h(0)
    qc.h(1)
    qc.h(2)
    # Oracle: constant 0 = identity (no gate)
    # Final H on input qubits only
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
    qc.h(2)
    # Forgot to initialize ancilla to |1>, and forgot final H
    return qc
'''

TASK = Task(
    id="T3a_DJ_constant",
    name="Deutsch-Jozsa (constant, n=2)",
    n_qubits=3,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED,
    threshold=0.05,
    expected_gate_count_range=(5, 10),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
