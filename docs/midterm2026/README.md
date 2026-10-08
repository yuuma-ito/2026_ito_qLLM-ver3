# 中間発表原稿の進捗更新版

研究題目は「量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究」。2023TC011 伊藤 悠真、指導教員：横山 哲郎。ユーザーが提示した中間発表原稿の本文を基に、7章構成と既報の120件を残して、その後の進捗を追記した。

- [paper.tex](paper.tex)：更新したTeX原稿。
- [paper.pdf](paper.pdf)：共有用PDF。
- [progress_report_draft.txt](progress_report_draft.txt)：前回の中間発表からの進捗報告下書き。
- [results_snapshot_20261008.json](results_snapshot_20261008.json)：原稿で使用した固定集計と出典区分。
- `winf-paper.sty`：リポジトリ内の検証済みスタイルの未変更コピー。

先に作成した `docs/winf2026/` の論文下書きと分けて保存している。今回の中間発表資料の共有には、このディレクトリのPDF・TeX・進捗報告を使用する。

## 更新内容

中間発表時の2モデル・baseline／Self-Refineの比較を既報として保持し、SF3上の3モデル、5条件の比較、実験と検証後の自動commit／push、定期進捗通知、接続回復処理を追記した。原稿の重複文とページ抽出時の改行・断片を整理した。

旧説明の「L3＝構造」と現行実装の「L3＝L0・L1・L2・structure_matchの総合成功」を区別し、旧L2終了と現行L3終了の違いも記載した。指標・モデル・seedが異なる実験は合算しない。失敗類型別の介入カタログは今後の分析成果とし、完成したとは記載していない。

## 結果の出典と検証状態

中間発表時の120件、Qwenの23/30から24/30、Gemmaの0/30は、今回提示された原稿による既報である。この作業では旧実験の生データによる再検証は行っていない。固定スナップショットの `legacy_presentation.revalidated_from_raw` は `false` として区別している。

その後の各60件の簡易実験2回は、次の保存済みCSV、sanity report、automation reportと照合した。これらの結果は検証済みである。

- `results/shared_three_models_quick_20261007T123904531170Z/`
- `results/shared_three_models_quick_20261007T123904532290Z/`

旧本実験は `results/shared_three_models_full_20261007T145103982885Z/`。1,500件記録、接続障害738件、未分類の評価エラー8件があり検証失敗。L2成功376件・失敗1,124件は障害を含む暫定値である。

新しい本実験は `results/shared_three_models_full_20261008T103231611899Z/`。2026-10-08 19:42 JSTの固定集計は19/1,500件、L2成功9件・失敗10件、接続障害0件、未分類エラー0件。実行中・未検証であり、最終的な比較結果として扱わない。以後の件数は変化するため、原稿の数値はこの固定時点に限る。

公開用スナップショットには件数、設定、出典、読み取り時の生データhashを保存し、生成コード・エラー本文・認証情報を含めない。

## 参考文献の整理

HumanEvalには[Chenらの論文](https://arxiv.org/abs/2107.03374)、MBPPには別途[Austinらの論文](https://arxiv.org/abs/2108.07732)を対応させた。自己修正の限界に関する[Huangらの論文](https://arxiv.org/abs/2310.01798)は、外部フィードバックを用いない推論の自己修正を対象とするため、量子コードや実行フィードバック一般への断定には用いない。

関連研究として[Self-Refine](https://arxiv.org/abs/2303.17651)、[Qiskit](https://arxiv.org/abs/2405.08810)、[Qiskit HumanEvalの公式リポジトリ](https://github.com/qiskit-community/qiskit-human-eval)も確認した。本実験の独自10タスクをQiskit HumanEvalそのものとして扱わない。参考文献番号は追加文献に合わせて更新している。

## ビルドと確認

TeX LiveのpLaTeX、dvipdfmx、IPAexフォントを使用する。

```bash
cd docs/midterm2026
platex -interaction=nonstopmode -halt-on-error paper.tex
platex -interaction=nonstopmode -halt-on-error paper.tex
dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi
```

更新PDFはA4・2ページ・187,190 bytes。全フォントを埋め込み、未解決の引用・参照と本文のはみ出しがないこと、両ページの画像表示による体裁を確認した。スタイルのSHA-256は `4dc0c47bdc9c61c7903734ad9068656f6cc11aa11391fe351713e3d23b73e86d` で、既存コピーと一致する。

今回の資料更新では追加のモデル生成を行わず、進行中の本実験を継続している。共有用資料をローカルに保存し、学会への投稿は行っていない。
