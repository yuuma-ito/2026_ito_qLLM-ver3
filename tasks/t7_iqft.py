"""T7: Inverse Quantum Fourier Transform (逆 QFT, n=3, input |001⟩)。

QFT(順変換) と方向・swap 規約を取り違えやすく，難度の高いタスク。
期待出力は MOCK_CORRECT を実行して Statevector で算出する。
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Apply the INVERSE 3-qubit Quantum Fourier Transform (inverse QFT, IQFT) to the input state |001⟩.

In Qiskit's little-endian convention, |001⟩ means qubit 0 = |1⟩ and qubits 1, 2 = |0⟩.

Algorithm:
1. Initialize the input state by applying X to qubit 0.
2. Apply the INVERSE QFT (not the forward QFT) to all 3 qubits.
   You may use qiskit.circuit.library.QFT with inverse=True, or implement it manually.
   Use the standard convention with swap gates (do_swaps=True).

Note: the inverse QFT is the conjugate transpose of the forward QFT; getting the direction
(sign of the phase rotations) and the swap placement right is essential.

Number of qubits: 3
"""

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.x(0)
    iqft = QFT(num_qubits=3, do_swaps=True, inverse=True)
    qc.compose(iqft, qubits=range(3), inplace=True)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.x(0)
    # Wrong: applies the FORWARD QFT instead of the inverse
    qft = QFT(num_qubits=3, do_swaps=True, inverse=False)
    qc.compose(qft, qubits=range(3), inplace=True)
    return qc
'''


def _compute_expected_statevector() -> tuple[complex, ...]:
    from qiskit.quantum_info import Statevector

    ns: dict = {}
    exec(MOCK_CORRECT, ns)
    qc = ns["build_circuit"]()
    sv = Statevector.from_instruction(qc).data
    return tuple(complex(x) for x in sv)


EXPECTED_STATEVECTOR = _compute_expected_statevector()

TASK = Task(
    id="T7_IQFT_001",
    name="Inverse QFT (n=3, input |001⟩)",
    n_qubits=3,
    prompt_text=PROMPT,
    expected_kind="statevector",
    expected_statevector=EXPECTED_STATEVECTOR,
    threshold=0.05,
    expected_gate_count_range=(1, 60),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
