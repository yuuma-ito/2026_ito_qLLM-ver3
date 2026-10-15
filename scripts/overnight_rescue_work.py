"""Supervise the authorized overnight analysis with reports at JST 00/03/... ."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from harness.run_state import ROOT, atomic_json, file_lock
from scripts.notify_progress import send_email

JST = ZoneInfo('Asia/Tokyo')
JOB = ROOT / '.cache/overnight_rescues_20261016'


def next_slot(now):
    local = now.astimezone(JST)
    return local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=3 - local.hour % 3)


def read_progress(job):
    try:
        progress = json.loads((job / 'progress.json').read_text())
        if not isinstance(progress, dict):
            return {'current_step': '進捗ファイルの形式を要確認'}
        return progress
    except FileNotFoundError:
        return {'current_step': 'Codex起動・対象データの確認'}
    except (ValueError, OSError):
        return {'current_step': '進捗ファイルの更新中または読み取り不備。ログ参照'}


def message(job, state, *, terminal=False):
    progress = read_progress(job)
    lines = ['介入救済分析・発表資料の夜間作業',
             f"報告時刻：{datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')}",
             f"状態：{state['status']}",
             f"現在：{progress.get('current_step', '詳細は進捗ファイルを参照')}"]
    for key, label in (('completed', '完了した作業'), ('findings', '確認できた結果'),
                       ('remaining', '残る作業・課題'), ('artifacts', '成果物')):
        items = progress.get(key, [])
        if items:
            lines.append(label + '：')
            lines.extend('- ' + str(item) for item in items)
    if progress.get('updated_at_utc'):
        lines.append('作業メモの更新UTC：' + progress['updated_at_utc'])
    if terminal:
        final = job / 'final_report.txt'
        if final.exists():
            lines += ['', '最終報告：', final.read_text()[:18000]]
        lines.append('この夜間作業の定期通知を終了します。')
    else:
        lines.append('定期報告：日本時間0:00・3:00・6:00・9:00・12:00・15:00・18:00・21:00。')
    lines += [f'作業記録：{job}', f"ログ：{state.get('log', '')}"]
    return '\n'.join(lines)


def notify_once(job, event, text, *, sender=send_email):
    """Persist intent before SMTP; uncertain delivery is never auto-retried."""
    ledger = job / 'notifications'
    ledger.mkdir(exist_ok=True)
    path = ledger / (event + '.json')
    with file_lock(path.with_suffix('.lock')):
        if path.exists():
            return json.loads(path.read_text())['status']
        state = dict(event=event, status='sending', attempted_at_utc=datetime.now(timezone.utc).isoformat())
        atomic_json(path, state)
        try:
            sender(text, 'overnight_rescues_20261016')
        except Exception as error:
            state.update(status='delivery_unconfirmed', exception_type=type(error).__name__)
        else:
            state.update(status='smtp_accepted', slack_delivery_confirmed=False)
        atomic_json(path, state)
        return state['status']


def completion_status(returncode, job):
    if returncode:
        return 'failed'
    try:
        completion = json.loads((job / 'completion.json').read_text())
        if completion.get('status') == 'completed' and completion.get('validation_passed') is True:
            artifacts = completion.get('required_artifacts', [])
            if not artifacts:
                return 'needs_review'
            resolved = []
            for name in artifacts:
                path = (ROOT / name).resolve()
                if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or path.stat().st_size == 0:
                    return 'needs_review'
                if path.suffix == '.pdf' and not path.read_bytes().startswith(b'%PDF-'):
                    return 'needs_review'
                resolved.append(path)
            if not {ROOT / 'docs/midterm2026/paper.pdf', ROOT / 'docs/winf2026/paper.pdf'} <= set(resolved):
                return 'needs_review'
            return 'completed'
    except (OSError, ValueError, TypeError):
        pass
    return 'needs_review'


def launch(job=JOB, codex='/home/23tc011/.local/bin/codex'):
    job.mkdir(parents=True, exist_ok=True, mode=0o700)
    with file_lock(job / 'supervisor.lock', nonblocking=True):
        state_path = job / 'supervisor.json'
        if state_path.exists():
            raise RuntimeError('Job was already launched; investigate before explicit manual retry')
        log = ROOT / 'logs/overnight_rescues_20261016_codex.log'
        log.parent.mkdir(exist_ok=True)
        env = os.environ.copy()
        for name in ('CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CODEX_PERMISSION_PROFILE'):
            env.pop(name, None)
        state = dict(status='starting', started_at_utc=datetime.now(timezone.utc).isoformat(),
                     log=str(log), interval_hours=3, timezone='Asia/Tokyo')
        atomic_json(state_path, state)
        due = next_slot(datetime.now(JST))
        with (job / 'prompt.txt').open() as prompt, log.open('a') as handle:
            try:
                child = subprocess.Popen([codex, 'exec', '--sandbox', 'workspace-write',
                    '--cd', str(ROOT), '--color', 'never',
                    '--output-last-message', str(job / 'final_report.txt'), '-'],
                    stdin=prompt, stdout=handle, stderr=subprocess.STDOUT, env=env)
            except OSError as error:
                state.update(status='failed_to_start', exception_type=type(error).__name__)
                atomic_json(state_path, state)
                raise
            # Mail credentials are loaded only after preparing the child's environment.
            load_dotenv(ROOT / '.env')
            state.update(status='running', worker_pid=child.pid, next_report_jst=due.isoformat())
            atomic_json(state_path, state)
            while child.poll() is None:
                now = datetime.now(JST)
                if now >= due:
                    event = 'periodic_' + due.strftime('%Y%m%dT%H%M')
                    if (now - due).total_seconds() < 90:
                        delivery = notify_once(job, event, message(job, state))
                    else:
                        delivery = 'missed_slot_no_late_delivery'
                    state.update(last_report_slot_jst=due.isoformat(), last_delivery=delivery)
                    due = next_slot(now)
                state.update(updated_at_utc=datetime.now(timezone.utc).isoformat(), next_report_jst=due.isoformat())
                atomic_json(state_path, state)
                time.sleep(5)
        state.update(status=completion_status(child.returncode, job), worker_exit_code=child.returncode,
                     finished_at_utc=datetime.now(timezone.utc).isoformat(), next_report_jst=None)
        atomic_json(state_path, state)
        state['terminal_delivery'] = notify_once(job, 'terminal', message(job, state, terminal=True))
        atomic_json(state_path, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    if args.preview:
        print(message(JOB, {'status': '準備中', 'log': 'logs/overnight_rescues_20261016_codex.log'}))
        print('次回：' + next_slot(datetime.now(JST)).isoformat())
    else:
        print(json.dumps(launch(), ensure_ascii=False))


if __name__ == '__main__':
    main()
