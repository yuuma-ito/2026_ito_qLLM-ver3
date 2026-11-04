"""Verify completed v2 suffixes and freeze a separate six-condition aggregate.

Reads generated code as text only; no model requests or generated-code execution.
Uses the same paired and six-condition aggregation functions as the old snapshot.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import json
import math
import sqlite3

from harness.independent_4 import read_checkpoint,code_hash,levels
from harness.run_state import atomic_json
from scripts import analyze_verified_rescues as base
from scripts.analyze_independent_4 import analyze,LABELS
from scripts.measurement_ban_report import write_csv
from scripts.measurement_ban_sources import ROOT,load_sources,csv_rows,sha,code_key
from scripts.reevaluation_followup_validation import read_db,validate_rows
from scripts.run_diagnostic_policy_followup import prepare,validate_result,IMPACT,FIXED

OUT=ROOT/'docs/analysis/diagnostic_policy_corrected_20261104'


def freeze():
    latest=json.loads((ROOT/'.cache/diagnostic_policy_followup_latest.json').read_text())
    if latest['status']!='completed_verified':raise ValueError('followup incomplete')
    output=ROOT/latest['output_dir'];plan,prefixes=prepare()
    if json.loads((output/'public_result.json').read_text())!=latest:
        raise ValueError('public result pointer drift')
    if read_checkpoint(output/'private/server_before.json')!=latest['server_before']:
        raise ValueError('server preflight evidence drift')
    if read_checkpoint(output/'manifest.json')!=plan or latest['plan_sha256']!=plan['plan_sha256']:
        raise ValueError('completed manifest/plan drift')
    completed={};new_rows=[];disposition=[]
    for c in plan['cases']:
        key=c['record_key'];folder=output/'private'/key
        result=read_checkpoint(folder/'completed.json');validate_result(result,c,prefixes[key],plan)
        completed[key]=result
        expected_rounds=list(range(c['branch_generation_round'],result['final_round']+1))
        actual_requests=sorted(int(p.stem.split('_')[1]) for p in folder.glob('round_*_request.json'))
        if actual_requests!=expected_rounds:raise ValueError('unexpected/missing requests')
        if list(folder.glob('round_*_failure.json')):raise ValueError('unresolved API failure')
        for i in range(c['branch_generation_round'],4):
            disposition.append({k:c[k] for k in ['record_key','model_spec','task_id','base_seed','condition_id']}|
                               {'round':i,'seed':c['base_seed']+i,'disposition':'generated' if i in expected_rounds else 'skipped_after_success'})
        for a in result['rounds'][c['branch_generation_round']:]:
            i=a['round'];req=read_checkpoint(folder/f'round_{i}_request.json')
            response=read_checkpoint(folder/f'round_{i}_response.json')
            evaluation=read_checkpoint(folder/f'round_{i}_evaluation.json')
            if code_hash(req['user'])!=a['input_prompt_sha256'] or code_hash(req['system'])!=plan['system_sha256'] or req['seed']!=a['round_seed'] or req['plan_sha256']!=plan['plan_sha256']:
                raise ValueError('request/body identity mismatch')
            from harness.code_extractor import extract_code
            if code_hash(extract_code(response['raw_output']))!=a['code_sha256'] or evaluation['primary']!=a['primary'] or evaluation['runtime_status']!='completed':
                raise ValueError('response or evaluation mismatch')
            if response['response']['model']!=c['model_spec'].removeprefix('ollama:'):
                raise ValueError('response model mismatch')
            for metric in ['tokens_in','tokens_out','generation_seconds']:
                if a[metric]!=response[metric]:raise ValueError('new cost mismatch')
            new_rows.append({k:c[k] for k in ['record_key','source_dir','model_spec','task_id','base_seed','condition_id']}|
                {k:a[k] for k in ['round','round_seed','code_sha256','input_prompt_sha256','system_sha256','diagnostic_policy_version','tokens_in','tokens_out','generation_seconds','evaluation_seconds','finish_reason']}|
                {k:a['primary'][k] for k in ['L0','L1','L2','L3','structure_match','error_category','failure_stage']})
    if len(completed)!=10 or len(new_rows)!=latest['new_requests'] or len(disposition)!=26:
        raise ValueError('planned coverage mismatch')
    if sum(r['final_success'] for r in completed.values())!=latest['successful_paths'] or sum(r['tokens_in']+r['tokens_out'] for r in new_rows)!=latest['new_tokens']:
        raise ValueError('public success/token total mismatch')
    data=load_sources();old_rounds=csv_rows(FIXED/'reachable_rounds.csv')
    status=json.loads((ROOT/'docs/analysis/reevaluation_full_20261014T141718Z/run_status.json').read_text())
    dbplan,stored=read_db(__import__('pathlib').Path(status['checkpoint_dir'])/'checkpoint.sqlite3');validate_rows(dbplan,stored)
    primary={k:json.loads(t)['primary'] for k,_,_,t,_ in stored}
    mdb=ROOT/'.cache/measurement_ban_impact_20261104/checkpoint.sqlite3'
    with sqlite3.connect(f'file:{mdb}?mode=ro',uri=True) as db:
        revision={}
        for key,t,h in db.execute("select key,result,result_hash from results where state='completed'"):
            if code_hash(t)!=h:raise ValueError('measurement checkpoint drift')
            revision[key]=json.loads(t)
    grouped=defaultdict(list)
    for r in old_rounds:grouped[r['record_key']].append(r)
    suffixes={};attempts={}
    for key,rr in grouped.items():
        rr.sort(key=lambda r:int(r['round']));pp=[]
        for r in rr:
            i=int(r['round'])
            if r['origin']=='saved_prefix':ev=primary[key+':'+str(i)]
            else:
                if key not in suffixes:
                    suffixes[key]={a['round']:a for a in json.loads((ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key/'completed.json').read_text())['suffix']}
                ev=suffixes[key][i]['evaluation']['primary']
            check=revision.get(code_key(r['task_id'],r['code_sha256']))
            if check and check['measurement_violation']:ev=check['primary']
            if ev['L3']!=base.truth(r['new_L3']):raise ValueError('frozen path verdict mismatch')
            pp.append({'round':i,'primary':ev,'code_sha256':r['code_sha256'],'tokens_in':int(r['tokens_in']),
                       'tokens_out':int(r['tokens_out']),'generation_seconds':float(r['generation_seconds']),'evaluation_seconds':None})
        if key in completed:
            pp=[{k:a[k] for k in ['round','primary','code_sha256','tokens_in','tokens_out','generation_seconds']}|
                 {'evaluation_seconds':a.get('evaluation_seconds')} for a in completed[key]['rounds']]
        attempts[key]=pp
    # Reuse the same paired rescue aggregation as the preceding fixed snapshot.
    mixed=deepcopy(data['mixed']);paths={}
    for m in mixed:
        key=m['record_key'];pp=attempts[key]
        m.update(success=str(pp[-1]['primary']['L3']),stop_round=pp[-1]['round'])
        if key in completed:m['path_origin']='preserved_prefix+diagnostic_v2_suffix'
        paths[key]=[{'code_sha256':a['code_sha256'],**{'new_'+k:str(a['primary'][k]) for k in ['L0','L1','L2','L3','structure_match','error_category']}} for a in pp]
    difficulties={r['task_id']:r['task_difficulty'] for r in old_rounds}
    ledger,summaries,overlaps,fd=base.analyze(mixed,paths,difficulties)
    meta={r['record_key']:r for r in ledger};reachable=[]
    for key,rr in grouped.items():
        for a in attempts[key]:
            i=a['round'];r=deepcopy(rr[min(i,len(rr)-1)])
            r.update(meta.get(key,{}));r.update(round=i,code_sha256=a['code_sha256'],new_L3=a['primary']['L3'],new_error_category=a['primary']['error_category'],
                      tokens_in=a['tokens_in'],tokens_out=a['tokens_out'],tokens=a['tokens_in']+a['tokens_out'],generation_seconds=a['generation_seconds'])
            if key in completed and i>=len(prefixes[key]):r['origin']='diagnostic_v2_suffix'
            reachable.append(r)
    b4=deepcopy(data['B4_records']);followdir=ROOT/json.loads((FIXED/'followup_public_result.json').read_text())['output_dir']
    follow=read_checkpoint(followdir/'private/completed.json')
    cases=[];references={}
    grouped_meta=defaultdict(dict)
    for m in mixed:grouped_meta[(m['model_spec'],m['task_id'],int(m['base_seed']))][m['condition_id']]=m
    for r in b4:
        if r['baseline_record_key']==follow['baseline_record_key']:r['rounds']=deepcopy(follow['rounds'])
        else:
            for a in r['rounds']:
                check=revision.get(code_key(r['task_id'],a['code_sha256']))
                if check and check['measurement_violation']:a['primary']=deepcopy(check['primary'])
        for i,a in enumerate(r['rounds']):
            if i:a['repeated_code']=any(p['code_sha256']==a['code_sha256'] for p in r['rounds'][:i])
        r['final_success']=r['rounds'][-1]['primary']['L3']
        r['first_success_round']=next((a['round'] for a in r['rounds'] if a['primary']['L3']),None)
        r['first_success_generation']=r['first_success_round']+1 if r['first_success_round'] is not None else None
        cases.append({k:r[k] for k in ['model_spec','task_id','base_seed','source_dir','baseline_record_key','task_difficulty']}|{'initial':deepcopy(r['rounds'][0])})
        identity=(r['model_spec'],r['task_id'],r['base_seed']);references[identity]={}
        for cond,label in LABELS.items():
            pp=attempts[grouped_meta[identity][cond]['record_key']]
            if label!='P' and (pp[0]['code_sha256']!=r['rounds'][0]['code_sha256'] or any(pp[0]['primary'][k]!=r['rounds'][0]['primary'][k] for k in ['L0','L1','L2','L3'])):
                raise ValueError('shared initial mismatch')
            references[identity][label]=pp
    config=json.loads((ROOT/'docs/analysis/independent_4_completed_20261022/runner_experiment_config.json').read_text())
    combined=analyze(b4,cases,references,config)
    for condition in ['B','P','R','B4']:
        old=[r for r in csv_rows(FIXED/'summary.csv') if r['condition']==condition]
        fresh=[r for r in combined['summary'] if r['condition']==condition]
        for a,b in zip(old,fresh):
            for k in ['groups','initial_failures','final_L3_successes','successes_from_initial_failure','additional_requests','additional_tokens','additional_generation_seconds']:
                if not math.isclose(float(a[k]),b[k],rel_tol=1e-10,abs_tol=1e-6):raise ValueError('unaffected condition changed')
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'core').mkdir(exist_ok=True)
    for name in ['summary','overlap','pairwise','first_success']:write_csv(OUT/(name+'.csv'),combined[name])
    for name,rr in [('paired_records',ledger),('repair_summary',[r for r in summaries if r['condition_id'] in base.REPAIRS]),
                    ('preventive_summary',[r for r in summaries if r['condition_id']==base.P]),('fd_overlap_records',overlaps),('fd_overlap_summary',fd)]:
        write_csv(OUT/'core'/(name+'.csv'),rr)
    write_csv(OUT/'reachable_rounds.csv',reachable);write_csv(OUT/'new_rounds.csv',new_rows);write_csv(OUT/'generation_disposition.csv',disposition)
    comparison=[]
    for c in plan['cases']:
        result=completed[c['record_key']]
        comparison.append({k:c[k] for k in ['record_key','source_dir','model_spec','task_id','base_seed','condition_id','branch_generation_round']}|
            {'old_final_success':False,'v2_final_success':result['final_success'],'old_stop_round':3,'v2_stop_round':result['final_round'],
             'old_suffix_requests':c['generation_cap'],'new_requests':result['new_requests'],
             'new_tokens':sum(a['tokens_in']+a['tokens_out'] for a in result['rounds'][c['branch_generation_round']:])})
    write_csv(OUT/'path_comparison.csv',comparison)
    totals=[r for r in combined['summary'] if r['grouping']=='overall' and r['generation_cap']==(1 if r['condition'] in ['B','P'] else 4)]
    success={r['condition']:r['final_L3_successes'] for r in totals}
    fdoverlap=next(r for r in fd if r['scope']=='pooled' and r['grouping']=='overall')
    sanity={'passed':True,'status':'completed_verified','paths':10,'unique_initial_groups':6,'missing':0,'duplicates':0,
            'unexpected':0,'pending_paths':0,'runtime_failures':0,'api_failures':0,'ambiguous_requests':0,
            'new_requests':len(new_rows),'skipped_after_success':sum(r['disposition']=='skipped_after_success' for r in disposition),
            'planned_request_slots':26,'historical_sources_unchanged':True,'shared_initial_unchanged':True,
            'unaffected_B_P_R_B4_verified':True,'stratified_totals_verified':True,'no_stronger_reference_checks':True,
            'preflight_connection_error':'resolved_before_generation; shared_Ollama_port_11435',
            'old_fixed_sources_overwritten':False,'diagnostic_policy_version':plan['diagnostic_policy_version'],
            'run_id':latest['run_id'],'final_successes':success,'fd_overlap':fdoverlap,'followup':latest}
    atomic_json(OUT/'sanity_report.json',sanity);atomic_json(OUT/'results_snapshot.json',sanity)
    atomic_json(OUT/'followup_manifest.json',plan);atomic_json(OUT/'followup_public_result.json',latest)
    lines=['診断修正v2の10履歴継続と固定集計',f"実験ID: {latest['run_id']}",
           f"10履歴完了。新規{len(new_rows)}要求・{latest['new_tokens']} tokens。対象履歴の成功{latest['successful_paths']}件。",
           '旧集計・raw・生成履歴は保持。再生成は最初の診断分岐以降のみ。成功時に停止。',
           f'最終成功 / 1,000: {success}',f'F/D対応: {fdoverlap}',
           '評価器は測定禁止修正版のまま。参照適合性の強い条件は主L3に加えていない。',
           '初期失敗545組の共通分母、最大3修正、初回を除く追加コストの定義は旧固定集計と同じ。',
           '新規生成で実際に消費したコストと、旧suffixを除外して再構成した全履歴のコストを区別する。',
           '後日の部分継続を含む。全件を初回から新生成した実験ではなく、同時期の無作為比較や因果効果の確定ではない。',
           '旧版との違いがない経路は保存履歴を保持。旧末尾の診断表示だけが変わる8箇所は生成を伴わない。']
    (OUT/'report.txt').write_text('\n'.join(lines)+'\n')
    inputs=dict(plan['inputs'])|{str((output/'manifest.json').relative_to(ROOT)):sha(output/'manifest.json'),
                                str((output/'public_result.json').relative_to(ROOT)):sha(output/'public_result.json')}
    for folder in (output/'private').iterdir():
        if folder.is_dir():
            for p in folder.glob('*.json'):inputs[str(p.relative_to(ROOT))]=sha(p)
    for name in ['scripts/freeze_diagnostic_policy_results.py','scripts/run_diagnostic_policy_followup.py',
                 'scripts/validate_diagnostic_policy_results.py','tests/test_diagnostic_policy_followup.py',
                 'tests/test_diagnostic_policy_result_validation.py']:
        inputs[name]=sha(ROOT/name)
    for name,h in inputs.items():
        if sha(ROOT/name)!=h:raise ValueError('source drift during freeze')
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'inputs':inputs,
              'outputs':{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='manifest.json'},
              'status':'completed_verified','old_fixed_source':str(FIXED.relative_to(ROOT)),
              'new_source':latest['output_dir'],'raw_and_generated_code_published':False,'scope':'v2 ten-path suffix replacement; unchanged paths preserved'}
    atomic_json(OUT/'manifest.json',manifest)
    print(json.dumps({'final_successes':success,'new_requests':len(new_rows),'new_tokens':latest['new_tokens'],'fd_overlap':fdoverlap},ensure_ascii=False,indent=2))
    return sanity


if __name__=='__main__':freeze()
