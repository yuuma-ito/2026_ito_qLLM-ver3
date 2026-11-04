"""Read-only consistency audit. Never executes saved generated code."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts import analyze_verified_rescues as base
from scripts.analyze_reachable_rescue_history import cost_summary

OUT=Path(__file__).with_name('audit_results.json')
checks={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with (ROOT/p).open() as f:return list(csv.DictReader(f))
def same(a,b):
    if (a is None or a=='') and (b is None or b==''):return True
    if str(a)==str(b):return True
    try:return math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-6)
    except (TypeError,ValueError):return False
def compare(name,actual,expected,keys):
    ident=lambda r:tuple(str(r.get(k,'')) for k in keys)
    aa={ident(r):r for r in actual};bb={ident(r):r for r in expected}
    errors=[]
    if len(aa)!=len(actual) or len(bb)!=len(expected):errors.append('duplicate keys')
    if set(aa)!=set(bb):errors.append('key mismatch')
    for k in aa.keys()&bb.keys():
        for field,v in bb[k].items():
            if not same(aa[k].get(field,''),v):errors.append([k,field,aa[k].get(field),v])
    checks[name]={'passed':not errors,'rows':len(actual),'errors':errors[:10]}
    return not errors

core=Path('docs/analysis/reachable_rescues_20261016')
b4=Path('docs/analysis/independent_4_completed_20261022')
follow=Path('docs/analysis/reevaluation_followup_20261015')
full=Path('docs/analysis/reevaluation_full_20261014T141718Z/final')
settings=json.loads((ROOT/follow/'settings_manifest.json').read_text())
raw={};hash_errors=[]
for source in settings['sources']:
    folder=ROOT/source['source_dir']
    for name,key in [('raw.jsonl','raw_sha256'),('experiment_config.json','config_sha256')]:
        if sha(folder/name)!=source[key]:hash_errors.append(str(folder/name))
    with (folder/'raw.jsonl').open() as f:
        for line in f:
            r=json.loads(line);k=(source['source_dir'],r['model_spec'],r['task_id'],str(r['base_seed']),r['condition_id'])
            assert k not in raw
            raw[k]={x['round']:x for x in r['rounds']}
checks['original_5000_raw_records_hashes']={'passed':len(raw)==5000 and not hash_errors,'records':len(raw),'errors':hash_errors}
mixed=read(follow/'mixed_path_records.csv');saved=read(full/'round_comparison.csv')
partial=read(follow/'partial_rerun_records.csv');new=read(follow/'partial_new_rounds.csv')
paths=base.build_paths(mixed,saved,partial,new)
difficulties={r['task_id']:r['task_difficulty'] for r in read(core/'core/paired_records.csv')}
ledger,repair,overlaps,fd=base.analyze(mixed,paths,difficulties)
groupkeys=['scope','source_dir','grouping',*list(dict.fromkeys(f for ff in base.GROUPINGS.values() for f in ff))]
compare('all_repair_summary_rows',read(core/'core/repair_summary.csv'),[r for r in repair if r['condition_id'] in base.REPAIRS],groupkeys+['condition_id'])
compare('all_preventive_summary_rows',read(core/'core/preventive_summary.csv'),[r for r in repair if r['condition_id']==base.P],groupkeys+['condition_id'])
compare('all_FD_overlap_summary_rows',read(core/'core/fd_overlap_summary.csv'),fd,groupkeys)
compare('all_paired_records',read(core/'core/paired_records.csv'),ledger,['record_key'])

rounds=read(core/'reachable_rounds.csv');rrmap={(r['record_key'],int(r['round'])):r for r in rounds}
branches={r['record_key']:int(r['branch_input_round']) for r in partial}
suffix={};cachehasherrors=[]
cache=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'
for key in branches:
    p=cache/key/'completed.json'
    if p.with_suffix('.sha256').read_text().strip()!=sha(p):cachehasherrors.append(key)
    suffix[key]={r['round']:r for r in json.loads(p.read_text())['suffix']}
errors=[]
for m in mixed:
    key=m['record_key']
    for i,e in enumerate(paths[key]):
        a=rrmap[(key,i)]
        origin='new_suffix' if i>=branches.get(key,4) else 'saved_prefix'
        source=suffix[key][i] if origin=='new_suffix' else raw[base.identity(m)][i]
        code=source['code'] if origin=='new_suffix' else source['extracted_code']
        expecthash=e.get('code_sha256',e.get('new_code_sha256'))
        if not (a['origin']==origin and a['code_sha256']==expecthash==hashlib.sha256(code.encode()).hexdigest()
            and base.truth(a['new_L3'])==base.truth(e['new_L3'])
            and a['new_error_category']==e['new_error_category']
            and int(a['tokens_in'])==int(source['tokens_in']) and int(a['tokens_out'])==int(source['tokens_out'])
            and same(a['generation_seconds'],source['elapsed_sec'])):errors.append([key,i])
checks['reachable_9249_rounds_match_raw_and_checkpoints']={'passed':not errors and not cachehasherrors and len(rounds)==sum(map(len,paths.values())),'rounds':len(rounds),'errors':errors[:10],'checkpoint_hash_errors':cachehasherrors}
typed=[]
for r in rounds:
    r=dict(r)
    for k in ['round','tokens_in','tokens_out','tokens']:r[k]=int(r[k])
    r['generation_seconds']=float(r['generation_seconds'])
    typed.append(r)
costs=cost_summary(ledger,typed)
compare('all_reconstructed_cost_rows',read(core/'cost_by_cap_and_stratum.csv'),costs,groupkeys+['condition_id','cap'])
third=[]
for current in costs:
    if current['cap']!=3:continue
    prior=next(p for p in costs if p['cap']==2 and all(p.get(k,'')==current.get(k,'') for k in groupkeys+['condition_id']))
    added=current['rescued']-prior['rescued']
    third.append(dict(current,additional_rescues=added,at_risk_after_2=current['initial_failures']-prior['rescued'],
        third_round_requests=current['generation_requests']-prior['generation_requests'],
        third_round_tokens=current['tokens']-prior['tokens'],third_round_seconds=current['generation_seconds']-prior['generation_seconds'],
        third_tokens_per_extra_rescue=(current['tokens']-prior['tokens'])/added if added else '',
        third_seconds_per_extra_rescue=(current['generation_seconds']-prior['generation_seconds'])/added if added else '',
        loss_if_stop_at_2=added/current['rescued'] if current['rescued'] else ''))
compare('all_third_round_summary_rows',read(core/'third_round_summary.csv'),third,groupkeys+['condition_id','cap'])

rawb4=ROOT/'results/independent_4_full_20261020T185811381595Z/raw.jsonl'
manifest=json.loads((ROOT/b4/'source_manifest.json').read_text())
checks['B4_raw_hash_matches_fixed']={'passed':sha(rawb4)==manifest['raw_sha256']}
with rawb4.open() as f:b4records=[json.loads(l) for l in f if l.strip()]
key=lambda r:(r['model_spec'],r['task_id'],str(r['base_seed']))
refs=defaultdict(dict)
labels={'self_refine':'R','execution_feedback':'F','self_debugging':'D','preventive_spec':'P'}
for r in ledger:
    hist=[]
    for i,e in enumerate(paths[r['record_key']]):
        a=rrmap[(r['record_key'],i)]
        hist.append({'primary':{l:base.truth(e['new_'+l]) for l in ['L0','L1','L2','L3']},'code_sha256':a['code_sha256'],
            'tokens_in':int(a['tokens_in']),'tokens_out':int(a['tokens_out']),'generation_seconds':float(a['generation_seconds']),'evaluation_seconds':None})
    refs[key(r)][labels[r['condition_id']]]=hist
totals=defaultdict(Counter);first=Counter();masks=Counter();pair=defaultdict(Counter);stoperrors=[]
metrics=('groups','initial_failures','final_L3_successes','successes_from_initial_failure','regressed','total_generation_opportunities','additional_requests','additional_tokens_in','additional_tokens_out','additional_tokens','additional_generation_seconds','additional_evaluation_seconds','evaluation_time_measured_requests','cumulative_L0','cumulative_L1','cumulative_L2','cumulative_L3')
seen=set();repetitions=[]
for rec in b4records:
    ident=key(rec)
    assert ident not in seen;seen.add(ident)
    history=rec['rounds'];initial=history[0];failed=not initial['primary']['L3']
    assert initial['code_sha256']==refs[ident]['R'][0]['code_sha256']
    assert all(initial['primary'][l]==refs[ident]['R'][0]['primary'][l] for l in ['L0','L1','L2','L3'])
    if not(len(history)==1 and not failed or 2<=len(history)<=4 and failed):stoperrors.append(ident)
    if any(r['primary']['L3'] for r in history[:-1]) or (not history[-1]['primary']['L3'] and len(history)!=4):stoperrors.append(ident)
    for r in history:
        assert hashlib.sha256(r['extracted_code'].encode()).hexdigest()==r['code_sha256']
        assert r['primary']['L3']==all(r['primary'][l] for l in ['L0','L1','L2','structure_match'])
    dims={'overall':'all','model':rec['model_spec'],'task':rec['task_id'],'difficulty':rec['task_difficulty'],'initial_failure':initial['primary']['error_category']}
    ps={'B':[initial],'B4':history,**refs[ident]}
    for label,h in ps.items():
        first_i=next((i for i,r in enumerate(h) if r['primary']['L3']),None)
        first[(label,'never' if first_i is None else 'generation_'+str(first_i+1))]+=1
        for cap in ([1] if label in ['B','P'] else range(1,5)):
            chosen=h[:cap];additional=chosen if label=='P' else chosen[1:]
            success=any(r['primary']['L3'] for r in chosen)
            count=dict(groups=1,initial_failures=int(failed),final_L3_successes=int(success),successes_from_initial_failure=int(failed and success),regressed=int(not failed and not success),total_generation_opportunities=len(chosen),additional_requests=len(additional),additional_tokens_in=sum(r['tokens_in'] for r in additional),additional_tokens_out=sum(r['tokens_out'] for r in additional),additional_generation_seconds=sum(r['generation_seconds'] for r in additional),additional_evaluation_seconds=sum(r.get('evaluation_seconds') or 0 for r in additional),evaluation_time_measured_requests=sum(r.get('evaluation_seconds') is not None for r in additional))
            count['additional_tokens']=count['additional_tokens_in']+count['additional_tokens_out']
            for l in ['L0','L1','L2','L3']:count['cumulative_'+l]=int(any(r['primary'][l] for r in chosen))
            for g,value in dims.items():totals[(label,str(cap),g,value)].update(count)
    if failed:
        successes={c:any(r['primary']['L3'] for r in ps[c]) for c in ['B4','R','F','D']}
        masks[tuple(successes[c] for c in ['B4','F','D'])]+=1
        for c in ['R','F','D']:
            a,b=successes['B4'],successes[c]
            pair[c]['both' if a and b else 'B4_only' if a else c+'_only' if b else 'neither']+=1
for r in read(b4/'summary.csv'):
    actual=totals[(r['condition'],r['generation_cap'],r['grouping'],r['group'])]
    assert all(same(r[m],actual[m]) for m in metrics),(r['condition'],r['grouping'],r['group'])
    assert same(r['final_L3_rate'],actual['final_L3_successes']/actual['groups'])
    assert same(r['success_from_initial_failure_rate'],actual['successes_from_initial_failure']/actual['initial_failures'] if actual['initial_failures'] else '')
    assert same(r['tokens_per_added_success'],actual['additional_tokens']/actual['successes_from_initial_failure'] if actual['successes_from_initial_failure'] else '')
assert len(read(b4/'summary.csv'))==len(totals)
checks['all_B4_summary_rows_from_individual_histories']={'passed':True,'rows':len(totals),'groups':len(seen),'stopping_errors':stoperrors}
assert not stoperrors
for r in read(b4/'overlap.csv'):assert int(r['initial_failure_groups'])==masks[tuple(base.truth(r[c+'_success']) for c in ['B4','F','D'])]
for r in read(b4/'pairwise.csv'):assert all(int(v)==pair[r['comparator']][k] for k,v in r.items() if k!='comparator' and v!='')
for r in read(b4/'first_success.csv'):assert int(r['groups'])==first[(r['condition'],r['first_success_generation'])]
checks['B4_overlap_pairwise_first_success_recomputed']={'passed':True}

# Mutation control: a changed success count must be rejected by the comparator.
test_actual=[dict(repair[0])];test_expected=[dict(repair[0])]
test_expected[0]['rescued']+=1
detected=not compare('mutation_control',test_actual,test_expected,['condition_id'])
checks['mutation_control']={'passed':detected,'altered_success_count_detected':detected}

manifest_results={}
for folder in [core,core/'core',b4,Path('docs/presentation_sources/20261016T_reachable_rescues')]:
    p=ROOT/folder/'manifest.json'
    if not p.exists():continue
    obj=json.loads(p.read_text());errors=[];missing=[]
    source_manifest=ROOT/folder/'source_manifest.json'
    meta=json.loads(source_manifest.read_text()) if source_manifest.exists() else {}
    output_root=ROOT/meta.get('source_analysis',str(folder))
    for section in ['inputs','outputs']:
        for name,digest in obj.get(section,{}).items():
            target=ROOT/name if section=='inputs' else output_root/name
            if not target.exists():missing.append(name)
            elif sha(target)!=digest:errors.append(name)
    manifest_results[str(folder)]={'output_root':str(output_root.relative_to(ROOT)),'hash_mismatches':errors,'missing_files':missing}
finish=Counter(r['api_finish_reason'] for r in new)
report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'passed':all(c['passed'] for c in checks.values()) and all(not m['hash_mismatches'] and not m['missing_files'] for m in manifest_results.values()),'checks':checks,'manifest_verification':manifest_results,'partial_rerun_finish_reasons':dict(finish),'audit_script_sha256':sha(Path(__file__)),'helper_script_sha256':{p:sha(ROOT/p) for p in ['scripts/analyze_verified_rescues.py','scripts/analyze_reachable_rescue_history.py']},'notes':['No model API calls, generated-code execution, rescoring, original artifact edits, or git operations.','Recomputed saved outcomes; this does not independently validate all scoring judgments.','B4 summary independently summed from private B4 records and frozen reachable comparator histories.']}
OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
