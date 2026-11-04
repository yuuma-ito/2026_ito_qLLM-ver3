"""Read-only current v2 evidence and pre-generation stagnation refresh."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3

from harness.independent_4 import read_checkpoint,code_hash,digest,levels
from scripts.measurement_ban_sources import ROOT,load_sources,csv_rows,sha,code_key
from scripts.measurement_ban_report import write_csv
from scripts.reevaluation_followup_validation import read_db,validate_rows

CURRENT=ROOT/'docs/analysis/diagnostic_policy_corrected_20261104'
MEASURED=ROOT/'docs/analysis/measurement_ban_corrected_20261104'
OLD_GAP=ROOT/'docs/analysis/b4_observed_gap_20261104'


def load_current():
    pinned=json.loads((CURRENT/'manifest.json').read_text())
    inputs=dict(pinned['inputs'])
    for name,h in inputs.items():
        if sha(ROOT/name)!=h:raise ValueError('current source changed: '+name)
    for name,h in pinned['outputs'].items():
        if sha(CURRENT/name)!=h:raise ValueError('current aggregate changed: '+name)
        inputs[str((CURRENT/name).relative_to(ROOT))]=h
    inputs[str((CURRENT/'manifest.json').relative_to(ROOT))]=sha(CURRENT/'manifest.json')
    data=load_sources()
    status=json.loads((ROOT/'docs/analysis/reevaluation_full_20261014T141718Z/run_status.json').read_text())
    plan,stored=read_db(Path(status['checkpoint_dir'])/'checkpoint.sqlite3');validate_rows(plan,stored)
    primary={key:json.loads(t)['primary'] for key,_,_,t,_ in stored}
    mdb=ROOT/'.cache/measurement_ban_impact_20261104/checkpoint.sqlite3'
    with sqlite3.connect(f'file:{mdb}?mode=ro',uri=True) as db:
        revised={}
        for key,t,h in db.execute("select key,result,result_hash from results where state='completed'"):
            if code_hash(t)!=h:raise ValueError('measurement result hash mismatch')
            revised[key]=json.loads(t)
    v2public=json.loads((CURRENT/'followup_public_result.json').read_text())
    v2dir=ROOT/v2public['output_dir'];v2cases=read_checkpoint(v2dir/'manifest.json')['cases']
    v2={c['record_key']:read_checkpoint(v2dir/'private'/c['record_key']/'completed.json') for c in v2cases}
    suffixes={};histories=defaultdict(list);metadata={}
    labels={'baseline':'initial','self_refine':'R','execution_feedback':'F','self_debugging':'D','preventive_spec':'P'}
    for r in csv_rows(CURRENT/'reachable_rounds.csv'):
        key=r['record_key'];index=int(r['round']);ident=(r['model_spec'],r['task_id'],int(r['base_seed']))
        if r['origin']=='saved_prefix':
            a=data['raw'][(r['source_dir'],r['model_spec'],r['task_id'],r['base_seed'],r['condition_id'])][index]
            code=a['extracted_code'];ev=primary[key+':'+str(index)];finish=None
        elif r['origin']=='new_suffix':
            if key not in suffixes:
                folder=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key
                p=folder/'completed.json'
                if sha(p)!=p.with_suffix('.sha256').read_text().strip():raise ValueError('old suffix damaged')
                suffixes[key]={a['round']:a for a in json.loads(p.read_text())['suffix']}
            a=suffixes[key][index];code=a['code'];ev=a['evaluation']['primary']
            response=json.loads((ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key/f'round_{index}_response.json').read_text())
            finish=response.get('response',{}).get('choices',[{}])[0].get('finish_reason')
        elif r['origin']=='diagnostic_v2_suffix':
            a=v2[key]['rounds'][index];code=a['extracted_code'];ev=a['primary'];finish=a.get('finish_reason')
        else:raise ValueError('unknown current provenance')
        if code_hash(code)!=r['code_sha256']:raise ValueError('current code hash mismatch')
        check=revised.get(code_key(r['task_id'],r['code_sha256']))
        if check and check['measurement_violation']:ev=check['primary']
        if ev['L3']!=(r['new_L3']=='True'):raise ValueError('current verdict mismatch')
        levels(ev)
        attempt={'round':index,'code':code,'hash':r['code_sha256'],'primary':ev,
                 'error':ev['error_category'],'success':ev['L3'],'tokens_in':int(r['tokens_in']),
                 'tokens_out':int(r['tokens_out']),'finish':finish}
        histories[(*ident,labels[r['condition_id']])].append(attempt)
        if r['condition_id']=='baseline':
            metadata[ident]={'model_spec':ident[0],'task_id':ident[1],'base_seed':ident[2],
                             'source_dir':r['source_dir'],'baseline_record_key':key,
                             'task_difficulty':r['task_difficulty']}
    b4follow=read_checkpoint(ROOT/json.loads((MEASURED/'followup_public_result.json').read_text())['output_dir']/'private/completed.json')
    repeat={(r['model_spec'],r['task_id'],int(r['base_seed']),int(r['round'])):r for r in csv_rows(MEASURED/'repetitions.csv')}
    for row in data['B4_records']:
        ident=(row['model_spec'],row['task_id'],row['base_seed'])
        rr=b4follow['rounds'] if row['baseline_record_key']==b4follow['baseline_record_key'] else row['rounds']
        for a in rr:
            i=a['round'];ev=deepcopy(a['primary'])
            check=revised.get(code_key(row['task_id'],a['code_sha256']))
            if check and check['measurement_violation']:ev=check['primary']
            if i and ev['L3']!=(repeat[(*ident,i)]['L3']=='True'):raise ValueError('B4 verdict mismatch')
            if code_hash(a['extracted_code'])!=a['code_sha256']:raise ValueError('B4 code mismatch')
            histories[(*ident,'B4')].append({'round':i,'code':a['extracted_code'],'hash':a['code_sha256'],
                'primary':ev,'error':ev['error_category'],'success':ev['L3'],'tokens_in':a['tokens_in'],
                'tokens_out':a['tokens_out'],'finish':a.get('finish_reason') if i else None})
    for rr in histories.values():
        rr.sort(key=lambda r:r['round'])
        if [a['round'] for a in rr]!=list(range(len(rr))) or any(a['success'] for a in rr[:-1]):
            raise ValueError('unreachable current trajectory')
    cases=[]
    for ident,m in sorted(metadata.items()):
        initial=histories[(*ident,'initial')][0]
        for label in ['R','F','D','B4']:
            other=histories[(*ident,label)][0]
            if initial['hash']!=other['hash'] or initial['success']!=other['success']:
                raise ValueError('initial is not shared')
        if initial['success']:continue
        case=dict(m,initial=initial,initial_error=initial['error'],case_id=digest(list(ident)))
        f=histories[(*ident,'F')][-1]['success'];b=histories[(*ident,'B4')][-1]['success']
        case['historical_outcome']='both' if f and b else 'F_only' if f else 'B4_only' if b else 'neither'
        cases.append(case)
    if len(cases)!=545 or len(metadata)!=1000:raise ValueError('current initial cohort mismatch')
    settings=json.loads((ROOT/'docs/analysis/reevaluation_followup_20261015/settings_manifest.json').read_text())
    digests={}
    for s in settings['sources']:
        for model,h in s['model_digests'].items():
            if model in digests and digests[model]!=h:raise ValueError('model identity differs by source')
            digests[model]=h
    if len(digests)!=5:raise ValueError('five frozen models required')
    return cases,dict(histories),{'inputs':inputs,'model_digests':digests}


def refresh_stagnation(output,cases,histories,evidence):
    """Never invoke the old scripts' main functions (which write old folders)."""
    from scripts.analyze_b4_observed_gap import analyze
    identities={(c['model_spec'],c['task_id'],c['base_seed']) for c in cases}
    paths={k:v for k,v in histories.items() if k[:-1] in identities and k[-1] in ['R','F','D','B4']}
    features,attempts,matched,strata,byoutcome=analyze(paths)
    old={tuple(str(r[k]) for k in ['model_spec','task_id','base_seed','condition']):r for r in csv_rows(OLD_GAP/'case_features.csv')}
    changed=[];totals=[]
    fields=['success','stop_round','additional_requests','tokens_in','tokens_out','has_exact_repeat','has_ast_repeat','all_rounds_same_ast','all_rounds_same_error','known_finish_requests']
    for r in features:
        key=tuple(str(r[k]) for k in ['model_spec','task_id','base_seed','condition']);before=old[key]
        for name in fields:
            if str(r[name])!=before[name]:changed.append({k:r[k] for k in ['model_spec','task_id','base_seed','condition']}|{'metric':name,'old_v1':before[name],'current_v2':r[name]})
    for label in ['R','F','D','B4']:
        rr=[r for r in features if r['condition']==label]
        totals.append({'condition':label,'initial_failures':len(rr),'successes':sum(r['success'] for r in rr),
                       'any_ast_repeat':sum(r['has_ast_repeat'] for r in rr),'unchanged_ast_all_rounds':sum(r['all_rounds_same_ast'] for r in rr),
                       'additional_requests':sum(r['additional_requests'] for r in rr),'finish_reason_known':sum(r['known_finish_requests'] for r in rr)})
    if {r['condition']:r['successes'] for r in totals}!={'R':96,'F':186,'D':179,'B4':216}:raise ValueError('v2 totals mismatch')
    output.mkdir(parents=True,exist_ok=False)
    for name,rr in [('case_features',features),('attempt_features',attempts),('matched_outcomes',matched),('gap_by_stratum',strata),('features_by_outcome',byoutcome),('old_v1_to_current_v2',changed),('overall_stagnation',totals)]:write_csv(output/(name+'.csv'),rr)
    report=['診断v2保存履歴による停滞分析の更新（新規生成前）',
            '旧分析は測定禁止修正後・旧診断版。今回は診断v2の10履歴・23新出力を反映し、分岐後の旧26出力を除外した。',
            '保存コードは文字列とASTとしてのみ解析し、生成コードの実行・再採点・モデル要求は0。AST一致は意味的同値性ではない。',
            *[str(r) for r in totals],f'旧分析から変わった指標行: {len(changed)}',
            '既存の成否群は抽出後の包含確認にのみ用いる。停滞特徴から因果関係は確定しない。',
            '旧prefixの終了理由は未記録を維持する。既知suffixだけの終了理由を全体の打切り率に拡張しない。']
    (output/'report.txt').write_text('\n'.join(report)+'\n')
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'new_model_requests':0,'generated_code_executions':0,
              'inputs':evidence['inputs']|{str((OLD_GAP/'case_features.csv').relative_to(ROOT)):sha(OLD_GAP/'case_features.csv')},
              'implementation':{f:sha(ROOT/f) for f in ['scripts/factorial_pilot_sources.py','scripts/analyze_b4_observed_gap.py']},
              'outputs':{p.name:sha(p) for p in output.iterdir()},'status':'verified_current_v2_descriptive_only'}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return totals
