"""Validate the transcribed-template thesis without claiming original fidelity."""
from datetime import datetime, timezone
import hashlib
import json
import re

from docx import Document
from docx.oxml.ns import qn
import pymupdf
import template_thesis as template

HERE = template.HERE


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate():
    d = Document(HERE/'thesis.docx')
    pdf = pymupdf.open(HERE/'thesis.pdf')
    checks = {}
    near = lambda a,b: abs(a-b)<.08
    checks['a4_portrait_and_requested_margins'] = all(
        all(near(actual,expected) for actual,expected in [(s.page_width.mm,210),(s.page_height.mm,297),
        (s.top_margin.mm,30),(s.bottom_margin.mm,30),(s.left_margin.mm,20),(s.right_margin.mm,20),
        (s.header_distance.mm,0),(s.footer_distance.mm,17.5)]) for s in d.sections)
    checks['single_column'] = all(s._sectPr.find(qn('w:cols')).get(qn('w:num'),'1')=='1' for s in d.sections)
    checks['empty_header'] = all(not any(p.text.strip() for p in s.header.paragraphs) for s in d.sections)
    checks['page_field_right_aligned_including_cover'] = all(
        not s.different_first_page_header_footer and s.footer.paragraphs[0].alignment==2 and
        any(e.text.strip()=='PAGE' for e in s.footer._element.iter(qn('w:instrText'))) for s in d.sections)
    for style,size,jp,latin in [('Normal',10.5,'MS 明朝','Century'),('Heading 1',18,'MS Pゴシック','Arial'),('Heading 2',14,'MS Pゴシック','Arial'),('Heading 3',12,'MS Pゴシック','Arial')]:
        st=d.styles[style];rf=st.element.rPr.rFonts
        checks[style+'_font'] = near(st.font.size.pt,size) and rf.get(qn('w:eastAsia'))==jp and rf.get(qn('w:ascii'))==latin
    checks['normal_spacing_not_fixed'] = d.styles['Normal'].element.pPr.find(qn('w:spacing')) is None
    checks['heading_multilevel_numbering'] = all(d.styles[f'Heading {i}'].element.pPr.find(qn('w:numPr')).find(qn('w:numId')).get(qn('w:val'))=='90' for i in range(1,4))
    definitions=next(e for e in d.part.numbering_part.element if e.tag==qn('w:abstractNum') and e.get(qn('w:abstractNumId'))=='90')
    checks['number_patterns'] = [e.find(qn('w:lvlText')).get(qn('w:val')) for e in definitions if e.tag==qn('w:lvl')]==['%1','%1.%2','%1.%2.%3']
    headings=[p for p in d.paragraphs if p.style.name.startswith('Heading ')]
    checks['heading_numbers_not_typed'] = all(not re.match(r'^(?:第\d|\d+\.|付録[A-Z])',p.text) for p in headings)
    checks['chapter_order'] = [p.text for p in headings if p.style.name=='Heading 1']==['はじめに','関連研究','提案手法','結果','考察','おわりに','参考文献','付録']
    checks['heading_keep_with_next'] = all(d.styles[f'Heading {i}'].paragraph_format.keep_with_next for i in range(1,4))
    checks['chapter_page_breaks'] = d.styles['Heading 1'].paragraph_format.page_break_before
    instructions=[e.text.strip() for e in d.element.iter(qn('w:instrText'))]
    checks['editable_toc_levels_1_to_3'] = any('TOC' in i and '"1-3"' in i for i in instructions)
    cache=json.loads((HERE/'toc_cache.json').read_text())
    checks['all_51_toc_entries_match_pdf']=len(cache)==51 and cache==template.toc_entries()
    checks['toc_dot_leaders_and_right_tabs']=all(
        p.paragraph_format.tab_stops[0].alignment==2 and p.paragraph_format.tab_stops[0].leader==1
        for p in d.paragraphs if '\t' in p.text)
    checks['nine_sequential_table_fields']=sum(i.startswith('SEQ Table ') for i in instructions)==9
    checks['editable_table_references']=any(i.startswith('REF Table') for i in instructions)
    checks['table_widths_within_170mm']=all(sum(c.width.mm for c in t.columns)<=170.1 for t in d.tables)
    checks['table_headers_repeat']=all(t.rows[0]._tr.get_or_add_trPr().find(qn('w:tblHeader')) is not None for t in d.tables)
    caption_ps=[p for p in d.paragraphs if any('SEQ Table' in e.text for e in p._p.iter(qn('w:instrText')))]
    checks['captions_before_table_and_kept_with_next']=all(p._p.getnext().tag==qn('w:tbl') and p.paragraph_format.keep_with_next for p in caption_ps)
    tables=[[[c.text for c in row.cells] for row in t.rows] for t in d.tables]
    checks['model_table_matches_frozen_csv']=tables[3][1:]==[[str(c) for c in row] for row in template.content.model_rows(True)]
    checks['failure_table_matches_frozen_csv']=tables[4][1:]==[[str(c) for c in row] for row in template.content.error_rows()]
    norm=lambda text:''.join(text.split())
    texts=[p.get_text() for p in pdf]
    checks['cover_identity_date']=all(norm(value) in norm(texts[0]) for value in ['卒業論文',template.content.TITLE,'2023TC011 伊藤 悠真','横山 哲郎','2027年1月'])
    checks['summary_second_page']=all(norm(value) in norm(texts[1]) for value in ['南山大学 理工学部 電子情報学科','要約','545','183','180'])
    checks['toc_third_page']='目次' in texts[2]
    checks['only_intentional_blank_page_4']=[i for i,text in enumerate(texts,1) if len(norm(re.sub(r'\d+\s*$','',text)))<5]==[4]
    checks['continuous_visible_decimal_pages']=all(text.rstrip().splitlines()[-1]==str(i) for i,text in enumerate(texts,1))
    checks['pdf_a4']=all(abs(p.rect.width-595.28)<.6 and abs(p.rect.height-841.89)<.6 for p in pdf)
    outside=[];margin=[]
    for i,p in enumerate(pdf,1):
        for b in p.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                for sp in line['spans']:
                    if not sp['text'].strip():continue
                    r=pymupdf.Rect(sp['bbox'])
                    if r.x0<-.5 or r.y0<-.5 or r.x1>p.rect.width+.5 or r.y1>p.rect.height+.5:outside.append(i)
                    if r.x0<56 or r.x1>539.5:margin.append({'page':i,'text':sp['text']})
    checks['no_text_outside_page']=not outside
    checks['text_within_left_right_margins']=not margin
    xrefs={f[0] for p in pdf for f in p.get_fonts()}
    checks['pdf_fonts_embedded']=all(bool(pdf.extract_font(x)[3]) for x in xrefs)
    checks['no_replacement_characters']=all('\ufffd' not in t for t in texts)
    checks['no_field_errors']=not any(s in '\n'.join(texts) for s in ['Error!','エラー!','参照元が見つかりません','目次はPDF'])
    checks['under_10mb']=(HERE/'thesis.pdf').stat().st_size<10_000_000
    manifest=json.loads((HERE/'source_manifest.json').read_text())
    checks['frozen_source_hashes_unchanged']=all(digest(template.content.ROOT/p)==sha for p,sha in manifest['source_hashes'].items())
    alltext='\n'.join(p.text for p in d.paragraphs)
    refs=set(re.findall(r'\[(\d+)\]',alltext))
    checks['reference_numbers_consistent']=refs=={'1','2','3'}
    visual_file=HERE/'thesis_visual_review.json'
    visual=json.loads(visual_file.read_text()) if visual_file.exists() else {'status':'pending'}
    visual_current=visual.get('pdf_sha256')==digest(HERE/'thesis.pdf') and visual.get('pages_reviewed')==list(range(1,len(pdf)+1))
    result={
        'checked_at_utc':datetime.now(timezone.utc).isoformat(), 'scope':'thesis.docx and thesis.pdf only; separate abstract and slides retained',
        'automated_checks_passed':all(checks.values()),'checks':checks,
        'documents':{'thesis':{'pages':len(pdf),'pdf_bytes':(HERE/'thesis.pdf').stat().st_size,'pdf_sha256':digest(HERE/'thesis.pdf')}},
        'visual_review':visual if visual_current else {'status':'pending_or_stale'},
        'original_template_comparison':'not performed; original .doc not accessible',
        'font_fidelity':'DOCX specifies requested fonts; LibreOffice PDF uses substitutes. Final Microsoft Word rendering unverified.',
        'format_spec':'format_spec.json', 'source_snapshot_at_utc':manifest['source_snapshot_at_utc'],
        'new_experiments':0, 'new_model_requests':0,'generated_code_executions':0,
        'artifact_sha256':{p.name:digest(p) for p in HERE.iterdir() if p.is_file() and p.name not in ['validation_report.json']},
        'out_of_margin_spans':margin,
        'pending':['Original template comparison, especially cover coordinates and inherited paragraph styles','Formal approval of thesis title','Final rendering and updated fields in Microsoft Word with the specified fonts','Supervisor review of content and references']}
    (HERE/'validation_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':all(checks.values()),'failed':[k for k,v in checks.items() if not v],'pages':len(pdf),'visual_review_current':visual_current},ensure_ascii=False))
    if not all(checks.values()):raise SystemExit(1)


if __name__=='__main__':validate()
