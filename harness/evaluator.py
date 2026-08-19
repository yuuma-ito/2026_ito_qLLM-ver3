"""コード文字列を L0/L1/L2/L3 で評価する。"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from tasks import Task


@dataclass
class EvalResult:
    L0: bool = False
    L1: bool = False
    L2: bool = False
    L3: bool = False
    L2_distance: float = float("nan")
    gate_count: int = 0
    n_qubits_actual: int = 0
    error_category: str = ""  # "syntax" | "import" | "no_function" | "wrong_signature" | "runtime" | "wrong_n_qubits" | "ok"
    error_message: str = ""
    # distribution タスクで実測した測定分布（Self-Refine のフィードバック用）。
    # statevector タスクや実行前に失敗した場合は None。
    actual_distribution: Optional[dict[str, float]] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _exec_code(code: str) -> tuple[bool, dict, str, str]:
    """L0: コードを fresh namespace で exec する。

    Returns: (ok, namespace, error_category, error_message)
    """
    ns: dict = {}
    try:
        exec(code, ns)
    except SyntaxError as e:
        return False, ns, "syntax", str(e)
    except ImportError as e:
        return False, ns, "import", str(e)
    except Exception as e:
        return False, ns, "exec_error", f"{type(e).__name__}: {e}"
    if "build_circuit" not in ns:
        return False, ns, "no_function", "function `build_circuit` is not defined"
    if not callable(ns["build_circuit"]):
        return False, ns, "wrong_signature", "`build_circuit` is not callable"
    return True, ns, "ok", ""


def _try_build(ns: dict) -> tuple[Optional[Any], str, str]:
    """build_circuit() を呼び出す。"""
    try:
        qc = ns["build_circuit"]()
    except Exception as e:
        return None, "build_error", f"{type(e).__name__}: {e}"
    return qc, "ok", ""


def _run_distribution(qc, shots: int = 8192) -> dict[str, float]:
    """測定確率分布を返す。"""
    from qiskit import transpile
    from qiskit_aer import AerSimulator

    qc_meas = qc.copy()
    qc_meas.measure_all()
    sim = AerSimulator()
    tqc = transpile(qc_meas, sim)
    job = sim.run(tqc, shots=shots)
    counts = job.result().get_counts()
    total = sum(counts.values())
    # Qiskit の bit string にスペースが入る場合があるので除去
    return {k.replace(" ", ""): v / total for k, v in counts.items()}


def _run_statevector(qc) -> np.ndarray:
    """状態ベクトル（complex 配列）を返す。"""
    from qiskit.quantum_info import Statevector

    return Statevector.from_instruction(qc).data


def _tvd(p: dict[str, float], q: dict[str, float]) -> float:
    """Total Variation Distance。キー集合は和集合で 0 補完。"""
    keys = set(p.keys()) | set(q.keys())
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def _statevector_distance(actual: np.ndarray, expected: np.ndarray) -> float:
    """状態ベクトルの L2 距離（global phase は許容）。

    min over global phase φ of ‖e^{iφ} actual − expected‖_2
    最適 φ では <actual|expected> の偏角の符号反転で最小化される。
    """
    # global phase 整合
    inner = np.vdot(actual, expected)
    if abs(inner) < 1e-12:
        return float(np.linalg.norm(actual - expected))
    phase = np.angle(inner)
    aligned = np.exp(-1j * phase) * actual
    return float(np.linalg.norm(aligned - expected))


def evaluate(code: str, task: Task) -> EvalResult:
    """コードを task に対して評価する。"""
    res = EvalResult()

    # L0: exec
    ok, ns, cat, msg = _exec_code(code)
    if not ok:
        res.error_category = cat
        res.error_message = msg
        return res
    res.L0 = True

    # build_circuit() 呼び出し
    qc, cat, msg = _try_build(ns)
    if qc is None:
        res.error_category = cat
        res.error_message = msg
        return res

    # qubit 数チェック
    res.n_qubits_actual = qc.num_qubits
    if qc.num_qubits != task.n_qubits:
        res.error_category = "wrong_n_qubits"
        res.error_message = f"expected {task.n_qubits} qubits, got {qc.num_qubits}"
        # L1 は実行可能性で判定するので続行できれば続行
    else:
        res.L3 = True  # 一旦 qubit 数 OK で True、ゲート数で再判定

    # ゲート数 (任意の depth でカウント)
    try:
        res.gate_count = sum(1 for _ in qc.data)
    except Exception:
        res.gate_count = 0

    # L3: ゲート数範囲チェック（qubit 数が合っている前提）
    if res.L3 and task.expected_gate_count_range is not None:
        gmin, gmax = task.expected_gate_count_range
        if not (gmin <= res.gate_count <= gmax):
            res.L3 = False

    # L1 + L2: 実行
    try:
        if task.expected_kind == "distribution":
            actual = _run_distribution(qc)
            res.L1 = True
            res.actual_distribution = actual
            res.L2_distance = _tvd(actual, task.expected_distribution or {})
        elif task.expected_kind == "statevector":
            actual_sv = _run_statevector(qc)
            expected_sv = np.array(task.expected_statevector, dtype=complex)
            # サイズ違いは即失敗
            if actual_sv.shape != expected_sv.shape:
                res.L1 = True
                res.L2_distance = float("inf")
                res.error_category = "shape_mismatch"
                res.error_message = (
                    f"sv shape {actual_sv.shape} vs expected {expected_sv.shape}"
                )
            else:
                res.L1 = True
                res.L2_distance = _statevector_distance(actual_sv, expected_sv)
        else:
            res.error_category = "internal_bug"
            res.error_message = f"unknown expected_kind: {task.expected_kind}"
            return res
    except Exception as e:
        res.error_category = "runtime"
        res.error_message = f"{type(e).__name__}: {e}"
        return res

    res.L2 = res.L2_distance < task.threshold

    if res.L0 and res.L1 and res.L2:
        res.error_category = "ok"
    else:
        res.error_category = "wrong_output"

    return res
