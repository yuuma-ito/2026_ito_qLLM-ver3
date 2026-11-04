"""Detached saved-code audit and explicitly requested Slackbot notification.

Never calls a model client or starts a generation/followup process. Sending
requires --notify; SMTP acceptance is not confirmation of Slack delivery.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import traceback

from dotenv import load_dotenv
from harness.run_state import atomic_json,file_lock
from scripts.audit_measurement_ban import run
from scripts.measurement_ban_sources import ROOT
from scripts.notify_progress import deliver

OUTPUT=ROOT/'docs/analysis/measurement_ban_impact_20261104'
PRIVATE=ROOT/'.cache/measurement_ban_impact_20261104'


def notify_once(event,text,*,private=PRIVATE,sender=None):
    private.mkdir(parents=True,exist_ok=True,mode=0o700)
    ledger=private/('notification_'+event+'.json')
    with file_lock(ledger.with_suffix('.lock'),nonblocking=True):
        if ledger.exists():return json.loads(ledger.read_text())['status']
        state={'status':'sending','event':event,'message_sha256':hashlib.sha256(text.encode()).hexdigest(),
               'started_at_utc':datetime.now(timezone.utc).isoformat(),'slack_delivery_confirmed':False}
        atomic_json(ledger,state)
        try:
            if sender is None:
                load_dotenv(ROOT/'.env')
                deliver(text,'測定禁止条件の影響調査','email')
            else:sender(text)
        except Exception as error:
            state.update(status='delivery_unconfirmed',failure_type=type(error).__name__)
        else:state.update(status='smtp_accepted',finished_at_utc=datetime.now(timezone.utc).isoformat())
        atomic_json(ledger,state)
        return state['status']


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--notify',action='store_true',help='authorized email-to-Slack start/final reports')
    args=p.parse_args(argv)
    PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with file_lock(PRIVATE/'detached_job.lock',nonblocking=True):
        job=PRIVATE/'job_state.json'
        if job.exists():
            print('existing job state; no automatic duplicate or retry',flush=True)
            return 1
        atomic_json(job,{'status':'running','started_at_utc':datetime.now(timezone.utc).isoformat(),
                         'new_model_requests':0,'automatic_followups':False})
        if args.notify:
            notify_once('started','測定禁止条件の影響調査をサーバーs3上で開始しました。保存済みL3成功コード×タスク1,561組を隔離再評価します。原課題の回路内測定禁止だけを追加し、新規モデル生成・自動部分追試は行いません。完了または停止時に件数と保存先を報告します。')
        try:
            result=run(OUTPUT,PRIVATE,workers=4)
            success=result.get('status')=='verified_impact_only'
        except BaseException as error:
            (PRIVATE/'failure_traceback.txt').write_text(traceback.format_exc())
            result={'status':'failed','failure_type':type(error).__name__,'new_model_requests':0}
            atomic_json(OUTPUT/'run_status.json',result)
            success=False
        state={**result,'finished_at_utc':datetime.now(timezone.utc).isoformat()}
        atomic_json(job,state)
        if success:
            text=(OUTPUT/'report.txt').read_text()+f'\n保存先：{OUTPUT}\n'
        else:
            text=('測定禁止条件の影響調査は停止・未確定です。\n'
                  f"状態：{result.get('status')}\n"
                  f"未解決件数：{result.get('unresolved_unique_code_tasks','未確定')}\n"
                  '成功数への確定的な影響は報告しません。新規モデル生成・部分追試は実施していません。\n'
                  f'保存先：{OUTPUT}\nログ：{PRIVATE}/detached.log\n')
        (PRIVATE/'notification_final_body.txt').write_text(text)
        if args.notify:
            status=notify_once('final',text)
            atomic_json(PRIVATE/'final_notification_status.json',{'status':status,'slack_delivery_confirmed':False})
            print('final notification status: '+status,flush=True)
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
        return 0 if success else 1


if __name__=='__main__':raise SystemExit(main())
