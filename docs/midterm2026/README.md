# 卒業論文最終要旨・中間発表の現行共有版（2026-10-22 B4反映版）

題目：**量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究**．要旨本文は「はじめに」「評価の枠組み」「関連研究・準備」「実験方法」「結果」「考察」「おわりに」の7章に改稿した．中間発表の構成・説明の流れはユーザーの文章による説明を参考にし，旧PDFの提出は求めていない．R/F/Dの主結果は2026-10-16版，B4は2026-10-22固定の検証済み集計を使用し，旧L2評価120件の結果を合算していない．

初見の読者向けに表現を見直し，初期L3未達の組数を「初期失敗数」，その後のL3成功を「追加成功」と定義した．R/F/Dの追加成功は修正による救済，B4は独立再生成による成功として区別する．表1・2は追加成功数を示す見出しとし，B/R/F/D/Pの5条件5,000件と追加対照B4の別実験を明記した．追加計算コストは生成要求数・tokensによる指標であり，金銭費用とは区別する．表のIF不適合は幅の制約から略記を維持し，本文でインターフェースと定義した．

表2の旧unknown 1組は，[原因確認記録](../analysis/reevaluation_followup_20261015/unknown_failure_triage.csv)のbaseline（Q4，T3a_DJ_constant，seed 19）で確認された未定義変数simのNameErrorに基づき，「実行時エラー（未定義変数）」に分類した．表中は「実行時」と略記し，本文で定義する．保存済みCSVの`unknown_error`との対応を維持し，元データ・成功判定・件数は変更しない．この表示分類は当該1組を対象とし，他のunknown_errorには一括適用しない．

独立再生成B4（`independent_4_full_20261020T185811381595Z`）の全1,000組完了を受け，2026-10-22に結果・モデル別／初期失敗類型別表・考察・結論を更新した．初期失敗545組中217組（39.8%）が成功し，最終成功672/1,000組（67.2%）．追加1,342要求・995,815 tokens，追加tokens／追加成功4,589.0．[固定集計・保存設定・出典hash](../analysis/independent_4_completed_20261022/source_manifest.json)に基づく．B4とR/F/Dは初回込み最大4回だが，入力情報・seed規則・実行時期・出典schemaが異なり，因果効果や一般的優劣は断定しない．既存5,000条件とB4の1,000組は区別する．

**フォント指定の更新：Wordは見出しを「ＭＳ Ｐゴシック」，本文を「ＭＳ Ｐ明朝」，英数字を「Times New Roman」に設定した．** 題目と参考文献見出しも見出し用フォント，表・キャプション・著者情報は本文用フォントを用いる．英数字のフォントは見出し・本文とも共通である．サーバーには指定3フォントが存在しないため，現在のPDFは代替フォントによる確認版である．LaTeX原稿は指定フォントを優先し，不足時はIPAPMincho・IPAPGothic・Nimbus Romanで代替して警告する．指定フォントを備えた環境でPDFを再生成し，2ページとフォント埋込みを再検証するまで，フォント規定を満たした最終PDFとは扱わない．Wordの変換時にもフォント置換が発生し，実際の使用フォントを検証記録へ保存する．

背景ではHumanEval・MBPP，生成コードの誤り，量子状態・測定分布の検証の必要性を順に説明した．関連研究はSelf-Refine・Self-Debugging・自己修正の限界・Qiskit HumanEvalを短く整理した．文献の著者・題名・年・要旨は原論文のarXiv公開ページで確認し，[確認記録](bibliography_sources.json)に根拠と本文で用いた範囲を記録した．Qiskit HumanEvalを本研究の10タスクの出典として扱わない．

評価の定義は`harness/evaluator.py`と固定追試の評価設定を照合した．L0を構文だけの判定とはせず，import・必須関数への適合も含めた．構造命令数は測定とbarrierを除く．現行実装と固定追試設定の測定・変換seedは42であり，旧稿の「未固定の測定乱数」という記述は削除した．有限shots・指定入力・構造要件の限界は保持した．

要旨はA4縦・2ページ，左右18mm，上18mm，下24mm，題目と著者情報は1段，本文は2段とした．本文・表・参考文献は11pt，両ページにページ番号を付けた．日本語の句読点は「，」「．」を使用し，表1〜3のキャプションは上に置いた．図は使用していない．PDFはLuaLaTeXから生成した．Wordも同じ文章・固定CSVから生成し，LibreOfficeでのPDF変換により2ページとレイアウトを確認した．Wordで編集後はフォントと改ページを再確認する．

研究の主題は初期失敗コードを介入がどれだけ救済できるか。主要結果は5モデルの現行到達経路：初期失敗545組にR96、F183、D180組救済。Fのみ43組・Dのみ40組の全83組を確認した。

- [paper.pdf](paper.pdf)：代替フォントによる確認用PDF．
- [paper.docx](paper.docx)：編集用Word原稿．
- [paper.tex](paper.tex)：編集用LaTeX原稿．
- [今回の更新内容](revision_notes_20261022.md)・[今回の検証記録](validation_report_20261022.json)：指定書式，全文と数値の照合結果．
- [進捗報告](progress_report_draft.txt)：前回からの変更・完了作業・残る課題。
- [6分用の仮スライドPDF](slides/slides.pdf)：本編8枚＋質疑用補足3枚。固定済みの現行集計に基づく。
- [スライドの編集用TeX](slides/slides.tex)・[6分用発表メモ](slides/speaker_notes.txt)：各ページの目安時間と質疑の要点。

スライドはリポジトリ直下から `.venv/bin/python docs/midterm2026/slides/build.py` でビルドする。固定CSVからグラフ・モデル別表・コスト値を取り込み、数値照合、11ページ、文字欠け・はみ出し、フォント埋め込みを確認する。中間ファイルは `.cache/midterm_slides_20261016/`、出典と成果物hashは [スライド検証記録](slides/validation_report.json) に保存する。ビルド直後の目視確認状態は未確認になるので、配布前に画像化して確認する。6分は発表メモ上の配分であり、実際の発表速度はリハーサルで調整する。

既存原稿の著者・指導教員情報を維持した。

[固定発表用スナップショット・全表・出典hash](../presentation_sources/20261016T_reachable_rescues/README.md)と[履歴・コスト分析](../analysis/reachable_rescues_20261016/README.md)を参照。集計UTCは固定snapshot内に記録。manifestには元実験ID・保存設定hash・schema・seedを保持した。

元3実験は3モデルseed 0〜9の1,500条件記録、5モデルseed 10〜19の2,500、残り2モデルseed 0〜9の1,000。合わせて1,000初期組・5,000条件記録。検証済み保存prefixと必要な新suffix（部分追試293ケース）を反映した現在の経路を主結果とし、全件新実験とは呼ばない。新L3は指定入力の出力と所定の構造要件に限定され、全入力の同値性は保証しない。共有初期・タスク・seed依存があり、因果効果や統計的有意差は断定しない。

追加修正コストは共有初期生成を除外し未救済への消費も含む。prefix記録値とsuffix実測値の再構成計算で、実測の費用削減とは呼ばない。金銭費用は未測定。Pは独立生成。3回目の寄与は同じ履歴の打切り比較であり、上限別独立実験ではない。

旧120件は2モデル・seed 0〜2・2条件・L2終了の既報で、主結果へ合算しない。旧20261013T_*固定発表出典・results_snapshot_20261008.json・analysis_snapshot_20261014.json（WiNF）・旧検証記録はその時点の資料として保持する。旧F/D191や片側42/42は現行値と混ぜない。更新前の現行原稿はユーザー指定の.cache/overnight_rescues_20261016/beforeにも保存されている。

## ビルドと確認

リポジトリ直下で以下を実行する．LuaLaTeX・IPAexフォント・python-docx・PyMuPDF・NumPyを使用する．[build_abstract.py](build_abstract.py)は共通の文章と固定CSVからTeX・Wordを生成するため，原稿を更新する場合はこのスクリプトの本文を編集する．旧WiNF用スタイルと共有表のファイルは保持し，この要旨からは読み込まない．中間ファイルとフォントキャッシュは`.cache/midterm_abstract_20261021/`に置く．

```bash
PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/midterm2026/build_abstract.py
mkdir -p .cache/midterm_abstract_20261021
TEXMFVAR="$PWD/.cache/midterm_abstract_20261021/texmf" lualatex -interaction=nonstopmode -halt-on-error -output-directory=.cache/midterm_abstract_20261021 docs/midterm2026/paper.tex
TEXMFVAR="$PWD/.cache/midterm_abstract_20261021/texmf" lualatex -interaction=nonstopmode -halt-on-error -output-directory=.cache/midterm_abstract_20261021 docs/midterm2026/paper.tex
cp .cache/midterm_abstract_20261021/paper.pdf docs/midterm2026/paper.pdf
libreoffice --headless --convert-to pdf --outdir .cache/midterm_abstract_20261021/word docs/midterm2026/paper.docx
PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/midterm2026/validate_abstract.py
```

この環境のLibreOfficeは`.cache/graduation_office/root/usr/lib/libreoffice/program/soffice.bin`にあり，既存の[変換処理](../graduation2026/convert_thesis.py)と同じ共有ライブラリ設定で使用した．Word変換PDFは検証用キャッシュであり，配布用`paper.pdf`はLaTeX出力である．

[検証スクリプト](validate_abstract.py)は両PDFのページ数・用紙・実際の文字サイズ・白黒・ページ番号・全段落と参考文献の欠落・表と固定CSVの一致・フォント埋込みを確認する．余白はTeX/Wordの設定に加え，216dpiの印字領域で確認する（全角括弧の空白を含むフォント矩形と実際の印字は区別する）．[画像確認記録](visual_review_20261022.json)はAIが確認した両PDFのhashに対応する．10月14日・16日の検証記録は改稿前の資料として保持する．今回，追加実験・通知・投稿は行っていない．要旨修正の関連ファイルのコミット・プッシュはユーザーの指示に従う．

Word変換の検証用PDFは `PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/graduation2026/convert_thesis.py --abstract-preview` で再生成できる．卒論側の `abstract.docx` / `abstract.pdf` は本要旨と同じ最新版を配置した．スライドは今回の更新対象外であり，従来のR/F/D集計版を保持する．
