"""Start Codex once after the saved experiment has finished collecting records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from dotenv import load_dotenv

from harness.experiment import load_config, load_existing, expected_keys, record_key, validate_config
from harness.run_state import ROOT, atomic_json, file_lock, process_identity, read_state
from scripts.automate_experiment import experiment_lock, output_path
from scripts.sanity_check import check_results
from scripts.update_experiment_report import collect_run

REQUIRED = (
    'midterm2026/paper.tex', 'midterm2026/paper.pdf',
    'midterm2026/progress_report_draft.txt', 'midterm2026/README.md',
    'winf2026/paper.tex', 'winf2026/paper.pdf', 'winf2026/abstract.txt',
    'winf2026/progress_report_draft.txt', 'winf2026/README.md',
)


def gate(config, root=ROOT):
    output = output_path(config, root)
    state = read_state(output, root)
    if not state or state.get('experiment_id') != config['experiment_id']:
        return 'blocked', 'Matching run state is required.'
    if state.get('process_identity') and process_identity(state['pid']) == state['process_identity']:
        return 'waiting', 'Experiment process is still alive.'
    try:
        with experiment_lock(root):
            rows, _ = load_existing(output / 'raw.jsonl')
            keys = [record_key(row) for row in rows]
            expected = expected_keys(validate_config(config))
            if len(keys) != len(set(keys)) or set(keys) - expected:
                return 'blocked', 'Duplicate or unexpected records.'
            if any(row.get('experiment_id') != config['experiment_id'] for row in rows):
                return 'blocked', 'Mixed experiment IDs.'
            if set(keys) != expected:
                return 'waiting', 'Collection is incomplete; no AI was started.'
            raw = output / 'raw.jsonl'
            if not raw.read_bytes().endswith(b'\n'):
                return 'waiting', 'Final record is not yet fully written.'
            sanity = check_results(config, raw)
            run = collect_run(dict(experiment_id=config['experiment_id'],
                                   source_dir=str(output.relative_to(root)), recorded=0), root)
            verified = run['automation_verified'] and sanity['passed'] and not sanity['warnings']
            return ('ready' if verified else 'ready_provisional'), run
    except RuntimeError as exc:
        if 'Another automated experiment' in str(exc):
            return 'waiting', 'Experiment lock is held.'
        raise


def prepare_workspace(config, run, root):
    key = hashlib.sha256(str(output_path(config, root)).encode()).hexdigest()[:24]
    workspace = root / 'docs' / 'completion_drafts' / key
    workspace.mkdir(parents=True, exist_ok=True)
    # Copy sources, not obsolete PDFs: every required artifact must be produced.
    for name in ('midterm2026', 'winf2026'):
        source = root / 'docs' / name
        dest = workspace / 'reference' / name
        shutil.copytree(source, dest, dirs_exist_ok=True)
        (workspace / name).mkdir(exist_ok=True)
        for style in source.glob('*.sty'):
            shutil.copy2(style, workspace / name / style.name)
    shutil.copy2(root / 'docs' / 'experiment_report_draft.md', workspace / 'reference' / 'experiment_report_draft.md')
    previous = json.loads((root / 'docs' / 'experiment_report_snapshot.json').read_text())
    snapshot = dict(previous, captured_at=datetime.now(timezone.utc).isoformat(),
                    runs=[collect_run(item, root) for item in previous['runs']])
    if not any(item['experiment_id'] == config['experiment_id'] for item in snapshot['runs']):
        snapshot['runs'].append(run)
    atomic_json(workspace / 'results_snapshot.json', snapshot)
    return workspace


def prompt(config, workspace, readiness, root):
    return f"""ユーザーの依頼：実験完了後の新データで中間発表資料と進捗報告をAIで下書きし共有用に整え、学会発表を準備する。
対象実験: {config['experiment_id']}
保存設定: {output_path(config, root) / 'experiment_config.json'}
検証状態: {readiness}。ready_provisionalの場合はAPI障害や検証不備を明記し、検証済み3モデルを主分析とする。
作業先は現在のディレクトリ {workspace} のみ。reference/ の中間発表・WiNF原稿を基に、
midterm2026/ と winf2026/ にそれぞれ paper.tex, paper.pdf, progress_report_draft.txt, README.mdを新規作成し、
winf2026/abstract.txt（300字以内）も作成する。reference/は変更せず、既存原稿の更新版はこの作業先に保存する。
results_snapshot.jsonが今回の固定集計の出典。主分析3モデル1,500件と追加5モデル2,500件はseed・設定が違うので合算しない。
背景、目的、方法、モデル別・条件別結果、失敗類型と介入効果、限界、次回までのアクションを記載する。
必要に応じて元リポジトリの集計CSV・介入カタログを読み、出典と検証状態を明記する。
旧資料の120件は既報として区別し、途中の19件など古い値は最新の固定集計に置き換える。
集計だけで統計的有意差やモデルの一般的優劣を断定しない。生成コードの実行、追加実験、投稿、通知、Git操作は行わない。
元リポジトリのユーザー変更を編集しない。.envや認証ファイルを読まない。共有は起動スクリプトが担当する。
platexを2回、dvipdfmxを実行してPDFを作成し、引用・参照、はみ出し、フォント、本文と集計数値の一致を確認する。
構造化最終応答で status=completed は全ファイルと検証が揃った場合のみ。失敗ならstatus=failed、summaryに理由を記載する。
"""


def notify(config, text, transport, root):
    if transport != 'none':
        from scripts.notify_progress import deliver
        load_dotenv(root / '.env')
        deliver(text, config['experiment_id'], transport)


def launch(config, *, root=ROOT, codex='codex', transport='email', dry_run=False,
           timeout=7200, retry=False):
    output = output_path(config, root)
    key = hashlib.sha256(str(output).encode()).hexdigest()[:24]
    state_path = root / '.cache' / 'draft_jobs' / (key + '.json')
    try:
        lock = file_lock(state_path.with_suffix('.lock'), nonblocking=True)
        lock.__enter__()
    except RuntimeError:
        return dict(status='running', detail='Another draft worker holds the lock.')
    try:
        previous = json.loads(state_path.read_text()) if state_path.exists() else {}
        if previous.get('status') == 'completed' or (
                previous.get('status') in {'attempting', 'failed'} and not retry):
            return previous
        readiness, detail = gate(config, root)
        state = dict(experiment_id=config['experiment_id'], status=readiness,
                     updated_at=datetime.now(timezone.utc).isoformat())
        if readiness not in {'ready', 'ready_provisional'}:
            state['detail'] = detail
            if not dry_run:
                atomic_json(state_path, state)
            return state
        if dry_run:
            return dict(state, detail='Would start Codex once; no generation or notification.')
        workspace = prepare_workspace(config, detail, root)
        state.update(status='attempting', readiness=readiness, workspace=str(workspace))
        atomic_json(state_path, state)  # Crash/timeout must not cause automatic duplicate runs.
        schema = dict(type='object', properties={
            'status': dict(type='string', enum=['completed', 'failed']),
            'summary': dict(type='string')}, required=['status', 'summary'], additionalProperties=False)
        atomic_json(workspace / 'response_schema.json', schema)
        response_path = workspace / 'ai_response.json'
        response_path.unlink(missing_ok=True)
        log = root / 'logs' / ('draft_codex_' + key + '.log')
        log.parent.mkdir(parents=True, exist_ok=True)
        try:
            env = os.environ.copy()
            # App-session settings should not leak into the independent cron agent.
            for name in ('CODEX_THREAD_ID', 'CODEX_SESSION_ID', 'CODEX_PERMISSION_PROFILE'):
                env.pop(name, None)
            with log.open('a') as handle:
                subprocess.run([codex, 'exec', '--sandbox', 'workspace-write',
                    '--cd', str(workspace), '--color', 'never',
                    '--output-schema', str(workspace / 'response_schema.json'),
                    '--output-last-message', str(response_path), '-'],
                    input=prompt(config, workspace, readiness, root), text=True,
                    stdout=handle, stderr=subprocess.STDOUT, env=env, timeout=timeout, check=True)
            response = json.loads(response_path.read_text())
            if response.get('status') != 'completed':
                raise RuntimeError('Codex did not report completed drafts.')
            for name in REQUIRED:
                path = workspace / name
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError('Required draft artifact is missing.')
                if path.suffix == '.pdf' and not path.read_bytes().startswith(b'%PDF-'):
                    raise RuntimeError('Invalid PDF artifact.')
            state.update(status='completed', files=[str(workspace / n) for n in REQUIRED])
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            state.update(status='failed', failure_type=type(exc).__name__, log=str(log))
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        atomic_json(state_path, state)
        # Record before attempting delivery: an uncertain SMTP response is not retried.
        state['notification'] = 'attempting' if transport != 'none' else 'disabled'
        atomic_json(state_path, state)
        text = ('発表資料・進捗報告のAI下書き作成完了' if state['status'] == 'completed'
                else '発表資料のAI下書き作成失敗（自動再実行なし）')
        text += f"\n実験: {config['experiment_id']}\n検証状態: {readiness}\n保存先: {workspace}"
        if state['status'] == 'completed':
            text += '\n\n' + (workspace / 'midterm2026' / 'progress_report_draft.txt').read_text()[:8000]
        else:
            text += f'\nログ: {log}'
        try:
            notify(config, text, transport, root)
            state['notification'] = 'accepted' if transport != 'none' else 'disabled'
        except (OSError, ValueError, RuntimeError, KeyError):
            state['notification'] = 'failed'
        atomic_json(state_path, state)
        return state
    finally:
        lock.__exit__(None, None, None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--codex', default='codex')
    parser.add_argument('--transport', choices=['none', 'email', 'slack'], default='email')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--retry', action='store_true', help='Explicitly retry a failed or interrupted AI job.')
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    source = Path(args.config).resolve()
    config = load_config(source)
    if source != output_path(config) / 'experiment_config.json':
        parser.error('Use the existing experiment saved configuration.')
    try:
        state = launch(config, codex=args.codex, transport=args.transport,
                       dry_run=args.dry_run, timeout=args.timeout, retry=args.retry)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 1 if state['status'] in {'failed', 'blocked'} or state.get('notification') == 'failed' else 0
    except (OSError, ValueError, RuntimeError, KeyError):
        print('Draft launcher failed; check local configuration and runtime state.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
