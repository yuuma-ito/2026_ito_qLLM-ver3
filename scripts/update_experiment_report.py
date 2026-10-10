"""Refresh report data from existing runs without generating code or sending messages."""
from __future__ import annotations

from harness.failure_metadata import normalize_record

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from harness.experiment import expected_keys, has_api_failure, record_key, validate_config
from harness.run_state import ROOT, atomic_json, file_lock

REPORT = Path('docs/experiment_report_draft.md')
SNAPSHOT = Path('docs/experiment_report_snapshot.json')


def collect_run(previous, root):
    output = (root / previous['source_dir']).resolve()
    if not output.is_relative_to((root / 'results').resolve()):
        raise ValueError('Report sources must be under results/')
    config = json.loads((output / 'experiment_config.json').read_text())
    if config['experiment_id'] != previous['experiment_id']:
        raise ValueError('Report source identity changed')
    expected = expected_keys(validate_config(config))
    raw = output / 'raw.jsonl'
    with raw.open('rb') as handle:
        data = handle.read()
        # Record the timestamp of this read, rather than a later writer update.
        import os
        modified = os.fstat(handle.fileno()).st_mtime
    rows = [normalize_record(json.loads(line)) for line in data.splitlines(keepends=True)
            if line.endswith(b'\n') and line.strip()]
    counts = Counter(record_key(row) for row in rows)
    unexpected = sum(n for key, n in counts.items() if key not in expected)
    duplicates = sum(n - 1 for n in counts.values())
    if unexpected or duplicates:
        raise ValueError('Duplicate or unexpected records; report preserved')
    if len(rows) < previous['recorded']:
        raise ValueError('Source records decreased; report preserved')
    pending = bool(data and not data.endswith(b'\n'))
    api_failures = sum(has_api_failure(row) for row in rows)
    report_path = output / 'automation_report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    sanity_path = output / 'sanity_report.json'
    sanity = json.loads(sanity_path.read_text()) if sanity_path.exists() else {}
    verified = (len(rows) == len(expected) and not pending and not api_failures
                and report.get('passed') is True and sanity.get('passed') is True
                and sanity.get('experiment_id') == config['experiment_id'])
    conditions = []
    for model in config['models']:
        for condition in config['conditions']:
            selected = [row for row in rows if row['model_spec'] == model
                        and row['condition_id'] == condition]
            if selected:
                conditions.append({'model': model, 'condition': condition, 'n': len(selected),
                                   'L2_success': sum(row['L2'] is True for row in selected),
                                   'L3_success': sum(row['L3'] is True for row in selected),
                                   'api_failure_records': sum(has_api_failure(row) for row in selected)})
    return dict(previous, config=config, raw_sha256_at_capture=hashlib.sha256(data).hexdigest(),
                raw_bytes_at_capture=len(data), last_record_at=datetime.fromtimestamp(
                    modified, ZoneInfo('Asia/Tokyo')).isoformat(),
                planned=len(expected), recorded=len(rows),
                L2_success=sum(row['L2'] is True for row in rows),
                L2_failure=sum(row['L2'] is False for row in rows),
                api_failure_records=api_failures, duplicates=duplicates, unexpected=unexpected,
                missing=len(expected) - len(rows), pending_write=pending, automation_verified=verified,
                records_by_model=dict(Counter(row['model_spec'] for row in rows)),
                records_by_task=dict(Counter(row['task_id'] for row in rows)),
                final_error_counts=dict(Counter(row['error_category'] for row in rows)),
                failure_classification_version='stage-cause-v1',
                original_final_error_counts=dict(Counter(row.get('original_error_category', row['error_category']) for row in rows)),
                failure_stage_counts=dict(Counter(row['failure_stage'] for row in rows if row['error_category'] not in {'ok', ''})),
                conditions=conditions)


def replace_block(text, name, body):
    start, end = f'<!-- auto:{name}:start -->', f'<!-- auto:{name}:end -->'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('Report update markers missing or duplicated')
    pattern = re.escape(start) + r'.*?' + re.escape(end)
    result, count = re.subn(pattern, lambda _: start + '\n' + body + '\n' + end,
                          text, flags=re.DOTALL)
    if count != 1:
        raise ValueError('Report update marker order invalid')
    return result


def full_results(run, captured_at):
    verified = run['automation_verified']
    text = [f"## 4 本実験の{'検証済み結果' if verified else '記録状況と暫定結果'}", '',
            f"{captured_at[:19].replace('T', ' ')}（日本時間）時点で、予定{run['planned']:,}件のうち"
            f"{run['recorded']:,}件（{100 * run['recorded'] / run['planned']:.1f}%）を記録した。"
            f"残りは{run['missing']:,}件である。L2成功は{run['L2_success']}件、"
            f"L2失敗は{run['L2_failure']}件、API障害を含む記録は{run['api_failure_records']}件であった。"
            f"重複は{run['duplicates']}件、予定外記録は{run['unexpected']}件であった。", '',
            '自動検証とsanity checkが成功し、API障害を含む記録はなかった。' if verified else
            '本実験は未検証のため、以下の数値は暫定結果である。全件の記録とsanity check・API障害確認を終えるまで、最終結果として扱わない。', '',
            '| モデル | 記録件数 | 予定件数 |', '| --- | --- | --- |']
    plan = validate_config(run['config'])
    model_planned = Counter(key[2] for key in expected_keys(plan))
    for model in run['config']['models']:
        text.append(f"| {model.removeprefix('ollama:')} | {run['records_by_model'].get(model, 0)} | {model_planned[model]} |")
    text += ['', '### 条件別のL2とL3成功件数', '',
             '| モデル | 条件 | 記録件数 | L2成功 | L3成功 | API障害を含む記録 |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in run['conditions']:
        text.append(f"| {row['model'].removeprefix('ollama:')} | {row['condition']} | {row['n']} | {row['L2_success']} | {row['L3_success']} | {row['api_failure_records']} |")
    text += ['', '未完了のモデル・タスク・条件には件数の偏りがある。途中データからモデル全体の優劣を判断しない。', '',
             '### タスク別の記録件数', '', '| タスク | 記録件数 |', '| --- | --- |']
    for task in run['config']['tasks']:
        text.append(f"| {task} | {run['records_by_task'].get(task, 0)} |")
    text += ['', '### 最終評価の類型別件数', '', '| 類型 | 件数 |', '| --- | --- |']
    for category, n in sorted(run['final_error_counts'].items()):
        text.append(f'| {category} | {n} |')
    text += ['', 'API障害を含む記録件数はround履歴も確認した値であり、最終評価の失敗類型とは別の集計である。API障害がある場合は、元結果を保持し、対応条件をそろえた追試を別実験として報告する。']
    if run['pending_write']:
        text += ['', '書き込み途中の末尾行は今回の集計から除外した。']
    return '\n'.join(text)


def render_report(original, previous, current):
    runs, captured = current['runs'], current['captured_at']
    primary = current.get('primary_full_experiment_id')
    full = next(run for run in runs if (run['experiment_id'] == primary if primary else
                                       run['experiment_id'].startswith('shared_three_models_full')))
    quick = [run for run in runs if run['experiment_id'].startswith('shared_three_models_quick')]
    classification_fields = {'failure_stage_counts', 'failure_classification_version', 'original_final_error_counts'}
    for before, after in zip(previous['runs'], runs):
        if not before['experiment_id'].startswith('shared_three_models_quick'):
            continue
        # Permit only the deterministic first migration of cause counts; measured
        # results, input hashes and all previously captured metadata remain fixed.
        migrated_counts = (not before.get('failure_classification_version') and
                           before.get('final_error_counts') == after.get('original_final_error_counts'))
        changed = any(after.get(k) != value for k, value in before.items()
                      if not (k == 'final_error_counts' and migrated_counts))
        if changed or set(after) - set(before) - classification_fields:
            raise ValueError('Completed quick results changed; review prose before updating')
    intro = f"簡易実験は{len(quick)}回完了した。本実験は"
    intro += ('全件記録と自動検証が完了した。モデル間・難度間の比較の考察は、検証済み結果に基づいて追記する。'
              if full['automation_verified'] else
              '未検証であり、モデル間・難度間の比較に関する結論は、全件記録と検証後に確定する。')
    capture_text = f"集計時点：{captured[:19].replace('T', ' ')} JST。数値は最終更新時点の値であり、60分ごと（毎時0分）に自動更新する。[集計スナップショット](experiment_report_snapshot.json)に同じ時点の件数と出典を保存する。"
    updated = replace_block(original, 'status', intro)
    updated = replace_block(updated, 'capture', capture_text)
    return replace_block(updated, 'full-results', full_results(full, captured))


def update_report(root=ROOT):
    with file_lock(root / '.cache' / 'experiment_report.lock'):
        previous = json.loads((root / SNAPSHOT).read_text())
        runs = [collect_run(run, root) for run in previous['runs']]
        captured = datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()
        current = dict(previous, captured_at=captured, runs=runs)
        path = root / REPORT
        original = path.read_text()
        updated = render_report(original, previous, current)
        # Serialize all content before any writes, and preserve manual prose outside marked blocks.
        atomic_json(root / SNAPSHOT, current)
        temporary = path.with_suffix('.md.tmp')
        temporary.write_text(updated)
        temporary.replace(path)
    return current


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        result = update_report()
        print(f"Experiment report updated: {result['captured_at']}")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, StopIteration):
        print('Experiment report update failed; check sources and automatic update markers.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
