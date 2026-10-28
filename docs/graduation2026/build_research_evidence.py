"""Prepare publication excerpts from frozen evidence without executing generated code."""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REACH = ROOT / 'docs/analysis/reachable_rescues_20261016'
B4 = ROOT / 'docs/analysis/independent_4_completed_20261022'
SETTINGS = ROOT / 'docs/analysis/reevaluation_followup_20261015/settings_manifest.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open() as handle:
        return list(csv.DictReader(handle))


def literal(tree, name):
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return ast.literal_eval(node.value)


def prompt_template(value):
    """Render only literal/f-string structure; do not import archived Python."""
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return value.value
    if isinstance(value, ast.JoinedStr):
        return ''.join(prompt_template(v) for v in value.values)
    if isinstance(value, ast.FormattedValue):
        expr = ast.unparse(value.value)
        return {'task.prompt_text': '〈課題仕様〉', 'prev_code': '〈前回コード〉',
                'diagnose(task, ev)': '〈直前の評価から生成した診断〉'}[expr]
    raise ValueError('Unrecognized prompt template node')


def build():
    inputs = {}
    for p in [SETTINGS, REACH/'discordant_cases.csv', REACH/'discordant_transitions.csv',
              REACH/'reachable_rounds.csv', B4/'summary.csv', REACH/'core/repair_summary.csv']:
        inputs[str(p.relative_to(ROOT))] = sha(p)
    settings = json.loads(SETTINGS.read_text())
    # All three source experiments used the same literal prompt functions/task texts.
    source_files = sorted({'prompts/system.txt', 'harness/interventions/prompts.py', 'harness/refine.py'}
                          | set(settings['sources'][0]['archived_tasks']))
    archived = {}
    for filename in source_files:
        versions = [subprocess.check_output(['git', 'show', s['git_commit']+':'+filename])
                    for s in settings['sources']]
        if not all(v == versions[0] for v in versions):
            raise ValueError('Prompt source versions differ: '+filename)
        if (ROOT/filename).read_bytes() != versions[0]:
            raise ValueError('Current prompt text differs from archived version: '+filename)
        archived[filename] = versions[0].decode()
        inputs[filename] = sha(ROOT/filename)
    tree = ast.parse(archived['harness/interventions/prompts.py'])
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_intervention_prompt')
    repairs = []
    for node in function.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            condition = ast.literal_eval(node.test.comparators[0])
            if condition in ['self_refine', 'execution_feedback', 'self_debugging']:
                returned = next(n for n in node.body if isinstance(n, ast.Return))
                repairs.append({'condition': condition, 'text': prompt_template(returned.value)})
    tasks = []
    for filename in sorted(archived):
        if not filename.startswith('tasks/t'):
            continue
        module = ast.parse(archived[filename])
        task = next(n.value for n in module.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'TASK' for t in n.targets))
        task_id = ast.literal_eval(next(k.value for k in task.keywords if k.arg == 'id'))
        tasks.append({'task_id': task_id, 'source': filename, 'text': literal(module, 'PROMPT')})
    tasks.sort(key=lambda task: task['task_id'])
    assert len(tasks) == 10 and len(repairs) == 3
    b4_manifest = json.loads((B4/'runner_manifest.json').read_text())
    b4_source = ROOT/'harness/independent_4.py'
    b4_hash = b4_manifest['implementation']['harness/independent_4.py']
    if b4_hash != sha(b4_source):
        raise ValueError('B4 runner differs from frozen implementation')
    if "prompt = build_initial_prompt('baseline', task)" not in b4_source.read_text():
        raise ValueError('B4 initial prompt construction changed')
    inputs[str(b4_source.relative_to(ROOT))] = sha(b4_source)
    inputs[str((B4/'runner_manifest.json').relative_to(ROOT))] = sha(B4/'runner_manifest.json')
    prompts = {'kind': 'archived_literal_templates_with_explicit_placeholders',
        'source_commits': [s['git_commit'] for s in settings['sources']],
        'provenance_limit': '固定テンプレートの復元掲載。個々のネットワーク要求全文の直接記録ではない。',
        'system': archived['prompts/system.txt'].strip(), 'tasks': tasks, 'repair_templates': repairs,
        'preventive_appendix': literal(tree, 'PREVENTIVE_SPEC'),
        'initial_rules': {'B/R/F/D': '課題仕様', 'P': '課題仕様 + 改行2個 + 予防的注意事項',
                          'B4': 'Bと共有する初回は保存コード。失敗後の各追加要求は同じ課題仕様だけ。'},
        'diagnostic_limit': '診断は各roundの評価値に依存する。保存schema・当時の評価処理と部分追試の判定の差を保持する。'}

    rows = read_csv(B4/'summary.csv')
    catalog = []
    for category, label in [('import_error','import失敗'), ('build_error','回路構築失敗'), ('wrong_output','出力不一致')]:
        found = {r['condition']: r for r in rows if r['grouping']=='initial_failure'
                 and r['group']==category and r['generation_cap']=='4'}
        counts = {c: int(found[c]['successes_from_initial_failure']) for c in ['F','D','B4']}
        denominator = int(found['F']['initial_failures'])
        assert all(int(found[c]['initial_failures']) == denominator for c in counts)
        catalog.append({'initial_failure':category,'label':label,'initial_failures':denominator,
                        **{c+'_successes':n for c,n in counts.items()},
                        **{c+'_rate_percent':f'{100*n/denominator:.1f}' for c,n in counts.items()}})
    with (HERE/'intervention_catalog.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(catalog[0]),lineterminator="\n");writer.writeheader();writer.writerows(catalog)

    selected_specs = [
        ('T7_IQFT_001','14','F_only',{'execution_feedback':{
            'before':['from qiskit.circuit import QFT'],
            'after':['from qiskit.circuit.library import QFT']}}),
        ('T8_QPE_001','10','D_only',{'self_debugging':{
            'before':['qc.inverse_qft(range(n_counting))'],
            'after':['from qiskit.circuit.library import QFT','iqft = QFT(n_counting, inverse=True)',
                     'qc.append(iqft.to_gate(), range(n_counting))']}}),
    ]
    cases = read_csv(REACH/'discordant_cases.csv')
    rounds = read_csv(REACH/'reachable_rounds.csv')
    transitions = read_csv(REACH/'discordant_transitions.csv')
    wanted = [r for r in cases if r['model_spec']=='ollama:gemma4:e4b-it-qat'
              and any((r['task_id'],r['base_seed'],r['cohort']) == s[:3] for s in selected_specs)]
    raw = {}
    for source in {r['source_dir'] for r in wanted}:
        path=ROOT/source/'raw.jsonl'; expected=next(s['raw_sha256'] for s in settings['sources'] if s['source_dir']==source)
        if sha(path)!=expected:raise ValueError('Saved raw source changed')
        inputs[str(path.relative_to(ROOT))]=sha(path)
        wanted_keys={(r['model_spec'],r['task_id'],int(r['base_seed']),r['condition_id']) for r in wanted if r['source_dir']==source}
        for line in path.open():
            item=json.loads(line);key=(item['model_spec'],item['task_id'],item['base_seed'],item['condition_id'])
            if key in wanted_keys:raw[key]={int(a['round']):a['extracted_code'] for a in item['rounds']}
    examples=[]
    for task_id, seed, cohort, snippets in selected_specs:
        records=[r for r in wanted if r['task_id']==task_id and r['base_seed']==seed]
        assert len(records)==2 and len({r['initial_code_sha256'] for r in records})==1
        published=[]
        for record in records:
            key=record['record_key'];rr=[r for r in rounds if r['record_key']==key]
            history=[]
            for row in rr:
                if row['origin']!='saved_prefix':raise ValueError('Selected example must use verified saved rounds')
                code=raw[(record['model_spec'],task_id,int(seed),record['condition_id'])][int(row['round'])]
                if hashlib.sha256(code.encode()).hexdigest()!=row['code_sha256']:raise ValueError('Code hash mismatch')
                history.append({k:row[k] for k in ['round','origin','code_sha256','new_L3','new_error_category']})
            excerpt=snippets.get(record['condition_id'])
            if excerpt:
                before=raw[(record['model_spec'],task_id,int(seed),record['condition_id'])][0]
                after=raw[(record['model_spec'],task_id,int(seed),record['condition_id'])][int(record['stop_round'])]
                assert all(s in before for s in excerpt['before']) and all(s in after for s in excerpt['after'])
                assert record['final_success']=='True'
            else:assert record['final_success']=='False'
            published.append({'condition_id':record['condition_id'],'record_key':key,
                'final_success':record['final_success']=='True','error_path':record['error_path'],
                'rounds':history,'excerpt':excerpt,
                'transition_count':sum(r['record_key']==key for r in transitions)})
        examples.append({'model_spec':records[0]['model_spec'],'task_id':task_id,'base_seed':int(seed),
                         'source_dir':records[0]['source_dir'],'cohort':cohort,'records':published,
                         'interpretation':'Observed changes and saved outcomes; causal role not identified.'})
    for name,data in [('experiment_prompts.json',prompts),('case_studies.json',examples)]:
        (HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    manifest={'inputs_sha256':inputs,'publication_scope':'固定プロンプトと明示プレースホルダー、選択2事例の短いコード抜粋とhashのみ。raw・応答全文・秘密情報なし。',
        'selection':'同じG4モデルのFのみ/Dのみ成功事例から、修正前後のAPI呼び出しを確認できる各1組を目的選択。頻度・代表性・因果効果を推定する標本ではない。',
        'catalog_scope':'初期失敗の主要3類型。観測率の比較であり介入選択の推奨規則ではない。',
        'outputs_sha256':{n:sha(HERE/n) for n in ['intervention_catalog.csv','experiment_prompts.json','case_studies.json']},
        'generated_code_executions':0,'new_model_requests':0}
    (HERE/'enrichment_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Prepared catalog, two verified saved-case excerpts, and archived prompt templates.')


if __name__=='__main__':build()
