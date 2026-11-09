"""Freeze the full 545-case notification experiment without model requests."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json

from harness.notification_ablation import (SCHEMA, CONDITIONS, COMPARISONS, SEED_NAMESPACE,
    SETTINGS, TEMPLATES, ordered_cases, schedule, paired_seed)
from harness.factorial_pilot import paired_seed as pilot_seed
from harness.independent_4 import digest, immutable_json, seed_for
from harness.llm_clients import SYSTEM_PROMPT
from harness.measurement_isolation import profile
from scripts.factorial_pilot_sources import ROOT, load_current
from scripts.measurement_ban_sources import sha
from scripts.measurement_ban_report import write_csv

IMPLEMENTATION = [
    'harness/notification_ablation.py', 'harness/factorial_pilot.py',
    'scripts/prepare_notification_ablation.py', 'scripts/run_notification_ablation.py',
    'scripts/analyze_notification_ablation.py', 'scripts/finish_notification_ablation.py',
    'scripts/complete_notification_ablation.py', 'tests/test_notification_ablation.py',
    'scripts/factorial_pilot_sources.py', 'harness/diagnostic_policy.py', 'harness/refine.py',
    'harness/llm_clients.py', 'harness/independent_4.py', 'harness/code_extractor.py',
    'harness/measurement_isolation.py', 'harness/evaluator.py', 'harness/run_state.py',
    'scripts/run_independent_4.py', 'scripts/measurement_ban_sources.py',
    'scripts/measurement_ban_report.py', 'prompts/system.txt',
]


def prepare():
    population, _, evidence = load_current()
    cases = ordered_cases(population)
    if len(cases) != 545 or len({c['model_spec'] for c in cases}) != 5 or len({c['task_id'] for c in cases}) != 10:
        raise ValueError('Fixed full cohort required')
    if any(c['initial']['primary']['L3'] for c in cases):
        raise ValueError('Initial successes cannot enter this cohort')
    seeds = [paired_seed(c, i) for c in cases for i in (1, 2, 3)]
    oldseeds = {pilot_seed(c, i) for c in cases for i in (1, 2, 3)} | {
        seed_for(c['model_spec'], c['task_id'], c['base_seed'], i, 'independent_4_v1')
        for c in cases for i in (1, 2, 3)} | set(range(23))
    if len(set(seeds)) != 1635 or set(seeds) & oldseeds:
        raise ValueError('Generation seed collision')
    run_id = 'notification_ablation_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    public = ROOT/'docs/analysis'/run_id
    output = ROOT/'results'/run_id
    public.mkdir(parents=True, exist_ok=False)
    (output/'private').mkdir(parents=True, mode=0o700)
    output.chmod(0o700)
    publiccases = [{k: c[k] for k in ('case_id', 'model_spec', 'task_id', 'base_seed', 'source_dir',
                                     'baseline_record_key', 'initial_error', 'task_difficulty')} | {
        'initial_code_sha256': c['initial']['hash'], 'initial_fingerprint': digest(c['initial'])} for c in cases]
    planned = schedule(cases)
    write_csv(public/'initial_cases_545.csv', publiccases)
    write_csv(public/'planned_schedule.csv', planned)
    (public/'prompts').mkdir()
    for condition, template in TEMPLATES.items():
        (public/'prompts'/f'{condition}.txt').write_text(template+'\n')
    (public/'prompts/system.txt').write_text(SYSTEM_PROMPT)
    protected = dict(evidence['inputs'])
    for folder in ('docs/graduation2026', 'docs/course_reports2026',
                   'docs/analysis/factorial_pilot_20261104T155653697245Z',
                   'docs/analysis/r_failure_paths_20261106'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                protected[str(path.relative_to(ROOT))] = sha(path)
    implementation = {name: sha(ROOT/name) for name in IMPLEMENTATION}
    for folder in ('tasks',):
        implementation.update({str(p.relative_to(ROOT)): sha(p) for p in (ROOT/folder).glob('*.py')})
    plan = dict(schema=SCHEMA, run_id=run_id, output_dir=str(output.relative_to(ROOT)),
                analysis_dir=str(public.relative_to(ROOT)), population=545, sample_size=545,
                sampling_rule='All current 545 initial failures; no outcome-based selection or replacements.',
                conditions=list(CONDITIONS), primary_comparisons=COMPARISONS,
                settings=SETTINGS, seed_namespace=SEED_NAMESPACE,
                seed_rule='Derived model/task/base_seed/round seed shared between conditions; distinct from prior runs; RNG stream identity not asserted.',
                orders='Six permutations, Latin triples; within-model case index and round shift; successful paths skipped without reordering.',
                stage1_requests=1635, max_total_requests=4905, max_additional_rounds=3,
                analysis_stages=[1, 3], primary_endpoint='L3 after first additional generation; same initial code across conditions.',
                secondary_endpoint='Cumulative L3 with success stop at three additional generations; diverging own histories.',
                strata=['model_spec', 'initial_error', 'task_id'],
                uncertainty='Reference percentile interval from 5000 paired base_seed-block resamples, seed 20261106; conditional seed stability, not population or internal-RNG confidence; no significance selection.',
                diagnostic_policy_version=__import__('harness.notification_ablation', fromlist=['DIAGNOSTIC_VERSION']).DIAGNOSTIC_VERSION,
                evaluator=profile(), model_digests=evidence['model_digests'], cases=publiccases,
                implementation=implementation, protected_inputs=protected,
                initials_sha256=digest(cases), schedule_sha256=digest(planned),
                prompt_templates=TEMPLATES, system_sha256=digest(SYSTEM_PROMPT),
                preparation_artifacts={str(p.relative_to(public)): sha(p) for p in public.rglob('*') if p.is_file()},
                historical_conditions_equivalent=False, git_operations_authorized=True,
                thesis_update_authorized=False, new_model_requests_at_preparation=0,
                inference_limit='R0 removes one sentence from historical R; R2 is not historical F. Fixed known cohort; one new generation seed per case/round. First-round input addition versus cumulative policy effects; no model-internal mechanism identification. No pooling with prior 100 pilot cases.',
                stopping_rule='Complete all planned paths regardless of outcome direction. Stop for API, ambiguous request, timeout, runtime failure, unknown classification or model/config drift; no automatic retry.')
    plan['plan_sha256'] = digest(plan)
    immutable_json(output/'private/initials.json', cases)
    for path in (output/'manifest.json', output/'experiment_config.json', public/'manifest.json'):
        immutable_json(path, plan)
    lines = ['失敗通知・詳細診断の追加効果を調べる固定実験計画', f'実験ID: {run_id}',
        f'固定計画hash: {plan["plan_sha256"]}',
        '対象は診断v2修正後の既存545初期失敗組全件。5モデル・10タスク。既存R成功組も含める。',
        'R0:既存Rから「外部のテスト結果や正解は与えません。」だけ削除。',
        'R1:R0に「このコードは検証に失敗しました。」だけ追加。',
        'R2:R1に検証器の詳細診断だけ追加。自己点検・修正・出力形式の指示は3条件で共通。',
        '旧Rそのものの再現ではなく、旧F/D/B4との直接の新旧差分は主張しない。',
        '主比較はR0-R1（通知追加）、R1-R2（診断追加）。主評価は追加1回のL3成功。',
        '第1段階1635要求の全件保存・検証・固定集計後、失敗経路だけ最大3回へ継続。全体の上限4905要求。',
        '後続出力は各条件自身の履歴を使う。累積差を同一コードに対する単一要素の直接効果と混同しない。',
        'temperature 0.7、max_tokens 1024、timeout 600秒、逐次1要求、reasoning_effort none。',
        '対応する新seedと6順序を固定。seed対応は内部乱数列の完全一致を証明しない。',
        '同じ要求回数上限を用いるが、診断による入力長増加は介入に含まれる。同tokens予算比較ではない。',
        '全条件の成功・片側成功・AST反復・構造変化・解析不能・tokens・終了理由を記録。',
        '差の参考区間はbase_seed単位の対応ブロック再標本化5000回（seed 20261106）。未知の母集団や内部生成乱数への信頼区間とはしない。',
        'モデル・課題・初期失敗類型の全層を保持し、少数層を選んだ有意差主張をしない。',
        'API障害・タイムアウト・評価基盤障害・曖昧要求・実装やdigestの変更では停止し、自動再送しない。',
        '生の要求・応答・生成コードはresults/<実験ID>/private/とraw.jsonlに非公開保存。',
        '完了・検証後、秘密情報と無関係な変更を除外して関連コード・設定・公開集計をコミットしoriginへpushする。',
        '既存固定結果と卒論本文は保持。新しい実験の観測結果からモデルの内的理解や一般的優劣を断定しない。']
    (public/'experiment_plan.txt').write_text('\n'.join(lines)+'\n')
    immutable_json(public/'preparation_check.json', dict(passed=True, plan_sha256=plan['plan_sha256'],
        cases=545, models=5, tasks=10, unique_new_seeds=1635, planned_slots=4905, new_model_requests=0))
    print(json.dumps({k: plan[k] for k in ('run_id', 'output_dir', 'analysis_dir', 'plan_sha256')}, ensure_ascii=False))
    return output


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--new-run', action='store_true', required=True)
    p.parse_args()
    prepare()
