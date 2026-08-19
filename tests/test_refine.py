"""Self-Refine フィードバックループの自己テスト。

MockClient を使い、API なしで「失敗→フィードバック→成功」の挙動を検証する。
mock-mixed は seed 偶数で correct / 奇数で wrong を返すので、run_refine が
ラウンドごとに seed を +1 する性質を使って round0=wrong, round1=correct を作る。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.evaluator import evaluate
from harness.llm_clients import MockClient
from harness.refine import build_feedback_prompt, diagnose
from harness.runner import run_refine
from tasks.t1_bell import TASK as T1


def test_refine_recovers_on_second_round():
    """round0 で wrong → フィードバック → round1 で correct になり成功する。"""
    client = MockClient("mock-mixed")
    # seed=1(奇=wrong) → round1 は seed=2(偶=correct)
    rec = run_refine(client, T1, seed=1, max_rounds=3)
    assert rec.mode == "refine"
    assert rec.L2, "2 ラウンド目で L2 を満たすはず"
    assert rec.first_success_round == 1
    assert rec.n_rounds == 2  # 成功した時点で停止
    assert len(rec.rounds) == 2
    assert rec.rounds[0]["L2"] is False
    assert rec.rounds[1]["L2"] is True


def test_refine_stops_immediately_on_first_success():
    """初回で成功すれば 1 ラウンドで終わる。"""
    client = MockClient("mock-correct")
    rec = run_refine(client, T1, seed=0, max_rounds=3)
    assert rec.L2
    assert rec.first_success_round == 0
    assert rec.n_rounds == 1
    assert len(rec.rounds) == 1


def test_refine_exhausts_rounds_when_never_correct():
    """常に wrong なら max_rounds まで使い、成功しない。"""
    client = MockClient("mock-wrong")
    rec = run_refine(client, T1, seed=0, max_rounds=3)
    assert not rec.L2
    assert rec.first_success_round == -1
    assert rec.n_rounds == 3
    assert len(rec.rounds) == 3


def test_feedback_prompt_includes_prev_code_and_diagnosis():
    """フィードバックプロンプトに前回コードと診断が含まれる。"""
    bad = "def build_circuit(:\n    pass"  # syntax error → L0 失敗
    ev = evaluate(bad, T1)
    assert not ev.L0
    prompt = build_feedback_prompt(T1, bad, ev)
    assert "前回の試行結果" in prompt
    assert bad in prompt
    assert "検出された問題" in prompt
    # 元のタスク指示も保持
    assert T1.prompt_text in prompt


def test_diagnose_l2_mismatch_mentions_distance():
    """L2 不一致の診断には距離が出る（正解コードは漏らさない）。"""
    ev = evaluate(T1.mock_wrong_code, T1)
    if ev.L1 and not ev.L2:
        msg = diagnose(T1, ev)
        assert "一致しません" in msg
        assert "距離" in msg
