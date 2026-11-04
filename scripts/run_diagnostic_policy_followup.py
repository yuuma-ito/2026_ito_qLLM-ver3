"""Authorized v2 continuation of the ten pinned F/D diagnostic divergences.

Private immutable request/response/evaluation checkpoints; no ambiguous retries.
Old raw, fixed aggregates, and generated suffixes are never modified.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from harness.code_extractor import extract_code
from harness.diagnostic_policy import DIAGNOSTIC_VERSION
from harness.diagnostic_prompts import build_intervention_prompt
from harness.independent_4 import code_hash, digest, immutable_json, read_checkpoint, strict_request, levels
from harness.llm_clients import SYSTEM_PROMPT, make_client
from harness.measurement_isolation import isolated_evaluate, profile
from harness.reevaluation_checkpoint import canonical
from harness.run_state import atomic_json, file_lock, RunTracker
from scripts.measurement_ban_sources import ROOT, load_sources, csv_rows, sha
from scripts.reevaluation_followup_validation import read_db, validate_rows
from scripts.reevaluation_impact_audit import event
from scripts.run_independent_4 import check_server, active_runs
from tasks import get_task

IMPACT=ROOT/'docs/analysis/diagnostic_policy_impact_20261104'
FIXED=ROOT/'docs/analysis/measurement_ban_corrected_20261104'


def prepare():
    audit=json.loads((IMPACT/'manifest.json').read_text())
    for name,h in audit['inputs'].items():
        if sha(ROOT/name)!=h:raise ValueError('impact input changed: '+name)
    for name,h in audit['outputs'].items():
        if sha(IMPACT/name)!=h:raise ValueError('impact output changed: '+name)
    pending=csv_rows(IMPACT/'pending_generation.csv')
    if len(pending)!=10 or len({r['record_key'] for r in pending})!=10:
        raise ValueError('exactly ten distinct authorized paths required')
    if Counter(r['condition_id'] for r in pending)!={'execution_feedback':6,'self_debugging':4}:
        raise ValueError('condition coverage differs')
    data=load_sources()
    settings=json.loads((ROOT/'docs/analysis/reevaluation_followup_20261015/settings_manifest.json').read_text())
    settings={s['source_dir']:s for s in settings['sources']}
    status=json.loads((ROOT/'docs/analysis/reevaluation_full_20261014T141718Z/run_status.json').read_text())
    dbplan,stored=read_db(Path(status['checkpoint_dir'])/'checkpoint.sqlite3');validate_rows(dbplan,stored)
    primary={k:json.loads(t)['primary'] for k,_,_,t,_ in stored}
    reachable={(r['record_key'],int(r['round'])):r for r in csv_rows(FIXED/'reachable_rounds.csv')}
    comparison={(r['record_key'],int(r['round'])):r for r in csv_rows(IMPACT/'round_diagnostic_comparison.csv')}
    cases=[];prefixes={};expected_digests=set()
    for p in pending:
        if (p['model_spec'],p['task_id'],p['old_final_success'])!=('ollama:gemma3:4b','T4_BV_011','False'):
            raise ValueError('unauthorized identity or success')
        key=p['record_key'];branch=int(p['branch_generation_round']);base=int(p['base_seed'])
        s=settings[p['source_dir']]
        if s['generation_settings']!={'max_tokens':1024,'timeout_sec':600,'reasoning_effort':'none','parallel_requests':1} or s['temperature']!=.7 or s['max_rounds']!=3:
            raise ValueError('historical generation settings drift')
        expected_digests.add(s['model_digests'][p['model_spec']])
        prefix=[]
        for i in range(branch):
            r=reachable[key,i]
            if r['origin']=='saved_prefix':
                a=data['raw'][(p['source_dir'],p['model_spec'],p['task_id'],p['base_seed'],p['condition_id'])][i]
                code=a['extracted_code'];ev=primary[key+':'+str(i)];seed=a['round_seed']
            elif r['origin']=='new_suffix':
                path=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/key/'completed.json'
                saved=json.loads(path.read_text())
                if sha(path)!=path.with_suffix('.sha256').read_text().strip():raise ValueError('suffix integrity drift')
                a=next(a for a in saved['suffix'] if a['round']==i)
                code=a['code'];ev=a['evaluation']['primary'];seed=a['seed']
            else:raise ValueError('unsupported prefix provenance')
            if code_hash(code)!=r['code_sha256'] or seed!=base+i or ev['L3'] or r['new_L3']!='False':
                raise ValueError('prefix code/seed/verdict mismatch')
            levels(ev)
            prefix.append({'round':i,'round_seed':seed,'extracted_code':code,'code_sha256':code_hash(code),
                           'primary':ev,'origin':r['origin'],'reused':True,'tokens_in':int(r['tokens_in']),
                           'tokens_out':int(r['tokens_out']),'generation_seconds':float(r['generation_seconds'])})
        task=get_task(p['task_id'])
        for i,a in enumerate(prefix):
            prompt=build_intervention_prompt(p['condition_id'],task,a['extracted_code'],event(a['primary']))
            cr=comparison[key,i]
            if code_hash(prompt)!=cr['new_prompt_sha256'] or (i<branch-1 and cr['prompt_changed']=='True'):
                raise ValueError('prefix or first divergence prompt mismatch')
        cr=comparison[key,branch-1]
        if cr['has_next']!='True' or cr['prompt_changed']!='True' or cr['actual_old_prompt_verified']!='True':
            raise ValueError('first branch was not a verified consumed change')
        case={k:p[k] for k in ['record_key','source_dir','model_spec','task_id','condition_id']}
        case.update(base_seed=base,branch_generation_round=branch,generation_cap=4-branch,
                    prefix_fingerprints=[digest(a) for a in prefix],old_first_changed_prompt_sha256=cr['old_prompt_sha256'],
                    first_v2_prompt_sha256=cr['new_prompt_sha256'],temperature=s['temperature'],
                    generation_settings=s['generation_settings'])
        cases.append(case);prefixes[key]=prefix
    if len(expected_digests)!=1 or sum(c['generation_cap'] for c in cases)!=26:
        raise ValueError('model identity or total cap mismatch')
    implementation=['scripts/run_diagnostic_policy_followup.py','harness/diagnostic_policy.py',
                    'harness/diagnostic_prompts.py','harness/interventions/prompts.py','harness/refine.py',
                    'harness/llm_clients.py','harness/independent_4.py','prompts/system.txt']
    plan={'schema':'diagnostic_policy_ten_path_followup_v1','diagnostic_policy_version':DIAGNOSTIC_VERSION,
          'audit_manifest_sha256':sha(IMPACT/'manifest.json'),'fixed_manifest_sha256':sha(FIXED/'manifest.json'),
          'inputs':audit['inputs']|{str((IMPACT/'manifest.json').relative_to(ROOT)):sha(IMPACT/'manifest.json')},
          'implementation':{f:sha(ROOT/f) for f in implementation},'evaluator':profile(),
          'expected_model_digest':next(iter(expected_digests)),'model_spec':'ollama:gemma3:4b',
          'cases':cases,'paths':10,'unique_initial_groups':6,'max_new_requests':26,
          'system_sha256':code_hash(SYSTEM_PROMPT),'seed_rule':'base_seed + correction_round',
          'feedback_serialization':'canonical_result_json_v1','no_stronger_reference_checks':True,
          'authorization':'user approved the proposed ten-path continuation; no other generation',
          'historical_results_preserved':True}
    plan['plan_sha256']=digest(plan)
    return plan,prefixes


def continue_case(case,prefix,plan,client,directory,*,request=strict_request,executor=isolated_evaluate):
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    completed=directory/'completed.json'
    if [digest(a) for a in prefix]!=case['prefix_fingerprints']:raise ValueError('prefix drift')
    if completed.exists():
        result=read_checkpoint(completed)
        validate_result(result,case,prefix,plan)
        return result
    rows=deepcopy(prefix);task=get_task(case['task_id'])
    for index in range(case['branch_generation_round'],4):
        if rows[-1]['primary']['L3']:break
        prompt=build_intervention_prompt(case['condition_id'],task,rows[-1]['extracted_code'],event(rows[-1]['primary']))
        if index==case['branch_generation_round'] and code_hash(prompt)!=case['first_v2_prompt_sha256']:
            raise ValueError('branch prompt drift')
        req={'record_key':case['record_key'],'round':index,'seed':case['base_seed']+index,
             'model_spec':case['model_spec'],'system':SYSTEM_PROMPT,'user':prompt,
             'temperature':case['temperature'],'generation_settings':case['generation_settings'],
             'diagnostic_policy_version':DIAGNOSTIC_VERSION,'plan_sha256':plan['plan_sha256']}
        paths={k:directory/f'round_{index}_{k}.json' for k in ['request','response','evaluation','evaluation_started','failure']}
        if paths['request'].exists():
            if read_checkpoint(paths['request'])!=req:raise ValueError('saved request drift')
            if not paths['response'].exists():raise RuntimeError('ambiguous request: no automatic retry')
        else:
            if any(paths[k].exists() for k in paths if k!='request'):raise ValueError('unexpected request checkpoint')
            immutable_json(paths['request'],req)
            try:response=request(client,prompt,req['seed'],case['temperature'])
            except Exception as error:
                immutable_json(paths['failure'],{'exception_type':type(error).__name__,'ambiguous_request':True})
                raise
            immutable_json(paths['response'],response)
        response=read_checkpoint(paths['response']);code=extract_code(response['raw_output'])
        if not paths['evaluation'].exists():
            if paths['evaluation_started'].exists():raise RuntimeError('ambiguous evaluation: review before retry')
            immutable_json(paths['evaluation_started'],{'code_sha256':code_hash(code)})
            immutable_json(paths['evaluation'],executor(code,case['task_id']))
        ev=read_checkpoint(paths['evaluation'])
        if ev.get('runtime_status')!='completed':raise RuntimeError('unresolved evaluation infrastructure failure')
        levels(ev['primary'])
        if ev['primary']['error_category']=='unknown_error':
            from scripts.reevaluation_followup_validation import cause
            cause(ev['primary'])  # Previously reviewed model exceptions only.
        rows.append({'round':index,'round_seed':req['seed'],'extracted_code':code,'code_sha256':code_hash(code),
                     'primary':json.loads(canonical(ev))['primary'],'origin':'diagnostic_v2_suffix','reused':False,
                     'input_prompt_sha256':code_hash(prompt),'system_sha256':code_hash(SYSTEM_PROMPT),
                     'diagnostic_policy_version':DIAGNOSTIC_VERSION,'tokens_in':response['tokens_in'],
                     'tokens_out':response['tokens_out'],'generation_seconds':response['generation_seconds'],
                     'evaluation_seconds':ev.get('seconds',0)+ev.get('build_seconds',0),
                     'finish_reason':response.get('finish_reason')})
    result={'plan_sha256':plan['plan_sha256'],'record_key':case['record_key'],'rounds':rows,
            'new_requests':len(rows)-len(prefix),'final_success':rows[-1]['primary']['L3'],
            'final_round':rows[-1]['round']}
    validate_result(result,case,prefix,plan)
    immutable_json(completed,result)
    return result


def validate_result(result,case,prefix,plan):
    rows=result['rounds'];branch=case['branch_generation_round']
    if result['plan_sha256']!=plan['plan_sha256'] or result['record_key']!=case['record_key']:
        raise ValueError('completed identity mismatch')
    if rows[:branch]!=prefix or [a['round'] for a in rows]!=list(range(len(rows))) or not branch<len(rows)<=4:
        raise ValueError('prefix, missing, duplicate or unexpected rounds')
    for i,a in enumerate(rows):
        levels(a['primary'])
        if code_hash(a['extracted_code'])!=a['code_sha256'] or a['round_seed']!=case['base_seed']+i:
            raise ValueError('saved code/seed drift')
        if a['primary']['L3'] and i!=len(rows)-1:raise ValueError('continued after success')
        if i>=branch:
            prompt=build_intervention_prompt(case['condition_id'],get_task(case['task_id']),rows[i-1]['extracted_code'],event(rows[i-1]['primary']))
            if a['input_prompt_sha256']!=code_hash(prompt) or a['diagnostic_policy_version']!=DIAGNOSTIC_VERSION or a['system_sha256']!=plan['system_sha256']:
                raise ValueError('completed prompt/policy drift')
            if any(type(a[k]) is not int or a[k]<0 for k in ['tokens_in','tokens_out']):raise ValueError('invalid usage')
    if result['new_requests']!=len(rows)-branch or result['final_success']!=rows[-1]['primary']['L3'] or result['final_round']!=len(rows)-1:
        raise ValueError('final status mismatch')
    if not result['final_success'] and result['final_round']!=3:raise ValueError('incomplete unsuccessful path')


def execute(output):
    plan,prefixes=prepare()
    if not output.resolve().is_relative_to((ROOT/'results').resolve()):raise ValueError('separate results destination required')
    with file_lock(ROOT/'.cache/automate_experiment.lock',nonblocking=True),file_lock(ROOT/'.cache/diagnostic_policy_followup.lock',nonblocking=True):
        if active_runs():raise RuntimeError('another generation experiment is active')
        output.mkdir(parents=True,exist_ok=True,mode=0o700)
        if (output/'manifest.json').exists():
            if read_checkpoint(output/'manifest.json')!=plan:raise ValueError('resume plan drift')
        else:
            if any(output.iterdir()):raise ValueError('nonempty destination without manifest')
            immutable_json(output/'manifest.json',plan)
            immutable_json(output/'experiment_config.json',plan)
        load_dotenv(ROOT/'.env');client=make_client(plan['model_spec'])
        before=check_server(client,plan['expected_model_digest']);immutable_json(output/'private/server_before.json',before) if not (output/'private/server_before.json').exists() else None
        with RunTracker(output,output.name,root=ROOT) as tracker:
            results=[]
            for case in plan['cases']:
                if profile()!=plan['evaluator'] or any(sha(ROOT/f)!=h for f,h in plan['implementation'].items()):
                    raise ValueError('implementation changed during execution')
                tracker.update(phase='diagnostic_v2_suffix_generation',model=case['model_spec'],task=case['task_id'],seed=case['base_seed'],recorded=len(results))
                result=continue_case(case,prefixes[case['record_key']],plan,client,output/'private'/case['record_key'])
                results.append(result)
                progress={'status':'running','output_dir':str(output.relative_to(ROOT)),'completed_paths':len(results),
                          'planned_paths':10,'new_requests':sum(r['new_requests'] for r in results)}
                atomic_json(output/'progress.json',progress);print(json.dumps(progress),flush=True)
            after=check_server(client,plan['expected_model_digest'])
            for name,h in plan['inputs'].items():
                if sha(ROOT/name)!=h:raise ValueError('old input changed during execution: '+name)
            public={'status':'completed_verified','run_id':output.name,'output_dir':str(output.relative_to(ROOT)),
                    'plan_sha256':plan['plan_sha256'],'diagnostic_policy_version':DIAGNOSTIC_VERSION,
                    'completed_paths':len(results),'new_requests':sum(r['new_requests'] for r in results),
                    'new_tokens':sum(a['tokens_in']+a['tokens_out'] for r,c in zip(results,plan['cases']) for a in r['rounds'][c['branch_generation_round']:]),
                    'successful_paths':sum(r['final_success'] for r in results),'server_before':before,'server_after':after,
                    'model_digest_matched':True,'historical_sources_unchanged':True,'no_stronger_reference_checks':True}
            atomic_json(output/'public_result.json',public)
            atomic_json(ROOT/'.cache/diagnostic_policy_followup_latest.json',public)
            atomic_json(output/'progress.json',dict(progress,status='completed'))
            tracker.finish(status='completed',recorded=len(results),published=False)
        print(json.dumps(public,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group();g.add_argument('--new-run',action='store_true');g.add_argument('--resume',type=Path)
    args=p.parse_args()
    if not args.new_run and not args.resume:
        plan,_=prepare();print(json.dumps({k:plan[k] for k in ['plan_sha256','paths','unique_initial_groups','max_new_requests','expected_model_digest']},indent=2));return
    output=ROOT/args.resume if args.resume else ROOT/'results'/('diagnostic_policy_followup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    execute(output)


if __name__=='__main__':main()
