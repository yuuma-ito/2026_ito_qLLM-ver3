# 研究資料（docs）

実験の仕様書、継続更新レポート、発表原稿、分析結果と固定出典を保存するフォルダです。資料を読むときは以下の索引から、編集するときは各フォルダの README から元原稿・出典・ビルド方法を確認してください。

[リポジトリの説明](../README.md)・[フォルダ構成](../README.md#フォルダ構成)

## 資料を読む

| 用途 | 入口 | 時点の扱い |
| --- | --- | --- |
| 中間発表 | [midterm2026/README.md](midterm2026/README.md)・[PDF](midterm2026/paper.pdf) | 原稿に記載された固定出典に基づく共有版 |
| WiNF原稿 | [winf2026/README.md](winf2026/README.md)・[PDF](winf2026/paper.pdf) | 学会発表に向けた下書き |
| 継続更新レポート | [experiment_report_draft.md](experiment_report_draft.md)・[snapshot](experiment_report_snapshot.json) | 定期更新される。検証状態も確認する |
| 分析と再評価 | [analysis/README.md](analysis/README.md) | 旧判定の分析・評価器監査・再評価を分けて案内 |
| 以前の統合版の固定出典 | [20261013T_pooled_verified](presentation_sources/20261013T_pooled_verified/README.md) | 5,000件の統合集計を反映した時点を保持 |
| 現行の固定出典 | [20261016T_reachable_rescues](presentation_sources/20261016T_reachable_rescues/README.md) | 現行の中間発表・WiNF原稿が参照する出典 |
| 以前の固定出典 | [20261013T_levels_verified](presentation_sources/20261013T_levels_verified/README.md) | 過去の資料に対応する出典 |
| 完了時に自動作成した初版 | [completion_drafts/](completion_drafts/) | 保存先hash別の下書き。`reference/` は当時の参考資料 |

発表資料の `paper.tex` は元原稿、`paper.pdf` は共有用PDF、`progress_report_draft.txt` は進捗報告です。固定出典や過去の下書きは、現在の評価器による確定結果へ自動的に置き換わるものではありません。

## 方法・仕様を読む

- [ハーネス仕様](new_harness_spec.md)：条件・評価・保存形式。
- [プロンプト一覧](experiment_prompts.md)：共通指示・全タスク・条件別指示。
- [評価仕様と版の扱い](evaluator_readout.md)：出力表現と評価器の方針。
- [seed 0〜19の統合方針](seed0_19_integration.md)：出典間の設定・処理差。
- [APIヒントablationの設計メモ](exp4_api_hint_ablation_design.md)：現行ハーネスの実装対象外の設計。

`model_inventory_20261008.json`・`sf3_model_inventory_20261008.json` は当時のモデル情報、`*_classification.json`・`*_reclassification.json` は失敗分類の確認記録、`evaluator_readout_validation.json` は評価仕様の検証記録です。

## 元データを確認する

実験ごとの保存設定・集計CSV・検証レポートは [results の README](../results/README.md) を参照してください。発表原稿の数値の根拠は [presentation_sources](presentation_sources/README.md)、自動作成された初版の構成は [completion_drafts](completion_drafts/README.md) にまとめています。

## 今後ファイルを追加するとき

分析資料は `docs/analysis/<テーマ>_<日付>/`、発表用の固定出典は `docs/presentation_sources/<時点>/` にまとめ、それぞれの索引に用途を追加します。分析フォルダにはREADMEを置き、出典・評価器の版・検証状態・結論の適用範囲を書きます。

保存設定・実験ID・自動処理が参照するパス・固定出典のhashを保つため、既存の成果物は用途だけを理由に移動・改名しません。公開するファイルは[GitHub公開ルール](../README.md#github公開時の注意)に従い、`raw.jsonl`・秘密情報・仮想環境・キャッシュを含めません。
