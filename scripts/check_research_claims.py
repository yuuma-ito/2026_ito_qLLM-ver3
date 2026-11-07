"""Check registered manuscript claims against pinned CSV snapshots; no scoring."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from harness.research_registry import local_path, read_json, sha256
from harness.run_state import ROOT, atomic_json

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def document(path):
    if path.suffix == '.docx':
        with zipfile.ZipFile(path) as z:
            tree = ET.fromstring(z.read('word/document.xml'))
        paragraphs = [''.join(n.text or '' for n in p.findall('.//w:t', NS))
                      for p in tree.findall('.//w:p', NS)]
        tables = [[[''.join(n.text or '' for n in cell.findall('.//w:t', NS))
                    for cell in row.findall('w:tc', NS)] for row in table.findall('w:tr', NS)]
                  for table in tree.findall('.//w:tbl', NS)]
        return '\n'.join(paragraphs), tables
    if path.suffix in {'.txt', '.md', '.tex'}:
        return path.read_text(encoding='utf-8'), []
    raise ValueError('Unsupported document type')


def audit(spec, root=ROOT):
    statuses, hashes, csv_cache, document_cache = [], {}, {}, {}
    def source_bytes(name):
        path = local_path(root, name)
        hashes[name] = sha256(path)
        return path.read_bytes()
    for name, expected in spec['sources'].items():
        try:
            source_bytes(name)
            statuses.append(dict(id='source:' + name, status='根拠と一致' if hashes[name] == expected else '不一致',
                                 scope='固定出典のSHA-256', source=name))
        except OSError:
            statuses.append(dict(id='source:' + name, status='根拠不足', source=name))

    for item in spec.get('manifest_checks', []):
        result = dict(id='manifest:' + item['path'], source=item['path'], status='根拠不足')
        try:
            if item['path'] not in spec['sources']:
                raise ValueError('Manifest not pinned')
            mapping = read_json(root, item['path'])[item['mapping']]
            matches = {}
            for name, digest in mapping.items():
                path = str(Path(item['base']) / name)
                source_bytes(path)
                matches[path] = hashes[path] == digest
            result.update(status='根拠と一致' if matches and all(matches.values()) else '不一致', matches=matches)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        statuses.append(result)

    def value(expression):
        if isinstance(expression, (str, int, float)):
            return str(expression)
        if 'csv' in expression:
            name = expression['csv']
            if name not in spec['sources']:
                raise ValueError('CSV source not pinned')
            if name not in csv_cache:
                csv_cache[name] = list(csv.DictReader(io.StringIO(source_bytes(name).decode('utf-8-sig'))))
            rows = [row for row in csv_cache[name] if all(row[key] == str(wanted)
                    for key, wanted in expression.get('where', {}).items())]
            if len(rows) != 1:
                raise ValueError('Expected exactly one source row')
            result = rows[0][expression['column']]
        elif 'ratio' in expression:
            numerator, denominator = (Decimal(value(v).replace(',', '')) for v in expression['ratio'])
            if denominator <= 0:
                raise ValueError('Invalid denominator')
            result = numerator / denominator * Decimal(str(expression.get('scale', 1)))
        elif 'join' in expression:
            return expression.get('separator', '').join(value(v) for v in expression['join'])
        else:
            raise ValueError('Unsupported expression')
        if 'digits' in expression:
            number = Decimal(str(result))
            if not number.is_finite():
                raise ValueError('Nonfinite source')
            result = f"{number:,.{expression['digits']}f}" if expression.get('thousands') else f"{number:.{expression['digits']}f}"
        return str(result) + expression.get('suffix', '')

    for claim in spec['claims']:
        result = dict(id=claim['id'], document=claim['document'], scope=claim.get('scope'), status='根拠不足')
        try:
            name = claim['document']
            if name not in document_cache:
                source_bytes(name)
                document_cache[name] = document(local_path(root, name))
            text, tables = document_cache[name]
            if claim['type'] == 'table':
                selected = [table for table in tables if table and table[0] == claim['headers']]
                expected = [[value(cell) for cell in row] for row in claim['rows']]
                actual = selected[0][1:] if len(selected) == 1 else None
                passed = actual == expected
                result.update(expected=expected, observed=actual, matching_tables=len(selected))
            elif claim['type'] == 'text':
                matches = list(re.finditer(claim['pattern'], text))
                expected = value(claim['value'])
                actual = [match.group('value') for match in matches]
                passed = len(matches) == claim.get('occurrences', 1) and all(s == expected for s in actual)
                # Only numeric captures, never arbitrary manuscript text, go into reports.
                if any(not re.fullmatch(r'[0-9,./%+−–〜：: \-]+', s) for s in actual):
                    raise ValueError('Only numeric captures may be reported')
                result.update(expected=expected, observed=actual)
            else:
                raise ValueError('Unsupported claim type')
            result['status'] = '根拠と一致' if passed else '不一致'
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, ET.ParseError, ArithmeticError):
            result['reason'] = '出典・対象箇所・一意の集計行を確認できません'
        statuses.append(result)
    return dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), scope=spec['scope'],
                passed=bool(spec['claims']) and all(r['status'] == '根拠と一致' for r in statuses),
                results=statuses, input_hashes=hashes, new_model_requests=0, generated_code_executions=0,
                limits=['登録した本文箇所・表・固定出典の照合のみ。未登録の記述は未確認。',
                        'CSVからの再計算と原稿の一致を確認する。rawからの再集計・採点は行わない。',
                        'hash一致は内容の同一性であり、評価基準や実験設計の正しさを保証しない。',
                        'PDFの表示・引用文献の真正性・公開先との一致は対象外。'])


def markdown(report):
    lines = ['# 論文の数値・出典照合', '', report['scope'], '',
             '判定: ' + ('登録範囲は根拠と一致' if report['passed'] else '不一致または根拠不足あり'), '',
             '| 検査ID | 判定 | 対象 |', '|---|---|---|']
    for r in report['results']:
        cells = [r['id'], r['status'], r.get('document', r.get('source', ''))]
        lines.append('| ' + ' | '.join(str(v).replace('|', '\\|') for v in cells) + ' |')
    lines += ['', *['- ' + s for s in report['limits']], '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', default='configs/research_claims.json')
    parser.add_argument('--out-dir', type=Path, default=ROOT / '.cache/research_claims')
    args = parser.parse_args(argv)
    try:
        result = audit(read_json(ROOT, args.spec), ROOT)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        atomic_json(args.out_dir / 'report.json', result)
        (args.out_dir / 'report.md').write_text(markdown(result), encoding='utf-8')
        print(json.dumps(dict(passed=result['passed'], checks=len(result['results']),
                              report=str(args.out_dir / 'report.md')), ensure_ascii=False))
        return 0 if result['passed'] else 1
    except (OSError, ValueError, KeyError, TypeError):
        print('Claim check failed; check the claim specification and repository paths.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
