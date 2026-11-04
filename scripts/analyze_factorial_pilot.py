"""Pinned-stage exploratory summaries and independent saved-record validation."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
import math
from statistics import mean

from harness.factorial_pilot import CONDITIONS,validate_history
from harness.independent_4 import read_checkpoint,digest,code_hash,immutable_json
from scripts.measurement_ban_sources import ROOT,sha
from scripts.measurement_ban_report import write_csv


def aggregates(cases,records,stage):
    lookup={c['case_id']:c for c in cases};paths=defaultdict(list)
    for r in records:
        if r['case_id'] not in lookup or r['condition'] not in CONDITIONS:raise ValueError('unexpected record')
        paths[r['case_id'],r['condition']].append(r)
    expected={(c['case_id'],a) for c in cases for a in CONDITIONS}
    if set(paths)!=expected:raise ValueError('missing/unexpected condition path')
    pathrows=[];publicrounds=[]
    for (key,a),rr in sorted(paths.items()):
        rr.sort(key=lambda r:r['round']);case=lookup[key]
        if [r['round'] for r in rr]!=list(range(1,len(rr)+1)) or len(rr)>stage:raise ValueError('duplicate or unreachable stage rounds')
        history=[case['initial']]+[{'code':r['code'],'primary':r['primary']} for r in rr]
        validate_history(case,a,history,rr,complete=stage==3)
        passed=rr[-1]['primary']['L3'];asts=[r['features']['ast_sha256'] for r in rr]
        from harness.factorial_pilot import ast_hash
        initial_ast=ast_hash(case['initial']['code'])
        row={k:case[k] for k in ['case_id','model_spec','task_id','base_seed','initial_error','historical_outcome']}
        row.update(condition=a,success=passed,requests=len(rr),success_round=rr[-1]['round'] if passed else '',
                   total_tokens=sum(r['tokens_in']+r['tokens_out'] for r in rr),
                   failed_request_tokens=sum(r['tokens_in']+r['tokens_out'] for r in rr if not r['primary']['L3']),
                   any_prior_ast_repeat=any(r['features']['any_prior_ast_repeat'] for r in rr),
                   unchanged_ast_all_rounds=initial_ast is not None and all(h==initial_ast for h in asts),
                   any_same_failed_ast=any(r['features']['same_failed_ast_as_previous'] for r in rr),
                   final_error=rr[-1]['primary']['error_category'])
        pathrows.append(row)
        for r in rr:
            publicrounds.append({k:case[k] for k in ['case_id','model_spec','task_id','base_seed','initial_error']}|
                {k:r[k] for k in ['condition','round','seed','nominal_position','execution_index','tokens_in','tokens_out','generation_seconds','evaluation_seconds','finish_reason','code_sha256','input_prompt_sha256','previous_code_sha256']}|
                r['features']|{k:r['primary'][k] for k in ['L0','L1','L2','L3','structure_match','error_category','failure_stage','exception_type']})
    totals=[];pairs=[]
    for dim in [None,'model_spec','initial_error','task_id']:
        strata=['all'] if dim is None else sorted({c[dim] for c in cases})
        for value in strata:
            selected=[c for c in cases if dim is None or c[dim]==value];ids={c['case_id'] for c in selected}
            for a in CONDITIONS:
                pp=[r for r in pathrows if r['case_id'] in ids and r['condition']==a]
                rr=[r for r in publicrounds if r['case_id'] in ids and r['condition']==a]
                n=len(pp);success=sum(r['success'] for r in pp);total_tokens=sum(p['total_tokens'] for p in pp)
                valid=sum(r['ast_pair_comparable'] for r in rr);changed=sum(r['ast_changed_from_previous'] for r in rr)
                repeats=sum(r['same_failed_ast_as_previous'] for r in rr)
                totals.append({'stage':stage,'grouping':dim or 'overall','group':value,'condition':a,'initial_failures':n,
                    'successes':success,'success_rate':success/n,'requests':len(rr),'total_tokens':total_tokens,
                    'tokens_in':sum(r['tokens_in'] for r in rr),'tokens_out':sum(r['tokens_out'] for r in rr),
                    'tokens_per_success':total_tokens/success if success else '',
                    'failed_request_tokens':sum(p['failed_request_tokens'] for p in pp),
                    'never_success_path_tokens':sum(p['total_tokens'] for p in pp if not p['success']),
                    'generation_seconds':sum(r['generation_seconds'] for r in rr),
                    'requests_per_initial_group':len(rr)/n,'mean_success_round':mean(p['success_round'] for p in pp if p['success']) if success else '',
                    'ast_comparable_requests':valid,'ast_unassessable_requests':len(rr)-valid,'ast_changed_requests':changed,
                    'ast_changed_rate_valid_pairs':changed/valid if valid else '',
                    'ast_changed_rate_all_requests':changed/len(rr),
                    'same_failed_ast_requests':repeats,'same_failed_ast_rate_valid_pairs':repeats/valid if valid else '',
                    'same_failed_ast_rate_all_requests':repeats/len(rr),
                    'paths_with_any_ast_repeat':sum(p['any_prior_ast_repeat'] for p in pp),
                    'paths_with_unchanged_ast_all_rounds':sum(p['unchanged_ast_all_rounds'] for p in pp),
                    'finish_length':sum(r['finish_reason']=='length' for r in rr),
                    'finish_length_rate':sum(r['finish_reason']=='length' for r in rr)/len(rr),
                    'output_at_1024':sum(r['tokens_out']==1024 for r in rr),
                    'output_at_1024_rate':sum(r['tokens_out']==1024 for r in rr)/len(rr),
                    'small_stratum':n<10})
            outcomes={(r['case_id'],r['condition']):r['success'] for r in pathrows if r['case_id'] in ids}
            for left,right in [('A','B'),('B','C'),('C','D')]:
                count=Counter('both' if outcomes[k,left] and outcomes[k,right] else 'left_only' if outcomes[k,left] else 'right_only' if outcomes[k,right] else 'neither' for k in ids)
                pairs.append({'stage':stage,'grouping':dim or 'overall','group':value,'left':left,'right':right,'initial_failures':len(ids),
                              **{k:count[k] for k in ['both','left_only','right_only','neither']},
                              'right_minus_left_rate':(count['right_only']-count['left_only'])/len(ids),'small_stratum':len(ids)<10})
    overlap=[]
    for case in cases:
        success={a:paths[case['case_id'],a][-1]['primary']['L3'] for a in CONDITIONS}
        overlap.append({k:case[k] for k in ['case_id','model_spec','task_id','base_seed','initial_error']}|
                       {a:success[a] for a in CONDITIONS}|{'pattern_ABCD':''.join('1' if success[a] else '0' for a in CONDITIONS)})
    transitions=Counter((r['condition'],r['round'],r['error_before'],r['error_after']) for r in publicrounds)
    transitionrows=[{'condition':a,'round':rnd,'error_before':before,'error_after':after,'requests':n} for (a,rnd,before,after),n in sorted(transitions.items())]
    finish=Counter((r['condition'],r['round'],r['finish_reason']) for r in publicrounds)
    finishrows=[{'condition':a,'round':rnd,'finish_reason':reason,'requests':n} for (a,rnd,reason),n in sorted(finish.items())]
    if stage==1 and len(records)!=len(cases)*4:raise ValueError('stage1 must have one request per case and condition')
    for a in CONDITIONS:
        pooled=next(r for r in totals if r['condition']==a and r['grouping']=='overall')
        for grouping in ['model_spec','initial_error','task_id']:
            partition=[r for r in totals if r['condition']==a and r['grouping']==grouping]
            for key in ['initial_failures','successes','requests','total_tokens','failed_request_tokens']:
                if sum(r[key] for r in partition)!=pooled[key]:raise ValueError('stratum reconciliation failed')
    return {'summary':totals,'paired_success':pairs,'success_overlap':overlap,'paths':pathrows,
            'structural_stagnation':publicrounds,'error_transitions':transitionrows,'finish_reasons':finishrows}


def save_stage(plan,cases,records,stage,public,*,extra_checks=None):
    directory=public/('stage1' if stage==1 else 'final')
    derived=aggregates(cases,records,stage)
    fingerprint=digest(records)
    if directory.exists():
        manifest=read_checkpoint(directory/'manifest.json')
        if manifest['records_fingerprint']!=fingerprint or manifest['plan_sha256']!=plan['plan_sha256']:
            raise ValueError('frozen stage changed')
        for name,h in manifest['outputs'].items():
            if sha(directory/name)!=h:raise ValueError('saved stage output drift')
        return manifest
    directory.mkdir()
    for name,rows in derived.items():write_csv(directory/(name+'.csv'),rows)
    overall=[r for r in derived['summary'] if r['grouping']=='overall']
    pair=[r for r in derived['paired_success'] if r['grouping']=='overall']
    positions=Counter((r['condition'],r['nominal_position']) for r in records)
    write_csv(directory/'actual_positions.csv',[{'condition':a,'nominal_position':p,'requests':positions[a,p]} for a in CONDITIONS for p in [1,2,3,4]])
    lines=[f'B4と修正介入の差に関する予備実験：{"追加1回" if stage==1 else "最大3回"}',
           f'実験ID: {plan["run_id"]}',f'固定計画hash: {plan["plan_sha256"]}',
           'A/B/C/Dは新規の要因分析条件であり、既存B4/R/F/Dと同一の実装・成績とは扱わない。',
           '対象100初期失敗組は事前固定。少数モデル×失敗類型を含む不均等抽出であり、率はこの標本内の値。',
           '', '条件別成功率・消費・構造の反復']
    for r in overall:
        lines.append(f"{r['condition']}: {r['successes']}/{r['initial_failures']} ({100*r['success_rate']:.1f}%)、{r['requests']}要求、{r['total_tokens']} tokens、tokens/成功={r['tokens_per_success']}、失敗要求tokens={r['failed_request_tokens']}、同じ失敗AST={r['same_failed_ast_requests']}/{r['ast_comparable_requests']}有効対、length終了={r['finish_length']}、出力1024到達={r['output_at_1024']}")
    lines.extend(['','対応比較（同じ100組）'])
    for r in pair:lines.append(f"{r['left']}対{r['right']}: 共通成功{r['both']}、左のみ{r['left_only']}、右のみ{r['right_only']}、双方失敗{r['neither']}、右−左={100*r['right_minus_left_rate']:.1f}ポイント")
    lines.extend(['','モデル別・失敗類型別・タスク別',
                  '全層をsummary.csvとpaired_success.csvに保存。10組未満の層はsmall_stratum=Trueとし、一般化や有意差を断定しない。'])
    for dim in ['model_spec','initial_error']:
        for r in derived['summary']:
            if r['grouping']==dim:lines.append(f"{dim} / {r['group']} / {r['condition']}: {r['successes']}/{r['initial_failures']}")
    lines.extend(['','B4優位の説明と限界',
                  'A-Bは前回コード提示を含む新しい入力条件の差、B-Cは診断追加、C-Dは説明指示追加の対応観測。差の向きは対応表のとおり報告する。',
                  'AST反復と成功の関連、tokens、終了理由を併記するが、反復が失敗を引き起こした機構の確定ではない。AST一致は意味的同値性ではない。',
                  '独立再生成が必ず優れるという結論を前提にしない。この100組の結果から旧1000組でのB4優位の原因全体や一般的優劣を確定しない。',
                  '条件ごとに後続コードが異なり、累積差は単一要素だけの直接的・機構的因果効果ではない。',
                  '終了理由lengthとtokens_out=1024を別指標で示す。seed対応とAPIでの設定受理は乱数列や内部実装の完全一致の証明ではない。',
                  '小さな差の確証、他のseed・モデル・タスクへの再現性、同tokens予算での比較は未解明。追加検証が必要であり、本実験では予算・条件を事後変更しない。',
                  '旧初期生成tokensは新規消費に加えない。失敗要求への消費と最後まで未救済の経路への消費を分けて保存した。',
                  '既存主結果・卒論本文・図表・要旨は変更せず、コミット・pushは行わない。'])
    (directory/'report.txt').write_text('\n'.join(lines)+'\n')
    checks={'passed':True,'stage':stage,'cases':len(cases),'condition_paths':len(cases)*4,'actual_requests':len(records),
            'missing':0,'duplicates':0,'unexpected':0,'shared_initials_verified':True,
            'own_history_and_prompts_verified':True,'seeds_and_stop_verified':True,
            'strata_and_token_totals_verified':True,'records_fingerprint':fingerprint,**(extra_checks or {})}
    immutable_json(directory/'validation_report.json',checks)
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'stage':stage,'plan_sha256':plan['plan_sha256'],
              'records_fingerprint':fingerprint,'requests':len(records),
              'outputs':{p.name:sha(p) for p in directory.iterdir() if p.is_file()},'status':'completed_verified'}
    immutable_json(directory/'manifest.json',manifest)
    return manifest
