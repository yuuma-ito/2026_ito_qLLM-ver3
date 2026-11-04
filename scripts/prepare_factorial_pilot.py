"""Freeze the exploratory pilot before generation; no network or Git writes."""
from collections import Counter
from datetime import datetime,timezone
import argparse
import json

from harness.factorial_pilot import (SCHEMA,SETTINGS,SAMPLE_SEED,SEED_NAMESPACE,TEMPLATES,
                                     sample_cases,schedule,paired_seed,identity,DIAGNOSTIC_VERSION)
from harness.independent_4 import digest,immutable_json,seed_for
from harness.llm_clients import SYSTEM_PROMPT
from harness.measurement_isolation import profile
from scripts.factorial_pilot_sources import ROOT,load_current,refresh_stagnation,OLD_GAP
from scripts.measurement_ban_sources import sha
from scripts.measurement_ban_report import write_csv

IMPLEMENTATION=['harness/factorial_pilot.py','scripts/factorial_pilot_sources.py',
                'scripts/prepare_factorial_pilot.py','scripts/run_factorial_pilot.py',
                'scripts/analyze_factorial_pilot.py','harness/diagnostic_policy.py',
                'harness/refine.py','harness/llm_clients.py','harness/independent_4.py',
                'harness/code_extractor.py','prompts/system.txt','tests/test_factorial_pilot.py']


def prepare():
    population,histories,evidence=load_current()
    selected=sample_cases(population)
    if len({c['model_spec'] for c in selected})!=5 or len({c['task_id'] for c in selected})!=10:
        raise ValueError('five models and ten tasks must be covered')
    outcomes=Counter(c['historical_outcome'] for c in selected)
    if set(outcomes)!={'both','F_only','B4_only','neither'}:
        raise ValueError('fixed outcome-blind sample lacks an outcome cell; stop, do not search another seed')
    if [c['case_id'] for c in selected]!=[c['case_id'] for c in sample_cases(population)]:
        raise ValueError('selection cannot be reproduced')
    # Outcomes cannot influence the sample: permuting them leaves identities identical.
    shuffled=[dict(c,historical_outcome='ignored_'+str(i%4)) for i,c in enumerate(population)]
    if [c['case_id'] for c in sample_cases(shuffled)]!=[c['case_id'] for c in selected]:
        raise ValueError('historical outcomes leaked into selection')
    seeds=[paired_seed(c,r) for c in selected for r in [1,2,3]]
    oldseeds={seed_for(*identity(c),r,'independent_4_v1') for c in population for r in [1,2,3]}|set(range(23))
    if len(set(seeds))!=300 or set(seeds)&oldseeds:raise ValueError('new seed collision')
    run_id='factorial_pilot_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    public=ROOT/'docs/analysis'/run_id;private=ROOT/'results'/run_id
    public.mkdir(parents=True,exist_ok=False);private.mkdir(parents=True,exist_ok=False,mode=0o700)
    (private/'private').mkdir(mode=0o700)
    totals=refresh_stagnation(public/'stagnation_v2_before_generation',population,histories,evidence)
    publiccases=[]
    for c in selected:
        initial=c['initial']
        if initial['primary']['L3']:raise ValueError('selected initial must fail')
        publiccases.append({k:c[k] for k in ['case_id','model_spec','task_id','base_seed','source_dir','baseline_record_key','initial_error','task_difficulty','historical_outcome']}|
                           {'initial_code_sha256':initial['hash'],'initial_evaluation_sha256':digest(initial['primary']),
                            'initial_fingerprint':digest(initial)})
    population_public=[{k:c[k] for k in ['case_id','model_spec','task_id','base_seed','initial_error','historical_outcome']} for c in population]
    write_csv(public/'population_545.csv',population_public);write_csv(public/'selected_100.csv',publiccases)
    balance=[]
    for dims in [('model_spec','initial_error'),('model_spec',),('task_id',),('initial_error',),('historical_outcome',)]:
        original=Counter(tuple(c[k] for k in dims) for c in population)
        sampled=Counter(tuple(c[k] for k in dims) for c in selected)
        for k,n in sorted(original.items()):
            balance.append({'grouping':'+'.join(dims),**dict(zip(dims,k)),'population':n,'sample':sampled[k],
                            'population_fraction':n/545,'sample_fraction':sampled[k]/100,
                            'sampling_fraction':sampled[k]/n,'fraction_difference':sampled[k]/100-n/545,
                            'used_for_selection':dims==('model_spec','initial_error') or dims==('task_id',)})
    write_csv(public/'sampling_balance.csv',balance)
    planned=schedule(selected);write_csv(public/'planned_schedule.csv',planned)
    (public/'prompts').mkdir()
    for condition,template in TEMPLATES.items():(public/'prompts'/f'{condition}.txt').write_text(template+'\n')
    (public/'prompts/system.txt').write_text(SYSTEM_PROMPT)
    protected=dict(evidence['inputs'])
    for directory in [ROOT/'docs/graduation2026',ROOT/'docs/course_reports2026',OLD_GAP]:
        for p in directory.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts:protected[str(p.relative_to(ROOT))]=sha(p)
    for name in ['docs/diagnostic_policy_v2_followup.txt','docs/diagnostic_policy_v2.txt']:
        protected[name]=sha(ROOT/name)
    plan={'schema':SCHEMA,'run_id':run_id,'output_dir':str(private.relative_to(ROOT)),
          'analysis_dir':str(public.relative_to(ROOT)),'population':545,'sample_size':100,
          'sample_seed':SAMPLE_SEED,'sampling_rule':'model×initial_error: minimum one per nonempty cell, residual proportional largest remainders; within-cell seeded sample; task-coverage replacement inside same cell only; outcomes never used',
          'selection_outcomes_checked_only_after_sampling':dict(outcomes),'population_sampling_balance':'sampling_balance.csv',
          'conditions':['A','B','C','D'],'historical_conditions_equivalent':False,'settings':SETTINGS,
          'preparation_artifacts':{str(p.relative_to(public)):sha(p) for p in public.rglob('*') if p.is_file()},
          'seed_namespace':SEED_NAMESPACE,'seed_rule':'SHA256([namespace,model,task,base_seed,round]); same derived seed across all four conditions; no claim of identical random streams',
          'orders':'Williams four sequences, case_index+round-1 modulo 4; model blocks; skip successes without reordering',
          'stage1_requests':400,'max_total_requests':1200,'max_additional_rounds':3,
          'diagnostic_policy_version':DIAGNOSTIC_VERSION,'evaluator':profile(),'model_digests':evidence['model_digests'],
          'cases':publiccases,'implementation':{name:sha(ROOT/name) for name in IMPLEMENTATION},
          'protected_inputs':protected,'initials_sha256':digest(selected),'schedule_sha256':digest(planned),
          'prompt_templates':TEMPLATES,'system_sha256':digest(SYSTEM_PROMPT),
          'stagnation_refresh_manifest_sha256':sha(public/'stagnation_v2_before_generation/manifest.json'),
          'primary_comparisons':[['A','B'],['B','C'],['C','D']],'analysis_stages':[1,3],
          'strata':['model_spec','initial_error','task_id'],'stage1_report_required_before_round2':True,
          'structural_definition':'ast.dump without attributes/comments/format; not semantic equivalence; invalid AST counted separately',
          'confidence_intervals':'not used for exploratory pilot; paired counts and differences, no significance selection',
          'new_model_requests_at_preparation':0,'git_operations_authorized':False,'thesis_update_authorized':False,
          'inference_limit':'outcome-blind stratified exploratory sample; unequal inclusion rates; unweighted sample rates do not estimate the full 545 without adjustment; no general superiority or mechanistic cumulative effect',
          'parameter_acceptance':'exact wire body + successful API response for experimental requests; no extra probe generations; acceptance does not prove full RNG equivalence or internal server implementation'}
    plan['plan_sha256']=digest(plan)
    immutable_json(private/'private/initials.json',selected)
    immutable_json(private/'experiment_config.json',plan);immutable_json(private/'manifest.json',plan)
    immutable_json(public/'manifest.json',plan)
    report=['B4と修正介入の差に関する新規予備実験計画',
            f'実験ID: {run_id}',f'計画hash: {plan["plan_sha256"]}',
            '既存の主実験・診断v2既存結果・卒論・図表・要旨は変更しない。コミット・pushしない。',
            '初期失敗545組から100組を固定。5モデル・10タスク、モデル×失敗類型層別。成否を使わず抽出し、抽出後に4成否群の包含だけを確認した。',
            '少数のモデル×失敗類型セルを最低1組含めるため、抽出率は均一でない。母集団との差はsampling_balance.csv。',
            'A:課題のみ、B:課題+前回コード、C:B+診断v2、D:C+説明・原因分析。既存B4/R/F/Dとは別の要因分析条件。',
            '4条件の共通system・課題・出力形式・temperature 0.7・出力1024 tokens・timeout600秒・逐次1要求・reasoning_effort noneを固定。',
            'Dの説明はコード先頭# DEBUG:コメント3〜6行に固定。説明への適合は別注記とし、主L3に新条件を追加しない。',
            '4条件とも同じ保存初期コード・評価から始める。Aは毎回独立生成、B/C/Dは自身の直前コードと評価のみを使う。',
            '新seedはmodel/task/初期組/roundから導出し条件間で対応。生成seedの対応が乱数条件の完全一致を意味するとは扱わない。',
            'Williams順序で予定位置を均等化し、modelごとに逐次実行。成功時停止で後半の実行構成が変わる分は記録する。',
            '第1段階は全100×4=400要求。全件保存後に第1段階の比較・対応表・構造特徴・tokens・終了理由・上限到達率を確定する。',
            '第2段階は失敗条件だけを同じ設計でround2,3へ継続し、最大1200要求。stage1とstage2は連続した同一実験。',
            '主比較A-B/B-C/C-D。両成功・左のみ・右のみ・両失敗、成功率差を初回追加と累積で分ける。',
            'モデル別・初期失敗類型別・タスク別を事前指定。小標本の層を選んで有意差を主張しない。',
            'AST比較は文字構造のみ。構造変化率と同じ失敗AST再出力率は有効なAST対を分母とした率と全要求分母の率を併記し、解析不能を分離する。',
            '全実消費、失敗要求への消費、未救済経路への消費、tokens/救済を保存。初期生成の旧消費は新規消費に加えない。',
            'API/タイムアウト/評価基盤障害やdigest・実装・入力の変更で停止し、記録を残す。曖昧要求の自動再送・条件変更・対象差替えをしない。',
            '既存停滞分析のv2更新はstagnation_v2_before_generation/。新規生成・生成コード実行・再採点なしで作成済み。',
            '探索的予備実験。後続コードが条件ごとに異なるため累積差を単一要素の機構的因果効果と断定しない。',
            '生の要求・応答・評価・コードと初期集合はresults/<実験ID>/private/に保存し、公開集計とは分離する。']
    (public/'experiment_plan.txt').write_text('\n'.join(report)+'\n')
    immutable_json(public/'preparation_check.json',{'passed':True,'plan_sha256':plan['plan_sha256'],
                   'sample_reproducible':True,'outcome_permutation_does_not_change_sample':True,
                   'selected':100,'models':5,'tasks':10,'new_seeds':300,'schedule_slots':1200,
                   'stage1_positions':{a:{str(pos):sum(r['condition']==a and r['nominal_position']==pos and r['round']==1 for r in planned) for pos in [1,2,3,4]} for a in ['A','B','C','D']},
                   'historical_outcome_counts':dict(outcomes),'stagnation_v2':totals,'new_model_requests':0})
    print(json.dumps({'output_dir':plan['output_dir'],'analysis_dir':plan['analysis_dir'],'plan_sha256':plan['plan_sha256'],'selected':100,'outcomes':dict(outcomes)},ensure_ascii=False,indent=2))
    return private


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--new-run',action='store_true',required=True);p.parse_args();prepare()
