# 中間発表の現行共有版（2026-10-16）

研究の主題は初期失敗コードを介入がどれだけ救済できるか。主要結果は5モデルの現行到達経路：初期失敗545組にR96、F183、D180組救済。Fのみ43組・Dのみ40組の全83組を確認した。

- [paper.pdf](paper.pdf)：共有用PDF。
- [paper.tex](paper.tex)：編集用原稿。
- [進捗報告](progress_report_draft.txt)：前回からの変更・完了作業・残る課題。
- [6分用の仮スライドPDF](slides/slides.pdf)：本編8枚＋質疑用補足3枚。固定済みの現行集計に基づく。
- [スライドの編集用TeX](slides/slides.tex)・[6分用発表メモ](slides/speaker_notes.txt)：各ページの目安時間と質疑の要点。

スライドはリポジトリ直下から `.venv/bin/python docs/midterm2026/slides/build.py` でビルドする。固定CSVからグラフ・モデル別表・コスト値を取り込み、数値照合、11ページ、文字欠け・はみ出し、フォント埋め込みを確認する。中間ファイルは `.cache/midterm_slides_20261016/`、出典と成果物hashは [スライド検証記録](slides/validation_report.json) に保存する。ビルド直後の目視確認状態は未確認になるので、配布前に画像化して確認する。6分は発表メモ上の配分であり、実際の発表速度はリハーサルで調整する。

既存原稿の著者・指導教員情報を維持した。

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
