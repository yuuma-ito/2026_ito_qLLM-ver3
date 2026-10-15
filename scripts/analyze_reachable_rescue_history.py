"""Read saved code as text only; audit reachable repairs, costs and truncations.

No generated code is imported or executed. Public outputs use allowlisted fields.
"""
from __future__ import annotations
import ast
from collections import Counter, defaultdict
import difflib
import json
import math
from pathlib import Path
import re
from datetime import datetime, timezone

from harness.run_state import atomic_json
from scripts import analyze_verified_rescues as base

ROOT = base.ROOT
OUT = Path('docs/analysis/reachable_rescues_20261016')
CACHE = Path('.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial')
JOB = Path('.cache/overnight_rescues_20261016')


def progress(step, completed, findings, remaining, artifacts=()):
    atomic_json(ROOT / JOB / 'progress.json', dict(updated_at_utc=datetime.now(timezone.utc).isoformat(),
        current_step=step, completed=completed, findings=findings, remaining=remaining, artifacts=list(artifacts)))


# These categories describe changed text, not verified semantic fixes. No strings
# or arbitrary identifiers from generated code are copied to public artifacts.
PATTERNS = {
    'import_API': r'^\s*(from|import)\b|\b(Aer|execute|transpile|AerSimulator|Statevector)\b',
    'circuit_interface': r'\b(build_circuit|QuantumCircuit|QuantumRegister|ClassicalRegister)\b|\breturn\b',
    'quantum_logic': r'\.(h|x|y|z|s|sdg|t|tdg|cx|cz|ccx|cp|swap|rx|ry|rz|p|u|append|compose|inverse|control)\s*\(|\b(QFT|Grover|pi)\b',
    'measurement_output': r'\b(measure|measure_all|save_statevector|get_statevector|get_counts|counts|result|run)\b',
}


def static_delta(before, after):
    """Count changed lines and flag lexical areas; never evaluate source."""
    changed = [s[1:] for s in difflib.ndiff(before.splitlines(), after.splitlines())
               if s.startswith(('+ ', '- '))]
    result = dict(changed_lines=len(changed), code_changed=before != after)
    for category, pattern in PATTERNS.items():
        result['changed_' + category] = any(re.search(pattern, line) for line in changed)
    for label, text in [('before', before), ('after', after)]:
        try:
            ast.parse(text)
            result[label + '_parses'] = True
        except (SyntaxError, ValueError):
            result[label + '_parses'] = False
    result['changed_other_text'] = bool(changed) and not any(result['changed_' + k] for k in PATTERNS)
    # Only fixed API/gate names are exposed, never arbitrary model text.
    known = ('Aer','execute','transpile','AerSimulator','Statevector','QuantumCircuit',
             'QuantumRegister','ClassicalRegister','build_circuit','measure','measure_all',
             'save_statevector','get_statevector','get_counts','counts','result','run',
             'h','x','y','z','cx','cz','ccx','cp','swap','rx','ry','rz','p','append','compose',
             'inverse','control','QFT','pi')
    def features(text):
        tokens = Counter(re.findall(r'[A-Za-z_][A-Za-z_0-9]*', text))
        return {k: tokens[k] for k in known}
    a, b = features(before), features(after)
    result['whitelist_symbol_count_changes'] = ';'.join(f'{k}:{a[k]}>{b[k]}' for k in known if a[k]!=b[k])
    result['removed_execute_symbol'] = a['execute'] > 0 and b['execute'] == 0
    result['added_AerSimulator_symbol'] = a['AerSimulator'] == 0 and b['AerSimulator'] > 0
    result['added_transpile_symbol'] = a['transpile'] == 0 and b['transpile'] > 0
    result['added_build_circuit_symbol'] = a['build_circuit'] == 0 and b['build_circuit'] > 0
    result['measurement_symbol_count_changed'] = any(a[k] != b[k] for k in ('measure','measure_all'))
    result['output_retrieval_symbol_count_changed'] = any(a[k] != b[k] for k in ('save_statevector','get_statevector','get_counts','counts'))
    result['interpretation'] = 'observed_text_change; causal_role_not_identified'
    return result


def cost_value(item):
    vals = {k: float(item[k]) for k in ('tokens_in', 'tokens_out', 'elapsed_sec')}
    if any(not math.isfinite(v) or v < 0 for v in vals.values()):
        raise ValueError('Invalid cost')
    if any(vals[k] != int(vals[k]) for k in ('tokens_in', 'tokens_out')):
        raise ValueError('Nonintegral token count')
    return dict(tokens_in=int(vals['tokens_in']), tokens_out=int(vals['tokens_out']),
                tokens=int(vals['tokens_in'] + vals['tokens_out']), generation_seconds=vals['elapsed_sec'])


def cost_summary(ledger, rounds):
    """Shared initial generation is excluded, failures consume repair budget too."""
    by_key = defaultdict(list)
    for r in rounds:
        by_key[r['record_key']].append(r)
    groups = defaultdict(list)
    for row in ledger:
        for scope, source in [('pooled', ''), ('source', row['source_dir'])]:
            for grouping, fields in base.GROUPINGS.items():
                groups[(scope, source, grouping, tuple(row[k] for k in fields), row['condition_id'])].append(row)
    summaries = []
    for (scope, source, grouping, values, condition), rows in sorted(groups.items()):
        independent = condition == base.P
        nfail = sum(not r['initial_success'] for r in rows)
        total_rescued = sum(r['rescued'] for r in rows)
        for cap in ((0,) if independent else (1, 2, 3)):
            selected = [r for row in rows for r in by_key[row['record_key']]
                        if r['round'] <= cap and (independent or r['round'] > 0)]
            rescued = sum(r['rescued'] and (independent or r['stop_round'] <= cap) for r in rows)
            s = dict(scope=scope, source_dir=source, grouping=grouping,
                **dict(zip(base.GROUPINGS[grouping], values)), condition_id=condition, cap=cap,
                comparison_kind='independent_generation' if independent else 'observed_history_truncation',
                pairs=len(rows), initial_successes=len(rows)-nfail, initial_failures=nfail,
                rescued=rescued, rescue_rate=rescued/nfail if nfail else '',
                lost_vs_cap3=total_rescued-rescued,
                lost_fraction_of_cap3=(total_rescued-rescued)/total_rescued if total_rescued else '',
                generation_requests=len(selected))
            for origin in ('saved_prefix', 'new_suffix'):
                subset = [r for r in selected if r['origin'] == origin]
                s[origin + '_requests'] = len(subset)
                for metric in ('tokens_in', 'tokens_out', 'tokens', 'generation_seconds'):
                    s[origin + '_' + metric] = sum(r[metric] for r in subset)
            for metric in ('tokens_in', 'tokens_out', 'tokens', 'generation_seconds'):
                s[metric] = sum(r[metric] for r in selected)
            s['tokens_per_rescue'] = s['tokens']/rescued if rescued else ''
            s['seconds_per_rescue'] = s['generation_seconds']/rescued if rescued else ''
            # Spending on all ultimately unrescued cases, not only successful paths.
            failed_keys = {r['record_key'] for r in rows if not r['initial_success'] and
                           not (r['rescued'] and (independent or r['stop_round'] <= cap))}
            s['unrescued_tokens'] = sum(r['tokens'] for r in selected if r['record_key'] in failed_keys)
            s['unrescued_seconds'] = sum(r['generation_seconds'] for r in selected if r['record_key'] in failed_keys)
            summaries.append(s)
    metrics = ('pairs','initial_successes','initial_failures','rescued','generation_requests',
               'tokens_in','tokens_out','tokens','generation_seconds','unrescued_tokens',
               'unrescued_seconds','saved_prefix_tokens','new_suffix_tokens',
               'saved_prefix_generation_seconds','new_suffix_generation_seconds')
    for total in [r for r in summaries if r['scope']=='pooled' and r['grouping']=='overall']:
        for scope in ('pooled','source'):
            for grouping in base.GROUPINGS:
                partition=[r for r in summaries if r['scope']==scope and r['grouping']==grouping
                    and r['condition_id']==total['condition_id'] and r['cap']==total['cap']]
                if any(not math.isclose(sum(r[k] for r in partition),total[k],rel_tol=1e-10,abs_tol=1e-6)
                       for k in metrics):
                    raise ValueError('Cost strata/source partition mismatch')
    return summaries


def run(root=ROOT, output=OUT):
    out = root / output
    out.mkdir(parents=True, exist_ok=True)
    # Re-run full public source/hash/coverage/stopping validation into a NEW folder.
    summary = base.run(root, output / 'core')
    inputs = json.loads((out/'core/manifest.json').read_text())['inputs']
    def csv(directory, name):
        return base.read_csv(root / directory / name)
    mixed = csv(base.FOLLOWUP, 'mixed_path_records.csv')
    saved = csv(base.FULL, 'round_comparison.csv')
    partial = csv(base.FOLLOWUP, 'partial_rerun_records.csv')
    new = csv(base.FOLLOWUP, 'partial_new_rounds.csv')
    paths = base.build_paths(mixed, saved, partial, new)
    difficulties = {t.id: t.task_difficulty for t in base.all_tasks()}
    ledger, repairs, overlaps, fd = base.analyze(mixed, paths, difficulties)
    settings = json.loads((root/base.FOLLOWUP/'settings_manifest.json').read_text())
    raw = {}
    for source in settings['sources']:
        path = Path(source['source_dir'])/'raw.jsonl'
        digest = base.sha(root/path)
        if digest != source['raw_sha256']:
            raise ValueError('Raw source integrity mismatch')
        inputs[str(path)] = digest
        with (root/path).open() as handle:
            for line in handle:
                record = json.loads(line)
                ident = (source['source_dir'], record['model_spec'], record['task_id'],
                         str(record['base_seed']), record['condition_id'])
                if ident in raw:
                    raise ValueError('Duplicate raw record')
                raw[ident] = {int(r['round']): r for r in record['rounds']}
    branch = {r['record_key']: int(r['branch_input_round']) for r in partial}
    suffix = {}
    for key in branch:
        path = CACHE/key/'completed.json'
        d = json.loads((root/path).read_text())
        if (root/path.with_suffix('.sha256')).read_text().strip() != base.sha(root/path):
            raise ValueError('Suffix checkpoint integrity mismatch')
        inputs[str(path)] = base.sha(root/path)
        suffix[key] = {r['round']: r for r in d['suffix']}
    metadata = {r['record_key']: r for r in ledger}
    rounds, codes = [], {}
    for record in mixed:
        key = record['record_key']
        for index, evaluation in enumerate(paths[key]):
            origin = 'new_suffix' if index >= branch.get(key, 4) else 'saved_prefix'
            item = suffix[key][index] if origin == 'new_suffix' else raw[base.identity(record)][index]
            code = item['code'] if origin == 'new_suffix' else item['extracted_code']
            digest = __import__('hashlib').sha256(code.encode()).hexdigest()
            if digest != evaluation.get('code_sha256', evaluation.get('new_code_sha256')):
                raise ValueError('Reachable code hash mismatch')
            c = cost_value(item)
            if origin == 'new_suffix':
                expected = cost_value(evaluation)
                if c != expected:
                    raise ValueError('Suffix public cost mismatch')
            codes[(key, index)] = code
            dims = metadata.get(key, {k: record[k] for k in ('record_key','source_dir','model_spec','task_id','base_seed','condition_id')})
            rounds.append(dict(**dims, round=index, origin=origin, code_sha256=digest,
                new_L3=base.truth(evaluation['new_L3']), new_error_category=evaluation['new_error_category'], **c))
        # Public reconstructed cost includes round zero, so subtracting later is explicit.
        owned = rounds[-len(paths[key]):]
        for field, expected_field in [('tokens_in','saved_prefix_allocated_tokens_in'),
                 ('tokens_out','saved_prefix_allocated_tokens_out'), ('generation_seconds','saved_prefix_allocated_elapsed_sec')]:
            if not math.isclose(sum(r[field] for r in owned), float(record[expected_field]) + float(record['new_' + ('elapsed_sec' if field == 'generation_seconds' else field)]), rel_tol=1e-10, abs_tol=1e-6):
                raise ValueError('Reconstructed cost reconciliation failed')
    # Check fixed aggregates before interpreting anything.
    overall = {r['condition_id']: r for r in repairs if r['scope']=='pooled' and r['grouping']=='overall'}
    if [(overall[c]['initial_failures'], overall[c]['initial_successes'], overall[c]['rescued']) for c in base.REPAIRS] != [(545,455,96),(545,455,183),(545,455,180)]:
        raise ValueError('Fixed aggregate mismatch; investigate instead of rewriting')
    fd_total = next(r for r in fd if r['scope']=='pooled' and r['grouping']=='overall')
    if [fd_total[k] for k in ('both','F_only','D_only','neither')] != [140,43,40,322]:
        raise ValueError('Fixed overlap mismatch')
    discordant = {tuple(str(r[k]) for k in ('source_dir','model_spec','task_id','base_seed')): r
                  for r in overlaps if r['cohort'] in ('F_only','D_only')}
    transitions, cases = [], []
    for pair, case in sorted(discordant.items()):
        for condition in ('execution_feedback','self_debugging'):
            row = next(r for r in ledger if tuple(str(r[k]) for k in ('source_dir','model_spec','task_id','base_seed')) == pair and r['condition_id']==condition)
            key = row['record_key']
            history = [r for r in rounds if r['record_key']==key]
            flags = Counter()
            for prev, cur in zip(history, history[1:]):
                delta = static_delta(codes[(key,prev['round'])], codes[(key,cur['round'])])
                flags.update(k for k,v in delta.items() if k.startswith('changed_') and isinstance(v,bool) and v)
                transitions.append(dict(**row, cohort=case['cohort'], from_round=prev['round'], to_round=cur['round'],
                    from_code_sha256=prev['code_sha256'], to_code_sha256=cur['code_sha256'],
                    from_origin=prev['origin'], to_origin=cur['origin'],
                    from_error=prev['new_error_category'], to_error=cur['new_error_category'],
                    to_L3=cur['new_L3'], **delta))
            cases.append(dict(**row, cohort=case['cohort'], reachable_rounds=len(history),
                initial_code_sha256=history[0]['code_sha256'], final_code_sha256=history[-1]['code_sha256'],
                error_path=' > '.join(r['new_error_category'] for r in history),
                origins=' > '.join(r['origin'] for r in history),
                **{'any_changed_'+k:bool(flags['changed_'+k]) for k in PATTERNS},
                annotation='all_reachable_transitions_inspected_statically; no_causal_attribution'))
    if len(cases)!=166:
        raise ValueError('Discordant coverage mismatch')
    base.write_csv(out/'discordant_cases.csv',cases)
    base.write_csv(out/'discordant_transitions.csv', transitions)
    # Summary keeps the 83-pair denominator, including rows with no tagged change.
    ds = []
    for grouping, fields in base.GROUPINGS.items():
        groups = defaultdict(list)
        for c in cases:
            groups[(tuple(c[k] for k in fields), c['cohort'],c['condition_id'])].append(c)
        for (values, cohort, condition), items in sorted(groups.items()):
            ds.append(dict(grouping=grouping, **dict(zip(fields,values)), cohort=cohort,condition_id=condition,
                pairs=len(items), all_discordant_pairs=83, share_of_83=len(items)/83,
                rescued=sum(r['rescued'] for r in items),
                **{'pairs_with_'+k:sum(r['any_changed_'+k] for r in items) for k in PATTERNS}))
    base.write_csv(out/'discordant_summary.csv',ds)
    progress('段階1終了・段階2開始：現行経路の追加コスト集計', ['出典整合性確認','Fのみ43組・Dのみ40組の両条件166履歴を静的確認'], ['83組の全到達修正をhash・由来付きで公開CSV化'], ['救済コスト','3回目の寄与','資料更新・PDF検証'])
    costs = cost_summary(ledger,rounds)
    base.write_csv(out/'reachable_rounds.csv',rounds)
    base.write_csv(out/'cost_by_cap_and_stratum.csv',costs)
    overall_costs=[r for r in costs if r['scope']=='pooled' and r['grouping']=='overall']
    third=[]
    for r in costs:
        if r['cap']!=3: continue
        prior=next(p for p in costs if all(p[k]==r[k] for k in ('scope','source_dir','grouping','condition_id',*base.GROUPINGS[r['grouping']])) and p['cap']==2)
        added=r['rescued']-prior['rescued']
        third.append(dict(**r, additional_rescues=added, at_risk_after_2=r['initial_failures']-prior['rescued'],
            third_round_requests=r['generation_requests']-prior['generation_requests'],
            third_round_tokens=r['tokens']-prior['tokens'], third_round_seconds=r['generation_seconds']-prior['generation_seconds'],
            third_tokens_per_extra_rescue=(r['tokens']-prior['tokens'])/added if added else '',
            third_seconds_per_extra_rescue=(r['generation_seconds']-prior['generation_seconds'])/added if added else '',
            loss_if_stop_at_2=added/r['rescued'] if r['rescued'] else ''))
    base.write_csv(out/'third_round_summary.csv',third)
    late=[r for r in ledger if r['condition_id'] in base.REPAIRS and r['rescued'] and r['stop_round']==3]
    base.write_csv(out/'third_round_rescues.csv',late)
    snapshot=dict(captured_at_utc=summary['captured_at_utc'],status='verified',primary=summary,
        discordant_pairs=83,discordant_condition_paths=166,discordant_transitions=len(transitions),
        overall_costs=overall_costs,third_round=[r for r in third if r['scope']=='pooled' and r['grouping']=='overall'],
        monetary_cost='not_measured',cost_scope='reconstructed reachable path; saved-prefix recorded cost + measured new-suffix cost; not full fresh experiment',
        static_scope='lexical changed-line categories plus parse checks; no semantic or causal attribution')
    atomic_json(out/'results_snapshot.json',snapshot)
    sanity=dict(passed=True,condition_records=5000,initial_groups=1000,discordant_pairs=83,
        discordant_condition_paths=166,discordant_transition_count=len(transitions),
        reachable_rounds=len(rounds),all_reachable_code_hashes_verified=True,raw_source_hashes_verified=True,
        checkpoint_hashes_verified=True,public_suffix_costs_verified=True,reconstructed_costs_reconciled=True,
        fixed_counts_match=True,unreachable_saved_suffixes_excluded=True,missing=0,duplicates=0,
        new_llm_requests=0,generated_code_executions=0)
    atomic_json(out/'sanity_report.json',sanity)
    render(out,snapshot,ds)
    atomic_json(out/'manifest.json',dict(captured_at_utc=summary['captured_at_utc'],inputs=inputs,
        source_settings=settings['sources'], script_sha256=base.sha(Path(__file__)),
        outputs={str(p.relative_to(out)):base.sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}))
    progress('段階2・3・4終了：現行経路のコスト・3回目寄与・再現用成果物作成済み',
        ['83組・166履歴の静的分析','現行経路の追加コスト集計','3回目の寄与と上限2で失う割合','再実行可能スクリプトと公開成果物'],
        ['R救済96/545、F183/545、D180/545','Fの3回目28組、Dの3回目33組'],
        ['関連テスト','継続レポート・発表資料更新','両PDFビルド・目視検証'],[str(output/'README.md')])
    return snapshot


def render(out,snapshot,ds):
    lines=['# 到達可能な介入履歴・救済コスト・3回目の寄与（2026-10-16）','',
        '研究の主題は初期失敗コードの救済である。1,000初期組・5,000条件記録、初期成功455組・失敗545組。R 96/545（17.6%）、F 183/545（33.6%）、D 180/545（33.0%）。初期成功455組は無修正で保持。Pは独立生成で、失敗からの成功124/545、成功に対応する失敗106/455、最終成功473/1,000。','',
        '## 83組の全履歴','',
        f"Fのみ43組・Dのみ40組の全83組について両条件166履歴、{snapshot['discordant_transitions']}修正遷移を静的確認した。分岐後の旧保存suffixは使用しない。旧20261013分析の42/42とは異なる。",'',
        '`discordant_cases.csv`は1組×2条件の166行、`discordant_transitions.csv`は到達した各修正の前後round・code hash・由来・失敗分類・静的差分注記。既知API/ゲート名の出現数変化と、executeの消失、AerSimulator/transpile/build_circuitの出現、測定/出力取得名の変化、構文解析の成否を全遷移で注記する。成功に到達した遷移はto_L3=Trueで識別できる。`discordant_summary.csv`はモデル・タスク・初期失敗類型等の全層を含み、各層の組数と全83組中の割合を併記する。','',
        '注記は変更行に対するimport/API、回路構築インターフェース、量子ゲート論理、測定/出力取得の複数該当可の機械的分類と構文解析である。コードは文字列として読み、実行しない。変更が成功と同時に観測された事実と、その変更が救済原因だったとの推測は区別する。ゲートのテキスト変更は量子論理の訂正の証明ではない。該当なしも除外せず、生成コード・prompt・応答・生例外文は公開しない。','',
        '## 追加生成コスト','',
        '| 条件 | 救済 | 保存prefix tokens | 新suffix tokens | 追加tokens/救済 | 生成要求秒/救済 | 未救済へのtokens |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in snapshot['overall_costs']:
        if r['cap']!=3:continue
        lines.append(f"| {base.LABELS[r['condition_id']]} | {r['rescued']}/545 | {r['saved_prefix_tokens']:,} | {r['new_suffix_tokens']:,} | {r['tokens_per_rescue']:,.1f} | {r['seconds_per_rescue']:,.1f} | {r['unrescued_tokens']:,} |")
    lines += ['', 'R/F/Dは共有初期生成を除外し、未救済への消費を含めた。tokensは入力＋出力。時間は保存された生成要求のelapsed_secの和で、評価時間・全工程時間ではない。保存prefixは過去の記録値、新suffixは部分追試時の実測値であり、合計は再構成経路の計算値。全件新実験の実測コストや実測の費用削減とは呼ばない。元記録の待機・再送処理や負荷差の影響を含み得る。金銭費用は未測定。Pは1,000独立生成のコストを別行（cap=0）に保存し、修正追加コストとして比較しない。','',
        '## 3回目の追加救済と消費','',
        '| 条件 | 追加救済/2回後未救済 | 3回目tokens | 3回目要求秒 | 2回で失う救済割合 |','| --- | ---: | ---: | ---: | ---: |']
    for r in snapshot['third_round']:
        lines.append(f"| {base.LABELS[r['condition_id']]} | {r['additional_rescues']}/{r['at_risk_after_2']} | {r['third_round_tokens']:,} | {r['third_round_seconds']:,.1f} | {100*r['loss_if_stop_at_2']:.1f}% |")
    lines += ['', '同じ最大3修正の履歴を回数で区切る集計で、上限別の独立実験ではない。3回目でしか救済できない例はFで28/183（15.3%）、Dで33/180（18.3%）。上限2/3の一般的最適性を断定しない。','',
        '## ファイルと再実行','',
        '- `core/`：現行救済率・全分母・元実験別・モデル×タスク/初期失敗類型別の再検証コピー。旧固定分析は保持。',
        '- `reachable_rounds.csv`：全到達roundのコードhash、由来、記録tokens・要求時間。',
        '- `cost_by_cap_and_stratum.csv`：上限別の経路計算値、分母、未救済消費、prefix/suffix別消費。',
        '- `third_round_summary.csv`・`third_round_rescues.csv`：3回目の追加救済と全対象。',
        '- `results_snapshot.json`・`manifest.json`・`sanity_report.json`・`validation_report.json`：固定値と出典hash・検証。','',
        '`.venv/bin/python -m scripts.analyze_reachable_rescue_history`で再集計。保存rawと部分追試cacheへの読み取り権限が必要。`.venv/bin/python -m pytest tests/test_analyze_reachable_rescue_history.py tests/test_analyze_verified_rescues.py`で検証。新しいモデル生成・生成コード実行・評価仕様変更は行わない。','',
        '## 方法の補足と限界','',
        '元3実験は3モデルseed 0〜9（1,500条件記録）、5モデルseed 10〜19（2,500）、残り2モデルseed 0〜9（1,000）。各実験の保存設定・schema・診断文処理差をmanifestへ保持。evaluation_policy_v4による検証済み保存prefixと必要な新suffix（部分追試293ケース）を組み合わせた現在の経路を主結果とする。旧結果・再採点・部分追試を三つの主結果として並べない。詳細は[追試記録](../reevaluation_followup_20261015/README.md)。','',
        '主L3は指定入力の期待状態/分布と量子ビット数・命令数範囲への適合であり、全入力のアルゴリズム同値性を保証しない。共有初期・タスク・seed依存、有限shotsと未固定の測定乱数、1,024 tokens上限、出典間の処理・負荷差がある。因果効果、統計的有意差、一般的な最適介入は断定しない。旧120件（2モデル、seed 0〜2、2条件、L2終了）は主結果に合算しない。','']
    (out/'README.md').write_text('\n'.join(lines))
    # Data-derived observation table uses every pair, rather than selected examples.
    obs=['# 救済対象の違いとコストの解釈','', '全83組を分母にし、片側救済の全例を含めて検討した。以下は救済側の履歴での変更領域の該当組数（重複可）。失敗側にも同じ変更が現れ得るので、成功原因の認定ではない。','',
         '| 集合 | 全83組中 | import/API | 回路構築/IF | 量子論理のテキスト | 測定/出力 |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for cohort,condition in [('F_only','execution_feedback'),('D_only','self_debugging')]:
        r=next(r for r in ds if r['grouping']=='overall' and r['cohort']==cohort and r['condition_id']==condition)
        obs.append('| '+ ' | '.join([cohort,f"{r['pairs']}/83",*[str(r['pairs_with_'+k]) for k in PATTERNS]])+' |')
    for grouping, field in [('model','model_spec'),('task','task_id'),('baseline_error','baseline_error_category')]:
        obs += ['', '| '+field+' | Fのみ（/83） | Dのみ（/83） |', '| --- | ---: | ---: |']
        labels=sorted({str(r[field]) for r in ds if r['grouping']==grouping})
        for label in labels:
            counts=[]
            for cohort, condition in [('F_only','execution_feedback'),('D_only','self_debugging')]:
                counts.append(sum(r['pairs'] for r in ds if r['grouping']==grouping and str(r[field])==label
                                  and r['cohort']==cohort and r['condition_id']==condition))
            obs.append('| '+label.removeprefix('ollama:')+' | '+str(counts[0])+'/83 | '+str(counts[1])+'/83 |')
    obs += ['', '初期import失敗ではFのみ8組・Dのみ22組、build失敗では19組・11組。失敗類型とモデル・タスクは関連し、集約値だけから介入選択規則を確定できない。各例のerror_pathは観察事実であり、静的変更の因果的寄与は未同定。全モデル・タスク・失敗類型別内訳と失敗側の変更はdiscordant_summary.csv、全遷移はdiscordant_transitions.csvで追える。','',
        'FとDは救済数が近い一方、対象は共通140組・片側83組に分かれる。両方の結果を見て選ぶ集合223/545を実行前の選択方策の成功率と解釈しない。コストは未救済例にも消費されるため成功例だけで割る前に全修正消費を合算した。現行値と旧F/D191件の費用比を混ぜない。','',
        '次の研究課題は、別seed/タスクに対して介入選択や停止方策を事前固定して検証すること、静的差分の複数変更を意味的に分離して確認すること、生成長・負荷・測定乱数への依存を調べることである。今回その実験は行っていない。']
    (out/'findings.md').write_text('\n'.join(obs)+'\n')


if __name__=='__main__':
    result=run()
    print(json.dumps({k:result[k] for k in ('status','discordant_pairs','discordant_transitions','overall_costs')},ensure_ascii=False))
