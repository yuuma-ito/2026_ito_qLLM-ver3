"""Build the university-format abstract from one text source (no experiments).

Run: PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/midterm2026/build_abstract.py
Then compile paper.tex with LuaLaTeX twice. See README.md for verification.
"""
from pathlib import Path
import csv
import json
from docx import Document
from docx.shared import Mm, Pt, RGBColor
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = ROOT / 'docs/presentation_sources/20261016T_reachable_rescues'
TITLE = '量子LLM支援プログラミングにおける\n失敗類型と介入カタログの実証研究'
AUTHOR = '2023TC011 伊藤 悠真　　指導教員：横山 哲郎'
CONDITIONS = ['self_refine', 'execution_feedback', 'self_debugging']
MODEL_NAMES = [('G3', 'gemma3:4b'), ('G4', 'gemma4:e4b-it-qat'),
               ('C7', 'qwen2.5-coder:7b'), ('Q4', 'qwen3.5:4b'), ('Q9', 'qwen3.5:9b')]
ERROR_NAMES = [('回路構築', 'build_error'), ('import', 'import_error'),
               ('IF不適合', 'interface_mismatch'), ('量子ビット数', 'qubit_count_mismatch'),
               ('構文', 'syntax'), ('unknown', 'unknown_error'), ('出力不一致', 'wrong_output')]
ROWS = list(csv.DictReader((ROOT / 'docs/analysis/reachable_rescues_20261016/core/repair_summary.csv').open()))
SNAP = json.loads((SOURCE / 'results_snapshot.json').read_text())


def rows(grouping, names):
    result = []
    for label, value in names:
        rr = [next(r for r in ROWS if r['scope'] == 'pooled' and r['grouping'] == grouping
                   and r['condition_id'] == c
                   and r['model_spec' if grouping == 'model' else 'baseline_error_category']
                   == ('ollama:' + value if grouping == 'model' else value)) for c in CONDITIONS]
        assert len({r['initial_failures'] for r in rr}) == 1
        result.append([label, rr[0]['initial_failures']] + [r['rescued'] for r in rr])
    return result


TABLES = [
    ('モデル別の救済件数（分母は初期失敗）', ['モデル', '分母', 'R', 'F', 'D'], rows('model', MODEL_NAMES)),
    ('初期失敗類型別の救済件数', ['初期失敗', '分母', 'R', 'F', 'D'], rows('baseline_error', ERROR_NAMES)),
    ('FとDの救済対象（初期失敗545組）', ['共通', 'Fのみ', 'Dのみ', '双方未救済'],
     [[str(SNAP['primary']['fd_overlap'][k]) for k in ['both', 'F_only', 'D_only', 'neither']]])
]

# Tables are kept in the reading order; the same prose is used in TeX and Word.
BLOCKS = [
('h', '背景'),
('p', 'LLMによる量子回路コード生成では，実行時の失敗に加え，実行できても期待した量子状態・測定分布を返さない場合がある．本研究の目的は，Qiskitコードの初期失敗に対する修正介入の救済率と救済対象の違いを明らかにし，失敗類型に応じた介入カタログの根拠を整理することである．Self-Refine［1］とSelf-Debugging［2］を背景に比較条件を実装したが，先行研究の完全再現ではない．'),
('h', '評価の枠組み'),
('p', 'L0はimport・必須関数の要件，L1は回路構築と評価処理の実行，L2は指定入力での期待出力との一致，主L3はこれらと構造要件への適合とする．構造要件は量子ビット数と測定以外の回路命令数の範囲である．主L3は限定された評価基準であり，全入力でのアルゴリズム同値性を保証しない．'),
('p', '測定分布は8,192 shotsの全変動距離，状態ベクトルは大域位相を整合した距離を用い，0.05未満を出力一致とする．測定先は量子ビット順に対応づける．救済率は「初期失敗から最終主L3成功となった組数／初期主L3失敗組数」とし，失敗類型は介入前の判定で固定する．'),
('h', '実験方法'),
('p', '5モデル・10タスク・seed 0〜19の1,000初期組を対象に，5条件，計5,000条件記録を分析した．モデル略号はQ4：qwen3.5:4b，G4：gemma4:e4b-it-qat，Q9：qwen3.5:9b，C7：qwen2.5-coder:7b，G3：gemma3:4bである．'),
('p', 'タスクはBell，GHZ，Deutsch–Jozsa（constant/balanced），Bernstein–Vazirani，Grover，QFT，IQFT，QPE，Ansatzとした．temperatureは0.7，1要求の生成上限は1,024 tokensである．'),
('p', 'Bは初期生成，Rは自己見直し，Fはエラー等の実行結果提示，Dは説明・原因分析を促す自己デバッグ，Pは生成前注意事項である．R/F/DはBと同じ初期コード・判定から最大3回修正し，成功時に停止する．Pは別プロンプトによる独立生成である．'),
('p', '検証済み保存結果と必要な部分追試293ケースを反映した到達可能な経路を用いた［3］．全件を新規生成した実験ではない．元実験の設定・診断文処理には差がある．今回の執筆では追加生成・コード再実行を行わず，旧120件も合算しない．'),
('h', '結果'),
('p', '初期成功は455組，失敗は545組であった．救済はRが96/545組（17.6%），Fが183/545組（33.6%），Dが180/545組（33.0%）であった．全体率は初期失敗545組を分母とする合算値である．'),
('t', 0),
('p', '表1では，G4の救済はF 48/62組，D 38/62組だが，Q4ではF 78/162組，D 90/162組と大小が入れ替わる．各モデル200初期組のうち失敗した組だけを分母とした．'),
('t', 1),
('p', '表2のimport失敗はF 58/271組（21.4%），D 72/271組（26.6%），回路構築失敗はF 76/126組（60.3%），D 68/126組（54.0%）であった．IFはインターフェースを表す．保存分類unknownの1組は生成コード側の失敗であり，API接続障害ではない．少数分母の率は参考値とする．'),
('t', 2),
('p', 'FとDの全体の救済数は3組差だが，表3の片側のみ救済した83組では対象が異なる．import失敗はFのみ8組・Dのみ22組，回路構築失敗は19組・11組であった．83組すべての両条件166履歴・398修正遷移を静的に確認した．複数箇所が同時に変わるため，変更内容から救済原因は分離できない．少なくとも一方が救済した223/545組（40.9%）は事後的な集合であり，実行前の選択方策の成功率ではない．'),
('p', '救済側の履歴では，import/API関係の変更がFのみ28組・Dのみ34組，回路構築・インターフェース関係の変更が24組・32組に認められた（分類は重複可）．これは静的な変更分類であり，量子論理の訂正や各変更の因果的寄与を示すものではない．'),
('p', 'PではBの初期失敗に対応する成功が124/545組（22.8%），初期成功に対応する失敗が106/455組（23.3%）で，最終成功は473/1,000組だった．独立生成の結果を同一コードの修正による救済と同じ作用とは解釈しない．'),
('p', '共有初期生成を除き，未救済例への消費も含めた追加入力・出力tokens／救済はR 18,852.6，F 9,333.8，D 10,976.6であった．保存記録と部分追試の再構成値であり，全件新実験の実測費用ではない．3回目はFで28/390組（7.2%），Dで33/398組（8.3%）を追加救済した．2回打切りでは3回で救済できた組の15.3%，18.3%をそれぞれ失う．これは同一履歴の打切り比較である．'),
('h', '考察'),
('p', 'FとDの救済率が近くても救済対象は一致せず，初期失敗類型・モデルによって大小が変わった．介入カタログには全体率だけでなく，適用対象，失敗分母，追加消費を併記する必要がある．ただし，失敗類型はモデル・タスクと関連しており，この結果だけで介入選択規則を確定できない．'),
('p', 'R/F/Dは最大3回の修正機会を持つ一方，B/Pは独立した1回生成であり，生成回数・投入情報が異なる．同じ要求回数の独立再生成対照もないため，介入の因果効果を断定しない．成功時停止，初期コード・タスク・seedの依存，元実験の診断文差もあり，5,000条件を独立標本として統計的有意差や一般的優劣を主張しない．指定入力の主L3，有限shots，未固定の測定乱数，生成上限も限界である．'),
('h', 'おわりに'),
('p', '初期失敗545組に対し，Fは33.6%，Dは33.0%を救済したが，片側のみ救済した83組の内訳は異なった．この違いを介入カタログの根拠として整理した．今後は介入選択・停止方策を事前固定し，要求回数をそろえた独立再生成対照と別seed・タスクによる検証を行う．'),
('ref', 'A. Madaan et al.：Self-Refine: Iterative Refinement with Self-Feedback，arXiv:2303.17651（2023）．'),
('ref', 'X. Chen et al.：Teaching Large Language Models to Self-Debug，arXiv:2304.05128（2023）．'),
('ref', '現行到達経路の固定集計・保存設定・出典hash（2026-10-16版）．本原稿READMEに出典と検証記録を示す．'),
]


def escape(s):
    return ''.join({'&': r'\&', '%': r'\%', '_': r'\_', '#': r'\#'}.get(c, c) for c in s)


def build_tex():
    pre = r'''% Generated by build_abstract.py; prose is shared with paper.docx.
\documentclass[a4paper,10pt,twocolumn]{extarticle}
\usepackage{luatexja-fontspec}
\setmainfont{Latin Modern Roman}
\setmainjfont[Scale=1]{IPAexMincho}
\setsansjfont[Scale=1]{IPAexGothic}
\usepackage[left=18mm,right=18mm,top=18mm,bottom=24mm,columnsep=7mm,footskip=12mm]{geometry}
\usepackage{titlesec}
\usepackage{caption}
\usepackage{array}
\usepackage{flushend}
\renewcommand{\tablename}{表}
\renewcommand{\thetable}{\arabic{table}}
\makeatletter
\renewcommand\normalsize{\@setfontsize\normalsize{11bp}{14.5bp}}
\makeatother
\normalsize
\titleformat{\section}{\fontsize{11bp}{14.5bp}\selectfont\sffamily\gtfamily\bfseries}{\thesection}{.65em}{}
\titlespacing*{\section}{0pt}{5bp}{2bp}
\captionsetup{font=normalsize,skip=3bp,labelsep=quad}
\setlength{\parindent}{11bp}
\setlength{\parskip}{0pt}
\setlength{\tabcolsep}{3bp}
\setlength{\intextsep}{5bp}
\pagestyle{plain}
\raggedbottom
\hyphenpenalty=10000
\exhyphenpenalty=10000
\emergencystretch=1em
\begin{document}
\twocolumn[\begin{center}
{\fontsize{11bp}{14bp}\selectfont\sffamily\gtfamily\bfseries TITLE\par}
\vspace{4bp}
AUTHOR
\end{center}\vspace{4bp}]
'''
    out = [pre.replace('TITLE', escape(TITLE).replace('\n', r'\\')).replace('AUTHOR', AUTHOR)]
    refnum = 0
    for kind, text in BLOCKS:
        if kind == 'h':
            out.append(r'\section{' + text + '}')
        elif kind == 'p':
            if text.startswith('FとDの全体の救済数'):
                out.append(r'\clearpage')
            out.append(escape(text) + '\n')
        elif kind == 't':
            caption, headers, rr = TABLES[text]
            out.append(r'\begin{center}\begin{minipage}{\linewidth}\centering')
            out.append(r'\captionof{table}{' + caption + '}')
            out.append(r'\begin{tabular}{@{}l' + 'r' * (len(headers)-1) + r'@{}}\hline')
            out.append(' & '.join(headers) + r'\\\hline')
            for row in rr:
                out.append(' & '.join(map(escape, row)) + r'\\')
            out.append(r'\hline\end{tabular}\end{minipage}\end{center}')
        elif kind == 'ref':
            refnum += 1
            if refnum == 1:
                out.append(r'\section*{参考文献}')
            out.append(r'\noindent\hangindent=1.5em ［' + str(refnum) + '］' + escape(text) + '\n')
    out.append(r'\end{document}')
    (HERE / 'paper.tex').write_text('\n'.join(out) + '\n')


def font(run, size=11, bold=False):
    run.font.name = 'IPAexMincho'
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    rf = run._element.get_or_add_rPr().get_or_add_rFonts()
    for name in ['ascii', 'hAnsi', 'eastAsia', 'cs']:
        rf.set(qn('w:' + name), 'IPAexMincho')


def build_docx():
    d = Document()
    s = d.sections[0]
    s.page_width, s.page_height = Mm(210), Mm(297)
    s.left_margin = s.right_margin = Mm(18)
    s.top_margin, s.bottom_margin = Mm(18), Mm(24)
    s.footer_distance = Mm(12)
    st = d.styles['Normal']
    st.font.name, st.font.size = 'IPAexMincho', Pt(11)
    st.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), 'IPAexMincho')
    pf = st.paragraph_format
    pf.line_spacing, pf.space_after, pf.space_before = Pt(14.5), Pt(0), Pt(0)
    pf.widow_control = True
    # PAGE remains editable and updates after repagination.
    p = s.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    r = p.add_run('1')
    font(r)
    field.append(r._r)
    p._p.append(field)
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.line_spacing = Pt(14)
    font(p.add_run(TITLE), 11, True)
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    font(p.add_run(AUTHOR))
    s = d.add_section(WD_SECTION_START.CONTINUOUS)
    cols = s._sectPr.find(qn('w:cols'))
    cols.set(qn('w:num'), '2')
    cols.set(qn('w:space'), str(round(7 / 25.4 * 1440)))
    secnum = refnum = 0
    for kind, text in BLOCKS:
        if kind in ['h', 'p', 'ref']:
            p = d.add_paragraph()
            if kind == 'h':
                secnum += 1
                text = f'{secnum}　{text}'
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.space_before = Pt(5)
                p.paragraph_format.space_after = Pt(2)
            elif kind == 'p':
                if text.startswith('FとDの全体の救済数'):
                    p.paragraph_format.page_break_before = True
                p.paragraph_format.first_line_indent = Pt(11)
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            else:
                refnum += 1
                if refnum == 1:
                    r = p.add_run('参考文献')
                    font(r, 11, True)
                    p.paragraph_format.keep_with_next = True
                    p.paragraph_format.space_before = Pt(5)
                    p = d.add_paragraph()
                text = f'［{refnum}］{text}'
                p.paragraph_format.left_indent = Pt(15)
                p.paragraph_format.first_line_indent = Pt(-15)
            font(p.add_run(text), 11, kind == 'h')
        elif kind == 't':
            caption, headers, rr = TABLES[text]
            p = d.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.keep_with_next = True
            font(p.add_run(f'表{text+1}　{caption}'))
            t = d.add_table(rows=0, cols=len(headers))
            t.autofit = False
            widths = [33, 12, 12, 12, 14.5] if len(headers) == 5 else [19, 19, 19, 26.5]
            for c, w in zip(t.columns, widths):
                c.width = Mm(w)
            tw = t._tbl.tblPr.find(qn('w:tblW'))
            tw.set(qn('w:type'), 'dxa')
            tw.set(qn('w:w'), str(round(83.5 / 25.4 * 1440)))
            margins = OxmlElement('w:tblCellMar')
            for edge in ['top', 'bottom', 'left', 'right']:
                el = OxmlElement('w:' + edge)
                el.set(qn('w:w'), '0')
                el.set(qn('w:type'), 'dxa')
                margins.append(el)
            t._tbl.tblPr.append(margins)
            for i, row in enumerate([headers] + rr):
                tr = t.add_row()
                tr._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
                for j, (c, val, w) in enumerate(zip(tr.cells, row, widths)):
                    c.width = Mm(w)
                    p = c.paragraphs[0]
                    p.paragraph_format.keep_with_next = i != len(rr)
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.RIGHT
                    font(p.add_run(str(val)))
                    borders = OxmlElement('w:tcBorders')
                    for edge in (['top', 'bottom'] if i == 0 else ['bottom'] if i == len(rr) else []):
                        el = OxmlElement('w:' + edge)
                        el.set(qn('w:val'), 'single')
                        el.set(qn('w:sz'), '4')
                        borders.append(el)
                    c._tc.get_or_add_tcPr().append(borders)
    # End the two-column section continuously so Word balances its final page.
    s = d.add_section(WD_SECTION_START.CONTINUOUS)
    s._sectPr.find(qn('w:cols')).set(qn('w:num'), '1')
    d.core_properties.title = TITLE.replace('\n', '')
    d.core_properties.author = '伊藤 悠真'
    d.save(HERE / 'paper.docx')


if __name__ == '__main__':
    build_tex()
    build_docx()
    print('Generated paper.tex and paper.docx from the same text and frozen CSV tables.')
