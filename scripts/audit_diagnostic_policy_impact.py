"""Compare frozen v1 feedback with v2 on the current reachable saved paths.

No API calls, generated-code execution, rescoring, or old-artifact writes.
Post-divergence saved outputs are hypothetical under v2, never reused as results.
"""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib,json,sqlite3
from pathlib import Path
from harness.diagnostic_policy import DIAGNOSTIC_VERSION,LEGACY_DIAGNOSTIC_VERSION,change_reason
from harness.diagnostic_prompts import build_intervention_prompt as corrected_prompt
from harness.interventions import build_intervention_prompt as legacy_prompt
from harness.reevaluation_checkpoint import digest
from scripts.measurement_ban_sources import ROOT,load_sources,code_key,sha,csv_rows
from scripts.measurement_ban_report import write_csv
from scripts.reevaluation_impact_audit import event
from scripts.reevaluation_followup_validation import read_db,validate_rows,PLAN_HASH
from tasks import get_task

DATA=ROOT/'docs/analysis/measurement_ban_corrected_20261104'
OUT=ROOT/'docs/analysis/diagnostic_policy_impact_20261104'
PRIVATE=ROOT/'.cache/diagnostic_policy_impact_20261104'
FD={'execution_feedback','self_debugging'}

def sha_text(t):return hashlib.sha256(t.encode()).hexdigest()

def classify_path(rows):
    """Only a changed, consumed prompt creates a branch requiring new generation."""
    if [r['round'] for r in rows]!=list(range(len(rows))):raise ValueError('path rounds invalid')
    branch=next((r['round']+1 for r in rows if r['prompt_changed'] and r['has_next']),None)
    return {'branch_generation_round':branch,'requires_generation':branch is not None,
            'minimum_new_requests':int(branch is not None),'maximum_new_requests':4-branch if branch else 0,
            'saved_suffix_rounds_not_reusable':len(rows)-branch if branch else 0}

def audit():
    source_manifest=json.loads((DATA/'manifest.json').read_text())
    for p,h in source_manifest['inputs'].items():
        if sha(ROOT/p)!=h:raise ValueError('fixed input changed')
    for p,h in source_manifest['outputs'].items():
        if sha(DATA/p)!=h:raise ValueError('fixed output changed')
    data=load_sources();inputs=dict(source_manifest['inputs'])
    status_path=ROOT/'docs/analysis/reevaluation_full_20261014T141718Z/run_status.json'
    status=json.loads(status_path.read_text());dbpath=Path(status['checkpoint_dir'])/'checkpoint.sqlite3'
    plan,stored=read_db(dbpath);validate_rows(plan,stored)
    if digest(plan)!=PLAN_HASH:raise ValueError('wrong evaluation checkpoint')
    primary={k:json.loads(t)['primary'] for k,_,_,t,_ in stored}
    inputs[str(dbpath.relative_to(ROOT))]=sha(dbpath)
    mdb=ROOT/'.cache/measurement_ban_impact_20261104/checkpoint.sqlite3'
    inputs[str(mdb.relative_to(ROOT))]=sha(mdb)
    with sqlite3.connect(f'file:{mdb}?mode=ro',uri=True) as db:
        revised={}
        for key,t,h in db.execute("select key,result,result_hash from results where state='completed'"):
            if sha_text(t)!=h:raise ValueError('measurement checkpoint hash drift')
            revised[key]=json.loads(t)
    inventory_path=ROOT/'docs/analysis/reevaluation_followup_20261015/saved_feedback_inventory.csv'
    inventory={r['key']:r for r in csv_rows(inventory_path)}
    source_rounds=csv_rows(DATA/'reachable_rounds.csv')
    paths=defaultdict(list)
    for r in source_rounds:
        if r['condition_id'] in FD:paths[r['record_key']].append(r)
    if len(paths)!=2000:raise ValueError('F/D path coverage changed')
    for rr in paths.values():rr.sort(key=lambda r:int(r['round']))
    suffixes={};public=[];cases=[];private=[];evidence=Counter()
    def suffix(key):
        if key not in suffixes:
            p=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key/'completed.json'
            if sha(p)!=p.with_suffix('.sha256').read_text().strip():raise ValueError('suffix hash mismatch')
            inputs[str(p.relative_to(ROOT))]=sha(p)
            suffixes[key]={a['round']:a for a in json.loads(p.read_text())['suffix']}
        return suffixes[key]
    for key,rr in sorted(paths.items()):
        compared=[]
        for i,r in enumerate(rr):
            if r['origin']=='saved_prefix':
                old=data['raw'][(r['source_dir'],r['model_spec'],r['task_id'],r['base_seed'],r['condition_id'])][i]
                code=old['extracted_code'];evdata=primary[key+':'+str(i)]
            elif r['origin']=='new_suffix':
                a=suffix(key)[i];code=a['code'];evdata=a['evaluation']['primary']
            else:raise ValueError('unrecognized origin')
            if sha_text(code)!=r['code_sha256']:raise ValueError('path code mismatch')
            check=revised.get(code_key(r['task_id'],r['code_sha256']))
            if check and check['measurement_violation']:
                evdata=check['primary']
            if evdata['L3']!=(r['new_L3']=='True'):raise ValueError('current path verdict mismatch')
            has_next=i+1<len(rr)
            if has_next and (evdata['L3'] or i>=3):raise ValueError('invalid saved continuation')
            ev=event(evdata);old_prompt=new_prompt='';verified=False;provenance='not_consumed'
            if not ev.L3:
                task=get_task(r['task_id'])
                old_prompt=legacy_prompt(r['condition_id'],task,code,ev)
                new_prompt=corrected_prompt(r['condition_id'],task,code,ev)
                if has_next:
                    nxt=rr[i+1]
                    if nxt['origin']=='new_suffix':
                        p=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key/f'round_{i+1}_request.json'
                        request=json.loads(p.read_text())['request']
                        if request['user']!=old_prompt or suffix(key)[i+1]['input_prompt_sha256']!=sha_text(old_prompt):
                            raise ValueError('actual suffix request differs from v1 reconstruction: '+key+':'+str(i))
                        if request['system']!=__import__('harness.llm_clients',fromlist=['SYSTEM_PROMPT']).SYSTEM_PROMPT:
                            raise ValueError('system drift')
                        inputs[str(p.relative_to(ROOT))]=sha(p)
                        provenance='captured_suffix_request'
                    else:
                        inv=inventory[key+':'+str(i)]
                        if inv['old_feedback_actually_consumed']!='True' or inv['old_consumed_prompt_reconstructed_sha256']!=sha_text(old_prompt):
                            raise ValueError('historical saved request differs from v1 reconstruction: '+key+':'+str(i))
                        provenance='archived_function_and_original_values_verified_hash; not_packet_capture'
                    verified=True;evidence[provenance]+=1
            changed=old_prompt!=new_prompt
            row={k:r[k] for k in ['record_key','source_dir','model_spec','task_id','base_seed','condition_id','origin','code_sha256']}
            row.update(round=i,L0=ev.L0,L1=ev.L1,L2=ev.L2,L3=ev.L3,structure_match=ev.structure_match,
                error_category=ev.error_category,L2_distance=ev.L2_distance if __import__('math').isfinite(ev.L2_distance) else '',
                has_next=has_next,prompt_changed=changed,change_reason=change_reason(ev),
                old_prompt_sha256=sha_text(old_prompt) if old_prompt else '',new_prompt_sha256=sha_text(new_prompt) if new_prompt else '',
                actual_old_prompt_verified=verified,old_prompt_evidence=provenance)
            compared.append(row)
            if changed:private.append({'record_key':key,'round':i,'before':old_prompt,'after_on_same_saved_output':new_prompt})
        impact=classify_path(compared);branch=impact['branch_generation_round']
        for row in compared:
            row['after_first_divergence']=branch is not None and row['round']>=branch
            public.append(row)
        cases.append({k:rr[0][k] for k in ['record_key','source_dir','model_spec','task_id','base_seed','condition_id']}|impact|
            {'old_final_success':rr[-1]['new_L3']=='True','old_stop_round':int(rr[-1]['round']),
             'branch_reason':compared[branch-1]['change_reason'] if branch else '',
             'saved_success_not_a_v2_result':branch is not None and rr[-1]['new_L3']=='True'})
    if len(public)!=4748 or sum(r['has_next'] for r in public)!=2748 or sum(evidence.values())!=2748:
        raise ValueError('consumed-feedback coverage changed')
    summary=[]
    for c,old_success in [('execution_feedback',638),('self_debugging',634)]:
        cc=[r for r in cases if r['condition_id']==c];affected=[r for r in cc if r['requires_generation']]
        if sum(r['old_final_success'] for r in cc)!=old_success:raise ValueError('historical success count drift')
        old_affected_successes=sum(r['old_final_success'] for r in affected)
        summary.append({'condition_id':c,'paths':len(cc),'affected_paths':len(affected),
            'affected_initial_groups':len({(r['model_spec'],r['task_id'],r['base_seed']) for r in affected}),
            'minimum_new_requests':len(affected),'maximum_new_requests':sum(r['maximum_new_requests'] for r in affected),
            'historical_final_successes':old_success,'historical_successes_on_affected_paths':old_affected_successes,
            'unchanged_path_successes':old_success-old_affected_successes,
            'possible_v2_successes_lower':old_success-old_affected_successes,
            'possible_v2_successes_upper':old_success-old_affected_successes+len(affected)})
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    affected=[r for r in cases if r['requires_generation']]
    for n,rows in [('round_diagnostic_comparison',public),('path_impacts',cases),('pending_generation',affected),('condition_summary',summary)]:write_csv(OUT/(n+'.csv'),rows)
    # These bodies contain saved generated code and remain private.
    (PRIVATE/'changed_prompts.json').write_text(json.dumps(private,ensure_ascii=False,indent=2)+'\n')
    for p in [DATA/'manifest.json',DATA/'reachable_rounds.csv',inventory_path,status_path,ROOT/'scripts/audit_diagnostic_policy_impact.py',ROOT/'harness/diagnostic_policy.py',ROOT/'harness/diagnostic_prompts.py']:
        inputs[str(p.relative_to(ROOT))]=sha(p)
    for p,h in inputs.items():
        if sha(ROOT/p)!=h:raise ValueError('source changed during audit')
    status={'status':'verified_impact_only','new_diagnostic_version':DIAGNOSTIC_VERSION,'old_diagnostic_version':LEGACY_DIAGNOSTIC_VERSION,
        'reachable_FD_paths':2000,'reachable_FD_rounds':len(public),'consumed_feedback_inputs_verified':sum(evidence.values()),
        'prompt_evidence':dict(evidence),'changed_saved_output_diagnostics':sum(r['prompt_changed'] for r in public),
        'diagnostic_change_reasons':dict(Counter(r['change_reason'] for r in public if r['prompt_changed'])),
        'changed_actually_consumed_prompts':sum(r['prompt_changed'] and r['has_next'] for r in public),
        'changed_terminal_diagnostics_without_generation_effect':sum(r['prompt_changed'] and not r['has_next'] for r in public),
        'affected_paths':len(affected),'affected_unique_initial_groups':len({(r['model_spec'],r['task_id'],r['base_seed']) for r in affected}),
        'minimum_new_requests':len(affected),'maximum_new_requests':sum(r['maximum_new_requests'] for r in affected),
        'old_saved_suffix_rounds_not_reusable_as_v2':sum(r['saved_suffix_rounds_not_reusable'] for r in affected),
        'conditions':summary,'new_model_requests':0,'generated_code_executions':0,'rescoring':False,'evaluator_changed':False,
        'historical_sources_unchanged':True,'old_success_counts_preserved':True,'v2_final_success_counts':'not_observed',
        'initial_B_R_P_B4_unchanged':True,'runtime_or_reconstruction_failures':0,
        'scope':'Current measurement-corrected reachable paths only. Removed original suffixes are excluded. Changed diagnostics after the first branch are hypothetical on old outputs, not v2 trajectories.'}
    (OUT/'summary.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    report=['診断修正v2の後続生成への影響調査（新規生成なし）',
        '評価器と合否は変更していない。旧固定集計・raw・生成履歴を保持した。',
        f"F/Dの{len(public)}到達round・2,000経路を調べ、後続に渡った2,748要求を旧診断で照合した。",
        f"診断差分{status['changed_saved_output_diagnostics']}箇所、うち後続に渡った差分{status['changed_actually_consumed_prompts']}箇所。",
        f"最初の分岐を持つ{len(affected)}条件経路・{status['affected_unique_initial_groups']}初期組で継続生成が必要となる。",
        f"追加要求の必要範囲は最少{len(affected)}〜最大{status['maximum_new_requests']}。今回は0要求。",
        '分岐後の旧コードを修正版診断で生成された結果と扱わない。v2の成功数は未観測。']
    for r in summary:report.append(str(r))
    (OUT/'report.txt').write_text('\n'.join(report)+'\n')
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'inputs':inputs,'outputs':{p.name:sha(p) for p in OUT.iterdir() if p.name not in ['manifest.json','sanity_report.json']},'policy':status}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (OUT/'sanity_report.json').write_text(json.dumps({'passed':True,'missing':0,'duplicates':0,'unverified_consumed_prompts':0,'source_hashes_verified':True,**status},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(status,ensure_ascii=False,indent=2))
    return status

if __name__=='__main__':audit()
