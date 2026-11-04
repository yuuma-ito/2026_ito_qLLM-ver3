"""Corrected diagnostics for new generation; frozen v1 remains in refine.py.

Evaluation verdicts and task requirements are never changed here. Existing
historical prompt reconstruction imports keep using harness.refine.diagnose.
"""
from __future__ import annotations

from harness.evaluator import EvalResult
from harness.refine import diagnose as diagnose_legacy_v1
from tasks import Task

DIAGNOSTIC_VERSION = 'diagnostic_policy_v2_structure_qubits'
LEGACY_DIAGNOSTIC_VERSION = 'legacy_refine_diagnose_with_measurement_ban_v1'


def change_reason(ev: EvalResult) -> str:
    """Only the two reviewed defects change; preserve other diagnostic wording."""
    if not ev.L0 or ev.error_category == 'build_error':
        return ''
    if ev.error_category in {'wrong_n_qubits', 'qubit_count_mismatch'}:
        # wrong_n_qubits already had the correct wording in the frozen function.
        return 'qubit_category_mismatch' if ev.error_category == 'qubit_count_mismatch' else ''
    if (ev.error_category == 'interface_mismatch' and ev.error_message.startswith(
            'in-circuit measurements are forbidden by the common system instruction')):
        return ''  # Retain the previously fixed, specific measurement diagnostic.
    if ev.L1 and ev.L2 and not ev.structure_match:
        return 'structure_only_misreported_as_output'
    return ''


def diagnose(task: Task, ev: EvalResult) -> str:
    reason=change_reason(ev)
    if reason == 'qubit_category_mismatch':
        return (f'- 回路の qubit 数が要求と異なります（{ev.error_message}）。\n'
                '  期待どおりの qubit 数で回路を構成してください。')
    if reason == 'structure_only_misreported_as_output':
        lines=['- 指定入力の出力は一致しましたが、回路の構造要件を満たしていません。']
        if ev.error_message:
            lines.append('  検証器の詳細: '+ev.error_message)
        if task.expected_gate_count_range is not None:
            lo,hi=task.expected_gate_count_range
            lines.append(f'  課題の回路命令数の許容範囲は{lo}〜{hi}です（測定とbarrierを除く）。')
        lines.append('  課題で指定された構造要件を確認し、出力が一致している部分を保って修正してください。')
        return '\n'.join(lines)
    return diagnose_legacy_v1(task,ev)
