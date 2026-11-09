"""Describe current saved R failure paths without generation, execution or scoring."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json

from scripts.analyze_b4_observed_gap import ast_hash
from scripts.factorial_pilot_sources import CURRENT, ROOT, load_current
from scripts.measurement_ban_report import write_csv
from scripts.measurement_ban_sources import sha

CONDITIONS = ('R', 'F', 'D', 'B4')


def failure_pattern(rounds):
    """Mutually exclusive path classes; parse failures never imply AST equality."""
    if rounds[-1]['success']:
        return 'rescued'
    if len({r['hash'] for r in rounds}) == 1:
        return 'unchanged_text'
    hashes = [ast_hash(r['code']) for r in rounds]
    if any(h is None for h in hashes):
        return 'ast_incomplete'
    return 'unchanged_ast_only' if len(set(hashes)) == 1 else 'changed_ast_still_failed'


def request_diagnostic(row, inputs):
    """Read actual saved request only; never reconstruct an absent historical prompt."""
    if row['origin'] == 'saved_prefix':
        return None
    if row['origin'] == 'new_suffix':
        base = ROOT / '.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'
    elif row['origin'] == 'diagnostic_v2_suffix':
        source = CURRENT / 'followup_public_result.json'
        base = ROOT / json.loads(source.read_text())['output_dir'] / 'private'
    else:
        raise ValueError('Unknown request origin')
    path = base / row['record_key'] / f"round_{row['round']}_request.json"
    obj = json.loads(path.read_text())
    inputs[str(path.relative_to(ROOT))] = sha(path)
    request = obj.get('request', obj)
    text = request['user']
    marker = '検証器から得られた情報:\n'
    if marker not in text:
        raise ValueError('Actual F request has no diagnostic marker')
    diagnostic = text.split(marker, 1)[1].split('\n\n', 1)[0]
    if not diagnostic:
        raise ValueError('Empty actual diagnostic')
    return {
        'request_sha256': inputs[str(path.relative_to(ROOT))],
        'diagnostic_sha256': hashlib.sha256(diagnostic.encode()).hexdigest(),
        'mentions_exception': '例外' in diagnostic or '種別:' in diagnostic,
        'mentions_expected_distribution': '期待される測定分布' in diagnostic,
        'mentions_actual_distribution': '実測分布' in diagnostic,
        'mentions_structure': '構造要件' in diagnostic,
        'mentions_qubit_count': 'qubit 数' in diagnostic,
        'mentions_measurement_ban': '禁止' in diagnostic and '測定' in diagnostic,
    }


def summarize(rows, fields):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in fields)].append(row)
    out = []
    for key, group in sorted(groups.items()):
        patterns = Counter(r['r_pattern'] for r in group)
        out.append(dict(zip(fields, key)) | {
            'initial_failures': len(group),
            **{c + '_successes': sum(r[c + '_success'] for r in group) for c in CONDITIONS},
            **{p: patterns[p] for p in ('rescued', 'unchanged_text', 'unchanged_ast_only',
                                       'changed_ast_still_failed', 'ast_incomplete')},
            'small_stratum': len(group) < 10,
        })
    return out


def run(output):
    if output.exists():
        raise ValueError('Use a new output directory; existing evidence is preserved')
    cases, histories, evidence = load_current()
    inputs = dict(evidence['inputs'])
    source = CURRENT / 'reachable_rounds.csv'
    with source.open() as stream:
        reachable = list(csv.DictReader(stream))
    lookup = {(r['model_spec'], r['task_id'], int(r['base_seed']), r['condition_id'], int(r['round'])): r
              for r in reachable}
    assert len(lookup) == len(reachable)
    rows, rounds, diagnostics, examples = [], [], [], []
    example_classes = set()
    for case in cases:
        ident = (case['model_spec'], case['task_id'], case['base_seed'])
        paths = {c: histories[(*ident, c)] for c in CONDITIONS}
        rpath = paths['R']
        pattern = failure_pattern(rpath)
        row = {k: case[k] for k in ('case_id', 'model_spec', 'task_id', 'base_seed', 'initial_error')}
        row.update(r_pattern=pattern, r_final_error=rpath[-1]['error'],
                   r_any_prior_ast_repeat=False, r_all_errors_same=len({r['error'] for r in rpath}) == 1,
                   r_any_output_at_1024=any(r['tokens_out'] == 1024 for r in rpath[1:]))
        row.update({c + '_success': paths[c][-1]['success'] for c in CONDITIONS})
        asts = [ast_hash(r['code']) for r in rpath]
        for i, attempt in enumerate(rpath[1:], 1):
            repeat = asts[i] is not None and asts[i] in asts[:i]
            row['r_any_prior_ast_repeat'] |= repeat
            rounds.append({k: row[k] for k in ('case_id', 'model_spec', 'task_id', 'base_seed', 'initial_error')} | {
                'round': i, 'success': attempt['success'], 'error_before': rpath[i-1]['error'],
                'error_after': attempt['error'], 'exact_same_as_previous': attempt['hash'] == rpath[i-1]['hash'],
                'ast_comparable_to_previous': asts[i] is not None and asts[i-1] is not None,
                'same_ast_as_previous': asts[i] is not None and asts[i] == asts[i-1],
                'any_prior_ast_repeat': repeat, 'tokens_in': attempt['tokens_in'],
                'tokens_out': attempt['tokens_out'], 'finish_reason': attempt['finish'] or 'not_recorded',
                'code_sha256': attempt['hash'], 'previous_code_sha256': rpath[i-1]['hash'],
            })
        rows.append(row)
        if not row['R_success'] and row['F_success']:
            fpath = paths['F']
            for i, attempt in enumerate(fpath[1:], 1):
                provenance = lookup[(*ident, 'execution_feedback', i)]
                actual = request_diagnostic(provenance, inputs)
                diagnostics.append({k: row[k] for k in ('case_id', 'model_spec', 'task_id', 'base_seed', 'initial_error')} | {
                    'round': i, 'success_after': attempt['success'], 'error_before': fpath[i-1]['error'],
                    'error_after': attempt['error'], 'origin': provenance['origin'],
                    'actual_request_available': actual is not None, **(actual or {}),
                })
        # Purposeful deterministic examples, including a counterexample; no representativeness claim.
        label = pattern if not row['R_success'] and row['F_success'] else (
            'R_only_against_F' if row['R_success'] and not row['F_success'] else None)
        if label is not None and label not in example_classes:
            example_classes.add(label)
            examples.append({'selection_class': label, 'case': row, 'paths': {
                c: [{'round': a['round'], 'error': a['error'], 'success': a['success'],
                     'code_sha256': a['hash']} for a in path] for c, path in paths.items()}})

    assert len(rows) == len({r['case_id'] for r in rows}) == 545
    assert {c: sum(r[c + '_success'] for r in rows) for c in CONDITIONS} == {'R': 96, 'F': 186, 'D': 179, 'B4': 216}
    pairs = []
    pair_strata = []
    for c in ('B4', 'F', 'D'):
        groups = defaultdict(list)
        for row in rows:
            name = 'both' if row['R_success'] and row[c+'_success'] else (
                'R_only' if row['R_success'] else 'other_only' if row[c+'_success'] else 'neither')
            groups[name].append(row)
        for name in ('both', 'R_only', 'other_only', 'neither'):
            group = groups[name]
            counts = Counter(r['r_pattern'] for r in group)
            pairs.append({'comparator': c, 'outcome': name, 'cases': len(group),
                          'r_any_prior_ast_repeat': sum(r['r_any_prior_ast_repeat'] for r in group),
                          **{p: counts[p] for p in ('rescued', 'unchanged_text', 'unchanged_ast_only',
                                                   'changed_ast_still_failed', 'ast_incomplete')}})
        assert sum(r['cases'] for r in pairs if r['comparator'] == c) == 545
        for field in ('model_spec', 'task_id', 'initial_error'):
            for value in sorted({r[field] for r in rows}):
                group = [r for r in rows if r[field] == value]
                other_only = [r for r in group if not r['R_success'] and r[c+'_success']]
                pair_strata.append({'comparator': c, 'grouping': field, 'group': value,
                                    'initial_failures': len(group),
                                    'both': sum(r['R_success'] and r[c+'_success'] for r in group),
                                    'R_only': sum(r['R_success'] and not r[c+'_success'] for r in group),
                                    'other_only': len(other_only),
                                    'neither': sum(not r['R_success'] and not r[c+'_success'] for r in group),
                                    'r_unchanged_ast_in_other_only': sum(r['r_pattern'] in (
                                        'unchanged_text', 'unchanged_ast_only') for r in other_only),
                                    'r_changed_ast_in_other_only': sum(r['r_pattern'] == 'changed_ast_still_failed' for r in other_only),
                                    'small_stratum': len(group) < 10})
    totals = summarize(rows, [])
    assert sum(totals[0][p] for p in ('rescued', 'unchanged_text', 'unchanged_ast_only',
                                    'changed_ast_still_failed', 'ast_incomplete')) == 545
    out_tables = {'cases': rows, 'r_rounds': rounds, 'paired_outcomes': pairs,
                  'paired_by_stratum': pair_strata,
                  'overall': totals, 'by_model': summarize(rows, ['model_spec']),
                  'by_task': summarize(rows, ['task_id']), 'by_initial_error': summarize(rows, ['initial_error']),
                  'by_model_task': summarize(rows, ['model_spec', 'task_id']),
                  'f_diagnostics_when_r_failed': diagnostics}
    # Reconcile every model/task/error partition with the overall totals.
    for name in ('by_model', 'by_task', 'by_initial_error', 'by_model_task'):
        for col in ('initial_failures', 'R_successes', 'F_successes', 'D_successes', 'B4_successes'):
            assert sum(r[col] for r in out_tables[name]) == totals[0][col]
    known = sum(r['actual_request_available'] for r in diagnostics)
    final_diags = [r for r in diagnostics if r['success_after']]
    f_only = [r for r in rows if not r['R_success'] and r['F_success']]
    f_only_errors = Counter(r['initial_error'] for r in f_only)
    known_success_diags = [r for r in final_diags if r['actual_request_available']]
    diagnostic_summary = {key: sum(r.get(key, False) for r in known_success_diags)
                          for key in ('mentions_exception', 'mentions_expected_distribution',
                                      'mentions_actual_distribution', 'mentions_structure',
                                      'mentions_qubit_count', 'mentions_measurement_ban')}
    checks = {'passed': True, 'initial_failure_cases': 545, 'condition_paths': 2180,
              'missing': 0, 'duplicates': 0, 'unexpected': 0, 'partition_totals_reconciled': True,
              'R_additional_requests': len(rounds), 'F_success_R_failure_cases': len(final_diags),
              'F_requests_in_these_paths': len(diagnostics), 'actual_F_requests_available': known,
              'actual_F_requests_unavailable': len(diagnostics)-known,
              'actual_successful_F_requests_available': sum(r['actual_request_available'] for r in final_diags),
              'new_model_requests': 0, 'generated_code_executions': 0, 'rescoring': False,
              'scope': 'Saved-verdict descriptive analysis; not a new experiment or causal identification.'}
    output.mkdir(parents=True)
    for name, table in out_tables.items():
        write_csv(output / (name + '.csv'), table)
    (output/'examples.json').write_text(json.dumps(examples, ensure_ascii=False, indent=2)+'\n')
    (output/'validation_report.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2)+'\n')
    lines = ['Rの低成績を調べる既存545初期失敗組の記述分析', '',
             '診断v2修正後の到達可能履歴を保存記録から再構成。新規生成・生成コード実行・再採点なし。',
             '成功基準は保存された主L3。初期成功455組を除く545組が分母。4条件で初期コードを共有する。',
             'R/F/Dの旧prefixと追試suffix、別時期に生成されたB4を含み、同時期の無作為比較ではない。', '',
             '1. Rの経路分類（初期コードを含む。排他的）', str(totals[0]),
             'rescued=追加成功。unchanged_text=全roundで完全に同じコード。',
             'unchanged_ast_only=文字列は変わったが全roundでAST一致。',
             'changed_ast_still_failed=全roundを構文解析でき、構造が変化したが最終失敗。',
             'ast_incomplete=文字列の変化があり、少なくとも1roundを解析できず、全経路の構造比較は不完全。',
             'AST一致はコメント・書式・位置を除いた構造一致。意味的同値性や誤りの根本原因は認定しない。', '',
             '2. 同じ初期組でのRとの対応比較']
    lines.extend(str(r) for r in pairs)
    lines.extend(['', '3. 初期失敗類型別', *[str(r) for r in out_tables['by_initial_error']],
                  '', '4. モデル別', *[str(r) for r in out_tables['by_model']],
                  '', '5. R失敗・F成功経路に実際に提示された診断',
                  f"対象{len(final_diags)}組・Fの追加要求{len(diagnostics)}回。実際の保存要求文を確認できるのは{known}回。",
                  f"成功した最終要求の診断文を確認できるのは{checks['actual_successful_F_requests_available']}組。",
                  '旧prefixの入力文は未保存。再構成した診断を実際に提示した文と同一視せず、unknownとして扱う。',
                  '例外・分布・構造等の診断フラグは文面の記述特徴であり、診断が成功原因だったことは示さない。',
                  '確認できた成功要求における診断フラグ（重複あり）: '+str(diagnostic_summary),
                  '診断の詳細はf_diagnostics_when_r_failed.csv。生の要求・コード・例外メッセージは公開表に含めない。',
                  '', '6. 解釈と次の検証',
                  'R最終失敗449組のうち、全roundで同じASTは157組（完全同一コード137、コメント等のみ変化20）。',
                  '構造を変えても失敗した221組、構文解析が不完全な71組もあり、反復だけでは低成績を説明できない。',
                  'R失敗・F成功110組では90組に途中のAST反復があるが、最初から最後まで同じASTは34組。55組は構造を変えてもRが失敗、21組は解析不完全。',
                  '初期失敗類型別のR失敗・F成功組数: '+str(dict(f_only_errors)),
                  'このうちimport/構築失敗は88/110組。これは差が生じた層の特定であり、診断が効いた原因の寄与率ではない。',
                  'Gemma3ではR=5/190、F=4/190で、外部診断を加える方式が全モデルで一律に高いわけではない。',
                  'Rのコード反復と失敗の関連は観測できるが、失敗通知の欠如、前回コード提示、自己点検指示のどれが原因かは未特定。',
                  '構造を変更しても失敗した経路と、Rだけ成功した反例を併記し、反復だけで全体を説明しない。',
                  'Rは成功までの停止制御に外部評価を使うが、その診断をモデルへ提示しない条件。モデルの内的判断は観測できない。',
                  'Rの旧要求では終了理由が未保存。tokens_out=1024を終了理由lengthと同一視しない。',
                  '実例は各分類の先頭1組を目的選択した説明例。代表性・原因の確定は主張しない。',
                  '失敗を認識できなかったという仮説を確かめるなら、既存Rを保持して失敗通知だけを追加する条件との比較を事前設計する。',
                  '診断の効果を分離するなら、共通指示を固定し失敗通知のみ／詳細診断ありを比較する別設計が必要。',
                  'これらの追試は本分析では開始しない。既存545組と予備実験100組を独立な645組として合算しない。'])
    (output/'report.txt').write_text('\n'.join(lines)+'\n')
    inputs[str(source.relative_to(ROOT))] = sha(source)
    for name in ('scripts/analyze_r_failure_paths.py', 'scripts/factorial_pilot_sources.py',
                 'scripts/analyze_b4_observed_gap.py', 'harness/interventions/prompts.py',
                 'harness/diagnostic_prompts.py', 'harness/diagnostic_policy.py', 'prompts/system.txt'):
        inputs[name] = sha(ROOT/name)
    for name, expected in inputs.items():
        if sha(ROOT/name) != expected:
            raise ValueError('Input drift during analysis: ' + name)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'verified_descriptive_only', 'new_model_requests': 0,
                'generated_code_executions': 0, 'rescoring': False, 'causal_effect_identified': False,
                'source': str(CURRENT.relative_to(ROOT)), 'inputs': inputs,
                'outputs': {p.name: sha(p) for p in output.iterdir() if p.is_file()}}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'output': str(output), 'overall': totals, 'pairs': pairs, 'validation': checks},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/analysis/r_failure_paths_20261106')
    run(parser.parse_args().output.resolve())
