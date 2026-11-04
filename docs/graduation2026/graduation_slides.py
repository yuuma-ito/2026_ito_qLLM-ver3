"""Build the six-minute presentation from the thesis's frozen evidence."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from six_conditions import values

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
B4 = ROOT / 'docs/analysis/independent_4_completed_20261022'
CORE = ROOT / 'docs/analysis/reachable_rescues_20261016/core'
TITLE = '量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究'
COMMIT = 'b4c0ba79b308e7b12ab88413714746a5620424b5'
FIXED = 'https://github.com/yuuma-ito/2026_ito_qLLM-ver3/tree/' + COMMIT
FONT = 'IPAexGothic'
SOURCES = [HERE / 'thesis.pdf', HERE / 'intervention_catalog.csv',
           CORE / 'repair_summary.csv', CORE / 'preventive_summary.csv',
           CORE / 'fd_overlap_summary.csv', B4 / 'summary.csv', B4 / 'source_manifest.json']


def build_slides():
    summaries = list(csv.DictReader((B4 / 'summary.csv').open()))
    catalog = list(csv.DictReader((HERE / 'intervention_catalog.csv').open()))
    def row(condition, grouping='overall', group='all'):
        selected = [r for r in summaries if r['condition'] == condition and r['generation_cap'] == '4'
                    and r['grouping'] == grouping and r['group'] == group]
        if len(selected) != 1:
            raise ValueError((condition, grouping, group))
        return selected[0]
    final = values()
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    prs.core_properties.title, prs.core_properties.author = TITLE, '伊藤 悠真'
    notes = []

    def text(slide, x, y, w, h, value, size=24, bold=False, color='202020', url=None):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(.025)
        tf.margin_top = tf.margin_bottom = Inches(.015)
        for i, line in enumerate(value.split('\n')):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(5)
            p.space_before = Pt(0)
            r = p.add_run()
            r.text = line
            r.font.name, r.font.size, r.font.bold = FONT, Pt(size), bold
            r.font.color.rgb = RGBColor.from_string(color)
            properties = r._r.get_or_add_rPr()
            properties.set('lang', 'ja-JP')
            for script in ('ea', 'cs'):
                typeface = OxmlElement('a:' + script)
                typeface.set('typeface', FONT)
                properties.append(typeface)
            if url:
                r.hyperlink.address = url
                r.font.underline = True
        return shape

    def box(slide, x, y, w, h, color='EAEAEA'):
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(color)
        shape.line.fill.background()
        return shape

    def slide(title, subtitle=None):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = RGBColor(255, 255, 255)
        text(s, .6, .35, 12.1, .65, title, 29, True)
        box(s, .63, 1.17, 12, .02, '444444')
        if subtitle:
            text(s, .7, 1.38, 12, .6, subtitle, 21)
        text(s, .65, 7.08, 11.6, .25, '卒業研究発表会 ｜ R/F/D：10月16日固定・B4：10月22日固定 [3]', 10, color='555555')
        text(s, 12.2, 7.02, .55, .35, str(len(prs.slides)), 13)
        return s

    def note(s, seconds, cues):
        index = len(prs.slides)
        start = sum(n['seconds'] or 0 for n in notes)
        clock = lambda sec: f'{sec//60}:{sec%60:02d}'
        timing = f'{clock(start)}–{clock(start+seconds)}（{seconds}秒）' if seconds else '質疑用（本編6分には含めない）'
        value = '目安：' + timing + '\n話す要点\n' + '\n'.join('・' + c for c in cues)
        s.notes_slide.notes_text_frame.text = value
        notes.append({'slide': index, 'seconds': seconds, 'text': value})

    s = slide('修正と独立再生成を，同じ初期失敗から比較する')
    text(s, .8, 1.9, 11.8, 1.4, TITLE.replace('における', 'における\n'), 30, True)
    text(s, .85, 3.8, 11.5, .6, '南山大学 理工学部 電子情報学科', 23)
    author = text(s, .85, 4.45, 11.5, .6, '発表者：2023TC011 伊藤 悠真', 24, True)
    author.text_frame.paragraphs[0].runs[0].font.underline = True
    text(s, .85, 5.12, 11.5, .6, '指導教員：横山 哲郎', 23)
    text(s, .85, 6.05, 11.5, .6, '追加成功数・成功対象・計算コストから介入を検討する', 23)
    note(s, 15, ['対象はLLMが生成するQiskitコード', '修正R/F/Dと独立再生成B4を比較する'])

    s = slide('失敗の段階によって，次に与える情報が異なる')
    for x, title, detail in [(0.8,'読込み','importの失敗'), (4.95,'回路構築','API・構築時の失敗'), (9.1,'出力評価','期待出力と不一致')]:
        box(s, x, 1.8, 3.45, 1.25)
        text(s, x+.15, 1.95, 3.15, .45, title, 26, True)
        text(s, x+.15, 2.5, 3.15, .4, detail, 20)
    for y, label, statement in [(3.5,'RQ1','修正と再生成で，追加成功数はどう違うか'),
                                (4.3,'RQ2','成功する対象は同じか'), (5.1,'RQ3','追加計算コストと停止回数はどう関係するか')]:
        text(s, .85, y, 1.1, .6, label, 24, True)
        text(s, 2, y, 10.4, .6, statement, 24)
    text(s, .85, 6.2, 11.6, .5, '背景：Self-Refine [1]・Self-Debugging [2]（完全再現実験ではない）', 18)
    note(s, 35, ['単に動くかと期待出力が正しいかを区別する', '自己点検と実行診断を用いる修正を背景に，修正と再生成を比べる'])

    s = slide('初回を共有し，修正R/F/Dと再生成B4に分岐', '5モデル × 10タスク × seed 0〜19 ＝ 1,000初期組')
    box(s, .8, 2.75, 2.7, 1.1)
    text(s, 1, 2.98, 2.3, .6, '初回生成 B', 26, True)
    for y, name, detail in [(2.05,'R','課題仕様＋前回コード（外部診断なし）'),
                             (2.9,'F','課題仕様＋前回コード＋実行診断'),
                             (3.75,'D','Fと同じ評価方式の診断＋説明・原因分析'),
                             (4.6,'B4','同じ課題から独立再生成（前回コード・診断なし）')]:
        text(s, 3.7, y+.1, .5, .5, '→', 26)
        box(s, 4.35, y, .9, .64, 'DADADA')
        text(s, 4.42, y+.06, .75, .5, name, 24, True)
        text(s, 5.4, y+.05, 7.3, .65, detail, 20)
    text(s, .85, 5.55, 11.8, .55, '追加最大3回・L3成功時停止 ／ Pは注意事項付きの独立1回生成', 21)
    text(s, .85, 6.2, 11.8, .65, 'B/R/F/D/P：5,000条件記録 ＋ B4：追加1,000組\nL3は指定入力の出力と構造要件への適合。全入力での正しさは保証しない。', 18)
    note(s, 50, ['1要求の生成上限は1,024 tokens', '初期成功455組を保持し，初期失敗545組で追加成功を比較する', 'R/F/Dは検証済み保存履歴と部分追試の再構成。全件新規生成ではない', '最大4回でも入力情報・実要求数・tokens・seed規則・実行時期は一致しない'])

    s = slide('B4は217組で追加成功し，最終成功は672組')
    text(s, .85, 1.55, 6.1, .5, '最終L3成功率：全1,000初期組', 23, True)
    shades = {'B':'BBBBBB','P':'AAAAAA','R':'999999','F':'555555','D':'777777','B4':'222222'}
    for i, r in enumerate(final):
        y = 2.35 + i*.53
        text(s, .85, y, .7, .42, r['condition'], 21, True)
        box(s, 1.65, y+.09, r['rate_percent']/70*2.4, .25, shades[r['condition']])
        text(s, 4.2, y, 2.1, .45, f"{r['successes']}組 {r['rate_percent']:.1f}%", 21)
    text(s, 6.9, 1.55, 5.7, .6, '追加成功率：初期失敗545組', 23, True)
    for i, c in enumerate(('R','F','D','B4')):
        r = row(c)
        y = 2.4+i*.76
        text(s, 7, y, .8, .5, c, 24, True)
        text(s, 8, y, 4.3, .6, f"{r['successes_from_initial_failure']}組  {100*float(r['success_from_initial_failure_rate']):.1f}%", 27, True)
    text(s, .85, 6.05, 11.6, .75, '分母を区別する。B4は今回の対象で最多。\n最大生成回数が同じでも，入力情報やtokens予算は等しくない。', 21)
    note(s, 60, ['左は全1,000組の最終L3成功率で，BとPも含む', '右は初期失敗545組からの追加成功で，R96・F183・D180・B4217組', 'B4の39.8%と最終67.2%を混ぜない', '観測差を因果効果や一般的優劣と断定しない'])

    s = slide('FとDの成功数は近いが，成功対象は一致しない')
    for x, n, label in [(.85,43,'Fのみ'),(4.8,140,'F/D共通'),(8.75,40,'Dのみ')]:
        box(s, x, 1.95, 3.65, 2.0)
        text(s, x+.2, 2.2, 3.25, .8, f'{n}組', 39, True)
        text(s, x+.2, 3.18, 3.25, .55, label, 26)
    text(s, .85, 4.45, 11.5, .65, 'Fのみ43組＋Dのみ40組＝片側救済83組', 28, True)
    text(s, .85, 5.35, 11.6, 1.2, '両条件166履歴・398修正遷移を静的に確認。双方未救済322組。\n同時に複数箇所が変わるため，成功原因は分離できない。\n和集合223組は，実行前に選べる方策の成績ではない。', 21)
    note(s, 40, ['共通140にFのみ43，Dのみ40を足して各条件の成功集合を説明する', '83組の全履歴確認と変更の因果効果の実証は区別する'])

    s = slide('失敗類型により，追加成功率が最大の条件は変わる', '介入カタログ：異なる失敗段階を比較する3類型（卒論 表11）')
    headers = ['初期失敗類型','分母','F救済率','D救済率','B4追加成功率']
    xs, widths = [.85,4.15,5.7,7.7,9.7], [3.1,1.35,1.8,1.8,2.7]
    box(s, .8, 2.2, 11.8, .6, 'DDDDDD')
    for x,w,h in zip(xs,widths,headers): text(s,x,2.3,w,.4,h,20,True)
    for i,r in enumerate(catalog):
        y = 3.05+i*.85
        entries = [r['label'],r['initial_failures'],*(r[c+'_rate_percent']+'%' for c in ('F','D','B4'))]
        for x,w,v in zip(xs,widths,entries):text(s,x,y,w,.6,v,24)
    text(s,.85,5.75,11.7,.9,'CSVは3行×9列。類型別の件数と観測率を整理したもの。\n自動選択方策による性能改善は未検証。',23)
    note(s,50,['importではD，構築・出力ではB4が最多', '件数上位3類型という意味ではない', 'CSVは分類キー・表示名・分母・F/D/B4の成功数と率の9列', 'モデル別でもQ4はD，他の4モデルはB4が最多。補足Aに示す'])

    s = slide('追加成功と計算コストを併せて比較する', '共有初期生成を除く入力＋出力tokens。未成功例への消費も含む。')
    for x,w,v in [(.85,1.0,'条件'),(2,2.8,'追加tokens'),(4.8,2.6,'tokens／追加成功')]:text(s,x,2.15,w,.6,v,21,True)
    for i,c in enumerate(('R','F','D','B4')):
        r=row(c);y=2.95+i*.67
        text(s,.85,y,.9,.5,c,24,True)
        text(s,2,y,2.7,.5,f"{int(r['additional_tokens']):,}",24)
        text(s,4.8,y,2.7,.5,f"{float(r['tokens_per_added_success']):,.1f}",24,True)
    text(s,8,2.15,4.4,.6,'3回目の修正による救済',22,True)
    text(s,8.15,3.05,4.15,1.2,'F：28組　D：33組',27,True)
    text(s,8,4.15,4.4,1.6,'同じ履歴を回数で区切った比較。\n上限別の独立実験ではない。',22)
    text(s,.85,6.15,11.6,.6,'R/F/Dは再構成した履歴の計算値。実行条件が異なり，資源効率は一般化しない。',18)
    note(s,55,['B4は995,815 tokensを217組で割り4,589.0 tokens／追加成功', '金銭費用ではなく，失敗要求への消費を含む', 'Fの28組とDの33組は3回目で初めて救済された。停止で失う成功も考慮する'])

    s = slide('全体成績・成功対象・失敗の特徴を合わせて見る')
    for y,n,v in [(1.85,'1','今回の追加成功数はB4が最多：217/545組'),
                  (3.0,'2','F/Dは成功対象が異なる：片側救済83組'),
                  (4.15,'3','モデル・初期失敗類型によって最多条件が変わる')]:
        text(s,.85,y,.5,.6,n,28,True);text(s,1.55,y,10.9,.8,v,26,True)
    text(s,.85,5.5,11.6,1.2,'観測結果を介入カタログに整理。自動選択の有効性は未検証。\n今後：選択・停止規則を事前固定し，別seed・タスクで検証する。',23)
    note(s,55,['全体の観測と層別の違いを合わせて三つの知見を述べる', '指定入力・有限タスクでの探索的な記述で，有意差や因果効果は主張しない', 'tokens予算も揃えた比較を今後の課題とする'])

    s = slide('補足A　モデル別の追加成功数', '分母は各モデルの初期失敗数。全体の545組を各行の分母にしない。')
    columns=[(.85,2.9,'モデル'),(3.9,1.35,'分母'),(5.6,1.2,'R'),(7,1.2,'F'),(8.4,1.2,'D'),(10,1.6,'B4')]
    for x,w,v in columns:text(s,x,2.1,w,.5,v,23,True)
    models=[('Q4','qwen3.5:4b'),('G4','gemma4:e4b-it-qat'),('Q9','qwen3.5:9b'),('C7','qwen2.5-coder:7b'),('G3','gemma3:4b')]
    for i,(short,tag) in enumerate(models):
        y=2.9+i*.52
        vals=[short,row('B4','model','ollama:'+tag)['initial_failures'],*(row(c,'model','ollama:'+tag)['successes_from_initial_failure'] for c in ('R','F','D','B4'))]
        for (x,w,_),v in zip(columns,vals):text(s,x,y,w,.45,v,24)
    text(s,.85,5.85,11.6,.8,'Q4=qwen3.5:4b　G4=gemma4:e4b-it-qat　Q9=qwen3.5:9b\nC7=qwen2.5-coder:7b　G3=gemma3:4b',19)
    note(s,None,['Q4ではD90組，他の4モデルではB4が最多', '失敗数やタスク構成の違いを伴い，一般的なモデルランキングではない'])

    s = slide('補足B　評価と比較の範囲')
    text(s,.85,1.75,11.6,4.9,'L3：L0・L1・L2・構造要件のすべてを満たす\n分布評価：8,192 shots・全変動距離0.05未満\nR/F/D：検証済みの保存履歴＋部分追試293ケース\nB4：同じ初期1,000組からの追加条件として別に集計\nP：独立1回生成，最終成功473/1,000組\n旧120件は合算しない。全入力のアルゴリズム同値性は保証しない。\n最大4回でも，入力情報・実要求数・tokens・seed規則・実行時期は異なる。',22)
    note(s,None,['初期成功の保持と成功時停止により退行0となる', '現行v4の測定・変換seedは42固定。別seedへの感度は未検証', '有限shots，1,024 tokens上限，診断文や負荷の差が残る', '測定禁止など課題文の全条件の遵守は主L3の保証範囲に含まれない', '部分追試647生成中120生成はlength終了。Dの説明指示の効果と出力枠の影響を分離しない'])

    s = slide('補足C　参考文献 [1]–[5]（卒論と同じ番号）')
    refs=[
        (1,'A. Madaan et al.','Self-Refine: Iterative Refinement with Self-Feedback','arXiv:2303.17651v2 (2023)','https://arxiv.org/abs/2303.17651v2'),
        (2,'X. Chen, M. Lin, N. Schärli, D. Zhou','Teaching Large Language Models to Self-Debug','arXiv:2304.05128v2 (2023)','https://arxiv.org/abs/2304.05128v2'),
        (3,'伊藤悠真','現行救済経路の固定発表出典（2026-10-16版）／B4追加実験（2026-10-22固定）','公開固定版（b4c0ba7）',FIXED),
        (4,'M. Chen et al.','Evaluating Large Language Models Trained on Code','arXiv:2107.03374v2 (2021)','https://arxiv.org/abs/2107.03374v2'),
        (5,'J. Austin et al.','Program Synthesis with Large Language Models','arXiv:2108.07732 (2021)','https://arxiv.org/abs/2108.07732'),
    ]
    for i,(n,author,title,label,url) in enumerate(refs):
        y=1.5+i*1.02
        text(s,.8,y,11.9,.35,f'[{n}] {author}',16,True)
        text(s,.8,y+.34,11.9,.35,title,17)
        text(s,.8,y+.69,11.9,.32,label,16,url=url)
    note(s,None,['本編では設計の背景として[1][2]，実験の一次資料として[3]を引用', '卒論の参考文献番号と版を保持。背景文献[4][5]も対応づける'])

    s = slide('補足D　参考文献 [6]–[9]・固定資料への入口')
    refs=[
        (6,'J. Huang et al.','Large Language Models Cannot Self-Correct Reasoning Yet','arXiv:2310.01798v2 (2024)','https://arxiv.org/abs/2310.01798v2'),
        (7,'S. Vishwakarma et al.','Qiskit HumanEval: An Evaluation Benchmark For Quantum Code Generative Models','arXiv:2406.14712 (2024)','https://arxiv.org/abs/2406.14712'),
        (8,'IBM Quantum','Construct circuits, IBM Quantum Documentation','公式資料（2026年10月29日参照）','https://quantum.cloud.ibm.com/docs/en/guides/construct-circuits'),
        (9,'Qiskit Development Team','Qiskit Aer documentation','公式資料（2026年10月29日参照）','https://qiskit.github.io/qiskit-aer/'),
    ]
    for i,(n,author,title,label,url) in enumerate(refs):
        y=1.5+i*1.02
        text(s,.8,y,11.9,.35,f'[{n}] {author}',16,True)
        text(s,.8,y+.34,11.9,.35,title,17)
        text(s,.8,y+.69,11.9,.32,label,16,url=url)
    text(s,.8,5.8,11.9,.4,'文献[3]の固定commit：'+COMMIT,16)
    text(s,.8,6.3,5.7,.4,'10月16日：R/F/D固定出典',18,url=FIXED+'/docs/presentation_sources/20261016T_reachable_rescues')
    text(s,6.5,6.3,5.9,.4,'10月22日：B4固定出典',18,url=FIXED+'/docs/analysis/independent_4_completed_20261022')
    note(s,None,['リンクから固定commit内の出典に移動できる', '参考文献の真正性と引用の範囲は卒論PDFの確認記録に基づく'])

    assert sum(n['seconds'] or 0 for n in notes)==360 and len(prs.slides)==12
    prs.save(HERE / 'slides.pptx')
    (HERE/'speaker_notes.txt').write_text('6分発表用の要点メモ\n本編8枚＝360秒。補足4枚は質疑用。\n\n'+ '\n\n'.join(f"{n['slide']}枚目\n{n['text']}" for n in notes)+'\n\n実際の所要時間はスライドを見て話すリハーサルで確認する。\n')
    manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'basis':'最新の卒論thesis.pdfと同じ固定CSV','main_slides':8,'supplemental_slides':4,'planned_seconds':360,'notes':notes,'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES},'new_model_requests':0,'generated_code_executions':0}
    (HERE/'slides_source_manifest_20261102.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    build_slides()
