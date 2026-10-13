# WiNF2026 原稿下書き

検証済み3モデル本実験と5モデル追加実験を出典別に報告する2026-10-13更新版。共有原稿の現行保存先をこのディレクトリに統一した。

- [paper.pdf](paper.pdf)：共有用PDF。
- [paper.tex](paper.tex)：編集用原稿。
- [abstract.txt](abstract.txt)：和文抄録（改行を除き247字）。
- [progress_report_draft.txt](progress_report_draft.txt)：進捗報告下書き。
- `winf-paper.sty`・`template-original.tex`：配布スタイル・サンプルの未変更コピー。

## 固定出典と検証状態

固定集計時点は2026-10-13 14:45:33 JST。[スナップショット](../presentation_sources/20261013T_pooled_verified/results_snapshot.json)、[詳細表とCSV案内](../presentation_sources/20261013T_pooled_verified/README.md)、[元ファイルのhash](../presentation_sources/20261013T_pooled_verified/source_manifest.json)を共通の出典とする。[継続更新レポート](../experiment_report_draft.md)の後日の数値と、原稿の固定時点を区別する。

| 分析 | 実験ID | モデル | seed | 件数 |
| --- | --- | ---: | --- | ---: |
| 主分析 | `shared_three_models_full_20261008T103231611899Z` | 3 | 0〜9 | 1,500 |
| 追加分析 | `shared_five_models_full_20261010T041019864060Z` | 5 | 10〜19 | 2,500 |
| 補完分析 | `shared_two_models_seed0_9_full_20261012T100658266051Z` | 2 | 0〜9 | 1,000 |
| 記述的統合集計 | `shared_five_models_pooled_seed0_19` | 5 | 0〜19 | 5,000 |

両実験とも全件記録、保存済みautomation成功、今回のsanity再検証成功を確認した。欠落・重複・予定外記録・条件対応欠落・共有初期不一致は0件、途中roundを含むAPI障害・timeout・未分類エラーも0件。介入カタログ3種類を全件から再計算した値と照合した。追加実験の旧分母137件は修正済みで、baseline L2失敗288件と一致する。旧固定資料は当時の状態を保持する。

L2・L3達成は主分析839件、追加分析1,242件で、全モデル・条件の件数が一致する。累積達成の単調性、排他的な5区分の合計、対応付き5×5遷移の分母を確認した。初期成功で修正しなかった例を、介入による救出から分けた。Pは別プロンプトからの独立生成として扱う。

補完実験の1,000件も再検証成功。statevector未保存での取得1件は生成コード側の `exec / interface_mismatch` へ再分類し、生データ・評価値は保持した。[分類確認記録](../qpe_seed2_failure_classification.json)を保存した。統合は各モデル1,000件、計5,000件、L2・L3成功2,457件。全件照合とカタログ照合は成功した。実行時ハーネス版とエラー分類が診断文に影響するため、統合値は混合手順の記述的結果であり、出典別内訳を保持する。

## 過去資料との区別

- [2026-10-08の固定集計](results_snapshot_20261008.json)は旧途中経過の記録として保持し、現行原稿の全件結果の出典には用いない。
- 旧120件は2モデル・seed 0〜2・2条件・L2終了の既報。23/30→24/30と0/30は参照原稿による値で、今回は生データから再検証していない。
- 各60件の簡易実験2回は予備検証。接続障害738件を含む旧1,500件は検証不合格の除外資料であり、主分析に混ぜない。
- [完了後の初版下書き](../completion_drafts/9b253632951b3656d9a72a97/)とそのreference・出典は保持した。旧「カタログ不整合」の説明は当時の状態で、現行原稿では修正後の出典を用いる。

## 評価の読み方

L0〜L3は独立した点数ではなく累積的な到達水準。各達成率は同じ評価対象の全件数を分母とする。未達／L0のみ／L1まで／L2まで／L3の5区分は排他的で、合計が全件数になる。段階上昇・維持・低下は順序カテゴリの比較であり、段階差を等間隔の点数として平均しない。部分改善は上昇したもののL3未達の例で、上昇件数の内数である。

構造検証は量子ビット数と測定操作を除いた回路命令数の範囲に限る。10タスクでは古典ビット数・測定数・測定の必須／禁止は未指定。全入力での正しさ、ゲート種、深さ、最適性を完全には検証しない。タスク定義は各実行時コミットと一致することを確認した。統計的有意差やモデルの一般的優劣は断定しない。

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


## ビルドと確認

TeX LiveのpLaTeX、dvipdfmx、IPAexフォントを使用する。表の共通TeXは[../presentation_sources/20261013T_pooled_verified/reach_tables.tex](../presentation_sources/20261013T_pooled_verified/reach_tables.tex)に固定した。リポジトリの構造を保ってビルドする。

```bash
platex -interaction=nonstopmode -halt-on-error paper.tex
platex -interaction=nonstopmode -halt-on-error paper.tex
dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi
```

両原稿をA4・4ページでビルドした。フォント埋め込み、引用・参照、欠落文字、本文のはみ出し、全ページの体裁と表の数値を確認した。確認結果は[validation_report.json](../presentation_sources/20261013T_pooled_verified/validation_report.json)に保存する。スタイルは未変更で、SHA-256は `4dc0c47bdc9c61c7903734ad9068656f6cc11aa11391fe351713e3d23b73e86d`。

今回の作業は保存済み評価の集計と資料更新であり、モデルの追加生成・生成コードの再評価・投稿・通知は行っていない。

## 投稿前の残作業

著者・共著者・正式所属の要確認表示は維持した。投稿要領の情報は上記の2026-10-08確認記録であり、今回改めて外部確認していない。投稿前に最新要領と著者情報を確認する。学会への投稿は別途指示を受ける。
