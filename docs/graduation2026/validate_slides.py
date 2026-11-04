"""Verify slide values, rendered text, references and source provenance."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from pptx import Presentation
import pymupdf

from graduation_slides import HERE, ROOT, TITLE, FIXED, B4
from six_conditions import values


def validate():
    pptx = Presentation(HERE / 'slides.pptx')
    pdf = pymupdf.open(HERE / 'slides.pdf')
    thesis = pymupdf.open(HERE / 'thesis.pdf')
    manifest = json.loads((HERE / 'slides_source_manifest_20261104.json').read_text())
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    norm = lambda t: re.sub(r'\s+', '', t)
    slide_text = lambda n: '\n'.join(s.text for s in pptx.slides[n-1].shapes if s.has_text_frame)
    def at(n, x, y):
        matches=[s.text for s in pptx.slides[n-1].shapes if s.has_text_frame
                 and abs(s.left/914400-x)<.01 and abs(s.top/914400-y)<.01]
        if len(matches)!=1:
            raise ValueError((n,x,y,matches))
        return matches[0]
    summary = list(csv.DictReader((B4/'summary.csv').open()))
    def row(c, grouping='overall', group='all'):
        return next(r for r in summary if r['condition']==c and r['generation_cap']=='4'
                    and r['grouping']==grouping and r['group']==group)
    checks = {
        'twelve_slides_in_pptx_and_pdf':len(pptx.slides)==len(pdf)==12,
        'eight_main_slides_360_seconds':manifest['main_slides']==8 and manifest['supplemental_slides']==4
            and sum(n['seconds'] or 0 for n in manifest['notes'])==360,
        'fixed_title_matches_thesis':norm(TITLE) in norm(slide_text(1)) and norm(TITLE) in norm(thesis[0].get_text()),
        'source_files_and_latest_thesis_match_manifest':all(digest(ROOT/p)==h for p,h in manifest['source_sha256'].items()),
        'all_shapes_text_rendered_in_pdf':all(norm(s.text) in norm(pdf[i].get_text())
            for i,slide in enumerate(pptx.slides) for s in slide.shapes if s.has_text_frame),
        'all_notes_match_manifest':all(pptx.slides[i].notes_slide.notes_text_frame.text==n['text']
            for i,n in enumerate(manifest['notes'])),
        'speaker_notes_match_manifest':all(n['text'] in (HERE/'speaker_notes.txt').read_text() for n in manifest['notes']),
        'all_slide_numbers_visible':all(re.search(rf'(?m)^\s*{i+1}\s*$',p.get_text()) for i,p in enumerate(pdf)),
    }
    checks['six_final_success_rates_match_fixed_csv']=all(
        at(4,4.2,2.35+i*.53)==f"{r['successes']}組 {r['rate_percent']:.1f}%"
        and at(4,.85,2.35+i*.53)==r['condition'] for i,r in enumerate(values()))
    checks['additional_success_rates_match_fixed_csv']=all(
        at(4,8,2.4+i*.76)==f"{row(c)['successes_from_initial_failure']}組  {100*float(row(c)['success_from_initial_failure_rate']):.1f}%"
        for i,c in enumerate(('R','F','D','B4')))
    catalog=list(csv.DictReader((HERE/'intervention_catalog.csv').open()))
    checks['all_catalog_cells_match_fixed_csv']=all(at(6,x,3.05+i*.85)==v
        for i,r in enumerate(catalog) for x,v in zip([.85,4.15,5.7,7.7,9.7],
            [r['label'],r['initial_failures'],*(r[c+'_rate_percent']+'%' for c in ('F','D','B4'))]))
    checks['all_cost_cells_match_fixed_csv']=all(
        at(7,2,2.95+i*.67)==f"{int(row(c)['additional_tokens']):,}"
        and at(7,4.8,2.95+i*.67)==f"{float(row(c)['tokens_per_added_success']):,.1f}"
        for i,c in enumerate(('R','F','D','B4')))
    third=next(r for r in csv.DictReader((B4/'third_round_summary.csv').open()) if r['scope']=='pooled' and r['grouping']=='overall' and r['condition_id']=='self_debugging')
    checks['third_round_D_count_matches_corrected_csv']=f"D：{third['additional_rescues']}組" in slide_text(7)
    models=['qwen3.5:4b','gemma4:e4b-it-qat','qwen3.5:9b','qwen2.5-coder:7b','gemma3:4b']
    checks['all_model_success_cells_match_fixed_csv']=all(
        at(9,x,2.9+i*.52)==row(c,'model','ollama:'+model)['successes_from_initial_failure']
        for i,model in enumerate(models) for x,c in zip([5.6,7,8.4,10],['R','F','D','B4']))
    checks['B4_method_and_scope_present']='前回コード・診断なし' in slide_text(3) and 'B4：追加1,000組' in slide_text(3)
    checks['catalog_policy_unverified_explicit']='性能改善は未検証' in slide_text(6) and '有効性は未検証' in slide_text(8)
    checks['reference_numbers_1_to_9_present']=all(f'[{i}]' in slide_text(11)+slide_text(12) for i in range(1,10))
    links={l['uri'] for p in pdf for l in p.get_links() if l.get('uri')}
    checks['all_eleven_source_links_in_pdf']=links=={
        'https://arxiv.org/abs/2303.17651v2','https://arxiv.org/abs/2304.05128v2',
        'https://arxiv.org/abs/2107.03374v2','https://arxiv.org/abs/2108.07732',
        'https://arxiv.org/abs/2310.01798v2','https://arxiv.org/abs/2406.14712',
        'https://quantum.cloud.ibm.com/docs/en/guides/construct-circuits',
        'https://qiskit.github.io/qiskit-aer/', FIXED,
        FIXED+'/docs/analysis/measurement_ban_corrected_20261104',
        FIXED+'/docs/analysis/measurement_ban_corrected_20261104'}
    overflow=[]
    for i,p in enumerate(pdf,1):
        for b in p.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                for span in line['spans']:
                    x0,y0,x1,y1=span['bbox']
                    if x0<0 or y0<0 or x1>p.rect.width or y1>p.rect.height:
                        overflow.append({'slide':i,'text':span['text']})
    checks['no_rendered_text_outside_page']=not overflow
    checks['fonts_embedded']=all(pdf.extract_font(f[0])[3] for p in pdf for f in p.get_fonts())
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'passed':all(checks.values()),'checks':checks,
            'overflow':overflow,'pdf_links':sorted(links),'artifact_sha256':{n:digest(HERE/n) for n in
            ['thesis.pdf','slides.pptx','slides.pdf','speaker_notes.txt','graduation_slides.py','convert_slides.py','validate_slides.py']},
            'scope':'最新卒論PDFを出典にしたスライドの値・注記・PDF収録・リンク・境界・ノートの照合。独立査読と実際の発表時間の検証ではない。',
            'new_model_requests':0,'generated_code_executions':0}
    (HERE/'slides_validation_20261104.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':validate()
