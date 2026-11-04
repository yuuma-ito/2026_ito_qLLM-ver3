"""Cross-check published research evidence without generation, execution or scoring."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
B4 = Path('docs/analysis/measurement_ban_corrected_20261104')
CORE = B4 / 'core'
CATALOG = Path('docs/graduation2026/intervention_catalog.csv')
LABELS = {'R': 'self_refine', 'F': 'execution_feedback', 'D': 'self_debugging'}


def audit(root=ROOT, public=False):
    inputs, checks = {}, {}

    def data(path):
        path = str(path)
        value = (root / path).read_bytes()
        inputs[path] = hashlib.sha256(value).hexdigest()
        return value

    def rows(path):
        return list(csv.DictReader(data(path).decode().splitlines()))

    def one(values):
        values = list(values)
        if len(values) != 1:
            raise ValueError(f'Expected one matching row; found {len(values)}')
        return values[0]

    manifest = json.loads(data(B4 / 'source_manifest.json'))
    # Keep the public check key for compatibility with corruption regression tests.
    checks['nine_frozen_hashes'] = bool(manifest['outputs']) and all(
        hashlib.sha256(data(B4 / p)).hexdigest() == h
        for p, h in manifest['outputs'].items())
    summary = rows(B4 / 'summary.csv')

    def total(label, grouping='overall', group='all'):
        return one(r for r in summary if r['condition'] == label
                   and r['generation_cap'] == '4'
                   and r['grouping'] == grouping and r['group'] == group)

    b4 = total('B4')
    checks['B4_headline_counts'] = all(int(b4[k]) == v for k, v in {
        'groups': 1000, 'initial_failures': 545, 'final_L3_successes': 671,
        'successes_from_initial_failure': 216, 'additional_requests': 1343,
        'additional_tokens': 996223}.items())
    checks['B4_tokens_arithmetic'] = (
        int(b4['additional_tokens_in']) + int(b4['additional_tokens_out']) == 996223
        and round(float(b4['tokens_per_added_success']), 1) == round(996223 / 216, 1))
    metrics = ('groups', 'initial_failures', 'final_L3_successes',
               'successes_from_initial_failure', 'additional_requests', 'additional_tokens')
    checks['B4_strata_reconcile'] = all(
        sum(int(r[k]) for r in summary if r['condition'] == 'B4'
            and r['generation_cap'] == '4' and r['grouping'] == grouping) == int(b4[k])
        for grouping in ('model', 'task', 'difficulty', 'initial_failure') for k in metrics)
    repetitions = rows(B4 / 'repetitions.csv')
    identity = lambda r: (r['model_spec'], r['task_id'], r['base_seed'])
    checks['B4_request_and_success_rows'] = (
        len(repetitions) == len({(*identity(r), r['round']) for r in repetitions}) == 1343
        and len({identity(r) for r in repetitions if r['L3'] == 'True'}) == 216)
    first = rows(B4 / 'first_success.csv')
    checks['B4_first_success_partition'] = {
        r['first_success_generation']: int(r['groups']) for r in first
        if r['condition'] == 'B4'} == {
            'generation_1': 455, 'generation_2': 118, 'generation_3': 56,
            'generation_4': 42, 'never': 329}
    sanity = json.loads(data(B4 / 'sanity_report.json'))
    checks['saved_sanity'] = (sanity['passed'] is True and sanity['groups'] == 1000
                              and all(sanity[k] == 0 for k in ('missing', 'duplicates', 'unexpected')))
    paired = rows(CORE / 'paired_records.csv')
    rescues = {}
    for label, condition in LABELS.items():
        selected = [r for r in paired if r['condition_id'] == condition]
        rescues[label] = {identity(r) for r in selected if r['rescued'] == 'True'}
        checks[f'{label}_original_pair_records'] = (
            len(selected) == len({identity(r) for r in selected}) == 1000
            and sum(r['initial_success'] == 'False' for r in selected) == 545
            and len(rescues[label]) == {'R': 96, 'F': 183, 'D': 179}[label]
            and all((r['rescued'] == 'True') == (
                r['initial_success'] == 'False' and r['final_success'] == 'True') for r in selected)
            and int(total(label)['successes_from_initial_failure']) == len(rescues[label]))
    checks['F_D_discordant_sets'] = (len(rescues['F'] - rescues['D']) == 44
                                    and len(rescues['D'] - rescues['F']) == 40)
    catalog = rows(CATALOG)
    checks['catalog_shape_and_categories'] = len(catalog) == 3 and all(len(r) == 9 for r in catalog) and {
        r['initial_failure'] for r in catalog} == {'import_error', 'build_error', 'wrong_output'}
    checks['catalog_all_counts_and_rates'] = all(
        int(r['initial_failures']) == int(total(c, 'initial_failure', r['initial_failure'])['initial_failures'])
        and int(r[c + '_successes']) == int(total(c, 'initial_failure', r['initial_failure'])['successes_from_initial_failure'])
        and r[c + '_rate_percent'] == f"{100 * int(r[c + '_successes']) / int(r['initial_failures']):.1f}"
        for r in catalog for c in ('F', 'D', 'B4'))
    checks['catalog_F_D_original_pair_records'] = all(
        sum(r['condition_id'] == LABELS[c] and r['initial_success'] == 'False'
            and r['baseline_error_category'] == item['initial_failure'] for r in paired) == int(item['initial_failures'])
        and sum(r['condition_id'] == LABELS[c] and r['baseline_error_category'] == item['initial_failure']
                and r['rescued'] == 'True' for r in paired) == int(item[c + '_successes'])
        for item in catalog for c in ('F', 'D'))
    thesis = Path('docs/graduation2026/thesis.docx')
    data(thesis)
    with zipfile.ZipFile(root / thesis) as z:
        doc = ET.fromstring(z.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    # Read text elements only; formatting XML and field metadata are not cell content.
    tables = [[[''.join(n.text or '' for n in c.findall('.//w:t', ns))
                for c in row.findall('w:tc', ns)] for row in t.findall('w:tr', ns)]
              for t in doc.findall('.//w:tbl', ns)]
    cat_table = one(t for t in tables if t[0] == [
        '初期失敗類型', '初期失敗数', 'F救済率', 'D救済率', 'B4追加成功率'])
    checks['catalog_matches_Word_table'] = cat_table[1:] == [
        [r['label'], r['initial_failures'], *(r[c + '_rate_percent'] + '%' for c in ('F', 'D', 'B4'))]
        for r in catalog]
    main_table = one(t for t in tables if t[0] == ['条件', '初期失敗数', '追加成功数', '追加成功率'])
    checks['headline_matches_Word_table'] = main_table[1:] == [
        [c, '545', str(n), f'{100*n/545:.1f}%'] for c, n in [('R',96), ('F',183), ('D',179), ('B4',216)]]
    checks['inputs_equal_committed_bytes'] = all(subprocess.run(
        ['git', '-C', str(root), 'show', 'HEAD:' + p], capture_output=True).stdout == (root / p).read_bytes()
        for p in inputs)
    public_result = {'status': 'not_checked'}
    if public:
        url = 'https://api.github.com/repos/yuuma-ito/2026_ito_qLLM-ver3/'
        def fetch(path):
            request = urllib.request.Request(url + path, headers={'User-Agent': 'research-evidence-audit'})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        commit = fetch('commits/main')['sha']
        tree = fetch('git/trees/' + commit + '?recursive=1')
        blobs = {r['path']: r['sha'] for r in tree['tree'] if r['type'] == 'blob'}
        matched = {}
        for p in [*inputs, 'README.md', 'docs/analysis/public_evidence_check_20261102.json']:
            content = (root / p).read_bytes()
            matched[p] = blobs.get(p) == hashlib.sha1(
                b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
        checks['public_main_blobs_equal_local'] = not tree['truncated'] and all(matched.values())
        public_result = {'status': 'checked', 'commit': commit, 'tree_url': url + 'git/trees/' + commit,
                         'matched_blobs': matched}
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'scope': '直前に公開したREADMEの主要数値、B4固定分析、カタログ、Wordの対応表。論文全体の査読ではない。',
            'passed': all(checks.values()), 'checks': checks, 'inputs_sha256': inputs,
            'public_verification': public_result,
            'limits': ['保存済みsanityは照合したが、rawからの再集計・再採点は実施していない。',
                       '996,223 tokensは固定集計内の入力＋出力・層別合計との一致。API側の実消費の独立検証ではない。',
                       'hash一致は同じ内容である証拠であり、評価器・実験設計の正しさの証明ではない。',
                       'Wordの対象表を確認した。PDF表示、文献の真正性、全記述の独立査読は対象外。'],
            'new_model_requests': 0, 'generated_code_executions': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check-public', action='store_true', help='Read unauthenticated GitHub main commit/tree')
    args = parser.parse_args()
    result = audit(public=args.check_public)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'checks': len(result['checks']), 'report': str(args.out)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
