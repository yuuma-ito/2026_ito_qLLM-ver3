"""Adapt B4's separate schema to the existing Slack progress/monitor interface."""
from collections import Counter
from datetime import datetime
import json
from pathlib import Path

from harness.independent_4 import identity, validate_config
from harness.run_state import read_state, observation


def snapshot(config, root):
    expected=validate_config(config)
    output=root/config['output_dir']
    raw=output/'raw.jsonl'
    records=[];pending=False
    if raw.exists():
        with raw.open('rb') as f:
            for line in f:
                if not line.endswith(b'\n'):
                    pending=True;break
                if line.strip():records.append(json.loads(line))
    counts=Counter(identity(r) for r in records)
    valid={identity(r):r for r in records if identity(r) in expected
           and r.get('condition_id')=='independent_4' and r.get('experiment_id')==config['experiment_id']}
    duplicates=sum(n-1 for n in counts.values())
    unexpected=len(records)-sum(1 for r in records if identity(r) in expected
                               and r.get('condition_id')=='independent_4' and r.get('experiment_id')==config['experiment_id'])
    passed=sum(r['final_success'] for r in valid.values())
    unknown=sum(any(a.get('primary',{}).get('error_category')=='unknown_error'
                    for a in r.get('rounds',[])[1:]) for r in valid.values())
    complete=set(valid)==expected and not (duplicates or unexpected or pending)
    state='未開始' if not raw.exists() else '未完了（B4）'
    if complete:state='記録完了・検証待ち'
    sanity=output/'analysis/sanity_report.json'
    if complete and sanity.exists():
        state='記録完了・自動検証成功' if json.loads(sanity.read_text()).get('passed') else '記録完了・自動検証失敗'
    runtime=read_state(output,root)
    status=observation(runtime) if runtime else None
    if status:
        labels={'running':'実行中','completed':'完了','failed':'失敗','interrupted':'中断',
                'stalled':'実行中・長時間進捗なし','heartbeat_stale':'状態更新の停滞'}
        state=labels[status]+'（B4・'+runtime.get('phase','unknown')+'）'
    return dict(experiment_id=config['experiment_id'],state=state,planned=len(expected),recorded=len(valid),
                primary_level='L3',passed_L3=passed,failed_L3=len(valid)-passed,
                api_failures=0,unknown_failures=unknown,duplicates=duplicates,unexpected=unexpected,pending_write=pending,
                runtime_status=status,runtime=runtime,
                last_update=datetime.fromtimestamp(raw.stat().st_mtime).astimezone() if raw.exists() else None)
