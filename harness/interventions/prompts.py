"""ver2 の介入プロンプト定義。

4 条件:
- baseline: 初回生成のみ
- self_refine: 外部評価情報を与えず、前回コードを自己批評して修正
- execution_feedback: evaluator の診断情報を与えて修正
- self_debugging: evaluator の診断情報に加え、説明→原因分析→修正を明示要求
- preventive_spec: 生成前に共通の注意事項を与え、1回のみ生成
"""
from __future__ import annotations

from harness.evaluator import EvalResult
from harness.refine import diagnose
from tasks import Task

INTERVENTIONS = (
    "baseline",
    "self_refine",
    "execution_feedback",
    "self_debugging",
    "preventive_spec",
)

PREVENTIVE_SPEC = """量子コード生成では以下の点に注意してください。

1. 指定された関数名と戻り値形式を必ず守ること。
2. Qiskitに存在しないAPIを使用しないこと。
3. 量子ビット数と古典ビット数を一致させること。
4. 測定結果のビット順序に注意すること。
5. 期待される測定分布または状態ベクトルと一致する回路を作ること。
6. 不要なゲートを追加しないこと。
7. 指定されたインターフェースを必ず実装すること。"""


def build_initial_prompt(intervention: str, task: Task) -> str:
    if intervention == "preventive_spec":
        return f"{task.prompt_text}\n\n{PREVENTIVE_SPEC}"
    return task.prompt_text


def intervention_feedback_type(intervention: str) -> str:
    mapping = {
        "baseline": "none",
        "self_refine": "self_critique",
        "execution_feedback": "execution_feedback",
        "self_debugging": "self_debugging",
        "preventive_spec": "preventive_spec",
    }
    if intervention not in mapping:
        raise ValueError(f"Unknown intervention: {intervention}")
    return mapping[intervention]


def build_intervention_prompt(
    intervention: str,
    task: Task,
    prev_code: str,
    ev: EvalResult,
) -> str:
    """次ラウンド用プロンプトを介入種別ごとに構築する。"""
    if intervention == "self_refine":
        return (
            f"{task.prompt_text}\n\n"
            "--- 前回のコード ---\n"
            "あなたは前回、以下のコードを生成しました。外部のテスト結果や正解は与えません。\n\n"
            f"```python\n{prev_code}\n```\n\n"
            "このコードを自分で慎重に点検してください。タスク要件、Qiskit API、量子回路の意味、"
            "build_circuit() の仕様を確認し、問題がある場合は修正してください。\n"
            "最終的に、完全な修正版 Python コードだけを ```python ``` ブロックで出力してください。"
        )

    if intervention == "execution_feedback":
        return (
            f"{task.prompt_text}\n\n"
            "--- 前回の試行結果 ---\n"
            "あなたは以下のコードを生成しましたが、実行ベース検証に失敗しました。\n\n"
            f"```python\n{prev_code}\n```\n\n"
            f"検証器から得られた情報:\n{diagnose(task, ev)}\n\n"
            "この実行フィードバックを使って問題を修正し、完全な Python コードを "
            "```python ``` ブロックで出力してください。"
        )

    if intervention == "self_debugging":
        return (
            f"{task.prompt_text}\n\n"
            "--- 前回の試行結果 ---\n"
            f"```python\n{prev_code}\n```\n\n"
            f"検証器から得られた情報:\n{diagnose(task, ev)}\n\n"
            "次の順序で自己デバッグしてください。\n"
            "1. 前回コードが何をしているかを説明する。\n"
            "2. タスク要件と検証結果を照合し、失敗原因を特定する。\n"
            "3. 原因を踏まえてコードを修正する。\n"
            "4. system の『コードブロックのみ』制約を守るため、説明と原因分析は "
            "修正版コードブロック先頭の Python コメント（# DEBUG: ...）として 3〜6 行残す。"
            "その後に完全な修正版コードを書く。"
        )

    if intervention == "baseline":
        raise ValueError("baseline has no refinement prompt")
    raise ValueError(f"Unknown intervention: {intervention}")
