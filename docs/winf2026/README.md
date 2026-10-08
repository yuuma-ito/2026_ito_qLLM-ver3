# WiNF2026 原稿下書き

公式のLaTeXテンプレートを使用した研究論文の下書き。検証済みの予備実験2回を中心とし、本実験は2026-10-08 19:42 JSTの[固定スナップショット](results_snapshot_20261008.json)に基づく途中経過として記載する。旧本実験の停止と、接続回復対策を適用した新しい本実験を区別する。

- `paper.tex`：編集用原稿。
- `paper.pdf`：ビルド済み原稿。
- `abstract.txt`：発表申込用の300字以内の和文抄録。
- `progress_report_draft.txt`：「前回からの進捗報告」の共有用下書き。
- `results_snapshot_20261008.json`：今回の原稿と進捗報告で使用した固定集計と出典。
- `winf-paper.sty`：公式配布ファイルの未変更コピー。
- `template-original.tex`：公式配布のサンプル原稿の未変更コピー。

## 公式要領の確認

2026-10-08に[公式トップページ](https://sites.google.com/view/winf2026/)と[発表申込ページ](https://sites.google.com/view/winf2026/submission)を確認した。

- 研究論文：A4、2段組、4ページ以内、カラー可、PDF 5MB以下。
- 発表申込用和文抄録：300字以内。
- 発表申込・論文投稿締切：2026-10-23（金）23:59。
- PDF提出先：発表申込受付の通知メールに記載されるアップロードリンク。
- 発表申込と別途、参加登録が必要。

[公式LaTeX配布アーカイブ](https://drive.google.com/file/d/1fcNbLwNtu926CVEjqUafEW9ArS20BZ8T/view?usp=drive_link)は `winf-paper.sty`、サンプルTeX、サンプルPDFを含む。スタイルのヘッダはversion 1.0（2015/09/15）だが、2026年の申込ページから指定されているファイルを使用した。

取得アーカイブのSHA-256：`c181db99e4833aa9bfb1f724336fc1646caca99516e298bd8d1fdbc3a979e92b`。
スタイルのSHA-256：`4dc0c47bdc9c61c7903734ad9068656f6cc11aa11391fe351713e3d23b73e86d`。

サンプルは `extarticle`、8pt、`twocolumn`、題名12pt、著者・所属10.5pt、ページ番号なし。スタイルは本文幅16.5cm、高さ23.3cm、段間0.8cm、行送り倍率1.25を設定する。寸法は配布スタイルの設定を維持した。

原稿では `extarticle` で未使用となる `a4j` を標準の `a4paper` に置き換え、PDF生成時もA4を明示した。`type1cm`、`fontenc`、`lmodern` で欧文の指定サイズとアクセントを扱う。表見出しを和文に設定し、日本語フォントはIPAexを埋め込む。公式スタイル自体は変更していない。

## ビルド

TeX LiveのpLaTeX、dvipdfmx、IPAexフォントを使用する。リポジトリのルートから以下を実行する。

```bash
cd docs/winf2026
platex -interaction=nonstopmode -halt-on-error paper.tex
platex -interaction=nonstopmode -halt-on-error paper.tex
dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi
```

## 数値の根拠と投稿前の残作業

2026-10-08の更新後の確認では、PDFはA4・2ページ・192,175 bytes、全フォント埋め込み済み。抄録は改行を除いて268字。予備実験の結果表6行を保存済みCSVと照合した。未解決の引用・参照と本文のはみ出しはなく、両ページの画像表示でも体裁を確認した。公式スタイルのSHA-256は変更前と一致する。

本文の方法は[既存レポート](../experiment_report_draft.md)、今回の途中経過は[発表用固定スナップショット](results_snapshot_20261008.json)に対応する。[継続更新されるスナップショット](../experiment_report_snapshot.json)は以後も件数が変わるため、今回の原稿の数値の出典としては固定集計を用いる。結果表は以下の保存済みCSVを照合した。予備実験のsanity reportとautomation reportは各実験ディレクトリに保存されている。

- `results/shared_three_models_quick_20261007T123904531170Z/summary_by_condition.csv`
- `results/shared_three_models_quick_20261007T123904532290Z/summary_by_condition.csv`
- 旧本実験：`results/shared_three_models_full_20261007T145103982885Z/`。1,500件記録、接続障害738件、未分類の評価エラー8件、検証失敗。L2成功376件・失敗1,124件は障害を含む暫定結果。
- 新しい本実験：`results/shared_three_models_full_20261008T103231611899Z/`。19:42時点で19/1,500件、L2成功9件・失敗10件、接続障害0件、未分類の評価エラー0件。実行中・未検証のため暫定結果。

投稿前に、著者名・共著者・正式所属のプレースホルダーを確定する。本実験が完了した場合は、API障害を切り分け、検証を終えた結果に基づいて本文・表・抄録を更新する。現状の予備結果からモデルの一般的な優劣や統計的有意差は主張しない。

今回の資料更新では追加のモデル生成を行っていない。進行中の本実験は継続し、19:42時点の既存記録を固定して原稿に反映した。共有用ファイルはこのディレクトリに保存する。学会への投稿は実施していない。
