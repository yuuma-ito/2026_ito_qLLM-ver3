"""Verify the supplement against case CSVs and the pre-edit manuscript."""
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import csv
import hashlib
import json
import re
import subprocess
import zipfile

from docx import Document
import pymupdf
import notification_supplement as supplement
from template_thesis import remap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = 'e991486'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def body(doc):
    result = []
    active = False
    for p in doc.paragraphs:
        if p.style.name == 'Heading 1' and p.text == 'はじめに':
            active = True
        if active:
            result.append((p.style.name, p.text))
    return result


def validate():
    previous_bytes = subprocess.check_output(
        ['git', 'show', f'{BASELINE}:docs/graduation2026/thesis.docx'], cwd=ROOT)
    previous = Document(BytesIO(previous_bytes))
    current_bytes = (HERE / 'thesis.docx').read_bytes()
    current = Document(BytesIO(current_bytes))
    pdf = pymupdf.open(HERE / 'thesis.pdf')
    norm = lambda text: re.sub(r'\s+', '', text)
    added = {remap(text) for text in (supplement.TITLE, supplement.METHOD, supplement.DISCUSSION)}
    added.add('表11 補足実験の追加1回によるL3成功（初期失敗545組）')
    retained = [(s, t.replace('表12', '表11')) for s, t in body(current) if t not in added]
    tables = lambda doc: [[[c.text for c in r.cells] for r in t.rows] for t in doc.tables]
    def media(data):
        with zipfile.ZipFile(BytesIO(data)) as z:
            return {n: sha(z.read(n)) for n in z.namelist() if n.startswith('word/media/')}
    texts = [norm(p.get_text()) for p in pdf]
    baseline_body = [(s, remap(t) if t.startswith('第2章で関連研究') else t) for s, t in body(previous)]
    checks = {
        'only_approved_body_additions_source_version_correction_and_catalog_reference_renumbering': retained == baseline_body,
        'exactly_four_added_body_paragraphs': len(body(current)) - len(body(previous)) == 4,
        'eleven_existing_tables_unchanged': tables(previous) == tables(current)[:10] + tables(current)[11:],
        'four_existing_figures_unchanged': len(media(current_bytes)) == 4 and media(previous_bytes) == media(current_bytes),
        'supplement_table_matches_csv': tables(current)[10][1:] == supplement.table_rows(),
        'all_added_prose_in_word_and_pdf': all(
            sum(p.text == remap(t) for p in current.paragraphs) == 1
            and norm(remap(t)) in ''.join(texts) for t in (supplement.METHOD, supplement.DISCUSSION)),
        'result_on_page_23': norm('4.8 補足実験：失敗通知と詳細診断の比較') in texts[22],
        'discussion_on_page_24': norm(remap(supplement.DISCUSSION)) in texts[23],
        'total_pages_35': len(pdf) == 35,
    }
    checked_rows = 0
    source_files = []
    for stage in ('stage1', 'final'):
        paths = [supplement.SOURCE / stage / n for n in ('summary.csv', 'success_overlap.csv')]
        source_files.extend(paths)
        with paths[1].open() as f:
            cases = list(csv.DictReader(f))
        assert len(cases) == len({r['case_id'] for r in cases}) == 545
        with paths[0].open() as f:
            for row in csv.DictReader(f):
                key = None if row['grouping'] == 'overall' else row['grouping']
                selected = cases if key is None else [r for r in cases if r[key] == row['group']]
                count = sum(r[row['condition']] == 'True' for r in selected)
                assert len(selected) == int(row['initial_failures']) and count == int(row['successes'])
                assert abs(count / len(selected) - float(row['success_rate'])) < 1e-12
                checked_rows += 1
    checks['all_138_summary_rows_recounted_from_unique_case_csvs'] = checked_rows == 138
    source_files.extend(supplement.SOURCE / n for n in (
        'experiment_plan.txt', 'manifest.json', 'packet_verification/sanity_report.json'))
    source_files.append(ROOT / 'results/notification_ablation_20261105T164644282604Z/experiment_config.json')
    source_commit = subprocess.check_output(['git', 'rev-parse', '9128f4b'], cwd=ROOT, text=True).strip()
    checks['fixed_sources_match_published_commit'] = all(
        subprocess.check_output(['git', 'show', f'{source_commit}:{p.relative_to(ROOT)}'], cwd=ROOT) == p.read_bytes()
        for p in source_files)
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'passed': all(checks.values()), 'checks': checks,
        'baseline_commit': subprocess.check_output(['git', 'rev-parse', BASELINE], cwd=ROOT, text=True).strip(),
        'experiment_commit': source_commit,
        'source_sha256': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in source_files},
        'artifact_sha256': {n: sha((HERE/n).read_bytes()) for n in (
            'thesis.docx', 'thesis.pdf', 'notification_supplement.py', 'validate_notification_supplement.py')},
        'new_model_requests': 0, 'generated_code_executions': 0, 're_evaluations': 0,
        'limits': ['Saved case CSVs were recounted; generated code was not re-evaluated.',
                   'Independent manuscript review and Microsoft Word rendering were not performed.'],
    }
    (HERE / 'notification_supplement_validation_20261109.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'failed': [k for k, v in checks.items() if not v]}, ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    validate()
