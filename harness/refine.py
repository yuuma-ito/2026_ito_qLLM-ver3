"""Self-Refine（フィードバックループ）実行。

baseline（単発生成）に対する処置群。1 サンプルにつき最大 max_rounds 回まで
「生成 → 評価 → 失敗ならエラーをフィードバックして再生成」を繰り返す。
L2 を満たした時点で停止する。

フィードバックは「失敗したテストのメッセージ」相当の情報のみを返す:
  - L0/L1 失敗 … 例外カテゴリと例外メッセージ（トレース相当）
  - qubit 数不一致 … 期待 vs 実際の qubit 数
  - L2 失敗（分布タスク）… 期待分布 vs 実測分布（アサーション失敗メッセージ相当）
  - L2 失敗（状態ベクトルタスク）… 距離と閾値のみ（振幅列の全ダンプは避ける）

これは実行系から自然に得られる情報のみを与える「execution-feedback 型」Self-Refine
であり、正解コードを直接渡すことはしない。
"""
from __future__ import annotations

from harness.code_extractor import extract_code
from harness.evaluator import EvalResult, evaluate
from tasks import Task


def _fmt_dist(dist: dict[str, float], top: int = 8) -> str:
    """測定分布を確率降順で整形する（上位 top 件）。"""
    items = sorted(dist.items(), key=lambda kv: -kv[1])
    shown = items[:top]
    body = ", ".join(f"|{k}⟩: {v:.3f}" for k, v in shown)
    if len(items) > top:
        body += f", …(他 {len(items) - top} 件)"
    return "{" + body + "}"


def diagnose(task: Task, ev: EvalResult) -> str:
    """評価結果から、失敗の段階に応じた日本語の診断メッセージを作る。"""
    if not ev.L0:
        return (
            f"- コード実行（L0）に失敗しました。種別: {ev.error_category}\n"
            f"  {ev.error_message}"
        )
    if ev.error_category == "build_error":
        return (
            f"- build_circuit() の呼び出しで例外が発生しました。\n"
            f"  {ev.error_message}"
        )
    if ev.error_category == "wrong_n_qubits":
        return (
            f"- 回路の qubit 数が要求と異なります（{ev.error_message}）。\n"
            f"  期待どおりの qubit 数で回路を構成してください。"
        )
    if not ev.L1:
        return (
            f"- 回路のシミュレーション（L1）に失敗しました。種別: {ev.error_category}\n"
            f"  {ev.error_message}"
        )
    # L1 は通ったが L2（出力一致）で失敗
    lines = [
        f"- 回路は実行できましたが、出力が期待値と一致しません"
        f"（距離 {ev.L2_distance:.4f} > 閾値 {task.threshold}）。"
    ]
    if task.expected_kind == "distribution" and task.expected_distribution:
        lines.append(f"  期待される測定分布: {_fmt_dist(task.expected_distribution)}")
        if ev.actual_distribution is not None:
            lines.append(f"  あなたの回路の実測分布: {_fmt_dist(ev.actual_distribution)}")
        lines.append("  期待分布に一致するようゲート構成を見直してください。")
    else:
        lines.append(
            "  期待される最終状態に一致するよう、ゲートの種類・順序・対象 qubit を見直してください。"
        )
    return "\n".join(lines)


def build_feedback_prompt(task: Task, prev_code: str, ev: EvalResult) -> str:
    """次ラウンド用のフィードバック付きプロンプトを組み立てる。"""
    return (
        f"{task.prompt_text}\n\n"
        f"--- 前回の試行結果 ---\n"
        f"あなたは以下のコードを生成しましたが、検証に失敗しました。\n\n"
        f"```python\n{prev_code}\n```\n\n"
        f"検出された問題:\n{diagnose(task, ev)}\n\n"
        f"上記の問題を修正した、完全に動作する Python コードを "
        f"```python ``` ブロックで再度出力してください。"
    )
