"""Split a copied thesis into two course reports; never build or modify the thesis."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.cache/graduation_tools'))
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.text.paragraph import Paragraph
import pymupdf

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
TITLE = '量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究'
KINDS = {
    'design': ('卒業研究_調査設計報告', '卒業研究に関する調査・設計報告', {1,2,3}),
    'progress': ('卒業研究_進捗成果報告', '卒業研究の進捗・成果報告', {4,5,6}),
}


def para(element, doc):
    return Paragraph(element, doc) if element.tag == qn('w:p') else None


def replace_text(element, pattern, replacement):
    """Replace across Word runs, keeping other fonts, pictures and hyperlinks."""
    nodes = list(element.iter(qn('w:t')))
    text = ''.join(n.text or '' for n in nodes)
    bounds = []
    position = 0
    for n in nodes:
        bounds.append((position, position + len(n.text or ''), n))
        position += len(n.text or '')
    for match in reversed(list(re.finditer(pattern, text))):
        value = replacement(match) if callable(replacement) else replacement
        touched = [(a,b,n) for a,b,n in bounds if a < match.end() and b > match.start()]
        if not touched:
            continue
        a,_,first = touched[0]
        la,_,last = touched[-1]
        prefix = (first.text or '')[:match.start()-a]
        suffix = (last.text or '')[match.end()-la:]
        first.text = prefix + value + (suffix if first is last else '')
        for _,_,n in touched[1:]:
            n.text = ''
        if first is not last:
            last.text = suffix
        for _,_,n in touched:
            n.set(qn('xml:space'), 'preserve')


def plain_cached_fields(element):
    # Freeze already rendered REF/SEQ results, so later Word opening cannot
    # reintroduce the thesis's numbering or references to removed bookmarks.
    for tag in ('instrText', 'fldChar', 'bookmarkStart', 'bookmarkEnd'):
        for node in list(element.iter(qn('w:' + tag))):
            node.getparent().remove(node)


def add_text(doc, value, style=None, size=None, center=False, before=0):
    p = doc.add_paragraph(value, style=style)
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    if size:
        for r in p.runs:
            r.font.size = Pt(size)
    return p


def heading(doc, number, title, level, headings):
    p = add_text(doc, number + ' ' + title, 'Heading ' + str(level))
    headings.append({'number':number, 'title':title, 'level':level, 'text':p.text})
    return p


def append_element(doc, element):
    doc.element.body.insert(len(doc.element.body)-1, element)


def sections(source):
    chapter = 0
    result = []
    for element in source.element.body:
        p = para(element, source)
        if p is not None and p.style.name == 'Heading 1':
            chapter += 1
        if element.tag != qn('w:sectPr'):
            result.append((chapter, element))
    return result


def build(kind, toc_entries):
    stem, report_title, keep = KINDS[kind]
    doc = Document(HERE / 'thesis_source.docx')
    source_elements = sections(doc)
    for node in list(doc.element.body):
        if node.tag != qn('w:sectPr'):
            doc.element.body.remove(node)
    # The retained typography matches the thesis, with explicit report numbers.
    for name in ('Heading 1','Heading 2','Heading 3'):
        pr = doc.styles[name].element.get_or_add_pPr()
        for node in list(pr.findall(qn('w:numPr'))):pr.remove(node)
    doc.core_properties.title = TITLE
    doc.core_properties.subject = report_title
    doc.core_properties.comments = '卒業論文の指定章を再利用した授業提出用レポート．'
    add_text(doc, report_title, size=18, center=True, before=35)
    add_text(doc, TITLE.replace('における', 'における\n'), size=18, center=True, before=70)
    add_text(doc, '南山大学 理工学部 電子情報学科', size=13, center=True, before=105)
    add_text(doc, '学籍番号：2023TC011', size=15, center=True, before=25)
    add_text(doc, '氏名：伊藤 悠真', size=16, center=True, before=20)
    doc.add_page_break()
    add_text(doc, '目次', size=18, before=0)
    for entry in toc_entries:
        p=add_text(doc, entry['text']+'\t'+str(entry['page']), size=10)
        p.paragraph_format.left_indent = Mm(4*(entry['level']-1))
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.tab_stops.add_tab_stop(Mm(169), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
    if not toc_entries:add_text(doc,'目次はPDF生成時に確定する．')
    headings, reused = [], []
    additions = []
    if kind == 'progress':
        heading(doc,'1','研究概要と実施内容',1,headings)
        heading(doc,'1.1','研究概要と比較条件',2,headings)
        overview = [
            '本研究は，LLMが生成したQiskit量子回路コードの初期失敗に対し，修正と独立再生成を比較し，追加成功数，成功対象，計算コストを整理する実証研究である．QiskitとQiskit Aerを用いて回路を構築・評価した[2][3]．研究の問いは，追加成功数の違い（RQ1），救済対象の重なり（RQ2），追加計算コストと修正回数の関係（RQ3）である．',
            '対象は5モデル・10タスク・seed 0〜19の1,000初期組である．略号はQ4=qwen3.5:4b，G4=gemma4:e4b-it-qat，Q9=qwen3.5:9b，C7=qwen2.5-coder:7b，G3=gemma3:4bとする．B/R/F/D/Pの5,000条件記録と，B4の追加実験1,000組を分けて集計した[1]．',
            'Bは初回生成のみ，Pは生成前注意事項を加えた独立1回生成である．Rは課題仕様と前回コードによる自己見直し，Fは実行診断を用いる修正，Dは同じ評価方式の診断に加えて説明・原因分析を促す修正である．B4は初回結果を共有し，追加要求には前回コード・診断を渡さず専用seedで同じ課題から独立再生成する．R/F/D/B4は追加最大3回で成功時に停止する．',
            'L3成功は，読込み・import等と必須インターフェース（L0），回路構築・評価実行（L1），指定入力の期待出力との一致（L2），量子ビット数・回路命令数の範囲などの構造要件をすべて満たすことをいう．分布は8,192 shotsの全変動距離，状態ベクトルは大域位相を整合したユークリッド距離で比較し，距離0.05未満を出力一致とする．全入力のアルゴリズム同値性は保証しない．',
            '初期成功は455組，初期失敗は545組である．追加成功率は，同じ初期失敗545組のうち追加生成でL3に到達した組の割合であり，全1,000組を分母とする最終成功率とは区別する．最大生成回数が同じでも，入力情報・tokens予算・seed規則・実行時期は等しくない．',
        ]
        for text in overview:add_text(doc,text);additions.append(text)
        heading(doc,'1.2','実施内容',2,headings)
        text='評価ハーネスを開発して実験を実施し，評価器と記録の整合性を検証した．評価器修正後は保存コードを再採点し，必要な部分追試293ケースを行ったうえで，到達可能な履歴を再構成した．公開CSVの集計と，Fのみ／Dのみ成功した83組の静的履歴分析を行った．以下の結果はこれらの実施済み作業に基づく．本報告の作成に伴う新規実験や再採点は行っていない．'
        add_text(doc,text);additions.append(text)
    counters = [0,0,0]
    current = 0
    for old_chapter, original in source_elements:
        if old_chapter not in keep:continue
        element = deepcopy(original)
        plain_cached_fields(element)
        p = para(element,doc)
        original_text = p.text if p is not None else None
        if p is not None and p.style.name.startswith('Heading '):
            level=int(p.style.name[-1])
            if level==1:
                current=old_chapter if kind=='design' else old_chapter-2
                counters=[current,0,0]
            else:
                counters[level-1]+=1
                for j in range(level,3):counters[j]=0
            title=p.text
            if kind=='design' and title=='論文の構成と対象範囲':title='報告書の構成と対象範囲'
            number='.'.join(map(str,counters[:level]))
            p.text=number+' '+title
            p.paragraph_format.keep_with_next=True
            for np in list(p._p.findall('.//'+qn('w:numPr'))):np.getparent().remove(np)
            headings.append({'number':number,'title':title,'level':level,'text':p.text})
        elif p is not None:
            if kind=='design':
                if p.text.startswith('第2章で関連研究を整理し'):
                    p.text='本報告は第1〜3章に研究背景，関連研究，評価・実験方法を収録し，第4章で実施済み実験の比較指標と評価計画を整理する．結果・考察・結論は別の進捗・成果報告にまとめる．本研究の分析には保存済みの実験結果と必要な部分追試を用いた．B/R/F/D/Pは2026-10-16版，B4は2026-10-22固定の追加実験結果[3]に基づく．'
                replace_text(element,r'付録（8\.1節）','文献[3]の固定出典')
            else:
                replace_text(element,r'\[3\]','[1]')
                replace_text(element,r'表(\d+)',lambda m:'表'+str(int(m[1])-2))
                replace_text(element,r'図(\d+)',lambda m:'図'+str(int(m[1])-1))
                replace_text(element,r'第3章と付録（8\.1節）','第1章と文献[1]の固定出典')
                replace_text(element,r'第3章','第1章')
                replace_text(element,r'(?<!\d)([456])\.(\d+)節',lambda m:str(int(m[1])-2)+'.'+m[2]+'節')
                replace_text(element,r'付録8\.3に示す注意事項','上記の注意事項')
        append_element(doc,element)
        reused.append({'source_chapter':old_chapter,'source_text':original_text,
                       'report_text':p.text if p is not None else None,'kind':'paragraph' if p is not None else 'table'})
    if kind=='design':
        heading(doc,'4','評価計画の整理',1,headings)
        intro='以下は，研究の評価計画として設定し，既に実施した実験へ適用した比較指標の整理である．実験を未実施の予定として示すものではない．'
        add_text(doc,intro);additions.append(intro)
        items=[
            ('追加成功率','初期L3失敗545組を共通の分母とし，R/F/Dによる修正の救済率とB4による独立再生成の追加成功率を比較した．初期成功を含む全1,000組の最終L3成功率は別指標として扱い，B・Pを含む6条件の到達状況を確認した．'),
            ('成功対象の重なり','モデル・タスク・seedを対応づけ，共通成功，片側のみ成功，双方未成功を集計した．成功数の近さと成功対象の一致を区別し，事後的な成功集合の和集合を実行前に利用できる選択方策の成績とは扱わない設計とした．'),
            ('モデル別・初期失敗類型別の分析','各モデルの初期失敗数を分母とする比較と，介入前の失敗類型で対象を固定した比較を行った．モデル・タスク・失敗類型の関連と少数例を考慮し，一般的な優劣や統計的有意差を断定しない．'),
            ('追加計算コストと修正回数','共有初期生成を除く入力＋出力tokens，追加要求数，生成要求時間，追加tokens／追加成功を集計した．未成功例への消費も含め，同じ履歴を修正回数で区切って追加成功と消費を比較した．R/F/Dの再構成履歴とB4の追加実験では，入力情報・seed規則・実行時期が異なるため，生成回数上限の一致をtokens予算の一致とみなさない．'),
        ]
        for i,(title,text) in enumerate(items,1):
            heading(doc,f'4.{i}',title,2,headings);add_text(doc,text);additions.append(text)
        ref_chapter=5
        ref_map={i:i for i in range(1,10)}
    else:
        heading(doc,'4.3','卒論完成に向けた計画',2,headings)
        text='卒論の完成に向けて本文を推敲し，目的・RQと結論の対応，実施済み作業と今後の検証課題の区別を最終確認する．固定集計・参考文献・図表と本文参照を照合し，数式，コード例，ページ番号，目次，文字のはみ出しを点検する．指導教員の指摘に基づいて必要な修正を行い，提出原稿の体裁を整える．これらの提出準備と，第3章に記した将来の研究上の追試計画は区別する．'
        add_text(doc,text);additions.append(text)
        ref_chapter=5
        ref_map={3:1,8:2,9:3}
    heading(doc,str(ref_chapter),'参考文献',1,headings)
    for chapter,original in source_elements:
        if chapter!=7:continue
        p=para(original,doc)
        if p is None:continue
        found=re.match(r'^\[(\d+)\]',p.text)
        if not found or int(found[1]) not in ref_map:continue
        element=deepcopy(original)
        plain_cached_fields(element)
        replace_text(element,r'^\[\d+\]',f'[{ref_map[int(found[1])]}]')
        if kind=='progress' and int(found[1])==3:
            Paragraph(element,doc).add_run('\nカタログ・事例・固定プロンプト：同固定版のdocs/graduation2026/内の\nintervention_catalog.csv，case_studies.json，experiment_prompts.json．')
        append_element(doc,element)
    path=HERE/(stem+'.docx')
    doc.save(path)
    record={'kind':kind,'stem':stem,'report_type':report_title,'headings':headings,'reused':reused,
            'additional_paragraphs':additions,'references':ref_map,
            'source_chapters':sorted(keep),'table_mapping':{str(i):i if kind=='design' else i-2 for i in (range(1,3) if kind=='design' else range(3,12))},
            'figure_mapping':{'1':1} if kind=='design' else {'2':1,'3':2,'4':3}}
    (HERE/(kind+'_build_record.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    return path,headings


def export(path):
    lib=ROOT/'.cache/graduation_office/root/usr/lib'
    env=os.environ.copy()
    binary=shutil.which('libreoffice')
    if not binary:
        binary=str(lib/'libreoffice/program/soffice.bin')
        env['LD_LIBRARY_PATH']=':'.join([str(lib/'libreoffice/program'),str(lib/'x86_64-linux-gnu'),env.get('LD_LIBRARY_PATH','')])
        env['SAL_USE_VCLPLUGIN']='svp'
    target=OUT/(path.stem+'.pdf')
    before=target.stat().st_mtime_ns if target.exists() else None
    command=[binary,'-env:UserInstallation=file:///tmp/qllm-course-reports-20261102','--headless','--convert-to','pdf','--outdir',str(OUT),str(path)]
    result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=90)
    if result.returncode==81:result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=90)
    if result.returncode or not target.exists() or target.stat().st_mtime_ns==before:
        raise RuntimeError('PDF export failed: '+result.stdout+result.stderr)
    return target


def locate_headings(pdf,headings):
    norm=lambda t:re.sub(r'\s+','',t)
    out=[]
    for h in headings:
        if h['level']>2:continue
        found=[]
        for i,page in enumerate(pdf):
            for block in page.get_text('dict')['blocks']:
                spans=[s for line in block.get('lines',[]) for s in line['spans']]
                heading_text = ''.join(s['text'] for s in spans
                    if abs(s['size']-({1:18,2:14}[h['level']]))<.2)
                if norm(h['text']) in norm(heading_text):
                    found.append(i+1)
        if len(found)!=1:raise ValueError(('Heading missing or duplicated',h,found))
        out.append({**h,'page':found[0]})
    return out


def main():
    for kind in KINDS:
        cache=HERE/(kind+'_toc.json')
        toc=json.loads(cache.read_text()) if cache.exists() else []
        for attempt in range(5):
            path,headings=build(kind,toc)
            pdf_path=export(path)
            pdf=pymupdf.open(pdf_path)
            entries=locate_headings(pdf,headings)
            if entries==toc:
                print(json.dumps({'report':kind,'pages':len(pdf),'toc_entries':len(entries)},ensure_ascii=False))
                break
            toc=entries
            cache.write_text(json.dumps(toc,ensure_ascii=False,indent=2)+'\n')
        else:raise RuntimeError('TOC did not converge: '+kind)
    manifest=json.loads((OUT/'source_manifest.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest['source_files'].items()),'Original source changed'


if __name__=='__main__':main()
