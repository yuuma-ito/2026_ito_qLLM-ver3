"""Reevaluate saved L3 successes in isolation. NO model-generation capability."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
import json
from pathlib import Path
import time

from harness.measurement_isolation import isolated_evaluate, profile
from harness.reevaluation_checkpoint import Checkpoint
from harness.run_state import atomic_json
from scripts.measurement_ban_sources import ROOT, load_sources, sha


def run(output,checkpoint,workers=4,max_cases=None):
    data=load_sources()
    cases=data['cases']
    immutable={'schema':'measurement_ban_audit_v1','evaluator':profile(),'source_hashes':data['inputs'],
               'cases':[{k:v for k,v in c.items() if k!='code'} for c in sorted(cases.values(),key=lambda c:c['key'])],
               'new_model_requests':0,'automatic_followups':False,'scope':'existing_common_system_measurement_ban_only'}
    output.mkdir(parents=True,exist_ok=True)
    with Checkpoint(checkpoint,immutable) as store:
        pending=[k for k in sorted(cases) if store.completed(k) is None]
        if max_cases is not None:pending=pending[:max_cases]
        start=time.monotonic();last=0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs={}
            for key in pending:
                store.claim(key)
                c=cases[key]
                jobs[pool.submit(isolated_evaluate,c['code'],c['task_id'])]=key
            for job in as_completed(jobs):
                key=jobs[job]
                # Worker/protocol exceptions remain an unresolved audit result.
                try:result=job.result()
                except Exception as error:result={'runtime_status':'parent_exception','exception_type':type(error).__name__}
                store.finish(key,result)
                now=time.monotonic()
                if now-last>=10:
                    sanity=store.sanity()
                    atomic_json(output/'run_status.json',{'status':'running',**sanity,'elapsed_seconds':now-start})
                    print(json.dumps({'completed':sanity['completed'],'planned':sanity['planned'],'elapsed_seconds':round(now-start)},ensure_ascii=False),flush=True)
                    last=now
        sanity=store.sanity()
        results={k:store.completed(k) for k in cases}
        unchanged=all(sha(ROOT/p)==h for p,h in data['inputs'].items())
        if not unchanged:raise ValueError('historical sources changed during audit')
        atomic_json(output/'run_status.json',{'status':'completed' if not sanity['missing'] else 'incomplete',**sanity})
        if sanity['missing']:
            return {'status':'incomplete',**sanity}
        from scripts.measurement_ban_report import publish
        return publish(output,data,results,immutable)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('docs/analysis/measurement_ban_impact_20261104'))
    p.add_argument('--checkpoint',type=Path,default=Path('.cache/measurement_ban_impact_20261104'))
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--max-cases',type=int)
    args=p.parse_args()
    if not 1<=args.workers<=4:p.error('workers must be 1..4')
    if args.max_cases is not None and args.max_cases<1:p.error('max-cases must be positive')
    result=run(ROOT/args.output,ROOT/args.checkpoint,args.workers,args.max_cases)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
