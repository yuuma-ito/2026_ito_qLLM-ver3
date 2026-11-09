"""Run once, verify, and publish only this experiment's authorized artifacts."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys

from harness.independent_4 import read_checkpoint
from harness.run_state import atomic_json, file_lock
from scripts.measurement_ban_sources import ROOT, sha
from scripts.run_notification_ablation import execute, assert_frozen
from scripts.finish_notification_ablation import verify_and_report


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, text=True, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


def update_report_status(plan, status):
    """Preserve handwritten sections and existing snapshot fields."""
    public = ROOT/plan['analysis_dir']
    snapshot = ROOT/'docs/experiment_report_snapshot.json'
    report = ROOT/'docs/experiment_report_draft.md'
    if snapshot.exists():
        current = json.loads(snapshot.read_text())
        entry = dict(run_id=plan['run_id'], status=status, source_dir=plan['output_dir'],
                     config=plan['output_dir']+'/experiment_config.json', analysis_dir=plan['analysis_dir'],
                     plan_sha256=plan['plan_sha256'], initial_failures=545, conditions=list(plan['conditions']),
                     stage1_requests=1635, max_total_requests=4905,
                     progress_source=plan['output_dir']+'/progress.json',
                     updated_at_utc=datetime.now(timezone.utc).isoformat(), provisional=status!='completed_verified')
        if status == 'completed_verified':
            entry['completion'] = read_checkpoint(public/'completion.json')
            entry['packet_verification_manifest_sha256'] = sha(public/'packet_verification/manifest.json')
        current['notification_ablation_current'] = entry
        atomic_json(snapshot, current)
    if report.exists():
        begin = '<!-- notification-ablation:begin -->'
        end = '<!-- notification-ablation:end -->'
        relative = str(public.relative_to(ROOT/'docs'))
        text = (begin+'\n\n失敗通知・詳細診断の3条件比較（'+plan['run_id']+'）。状態：'+status+'。'
                '共通の初期失敗545組をR0（通知なし）・R1（通知のみ）・R2（通知＋診断）で比較する。'
                '追加1回1635要求を主評価、最大3回4905要求を上限とする。'
                '旧R/F/Dとは指示文が異なる。旧実験や100組の予備実験とは別の出典として扱う。'
                '未完了・未検証の成績から結論を確定しない。'
                f' [保存計画]({relative}/experiment_plan.txt)・[保存設定](../{plan["output_dir"]}/experiment_config.json)。\n\n'+end)
        original = report.read_text()
        if begin in original:
            first, rest = original.split(begin,1)
            _, last = rest.split(end,1)
            updated = first+text+last
        else:
            updated = original.rstrip()+'\n\n'+text+'\n'
        report.write_text(updated)


def publication_paths(plan, public):
    paths = set(plan['implementation'])
    paths.update(str(p.relative_to(ROOT)) for p in public.rglob('*') if p.is_file())
    # The earlier read-only R analysis is the motivation/source for this experiment.
    for name in ('scripts/analyze_r_failure_paths.py', 'tests/test_r_failure_paths.py'):
        paths.add(name)
    directory = ROOT/'docs/analysis/r_failure_paths_20261106'
    paths.update(str(p.relative_to(ROOT)) for p in directory.iterdir() if p.is_file())
    directory = ROOT/plan['output_dir']
    for name in ('experiment_config.json', 'experiment_config.json.integrity.json', 'manifest.json',
                 'manifest.json.integrity.json', 'model_check_start.json', 'model_check_stage1.json',
                 'model_check_final.json'):
        paths.add(str((directory/name).relative_to(ROOT)))
    return sorted(paths)


def publish(plan, public, statepath):
    assert_frozen(plan, protected=True)
    paths = publication_paths(plan, public)
    forbidden = re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|Authorization:\s*Bearer\s+\S+', re.I)
    for name in paths:
        path = ROOT/name
        if any(part in ('.env', '.venv', '.cache', 'private', 'logs') for part in path.parts) or path.name == 'raw.jsonl':
            raise RuntimeError('Private file in publication selection')
        if forbidden.search(path.read_text()):
            raise RuntimeError('Potential secret in publication file: '+name)
    if git('diff', '--cached', '--name-only'):
        raise RuntimeError('Existing staged changes: publication stopped without touching them')
    report = dict(passed=True, run_id=plan['run_id'], status='verified_ready_to_publish',
                  checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  secrets_scan_passed=True, unrelated_changes_excluded=True,
                  packet_verification_manifest_sha256=sha(public/'packet_verification/manifest.json'),
                  published_files=paths)
    atomic_json(public/'automation_report.json', report)
    paths.append(str((public/'automation_report.json').relative_to(ROOT)))
    git('add', '-f', '--', *paths)
    staged = git('diff', '--cached', '--name-only').splitlines()
    if not set(staged) <= set(paths):
        raise RuntimeError('Unexpected staged file; no commit or push performed')
    git('diff', '--cached', '--check')
    if staged:
        git('-c', 'user.name=yuuma-ito', '-c', 'user.email=23tc011@tc.nanzan-u.ac.jp',
            'commit', '-m', 'data: 失敗通知と詳細診断の比較実験を検証して公開',
            '-m', '既存545初期失敗組に共通の自己点検指示を用い、通知と詳細診断の追加効果を比較。全予定枠と保存パケットを照合し、生の生成記録と無関係な変更は公開対象から除外した。')
    commit = git('rev-parse', 'HEAD')
    branch = git('branch', '--show-current')
    if not branch:
        raise RuntimeError('Detached HEAD; no push performed')
    atomic_json(statepath, dict(status='committed_push_pending', commit=commit, branch=branch))
    git('push', 'origin', branch)
    if git('ls-remote', 'origin', 'refs/heads/'+branch).split()[0] != commit:
        raise RuntimeError('Remote commit confirmation failed')
    atomic_json(statepath, dict(status='published', commit=commit, branch=branch,
                               finished_at_utc=datetime.now(timezone.utc).isoformat()))
    return commit


def complete(output):
    plan = read_checkpoint(output/'manifest.json')
    public = ROOT/plan['analysis_dir']
    cache = ROOT/'.cache'/plan['run_id']
    cache.mkdir(parents=True, exist_ok=True)
    statepath = cache/'completion_job.json'
    with file_lock(cache/'completion_job.lock', nonblocking=True):
        if statepath.exists():
            raise RuntimeError('Existing completion job: investigate before explicit recovery; no automatic retry')
        atomic_json(statepath, dict(status='running', run_id=plan['run_id']))
        try:
            update_report_status(plan, 'running_provisional')
            execute(output)
            checks = verify_and_report(output)
            if not checks['passed']:
                raise RuntimeError('Packet verification failed')
            update_report_status(plan, 'completed_verified')
            # Serialize publication, without holding the generation lock during long Git operations.
            with file_lock(ROOT/'.cache/notification_publication.lock', nonblocking=True):
                commit = publish(plan, public, statepath)
            print(json.dumps(dict(status='published', commit=commit, run_id=plan['run_id']), ensure_ascii=False), flush=True)
        except BaseException as error:
            previous = json.loads(statepath.read_text())
            atomic_json(statepath, dict(previous, status='stopped_for_review', exception_type=type(error).__name__,
                                        automatic_retry=False, stopped_at_utc=datetime.now(timezone.utc).isoformat()))
            if isinstance(error, subprocess.CalledProcessError):
                (cache/'git_error.txt').write_text(error.stderr or str(error))
            update_report_status(plan, 'stopped_for_review')
            raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output if args.output.is_absolute() else ROOT/args.output
    if not output.resolve().is_relative_to((ROOT/'results').resolve()) or not output.name.startswith('notification_ablation_'):
        raise ValueError('Notification experiment output directory required')
    complete(output)
