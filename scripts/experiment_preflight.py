"""Check a saved/new experiment plan locally, without model or server requests."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from harness.experiment import build_manifest, expected_keys, load_config, validate_config
from harness.research_registry import compatibility, local_path, model_digests, read_json, sha256
from harness.run_state import ROOT, atomic_json, observation, read_state


def check(config, root=ROOT, *, new_run=False, resume=False, model_snapshot=None):
    if new_run and resume:
        raise ValueError('new-run and resume are exclusive')
    plan = validate_config(config)
    # These checks describe the standard harness. Specialized schemas have dedicated checks.
    if config.get('schema') or config.get('condition_id') == 'independent_4':
        raise ValueError('Specialized plan requires its dedicated validator')
    blockers, warnings, overlaps, estimates = [], [], [], []
    output = local_path(root, config.get('output_dir', f"results/{plan['experiment_id']}"))
    if not output.is_relative_to((root / 'results').resolve()) or output == (root / 'results').resolve():
        blockers.append('出力先はresults内の実験専用ディレクトリにしてください')
    if output.exists() and not new_run and not resume:
        blockers.append('出力先が存在します。保存設定でのresumeか、新しい追試IDを指定してください')
    if resume:
        saved = output / 'experiment_config.json'
        if not saved.exists() or read_json(root, saved) != config:
            blockers.append('resumeの設定が保存設定と一致しません')
        else:
            from scripts.notify_progress import snapshot
            progress = snapshot(config, root)
            if any(progress.get(k) for k in ('api_failures', 'unknown_failures', 'duplicates', 'unexpected', 'pending_write')):
                blockers.append('既存記録にAPI障害・未分類エラー・記録不整合があります。別実験での追試を確認してください')
    for path in (root / '.cache/run_states').glob('*.json'):
        try:
            runtime = read_json(root, path)
            if observation(runtime) in {'running', 'stalled', 'heartbeat_stale'}:
                blockers.append('稼働中の実験があります。共有サーバの重複実行を確認してください')
                break
        except (OSError, ValueError, KeyError, TypeError):
            warnings.append('読み取れない実行状態があります')
    current_manifest = build_manifest(config, root)
    digest_evidence = None
    if model_snapshot:
        current_manifest['model_digests'] = model_digests(read_json(root, model_snapshot))
        digest_evidence = dict(path=str(model_snapshot), sha256=sha256(local_path(root, model_snapshot)))
        warnings.append('モデルdigestは指定した保存スナップショットによる宣言値です。サーバの現時点の状態は未確認です')
    desired = {key[1:] for key in expected_keys(plan)}
    for saved in sorted((root / 'results').glob('*/experiment_config.json')):
        try:
            previous = load_config(saved)
            if previous.get('schema') or previous.get('condition_id') == 'independent_4':
                continue
            old_plan = validate_config(previous)
            if saved.parent == output and resume:
                continue
            common = desired & {key[1:] for key in expected_keys(old_plan)}
            if not common:
                continue
            manifest_path = saved.parent / 'manifest.json'
            manifest = read_json(root, manifest_path) if manifest_path.exists() else {}
            automation_path = saved.parent / 'automation_report.json'
            automation = read_json(root, automation_path) if automation_path.exists() else {}
            manifest = dict(manifest, model_digests=model_digests(manifest) or model_digests(automation))
            compared = compatibility(config, current_manifest, previous, manifest)
            item = dict(experiment_id=old_plan['experiment_id'], config=str(saved.relative_to(root)),
                        overlapping_condition_records=len(common),
                        overlapping_initial_groups=len({(key[1], key[2], key[3]) for key in common}),
                        configuration_comparison=compared)
            overlaps.append(item)
            # Use measured whole-run wall time only for fully matching workloads and evidence.
            elapsed = manifest.get('elapsed_sec')
            if (compared['status'] == 'matched' and old_plan['pair_keys'] == plan['pair_keys']
                    and manifest.get('sanity_passed') is True and automation.get('passed') is True
                    and isinstance(elapsed, (float, int)) and math.isfinite(elapsed) and elapsed > 0):
                estimates.append(dict(experiment_id=old_plan['experiment_id'], hours=elapsed / 3600,
                                      manifest_sha256=sha256(manifest_path)))
        except (OSError, ValueError, KeyError, TypeError):
            warnings.append('比較対象の保存設定またはmanifestが未対応・不整合: ' + saved.parent.name)
    if overlaps:
        warnings.append('既存実験と対象組が重複します。意図した追試・再現か確認してください')
    if not estimates:
        warnings.append('一致する条件・評価版・モデルdigestの検証済み壁時計時間がなく、所要時間は算出しません')
    groups = plan['planned_initial_generations']
    # Shared initial generation plus each repair's upper bound; preventive generates separately.
    upper = groups * (1 + sum(1 if c.intervention == 'preventive_spec' else c.max_rounds
                              for c in plan['conditions'] if c.intervention != 'baseline'))
    return dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), passed=not blockers,
                experiment_id=plan['experiment_id'], mode='new_run' if new_run else 'resume' if resume else 'new',
                output=str(output.relative_to(root)), new_output_required=new_run, model_digest_evidence=digest_evidence,
                planned_condition_records=plan['planned_records'], planned_initial_groups=groups,
                model_request_upper_bound=upper, overlaps=overlaps, blockers=blockers, warnings=warnings,
                duration_estimate=dict(status='reference_only' if estimates else 'unavailable',
                    lower_hours=min((p['hours'] for p in estimates), default=None),
                    upper_hours=max((p['hours'] for p in estimates), default=None), sources=estimates),
                limits=['ローカル計画チェックのみ。サーバ到達性・モデルの現在digest・API認証は未確認。',
                        'モデル・タスク・seed・条件の重複は、生成コードの同一性を意味しない。',
                        '実験の起動・追試設定生成・Git操作は行わない。時間参考値は検証・公開時間を含まない。'],
                new_model_requests=0)


def markdown(report):
    lines = ['# 実験前の計画チェック', '',
             '判定: ' + ('実行を妨げる問題なし（警告・未確認事項は下記）' if report['passed'] else '要修正'), '',
             f"実験: {report['experiment_id']} / モード: {report['mode']}",
             f"予定: {report['planned_initial_groups']}初期組・{report['planned_condition_records']}条件記録・最大{report['model_request_upper_bound']}モデル要求", '',
             '## 実行を妨げる問題', '']
    lines += ['- ' + item for item in report['blockers']] or ['なし']
    lines += ['', '## 警告・未確認', ''] + ['- ' + item for item in report['warnings']]
    lines += ['', '## 既存実験との重複・比較条件', '']
    for item in report['overlaps']:
        c = item['configuration_comparison']
        lines.append(f"- {item['experiment_id']}: {item['overlapping_condition_records']}条件記録の対象が重複 / 設定比較 {c['status']} / 差異 {','.join(c['different']) or 'なし'} / 未確認 {','.join(c['unknown']) or 'なし'}")
    d = report['duration_estimate']
    lines += ['', '所要時間: ' + (f"過去実測 {d['lower_hours']:.2f}〜{d['upper_hours']:.2f}時間（参考）"
                               if d['sources'] else '算出なし'), '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--new-run', action='store_true')
    mode.add_argument('--resume', action='store_true')
    parser.add_argument('--out-dir', type=Path, default=ROOT / '.cache/experiment_preflight')
    parser.add_argument('--model-snapshot', help='Repository-local saved model digest/automation JSON; never a live server check')
    args = parser.parse_args(argv)
    try:
        report = check(load_config(args.config), ROOT, new_run=args.new_run, resume=args.resume, model_snapshot=args.model_snapshot)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(args.out_dir / 'report.json', report)
        text = markdown(report)
        (args.out_dir / 'report.md').write_text(text, encoding='utf-8')
        print(text)
        return 0 if report['passed'] else 1
    except (OSError, ValueError, KeyError, TypeError):
        print('Plan check failed; use a valid standard configuration or its dedicated preflight validator.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
