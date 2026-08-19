"""ver2 介入プロンプトの差分を API/Qiskit 実行なしで確認する。"""
from __future__ import annotations

from harness.evaluator import EvalResult
from harness.interventions import build_intervention_prompt
from tasks import Task


TASK = Task(
    id="T_TEST",
    name="test",
    n_qubits=2,
    prompt_text="Make a two-qubit circuit.",
    expected_kind="distribution",
    expected_distribution={"00": 0.5, "11": 0.5},
)
EV = EvalResult(
    L0=True,
    L1=True,
    L2=False,
    L3=True,
    L2_distance=0.5,
    error_category="wrong_output",
    actual_distribution={"00": 1.0},
)
CODE = "def build_circuit():\n    pass"


def test_self_refine_does_not_include_execution_diagnosis():
    p = build_intervention_prompt("self_refine", TASK, CODE, EV)
    assert CODE in p
    assert "外部のテスト結果や正解は与えません" in p
    assert "期待される測定分布" not in p
    assert "実測分布" not in p


def test_execution_feedback_includes_evaluator_information():
    p = build_intervention_prompt("execution_feedback", TASK, CODE, EV)
    assert "検証器から得られた情報" in p
    assert "期待される測定分布" in p
    assert "実測分布" in p


def test_self_debugging_requires_explanation_as_code_comments():
    p = build_intervention_prompt("self_debugging", TASK, CODE, EV)
    assert "説明" in p
    assert "失敗原因" in p
    assert "# DEBUG:" in p
