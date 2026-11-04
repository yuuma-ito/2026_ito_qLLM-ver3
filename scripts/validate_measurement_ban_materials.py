"""Check current exported materials against the corrected fixed evidence; no scoring."""
from pathlib import Path
import csv,hashlib,json,re,sys,zipfile
from datetime import datetime,timezone
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.cache/graduation_tools'))
import pymupdf
from pptx import Presentation
DATA=ROOT/'docs/analysis/measurement_ban_corrected_20261104'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(t):return re.sub(r'\s+','',t).replace('\u00ad','').replace('ﬁ','fi').replace('ﬂ','fl')
def validate():
    manifest=json.loads((DATA/'manifest.json').read_text());snap=json.loads((DATA/'results_snapshot.json').read_text())
    checks={'corrected_fixed_outputs_unchanged':all(digest(DATA/p)==h for p,h in manifest['outputs'].items()),'historical_inputs_and_checkpoints_unchanged':all(digest(ROOT/p)==h for p,h in manifest['inputs'].items()),'pending_paths_zero':snap['pending_paths']==0,'followup_exactly_one_request_408_tokens':snap['followup']['new_requests']==1 and snap['followup']['new_tokens']==408}
    files={'docs/graduation2026/thesis.pdf':35,'docs/graduation2026/abstract.pdf':2,'docs/midterm2026/paper.pdf':2,'docs/winf2026/paper.pdf':2,'docs/graduation2026/slides.pdf':12,'docs/midterm2026/slides/slides.pdf':11,'docs/winf2026/slides/slides.pdf':17,'docs/course_reports2026/卒業研究_調査設計報告.pdf':17,'docs/course_reports2026/卒業研究_進捗成果報告.pdf':14,'docs/course_reports2026/slides/調査設計報告_スライド.pdf':10,'docs/course_reports2026/slides/進捗成果報告_スライド.pdf':10}
    texts={};pdfs={}
    for name,pages in files.items():
        d=pymupdf.open(ROOT/name);text=norm(''.join(p.get_text() for p in d));texts[name]=text
        passed=len(d)==pages and norm('量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究') in text and '\ufffd' not in text
        checks[name]=passed;pdfs[name]={'pages':len(d),'sha256':digest(ROOT/name),'title_and_no_replacement_glyph':passed}
    for name in ['docs/graduation2026/thesis.pdf','docs/course_reports2026/卒業研究_進捗成果報告.pdf']:
        checks[name+'_corrected_results']=all(x in texts[name] for x in ['634','671','179','216','139','44','996,223','4,612.1','408','厳格評価'])
    checks['WiNF_wrong_output_D_prose_matches_corrected_count']='D17/65組' in texts['docs/winf2026/paper.pdf']
    summary=list(csv.DictReader((DATA/'summary.csv').open()))
    overall={r['condition']:r for r in summary if r['grouping']=='overall' and r['generation_cap']=='4'}
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(ROOT/'docs/graduation2026/thesis.docx') as z:doc=ET.fromstring(z.read('word/document.xml'))
    tables=[[[''.join(x.text or '' for x in c.findall('.//w:t',ns)) for c in rr.findall('w:tc',ns)] for rr in t.findall('w:tr',ns)] for t in doc.findall('.//w:tbl',ns)]
    headline=next(t for t in tables if t[0]==['条件','初期失敗数','追加成功数','追加成功率'])
    checks['Word_added_success_table_matches_corrected_csv']=headline[1:]==[[c,'545',overall[c]['successes_from_initial_failure'],f"{100*float(overall[c]['success_from_initial_failure_rate']):.1f}%"] for c in ['R','F','D','B4']]
    for path in [ROOT/'docs/graduation2026/slides.pptx',ROOT/'docs/winf2026/slides/slides.pptx',*list((ROOT/'docs/course_reports2026/slides').glob('*.pptx'))]:
        prs=Presentation(path);text='\n'.join((s.text if s.has_text_frame else '') for slide in prs.slides for s in slide.shapes)+'\n'+'\n'.join(s.notes_slide.notes_text_frame.text for s in prs.slides)
        checks[str(path.relative_to(ROOT))+'_no_stale_correlated_counts']=not re.search(r'D[ ：:はが]*180組|B4[ ：:はが]*217組|D[ ：:はがの]*33組|共通[救済は ：:]*140|Fのみ[ ：:]*43|片側救済83組',text)
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'passed':all(checks.values()),'checks':checks,'pdfs':pdfs,'evaluator_version':manifest['evaluator_version'],'scope':'固定出典hash・旧入力不変・出力PDF題目/ページ/修正版数値・Word主要表・スライド本文/ノートの旧数値を照合。独立した章査読は別記録。','new_model_requests_in_validation':0,'generated_code_executions_in_validation':0,'limits':['API側消費の独立検証なし','指定MSフォント不足のため卒論・要旨PDFは代替フォント確認版','発表時間の実測なし']}
    out=ROOT/'docs/analysis/measurement_ban_materials_validation_20261104.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False));return report

if __name__=='__main__':raise SystemExit(0 if validate()['passed'] else 1)
