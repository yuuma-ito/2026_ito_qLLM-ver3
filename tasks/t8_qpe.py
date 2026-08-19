"""T8: Quantum Phase Estimation (QPE)。

3 カウント量子ビット + 1 固有状態量子ビットで，位相ゲート P(theta) の
固有状態 |1> に対する位相 phi = theta/(2*pi) を推定する。
theta = pi/2 を選ぶと phi = 1/4 = 0.010(2) なので，3 ビットで厳密に表現でき，
カウントレジスタの測定結果は決定的になる。

期待分布は MOCK_CORRECT を実行し，Statevector の確率分布として算出する
（measure_all と同じビット順規約に一致させるため）。
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Implement 3-bit Quantum Phase Estimation (QPE) for the single-qubit phase gate P(theta)
with theta = pi/2, acting on its eigenstate |1>.

Setup (4 qubits total):
- Qubits 0, 1, 2: the counting register (3 estimation qubits).
- Qubit 3: the eigenstate register, prepared in |1> (eigenstate of P(theta) with eigenvalue e^{i*theta}).

Algorithm:
1. Apply X to qubit 3 to prepare the eigenstate |1>.
2. Apply H to each of the counting qubits 0, 1, 2.
3. For each counting qubit j (j = 0, 1, 2), apply controlled-P(theta) with qubit j as control and
   qubit 3 as target, repeated 2**j times (equivalently controlled-P(theta * 2**j)).
4. Apply the inverse QFT to the counting register (qubits 0, 1, 2).

Since theta = pi/2 corresponds to phase phi = theta/(2*pi) = 1/4 = 0.010 in binary, the counting
register should deterministically encode the estimate. Do NOT add measurements; the evaluator adds them.

Number of qubits: 4
"""

MOCK_CORRECT = '''\
import math
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(4)
    theta = math.pi / 2
    # eigenstate |1> on qubit 3
    qc.x(3)
    # superposition on counting register
    for j in range(3):
        qc.h(j)
    # controlled phase kickback, qubit j controls P(theta)^(2**j)
    for j in range(3):
        for _ in range(2 ** j):
            qc.cp(theta, j, 3)
    # inverse QFT on the counting register
    iqft = QFT(num_qubits=3, do_swaps=True, inverse=True)
    qc.compose(iqft, qubits=range(3), inplace=True)
    return qc
'''

MOCK_WRONG = '''\
import math
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(4)
    theta = math.pi / 2
    qc.x(3)
    for j in range(3):
        qc.h(j)
    # Wrong: forgets to repeat 2**j times (applies P(theta) once per qubit)
    for j in range(3):
        qc.cp(theta, j, 3)
    # Wrong: uses forward QFT instead of inverse
    qft = QFT(num_qubits=3, do_swaps=True, inverse=False)
    qc.compose(qft, qubits=range(3), inplace=True)
    return qc
'''


def _compute_expected_distribution() -> dict[str, float]:
    from qiskit.quantum_info import Statevector

    ns: dict = {}
    exec(MOCK_CORRECT, ns)
    qc = ns["build_circuit"]()
    probs = Statevector.from_instruction(qc).probabilities_dict()
    # 数値誤差で生じる微小確率を切り捨て。numpy 型が JSON 化時に混入しないよう
    # native float へ明示変換する（評価器の L2 判定が numpy.bool_ になるのを防ぐ）。
    return {k.replace(" ", ""): float(v) for k, v in probs.items() if v > 1e-9}


EXPECTED_DISTRIBUTION = _compute_expected_distribution()

TASK = Task(
    id="T8_QPE_001",
    name="Quantum Phase Estimation (phi=1/4, 3 counting qubits)",
    n_qubits=4,
    prompt_text=PROMPT,
    expected_kind="distribution",
    expected_distribution=EXPECTED_DISTRIBUTION,
    threshold=0.05,
    expected_gate_count_range=(8, 80),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
