"""Read-only portable checks; never substitutes for Microsoft Office rendering."""
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import pymupdf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TITLE = '量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究'
N = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run():
    checks = {}
    pdfs = {}
    names = ['thesis.pdf','abstract.pdf','slides.pdf']
    for name, count in zip(names,[40,2,12]):
        path=ROOT/'docs/graduation2026'/name
        d=pymupdf.open(path)
        outside=[]
        for i,p in enumerate(d,1):
            for block in p.get_text('rawdict')['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        for char in span['chars']:
                            x0,y0,x1,y1=char['bbox']
                            if x0<-.5 or y0<-.5 or x1>p.rect.width+.5 or y1>p.rect.height+.5:
                                outside.append({'page':i,'character':char['c']})
        xrefs={font[0] for p in d for font in p.get_fonts()}
        size_ok=all(abs(p.rect.width-595.28)<.6 and abs(p.rect.height-841.89)<.6 for p in d) if name!='slides.pdf' else all(abs(p.rect.width/p.rect.height-16/9)<.001 for p in d)
        checks[name+'_page_count']=len(d)==count
        checks[name+'_paper_size']=size_ok
        checks[name+'_fonts_embedded']=all(bool(d.extract_font(x)[3]) for x in xrefs)
        checks[name+'_no_characters_outside_page']=not outside
        checks[name+'_title_present']=re.sub(r'\s+','',TITLE) in re.sub(r'\s+','',d[0].get_text())
        pdfs[name]={'pages':len(d),'bytes':path.stat().st_size,'sha256':sha(path),'fonts':sorted({f[3] for p in d for f in p.get_fonts()}),'outside_page':outside}
    checks['thesis_under_local_10MB_target']=(ROOT/'docs/graduation2026/thesis.pdf').stat().st_size<10_000_000
    checks['thesis_under_official_100MB_limit']=(ROOT/'docs/graduation2026/thesis.pdf').stat().st_size<100_000_000
    checks['abstract_mirrors_identical']=all((ROOT/'docs/midterm2026'/a).read_bytes()==(ROOT/'docs/graduation2026'/b).read_bytes() for a,b in [('paper.docx','abstract.docx'),('paper.pdf','abstract.pdf')])
    word={}
    for name in ['thesis.docx','abstract.docx']:
        path=ROOT/'docs/graduation2026'/name
        with ZipFile(path) as z:
            checks[name+'_zip_integrity']=z.testzip() is None
            body=ET.fromstring(z.read('word/document.xml'))
            style=ET.fromstring(z.read('word/styles.xml'))
        normal=style.find("w:style[@w:styleId='Normal']",N)
        fonts=normal.find('w:rPr/w:rFonts',N)
        pt=normal.find('w:rPr/w:sz',N)
        sections=[]
        for sec in body.findall('.//w:sectPr',N):
            item={}
            for tag in ['pgSz','pgMar','cols']:
                el=sec.find('w:'+tag,N)
                item[tag]={k.rsplit('}',1)[-1]:v for k,v in el.attrib.items()} if el is not None else {}
            sections.append(item)
        word[name]={'normal_fonts':{k.rsplit('}',1)[-1]:v for k,v in fonts.attrib.items()},'normal_half_points':pt.get('{'+N['w']+'}val'),'sections':sections}
        checks[name+'_requested_body_fonts_declared']=fonts.get('{'+N['w']+'}eastAsia')=='ＭＳ Ｐ明朝' and fonts.get('{'+N['w']+'}ascii')=='Times New Roman'
        checks[name+'_body_11pt']=pt.get('{'+N['w']+'}val')=='22'
    path=ROOT/'docs/graduation2026/slides.pptx'
    with ZipFile(path) as z:
        checks['pptx_zip_integrity']=z.testzip() is None
        slide_files=[x for x in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',x)]
        checks['pptx_has_12_slides']=len(slide_files)==12
    commands={cmd:shutil.which(cmd) for cmd in ['winword','WINWORD.EXE','powerpnt','POWERPNT.EXE','wine','powershell','pwsh']}
    fc=subprocess.run(['fc-list',':','family'],capture_output=True,text=True)
    families=fc.stdout.lower()
    font_installed={
        'MS PMincho':bool(re.search(r'ms pmincho|ｍｓ ｐ明朝',families)),
        'MS PGothic':bool(re.search(r'ms pgothic|ｍｓ ｐゴシック',families)),
        'Times New Roman':'times new roman' in families,
    }
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'portable_checks_passed':all(checks.values()),'checks':checks,'pdfs':pdfs,'word':word,
            'local_office_commands':commands,'requested_fonts_installed':font_installed,
            'microsoft_office_rendering':'NOT_PERFORMED: this portable script does not render documents in Microsoft Office or query connected sessions; see office_sessions.json for the separately observed connection state.',
            'formal_department_rules':'UNVERIFIED: user states the current instructions are WebClass-only; no authenticated course session or original template supplied.',
            'department_format_basis':'User-specified repository settings are checked separately; they are not certification against the formal template.',
            'limits':['Portable PDF and XML checks do not establish correct rendering in Microsoft Word or PowerPoint.','Formal department submission readiness is not certified.','No manuscripts, Office documents or PDFs are modified by this script.']}
    (HERE/'submission_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'portable_checks_passed':report['portable_checks_passed'],'failed':[k for k,v in checks.items() if not v]},ensure_ascii=False))


if __name__=='__main__':
    run()
