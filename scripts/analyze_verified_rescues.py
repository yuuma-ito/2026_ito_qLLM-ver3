"""Analyze intervention rescues from verified saved-prefix/new-suffix paths.

Reads public evaluation tables only; does not generate or execute model code.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
from itertools import product
import json
from pathlib import Path

from tasks import all_tasks

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUP = Path('docs/analysis/reevaluation_followup_20261015')
FULL = Path('docs/analysis/reevaluation_full_20261014T141718Z/final')
OUTPUT = Path('docs/analysis/intervention_rescues_20261015')
REPAIRS = ('self_refine', 'execution_feedback', 'self_debugging')
P = 'preventive_spec'
LABELS = dict(zip(REPAIRS, ('R', 'F', 'D'))) | {P: 'P'}
GROUPINGS = {
    'overall': (), 'model': ('model_spec',), 'task': ('task_id',),
    'difficulty': ('task_difficulty',), 'baseline_error': ('baseline_error_category',),
    'model_task': ('model_spec', 'task_id'),
    'model_error': ('model_spec', 'baseline_error_category'),
    'model_difficulty': ('model_spec', 'task_difficulty'),
    'seed_block': ('seed_block',), 'model_seed_block': ('model_spec', 'seed_block'),
    'seed': ('base_seed',),
}
COUNTS = ('pairs', 'initial_successes', 'initial_failures', 'rescued', 'unrescued',
          'preserved', 'regressed', 'final_successes', 'round_1_rescues',
          'round_2_rescues', 'round_3_rescues', 'repair_rounds')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def truth(value):
    if value not in ('True', 'False'):
        raise ValueError(f'Invalid boolean: {value!r}')
    return value == 'True'


def unique(rows, key):
    result = {}
    for row in rows:
        identity = key(row)
        if identity in result:
            raise ValueError('Duplicate identity')
        result[identity] = row
    return result


def identity(row):
    return tuple(row[k] for k in ('source_dir', 'model_spec', 'task_id', 'base_seed', 'condition_id'))


def build_paths(mixed, saved, partial, new_rounds):
    """Discard unreachable saved suffixes and enforce success/limit stopping."""
    records = unique(mixed, lambda r: r['record_key'])
    unique(mixed, identity)
    saved_map = unique(saved, lambda r: (r['record_key'], int(r['round'])))
    suffix_map = unique(new_rounds, lambda r: (r['record_key'], int(r['round'])))
    branches = unique(partial, lambda r: r['record_key'])
    if set(branches) - set(records):
        raise ValueError('Unexpected partial case')
    used_suffix, paths = set(), {}
    for key, row in records.items():
        stop = int(row['stop_round'])
        condition = row['condition_id']
        if condition not in ('baseline', *REPAIRS, P) or not 0 <= stop <= 3:
            raise ValueError('Invalid condition/stop round')
        if condition not in REPAIRS and stop != 0:
            raise ValueError('Independent generation has a repair round')
        branch = int(branches[key]['branch_input_round']) if key in branches else stop + 1
        if key in branches and not 1 <= branch <= stop:
            raise ValueError('Invalid branch position')
        expected_origin = 'saved_prefix_new_suffix' if key in branches else 'saved_path_reconstruction'
        if row['path_origin'] != expected_origin:
            raise ValueError('Path origin mismatch')
        history = []
        for index in range(stop + 1):
            source = saved_map if index < branch else suffix_map
            item = source[(key, index)]
            if identity(item) != identity(row):
                raise ValueError('Round identity mismatch')
            if index < branch and item['runtime_status'] != 'completed':
                raise ValueError('Incomplete saved evaluation')
            if index >= branch:
                used_suffix.add((key, index))
            success = truth(item['new_L3'])
            if success and index != stop:
                raise ValueError('Path continues after success')
            history.append(item)
        if truth(row['success']) != truth(history[-1]['new_L3']):
            raise ValueError('Final success mismatch')
        if condition in REPAIRS and not truth(row['success']) and stop != 3:
            raise ValueError('Unsuccessful repair path is incomplete')
        if key in branches and (int(branches[key]['new_generations']) != stop - branch + 1
                                or truth(branches[key]['success']) != truth(row['success'])):
            raise ValueError('Partial outcome mismatch')
        paths[key] = history
    if used_suffix != set(suffix_map):
        raise ValueError('Unconsumed new suffix rounds')
    if {key for key, _ in saved_map} != set(records):
        raise ValueError('Saved record coverage mismatch')
    return paths


def analyze(mixed, paths, difficulties):
    pairs = defaultdict(dict)
    global_ids = set()
    for row in mixed:
        ident = (row['model_spec'], row['task_id'], row['base_seed'], row['condition_id'])
        if ident in global_ids:
            raise ValueError('Overlapping source cohorts')
        global_ids.add(ident)
        pairs[identity(row)[:-1]][row['condition_id']] = row
    ledger, overlaps = [], []
    for (source, model, task, seed), conditions in sorted(pairs.items()):
        if set(conditions) != {'baseline', *REPAIRS, P}:
            raise ValueError('Missing paired condition')
        baseline = conditions['baseline']
        initial = paths[baseline['record_key']][0]
        passed = truth(initial['new_L3'])
        dims = dict(source_dir=source, model_spec=model, task_id=task,
                    task_difficulty=difficulties[task], base_seed=int(seed),
                    seed_block='0-9' if int(seed) < 10 else '10-19',
                    baseline_error_category=initial['new_error_category'])
        for condition in (*REPAIRS, P):
            row = conditions[condition]
            history = paths[row['record_key']]
            if condition in REPAIRS:
                first = history[0]
                if any(first[k] != initial[k] for k in
                       ('code_sha256', 'new_L0', 'new_L1', 'new_L2', 'new_L3', 'new_error_category')):
                    raise ValueError('Shared initial code/evaluation mismatch')
            success = truth(row['success'])
            rescued = not passed and success
            stop = int(row['stop_round'])
            ledger.append(dict(**dims, record_key=row['record_key'], condition_id=condition,
                comparison_kind='repair' if condition in REPAIRS else 'independent_generation',
                initial_success=passed, final_success=success, rescued=rescued,
                regressed=passed and not success, stop_round=stop, path_origin=row['path_origin'],
                final_error_category=history[-1]['new_error_category']))
        if not passed:
            f = truth(conditions['execution_feedback']['success'])
            d = truth(conditions['self_debugging']['success'])
            cohort = 'both' if f and d else 'F_only' if f else 'D_only' if d else 'neither'
            overlaps.append(dict(**dims, cohort=cohort))
    groups, fd = defaultdict(Counter), defaultdict(Counter)
    for row in ledger:
        passed, success = row['initial_success'], row['final_success']
        counts = dict(pairs=1, initial_successes=int(passed), initial_failures=int(not passed),
                      rescued=int(row['rescued']), unrescued=int(not passed and not success),
                      preserved=int(passed and success), regressed=int(row['regressed']),
                      final_successes=int(success), repair_rounds=row['stop_round'])
        counts.update({f'round_{i}_rescues': int(row['rescued'] and row['stop_round'] == i)
                       for i in (1, 2, 3)})
        for scope, source in (('pooled', ''), ('source', row['source_dir'])):
            for name, fields in GROUPINGS.items():
                groups[(scope, source, name, tuple(row[k] for k in fields), row['condition_id'])].update(counts)
    for row in overlaps:
        for scope, source in (('pooled', ''), ('source', row['source_dir'])):
            for name, fields in GROUPINGS.items():
                fd[(scope, source, name, tuple(row[k] for k in fields))].update({row['cohort']: 1, 'initial_failures': 1})
    summaries = []
    for (scope, source, name, values, condition), counts in sorted(groups.items()):
        summaries.append(dict(scope=scope, source_dir=source, grouping=name,
            **dict(zip(GROUPINGS[name], values)), condition_id=condition,
            comparison_kind='repair' if condition in REPAIRS else 'independent_generation',
            **{k: counts[k] for k in COUNTS},
            rescue_rate=counts['rescued'] / counts['initial_failures'] if counts['initial_failures'] else '',
            regression_rate=counts['regressed'] / counts['initial_successes'] if counts['initial_successes'] else '',
            small_denominator=0 < counts['initial_failures'] < 10))
    fd_rows = [dict(scope=scope, source_dir=source, grouping=name,
                   **dict(zip(GROUPINGS[name], values)),
                   **{k: counts[k] for k in ('initial_failures', 'both', 'F_only', 'D_only', 'neither')})
               for (scope, source, name, values), counts in sorted(fd.items())]
    for row in summaries:
        if (row['rescued'] + row['unrescued'] != row['initial_failures'] or
            row['preserved'] + row['regressed'] != row['initial_successes'] or
            row['rescued'] + row['preserved'] != row['final_successes']):
            raise ValueError('Outcome partition mismatch')
        if row['condition_id'] in REPAIRS and (row['regressed'] or
            sum(row[f'round_{i}_rescues'] for i in (1, 2, 3)) != row['rescued']):
            raise ValueError('Repair stopping/rescue round mismatch')
    # Each disjoint grouping and each source partition must reconcile to pooled totals.
    for condition in (*REPAIRS, P):
        total = next(r for r in summaries if r['scope'] == 'pooled' and r['grouping'] == 'overall'
                     and r['condition_id'] == condition)
        for scope in ('pooled', 'source'):
            for name in GROUPINGS:
                partition = [r for r in summaries if r['scope'] == scope and r['grouping'] == name
                             and r['condition_id'] == condition]
                if any(sum(r[k] for r in partition) != total[k] for k in COUNTS):
                    raise ValueError('Strata/source total mismatch')
    for row in fd_rows:
        if sum(row[k] for k in ('both', 'F_only', 'D_only', 'neither')) != row['initial_failures']:
            raise ValueError('F/D partition mismatch')
        for condition, extra in (('execution_feedback', 'F_only'), ('self_debugging', 'D_only')):
            match = next(s for s in summaries if s['scope'] == row['scope'] and s['source_dir'] == row['source_dir']
                         and s['grouping'] == row['grouping'] and s['condition_id'] == condition
                         and all(s[k] == row[k] for k in GROUPINGS[row['grouping']]))
            if match['rescued'] != row['both'] + row[extra]:
                raise ValueError('F/D rescue count mismatch')
    return ledger, summaries, overlaps, fd_rows


def render(summaries, fd_rows, captured):
    def table(grouping, field=None):
        rows = [r for r in summaries if r['scope'] == 'pooled' and r['grouping'] == grouping
                and r['condition_id'] in REPAIRS]
        labels = sorted({str(r[field]) for r in rows if grouping != 'baseline_error' or r['initial_failures']}) if field else ['全体']
        lines = ['| 区分 | 初期失敗 | R 救済数／率 | F 救済数／率 | D 救済数／率 |',
                 '| --- | ---: | ---: | ---: | ---: |']
        for label in labels:
            selected = {r['condition_id']: r for r in rows if not field or str(r[field]) == label}
            n = selected[REPAIRS[0]]['initial_failures']
            values = [f"{selected[c]['rescued']} / {100*selected[c]['rescue_rate']:.1f}%" if n else '—' for c in REPAIRS]
            lines.append('| ' + ' | '.join([label.removeprefix('ollama:'), str(n), *values]) + ' |')
        return '\n'.join(lines)
    total = [r for r in summaries if r['scope'] == 'pooled' and r['grouping'] == 'overall']
    repair = {r['condition_id']: r for r in total}
    n = repair[REPAIRS[0]]['initial_failures']
    initial_success = repair[REPAIRS[0]]['initial_successes']
    fd = next(r for r in fd_rows if r['scope'] == 'pooled' and r['grouping'] == 'overall')
    p = repair[P]
    text = ['# 介入による初期失敗コードの救済', '',
        f'集計UTC：{captured}。検証済み5,000条件記録を1,000初期組に対応づけた。初期成功{initial_success}組、初期失敗{n}組。', '',
        '研究の主題は、初期失敗に対する介入の救済率と救済対象の違いである。評価には課題仕様に沿って整備した主L3（evaluation_policy_v4）を採用する。救済率＝初期失敗から最終L3成功となった組数／初期失敗組数。R＝自己見直し、F＝実行結果提示、D＝自己デバッグ。3条件は同一の初期コード・初期評価を共有し、最大3回修正し、成功時に停止する。', '',
        '## 主要結果', '', table('overall'), '',
        f"F・Dの共通救済は{fd['both']}組、Fのみ{fd['F_only']}組、Dのみ{fd['D_only']}組、双方未救済{fd['neither']}組。同じ初期失敗{n}組を分母に比較する。", '',
        '## モデル別', '', table('model', 'model_spec'), '',
        '## タスク別', '', table('task', 'task_id'), '',
        '## 初期失敗類型別', '', table('baseline_error', 'baseline_error_category'), '',
        '分類は新評価でのbaseline初期失敗類型で固定する。修正後の失敗類型による事後選別は行わない。初期失敗10件未満の層は参考値とし、分母0の率はCSVで空欄とする。', '',
        '## 難度別', '', table('difficulty', 'task_difficulty'), '',
        '## 修正回数別の救済', '',
        '| 条件 | 1回目の救済 | 2回目の追加救済 | 3回目の追加救済 | 累積救済率（1→2→3回） |',
        '| --- | ---: | ---: | ---: | --- |']
    for c in REPAIRS:
        row = repair[c]
        counts = [row[f'round_{i}_rescues'] for i in (1, 2, 3)]
        cumulative = [sum(counts[:i]) / n * 100 for i in (1, 2, 3)]
        text.append('| ' + ' | '.join([LABELS[c], *map(str, counts), ' → '.join(f'{v:.1f}%' for v in cumulative)]) + ' |')
    text += ['', '同じ経路を各修正回数で区切った観測済み履歴の集計であり、上限を変えた独立実験ではない。', '',
        '## P：生成前注意事項の独立生成比較', '',
        f"Pはbaselineと同じ初期コードを修正する条件ではない。baseline初期失敗{n}組に対応する独立生成での成功は{p['rescued']}組（{p['rescue_rate']*100:.1f}%）、baseline初期成功{initial_success}組に対応する失敗は{p['regressed']}組（{p['regression_rate']*100:.1f}%）。Pの最終成功は{p['final_successes']}/1,000組。改善と悪化を併記し、R/F/Dの修正成功と分けて解釈する。", '',
        '## 方法・出典・限界', '',
        '元の3実験の保存設定・seed範囲・schema差を保持する。合理化した評価方法で保存コードを判定し、停止判断またはフィードバックが変わる経路の部分追試293ケースを反映した。経路は保存prefixと新規suffixの組合せであり、全件を新評価器で初回生成から実施し直したものではない。元結果との比較と評価器監査の詳細は[追試記録](../reevaluation_followup_20261015/README.md)に置く。', '',
        '共有初期・同一タスク・seedおよび出典間の依存と処理差がある。示すのは対象モデル・10タスク・seed 0〜19・最大3修正・生成長1,024 tokensでの観測値であり、モデルや介入の一般的優劣、因果効果、統計的有意差を断定しない。主L3は指定入力の出力一致と所定の構造条件であり、全入力に対するアルゴリズム同値性を保証しない。', '',
        'repair_summary.csvにモデル×タスク、モデル×失敗類型、seedブロック、元実験別の全表を保存する。Pはpreventive_summary.csv、F/D対応比較はfd_overlap_summary.csv、全対応記録はpaired_records.csvとfd_overlap_records.csvを参照。manifest.jsonとsanity_report.jsonに出典hash・整合性確認を保存した。生成コード・prompt本文・API応答は含まない。新規LLM生成や生成コードの再実行は行っていない。', '',
        '再集計はリポジトリ直下で `python -m scripts.analyze_verified_rescues --update-report`。継続レポートとスナップショットの主要結果も更新し、既存の元実験表・出典を保持する。', '']
    return '\n'.join(text)


def run(root=ROOT, output=OUTPUT):
    captured = datetime.now(timezone.utc).isoformat()
    used = {}
    def load(path):
        used[str(path)] = sha(root / path)
        return json.loads((root / path).read_text())
    def verified_csv(directory, name, manifest):
        path = directory / name
        if sha(root / path) != manifest['files'][name]['sha256']:
            raise ValueError(f'Artifact hash mismatch: {path}')
        used[str(path)] = sha(root / path)
        return read_csv(root / path)
    artifacts = load(FOLLOWUP / 'artifact_manifest.json')
    full_artifacts = load(FULL / 'artifact_manifest.json')
    for name in ('completion_checks.json', 'comparison_snapshot.json', 'settings_manifest.json'):
        if sha(root / FOLLOWUP / name) != artifacts['files'][name]['sha256']:
            raise ValueError(f'Followup metadata hash mismatch: {name}')
    checks = load(FOLLOWUP / 'completion_checks.json')
    if not checks or not all(v is True for v in checks.values()):
        raise ValueError('Followup completion checks did not pass')
    snapshot = load(FOLLOWUP / 'comparison_snapshot.json')
    if snapshot['status'] != 'completed':
        raise ValueError('Incomplete followup')
    settings = load(FOLLOWUP / 'settings_manifest.json')
    mixed = verified_csv(FOLLOWUP, 'mixed_path_records.csv', artifacts)
    partial = verified_csv(FOLLOWUP, 'partial_rerun_records.csv', artifacts)
    new_rounds = verified_csv(FOLLOWUP, 'partial_new_rounds.csv', artifacts)
    saved = verified_csv(FULL, 'round_comparison.csv', full_artifacts)
    expected = set()
    for source in settings['sources']:
        path = Path(source['source_dir']) / 'experiment_config.json'
        config = load(path)
        if used[str(path)] != source['config_sha256']:
            raise ValueError('Saved config hash mismatch')
        for model, task, seed, condition in product(config['models'], config['tasks'],
                range(config['seeds']['start'], config['seeds']['stop']), config['conditions']):
            expected.add((source['source_dir'], model, task, str(seed), condition))
    if set(map(identity, mixed)) != expected or len(mixed) != 5000:
        raise ValueError('Missing/unexpected source records')
    if (len(saved), len(partial), len(new_rounds)) != (9517, snapshot['partial_completed'], snapshot['new_generations']):
        raise ValueError('Round/partial coverage mismatch')
    paths = build_paths(mixed, saved, partial, new_rounds)
    difficulties = {t.id: t.task_difficulty for t in all_tasks()}
    used['tasks/__init__.py'] = sha(root / 'tasks/__init__.py')
    ledger, summaries, overlap_records, overlaps = analyze(mixed, paths, difficulties)
    if sum(truth(r['success']) for r in mixed) != snapshot['mixed_path_successes']:
        raise ValueError('Published final total mismatch')
    overall = [r for r in summaries if r['scope'] == 'pooled' and r['grouping'] == 'overall']
    summary = dict(captured_at_utc=captured, status='verified', primary_metric='rescued / baseline_initial_failures',
                   condition_records=len(mixed), initial_groups=len(ledger)//4,
                   evaluator='evaluation_policy_v4', source_plan_sha256=settings['source_plan_sha256'],
                   path_scope='verified saved prefix + partial rerun suffix', overall=overall,
                   fd_overlap=next(r for r in overlaps if r['scope'] == 'pooled' and r['grouping'] == 'overall'))
    out = root / output
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in [('paired_records.csv', ledger), ('repair_summary.csv', [r for r in summaries if r['condition_id'] in REPAIRS]),
                       ('preventive_summary.csv', [r for r in summaries if r['condition_id'] == P]),
                       ('fd_overlap_records.csv', overlap_records), ('fd_overlap_summary.csv', overlaps)]:
        write_csv(out / name, rows)
    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    save('results_snapshot.json', summary)
    save('sanity_report.json', dict(passed=True, missing=0, duplicates=0, unexpected=0,
        shared_initial_mismatches=0, strata_and_source_totals_verified=True,
        fd_partitions_verified=True, reachable_paths_and_stopping_verified=True,
        input_artifact_hashes_verified=True, condition_records=len(mixed), initial_groups=len(ledger)//4,
        partial_cases=len(partial), new_suffix_rounds=len(new_rounds),
        llm_requests=0, generated_code_executions=0))
    (out / 'README.md').write_text(render(summaries, overlaps, captured))
    save('manifest.json', dict(captured_at_utc=captured, inputs=used,
        script_sha256=sha(Path(__file__)), source_settings=settings['sources'],
        outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name != 'manifest.json'}))
    return summary


def refresh_report(summary, output=OUTPUT, root=ROOT):
    """Keep the current rescue result outside historical auto-update blocks."""
    from harness.run_state import atomic_json, file_lock

    repair = {r['condition_id']: r for r in summary['overall']}
    n = repair[REPAIRS[0]]['initial_failures']
    passed = repair[REPAIRS[0]]['initial_successes']
    overlap = summary['fd_overlap']
    link = str(Path(output).relative_to('docs'))
    lines = ['## 現行の主要結果：介入による初期失敗の救済', '',
        '本研究の主要評価指標は、初期生成で失敗したコードに対する介入の救済率である。評価方法の整備は妥当な判定のための手続きとして扱い、評価器間の比較を研究の主題には置かない。', '',
        f"集計UTC：{summary['captured_at_utc']}。5モデル・10タスク・seed 0〜19の1,000初期組（5,000条件記録）で、初期成功{passed}組、初期失敗{n}組。R・F・Dは同じ初期コードと判定を共有する。救済率の分母は新評価での初期失敗{n}組とし、最大3修正後の成功を数える。", '',
        '| 介入 | 救済数／初期失敗 | 救済率 |', '| --- | ---: | ---: |']
    for condition in REPAIRS:
        row = repair[condition]
        lines.append(f"| {LABELS[condition]} | {row['rescued']}/{n} | {row['rescue_rate']*100:.1f}% |")
    p = repair[P]
    lines += ['', 'R＝自己見直し、F＝実行結果提示、D＝自己デバッグ。', '',
        f"FとDの共通救済{overlap['both']}組、Fのみ{overlap['F_only']}組、Dのみ{overlap['D_only']}組、双方未救済{overlap['neither']}組。全体の救済率は近いが、救済対象とモデル別の大小は異なる。観測値の差を一般的な優劣や統計的有意差として扱わない。", '',
        f"P（生成前注意事項）は独立生成であり、修正型と分ける。baseline初期失敗に対応する成功{p['rescued']}/{n}組、baseline初期成功に対応する失敗{p['regressed']}/{passed}組を併記する。", '',
        f'[モデル・タスク・初期失敗類型・修正回数別の結果]({link}/README.md)、[解釈と次の分析]({link}/findings.md)、[固定スナップショット]({link}/results_snapshot.json)を参照。', '',
        '主L3はevaluation_policy_v4を採用し、保存経路と必要な部分追試の結果を反映した。全件を新評価器で初回生成からやり直した実験ではない。出典・設定差と経路の由来は詳細資料へ保存する。', '',
        '以下の旧実験表・過去の分析節は当時の評価での記録として保持する。現在の救済率の引用には上記の固定集計を用い、旧分母・旧救済数・旧コスト分析を現行値と組み合わせない。']
    start, end = '<!-- intervention-rescues:20261015:start -->', '<!-- intervention-rescues:20261015:end -->'
    block = start + '\n' + '\n'.join(lines) + '\n' + end
    with file_lock(root / '.cache/experiment_report.lock'):
        report = root / 'docs/experiment_report_draft.md'
        text = report.read_text()
        if start in text:
            if text.count(start) != 1 or text.count(end) != 1:
                raise ValueError('Rescue report markers mismatch')
            text = text[:text.index(start)] + block + text[text.index(end) + len(end):]
        else:
            marker = '<!-- auto:status:start -->'
            text = text.replace(marker, block + '\n\n' + marker, 1)
        snapshot_path = root / 'docs/experiment_report_snapshot.json'
        snapshot = json.loads(snapshot_path.read_text())
        snapshot['primary_intervention_rescues'] = dict(summary, analysis_dir=str(output))
        atomic_json(snapshot_path, snapshot)
        temporary = report.with_suffix('.md.rescues.tmp')
        temporary.write_text(text)
        temporary.replace(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--update-report', action='store_true')
    args = parser.parse_args()
    summary = run(output=args.output)
    if args.update_report:
        refresh_report(summary, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
