"""Check the rendered PDF's bibliography links and corrected source paths."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

from docx import Document
import pymupdf
import build

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(before=None):
    pdf = pymupdf.open(HERE / 'thesis.pdf')
    doc = Document(HERE / 'thesis.docx')
    norm = lambda text: re.sub(r'\s+', '', text)
    bibliography = next(p for p in pdf if p.get_text().startswith('7 参考文献'))
    text = norm(bibliography.get_text())
    targets = {
        'https://arxiv.org/abs/2303.17651v2', 'https://arxiv.org/abs/2304.05128v2',
        'https://arxiv.org/abs/2107.03374v2', 'https://arxiv.org/abs/2108.07732',
        'https://arxiv.org/abs/2310.01798v2', 'https://arxiv.org/abs/2406.14712',
        'https://quantum.cloud.ibm.com/docs/en/guides/construct-circuits',
        'https://qiskit.github.io/qiskit-aer/',
        'https://github.com/yuuma-ito/2026_ito_qLLM-ver3', build.FIXED_SOURCE_URL,
    }
    links = [l for l in bibliography.get_links() if l.get('uri')]
    fixed_link = next(l for l in links if l['uri'] == build.FIXED_SOURCE_URL)
    word_targets = {r.target_ref for r in doc.part.rels.values()
                    if r.is_external and r.reltype.endswith('/hyperlink')}
    checks = {
        'all_ten_PDF_links_present': {l['uri'] for l in links} == targets,
        'all_ten_Word_links_present': word_targets == targets,
        'fixed_link_short_label': norm(build.FIXED_SOURCE_LABEL) in text and build.FIXED_SOURCE_URL not in text,
        'fixed_link_on_one_line': fixed_link['from'].height < 15,
        'full_commit_visible': build.FIXED_SOURCE_COMMIT in text,
        'reference_six_fixed_v2_2024': 'arXiv:2310.01798v2（2024）' in text,
        'all_nine_references_visible': all(f'[{i}]' in text for i in range(1, 10)),
    }
    appendix = next(p.get_text() for p in pdf if '追加計算コストの保存先' in p.get_text())
    cost_dir = 'docs/analysis/reachable_rescues_20261016/'
    checks['explicit_cost_directory'] = norm(cost_dir) in norm(appendix)
    checks['both_cost_files_exist'] = all((HERE.parents[1] / cost_dir / name).is_file()
        and name in norm(appendix) for name in ('cost_by_cap_and_stratum.csv', 'third_round_summary.csv'))
    checks['ambiguous_cost_pointer_removed'] = '同ディレクトリのcost_by_cap_and_stratum.csv' not in norm(appendix)
    pages = [norm(p.get_text()) for p in pdf]
    checks['all_54_table_rows_in_PDF'] = len(doc.tables) == 11 and sum(len(t.rows)-1 for t in doc.tables) == 54 and all(
        any(norm(''.join(c.text for c in row.cells)) in p for p in pages)
        for table in doc.tables for row in table.rows[1:])
    comparison = {}
    if before:
        old_pdf = pymupdf.open(before / 'thesis.pdf')
        old_doc = Document(before / 'thesis.docx')
        table_values = lambda d: [[[c.text for c in r.cells] for r in t.rows] for t in d.tables]
        def media(path):
            with zipfile.ZipFile(path) as z:
                return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('word/media/')}
        checks['eleven_tables_unchanged'] = table_values(old_doc) == table_values(doc)
        checks['four_figures_unchanged'] = len(media(HERE / 'thesis.docx')) == 4 and media(before / 'thesis.docx') == media(HERE / 'thesis.docx')
        checks['pages_1_to_27_unchanged'] = all(norm(old_pdf[i].get_text()) == pages[i] for i in range(27))
        checks['page_count_unchanged'] = len(old_pdf) == len(pdf) == 35
        comparison = {'previous_pdf_sha256': digest(before / 'thesis.pdf')}
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'passed': all(checks.values()),
              'checks': checks, 'pdf_pages': len(pdf), 'bibliography_page': bibliography.number + 1,
              'pdf_uri_targets': sorted({l['uri'] for l in links}), **comparison,
              'artifact_sha256': {n: digest(HERE / n) for n in (
                  'thesis.docx', 'thesis.pdf', 'build.py', 'template_thesis.py',
                  'thesis_expansion.py', 'bibliography_sources.json', 'validate_reference_links.py')},
              'scope': 'PDFリンクと対象文字列、Wordとの表一致、指定した変更前資料との差分。原論文の再確認は前段のpdf_reference_check_20261102.json参照。',
              'new_model_requests': 0, 'generated_code_executions': 0}
    (HERE / 'reference_links_validation_20261102.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'checks': checks}, ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path)
    validate(parser.parse_args().before)
