"""T6: Quantum Fourier Transform (n=3, input |001⟩)。

期待出力は qiskit の Statevector で実行時に計算（QFT の swap 規約への依存を吸収するため）。
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Apply the 3-qubit Quantum Fourier Transform (QFT) to the input state |001⟩.

In Qiskit's little-endian convention, |001⟩ means qubit 0 = |1⟩ and qubits 1, 2 = |0⟩.

Algorithm:
1. Initialize the input state by applying X to qubit 0.
2. Apply QFT to all 3 qubits. You may use qiskit.circuit.library.QFT or implement it manually.
   Use the standard convention with swap gates at the end (do_swaps=True).

The expected output statevector is determined by the canonical QFT mapping:
QFT|j⟩ = (1/√N) Σ_k exp(2πi · j · k / N) |k⟩  with N = 2^3 = 8

Number of qubits: 3
"""

MOCK_CORRECT = '''\
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.x(0)
    qft = QFT(num_qubits=3, do_swaps=True)
    qc.compose(qft, qubits=range(3), inplace=True)
    return qc
'''

MOCK_WRONG = '''\
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.x(0)
    # Wrong: just apply Hadamards instead of QFT
    qc.h(0)
    qc.h(1)
    qc.h(2)
    return qc
'''


def _compute_expected_statevector() -> tuple[complex, ...]:
    """mock_correct_code を実行して状態ベクトルを得る（モジュール読み込み時に1回）。"""
    from qiskit.quantum_info import Statevector

    ns: dict = {}
    exec(MOCK_CORRECT, ns)
    qc = ns["build_circuit"]()
    sv = Statevector.from_instruction(qc).data
    return tuple(complex(x) for x in sv)


EXPECTED_STATEVECTOR = _compute_expected_statevector()

TASK = Task(
    id="T6_QFT_001",
    name="QFT (n=3, input |001⟩)",
    n_qubits=3,
    prompt_text=PROMPT,
    expected_kind="statevector",
    expected_statevector=EXPECTED_STATEVECTOR,
    threshold=0.05,
    expected_gate_count_range=(1, 50),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
