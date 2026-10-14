"""検証済みの分割実験を統合し、元記録を保持した公開用集計を作る。"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from harness.experiment import build_manifest, expected_keys, load_config, load_existing, validate_config
from harness.run_state import ROOT
from scripts.analyze_interventions import _summary, _write, write_analysis_outputs
from scripts.analyze_intervention_catalog import write_catalog, verify_catalog
from scripts.sanity_check import check_results

CATALOG_NAMES = ('intervention_catalog_by_error', 'intervention_catalog_by_error_model',
                 'intervention_catalog_by_error_difficulty')
ANALYSIS_NAMES = ('summary_by_condition', 'summary_by_model', 'summary_by_task',
                  'summary_by_difficulty', 'rescue_rates_by_error', 'degradation_cases',
                  'baseline_regressions', 'timeout_summary', 'cost_runtime_summary',
                  'failure_stage_summary')
PUBLIC_FILES = tuple(n + '.csv' for n in (*ANALYSIS_NAMES, *CATALOG_NAMES)) + (
    'summary_by_source.csv', 'manifest.json', 'experiment_config.json', 'sanity_report.json',
    'automation_report.json', 'pool_report.md')


def pool_output(plan, root=ROOT):
    output = (root / plan['output_dir']).resolve()
    if not output.is_relative_to((root / 'results').resolve()) or output == (root / 'results').resolve():
        raise ValueError('統合先はresults/内の専用フォルダにしてください')
    return output


def signature(config, manifest):
    parsed = validate_config(config)
    return dict(tasks=config['tasks'], temperature=parsed['temperature'],
                conditions=[(c.id, c.intervention, c.max_rounds) for c in parsed['conditions']],
                generation_settings=config.get('generation_settings'),
                prompt_fingerprints=manifest['prompt_fingerprints'],
                environment=manifest['environment'],
                evaluator_version=manifest.get('evaluator_version', 'legacy_unspecified'),
                evaluation_sampling=manifest.get('evaluation_sampling'),
                statevector_policy=manifest.get('statevector_policy'),
                transport_recovery=manifest.get('transport_recovery'))


def check_preflight(plan, config, server, root=ROOT):
    """モデル呼び出し前に、予定グリッドと保存条件・digestの一致を確認する。"""
    current = build_manifest(config, root)
    target = signature(config, current)
    versions = {current['schema_version']}
    keys = set()
    tags = {m['name']: m['digest'] for m in server.get('models', [])}
    for source_dir in plan['source_dirs']:
        source = (root / source_dir).resolve()
        if not source.is_relative_to((root / 'results').resolve()):
            raise ValueError('出典はresults/内に限定します')
        saved = load_config(source / 'experiment_config.json')
        manifest = load_config(source / 'manifest.json')
        report = load_config(source / 'automation_report.json')
        if signature(saved, manifest) != target or not report.get('passed'):
            raise ValueError('追試と既存実験の条件または検証状態が不一致')
        versions.add(manifest['schema_version'])
        previous_tags = {m['name']: m['digest'] for m in report.get('shared_server', {}).get('models', [])}
        for model in config['models']:
            if not model.startswith('ollama:'):
                continue
            name = model.removeprefix('ollama:')
            if model in saved['models'] and (not tags.get(name) or tags[name] != previous_tags.get(name)):
                raise ValueError('追試対象モデルのdigestが既存実験と不一致')
        for key in expected_keys(validate_config(saved)):
            identity = key[1:]
            if identity in keys:
                raise ValueError('既存実験の予定グリッドが重複')
            keys.add(identity)
    if len(versions) > 1 and not plan.get('allow_mixed_failure_feedback'):
        raise ValueError('エラー分類・フィードバックの版が異なります')
    for key in expected_keys(validate_config(config)):
        if key[1:] in keys:
            raise ValueError('追試の予定グリッドが既存実験と重複')
        keys.add(key[1:])
    pooled = dict(config, models=plan['models'], seeds=plan['seeds'])
    if keys != {k[1:] for k in expected_keys(validate_config(pooled))}:
        raise ValueError('追試完了後の予定グリッドに欠落・予定外記録があります')
    return True


def write_pool(plan, *, current_output=None, root=ROOT):
    from scripts.automate_experiment import verify
    output = pool_output(plan, root)
    sources = [(root / p).resolve() for p in plan['source_dirs']]
    if current_output is not None:
        sources.append(Path(current_output).resolve())
    if len(sources) != len(set(sources)) or output in sources:
        raise ValueError('出典の重複または統合先との衝突')
    combined, provenance, signatures, versions, digests = [], [], [], set(), {}
    for source in sources:
        if not source.is_relative_to((root / 'results').resolve()):
            raise ValueError('出典はresults/内に限定します')
        config = load_config(source / 'experiment_config.json')
        manifest = load_config(source / 'manifest.json')
        automation = load_config(source / 'automation_report.json')
        if manifest['experiment_id'] != config['experiment_id'] or manifest['config'] != config:
            raise ValueError('出典の保存設定とmanifestが不一致')
        if not automation.get('passed') or not verify(config, source)['passed']:
            raise ValueError('未検証または不整合のある出典: ' + source.name)
        signatures.append(signature(config, manifest))
        versions.add(manifest['schema_version'])
        model_tags = {m['name']: m['digest'] for m in automation.get('shared_server', {}).get('models', [])}
        for model in config['models']:
            if model.startswith('ollama:'):
                digest = model_tags.get(model.removeprefix('ollama:'))
                if not digest or (model in digests and digests[model] != digest):
                    raise ValueError('モデルdigestが欠落または不一致: ' + model)
                digests[model] = digest
        rows, _ = load_existing(source / 'raw.jsonl')
        provenance.append(dict(experiment_id=config['experiment_id'], source_dir=str(source.relative_to(root)),
                               config=config, records=len(rows), schema_version=manifest['schema_version'],
                               git_commit=manifest['git_commit'],
                               raw_sha256=hashlib.sha256((source / 'raw.jsonl').read_bytes()).hexdigest(),
                               baseline_L2_failures=sum(r['intervention'] == 'baseline' and not r['L2'] for r in rows)))
        combined.extend(dict(r, source_experiment_id=config['experiment_id'], experiment_id=plan['experiment_id'])
                        for r in rows)
    if not signatures or any(s != signatures[0] for s in signatures):
        raise ValueError('タスク・生成条件・プロンプト・環境が一致しません')
    if len(versions) > 1 and not plan.get('allow_mixed_failure_feedback', False):
        raise ValueError('エラー分類・フィードバックの版が異なります')
    first = provenance[0]['config']
    config = dict(first, experiment_id=plan['experiment_id'], output_dir=plan['output_dir'],
                  models=plan['models'], seeds=plan['seeds'])
    config.pop('pairs', None)
    actual = [(r['experiment_id'], r['condition_id'], r['model_spec'], r['task_id'], r['base_seed'])
              for r in combined]
    expected = expected_keys(validate_config(config))
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError('統合後の記録に重複・欠落・予定外記録があります')
    if output.exists() and any((output / name).exists() for name in PUBLIC_FILES):
        previous = load_config(output / 'manifest.json')
        if previous.get('sources') != provenance:
            raise ValueError('既存統合集計の出典が異なります。新しい統合先を指定してください')
    # Private temporary JSONL is never copied into the publication directory.
    cache = root / '.cache'
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pool-', dir=cache) as temporary:
        private = Path(temporary)
        raw = private / 'raw.jsonl'
        raw.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in combined))
        sanity = check_results(config, raw)
        if not sanity['passed'] or sanity['warnings']:
            raise ValueError('統合後のsanity checkが失敗しました')
        write_analysis_outputs(raw, private)
        write_catalog(raw, private)
        verify_catalog(combined, private)
        output.mkdir(parents=True, exist_ok=True)
        for name in (*ANALYSIS_NAMES, *CATALOG_NAMES):
            with (private / (name + '.csv')).open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                fields = [k for k in reader.fieldnames if k != 'code_diff_round0_final']
                _write(output / (name + '.csv'), list(reader), fields)
    by_source = _summary(combined, ('source_experiment_id', 'model_spec', 'condition_id', 'intervention'))
    _write(output / 'summary_by_source.csv', by_source, list(by_source[0]))
    captured = datetime.now(timezone.utc).isoformat()
    limitations = [
        '各条件は共有round 0を含むため、5,000件は独立した5,000回の初期生成ではありません。',
        'seedブロック・実施時期の差を保持し、モデルの一般的優劣や統計的有意差は断定しません。',
    ]
    if len(versions) > 1:
        limitations.append('schema 2.0と2.1を含みます。エラー分類変更はexecution_feedbackとself_debuggingの診断文にも影響します。統合値は混合手順の記述的結果であり、単一手順の介入効果とは解釈しません。')
    manifest = dict(experiment_id=config['experiment_id'], captured_at=captured, config=config,
                    sources=provenance, model_digests=digests, compatibility_signature=signatures[0],
                    schema_versions=sorted(versions), limitations=limitations, records=len(combined),
                    sanity_passed=True, generated_new_code=False)
    report = dict(passed=True, problems=[], sanity=sanity, catalog_verified=True,
                  source_automation_verified=True, limitations=limitations)
    for filename, data in (('experiment_config.json', config), ('manifest.json', manifest),
                           ('sanity_report.json', sanity), ('automation_report.json', report)):
        (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    lines = ['# seed 0〜19の統合集計', '', f'集計時点: {captured}', '',
             f'記録件数: {len(combined)}件。元の保存設定と記録は保持し、新規生成は行っていません。', '',
             '| 出典実験 | seed | 件数 | baseline L2失敗 |', '| --- | --- | ---: | ---: |']
    for item in provenance:
        lines.append(f"| {item['experiment_id']} | {item['config']['seeds']} | {item['records']} | {item['baseline_L2_failures']} |")
    lines += ['', 'モデル・条件別の成功率はsummary_by_model.csv、出典別の内訳はsummary_by_source.csv、失敗原因別の救済率はintervention_catalog_by_error.csvを参照してください。', '', *['- ' + note for note in limitations]]
    (output / 'pool_report.md').write_text('\n'.join(lines) + '\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    print(write_pool(load_config(args.config)))


if __name__ == '__main__':
    main()
