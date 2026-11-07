"""Unify saved experiments and explicitly registered frozen analyses in a ledger."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from harness.research_registry import evaluation_metadata, local_path, read_json, sha256
from harness.run_state import ROOT, atomic_json


def build(root=ROOT, registry='configs/research_registry.json'):
    metadata = read_json(root, registry)
    annotations = metadata.get('entries', [])
    ids = [item['id'] for item in annotations]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate registry identifiers')
    by_config = {item['config']: item for item in annotations if item.get('config')}
    if len(by_config) != sum(bool(item.get('config')) for item in annotations):
        raise ValueError('Duplicate registered configuration')
    sources = {str(p.relative_to(root)): {} for p in sorted((root / 'results').glob('*/experiment_config.json'))}
    sources.update({path: item for path, item in by_config.items()})
    entries = []
    for config_path in sources:
        entry = dict(by_config.get(config_path, {}))
        entry.setdefault('id', Path(config_path).parent.name)
        entry['config'] = config_path
        entries.append(entry)
    entries.extend(dict(item) for item in annotations if not item.get('config'))
    result = []
    for item in entries:
        row = {key: item.get(key) for key in ('id', 'kind', 'purpose', 'hypothesis', 'config', 'manifest', 'generation_manifest')}
        row.update(parents=item.get('parents', []), materials=item.get('materials', []),
                   notes=item.get('notes', []), issues=[], hashes={})
        config, manifest = {}, {}
        try:
            if row['config']:
                config = read_json(root, row['config'])
                row['hashes'][row['config']] = sha256(local_path(root, row['config']))
                row['manifest'] = row['manifest'] or str(Path(row['config']).with_name('manifest.json'))
                row['schema'] = config.get('schema', 'standard')
            if row['manifest']:
                manifest = read_json(root, row['manifest'])
                row['hashes'][row['manifest']] = sha256(local_path(root, row['manifest']))
            if row['config']:
                saved_id = config.get('experiment_id', config.get('run_id', Path(row['config']).parent.name))
                if saved_id != row['id']:
                    row['issues'].append('登録IDと保存設定のIDが不一致')
            row['evaluation'] = evaluation_metadata(manifest)
            row['generation_evaluation'] = evaluation_metadata(read_json(root, item['generation_manifest'])) if item.get('generation_manifest') else None
            if row['generation_manifest']:
                row['hashes'][row['generation_manifest']] = sha256(local_path(root, row['generation_manifest']))
            row['models'] = config.get('models', [config['model_spec']] if config.get('model_spec') else [])
            row['tasks'] = config.get('tasks', [config['task_id']] if config.get('task_id') else [])
            row['seeds'] = config.get('seeds', [config['base_seed']] if 'base_seed' in config else None)
            row['conditions'] = config.get('conditions')
            row['retry_of'] = config.get('retry_of')
            row['primary_level'] = item.get('primary_level')
            for key in ('purpose', 'hypothesis', 'kind'):
                if row[key] is None:
                    row['issues'].append(key + ': 未登録')
            if not row['evaluation']['evaluator_version']:
                row['issues'].append('評価器の版: 保存記録では未確認')
            if row['config'] and row['kind'] != 'pooled':
                try:
                    from harness.experiment import validate_config
                    row['planned_records'] = validate_config(config)['planned_records']
                except (ValueError, KeyError, TypeError):
                    row['planned_records'] = None
        except (OSError, ValueError, KeyError, TypeError):
            row['issues'].append('設定またはmanifestを読み取れません')
        result.append(row)
    known = {p['id'] for p in result}
    for row in result:
        for parent in row['parents']:
            if parent not in known:
                row['issues'].append('未登録の親実験: ' + parent)
        for material in row['materials']:
            if not local_path(root, material).is_file():
                row['issues'].append('採用資料がありません: ' + material)
    if len(known) != len(result):
        raise ValueError('Conflicting discovered and registered IDs')
    # Reject cycles, including registered analyses referring back to descendants.
    parents = {p['id']: p['parents'] for p in result}
    def visit(key, stack):
        if key in stack:
            raise ValueError('Cyclic provenance')
        for parent in parents.get(key, []):
            visit(parent, stack | {key})
    for key in parents:
        visit(key, set())
    return dict(schema_version=1, updated_at_utc=datetime.now(timezone.utc).isoformat(),
                registry=registry, registry_sha256=sha256(local_path(root, registry)), entries=result, new_model_requests=0,
                limits=['未登録の目的・仮説・版を推測で補わない。',
                        '保存設定と固定manifestの台帳であり、再検証・再採点・公開確認ではない。'])


def markdown(report):
    def esc(value):
        return str(value if value is not None else '未登録').replace('|', '\\|').replace('\n', ' ')
    lines = ['# 実験・固定分析台帳', '', '更新: ' + report['updated_at_utc'], '',
             '生成実験・追試・再採点・統合を別項目で保持します。未登録は未確認であり、失敗の判定ではありません。', '']
    for row in report['entries']:
        lines += ['## ' + row['id'], '', '| 項目 | 記録 |', '|---|---|']
        values = {'種別': row['kind'], '目的': row['purpose'], '事前仮説': row['hypothesis'],
                  '親実験・元分析': ', '.join(row['parents']) or '未登録',
                  '保存設定': row['config'], '固定manifest': row['manifest'], '生成時manifest': row['generation_manifest'],
                  '評価器': row.get('evaluation', {}).get('evaluator_version'),
                  '生成時評価器（別manifest指定時）': (row.get('generation_evaluation') or {}).get('evaluator_version'),
                  '診断文の版': row.get('evaluation', {}).get('diagnostic_policy_version'),
                  '成功基準': row.get('primary_level'), '予定条件記録数': row.get('planned_records'),
                  '採用資料': ', '.join(row['materials']) or '未登録',
                  '要確認': '・'.join(row['issues']) or 'なし', '注記': '・'.join(row['notes'])}
        lines.extend(f'| {key} | {esc(value)} |' for key, value in values.items())
        lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', default='configs/research_registry.json')
    parser.add_argument('--out-dir', type=Path, default=ROOT / '.cache/research_ledger')
    args = parser.parse_args(argv)
    try:
        report = build(ROOT, args.registry)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(args.out_dir / 'ledger.json', report)
        (args.out_dir / 'ledger.md').write_text(markdown(report), encoding='utf-8')
        print(f"Ledger: {len(report['entries'])} entries; {args.out_dir / 'ledger.md'}")
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('Ledger update failed; check registered paths, identifiers and lineage.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
