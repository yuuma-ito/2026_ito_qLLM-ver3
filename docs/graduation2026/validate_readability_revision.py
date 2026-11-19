"""Check table labels, printed source URLs and the conclusion's scope."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from docx import Document
import pymupdf
import build

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(before=None):
    doc = Document(HERE/'thesis.docx')
    pdf = pymupdf.open(HERE/'thesis.pdf')
    norm = lambda value: ''.join(value.split())
    text = '\n'.join(p.text for p in doc.paragraphs)
    table_page = next(p for p in pdf if '到達履歴の再構成を確認する手順' in p.get_text())
    lines = [norm(''.join(s['text'] for s in line['spans']))
             for block in table_page.get_text('dict')['blocks']
             for line in block.get('lines', [])]
    labels = ['初期照合', '評価版確認', '分岐確認', '追試開始', '履歴接続', '最終集計']
    record_ids = ['B1', 'A1・B2', 'A2', 'A3', 'A4・B1', 'A5・B3']
    tables = [[[c.text for c in r.cells] for r in t.rows] for t in doc.tables]
    ref_page = next(p for p in pdf if '[3]' in p.get_text() and build.FIXED_SOURCE_COMMIT in norm(p.get_text()))
    ref_text = norm(ref_page.get_text())
    urls = {link.get('uri') for link in ref_page.get_links()}
    def section(title):
        active = False
        result = []
        for p in doc.paragraphs:
            if p.style.name.startswith('Heading'):
                if active:
                    break
                active = p.text == title
            elif active:
                result.append(p.text)
        return '\n'.join(result)
    catalog = section('介入カタログの構成と適用範囲')
    conclusion = section('研究成果')
    future = section('今後の課題')
    checks = {
        'all_stage_labels_on_single_lines': all(label in lines for label in labels),
        'record_column_only_short_ids': [r[-1] for r in tables[1][1:]] == record_ids,
        'all_record_ids_on_single_lines': all(value in lines for value in record_ids),
        'record_file_legend_visible': all(value in norm(table_page.get_text()) for value in ['A1：settings_manifest.json', 'A4：partial_new_rounds.csv', 'B1：reachable_rounds.csv']),
        'repository_and_fixed_urls_printed': all(url in ref_text for url in [build.REPOSITORY_URL, build.FIXED_SOURCE_URL]),
        'repository_and_fixed_urls_clickable': {build.REPOSITORY_URL, build.FIXED_SOURCE_URL} <= urls,
        'duplicated_fixed_label_removed': '固定版：公開固定版' not in ref_text,
        'catalog_scope_repetition_removed': '最適介入の推奨規則ではない' in catalog and '無条件に推奨する規則ではない' not in catalog,
        'conclusion_separates_achievements_and_future': '観測結果を参照できる形に整理した' in conclusion and '未検証' not in conclusion and '介入選択方策の性能は未検証' in future,
    }
    if before:
        old = Document(before/'thesis.docx')
        previous = [[[c.text for c in r.cells] for r in t.rows] for t in old.tables]
        checks['all_12_other_tables_unchanged'] = previous[:1]+previous[2:] == tables[:1]+tables[2:]
        checks['table_2_content_columns_unchanged'] = all(a[1:3] == b[1:3] for a,b in zip(previous[1], tables[1]))
        def media(path):
            with ZipFile(path) as z:
                return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('word/media/')}
        checks['embedded_figures_unchanged'] = media(before/'thesis.docx') == media(HERE/'thesis.docx')
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'passed': all(checks.values()), 'checks': checks,
        'pages': len(pdf), 'tables': len(tables), 'figures':len(doc.inline_shapes),
        'table_page':table_page.number+1,'reference_page':ref_page.number+1,
        'artifact_sha256': {name:digest(HERE/name) for name in ['thesis.docx','thesis.pdf']},
        'scope':'表2・参考文献[3]の表示と5.2・6.1・6.2節の整理。ネットワーク接続や実験の再評価は行わない。',
        'limits':['全ページの再目視確認とMicrosoft Word上の最終表示確認は未実施。'],
    }
    (HERE/'readability_revision_validation_20261119.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path)
    validate(parser.parse_args().before)
