"""T5: Grover search (n=2, marked = |11⟩, 1 iteration)。

For n=2 with 1 marked state, a single Grover iteration produces the marked state with probability 1.
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Implement Grover's search algorithm on 2 qubits with the marked state |11⟩, using exactly one Grover iteration.

For n=2 and 1 marked state, the Grover iteration produces the marked state with probability 1 (exact).

Algorithm:
1. Initialize 2 qubits in uniform superposition (H on both).
2. Apply oracle that marks |11⟩ with a phase flip: e.g., CZ(0,1).
3. Apply diffusion operator (inversion about the mean): H on all, X on all, CZ(0,1), X on all, H on all.

Expected: measuring should yield "11" with probability 1.

Number of qubits: 2
"""

# Bit order "q1 q0" → |11⟩ = "11"
EXPECTED = {"11": 1.0}

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    # Init superposition
    qc.h(0)
    qc.h(1)
    # Oracle: phase flip on |11>
    qc.cz(0, 1)
    # Diffusion
    qc.h(0)
    qc.h(1)
    qc.x(0)
    qc.x(1)
    qc.cz(0, 1)
    qc.x(0)
    qc.x(1)
    qc.h(0)
    qc.h(1)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.h(1)
    qc.cz(0, 1)
    # Forgot diffusion operator
    return qc
'''

TASK = Task(
    id="T5_Grover_11",
    name="Grover search (n=2, marked=11)",
    n_qubits=2,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED,
    threshold=0.05,
    expected_gate_count_range=(8, 18),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
