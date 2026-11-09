"""Matched self-check prompts: no notice, failure notice, notice plus diagnostics."""
from harness.diagnostic_policy import DIAGNOSTIC_VERSION, diagnose
from harness.factorial_pilot import (SETTINGS, HOST, RecordedClient, wire_body, features,
                                     validate_response, ast_hash)
from harness.independent_4 import digest, code_hash, seed_for, levels
from scripts.reevaluation_impact_audit import event
from tasks import get_task

SCHEMA = 'notification_ablation_v1'
CONDITIONS = ('R0', 'R1', 'R2')
COMPARISONS = (('R0', 'R1'), ('R1', 'R2'))
SEED_NAMESPACE = 'notification_ablation_v1_20261106'
NOTICE = 'このコードは検証に失敗しました。'
REMOVED_SENTENCE = '外部のテスト結果や正解は与えません。'
PREFIX = ('{task}\n\n--- 前回のコード ---\n'
          'あなたは前回、以下のコードを生成しました。\n\n'
          '```python\n{code}\n```\n\n')
SUFFIX = ('このコードを自分で慎重に点検してください。タスク要件、Qiskit API、量子回路の意味、'
          'build_circuit() の仕様を確認し、問題がある場合は修正してください。\n'
          '最終的に、完全な修正版 Python コードだけを ```python ``` ブロックで出力してください。')
TEMPLATES = {'R0': PREFIX + SUFFIX,
             'R1': PREFIX + NOTICE + '\n' + SUFFIX,
             'R2': PREFIX + NOTICE + '\n検証器から得られた情報:\n{diagnostic}\n\n' + SUFFIX}
# Each Latin triple balances position; all six permutations balance preceding pairs.
ORDERS = (('R0', 'R1', 'R2'), ('R1', 'R2', 'R0'), ('R2', 'R0', 'R1'),
          ('R2', 'R1', 'R0'), ('R1', 'R0', 'R2'), ('R0', 'R2', 'R1'))


def ordered_cases(cases):
    if len({c['case_id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate initial case')
    return sorted(cases, key=lambda c: (digest([SEED_NAMESPACE, 'model', c['model_spec']]),
                                       digest([SEED_NAMESPACE, 'case', c['case_id']])))


def paired_seed(case, round_index):
    return seed_for(case['model_spec'], case['task_id'], case['base_seed'], round_index, SEED_NAMESPACE)


def build_prompt(condition, task, previous):
    if condition not in CONDITIONS:
        raise ValueError('Unknown ablation condition')
    diagnostic = diagnose(task, event(previous['primary'])) if condition == 'R2' else ''
    return TEMPLATES[condition].format(task=task.prompt_text, code=previous['code'], diagnostic=diagnostic)


def schedule(cases):
    slots = []
    for round_index in (1, 2, 3):
        counts = {}
        for index, case in enumerate(cases):
            model = case['model_spec']
            local = counts.get(model, 0)
            counts[model] = local + 1
            for position, condition in enumerate(ORDERS[(local+round_index-1) % 6], 1):
                slots.append(dict(round=round_index, case_id=case['case_id'], condition=condition,
                                  nominal_position=position, case_index=index,
                                  seed=paired_seed(case, round_index)))
    return slots


def validate_history(case, condition, history, records, *, complete=False):
    if condition not in CONDITIONS or not history or digest(history[0]) != digest(case['initial']):
        raise ValueError('Shared initial or condition drift')
    if len(history) != len(records)+1 or not 1 <= len(records) <= 3:
        raise ValueError('History size mismatch')
    for i, (attempt, record) in enumerate(zip(history[1:], records), 1):
        previous = history[i-1]
        if previous['primary']['L3']:
            raise ValueError('Continued after success')
        levels(attempt['primary'])
        prompt = build_prompt(condition, get_task(case['task_id']), previous)
        if (record['round'], record['seed'], record['case_id'], record['condition']) != (
                i, paired_seed(case, i), case['case_id'], condition):
            raise ValueError('Round/seed/condition drift')
        if record['input_prompt_sha256'] != code_hash(prompt) or record['previous_code_sha256'] != code_hash(previous['code']):
            raise ValueError('Own previous history or prompt drift')
        if record['code_sha256'] != code_hash(attempt['code']) or record['initial_fingerprint'] != digest(case['initial']):
            raise ValueError('Code/initial drift')
        if record['primary'] != attempt['primary'] or record['features'] != features(
                previous, attempt['code'], attempt['primary'], history[:i]):
            raise ValueError('Evaluation or feature drift')
        if record['wire_body_sha256'] != digest(wire_body(case['model_spec'], prompt, paired_seed(case, i))):
            raise ValueError('Wire settings drift')
        expected_policy = DIAGNOSTIC_VERSION if condition == 'R2' else 'none'
        if record['diagnostic_policy_version'] != expected_policy:
            raise ValueError('Diagnostic policy drift')
    if complete and not history[-1]['primary']['L3'] and len(records) != 3:
        raise ValueError('Incomplete unsuccessful path')
