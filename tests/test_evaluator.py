"""evaluator の自己テスト。

各タスクについて：
  - mock_correct_code は L0/L1/L2 全通過すること
  - mock_wrong_code は L2 で落ちること
"""
from __future__ import annotations

import sys
from pathlib import Path

# pytest 実行時に project root を sys.path に追加
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from harness.code_extractor import extract_code
from harness.evaluator import evaluate
from tasks import all_tasks


@pytest.mark.parametrize("task", all_tasks(), ids=lambda t: t.id)
def test_mock_correct_passes_L2(task):
    """canonical な correct コードは L0/L1/L2 通過、L2 距離は閾値以下。"""
    res = evaluate(task.mock_correct_code, task)
    assert res.L0, f"{task.id}: L0 failed: {res.error_category}: {res.error_message}"
    assert res.L1, f"{task.id}: L1 failed: {res.error_category}: {res.error_message}"
    assert res.L2, (
        f"{task.id}: L2 failed: distance={res.L2_distance} "
        f"threshold={task.threshold} cat={res.error_category}"
    )


@pytest.mark.parametrize("task", all_tasks(), ids=lambda t: t.id)
def test_mock_wrong_fails_L2(task):
    """明らかに間違ったコードは L2 を通らない。"""
    res = evaluate(task.mock_wrong_code, task)
    # L0/L1 は通る場合があってよい（コード自体は走る）
    # L2 だけは通らないことを要求
    assert not res.L2, (
        f"{task.id}: wrong code unexpectedly passed L2 "
        f"(distance={res.L2_distance})"
    )


def test_extract_code_basic():
    """フェンス付きブロックを抽出できる。"""
    text = "Here is the answer:\n```python\nx = 1\n```\nThanks!"
    assert extract_code(text) == "x = 1"


def test_extract_code_no_fence():
    """フェンスがなければ全文を返す。"""
    text = "x = 1"
    assert extract_code(text) == "x = 1"


def test_extract_code_largest():
    """複数ブロックがあれば最大を返す。"""
    text = "```python\na = 1\n```\nthen\n```python\nb = 1\nc = 2\nd = 3\n```"
    assert "b = 1" in extract_code(text)


def test_syntax_error_caught():
    """構文エラーは L0 で落ちる。"""
    from tasks.t1_bell import TASK as T1

    res = evaluate("def build_circuit(:\n    pass", T1)
    assert not res.L0
    assert res.error_category == "syntax"


def test_no_function_caught():
    """build_circuit が定義されていないと L0 後の関数チェックで落ちる。"""
    from tasks.t1_bell import TASK as T1

    res = evaluate("x = 1", T1)
    assert not res.L0
    assert res.error_category == "no_function"
