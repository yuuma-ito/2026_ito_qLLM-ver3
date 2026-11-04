"""v2 diagnostic prompts used by the active runner.

The frozen harness.interventions builders remain unchanged for historical
reconstruction. R and initial/P prompts retain their exact historical text.
"""
from harness.diagnostic_policy import DIAGNOSTIC_VERSION, diagnose
from harness.interventions import build_intervention_prompt as build_legacy_intervention_prompt
from harness.evaluator import EvalResult
from tasks import Task


def build_intervention_prompt(intervention: str, task: Task, prev_code: str, ev: EvalResult) -> str:
    if intervention == 'execution_feedback':
        return (
            f"{task.prompt_text}\n\n"
            "--- 前回の試行結果 ---\n"
            "あなたは以下のコードを生成しましたが、実行ベース検証に失敗しました。\n\n"
            f"```python\n{prev_code}\n```\n\n"
            f"検証器から得られた情報:\n{diagnose(task, ev)}\n\n"
            "この実行フィードバックを使って問題を修正し、完全な Python コードを "
            "```python ``` ブロックで出力してください。"
        )
    if intervention == 'self_debugging':
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
    return build_legacy_intervention_prompt(intervention,task,prev_code,ev)
