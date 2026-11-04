"""Authorized continuation of the SINGLE B4 path invalidated at round 1.

Independent baseline prompt, original seeds/settings/digest, at most rounds
2 and 3. Old raw/history is never written. Ambiguous requests are not retried.
"""
from copy import deepcopy
from datetime import datetime,timezone
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from dotenv import load_dotenv
from harness.code_extractor import extract_code
from harness.independent_4 import (code_hash,digest,immutable_json,read_checkpoint,
                                  seed_for,strict_request,levels)
from harness.interventions import build_initial_prompt
from harness.llm_clients import SYSTEM_PROMPT,make_client
from harness.measurement_isolation import isolated_evaluate,profile
from harness.run_state import atomic_json,file_lock,RunTracker
from scripts.run_independent_4 import check_server,active_runs
from tasks import get_task

ROOT=Path(__file__).resolve().parents[1]
IMPACT=ROOT/'docs/analysis/measurement_ban_impact_20261104'
OLD=ROOT/'docs/analysis/independent_4_completed_20261022'


def prepare():
    impact=json.loads((IMPACT/'manifest.json').read_text())
    for name,hashed in impact['source_hashes'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=hashed:
            raise ValueError('impact source hash changed')
    with (IMPACT/'pending_generation.csv').open() as f:pending=list(csv.DictReader(f))
    if len(pending)!=1:raise ValueError('exactly one authorized pending path required')
    p=pending[0]
    ident=(p['model_spec'],p['task_id'],int(p['base_seed']))
    if ident!=('ollama:qwen2.5-coder:7b','T3a_DJ_constant',3) or p['old_stop_round']!='1':
        raise ValueError('authorized path identity differs')
    config=json.loads((OLD/'runner_experiment_config.json').read_text())
    old_manifest=json.loads((OLD/'runner_manifest.json').read_text())
    source=ROOT/'results/independent_4_full_20261020T185811381595Z/raw.jsonl'
    with source.open() as f:
        rows=[json.loads(l) for l in f if l.strip()]
    match=[r for r in rows if (r['model_spec'],r['task_id'],r['base_seed'])==ident]
    if len(match)!=1 or len(match[0]['rounds'])!=2:raise ValueError('old prefix mismatch')
    original=match[0]
    if original['rounds'][1]['code_sha256']!=p['branch_code_sha256']:raise ValueError('branch code changed')
    key=hashlib.sha256((ident[1]+'\n'+p['branch_code_sha256']).encode()).hexdigest()
    db=ROOT/'.cache/measurement_ban_impact_20261104/checkpoint.sqlite3'
    with sqlite3.connect(f'file:{db}?mode=ro',uri=True) as c:
        row=c.execute("select result,result_hash from results where key=? and state='completed'",(key,)).fetchone()
    if not row or hashlib.sha256(row[0].encode()).hexdigest()!=row[1]:raise ValueError('impact checkpoint mismatch')
    evaluation=json.loads(row[0])
    if not evaluation['measurement_violation'] or evaluation['primary']['L3']:
        raise ValueError('branch is not an invalidated success')
    prefix=deepcopy(original['rounds'])
    prefix[1]['original_primary']=deepcopy(prefix[1]['primary'])
    prefix[1]['primary']=evaluation['primary']
    prefix[1]['evaluation_origin']='measurement_ban_impact_20261104'
    prefix[0]['evaluation_origin']='preserved_v4_initial_failure; adding ban cannot make it pass'
    plan={'schema':'measurement_ban_single_B4_followup_v1','model_spec':ident[0],'task_id':ident[1],
          'base_seed':ident[2],'baseline_record_key':original['baseline_record_key'],
          'old_experiment_id':original['experiment_id'],'old_source':str(source.relative_to(ROOT)),
          'old_source_sha256':impact['source_hashes'][str(source.relative_to(ROOT))],
          'expected_model_digest':old_manifest['model_digests'][ident[0]],
          'generation_settings':config['generation_settings'],'temperature':config['temperature'],
          'seed_namespace':config['seed_namespace'],'new_rounds':[2,3],'max_new_requests':2,
          'derived_seeds':{str(i):seed_for(*ident,i,config['seed_namespace']) for i in [2,3]},
          'prompt_sha256':code_hash(build_initial_prompt('baseline',get_task(ident[1]))),
          'system_sha256':code_hash(SYSTEM_PROMPT),'prefix_code_sha256':[a['code_sha256'] for a in prefix],
          'evaluator':profile(),'authorization':'user explicitly approved this max-two-request followup and document update',
          'no_stronger_reference_checks':True}
    if config['generation_settings']!={'max_tokens':1024,'timeout_sec':600,'reasoning_effort':'none','parallel_requests':1}:
        raise ValueError('historical generation settings changed')
    plan['plan_sha256']=digest(plan)
    return plan,prefix


def continue_case(plan,prefix,client,directory,*,request=strict_request,executor=isolated_evaluate):
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    done=directory/'completed.json'
    if done.exists():
        saved=read_checkpoint(done)
        if saved['plan_sha256']!=plan['plan_sha256']:raise ValueError('completed plan differs')
        return saved
    rows=deepcopy(prefix)
    if [r['round'] for r in rows]!=[0,1] or any(r['primary']['L3'] for r in rows):
        raise ValueError('both preserved prefix attempts must fail revised policy')
    prompt=build_initial_prompt('baseline',get_task(plan['task_id']))
    for index in [2,3]:
        if rows[-1]['primary']['L3']:break
        seed=plan['derived_seeds'][str(index)]
        paths={kind:directory/f'round_{index}_{kind}.json' for kind in ['request','response','evaluation','evaluation_started']}
        req={'model_spec':plan['model_spec'],'system':SYSTEM_PROMPT,'user':prompt,'round':index,
             'round_seed':seed,'temperature':plan['temperature'],'generation_settings':plan['generation_settings']}
        if paths['request'].exists():
            if read_checkpoint(paths['request'])!=req:raise ValueError('request drift')
            if not paths['response'].exists():raise RuntimeError('ambiguous request: no automatic retry')
        else:
            if any(paths[k].exists() for k in ['response','evaluation','evaluation_started']):
                raise ValueError('unexpected checkpoint before request')
            immutable_json(paths['request'],req)
            response=request(client,prompt,seed,plan['temperature'])
            immutable_json(paths['response'],response)
        response=read_checkpoint(paths['response'])
        code=extract_code(response['raw_output'])
        if not paths['evaluation'].exists():
            if paths['evaluation_started'].exists():raise RuntimeError('ambiguous evaluation: review before retry')
            immutable_json(paths['evaluation_started'],{'code_sha256':code_hash(code)})
            immutable_json(paths['evaluation'],executor(code,plan['task_id']))
        ev=read_checkpoint(paths['evaluation'])
        if ev.get('runtime_status')!='completed':raise RuntimeError('unresolved evaluation infrastructure failure')
        levels(ev['primary'])
        rows.append({'round':index,'generation_number':index+1,'round_seed':seed,'reused':False,
            'prompt_sha256':code_hash(prompt),'system_sha256':code_hash(SYSTEM_PROMPT),
            'code_sha256':code_hash(code),'extracted_code':code,'primary':ev['primary'],
            'old_v4_primary':ev.get('old_primary'),'measurement_count':ev.get('measurement_count'),
            'tokens_in':response['tokens_in'],'tokens_out':response['tokens_out'],
            'generation_seconds':response['generation_seconds'],
            'evaluation_seconds':ev.get('seconds',0)+ev.get('build_seconds',0),
            'finish_reason':response.get('finish_reason'),'evaluation_origin':plan['evaluator']['primary_version']})
    result={'plan_sha256':plan['plan_sha256'],'model_spec':plan['model_spec'],'task_id':plan['task_id'],
            'base_seed':plan['base_seed'],'baseline_record_key':plan['baseline_record_key'],'rounds':rows,
            'new_requests':len(rows)-2,'final_success':rows[-1]['primary']['L3'],'final_round':rows[-1]['round']}
    if not result['final_success'] and result['final_round']!=3:raise ValueError('incomplete failed path')
    immutable_json(done,result)
    return result


def execute(output):
    plan,prefix=prepare()
    if not output.resolve().is_relative_to((ROOT/'results').resolve()):raise ValueError('separate results directory required')
    with file_lock(ROOT/'.cache/automate_experiment.lock',nonblocking=True),file_lock(ROOT/'.cache/measurement_ban_followup.lock',nonblocking=True):
        if active_runs():raise RuntimeError('another generation experiment is active')
        output.mkdir(parents=True,exist_ok=True,mode=0o700)
        manifest=output/'manifest.json'
        if manifest.exists():
            if read_checkpoint(manifest)['plan_sha256']!=plan['plan_sha256']:raise ValueError('resume profile/plan drift')
        else:
            if any(output.iterdir()):raise ValueError('nonempty output without manifest')
            immutable_json(manifest,plan)
            immutable_json(output/'experiment_config.json',plan)
        load_dotenv(ROOT/'.env')
        client=make_client(plan['model_spec'])
        before=check_server(client,plan['expected_model_digest'])
        with RunTracker(output,output.name,root=ROOT) as tracker:
            tracker.update(phase='measurement_ban_single_B4_followup',model=plan['model_spec'],task=plan['task_id'],seed=plan['base_seed'])
            result=continue_case(plan,prefix,client,output/'private')
            after=check_server(client,plan['expected_model_digest'])
            if not (ROOT/plan['old_source']).is_file() or hashlib.sha256((ROOT/plan['old_source']).read_bytes()).hexdigest()!=plan['old_source_sha256']:
                raise ValueError('old source changed')
            public={'status':'completed_verified','run_id':output.name,'output_dir':str(output.relative_to(ROOT)),
                    'model_spec':plan['model_spec'],'task_id':plan['task_id'],'base_seed':plan['base_seed'],
                    'new_requests':result['new_requests'],'final_success':result['final_success'],'final_round':result['final_round'],
                    'new_tokens':sum(a['tokens_in']+a['tokens_out'] for a in result['rounds'][2:]),
                    'plan_sha256':plan['plan_sha256'],'model_digest_matched':True,'server_before':before,'server_after':after,
                    'new_rounds':[{'round':a['round'],'seed':a['round_seed'],'code_sha256':a['code_sha256'],
                                   'L3':a['primary']['L3'],'error_category':a['primary']['error_category'],
                                   'tokens_in':a['tokens_in'],'tokens_out':a['tokens_out']} for a in result['rounds'][2:]]}
            atomic_json(output/'public_result.json',public)
            atomic_json(ROOT/'.cache/measurement_ban_followup_latest.json',public)
            tracker.finish(status='completed',recorded=1,published=False)
        print(json.dumps(public,ensure_ascii=False,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group();group.add_argument('--new-run',action='store_true');group.add_argument('--resume',type=Path)
    args=p.parse_args()
    if not args.new_run and not args.resume:
        plan,_=prepare();print(json.dumps(plan,ensure_ascii=False,indent=2));return
    output=ROOT/args.resume if args.resume else ROOT/'results'/('measurement_ban_followup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    execute(output)


if __name__=='__main__':main()
