"""T9: パラメータ付き hardware-efficient ansatz（2 量子ビット，2 層，角度固定）。

VQE/QAOA で用いられる hardware-efficient ansatz を，角度を固定した形で構築させる。
回転角の値・適用順・エンタングル層（CX）の位置を正しく束縛できるかを問う。
期待出力は MOCK_CORRECT を実行して Statevector で算出する。
"""
from __future__ import annotations

from . import Task

PROMPT = """\
Task: Build a 2-qubit hardware-efficient ansatz with the following exact structure and fixed
rotation angles (in radians). Apply the operations in this order:

1. RY(pi/4) on qubit 0
2. RY(pi/3) on qubit 1
3. CX with qubit 0 as control and qubit 1 as target
4. RY(pi/6) on qubit 0
5. RY(pi/5) on qubit 1

This is a single-entangling-layer ansatz: a layer of parameterized RY rotations, one CX entangler,
then a second layer of RY rotations. Use the angle values exactly as given. Do NOT add measurements.

Number of qubits: 2
"""

MOCK_CORRECT = '''\
import math
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.ry(math.pi / 4, 0)
    qc.ry(math.pi / 3, 1)
    qc.cx(0, 1)
    qc.ry(math.pi / 6, 0)
    qc.ry(math.pi / 5, 1)
    return qc
'''

MOCK_WRONG = '''\
import math
from qiskit import QuantumCircuit

def build_circuit() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    # Wrong: missing the entangling CX and the second rotation layer
    qc.ry(math.pi / 4, 0)
    qc.ry(math.pi / 3, 1)
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
    id="T9_Ansatz_001",
    name="Parameterized hardware-efficient ansatz (2-qubit, fixed angles)",
    n_qubits=2,
    prompt_text=PROMPT,
    expected_kind="statevector",
    expected_statevector=EXPECTED_STATEVECTOR,
    threshold=0.05,
    expected_gate_count_range=(4, 10),
    mock_correct_code=MOCK_CORRECT,
    mock_wrong_code=MOCK_WRONG,
)
