"""Build a local research status index without generation or network requests."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

from harness.run_state import ROOT, atomic_json, file_lock, observation, read_state


def history_path(root, channel):
    return root / '.cache/research_status' / (channel + '.json')


def read_history(root, channel):
    path = history_path(root, channel)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or any(not isinstance(p, dict) or
                not isinstance(p.get('recorded'), int) or
                not isinstance(p.get('observed_at'), (int, float)) for p in value.values()):
            raise ValueError('invalid history')
        return value
    except (OSError, ValueError):
        print('Observation history unreadable; comparison unavailable for this report.', file=sys.stderr)
        return {}


def trend(progress, previous, now):
    """Compare the same saved configuration and process; never extrapolate a stall."""
    result = dict(delta=None, elapsed_hours=None, records_per_hour=None, eta_hours=None)
    if not previous or previous.get('identity') != progress.get('identity'):
        return result
    elapsed = now - previous['observed_at']
    delta = progress['recorded'] - previous['recorded']
    if elapsed <= 0 or delta < 0:
        return result
    result.update(delta=delta, elapsed_hours=elapsed / 3600)
    if elapsed < 60 or progress.get('runtime_status') != 'running':
        return result
    result['records_per_hour'] = delta * 3600 / elapsed
    if (delta > 0 and progress['recorded'] < progress['planned']
            and not progress.get('issues') and not progress.get('planned_is_upper_bound')):
        result['eta_hours'] = (progress['planned'] - progress['recorded']) / result['records_per_hour']
    return result


def trend_text(p):
    if p.get('delta') is None:
        return '前回比較: 初回観測・設定変更・再開直後は算出なし'
    text = f"前回比較: {p['elapsed_hours']:.2f}時間で +{p['delta']}件"
    if p.get('records_per_hour') is not None:
        text += f"・{p['records_per_hour']:.1f}件/時"
    if p.get('eta_hours') is not None:
        text += f"・残り約{p['eta_hours']:.1f}時間（記録完了までの概算、検証・公開時間を除く）"
    else:
        text += '・完了見込みは算出なし'
    return text


def verification(output, names=('sanity_report.json', 'analysis/sanity_report.json', 'automation_report.json')):
    """Show report evidence separately from process completion or publication."""
    reports = {}
    for name in names:
        path = output / name
        if path.exists():
            try:
                value = json.loads(path.read_text()).get('passed')
                reports[name] = '成功' if value is True else '失敗' if value is False else '判定不明'
            except (OSError, ValueError, AttributeError):
                reports[name] = '読取失敗'
    return reports


def collect(root=ROOT, *, previous=None, now=None):
    from scripts.notify_progress import ACTIVE, snapshot
    now = time.time() if now is None else now
    previous = previous or {}
    items, outputs = [], set()
    results = (root / 'results').resolve()
    reviewed_path = root / 'configs/reviewed_experiments.json'
    reviewed = json.loads(reviewed_path.read_text()) if reviewed_path.exists() else {}
    for saved in sorted(results.glob('*/experiment_config.json')):
        output = saved.parent
        outputs.add(output)
        p = dict(experiment_id=output.name, output=str(output.relative_to(root)),
                 config=str(saved.relative_to(root)), recorded=0, planned=0,
                 runtime_status=None, last_update=None, runtime=None, issues=[])
        try:
            config = json.loads(saved.read_text())
            configured_output = (root / config.get('output_dir', str(output.relative_to(root)))).resolve()
            if configured_output != output:
                raise ValueError('saved output mismatch')
            if config.get('schema') in {'notification_ablation_v1', 'factorial_pilot_v1'}:
                runtime = read_state(output, root)
                progress_path = output / 'progress.json'
                progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
                status = observation(runtime) if runtime else None
                p.update(experiment_id=config['run_id'], runtime=runtime, runtime_status=status,
                         state=(status or progress.get('status', '実行未確認')) + '（要求数・上限、検証は別途確認）',
                         recorded=progress.get('completed_requests', progress.get('actual_requests', 0)),
                         planned=config['max_total_requests'], planned_is_upper_bound=True,
                         last_update=datetime.fromtimestamp(progress_path.stat().st_mtime).astimezone()
                         if progress_path.exists() else None)
            else:
                p.update(snapshot(config, root))
            p['verification'] = verification(output)
            if p.get('planned_is_upper_bound'):
                analysis = (root / config.get('analysis_dir', '__no_analysis__')).resolve()
                if analysis.is_relative_to((root / 'docs/analysis').resolve()):
                    p['verification'].update(verification(analysis, (
                        'stage1/validation_report.json', 'final/validation_report.json')))
                if p['verification'].get('final/validation_report.json') != '成功':
                    p['issues'].append('最終段階の検証レポート未確認または未成功')
            for key, label in (('api_failures', 'API障害'), ('unknown_failures', '未分類エラー'),
                               ('duplicates', '重複'), ('unexpected', '予定外記録')):
                if p.get(key):
                    p['issues'].append(f"{label} {p[key]}件")
            if p.get('pending_write'):
                p['issues'].append('末尾レコード書込中')
            if p['runtime_status'] in {'stalled', 'heartbeat_stale', 'failed', 'interrupted'}:
                p['issues'].append('実行状態の確認が必要')
            if (p['recorded'] < p['planned'] and p['runtime_status'] not in ACTIVE
                    and not (p.get('planned_is_upper_bound') and p['runtime_status'] == 'completed')):
                p['issues'].append('未完了・実行を確認できません')
            if any(v != '成功' for v in p['verification'].values()):
                p['issues'].append('検証レポートを確認してください')
            if p['recorded'] == p['planned'] and not p['verification']:
                p['issues'].append('検証レポート未確認')
            identity = json.dumps(config, sort_keys=True) + (p.get('runtime') or {}).get('token', '')
            p['identity'] = hashlib.sha256(identity.encode()).hexdigest()
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # Never copy arbitrary config, error text or generated code to reports.
            p.update(state='読取失敗・未対応形式または記録不整合', verification={}, identity=None)
            p['issues'].append('保存設定・記録形式を確認してください')
            try:
                runtime = read_state(output, root)
                if runtime:
                    p.update(runtime=runtime, runtime_status=observation(runtime))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        p['reviewed'] = p['experiment_id'] in reviewed
        p.update(trend(p, previous.get(p['output']), now))
        p['observed_at'] = now
        items.append(p)
    for path in sorted((root / '.cache/run_states').glob('*.json')):
        try:
            runtime = json.loads(path.read_text())
            output = Path(runtime['output']).resolve()
            if not output.is_relative_to(results) or output in outputs or observation(runtime) not in ACTIVE:
                continue
            items.append(dict(experiment_id=runtime['experiment_id'], output=str(output.relative_to(root)),
                              config=None, recorded=0, planned=0, state='保存設定作成前',
                              runtime_status=observation(runtime), runtime=runtime, last_update=None,
                              verification={}, issues=['保存設定の作成待ち'], reviewed=False,
                              identity=None, observed_at=now, **trend({}, None, now)))
        except (OSError, ValueError, KeyError, TypeError):
            # Retain a visible warning instead of silently dropping a broken state.
            items.append(dict(experiment_id=path.stem, output='', config=None, recorded=0, planned=0,
                              state='実行状態の読取失敗', runtime_status=None, runtime=None,
                              last_update=None, verification={}, issues=['実行状態ファイルを確認してください'],
                              reviewed=False, identity=None, observed_at=now, **trend({}, None, now)))
    return sorted(items, key=lambda p: (p['runtime_status'] not in ACTIVE, not bool(p['issues']), p['experiment_id']))


def save_history(items, root, channel):
    atomic_json(history_path(root, channel), {p['output']: {key: p[key] for key in
                ('identity', 'recorded', 'observed_at')} for p in items if p.get('identity')})


def serializable(items):
    # Explicit allowlist: runtime state and raw config are deliberately excluded.
    keys = ('experiment_id', 'output', 'config', 'recorded', 'planned', 'state', 'runtime_status',
            'verification', 'issues', 'reviewed', 'delta', 'elapsed_hours', 'records_per_hour', 'eta_hours',
            'planned_is_upper_bound')
    return [{**{k: p.get(k) for k in keys},
             'last_update': p['last_update'].isoformat() if p.get('last_update') else None} for p in items]


def markdown(items, now, root=ROOT):
    from scripts.notify_progress import ACTIVE
    def escape(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')
    lines = ['# 研究・実験の状況', '', f"更新: {datetime.fromtimestamp(now, ZoneInfo('Asia/Tokyo')):%Y-%m-%d %H:%M:%S %Z}", '',
             '保存設定と実行状態から作成。検証レポートの表示は既存の判定であり、再検証ではありません。',
             '完了見込みは観測間の件数から推定し、モデル・条件の変化で変動します。', '',
             '| 実験 | 状態 | 記録 | 前回との差・速度・見込み | 検証 | 要確認 |',
             '|---|---|---:|---|---|---|']
    for p in items:
        if p['reviewed'] and p['runtime_status'] not in ACTIVE:
            continue
        output = root / p['output']
        link = output / 'experiment_config.json' if p['config'] else output
        name = f"[{escape(p['experiment_id'])}](<{link}>)"
        checks = '・'.join(f'{k}: {v}' for k, v in p['verification'].items()) or '未確認'
        count = f"{p['recorded']}/{p['planned']}" if p['identity'] else '未確認'
        if p.get('planned_is_upper_bound'):
            count += '要求（上限）'
        lines.append('| ' + ' | '.join((name, escape(p['state']), count,
                     escape(trend_text(p)), escape(checks), escape('・'.join(p['issues']) or 'なし'))) + ' |')
    lines += ['', '確認済みの過去実験もJSONには残します。実行完了、検証成功、Git公開は別の状態です。', '',
              f'[実験レポート](<{root / "docs/experiment_report_draft.md"}>)', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.cache/research_status')
    parser.add_argument('--dry-run', action='store_true', help='Print without changing files or observation history')
    args = parser.parse_args(argv)
    try:
        with file_lock(history_path(ROOT, 'dashboard').with_suffix('.lock')):
            now = time.time()
            items = collect(ROOT, previous=read_history(ROOT, 'dashboard'), now=now)
            text = markdown(items, now)
            if args.dry_run:
                print(text)
            else:
                args.output_dir.mkdir(parents=True, exist_ok=True)
                atomic_json(args.output_dir / 'status.json', dict(updated_at=now, experiments=serializable(items)))
                temporary = args.output_dir / 'status.md.tmp'
                temporary.write_text(text, encoding='utf-8')
                temporary.replace(args.output_dir / 'status.md')
                save_history(items, ROOT, 'dashboard')
                print(args.output_dir / 'status.md')
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('Research status update failed; check local settings and records.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
