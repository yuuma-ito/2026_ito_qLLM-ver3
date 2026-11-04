"""Independently reconcile public v2 trajectories, counts and costs; no generation."""
from collections import Counter,defaultdict
import json
import math

from scripts.measurement_ban_sources import ROOT,csv_rows,sha
from scripts.freeze_diagnostic_policy_results import OUT,FIXED,IMPACT


def verify_summary(rounds,paired,summary):
    paths=defaultdict(list)
    for r in rounds:paths[r['record_key']].append(r)
    for pp in paths.values():
        pp.sort(key=lambda r:int(r['round']))
        if [int(r['round']) for r in pp]!=list(range(len(pp))):raise ValueError('missing/duplicate round')
        if any(r['new_L3']=='True' for r in pp[:-1]):raise ValueError('continued after success')
    if len(paths)!=5000 or Counter(p[0]['condition_id'] for p in paths.values())!={c:1000 for c in ['baseline','preventive_spec','self_refine','execution_feedback','self_debugging']}:
        raise ValueError('five-condition trajectory coverage mismatch')
    baseline={}
    for pp in paths.values():
        r=pp[0]
        if r['condition_id']=='baseline':baseline[r['model_spec'],r['task_id'],r['base_seed']]=r
    if len(baseline)!=1000 or sum(r['new_L3']=='True' for r in baseline.values())!=455:
        raise ValueError('initial cohort mismatch')
    ledger={r['record_key']:r for r in paired}
    if len(ledger)!=4000 or len(paired)!=4000:raise ValueError('paired ledger coverage mismatch')
    labels={'B':'baseline','P':'preventive_spec','R':'self_refine','F':'execution_feedback','D':'self_debugging'}
    for key,m in ledger.items():
        pp=paths[key];first=pp[0];last=pp[-1]
        initial=baseline[first['model_spec'],first['task_id'],first['base_seed']]
        if m['final_success']!=last['new_L3'] or int(m['stop_round'])!=int(last['round']):raise ValueError('ledger outcome mismatch')
        if m['initial_success']!=initial['new_L3']:raise ValueError('ledger initial mismatch')
        if first['condition_id']!='preventive_spec' and (first['code_sha256']!=initial['code_sha256'] or first['new_L3']!=initial['new_L3']):
            raise ValueError('shared initial mismatch')
    for row in summary:
        if row['condition']=='B4':continue
        selected=[]
        for key,pp in paths.items():
            first=pp[0]
            if first['condition_id']!=labels[row['condition']]:continue
            group=row['grouping'];value=row['group']
            field={'model':'model_spec','task':'task_id','difficulty':'task_difficulty','initial_failure':'baseline_error_category'}.get(group)
            if field and first[field]!=value:continue
            selected.append(pp)
        metrics=Counter()
        for pp in selected:
            first=pp[0];initial=baseline[first['model_spec'],first['task_id'],first['base_seed']]
            chosen=pp[:int(row['generation_cap'])];success=any(r['new_L3']=='True' for r in chosen);failed=initial['new_L3']!='True'
            extra=chosen if row['condition']=='P' else chosen[1:] if row['condition']!='B' else []
            metrics.update(groups=1,initial_failures=int(failed),final_L3_successes=int(success),successes_from_initial_failure=int(failed and success),regressed=int(not failed and not success),total_generation_opportunities=len(chosen),additional_requests=len(extra),additional_tokens=sum(int(r['tokens_in'])+int(r['tokens_out']) for r in extra),additional_generation_seconds=sum(float(r['generation_seconds']) for r in extra))
        for name,value in metrics.items():
            if not math.isclose(float(row[name]),value,rel_tol=1e-10,abs_tol=1e-6):
                raise ValueError('summary metric mismatch: '+str((row['condition'],row['generation_cap'],row['grouping'],row['group'],name)))
    return paths


def validate():
    manifest=json.loads((OUT/'manifest.json').read_text())
    for name,h in manifest['inputs'].items():
        if sha(ROOT/name)!=h:raise ValueError('input hash mismatch: '+name)
    for name,h in manifest['outputs'].items():
        if sha(OUT/name)!=h:raise ValueError('output hash mismatch: '+name)
    rounds=csv_rows(OUT/'reachable_rounds.csv');paired=csv_rows(OUT/'core/paired_records.csv');summary=csv_rows(OUT/'summary.csv')
    paths=verify_summary(rounds,paired,summary)
    pending={r['record_key']:r for r in csv_rows(IMPACT/'pending_generation.csv')}
    comparisons=csv_rows(OUT/'path_comparison.csv')
    if len(comparisons)!=10 or {r['record_key'] for r in comparisons}!=set(pending):raise ValueError('pending path replacement mismatch')
    old={(r['record_key'],r['round']):r for r in csv_rows(FIXED/'reachable_rounds.csv')}
    for r in rounds:
        key=r['record_key'];i=int(r['round'])
        if key not in pending:
            if r!=old[key,r['round']]:raise ValueError('unaffected trajectory changed')
        elif i<int(pending[key]['branch_generation_round']):
            original=old[key,r['round']]
            if any(r[k]!=original[k] for k in ['code_sha256','new_L3','new_error_category','tokens_in','tokens_out','generation_seconds','origin']):
                raise ValueError('preserved prefix changed')
        elif r['origin']!='diagnostic_v2_suffix':raise ValueError('old post-divergence suffix reused')
    before=[r for r in csv_rows(FIXED/'summary.csv') if r['condition']=='B4']
    after=[r for r in summary if r['condition']=='B4']
    if before!=after:raise ValueError('unaffected B4 summary changed')
    generated=csv_rows(OUT/'new_rounds.csv');slots=csv_rows(OUT/'generation_disposition.csv')
    if len(slots)!=26 or len({(r['record_key'],r['round']) for r in slots})!=26:raise ValueError('planned slot coverage mismatch')
    if {(r['record_key'],r['round']) for r in slots if r['disposition']=='generated'}!={(r['record_key'],r['round']) for r in generated}:
        raise ValueError('request coverage mismatch')
    snapshot=json.loads((OUT/'results_snapshot.json').read_text())
    if snapshot['new_requests']!=len(generated) or snapshot['followup']['new_tokens']!=sum(int(r['tokens_in'])+int(r['tokens_out']) for r in generated):
        raise ValueError('followup usage mismatch')
    # Mutation checks demonstrate that independent reconciliation rejects bad data.
    from copy import deepcopy
    damaged=deepcopy(summary);row=next(r for r in damaged if r['condition']=='F' and r['grouping']=='overall' and r['generation_cap']=='4')
    row['final_L3_successes']=str(int(row['final_L3_successes'])+1)
    try:verify_summary(rounds,paired,damaged)
    except ValueError:pass
    else:raise ValueError('mutated success count was not rejected')
    damaged=deepcopy(rounds);damaged[0]['tokens_in']=str(int(damaged[0]['tokens_in'])+1)
    # Select an additional round so a cost mutation must affect the cost totals.
    target=next(r for r in damaged if r['condition_id']=='execution_feedback' and r['round']=='1')
    target['tokens_in']=str(int(target['tokens_in'])+1)
    try:verify_summary(damaged,paired,summary)
    except ValueError:pass
    else:raise ValueError('mutated cost was not rejected')
    result={'passed':True,'inputs_verified':len(manifest['inputs']),'outputs_verified':len(manifest['outputs']),
            'paths_verified':len(paths),'condition_records_verified':len(paired),'pending_paths_replaced':10,
            'new_requests':len(generated),'planned_slots_accounted':26,'missing':0,'duplicates':0,
            'unaffected_paths_preserved':True,'old_suffix_excluded':True,'success_count_mutation_rejected':True,
            'token_cost_mutation_rejected':True,'model_requests':0,'generated_code_executions':0,
            'validator_sha256':sha(ROOT/'scripts/validate_diagnostic_policy_results.py')}
    from harness.run_state import atomic_json
    atomic_json(ROOT/'docs/diagnostic_policy_followup_validation_20261104.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2));return result


if __name__=='__main__':validate()
