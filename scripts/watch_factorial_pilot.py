"""Supervise the detached pilot and publish its final independent report once."""
import argparse
from datetime import datetime,timezone
import json
import time
import traceback

from dotenv import load_dotenv
from harness.independent_4 import read_checkpoint
from harness.run_state import atomic_json,file_lock,read_state,observation
from scripts.measurement_ban_sources import ROOT
from scripts.run_factorial_pilot import notify
from scripts.finish_factorial_pilot import verify_and_report


def watch(output,interval=55):
    plan=read_checkpoint(output/'manifest.json');public=ROOT/plan['analysis_dir']
    cache=ROOT/'.cache'/plan['run_id'];cache.mkdir(parents=True,exist_ok=True)
    statefile=cache/'independent_supervisor.json'
    load_dotenv(ROOT/'.env')
    with file_lock(cache/'independent_supervisor.lock',nonblocking=True):
        if statefile.exists():raise RuntimeError('existing supervisor job: no automatic duplicate/retry')
        state={'status':'running','run_id':plan['run_id'],'started_at_utc':datetime.now(timezone.utc).isoformat()}
        atomic_json(statefile,state)
        try:
            while not (public/'completion.json').exists():
                progress=json.loads((output/'progress.json').read_text()) if (output/'progress.json').exists() else {}
                runtime=read_state(output,ROOT)
                if progress.get('status')=='stopped_for_review' or (runtime and observation(runtime) in ['failed','interrupted']):
                    state.update(status='stopped_for_review',progress=progress)
                    atomic_json(statefile,state)
                    notify(plan,'supervisor_stopped',f"要因分析予備実験は異常で停止しました。条件変更・自動再送・commit/pushはしていません。状態: {output/'progress.json'}、ログ: {ROOT/'logs'/(plan['run_id']+'.log')}")
                    return 1
                n=progress.get('completed_requests',0)
                if n and n//100:
                    mark=n//100
                    notify(plan,f'progress_{mark*100}',f"予備実験進捗: {progress.get('phase')}、{n}要求保存、第1段階{progress.get('completed_round1_requests',0)}/400要求。途中の成績を結論として扱わず、固定計画のまま実行中。保存先: {public}")
                atomic_json(cache/'supervisor_heartbeat.json',{'updated_at_utc':datetime.now(timezone.utc).isoformat(),'completed_requests':n,'phase':progress.get('phase')})
                time.sleep(interval)
            verify_and_report(output,send_notification=True)
            state.update(status='completed_verified',finished_at_utc=datetime.now(timezone.utc).isoformat(),report=str(public/'independent_review/final_report.txt'))
            atomic_json(statefile,state);return 0
        except BaseException as error:
            state.update(status='stopped_for_review',exception_type=type(error).__name__,automatic_retry=False)
            atomic_json(statefile,state)
            (cache/'independent_review_error.log').write_text(traceback.format_exc())
            notify(plan,'independent_review_failed',f"予備実験の独立検証・最終報告処理で停止しました。異常: {type(error).__name__}。生成記録は保持。自動再生成・条件変更・commit/pushは行いません。ログ: {cache/'independent_review_error.log'}")
            raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);args=p.parse_args()
    raise SystemExit(watch(ROOT/args.output))
