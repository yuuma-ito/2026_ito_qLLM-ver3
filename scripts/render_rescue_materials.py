"""Render sharing drafts from the fixed, verified reachable-path analysis (no API)."""
import json
import re
import shutil
from pathlib import Path
from scripts import analyze_verified_rescues as base
from scripts.analyze_reachable_rescue_history import OUT, progress
from harness.run_state import atomic_json, file_lock

ROOT=base.ROOT
FIXED=Path('docs/presentation_sources/20261016T_reachable_rescues')


def tex_table(caption,label,header,rows,columns):
    return '\n'.join([r'\begin{table}[tb]',r'\centering',r'\caption{'+caption+'}',
        r'\label{'+label+'}',r'\begin{tabular}{'+columns+'}',r'\hline',
        ' & '.join(header)+r' \\',r'\hline',*[' & '.join(map(str,row))+r' \\' for row in rows],
        r'\hline',r'\end{tabular}',r'\end{table}'])


def tables(snapshot,repair,overlap):
    names={'ollama:gemma3:4b':'G3','ollama:gemma4:e4b-it-qat':'G4',
           'ollama:qwen2.5-coder:7b':'C7','ollama:qwen3.5:4b':'Q4','ollama:qwen3.5:9b':'Q9'}
    result=[]
    errors={'build_error':'回路構築','import_error':'import','interface_mismatch':'IF不適合',
        'qubit_count_mismatch':'量子ビット数','syntax':'構文','unknown_error':'保存分類unknown','wrong_output':'出力不一致'}
    for grouping,field,caption,label,labels in [
        ('model','model_spec','モデル別の救済件数／率（分母は初期失敗）','tab:model',names),
        ('baseline_error','baseline_error_category','初期失敗類型別の救済件数','tab:error',errors)]:
        rows=[]
        for key,title in labels.items():
            selected={r['condition_id']:r for r in repair if r['scope']=='pooled' and r['grouping']==grouping and r[field]==key}
            n=int(selected[base.REPAIRS[0]]['initial_failures'])
            cells=[]
            for c in base.REPAIRS:
                r=selected[c];cells.append(f"{r['rescued']} ({100*float(r['rescue_rate']):.1f}\\%)" if grouping=='model' else r['rescued'])
            rows.append([title,n,*cells])
        result.append(tex_table(caption,label,['区分','分母','R','F','D'],rows,'lrrrr'))
    result.append(tex_table('F/Dの救済対象（初期失敗545組）','tab:overlap',
        ['共通','Fのみ','Dのみ','双方未救済'],[[140,43,40,322]],'rrrr'))
    rows=[]
    for c in base.REPAIRS:
        r=next(r for r in snapshot['overall_costs'] if r['condition_id']==c and r['cap']==3)
        rows.append([base.LABELS[c],f"{r['saved_prefix_tokens']/1000:.1f}",f"{r['new_suffix_tokens']/1000:.1f}",
            f"{r['tokens_per_rescue']:,.1f}",f"{r['seconds_per_rescue']:.1f}"])
    result.append(tex_table('修正追加コスト（未救済への消費も含む）','tab:cost',
        ['条件','保存$10^3$tok','新$10^3$tok','tok/救済','秒/救済'],rows,'lrrrr'))
    rows=[]
    for c in base.REPAIRS:
        r=next(r for r in snapshot['third_round'] if r['condition_id']==c)
        # Prefix/suffix components are retained in the fixed CSV, not hidden by totals.
        rows.append([base.LABELS[c],f"{r['additional_rescues']}/{r['at_risk_after_2']}",
            f"{r['third_round_tokens']/1000:.1f}",f"{r['third_round_seconds']/3600:.2f}",f"{100*r['loss_if_stop_at_2']:.1f}\\%"])
    result.append(tex_table('3回目の追加救済・消費と2回打切り時の損失','tab:third',
        ['条件','追加/未救済','千tok','要求時間h','失う割合'],rows,'lrrrr'))
    return '\n\n'.join(result)+'\n'


BODY=r'''
\section{背景と目的}
LLMによる量子回路コード生成では，importや回路構築の失敗に加え，実行可能でも指定した量子状態・測定分布を返さない場合がある．本研究の主題は，\textbf{介入によって初期失敗コードをどれだけ救済できるか}である．実行結果を与えること，自己見直し，自己デバッグで救済率と救済対象がどう異なるかを調べる．失敗類型・モデル・タスクに依存する適用範囲を記述し，介入カタログの根拠を整える．

Self-Refine\cite{selfrefine}とSelf-Debugging\cite{selfdebug}を背景に，本ハーネス内で修正条件を実装した．先行研究の完全再現ではない．課題仕様に沿った合理的な評価を共通手続きとして用い，介入による救済を主要指標とする．

\section{方法}
\subsection{対象と介入}
5モデル・10タスク・seed 0--19の1,000初期組を対象とし，各組5条件，計5,000条件記録を対応づける．Q4は\texttt{qwen3.5:4b}，G4は\texttt{gemma4:e4b-it-qat}，Q9は\texttt{qwen3.5:9b}，C7は\texttt{qwen2.5-coder:7b}，G3は\texttt{gemma3:4b}を表す．タグをモデル識別子として使い，数値を厳密なパラメータ数とはみなさない．

タスクはBell，GHZ，Deutsch--Jozsa（constant/balanced），Bernstein--Vazirani，Grover，QFT，IQFT，QPE，Ansatz．temperature 0.7，1要求の生成上限1,024 tokens，修正は最大3回とする．Bは初期生成，Rは自己見直し，Fはエラー等の実行結果提示，Dは説明・原因分析を促す自己デバッグ，Pは生成前注意事項である．BとR/F/Dは同じ初期コードと判定を共有し，成功時に停止する．Pは別プロンプトによる独立生成である．

\subsection{救済の定義と検証範囲}
L0はimport・必須関数の要件，L1は回路構築と評価処理の実行，L2は指定入力に対する期待出力との一致，主L3はこれらと構造要件への適合とする．構造要件は量子ビット数と測定以外の回路命令数の範囲であり，全入力のアルゴリズム同値性を保証しない．測定分布は8,192 shotsの全変動距離，状態ベクトルは大域位相を整合した距離を用い，0.05未満を出力一致とする．測定先を量子ビット順に戻す\texttt{evaluation\_policy\_v4}を採用した．救済率は
\[
 \frac{\text{初期失敗から最終主L3成功となった組数}}{\text{初期主L3失敗組数}}
\]
と定義する．失敗類型は介入前のBで固定し，修正後の分類で対象を選別しない．

\subsection{出典と到達経路}
元の保存設定は3モデル・seed 0--9（1,500条件記録），5モデル・seed 10--19（2,500），残り2モデル・seed 0--9（1,000）である．各設定・実験ID・schema・診断文処理差を固定manifestに保持する\cite{data}．現在の主経路は検証済み保存prefixと必要な新suffixの組合せで，停止判断やフィードバックに影響する部分追試293ケースを反映する．分岐後に到達できない旧保存suffixは除外する．全件を新評価で初回生成からやり直した実験ではない．

今回行ったのは保存済み結果の分析のみであり，追加生成や生成コードの再実行はない．5,000条件の対応，欠落・重複，成功時停止，共有初期，出典hashと到達コードhashを確認した．旧結果・保存コード再採点・部分追試は経路の由来であり，三つの独立した主結果として比較しない．旧120件は2モデル・seed 0--2・2条件・L2終了の既報で，再検証・合算しない．

\section{主要結果：初期失敗の救済}
1,000初期組中，初期成功455組，初期失敗545組だった．Rは96/545組（17.6\%），Fは183/545組（33.6\%），Dは180/545組（33.0\%）を救済した．R/F/Dの最終成功はそれぞれ551，638，635組であり，初期成功455組の無修正保持を含む．修正型の退行0は成功時停止の設計と合わせて解釈する．全体率は545組を分母にした合算値で，モデル率の単純平均ではない．

\input{../presentation_sources/20261016T_reachable_rescues/tables.tex}

\subsection{モデル・初期失敗類型別}
表\ref{tab:model}ではG4でF 48/62組，D 38/62組，Q4でF 78/162組，D 90/162組と大小が入れ替わる．C7は両条件23/65組で，G3はともに1/190組だった．各モデル200初期組のうち失敗した組だけが修正対象であり，異なる失敗分母を併記した．G3の190失敗組も全体分母に含まれる．

表\ref{tab:error}ではimport失敗に対してF 58/271組（21.4\%），D 72/271組（26.6\%），回路構築失敗に対してF 76/126組（60.3\%），D 68/126組（54.0\%）だった．出力不一致はF 24/65組，D 18/65組．類型の構成はモデル・タスクと関連するため，これだけで選択規則を確定しない．保存分類unknownの1組は原因確認記録を出典に持つ生成コード側の失敗で，API障害を意味しない．少数分母の率は参考値とする．

タスク別ではF/DはBell 10/34・12/34，GHZ 12/35・13/35，QFT 34/67・34/67，QPE 13/94・11/94だった．難度別のF/Dは易22/69・25/69，中79/225・79/225，難82/251・76/251．難度はハーネスの分類であり普遍的尺度ではない．全10タスク，モデル×タスク，初期失敗類型，元実験，seedブロックの分母と件数を固定CSVに残す．

\subsection{救済する対象の違いと83組の履歴}
表\ref{tab:overlap}の共通救済は140組，Fのみ43組，Dのみ40組，双方未救済322組だった．少なくとも一方が救済した223/545組（40.9\%）は，結果を見て選んだ集合であり，実行前の選択方策の成功率ではない．旧分析の片側各42組とは混同しない．

現行の片側救済83組すべてについて両条件166履歴・398修正遷移を静的確認した．import失敗はFのみ8組・Dのみ22組，回路構築失敗は19組・11組だった．救済側の到達履歴でimport/APIに関係する変更行はFのみ28/83組，Dのみ34/83組，回路構築・インターフェース関係は24/83組・32/83組，量子ゲート等のテキスト変更は38/83組・32/83組，測定・出力取得関係は11/83組・16/83組に認められた（重複可）．全83組を除外なく確認した結果である．

公開遷移CSVには前後round，コードhash，保存prefix/新suffixの由来，失敗分類の移動，既知API・ゲート名の出現数変化を記録した．例えばimport/APIや回路構築の修正と成功が同じ遷移に現れても，複数箇所が同時に変わるため救済原因を分離できない．静的変更分類は観察事実の注記であり，量子論理の訂正や因果的効果の証明ではない．失敗側の履歴・該当なしの例もCSVに含める．

\subsection{Pは独立生成として比較}
PはBの初期失敗に対応する成功124/545組（22.8\%）の一方，初期成功に対応する失敗106/455組（23.3\%）があり，最終成功473/1,000組だった．Bとの差18組は改善と悪化の双方を含む．同一コードを修正するR/F/Dの救済と同じ作用とは解釈しない．

\section{救済コストと3回目の寄与}
表\ref{tab:cost}は共有初期生成を除いた追加修正コストである．未救済例への消費も含む総入力＋出力tokensを救済数で割った．保存prefixの過去の記録値と，新suffixの部分追試時の実測値を分離した．Fの総追加tokensは1,708,086，Dは1,975,782，Rは1,809,845だった．未救済への消費はF 1,374,240，D 1,605,388，R 1,618,684 tokensを占める．

要求時間は保存された生成要求の\texttt{elapsed\_sec}の和で，評価時間や全工程時間ではない．経路の合計は再構成した計算値であり，全件新実験の実測コスト，実測の費用削減とは呼ばない．出典間の負荷・待機・再送処理差があり，金銭費用は未測定である．Pの1,000独立生成のコストは固定CSVで別扱いとする．

Fのround別救済は112，43，28組，Dは108，39，33組，Rは57，20，19組だった．表\ref{tab:third}の3回目では，Fは2回後未救済390組から28組（7.2\%），Dは398組から33組（8.3\%）を追加救済した．2回で区切ればFの155/183組，Dの147/180組を保持する一方，3回で救済できたうち15.3\%，18.3\%を失う．3回目の消費には最後まで失敗した例も含めた．

この比較は同じ最大3修正の観測履歴を区切った結果であり，上限別に独立実験した結果ではない．上限2/3のどちらかが一般的に最適とは断定しない．救済を失う割合と追加消費を並べ，対象タスクでの判断材料とする．

\section{考察・限界と次のアクション}
本対象ではFとDがRより多くの初期失敗を救済した．FとDの全体差は3組だが，片側救済83組が示すように救済対象は異なり，モデル・初期失敗類型で大小が変わる．この観測から一般的な介入の優劣や運用規則を確定しない．

共有初期，同一タスク・seedの依存，元実験のschema・診断文差があり，5,000条件を独立標本と扱わない．因果効果や統計的有意差は主張しない．指定入力・構造要件に限定した主L3，有限shotsと未固定の測定乱数，生成上限1,024 tokens，モデルdigest・量子化とサーバ負荷も限界である．保存prefixには完全な要求ログがない出典もある．静的差分だけでは複数変更の意味的寄与を分離できない．

次は介入選択・停止方策を事前固定し，別seed・タスクで検証する計画を立てる．意味的変更の人手確認，測定乱数・生成長・負荷への感度も検討する．今回の作業で新しい実験は行っていない．原稿・抄録・固定出典・検証結果を共有用に整えた段階であり，投稿は別途の指示による．

\begin{thebibliography}{9}
\bibitem{selfrefine} A. Madaan et al.: Self-Refine: Iterative Refinement with Self-Feedback, arXiv:2303.17651 (2023).
\bibitem{selfdebug} X. Chen et al.: Teaching Large Language Models to Self-Debug, arXiv:2304.05128 (2023).
\bibitem{data} 現行到達経路の固定集計・保存設定・出典hash（2026-10-16版）：両原稿READMEから固定出典のresults\_snapshot.jsonとsource\_manifest.jsonを参照．全対応記録，83組の全履歴，コストと3回目の集計，sanity/validation reportを収録．
\end{thebibliography}
'''


def refresh_report(snapshot):
    # Retain the user's existing main result and every auto block verbatim.
    start='<!-- reachable-rescues:20261016:start -->'
    end='<!-- reachable-rescues:20261016:end -->'
    text='''## 現行経路の全履歴・追加コスト（2026-10-16）

Fのみ43組・Dのみ40組の全83組、両条件166履歴・398修正遷移を確認した。分岐後の旧suffixを除外し、各record・round・コードhash・由来と静的変更を公開CSVで追跡できる。import/API、回路構築、量子論理、測定/出力取得の変更は観察注記であり、成功原因の認定ではない。

共有初期生成を除き未救済への消費も含む追加tokens/救済はR 18,852.6、F 9,333.8、D 10,976.6。生成要求秒/救済はR 911.1、F 444.2、D 553.6。保存prefixの記録値と新suffix実測値の合算は再構成経路の計算値であり、全件新実験の実測コストや実測の費用削減とは呼ばない。金銭費用は未測定。Pは独立生成として別集計。

3回目の追加救済はR 19/468組、F 28/390組、D 33/398組。3回目の追加tokensはR 559,141、F 491,676、D 588,970。2回で区切ると3回までに救済できたうちR 19.8%、F 15.3%、D 18.3%を失う。同一履歴の打切りであり、上限別独立実験でも一般的最適性の根拠でもない。

[全分析・再実行手順](analysis/reachable_rescues_20261016/README.md)、[考察](analysis/reachable_rescues_20261016/findings.md)、[固定発表出典](presentation_sources/20261016T_reachable_rescues/README.md)を参照。モデル・タスク/難度・初期失敗類型・元実験・seedブロックの分母を保持した。研究の主題は介入による救済であり、評価器比較ではない。旧数値は過去の記録として以下に保持する。
'''
    block=start+'\n'+text+end
    with file_lock(ROOT/'.cache/experiment_report.lock'):
        p=ROOT/'docs/experiment_report_draft.md'
        old=p.read_text()
        if start in old:
            updated=old[:old.index(start)]+block+old[old.index(end)+len(end):]
        else:
            anchor='<!-- intervention-rescues:20261015:end -->'
            if anchor not in old:raise ValueError('Missing primary section')
            updated=old.replace(anchor,anchor+'\n\n'+block,1)
        for original in re.findall(r'<!-- auto:[^>]+:start -->.*?<!-- auto:[^>]+:end -->',old,re.S):
            if original not in updated:raise ValueError('Auto block changed')
        tmp=p.with_suffix('.md.reachable.tmp');tmp.write_text(updated);tmp.replace(p)
        sp=ROOT/'docs/experiment_report_snapshot.json'
        d=json.loads(sp.read_text());d['primary_reachable_history']=dict(snapshot,analysis_dir=str(OUT),fixed_presentation_source=str(FIXED))
        atomic_json(sp,d)


def main():
    source=ROOT/OUT; fixed=ROOT/FIXED;fixed.mkdir(parents=True,exist_ok=True)
    snapshot=json.loads((source/'results_snapshot.json').read_text())
    # Copies are explicit public artifacts; no raw/cache files are copied.
    for name in ['results_snapshot.json','sanity_report.json','manifest.json','discordant_cases.csv',
                 'discordant_transitions.csv','discordant_summary.csv','cost_by_cap_and_stratum.csv',
                 'third_round_summary.csv','third_round_rescues.csv','findings.md']:
        shutil.copyfile(source/name,fixed/name)
    for name in ['repair_summary.csv','preventive_summary.csv','fd_overlap_summary.csv','paired_records.csv']:
        shutil.copyfile(source/'core'/name,fixed/name)
    repair=base.read_csv(source/'core/repair_summary.csv')
    overlap=base.read_csv(source/'core/fd_overlap_summary.csv')
    (fixed/'tables.tex').write_text(tables(snapshot,repair,overlap))
    (fixed/'README.md').write_text('''# 2026-10-16 現行救済経路の固定発表出典

5モデル・1,000初期組・5,000条件記録。初期成功455組・失敗545組。R96、F183、D180組救済。主結果は検証済み保存prefixと必要な新suffixを反映した現在の経路。集計時点はresults_snapshot.jsonのcaptured_at_utc（UTC）に記載。

[分析手順・設定差・限界](../../analysis/reachable_rescues_20261016/README.md)と[考察](findings.md)を参照。元3実験のID、保存設定hash、モデルdigest、seed範囲、ハーネス版はmanifest.jsonのsource_settingsへ固定。保存設定は各source_dir/experiment_config.json。prefix/suffix出典はmanifest.jsonのinputsにhashで記録し、私的raw/cacheの内容は収録しない。分析値は静的確認と到達経路の計算値で、全件新規実験ではない。

全83組の両条件166履歴と398修正遷移はdiscordant_cases.csv・discordant_transitions.csv。全分母はrepair_summary.csvとcost_by_cap_and_stratum.csv。費用単価未測定。Pは独立生成の別行。上限別集計は同一履歴の打切り。旧120件・旧固定5,000件は設定・評価時点を区別して保持し、混ぜない。

source_manifest.jsonは公開用コピー・スクリプト・原稿・PDFのhash、validation_report.jsonは関連テスト、本文/CSV一致、PDFビルドと目視検査の状態を記録する。生成コード・prompt本文・API応答・生例外文・秘密・rawを含まない。

再生成：`.venv/bin/python -m scripts.analyze_reachable_rescue_history`、続いて`.venv/bin/python -m scripts.render_rescue_materials`。これらは保存済み資料の読み取りと公開資料の作成のみ。PDFビルドは各資料READMEのコマンドによる。旧固定発表出典20261013T_*と10月14日検証記録は保持した。
''')
    refresh_report(snapshot)
    progress('段階5終了・段階6開始：継続レポート反映・発表原稿作成',
        ['83組の全履歴','救済コスト・3回目の寄与','新分析公開成果物','ロック下で継続レポートとsnapshot更新'],
        ['初期失敗545組、R96/F183/D180救済','2回で打切るとF15.3%・D18.3%の救済を失う'],
        ['発表資料更新','両PDFビルド','数値・目視・公開範囲検証'],[str(FIXED/'README.md')])
    abstract='量子回路コード生成の初期失敗を介入がどれだけ救済できるかを調べた。5モデル・10タスク・seed 0〜19の1,000初期組を対応づけ、検証済み保存prefixと必要な新suffixから現行経路を構成した。初期失敗545組に対し、自己見直しは96組、実行結果提示は183組、自己デバッグは180組を救済した。後二者の共通救済は140組、片側救済は43組と40組で、モデル・失敗類型により内訳が異なった。全83組の静的履歴、未救済を含む追加生成コスト、3回目の追加救済を整理した。経路再構成と共有初期・タスク・seed依存を限界として記し、一般的な優劣は断定しない。'
    (ROOT/'docs/winf2026/abstract.txt').write_text(abstract+'\n')
    for directory,author,affiliation in [('midterm2026','2023TC011 伊藤 悠真','指導教員：横山 哲郎'),
                ('winf2026','著者名（要確認）','所属（要確認）')]:
        p=ROOT/'docs'/directory
        header=r'''\documentclass[a4paper,8pt,twocolumn]{extarticle}
\usepackage{winf-paper}
\usepackage{type1cm}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath,amssymb}
\usepackage{url}
\renewcommand{\tablename}{表}
\title{Qiskit量子回路コードの初期失敗に対する\\修正介入の救済率と救済対象の分析}
'''
        opening='\n\\author{'+author+'}\n\\affiliation{'+affiliation+'}\n\\begin{document}\n\\maketitle\n\\thispagestyle{empty}\n'
        (p/'paper.tex').write_text(header+opening+BODY+'\n\\end{document}\n')
        report=f'''2026-10-16 進捗報告：初期失敗の救済を中心とした現行共有版

前回からの変更
旧評価の表を主要結果に用いた原稿から、検証済み保存prefixと必要な新suffixを反映した現在の到達経路を主結果とする原稿へ更新した。研究の中心は介入による初期失敗の救済とし、評価方法の整備と由来は方法節に記載した。旧固定資料は保持した。

完了した分析
1,000初期組（5,000条件記録）、初期成功455組・失敗545組を照合。R96/545（17.6%）、F183/545（33.6%）、D180/545（33.0%）救済。Pは独立生成で失敗からの成功124、成功に対応する失敗106、最終成功473。
F/D共通140組、Fのみ43組、Dのみ40組、双方未救済322組。片側全83組の両条件166履歴・398修正遷移を静的確認し、record・round・code hash・由来・既知API/ゲート名の変化を公開CSV化した。旧suffixを分岐後の経路へ流用しない。
共有初期を除き未救済消費も含む追加tokens/救済はR18,852.6、F9,333.8、D10,976.6。生成要求秒/救済はR911.1、F444.2、D553.6。保存prefixの記録値と新suffix実測値を分離した再構成経路の計算値であり、全件新実験の実測コストではない。金銭費用未測定。
3回目の追加救済はR19、F28、D33組。2回で区切ると3回までの救済のR19.8%、F15.3%、D18.3%を失う。上限別の独立実験ではなく、一般的最適性は断定しない。

資料と出典
{FIXED}/results_snapshot.json、source_manifest.json、validation_report.jsonを共通の固定出典とする。分析全表は{OUT}/。原稿・PDF・READMEと進捗報告を更新した。PDFのビルド・数値/引用/体裁の実施結果はvalidation_report_20261016.jsonへ記録する。

残る研究課題
複数変更の意味的寄与の分離、介入選択と停止方策の事前固定・別seed/タスクでの検証、生成長・負荷・測定乱数への感度。共有初期・タスク・seed依存と元3実験の設定/診断文差があり、因果効果や統計的有意差は主張しない。旧120件は合算しない。WiNFの著者・共著者・正式所属は要確認。

今回新しい実験・生成コード実行・評価仕様変更・通知設定変更・外部アップロード・学会投稿は行っていない。通知は親監視プロセスが担当する。
'''
        (p/'progress_report_draft.txt').write_text(report)
        (p/'README.md').write_text(f'''# {'中間発表' if directory=='midterm2026' else 'WiNF2026'}の現行共有版（2026-10-16）

研究の主題は初期失敗コードを介入がどれだけ救済できるか。主要結果は5モデルの現行到達経路：初期失敗545組にR96、F183、D180組救済。Fのみ43組・Dのみ40組の全83組を確認した。

- [paper.pdf](paper.pdf)：共有用PDF。
- [paper.tex](paper.tex)：編集用原稿。
- [進捗報告](progress_report_draft.txt)：前回からの変更・完了作業・残る課題。
'''+('- [和文抄録](abstract.txt)：独立した共有用ファイル。著者・共著者・正式所属は要確認。\n' if directory=='winf2026' else '\n既存原稿の著者・指導教員情報を維持した。\n')+f'''
[固定発表用スナップショット・全表・出典hash](../presentation_sources/20261016T_reachable_rescues/README.md)と[履歴・コスト分析](../analysis/reachable_rescues_20261016/README.md)を参照。集計UTCは固定snapshot内に記録。manifestには元実験ID・保存設定hash・schema・seedを保持した。

元3実験は3モデルseed 0〜9の1,500条件記録、5モデルseed 10〜19の2,500、残り2モデルseed 0〜9の1,000。合わせて1,000初期組・5,000条件記録。検証済み保存prefixと必要な新suffix（部分追試293ケース）を反映した現在の経路を主結果とし、全件新実験とは呼ばない。新主L3は指定入力の出力と所定の構造要件に限定され、全入力の同値性は保証しない。共有初期・タスク・seed依存があり、因果効果や統計的有意差は断定しない。

追加修正コストは共有初期生成を除外し未救済への消費も含む。prefix記録値とsuffix実測値の再構成計算で、実測の費用削減とは呼ばない。金銭費用は未測定。Pは独立生成。3回目の寄与は同じ履歴の打切り比較であり、上限別独立実験ではない。

旧120件は2モデル・seed 0〜2・2条件・L2終了の既報で、主結果へ合算しない。旧20261013T_*固定発表出典・results_snapshot_20261008.json・analysis_snapshot_20261014.json（WiNF）・旧検証記録はその時点の資料として保持する。旧F/D191や片側42/42は現行値と混ぜない。更新前の現行原稿はユーザー指定の.cache/overnight_rescues_20261016/beforeにも保存されている。

## ビルドと確認

このディレクトリでpLaTeX・dvipdfmx・IPAexフォントを用いる。スタイルファイルは変更しない。共通表は固定出典のtables.texから読み込む。

```bash
platex -interaction=nonstopmode -halt-on-error paper.tex
platex -interaction=nonstopmode -halt-on-error paper.tex
dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi
```

[今回の検証記録](validation_report_20261016.json)に関連テスト、本文/CSV一致、引用・参照、ページ数、フォント、はみ出し、ページ画像の目視確認を記録する。10月14日検証記録は当時の資料に対応する。本資料は共有用下書き。今回の作業では追加生成・生成コード再実行・通知・投稿・外部アップロードを行わない。
''')
    print('Rendered fixed sources, report and both sharing drafts.')


if __name__=='__main__':main()
