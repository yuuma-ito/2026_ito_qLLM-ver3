"""Freeze corrected six-condition results after the authorized single B4 continuation.

Reads old evidence and new checkpoints; no model calls or generated-code execution.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path

from harness.independent_4 import read_checkpoint,code_hash
from harness.run_state import atomic_json
from scripts import analyze_verified_rescues as base
from scripts.analyze_reachable_rescue_history import cost_summary,static_delta,PATTERNS
from scripts.analyze_independent_4 import analyze
from scripts.measurement_ban_sources import ROOT,load_sources,code_key,sha
from scripts.measurement_ban_report import write_csv

OUT=ROOT/'docs/analysis/measurement_ban_corrected_20261104'


def freeze():
    latest=json.loads((ROOT/'.cache/measurement_ban_followup_latest.json').read_text())
    if latest['status']!='completed_verified':raise ValueError('followup not verified')
    followdir=ROOT/latest['output_dir']
    follow=read_checkpoint(followdir/'private/completed.json')
    plan=read_checkpoint(followdir/'manifest.json')
    if follow['new_requests'] not in [1,2] or not plan['no_stronger_reference_checks']:
        raise ValueError('followup scope changed')
    data=load_sources()
    impact=json.loads((ROOT/'docs/analysis/measurement_ban_impact_20261104/manifest.json').read_text())
    import sqlite3
    with sqlite3.connect(f"file:{ROOT/'.cache/measurement_ban_impact_20261104/checkpoint.sqlite3'}?mode=ro",uri=True) as db:
        evaluations={}
        for key,text,hashed in db.execute("select key,result,result_hash from results where state='completed'"):
            if hashlib.sha256(text.encode()).hexdigest()!=hashed:raise ValueError('impact result hash mismatch')
            evaluations[key]=json.loads(text)
    if len(evaluations)!=1561:raise ValueError('impact incomplete')
    def revision(e,task,hashed):
        r=deepcopy(e)
        if base.truth(e['new_L3']):
            primary=evaluations[code_key(task,hashed)]['primary']
            for key in ['L0','L1','L2','L3','structure_match']:
                r['new_'+key]=str(primary[key])
            for key in ['error_category','failure_stage','exception_type']:
                r['new_'+key]=primary.get(key,'')
        return r
    reach={(r['record_key'],int(r['round'])):r for r in data['reachable']}
    paths={};mixed=deepcopy(data['mixed'])
    for r in mixed:
        key=r['record_key']
        paths[key]=[revision(e,r['task_id'],reach[(key,i)]['code_sha256']) for i,e in enumerate(data['paths'][key])]
        r['success_old_v4']=r['success'];r['success']=str(base.truth(paths[key][-1]['new_L3']))
    difficulties={r['task_id']:r['task_difficulty'] for r in data['reachable']}
    ledger,all_summaries,overlaps,fd=base.analyze(mixed,paths,difficulties)
    meta={r['record_key']:r for r in ledger}
    rounds=[];codes={};suffixes={}
    for m in mixed:
        key=m['record_key']
        for i,e in enumerate(paths[key]):
            old=reach[(key,i)]
            r=dict(old)
            r.update(meta.get(key,{}))
            r['new_L3']=base.truth(e['new_L3']);r['new_error_category']=e['new_error_category']
            for field in ['round','tokens_in','tokens_out','tokens']:r[field]=int(r[field])
            r['generation_seconds']=float(r['generation_seconds'])
            rounds.append(r)
            if i<data['branches'].get(key,4):code=data['raw'][base.identity(m)][i]['extracted_code']
            else:
                if key not in suffixes:
                    p=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key/'completed.json'
                    suffixes[key]={a['round']:a['code'] for a in json.loads(p.read_text())['suffix']}
                code=suffixes[key][i]
            if code_hash(code)!=r['code_sha256']:raise ValueError('reachable code hash mismatch')
            codes[(key,i)]=code
    costs=cost_summary(ledger,rounds)
    b4_records=deepcopy(data['B4_records']);cases=[];references={}
    labels={'self_refine':'R','execution_feedback':'F','self_debugging':'D','preventive_spec':'P'}
    bygroup=defaultdict(dict)
    for r in ledger:bygroup[(r['model_spec'],r['task_id'],r['base_seed'])][r['condition_id']]=r
    for b4 in b4_records:
        initial=deepcopy(b4['rounds'][0])
        key=(b4['model_spec'],b4['task_id'],b4['base_seed'])
        cases.append({k:b4[k] for k in ['model_spec','task_id','base_seed','source_dir','baseline_record_key','task_difficulty']}|{'initial':initial})
        if b4['baseline_record_key']==follow['baseline_record_key']:
            b4['rounds']=deepcopy(follow['rounds'])
        else:
            for a in b4['rounds']:
                if a['primary']['L3']:
                    checked=evaluations[code_key(b4['task_id'],a['code_sha256'])]
                    if checked['measurement_violation']:
                        a['primary']=deepcopy(checked['primary'])
        if any(b4['rounds'][0].get(k)!=v for k,v in initial.items()):
            raise ValueError('shared initial values changed')
        cases[-1]['initial']=deepcopy(b4['rounds'][0])  # Additional provenance annotation only.
        for i,a in enumerate(b4['rounds']):
            if i:a['repeated_code']=any(p['code_sha256']==a['code_sha256'] for p in b4['rounds'][:i])
        b4['final_success']=b4['rounds'][-1]['primary']['L3']
        b4['first_success_round']=next((a['round'] for a in b4['rounds'] if a['primary']['L3']),None)
        b4['first_success_generation']=None if b4['first_success_round'] is None else b4['first_success_round']+1
        references[key]={}
        for condition,r in bygroup[key].items():
            pp=[]
            for i,e in enumerate(paths[r['record_key']]):
                cost=reach[(r['record_key'],i)]
                primary={k:base.truth(e['new_'+k]) for k in ['L0','L1','L2','L3','structure_match']}
                primary.update(failure_stage=e['new_failure_stage'],error_category=e['new_error_category'])
                pp.append({'round':i,'primary':primary,'code_sha256':cost['code_sha256'],
                           'tokens_in':int(cost['tokens_in']),'tokens_out':int(cost['tokens_out']),
                           'generation_seconds':float(cost['generation_seconds']),'evaluation_seconds':None})
            references[key][labels[condition]]=pp
    config=json.loads((ROOT/'docs/analysis/independent_4_completed_20261022/runner_experiment_config.json').read_text())
    combined=analyze(b4_records,cases,references,config)
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'core').mkdir(exist_ok=True)
    atomic_json(OUT/'followup_manifest.json',plan)
    atomic_json(OUT/'followup_public_result.json',latest)
    for name,rows in [('paired_records',ledger),('repair_summary',[r for r in all_summaries if r['condition_id'] in base.REPAIRS]),
                      ('preventive_summary',[r for r in all_summaries if r['condition_id']==base.P]),
                      ('fd_overlap_records',overlaps),('fd_overlap_summary',fd)]:write_csv(OUT/'core'/(name+'.csv'),rows)
    for name in ['summary','overlap','pairwise','first_success','repetitions']:write_csv(OUT/(name+'.csv'),combined[name])
    write_csv(OUT/'reachable_rounds.csv',rounds);write_csv(OUT/'cost_by_cap_and_stratum.csv',costs)
    third=[]
    keys=['scope','source_dir','grouping','condition_id']
    for r in costs:
        if r['cap']!=3:continue
        prior=next(p for p in costs if p['cap']==2 and all(p.get(k,'')==r.get(k,'') for k in keys+list(base.GROUPINGS[r['grouping']])))
        added=r['rescued']-prior['rescued']
        third.append(dict(r,additional_rescues=added,at_risk_after_2=r['initial_failures']-prior['rescued'],
                          third_round_requests=r['generation_requests']-prior['generation_requests'],
                          third_round_tokens=r['tokens']-prior['tokens'],third_round_seconds=r['generation_seconds']-prior['generation_seconds'],
                          loss_if_stop_at_2=added/r['rescued'] if r['rescued'] else ''))
    write_csv(OUT/'third_round_summary.csv',third)
    dcases=[];transitions=[]
    rowmap={r['record_key']:r for r in ledger}
    for group in overlaps:
        if group['cohort'] not in ['F_only','D_only']:continue
        rr=bygroup[(group['model_spec'],group['task_id'],group['base_seed'])]
        for condition in ['execution_feedback','self_debugging']:
            r=rr[condition];key=r['record_key'];history=[a for a in rounds if a['record_key']==key]
            flags=Counter()
            for prev,cur in zip(history,history[1:]):
                delta=static_delta(codes[(key,prev['round'])],codes[(key,cur['round'])])
                flags.update(k for k,v in delta.items() if k.startswith('changed_') and isinstance(v,bool) and v)
                transitions.append(dict(r,cohort=group['cohort'],from_round=prev['round'],to_round=cur['round'],
                    from_code_sha256=prev['code_sha256'],to_code_sha256=cur['code_sha256'],from_origin=prev['origin'],to_origin=cur['origin'],
                    from_error=prev['new_error_category'],to_error=cur['new_error_category'],to_L3=cur['new_L3'],**delta))
            dcases.append(dict(r,cohort=group['cohort'],reachable_rounds=len(history),initial_code_sha256=history[0]['code_sha256'],
                final_code_sha256=history[-1]['code_sha256'],error_path=' > '.join(a['new_error_category'] for a in history),
                origins=' > '.join(a['origin'] for a in history),**{'any_changed_'+k:bool(flags['changed_'+k]) for k in PATTERNS}))
    write_csv(OUT/'discordant_cases.csv',dcases);write_csv(OUT/'discordant_transitions.csv',transitions)
    ds=[]
    ndiscordant=len(dcases)//2
    for grouping,fields in base.GROUPINGS.items():
        groups=defaultdict(list)
        for r in dcases:groups[(tuple(r[k] for k in fields),r['cohort'],r['condition_id'])].append(r)
        for (values,cohort,condition),rr in sorted(groups.items()):
            ds.append(dict(grouping=grouping,**dict(zip(fields,values)),cohort=cohort,condition_id=condition,pairs=len(rr),
                           all_discordant_pairs=ndiscordant,share_of_discordant_pairs=len(rr)/ndiscordant,rescued=sum(r['rescued'] for r in rr),
                           **{'pairs_with_'+k:sum(r['any_changed_'+k] for r in rr) for k in PATTERNS}))
    write_csv(OUT/'discordant_summary.csv',ds)
    now=datetime.now(timezone.utc).isoformat()
    primary={'captured_at_utc':now,'status':'verified','primary_metric':'rescued / baseline_initial_failures',
             'condition_records':5000,'initial_groups':1000,'evaluator':plan['evaluator']['primary_version'],
             'source_plan_sha256':plan['plan_sha256'],'path_scope':'preserved prefixes + old partial suffixes + measurement-only revision; B4 single continuation separately recorded',
             'overall':[r for r in all_summaries if r['scope']=='pooled' and r['grouping']=='overall'],
             'fd_overlap':next(r for r in fd if r['scope']=='pooled' and r['grouping']=='overall')}
    snapshot={'captured_at_utc':now,'status':'verified','primary':primary,'discordant_pairs':ndiscordant,
              'discordant_condition_paths':len(dcases),'discordant_transitions':len(transitions),
              'overall_costs':[r for r in costs if r['scope']=='pooled' and r['grouping']=='overall'],
              'third_round':[r for r in third if r['scope']=='pooled' and r['grouping']=='overall'],
              'monetary_cost':'not_measured','cost_scope':'reconstructed historical costs plus actually measured single B4 continuation',
              'static_scope':'lexical differences only; not causal','followup':latest,'pending_paths':0}
    atomic_json(OUT/'core/results_snapshot.json',primary);atomic_json(OUT/'results_snapshot.json',snapshot)
    if not combined['sanity']['passed'] or len(ledger)!=4000 or len(bygroup)!=1000:
        raise ValueError('corrected paired history incomplete')
    for path in paths.values():
        if any(base.truth(e['new_L3']) for e in path[:-1]):
            raise ValueError('history continues after revised success')
    if not follow['final_success'] and follow['final_round']!=3:
        raise ValueError('followup still requires generation')
    sanity={**combined['sanity'],'passed':True,'condition_records':5000,'initial_groups':1000,
            'reachable_rounds':len(rounds),'discordant_pairs':ndiscordant,'discordant_transition_count':len(transitions),
            'pending_paths':0,'new_model_requests':follow['new_requests'],'historical_inputs_unchanged':True,
            'reference_conformance_used':False,'unresolved_runtime_failures':0}
    for p in [OUT/'sanity_report.json',OUT/'core/sanity_report.json',OUT/'validation_report.json']:atomic_json(p,sanity)
    for name in ['runner_manifest.json','runner_experiment_config.json']:
        (OUT/name).write_bytes((ROOT/'docs/analysis/independent_4_completed_20261022'/name).read_bytes())
    for name in ['case_studies.json','experiment_prompts.json']:(OUT/name).write_bytes((ROOT/'docs/graduation2026'/name).read_bytes())
    catalog=[]
    for key,label in [('import_error','import失敗'),('build_error','回路構築失敗'),('wrong_output','出力不一致')]:
        rr={r['condition']:r for r in combined['summary'] if r['grouping']=='initial_failure' and r['group']==key and r['generation_cap']==4}
        catalog.append({'initial_failure':key,'label':label,'initial_failures':rr['F']['initial_failures'],
                        **{c+'_successes':rr[c]['successes_from_initial_failure'] for c in ['F','D','B4']},
                        **{c+'_rate_percent':f"{100*rr[c]['success_from_initial_failure_rate']:.1f}" for c in ['F','D','B4']}})
    write_csv(OUT/'intervention_catalog.csv',catalog)
    for name,expected in data['inputs'].items():
        if sha(ROOT/name)!=expected:raise ValueError('old source changed')
    settings=json.loads((ROOT/'docs/analysis/reevaluation_followup_20261015/settings_manifest.json').read_text())
    recheck_sources=[ROOT/'docs/analysis/measurement_ban_impact_20261104'/n for n in ['manifest.json','code_rechecks.csv','path_impacts.csv']]
    recheck_sources.append(ROOT/'.cache/measurement_ban_impact_20261104/checkpoint.sqlite3')
    manifest={'captured_at_utc':now,'evaluator_version':plan['evaluator']['primary_version'],'source_settings':settings['sources'],
              'inputs':{**data['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in recheck_sources},str((followdir/'private/completed.json').relative_to(ROOT)):sha(followdir/'private/completed.json')},
              'followup':latest,'prior_fixed_sources_preserved':True,'no_stronger_reference_checks':True,
              'outputs':{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in ['manifest.json','source_manifest.json']}}
    atomic_json(OUT/'manifest.json',manifest);atomic_json(OUT/'source_manifest.json',manifest)
    total=[r for r in combined['summary'] if r['grouping']=='overall' and r['generation_cap'] in [1,4]]
    report=['測定禁止修正版：追試完了後の固定集計','旧固定集計と生成履歴は上書きしていない。',
            f"B4の1経路を元設定・元seed規則で継続：追加{follow['new_requests']}要求、最終L3成功={follow['final_success']}。",
            f'片側救済{ndiscordant}組、両条件{len(dcases)}履歴、静的差分{len(transitions)}遷移。',
            '主L3は指定入力・元の構造要件と共通systemの回路内測定禁止。原課題より強い参照適合性検査は使用しない。']
    for r in total:report.append(f"{r['condition']} cap={r['generation_cap']}: {r['final_L3_successes']}/1000, added={r['successes_from_initial_failure']}/545, tokens={r['additional_tokens']}")
    (OUT/'report.txt').write_text('\n'.join(report)+'\n')
    # Include the final textual report in the manifest.
    for p in [OUT/'manifest.json',OUT/'source_manifest.json']:
        obj=json.loads(p.read_text());obj['outputs']['report.txt']=sha(OUT/'report.txt');atomic_json(p,obj)
    print(json.dumps({'output':str(OUT),'followup':latest,'primary':primary,'discordant_pairs':ndiscordant},ensure_ascii=False,indent=2))


if __name__=='__main__':freeze()
