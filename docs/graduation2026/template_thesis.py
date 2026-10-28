"""Apply the user-transcribed template to the existing, sourced thesis draft.

The original .doc has not been supplied. Unknown settings are documented in
format_spec.json; this module does not assert institutional compliance.
"""
from copy import deepcopy
from pathlib import Path
import json
import re

from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import build as content

HERE = Path(__file__).resolve().parent
MARKER = 'user-transcribed-template-20261020'
FONTS = {'body': ('MS 明朝', 'Century'), 'heading': ('MS Pゴシック', 'Arial')}


def element(tag, **attrs):
    e = OxmlElement('w:' + tag)
    for key, value in attrs.items():
        e.set(qn('w:' + key), str(value))
    return e


def font(target, size=10.5, heading=False, bold=False):
    jp, latin = FONTS['heading' if heading else 'body']
    target.font.name = latin
    target.font.size = Pt(size)
    target.font.bold = bold
    target.font.color.rgb = RGBColor(0, 0, 0)
    rf = target.get_or_add_rPr().get_or_add_rFonts() if hasattr(target, 'get_or_add_rPr') else None
    if rf is None:
        owner = target._r if hasattr(target, '_r') else target.element
        rf = owner.get_or_add_rPr().get_or_add_rFonts()
    rf.attrib.clear()
    for key, name in [('ascii', latin), ('hAnsi', latin), ('cs', latin), ('eastAsia', jp)]:
        rf.set(qn('w:' + key), name)


def field(paragraph, code, value):
    paragraph.add_run()._r.append(element('fldChar', fldCharType='begin'))
    instruction = element('instrText')
    instruction.set(qn('xml:space'), 'preserve')
    instruction.text = ' ' + code + ' '
    paragraph.add_run()._r.append(instruction)
    paragraph.add_run()._r.append(element('fldChar', fldCharType='separate'))
    paragraph.add_run(value)
    paragraph.add_run()._r.append(element('fldChar', fldCharType='end'))


def configure(d):
    d.core_properties.title = content.TITLE
    d.core_properties.author = '伊藤 悠真'
    d.core_properties.category = MARKER
    d.core_properties.comments = 'ユーザー転記仕様に基づく草稿。原本未照合。題目の正式承認とWord上の最終確認は未実施。'
    sec = d.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin = sec.bottom_margin = Mm(30)
    sec.left_margin = sec.right_margin = Mm(20)
    sec.header_distance, sec.footer_distance = Mm(0), Mm(17.5)
    sec.different_first_page_header_footer = False
    cols = sec._sectPr.find(qn('w:cols'))
    cols.set(qn('w:num'), '1')
    for tag in ['docGrid', 'pgNumType']:
        for child in sec._sectPr.findall(qn('w:' + tag)):
            sec._sectPr.remove(child)
    sec._sectPr.append(element('pgNumType', fmt='decimal', start='1'))
    for name in ['Normal', 'Body Text', 'Caption']:
        st = d.styles[name]
        font(st)
        pf = st.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        # Neither line spacing nor paragraph spacing was established by the
        # source description. Leave these unspecified rather than fixing 17pt.
        for tag in ['spacing', 'ind']:
            for child in st.element.get_or_add_pPr().findall(qn('w:' + tag)):
                st.element.pPr.remove(child)
        pf.widow_control = True
    for level, size in [(1, 18), (2, 14), (3, 12)]:
        st = d.styles[f'Heading {level}']
        font(st, size, heading=True)
        st.paragraph_format.keep_with_next = True
        st.paragraph_format.keep_together = True
        st.paragraph_format.page_break_before = level == 1
        st.paragraph_format.space_before = Pt(0 if level == 1 else 8)
        st.paragraph_format.space_after = Pt(6)
        # Explicit positions are provisional, not an inferred university rule.
        st.paragraph_format.left_indent = Mm(0)
        st.paragraph_format.first_line_indent = Mm(0)
    for name in ['Hyperlink', 'FollowedHyperlink']:
        if name in d.styles:
            d.styles[name].font.color.rgb = RGBColor(0, 0, 0)
    defaults = d.styles.element.find(qn('w:docDefaults'))
    for spacing in list(defaults.iter(qn('w:spacing'))):
        spacing.getparent().remove(spacing)
    settings = d.settings.element
    update = settings.find(qn('w:updateFields'))
    if update is None:
        settings.append(element('updateFields', val='true'))
    footer = sec.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    field(footer, 'PAGE', '1')
    for r in footer.runs:
        font(r)
    numbering(d)


def numbering(d):
    root = d.part.numbering_part.element
    abstract = element('abstractNum', abstractNumId='90')
    abstract.append(element('multiLevelType', val='multilevel'))
    for i in range(3):
        lvl = element('lvl', ilvl=i)
        for e in [element('start', val=1), element('numFmt', val='decimal'),
                  element('pStyle', val=f'Heading{i+1}'),
                  element('lvlText', val='.'.join('%' + str(n+1) for n in range(i+1))),
                  element('lvlJc', val='left'), element('suff', val='space')]:
            lvl.append(e)
        pp = element('pPr')
        pp.append(element('ind', left=0, hanging=0))
        lvl.append(pp)
        abstract.append(lvl)
    # Word expects abstractNum definitions before num instances.
    first_num = root.find(qn('w:num'))
    if first_num is not None:
        first_num.addprevious(abstract)
    else:
        root.append(abstract)
    num = element('num', numId='90')
    num.append(element('abstractNumId', val='90'))
    root.append(num)
    for i in range(3):
        pp = d.styles[f'Heading {i+1}'].element.get_or_add_pPr()
        np = element('numPr')
        np.append(element('ilvl', val=i)); np.append(element('numId', val='90'))
        pp.append(np)


def paragraph(d, text, size=10.5, heading=False, center=False, bold=False):
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
    font(p.add_run(text), size, heading, bold)
    return p


def front_title(d, text):
    p = paragraph(d, text, 18, heading=True)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_after = Pt(12)
    return p


def toc(d):
    front_title(d, '目次')
    cache = HERE / 'toc_cache.json'
    entries = json.loads(cache.read_text()) if cache.exists() else []
    # Discard the old thesis layout's cache on the first template build.
    if entries and 'level' not in entries[0]:
        entries = []
    p = d.add_paragraph()
    p.add_run()._r.append(element('fldChar', fldCharType='begin'))
    i = element('instrText'); i.text = ' TOC \\o "1-3" \\h \\z \\u '
    p.add_run()._r.append(i)
    p.add_run()._r.append(element('fldChar', fldCharType='separate'))
    for index, entry in enumerate(entries):
        p = p if index == 0 else d.add_paragraph()
        p.paragraph_format.left_indent = Mm((entry['level'] - 1) * 4)
        p.paragraph_format.tab_stops.add_tab_stop(Mm(169), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        font(p.add_run(f"{entry['number']} {entry['title']}\t{entry['page']}"), 9)
    if not entries:
        font(p.add_run('目次はPDF生成後に更新します。'), 9)
    p.add_run()._r.append(element('fldChar', fldCharType='end'))


def remap(text):
    mappings = {'表3.1': '表1', '表5.1': '表2'}
    mappings.update({f'表6.{i}': f'表{i+2}' for i in range(1, 11)})
    for old, new in sorted(mappings.items(), key=lambda item: -len(item[0])):
        text = text.replace(old, new)
    text = text.replace('付録A', '付録（8.1節）').replace('付録B', '付録（8.2節）')
    text = text.replace('提出年月，英語の著者表記・所属，', '題目の正式承認，')
    if text.startswith('提出年月と日英の正式表記'):
        text = text.replace('提出年月と日英の正式表記', '原本の書式と題目の正式承認')
    if text.startswith('第2章で関連研究'):
        text = ('第2章で関連研究を整理し，第3章で提案手法として介入条件・評価指標・実装・実験設定を述べる．'
                '第4章で結果，第5章で考察，第6章で結論と今後の課題を述べる．'
                '第7章に参考文献，第8章に出典と指標の付録を置く．'
                '本稿は2026-10-16版の到達経路と2026-10-22固定のB4追加実験 [3] に基づく草稿であり，今回の執筆では追加生成・生成コード実行を行っていない．')
    return text


def build_thesis():
    # Retain the source manuscript, tables and appendices. Existing outputs were
    # backed up in .cache/graduation_template_before before this change.
    content.legacy_thesis()
    old = Document(HERE / 'thesis.docx')
    d = Document(); configure(d)
    # Unknown cover coordinates are an explicitly documented approximation.
    for text, size, before in [
        ('卒　業　論　文', 18, 45), (content.TITLE.replace('における', 'における\n'), 18, 60),
        ('2023TC011 伊藤 悠真', 16, 100), ('指導教員　横山 哲郎', 12, 40),
        ('2027年1月', 12, 35)]:
        p = paragraph(d, text, size, heading=True, center=True)
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.keep_together = True
    d.add_page_break()
    paragraph(d, '南山大学 理工学部 電子情報学科', 12, center=True, bold=True)
    front_title(d, '要約')
    for text in content.JA_SUMMARY.splitlines():
        paragraph(d, text)
    d.add_page_break(); toc(d)
    # Preserve the template's intentional blank page following the TOC.
    d.add_page_break(); d.add_page_break()
    started = False
    old_chapter = 0
    table_index = 0
    headings = []
    counters = [0, 0, 0]
    body = d.element.body
    for child in old.element.body:
        if child.tag == qn('w:sectPr'):
            continue
        if child.tag == qn('w:p'):
            from docx.text.paragraph import Paragraph
            op = Paragraph(child, old)
            title, style = op.text, op.style.name
            if style == 'Heading 1' and title.startswith('第1章'):
                started = True
            if not started:
                continue
            # Remove the old standalone page break paragraphs. Chapter styles
            # now control breaks; supplementary groups remain in one appendix.
            if not title.strip():
                continue
            level = None
            if style == 'Heading 1':
                match = re.match(r'第(\d+)章\s*(.*)', title)
                if match:
                    old_chapter = int(match[1])
                    if old_chapter in [4, 5]:
                        title, level = match[2], 2
                    else:
                        title = {1:'はじめに', 2:'関連研究', 3:'提案手法', 6:'結果', 7:'考察', 8:'おわりに'}[old_chapter]
                        level = 1
                elif title == '参考文献':
                    old_chapter, title, level = 9, '参考文献', 1
                elif title.startswith('付録A'):
                    old_chapter, title, level = 10, '付録', 1
                elif title.startswith('付録B'):
                    old_chapter, title, level = 11, '指標の読み方と提出前確認', 2
            elif style == 'Heading 2':
                title = re.sub(r'^(?:\d+\.\d+|A\.\d+)\s*', '', title)
                level = 3 if old_chapter in [3,4,5,10,11] else 2
            if level:
                if old_chapter == 10 and level == 3 and counters[1] == 0:
                    add_heading(d, '出典と再現性', 2, counters, headings)
                p = add_heading(d, title, level, counters, headings)
                if old_chapter == 11 and level == 2:
                    p.paragraph_format.page_break_before = True
                if old_chapter == 3 and level == 1:
                    add_heading(d, '介入条件と評価指標', 2, counters, headings)
                continue
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.widow_control = True
            # The observed 3.47mm indent is not established as a universal rule;
            # retain no universal first-line indent until the source is present.
            text = remap(title)
            cap = re.match(r'表(\d+)[\s\u3000]+(.*)', text)
            if cap:
                table_index += 1
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.keep_together = True
                font(p.add_run('表'))
                p._p.append(element('bookmarkStart', id=100+table_index, name=f'Table{table_index}'))
                field(p, 'SEQ Table \\* ARABIC', str(table_index))
                p._p.append(element('bookmarkEnd', id=100+table_index))
                font(p.add_run(' ' + cap[2]))
            else:
                # Keep normal citations [n]; link table references to their
                # caption numbers using editable REF fields.
                chunks = re.split(r'(表[1-9]\d*(?!\d))', text)
                for chunk in chunks:
                    if re.fullmatch(r'表[1-9]\d*', chunk):
                        font(p.add_run('表')); field(p, f'REF Table{chunk[1:]} \\h', chunk[1:])
                    else:
                        font(p.add_run(chunk))
            for run in p.runs:
                font(run)
        elif started and child.tag == qn('w:tbl'):
            copy = deepcopy(child)
            body.insert(len(body)-1, copy)
    # Clear legacy direct font/spacing settings in copied tables.
    for table in d.tables:
        for row_index, row in enumerate(table.rows):
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.keep_together = True
                    p.paragraph_format.keep_with_next = row_index < len(table.rows)-1
                    for run in p.runs:
                        font(run)
    d.save(HERE / 'thesis.docx')
    (HERE / 'thesis_headings.json').write_text(json.dumps(headings, ensure_ascii=False, indent=2)+'\n')
    spec = {
        'basis': 'User-transcribed analysis of 卒論テンプレート_ver.1.2_260430.doc',
        'original_received': False,
        'paper': {'width_mm':210,'height_mm':297,'top_mm':30,'bottom_mm':30,'left_mm':20,'right_mm':20,'header_mm':0,'footer_mm':17.5,'columns':1},
        'fonts': FONTS, 'body_pt':10.5, 'heading_pt':[18,14,12],
        'provided_identity': {'student':'2023TC011 伊藤 悠真','supervisor':'横山 哲郎','date':'2027年1月','affiliation':'南山大学 理工学部 電子情報学科'},
        'title_status': 'Fixed research title specified by the user on 2026-10-25; retain across future revisions.',
        'implemented': ['Heading 1–3 linked multilevel numbering','TOC levels 1–3 with cached PDF-matched pages','decimal PAGE field including cover','SEQ captions and REF table references','intentional blank page after TOC','six body chapters followed by references and appendix'],
        'supplemental_settings_not_verified_against_original': [
            'Cover vertical spacing: paragraph-before 45/60/100/40/35pt; visual coordinates unknown.',
            'Normal line/paragraph spacing left unspecified; original style inheritance cannot be recovered.',
            'No universal 3.47mm first-line indent; description did not establish this for all paragraphs.',
            'Heading bold off, left indent 0, keep-with-next; lower-level spacing before 8pt / after 6pt.',
            'TOC cache 9pt single-spaced, 4mm indent per level, right tab 169mm; automatic TOC remains editable.',
            'Table layout retained from previous draft, 160mm width, 10.5pt; captions use provisional sequential numbering.',
            'Blank page follows TOC even if TOC uses multiple pages; no fixed 11-page length imposed.',
            'Appendix subsection 8.2 starts a new page to avoid a lone final subsection on its own page.'
        ],
        'pdf_font_limit': 'MS 明朝, MS Pゴシック and Century unavailable on server; PDF uses substitutes. Word fidelity requires original fonts and original template.',
        'source_snapshot': str(content.SOURCE.relative_to(content.ROOT)),
    }
    (HERE/'format_spec.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2)+'\n')


def add_heading(d, title, level, counters, headings):
    counters[level-1] += 1
    for i in range(level, 3):
        counters[i] = 0
    p = d.add_paragraph(title, style=f'Heading {level}')
    number = '.'.join(str(n) for n in counters[:level])
    headings.append({'number':number, 'title':title, 'level':level})
    return p


def toc_entries():
    import pymupdf
    pdf = pymupdf.open(HERE/'thesis.pdf')
    headings = json.loads((HERE/'thesis_headings.json').read_text())
    norm = lambda s: ''.join(s.split())
    out = []
    # A real heading must have the heading font size. This excludes cached TOC
    # text and body references without relying on the old running header.
    previous = 0
    for h in headings:
        found = []
        expected_size = [18,14,12][h['level']-1]
        for index in range(previous, len(pdf)):
            for block in pdf[index].get_text('dict')['blocks']:
                spans = [sp for line in block.get('lines',[]) for sp in line['spans']]
                if norm(h['title']) in norm(''.join(sp['text'] for sp in spans)) and any(abs(sp['size']-expected_size)<.2 for sp in spans):
                    found.append(index)
            if found:
                break
        if not found:
            raise ValueError(f'Heading missing from PDF: {h}')
        previous = found[0]
        out.append({**h, 'page':str(previous+1)})
    return out


if __name__ == '__main__':
    import sys
    if '--update-toc' in sys.argv:
        entries = toc_entries()
        (HERE/'toc_cache.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2)+'\n')
    build_thesis()
