# 実験結果（results）

実験IDごとに、保存設定・生成記録・集計表・検証レポートを保存するフォルダです。統合集計のフォルダには複数の出典をまとめた結果も含みます。

| ファイル | 内容 |
| --- | --- |
| `experiment_config.json` | 実際のモデル・タスク・seed・条件を記録した設定 |
| `raw.jsonl` | 生成コードと各roundの評価を含むローカル専用の記録。公開対象外 |
| `summary_by_*.csv` | モデル・条件・タスクなどの単位でまとめた集計表 |
| `manifest.json` | 出典・実行環境などの再現用情報 |
| `sanity_report.json` | 欠落・重複などの整合性検証 |
| `automation_report.json` | 自動公開に必要な検証の記録。プッシュの成功自体は表さない |

主要な保存先は次のとおりです。件数は予定した条件記録数です。

| フォルダ | 対象 |
| --- | --- |
| `shared_three_models_full_20261008T103231611899Z/` | 3モデル、seed 0〜9、1,500件 |
| `shared_five_models_full_20261010T041019864060Z/` | 5モデル、seed 10〜19、2,500件 |
| `shared_two_models_seed0_9_full_20261012T100658266051Z/` | 残る2モデル、seed 0〜9、1,000件 |
| `shared_five_models_pooled_seed0_19/` | 上記3出典の記述的統合集計、5,000件 |
| `*quick*` | 小規模な動作確認 |

保存フォルダの存在や予定件数だけでは、完了・検証済みとは判断できません。各保存設定・検証レポートを確認してください。評価器修正後の再評価や部分追試は [分析・再評価資料](../docs/analysis/README.md)、発表時点の数値は [固定出典](../docs/presentation_sources/README.md) を参照します。

公開する集計と検証記録は [公開ルール](../README.md#github公開時の注意) に従って選び、`raw.jsonl` や秘密情報を含めません。
