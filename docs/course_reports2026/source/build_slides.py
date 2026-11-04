"""Build two six-minute decks from the course reports and frozen aggregates.

Run with PYTHONPATH=.cache/graduation_tools .venv/bin/python
docs/course_reports2026/source/build_slides.py
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import pymupdf
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT = HERE / 'slides'
TITLE = '量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究'
FIXED = 'https://github.com/yuuma-ito/2026_ito_qLLM-ver3/tree/b4c0ba79b308e7b12ab88413714746a5620424b5'
SUMMARY = ROOT / 'docs/analysis/independent_4_completed_20261022/summary.csv'
CATALOG = ROOT / 'docs/graduation2026/intervention_catalog.csv'
FONT = 'IPAexGothic'
NAVY, TEAL, GRAY = '16324F', '007F86', '566477'


def read_csv(path):
    with path.open() as f:
        return list(csv.DictReader(f))


SUMMARY_ROWS = read_csv(SUMMARY)


def row(condition, grouping='overall', group='all'):
    found = [r for r in SUMMARY_ROWS if r['condition'] == condition
             and r['generation_cap'] == ('1' if condition == 'B' else '4')
             and r['grouping'] == grouping and r['group'] == group]
    if len(found) != 1:
        raise ValueError((condition, grouping, group))
    return found[0]


class Deck:
    def __init__(self, name, label, source):
        self.name, self.label, self.source = name, label, source
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.prs.core_properties.title = TITLE
        self.prs.core_properties.subject = label
        self.notes, self.pages = [], []

    def text(self, s, x, y, w, h, value, size=24, bold=False, color=NAVY, url=None):
        sh = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = sh.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(.025)
        tf.margin_top = tf.margin_bottom = Inches(.015)
        for i, line in enumerate(str(value).split('\n')):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(7)
            r = p.add_run()
            r.text = line
            r.font.name, r.font.size, r.font.bold = FONT, Pt(size), bold
            r.font.color.rgb = RGBColor.from_string(color)
            pr = r._r.get_or_add_rPr()
            pr.set('lang', 'ja-JP')
            for script in ('ea', 'cs'):
                el = OxmlElement('a:' + script)
                el.set('typeface', FONT)
                pr.append(el)
            if url:
                r.hyperlink.address = url
        return sh

    def box(self, s, x, y, w, h, color='EAF2F5'):
        sh = s.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        sh.fill.solid()
        sh.fill.fore_color.rgb = RGBColor.from_string(color)
        sh.line.fill.background()

    def slide(self, title, seconds, pages, cues):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.box(s, 0, 0, .15, 7.5, TEAL)
        self.text(s, .65, .35, 12, .65, title, 29, True)
        self.box(s, .7, 1.17, 11.9, .025, TEAL)
        self.text(s, .7, 6.98, 11.5, .32, f'{self.label} ｜ 元報告 p.{pages}', 11, color=GRAY)
        self.text(s, 12.1, 6.98, .6, .32, len(self.prs.slides), 12, color=GRAY)
        elapsed = sum(n['seconds'] or 0 for n in self.notes)
        clock = lambda t: f'{t//60}:{t%60:02d}'
        timing = f'{clock(elapsed)}–{clock(elapsed + seconds)}（{seconds}秒）' if seconds else '補足：本編6分に含めない'
        note = f'目安：{timing}\n出典：{self.source.name} p.{pages}\n' + '\n'.join('・' + c for c in cues)
        s.notes_slide.notes_text_frame.text = note
        self.notes.append({'slide': len(self.notes)+1, 'seconds': seconds, 'text': note})
        self.pages.append(pages)
        return s

    def cover(self, cues):
        s = self.slide(self.label, 15, '1, 3', cues)
        self.text(s, .85, 2, 11.8, 1.5, TITLE.replace('における', 'における\n'), 29, True)
        self.text(s, .9, 4.1, 11.7, .6, '南山大学 理工学部 電子情報学科', 23)
        self.text(s, .9, 4.85, 11.7, .6, '2023TC011　伊藤 悠真', 26, True)
        self.text(s, .9, 5.8, 11.7, .6, '授業報告用 ｜ 本編8枚・約6分', 21, color=GRAY)

    def lines(self, s, lines, y=1.65):
        for i, (head, body) in enumerate(lines):
            yy = y + i*1.5
            self.text(s, .85, yy, 11.6, .55, head, 25, True, TEAL)
            self.text(s, 1, yy+.62, 11.4, .8, body, 23)

    def table(self, s, headers, rows, widths, y=1.8, height=.66, size=22):
        for i, cells in enumerate([headers, *rows]):
            self.box(s, .8, y+i*height, 11.7, height, 'DCECEF' if i == 0 else ('F1F5F8' if i%2 else 'FFFFFF'))
            x = .9
            for cell, w in zip(cells, widths):
                self.text(s, x, y+i*height+.10, w-.1, height-.1, cell, size, i == 0)
                x += w

    def save(self):
        assert len(self.prs.slides) == 10
        assert sum(n['seconds'] or 0 for n in self.notes) == 360
        OUT.mkdir(exist_ok=True)
        self.prs.save(OUT / (self.name + '.pptx'))
        (OUT / (self.name + '_発表者ノート.txt')).write_text(
            '\n\n'.join(f"スライド{n['slide']}\n{n['text']}" for n in self.notes)+'\n')


def design():
    d = Deck('調査設計報告_スライド', '調査・設計報告', HERE / '卒業研究_調査設計報告.pdf')
    d.cover(['量子回路コードの失敗後に，修正か再生成かを選ぶための研究設計を説明する。'])
    s = d.slide('失敗した後に，何を与えて生成し直すか', 45, '3–5', ['import，回路構築，出力評価では利用できる手掛かりが違う。', 'Self-RefineとSelf-Debuggingを背景にするが，完全再現実験ではない。'])
    for x, head, body in [(.85,'読込み','構文・import・IF'),(4.9,'回路構築','API・回路の構成'),(8.95,'出力評価','期待状態・分布との一致')]:
        d.box(s,x,1.9,3.5,1.5)
        d.text(s,x+.15,2.1,3.2,.5,head,26,True)
        d.text(s,x+.15,2.85,3.2,.5,body,19)
    d.text(s,.9,4.05,11.5,.7,'実行できることと，期待出力が得られることを区別する。',27,True)
    d.text(s,.9,5.15,11.5,1.1,'自己見直しや実行診断を与える修正と，\n同じ課題からの独立再生成を比較する。',25)
    s = d.slide('研究課題は「数・対象・コスト」の三つ', 40, '3–4, 16', ['全体成功率だけでは初期成功の保持と追加成功が混ざる。', '最適な選択方策の実証前に，比較の根拠を整える。'])
    d.lines(s,[('RQ1　追加成功','同じ初期失敗から，どれだけL3へ到達するか。'),('RQ2　成功対象','成功数が近い条件は，同じ事例を成功させるか。'),('RQ3　計算コストと回数','未成功への消費も含め，何回まで生成するか。')])
    s = d.slide('共通の初回生成から，修正と再生成へ分岐', 60, '8–9', ['初回込み最大4回。成功した時点で停止する。', 'Pは初期コードを共有しない注意事項付きの独立1回生成。', 'Dでは説明・原因分析をコード先頭のコメントへ残す。'])
    d.box(s,.85,2.5,2.6,1.3)
    d.text(s,1.05,2.8,2.2,.7,'初回生成 B',26,True)
    for i,(c,t) in enumerate([('R','課題仕様＋前回コード'),('F','課題仕様＋前回コード＋実行診断'),('D','Fと同じ評価方式の診断＋説明・原因分析'),('B4','課題仕様のみから独立再生成')]):
        y=1.75+i*.9
        d.text(s,3.65,y,.6,.6,'→',25)
        d.text(s,4.4,y,1,.6,c,26,True,TEAL)
        d.text(s,5.5,y,7,.7,t,21)
    d.text(s,.9,5.6,11.5,.8,'初期成功を保持 ／ 初期失敗に追加最大3回 ／ L3成功時停止',22,True)
    d.text(s,.9,6.25,11.5,.45,'P：生成前注意事項付きの独立1回生成（Bとは別コード）',19,color=GRAY)
    s = d.slide('成功は，実行・期待出力・構造要件で判定', 55, '9–11', ['L3は指定入力に対する所定検査への適合。', '測定結果は量子ビットと古典ビットの対応を反映して比較する。', '全入力のアルゴリズム同値性や実機動作は保証しない。'])
    d.table(s,['段階','確認する内容'],[['L0','読込み・import・必須インターフェース'],['L1','回路構築・評価処理の実行'],['L2','指定入力で期待出力と一致'],['L3','L0・L1・L2と構造要件のすべて']], [1.7,9.8],y=1.6,height=.65)
    d.text(s,.9,5.05,11.6,1.1,'分布：8,192 shots，全変動距離0.05未満\n状態：大域位相を整合した距離0.05未満',22)
    d.text(s,.9,6.23,11.6,.5,'指定入力での一致を評価。任意入力に対する同値性は未検証。',20,True,TEAL)
    s = d.slide('5モデル・10タスク・20 seedを対応づける', 50, '12–15', ['5,000条件記録とB4追加1,000組を区別する。', '保存コード再採点と部分追試293ケースに基づく到達履歴の再構成を含む。', '旧120件は合算しない。'])
    d.text(s,.9,1.65,11.5,.8,'5 × 10 × seed 0〜19 ＝ 1,000初期組',32,True,TEAL)
    d.text(s,.9,2.75,11.5,1.2,'qwen3.5:4b ／ gemma4:e4b-it-qat ／ qwen3.5:9b\nqwen2.5-coder:7b ／ gemma3:4b',23)
    d.text(s,.9,4.2,11.5,1.3,'B/R/F/D/P：5,000条件記録（2026-10-16版）\nB4：追加1,000組（2026-10-22固定）',24,True)
    d.text(s,.9,5.9,11.5,.8,'保存済み履歴＋部分追試を利用。全件の新規生成ではない。',23)
    s = d.slide('追加成功率と最終成功率では分母が異なる', 50, '11–12, 16', ['初期失敗類型はBの時点で固定し，途中で類型が変わっても分母を動かさない。', 'コストは共有初期を除く入力と出力tokensで，未成功への消費も含む。'])
    d.box(s,.85,1.8,5.6,2)
    d.box(s,6.75,1.8,5.6,2)
    d.text(s,1.05,2,5.1,.6,'追加成功率',28,True,TEAL)
    d.text(s,1.05,2.85,5.1,.7,'追加成功数 ／ 初期失敗545組',22)
    d.text(s,6.95,2,5.1,.6,'最終成功率',28,True,TEAL)
    d.text(s,6.95,2.85,5.1,.7,'最終成功数 ／ 全1,000組',22)
    d.text(s,.9,4.35,11.5,1.7,'成功対象：共通・片側のみ・双方未成功を集計\n層別比較：モデル別・介入前の失敗類型別に分母を明示\n計算コスト：共有初期を除くtokensと追加要求数',24)
    s = d.slide('設計で揃える条件と，残る比較上の制約', 45, '15–16', ['ここまでの指標は実施済み実験に適用した設計であり，未実施の予定ではない。', '成功時停止による退行0は設計上の性質。', '以降の成果編で，数・対象・コストの観測結果を報告する。'])
    d.lines(s,[('比較の起点を揃える','同じ初期組・初期コード・初期判定から比較する。'),('最大生成回数を揃える','初回込み4回。ただし入力情報・tokens・seed・時期は異なる。'),('観測結果からカタログへ','選択の根拠を整理し，方策の検証は次の課題とする。')])
    s = d.slide('補足　再現設定と分析範囲', None, '9–15', ['質疑用。保存設定と固定出典を参照する。'])
    d.lines(s,[('生成設定','temperature 0.7 ／ max_tokens 1,024 ／ timeout 600秒'),('評価と乱数','測定・変換seed 42。B4の追加生成は専用seed規則。'),('制約','有限shots・指定入力・独自10タスク。一般的優劣は断定しない。')])
    s = d.slide('補足　参考文献・固定出典', None, '17', ['元報告の文献番号を使用。リンク先の新規照合は今回の作業範囲に含まない。'])
    refs=[('[1] Madaan et al. Self-Refine (2023)','https://arxiv.org/abs/2303.17651v2'),('[2] Chen et al. Teaching Large Language Models to Self-Debug (2023)','https://arxiv.org/abs/2304.05128v2'),('[3] 固定公開出典：commit b4c0ba7',FIXED),('[8] IBM Quantum: Construct circuits','https://quantum.cloud.ibm.com/docs/en/guides/construct-circuits'),('[9] Qiskit Aer documentation','https://qiskit.github.io/qiskit-aer/')]
    for i,(t,u) in enumerate(refs):d.text(s,.9,1.7+i*.83,11.5,.65,t,21,url=u)
    d.text(s,.9,6,11.5,.65,'文献番号は元報告に対応。その他の関連研究は元報告p.17を参照。',18,color=GRAY)
    return d


def progress():
    d = Deck('進捗成果報告_スライド', '進捗・成果報告', HERE / '卒業研究_進捗成果報告.pdf')
    d.cover(['修正と独立再生成の結果と，卒論完成に向けた残る作業を報告する。'])
    s = d.slide('同じ初期失敗545組から，追加成功を比較', 45, '3–5', ['初期成功455組を保持する。5モデル，10タスク，seed 0〜19の1,000初期組。', 'R/F/Dは検証済み保存履歴と部分追試293ケースから再構成した。B4は追加実験。', 'L3は指定入力の出力と構造要件への適合であり，全入力の同値性を保証しない。'])
    d.lines(s,[('実施済み','評価ハーネス開発・再採点・部分追試・公開集計・履歴分析'),('比較条件','R：自己見直し ／ F：実行診断 ／ D：診断＋説明・原因分析'),('独立再生成 B4','前回コード・診断を渡さず追加最大3回。L3成功時停止。')])
    s = d.slide('今回の追加成功数は，B4が217組で最多', 55, '4–5', ['追加成功率の分母は545組。全1,000組の最終成功率と分けて示す。', 'Pは注意事項付き独立1回生成であり，初期失敗への修正と区別する。', '最大回数は同じでも入力情報，tokens予算，seed規則，時期は一致しない。'])
    for i,c in enumerate(('R','F','D','B4')):
        r=row(c); n=int(r['successes_from_initial_failure']); y=1.85+i*.87
        d.text(s,.9,y,.8,.55,c,26,True)
        d.box(s,1.9,y+.08,n/545*12,.36,TEAL if c=='B4' else '91ADB9')
        d.text(s,7.05,y,5.2,.6,f'{n}/545組　{n/545*100:.1f}%',26,True)
    d.text(s,.9,5.65,11.5,.9,'最終成功率（分母1,000組）：B 45.5% ／ P 47.3%\nR 55.1% ／ F 63.8% ／ D 63.5% ／ B4 67.2%',21)
    s = d.slide('モデルごとに，最多の条件は異なる', 40, '5', ['Q4ではD，他の4モデルではB4が最多。', '分母と失敗類型の構成が違うため，一般的なモデル順位を表す表ではない。'])
    tags=['qwen3.5:4b','gemma4:e4b-it-qat','qwen3.5:9b','qwen2.5-coder:7b','gemma3:4b']
    rows=[]
    for label,tag in zip(['Q4','G4','Q9','C7','G3'],tags):
        rows.append([label,row('B4','model','ollama:'+tag)['initial_failures'],*[row(c,'model','ollama:'+tag)['successes_from_initial_failure'] for c in ('R','F','D','B4')]])
    d.table(s,['モデル','初期失敗','R','F','D','B4'],rows,[2.5,2.3,1.7,1.7,1.7,1.6],height=.63)
    d.text(s,.9,5.95,11.5,.85,'Q4=qwen3.5:4b ／ G4=gemma4:e4b-it-qat ／ Q9=qwen3.5:9b\nC7=qwen2.5-coder:7b ／ G3=gemma3:4b',18)
    s = d.slide('FとDは成功数が近くても，対象は一致しない', 50, '7–8', ['F183組，D180組で差は3組だが，片側のみの成功は83組。', '全83組の両条件166履歴・398修正遷移を静的に確認した。', '複数箇所が同時に変わり，変更の因果的寄与は分離できない。'])
    for x,n,label in [(.85,43,'Fのみ'),(4.8,140,'F/D共通'),(8.75,40,'Dのみ')]:
        d.box(s,x,1.9,3.65,2)
        d.text(s,x+.2,2.15,3.2,.85,f'{n}組',42,True,TEAL)
        d.text(s,x+.2,3.15,3.2,.55,label,25,True)
    d.text(s,.9,4.4,11.5,.7,'片側救済83組 ／ 双方未救済322組',28,True)
    d.text(s,.9,5.45,11.5,1.1,'和集合223組は，結果を見て分かる事後的な集合。\n実行前に選べる方策の成功数として扱わない。',23)
    s = d.slide('失敗段階ごとの観測を介入カタログへ整理', 55, '6, 10, 13', ['初期失敗類型はBの段階で固定する。', '3行は異なる失敗段階の比較であり，頻度上位3類型という意味ではない。', '分類は最初に露見した段階であり，根本原因を完全に認定したものではない。'])
    rows=[[r['label'],r['initial_failures'],*[r[c+'_rate_percent']+'%' for c in ('F','D','B4')]] for r in read_csv(CATALOG)]
    d.table(s,['初期失敗類型','分母','F','D','B4'],rows,[3.6,1.8,2.1,2.1,1.9],height=.83)
    d.text(s,.9,5.4,11.5,1.15,'importではD，回路構築・出力不一致ではB4が最多。\n自動選択方策による性能改善は未検証。',25,True)
    s = d.slide('成功数と，未成功例を含む追加tokensを見る', 55, '8–9', ['共有初期生成を除く入力と出力tokens。未成功への消費も含む。', 'Fの3回目は28組，Dの3回目は33組を追加救済した。', '同じ履歴の打切り比較であり，上限別の独立実験ではない。'])
    rows=[]
    for c in ('R','F','D','B4'):
        r=row(c)
        rows.append([c,f"{int(r['additional_tokens']):,}",f"{float(r['tokens_per_added_success']):,.1f}"])
    d.table(s,['条件','追加tokens','tokens／追加成功'],rows,[2,4.6,4.9],height=.66)
    d.text(s,.9,5.45,11.5,1.15,'3回目の追加救済：F 28組 ／ D 33組\n入力情報・実行時期が異なる。資源効率は一般化しない。',23)
    s = d.slide('成果をまとめ，卒論提出と次の検証へ進む', 45, '11–13', ['選択・停止規則の性能検証は未実施。', '有限タスク・指定入力・出典時期の違いを限界として残す。', '提出準備と，新しいseedやタスクでの研究上の追試は別の作業。'])
    d.lines(s,[('得られた成果','追加成功・成功対象・計算コストを整理し，カタログ化した。'),('卒論完成に向けた作業','RQと結論・固定集計・図表参照・引用・体裁を最終確認する。'),('次の研究課題','選択・停止規則を事前固定し，別seed・タスクで検証する。')])
    s = d.slide('補足　Pの成績と検証状態', None, '4–5, 9', ['質疑用。Pの独立生成を修正による救済と混同しない。'])
    d.lines(s,[('P：注意事項付き独立1回生成','B失敗に対応する成功124/545，B成功に対応する失敗106/455。'),('B4：1,000組の完備性を確認済み','欠落・重複・予定外0，sanity成功。コード側NameError 2件。'),('解釈上の限界','一般的優劣・有意差・因果効果・自動選択性能は断定しない。')])
    s = d.slide('補足　元報告と固定出典', None, '14', ['文献番号は進捗・成果報告に対応する。リンク先の新規照合は今回行っていない。'])
    for i,(t,u) in enumerate([('[1] 固定公開出典：commit b4c0ba7',FIXED),('[1] B/R/F/D/P：2026-10-16版',FIXED+'/docs/presentation_sources/20261016T_reachable_rescues'),('[1] B4：2026-10-22固定',FIXED+'/docs/analysis/independent_4_completed_20261022'),('[2] IBM Quantum: Construct circuits','https://quantum.cloud.ibm.com/docs/en/guides/construct-circuits'),('[3] Qiskit Aer documentation','https://qiskit.github.io/qiskit-aer/')]):
        d.text(s,.9,1.65+i*.85,11.5,.65,t,22,url=u)
    d.text(s,.9,6.1,11.5,.6,'カタログ・保存事例・固定プロンプト：固定版 docs/graduation2026/',18,color=GRAY)
    return d


def export_pdf(deck):
    local = ROOT / '.cache/graduation_office/root/usr/lib'
    env = os.environ.copy()
    binary = shutil.which('libreoffice')
    if not binary:
        binary = str(local / 'libreoffice/program/soffice.bin')
        env['LD_LIBRARY_PATH'] = ':'.join([str(local/'libreoffice/program'),str(local/'x86_64-linux-gnu'),env.get('LD_LIBRARY_PATH','')])
        env['SAL_USE_VCLPLUGIN'] = 'svp'
    with tempfile.TemporaryDirectory(prefix='course-slides-') as profile:
        command=[binary,'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--convert-to','pdf','--outdir',str(OUT),str(OUT/(deck.name+'.pptx'))]
        pdf=OUT/(deck.name+'.pdf')
        before=pdf.stat().st_mtime_ns if pdf.exists() else None
        for _ in range(2):
            result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=90)
            if result.returncode != 81:break
        if result.returncode or not pdf.exists() or pdf.stat().st_mtime_ns == before:
            raise RuntimeError(result.stdout+result.stderr)


def validate(decks):
    norm=lambda s:re.sub(r'\s+','',s)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    checks={}
    for d in decks:
        pdf=pymupdf.open(OUT/(d.name+'.pdf'))
        source=pymupdf.open(d.source)
        source_text=norm(''.join(p.get_text() for p in source))
        texts=['\n'.join(s.text for s in page.shapes if s.has_text_frame) for page in d.prs.slides]
        checks[d.name]={
            'ten_slides':len(pdf)==len(d.prs.slides)==10,
            'eight_main_slides_six_minutes':sum(n['seconds'] or 0 for n in d.notes)==360 and all(n['seconds'] for n in d.notes[:8]) and all(n['seconds'] is None for n in d.notes[8:]),
            'fixed_title':norm(TITLE) in norm(texts[0]),
            'all_text_rendered':all(norm(s.text) in norm(pdf[i].get_text()) for i,page in enumerate(d.prs.slides) for s in page.shapes if s.has_text_frame),
            'fonts_embedded':all(pdf.extract_font(f[0])[3] for p in pdf for f in p.get_fonts()),
            'notes_saved':all(Presentation(OUT/(d.name+'.pptx')).slides[i].notes_slide.notes_text_frame.text==n['text'] for i,n in enumerate(d.notes)),
            'no_text_outside_page':all(0<=sp['bbox'][0] and 0<=sp['bbox'][1] and sp['bbox'][2]<=p.rect.width and sp['bbox'][3]<=p.rect.height for p in pdf for b in p.get_text('dict')['blocks'] for line in b.get('lines',[]) for sp in line['spans']),
            'source_contains_key_counts':all(norm(t) in source_text for t in ['1,000','545','455']),
        }
        if d.name.startswith('進捗'):
            checks[d.name]['additional_counts_match_report_and_csv']=all(f"{row(c)['successes_from_initial_failure']}/545組" in texts[2] and row(c)['successes_from_initial_failure'] in source_text for c in ('R','F','D','B4'))
        pdf.close()
        source.close()
    sources=[d.source for d in decks]+[SUMMARY,CATALOG,Path(__file__)]
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'title':TITLE,'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sources},'decks':[{'name':d.name,'main_slides':8,'supplemental_slides':2,'notes':d.notes} for d in decks],'new_experiments':False,'scope':'元報告の要約と固定CSVからの転記。参考文献の再調査・独立査読・発表時間の実測は未実施。'}
    (OUT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    report={'passed':all(all(c.values()) for c in checks.values()),'checks':checks,'artifact_sha256':{p.name:digest(p) for p in OUT.iterdir() if p.suffix in ('.pdf','.pptx','.txt')},'visual_review':'別途visual_review.jsonを参照'}
    (OUT/'validation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report['checks'],ensure_ascii=False,indent=2))
    if not report['passed']:raise SystemExit('Slide validation failed')


if __name__ == '__main__':
    decks=[design(),progress()]
    for deck in decks:
        deck.save()
        export_pdf(deck)
    validate(decks)
