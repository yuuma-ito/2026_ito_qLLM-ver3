"""Validate only the two course reports and prove original artifacts unchanged."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'.cache/graduation_tools'))
from docx import Document
from docx.oxml.ns import qn
import pymupdf

HERE=Path(__file__).resolve().parent
OUT=HERE.parent
TITLE='量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究'


def norm(value):
    return re.sub(r'\s+','',value).replace('\u00ad','').replace('ﬁ','fi').replace('ﬂ','fl')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def validate():
    source=Document(HERE/'thesis_source.docx')
    manifest=json.loads((OUT/'source_manifest.json').read_text())
    checks={'original_files_unchanged':all(digest(ROOT/p)==h for p,h in manifest['source_files'].items()),
            'copied_source_matches_original':digest(HERE/'thesis_source.docx')==manifest['source_files']['docs/graduation2026/thesis.docx'],
            'exactly_two_requested_PDFs':{p.name for p in OUT.rglob('*.pdf')}=={'卒業研究_調査設計報告.pdf','卒業研究_進捗成果報告.pdf'}}
    reports={}
    source_tables=[[[c.text for c in r.cells] for r in t.rows] for t in source.tables]
    for kind in ['design','progress']:
        build=json.loads((HERE/(kind+'_build_record.json')).read_text())
        stem=build['stem']
        doc=Document(HERE/(stem+'.docx'))
        pdf=pymupdf.open(OUT/(stem+'.pdf'))
        text='\n'.join('\n'.join(p.get_text().splitlines()[:-1]) for p in pdf)
        text_norm=norm(text)
        paragraphs=[p.text for p in doc.paragraphs]
        missing=[r['report_text'] for r in build['reused'] if r['report_text'] and norm(r['report_text']) not in text_norm]
        additions_missing=[s for s in build['additional_paragraphs'] if norm(s) not in text_norm]
        figures=[]
        for shape in doc.inline_shapes:
            rid=shape._inline.xpath('.//a:blip')[0].get(qn('r:embed'))
            figures.append(hashlib.sha256(doc.part.related_parts[rid].blob).hexdigest())
        original_figures=[]
        for old_number in build['figure_mapping']:
            shape=source.inline_shapes[int(old_number)-1]
            rid=shape._inline.xpath('.//a:blip')[0].get(qn('r:embed'))
            original_figures.append(hashlib.sha256(source.part.related_parts[rid].blob).hexdigest())
        table_values=[[[c.text for c in r.cells] for r in t.rows] for t in doc.tables]
        expected_tables=source_tables[:2] if kind=='design' else source_tables[2:]
        captions={'表':[],'図':[]}
        for p in paragraphs:
            match=re.match(r'^(表|図)(\d+)\s',p)
            if match:captions[match[1]].append(int(match[2]))
        toc=json.loads((HERE/(kind+'_toc.json')).read_text())
        toc_text=re.sub(r'[.·…]','',norm(pdf[1].get_text()))
        refs=[p for p in paragraphs if re.match(r'^\[\d+\]',p)]
        ref_ids={int(re.match(r'^\[(\d+)\]',p)[1]) for p in refs}
        body_text='\n'.join(paragraphs[:next(i for i,p in enumerate(paragraphs) if re.match(r'^5 参考文献$',p))])
        cited={int(n) for n in re.findall(r'\[(\d+)\]',body_text)}
        overflow=[]
        for i,page in enumerate(pdf,1):
            for block in page.get_text('dict')['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        x0,y0,x1,y1=span['bbox']
                        if x0<-.5 or y0<-.5 or x1>page.rect.width+.5 or y1>page.rect.height+.5:
                            overflow.append({'page':i,'text':span['text'],'bbox':list(span['bbox'])})
        pdf_links={l['uri'] for page in pdf for l in page.get_links() if l.get('uri')}
        word_links={r.target_ref for r in doc.part.rels.values() if r.is_external and r.reltype.endswith('/hyperlink')}
        # Unused relationships from the copied source remain in the package;
        # only relationships actually used by retained paragraphs matter.
        used_links={doc.part.rels[n.get(qn('r:id'))].target_ref for n in doc.element.body.iter(qn('w:hyperlink')) if n.get(qn('r:id'))}
        rc={
            'independent_cover_identity':all(norm(s) in norm(pdf[0].get_text()) for s in [TITLE,build['report_type'],'南山大学','電子情報学科','2023TC011','伊藤悠真']),
            'all_selected_source_paragraphs_in_pdf':not missing,
            'all_additions_in_pdf':not additions_missing,
            'all_non_TOC_paragraphs_in_pdf':all(norm(s) in text_norm for s in paragraphs if '\t' not in s),
            'all_source_tables_unchanged':table_values==expected_tables,
            'all_source_figures_unchanged':figures==original_figures,
            'all_table_rows_in_pdf':all(norm(''.join(r)) in text_norm for t in table_values for r in t),
            'sequential_table_and_figure_numbers':captions['表']==list(range(1,len(doc.tables)+1)) and captions['図']==list(range(1,len(figures)+1)),
            'all_table_and_figure_references_defined':all(int(n) in captions[k] for k,n in re.findall(r'(表|図)(\d+)',body_text)),
            'all_numeric_section_references_defined':all(n in {h['number'] for h in build['headings']} for n in re.findall(r'(?<!\d)(\d+\.\d+)節',body_text)),
            'no_dangling_appendix_references':'付録' not in body_text,
            'citations_match_reference_list':cited==ref_ids,
            'PDF_links_match_used_Word_links':pdf_links==used_links,
            'no_broken_field_errors':all(s not in text for s in ['Error!','エラー!','参照元が見つかりません']),
            'no_stale_REF_or_SEQ_fields':not list(doc.element.body.iter(qn('w:instrText'))),
            'toc_matches_PDF_pages':all(norm(h['text']) in norm(pdf[h['page']-1].get_text()) and re.sub(r'[.·…]','',norm(h['text']+str(h['page']))) in toc_text for h in toc),
            'page_numbers_sequential':all(p.get_text().strip().splitlines()[-1]==str(i) for i,p in enumerate(pdf,1)),
            'no_blank_pages':all(len(norm(p.get_text()))>20 for p in pdf),
            'no_text_outside_page':not overflow,
            'all_PDF_fonts_embedded':all(pdf.extract_font(font[0])[3] for p in pdf for font in p.get_fonts()),
        }
        if kind=='design':
            rc['all_RQs_and_evaluation_axes_present']=all(s in text_norm for s in ['RQ1','RQ2','RQ3','追加成功率','成功対象の重なり','モデル別・初期失敗類型別','追加計算コスト'])
            rc['completed_experiments_not_presented_as_unperformed']='既に実施した実験へ適用した' in text_norm
        else:
            results_page=next(h['page'] for h in toc if h['number']=='2')
            overview_page=next(h['page'] for h in toc if h['number']=='1')
            rc['overview_is_one_page']=results_page-overview_page==1
            rc['key_results_and_limits_preserved']=all(s in text_norm for s in ['455','473','551','638','635','672','96','183','180','217','140','43','40','995,815','4,589.0','介入カタログ','未検証','全入力','seed規則'])
            rc['implementation_and_submission_plan_present']=all(s in text_norm for s in ['評価ハーネスを開発','再採点','部分追試293','静的履歴分析','本文を推敲','固定集計・参考文献・図表','指導教員の指摘'])
        checks[kind]=all(rc.values())
        reports[kind]={'pdf':stem+'.pdf','pages':len(pdf),'source_chapters':build['source_chapters'],
            'source_pdf_pages':[5,17] if kind=='design' else [18,27],
            'tables':len(doc.tables),'data_rows':sum(len(t)-1 for t in table_values),'figures':len(figures),
            'references':len(refs),'PDF_links':len(pdf_links),'reused_paragraphs':sum(bool(r['report_text']) for r in build['reused']),
            'additional_paragraphs':len(build['additional_paragraphs']),'checks':rc,'missing_paragraphs':missing,'missing_additions':additions_missing,
            'overflow':overflow,'pdf_sha256':digest(OUT/(stem+'.pdf')),'docx_sha256':digest(HERE/(stem+'.docx'))}
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'passed':all(checks.values()),'checks':checks,'reports':reports,
        'new_experiments':0,'new_model_requests':0,'rescoring':False,'original_artifacts_modified':False,
        'scope':'章単位の再利用，参照・図表・主要数値・PDF収録・体裁の検証。原論文の再照合と原稿全体の独立査読は行わない。'}
    (OUT/'validation_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':result['passed'],'checks':checks,'failed':{k:[n for n,v in r['checks'].items() if not v] for k,r in reports.items()}},ensure_ascii=False))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':validate()
