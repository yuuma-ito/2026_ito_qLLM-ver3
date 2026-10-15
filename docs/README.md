# リポジトリの案内

<!-- reachable-rescues:20261016 -->
現行共有版は[2026-10-16固定出典](presentation_sources/20261016T_reachable_rescues/README.md)に基づく[中間発表](midterm2026/README.md)・[WiNF下書き](winf2026/README.md)。初期失敗545組からのR96/F183/D180救済を主結果に更新。下記の旧紹介は当時の資料として参照する。


[トップのREADME](../README.md)は操作手順、このページはファイルの置き場所の案内です。

## 全体の構成

| 場所 | 何が入っているか | 主に見る・変更する場面 |
| --- | --- | --- |
| [configs/](../configs/README.md) | 実験・統合・定期実行の設定 | モデル・seed・条件を選ぶ |
| [scripts/](../scripts/README.md) | 実行・検証・集計・通知の入口 | コマンドを選ぶ |
| [harness/](../harness/) | LLM接続、実験制御、コード抽出、L0〜L3評価、隔離実行 | 実験処理や評価器を修正する |
| [tasks/](../tasks/) | 10種類の量子回路タスクと期待値 | タスクの定義を確認する |
| [prompts/](../prompts/) | 共通指示・予防的仕様のプロンプト | モデルへの指示を確認する |
| [tests/](../tests/) | ハーネス・集計・運用処理のテスト | 変更を検証する |
| [results/](../results/) | 実験IDごとの保存設定・記録・集計・検証結果 | 数値の元データを確認する |
| [docs/](./) | 仕様、レポート、発表原稿、分析資料 | 結果や方法を読む |
| [experiments/](../experiments/) | 従来の介入比較設定 `intervention_compare_v2.json` | 旧設定を参照する。今後の標準設定は `configs/` |
| [findings.md](../findings.md) | 2026年6月からの旧実験の知見メモ | 研究の経緯を確認する |
| [AGENTS.md](../AGENTS.md)・[CLAUDE.md](../CLAUDE.md) | AI作業者向けの指示・背景情報 | AIによる作業ルールを確認する |
| [requirements.txt](../requirements.txt)・[.env.example](../.env.example) | Python依存関係・環境設定のひな形 | 環境を準備する |

ローカル専用の `logs/` は実行ログ、`.cache/` はロック・checkpoint・ジョブ状態、`.venv/` はPython環境、`.pytest_cache/`・`__pycache__/` はキャッシュです。`.env` は接続設定などを置く非公開ファイルです。`.git/` はGit自身の管理情報です。これらは通常、研究資料として読む場所ではありません。特に実行中のログ・ロック・checkpointは処理の継続に使います。

## 資料を読む

| 用途 | 入口 | 時点の扱い |
| --- | --- | --- |
| 中間発表 | [midterm2026/README.md](midterm2026/README.md)・[PDF](midterm2026/paper.pdf) | 原稿に記載された固定出典に基づく共有版 |
| WiNF原稿 | [winf2026/README.md](winf2026/README.md)・[PDF](winf2026/paper.pdf) | 学会発表に向けた下書き |
| 継続更新レポート | [experiment_report_draft.md](experiment_report_draft.md)・[snapshot](experiment_report_snapshot.json) | 定期更新される。検証状態も確認する |
| 分析と再評価 | [analysis/README.md](analysis/README.md) | 旧判定の分析・評価器監査・再評価を分けて案内 |
| 発表資料の固定出典 | [20261013T_pooled_verified](presentation_sources/20261013T_pooled_verified/README.md) | 5,000件の統合集計を反映した時点を保持 |
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

## 実験結果の置き場所

| 保存先（`results/` 以下） | 用途 |
| --- | --- |
| `shared_three_models_full_20261008T103231611899Z/` | 3モデル本実験、seed 0〜9、予定1,500件 |
| `shared_five_models_full_20261010T041019864060Z/` | 5モデル追加本実験、seed 10〜19、予定2,500件 |
| `shared_two_models_seed0_9_full_20261012T100658266051Z/` | 残る2モデルのseed 0〜9補完、予定1,000件 |
| `shared_five_models_pooled_seed0_19/` | 上記3出典の記述的統合集計、予定5,000件 |
| `*quick*` | 小規模な動作確認の結果 |
| その他の実験ID | 過去の実行記録。各保存設定と検証記録で用途を確認 |

予定件数は結果の検証済み件数を意味しません。各実験の `experiment_config.json` を設定の根拠とし、`sanity_report.json`・`automation_report.json` とレポートを合わせて確認します。`summary_by_*.csv` は集計表、`manifest.json` は出典・環境の記録です。詳細は[結果ファイルの説明](../README.md#実験結果集計)を参照してください。

## 今後ファイルを追加するとき

設定は `configs/`、実行処理は `scripts/`、分析資料は `docs/analysis/<テーマ>_<日付>/`、発表用の固定出典は `docs/presentation_sources/<時点>/` にまとめ、それぞれの索引に用途を追加します。分析フォルダにはREADMEを置き、出典・評価器の版・検証状態・結論の適用範囲を書きます。

保存設定・実験ID・自動処理が参照するパス・固定出典のhashを保つため、既存の成果物は用途だけを理由に移動・改名しません。公開するファイルは[GitHub公開ルール](../README.md#github公開時の注意)に従い、`raw.jsonl`・秘密情報・仮想環境・キャッシュを含めません。
