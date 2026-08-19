"""T4: Bernstein-Vazirani for hidden bitstring s = 011 (n=3)。

Convention: 4 total qubits (q0, q1, q2 = query; q3 = ancilla in |1⟩→|−⟩).
Qiskit measure_all returns bit string "q3 q2 q1 q0".
Hidden s = 011 means s[0]=1, s[1]=1, s[2]=0 (s read as binary "0 1 1" with bit i corresponding to qubit i).
After algorithm, query qubits collapse to s = q2=0, q1=1, q0=1.
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Implement the Bernstein-Vazirani algorithm to recover the hidden bitstring s = "011" (binary).

Bitstring convention: s is read as bits (s[2], s[1], s[0]) where s[i] corresponds to qubit i.
So s[0]=1, s[1]=1, s[2]=0.

Setup:
- 4 total qubits: q0, q1, q2 are the query register, q3 is the ancilla.
- Initialize ancilla q3 to |1⟩ (X gate).
- Apply H to all 4 qubits.
- Oracle for f(x) = s · x = (s[0]·x[0] + s[1]·x[1] + s[2]·x[2]) mod 2:
  - Apply CNOT(q_i, q3) for each i where s[i] = 1.
  - For s = "011": apply CNOT(q0, q3) and CNOT(q1, q3).
- Apply final H on the query qubits q0, q1, q2.

Expected: q0, q1, q2 measure as "011" (= s) with certainty. Ancilla q3 measures 50/50.

Number of qubits: 4
"""

# Bit order: "q3 q2 q1 q0". Query collapses to (q0=1, q1=1, q2=0). Ancilla 0/1.
EXPECTED = {"0011": 0.5, "1011": 0.5}

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(4)
    qc.x(3)
    for i in range(4):
        qc.h(i)
    # Oracle for s = 011: CNOTs from qubits where s[i]=1 to ancilla
    qc.cx(0, 3)
    qc.cx(1, 3)
    # Final H on query qubits
    qc.h(0)
    qc.h(1)
    qc.h(2)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(4)
    # Wrong: missing ancilla init, wrong oracle
    for i in range(4):
        qc.h(i)
    qc.cx(0, 3)  # Only one CNOT
    qc.h(0)
    qc.h(1)
    qc.h(2)
    return qc
'''

TASK = Task(
    id="T4_BV_011",
    name="Bernstein-Vazirani (s=011, n=3)",
    n_qubits=4,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED,
    threshold=0.05,
    expected_gate_count_range=(7, 16),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
