"""タスク定義モジュール。

各タスクは Task dataclass を1つエクスポートする。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Task:
    """1つの評価タスクの定義。

    expected_kind:
      - "distribution": 測定確率分布で比較。expected_distribution を使用。
      - "statevector": 状態ベクトルで比較。expected_statevector を使用（complex のリスト）。

    threshold は L2 判定のしきい値（TVD または L2 距離）。
    """

    id: str
    name: str
    n_qubits: int
    prompt_text: str
    expected_kind: str  # "distribution" or "statevector"
    expected_distribution: Optional[dict[str, float]] = None
    expected_statevector: Optional[tuple[complex, ...]] = None
    threshold: float = 0.05
    expected_gate_count_range: Optional[tuple[int, int]] = None  # structure_match oracle (min, max)
    mock_correct_code: str = ""
    mock_wrong_code: str = ""
    task_difficulty: str = "medium"
    measurement_required: Optional[bool] = None
    expected_measurement_count: Optional[int] = None
    expected_classical_bits: Optional[int] = None


def all_tasks() -> list[Task]:
    """全タスクをリストで返す。"""
    from . import (
        t1_bell,
        t2_ghz,
        t3_dj_constant,
        t3_dj_balanced,
        t4_bv,
        t5_grover,
        t6_qft,
        t7_iqft,
        t8_qpe,
        t9_ansatz,
    )

    tasks = [
        t1_bell.TASK,
        t2_ghz.TASK,
        t3_dj_constant.TASK,
        t3_dj_balanced.TASK,
        t4_bv.TASK,
        t5_grover.TASK,
        t6_qft.TASK,
        t7_iqft.TASK,
        t8_qpe.TASK,
        t9_ansatz.TASK,
    ]
    difficulty = {
        "T1_Bell": "easy", "T2_GHZ": "easy",
        "T3a_DJ_constant": "medium", "T3b_DJ_balanced": "medium",
        "T4_BV_011": "medium", "T5_Grover_11": "medium",
        "T6_QFT_001": "hard", "T7_IQFT_001": "hard",
        "T8_QPE_001": "hard", "T9_Ansatz_001": "hard",
    }
    from dataclasses import replace
    return [replace(task, task_difficulty=difficulty[task.id]) for task in tasks]


def get_task(task_id: str) -> Task:
    for t in all_tasks():
        if t.id == task_id:
            return t
    raise KeyError(f"Unknown task id: {task_id}")
