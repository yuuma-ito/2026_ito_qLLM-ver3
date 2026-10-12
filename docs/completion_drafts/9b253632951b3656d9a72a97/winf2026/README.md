# WiNF2026更新版下書き

固定出典は[results_snapshot.json](../results_snapshot.json)、集計時点は2026-10-12 08:25:03 UTC（17:25:03 JST）。reference/を保持して作成した更新版。

- [paper.pdf](paper.pdf)：共有用PDF。
- [paper.tex](paper.tex)：編集用本文（結果表を含む）。
- [progress_report_draft.txt](progress_report_draft.txt)：前回からの変更、完了作業、課題、次のアクション。
- [abstract.txt](abstract.txt)：300字以内の和文抄録。

## 出典と検証状態

主分析は`shared_three_models_full_20261008T103231611899Z`（3モデル・seed 0〜9・1,500件）、追加分析は`shared_five_models_full_20261010T041019864060Z`（5モデル・seed 10〜19・2,500件）。保存設定は元リポジトリの`results/<実験ID>/experiment_config.json`。設定差があるため合算しない。

両者の全件記録、sanity・automation成功を確認し、モデル・条件別CSVとL2/L3件数を固定スナップショットと照合した。欠落・重複・予定外・条件対応欠落・共有初期不一致は0件、固定集計のAPI障害記録・保存CSVのtimeout・最終未分類エラーは0件。

ただし追加実験の介入カタログCSVはbaseline失敗分母137件で固定集計288件と不一致。追加分析の失敗類型別救出・退行は未確定として、その表を本稿に採用しない。主分析のカタログ分母161件は固定集計と一致。実験がreadyであることと派生カタログの不整合を区別する。

旧120件はreferenceの既報（生データ再検証なし）、各60件2回は予備検証、API障害738件を含む旧本実験は除外資料とした。古い19件の途中値を全件結果へ更新した。統計的有意差・モデルの一般的優劣は断定していない。

出典CSV・設定・検証報告の固定コピーは[../sources/](../sources/)、元パスとSHA-256、数値照合結果は[source_manifest.json](../sources/source_manifest.json)。カタログの不整合も保存した。生成コード・raw.jsonl・秘密情報を含めない。

## ビルドと検証

```bash
platex -interaction=nonstopmode -halt-on-error paper.tex
platex -interaction=nonstopmode -halt-on-error paper.tex
dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi
```

`winf-paper.sty`は既存の未変更コピーを使用。引用文献は参照原稿に基づき、今回新たな関連研究や投稿規則の確認は行っていない。ビルド・フォント・体裁・数値の確認結果は[validation_report.json](../validation_report.json)に記録する。

WiNF原稿の著者・共著者・正式所属の要確認表示は維持した。投稿要領の最新確認と投稿は別作業。今回、生成コード実行・追加実験・投稿・通知・Git操作は行わず、共有は起動スクリプトが担当する。

最終検証：A4・2ページ・188,387 bytes。全フォント埋め込み、未解決引用・参照0、欠落文字0、はみ出し0。全ページ画像表示を確認し、モデル・条件表8行をPDFと固定集計で照合した。Underfullの余白警告5件は目視確認済み。抄録は258字。
