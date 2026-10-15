# スクリプトの索引

<!-- reachable-rescues:20261016 -->
[analyze_reachable_rescue_history.py](analyze_reachable_rescue_history.py)：現行経路の全83組・追加コスト・3回目を保存資料から再集計。[render_rescue_materials.py](render_rescue_materials.py)：固定出典・継続レポート・両発表原稿を更新。生成・評価実行・通知は行わない。


[全体の案内へ戻る](../docs/README.md)

リポジトリ直下から `python -m scripts.<名前>` で使います。以下は用途の分類です。再評価関連には特定の保存設定や実行先を前提とする処理もあるため、索引の掲載を新たな実行指示とは扱わず、対応する記録と各引数を確認してください。

## 実験の実行・再開・公開

| スクリプト | 役割 |
| --- | --- |
| [automate_experiment.py](automate_experiment.py) | 実験後の検証とコミット・プッシュまで行う標準ラッパー |
| [run_experiment.py](run_experiment.py) | 設定に基づく実験本体。Git操作は行わない |
| [run_queue.py](run_queue.py) | 複数実験を順番に実行 |
| [finalize_completed_experiment.py](finalize_completed_experiment.py) | 既存実験の終了を待って再検証・公開 |
| [prepare_retry.py](prepare_retry.py) | 通信障害などの明示的な追試設定を準備 |
| [pool_experiments.py](pool_experiments.py) | 検証済みの実験を統合し、出典を残して集計 |
| [sanity_check.py](sanity_check.py) | 欠落・重複など記録の整合性を確認 |

設定は[configsの索引](../configs/README.md)、操作は[トップREADME](../README.md)を参照してください。

## 保存済み結果の集計・分析

| スクリプト | 役割 |
| --- | --- |
| [analyze_verified_rescues.py](analyze_verified_rescues.py) | 整備後の評価・部分追試を反映した初期失敗の救済率。`--update-report`で主要結果とsnapshotも更新 |
| [analyze_interventions.py](analyze_interventions.py) | 現行ハーネスの分析CSVを作成 |
| [analyze_intervention_catalog.py](analyze_intervention_catalog.py) | 失敗原因別の介入カタログ |
| [analyze_reach_levels.py](analyze_reach_levels.py) | L0〜L3の累積達成・最終段階・移動を固定集計 |
| [analyze_stratified_effects.py](analyze_stratified_effects.py) | モデル・難度・seed・出典別の比較 |
| [analyze_discordant_repairs.py](analyze_discordant_repairs.py) | FとDの片方だけで救出した例 |
| [analyze_repair_costs.py](analyze_repair_costs.py) | 修正の追加生成コスト |
| [analyze_repair_limits.py](analyze_repair_limits.py) | 保存履歴を使う修正上限別の比較 |
| [analyze_third_round.py](analyze_third_round.py) | 3回目修正の救出と継続条件 |
| [compare_experiments.py](compare_experiments.py) | 対応する実験集団の公開集計を比較 |

出力資料は[分析の索引](../docs/analysis/README.md)で探せます。

## 評価器監査・保存コードの再評価

| スクリプト | 役割 |
| --- | --- |
| [audit_evaluation_methods.py](audit_evaluation_methods.py) | 評価方法と確認用回路の監査 |
| [audit_literature_reliability.py](audit_literature_reliability.py) | 文献・仕様に基づく監査 |
| [check_output_representation.py](check_output_representation.py) | 出力表現への評価感度の確認 |
| [pilot_reevaluation.py](pilot_reevaluation.py) | 小規模な保存コード再評価 |
| [reevaluate_saved.py](reevaluate_saved.py) | 保存コードの本再評価・checkpoint管理 |
| [followup_reevaluation.py](followup_reevaluation.py) | 指定された後続処理の起動・進捗管理 |
| [reevaluation_impact_audit.py](reevaluation_impact_audit.py) | 保存roundと診断文の影響監査 |
| [reevaluation_feedback_inventory.py](reevaluation_feedback_inventory.py) | 過去のフィードバックと停止条件変化の棚卸し |
| [reevaluation_partial_rerun.py](reevaluation_partial_rerun.py) | 固定した対象の後続生成を再実行 |
| [reevaluation_unchanged_check.py](reevaluation_unchanged_check.py) | 変更なし群の固定サンプル確認 |
| [reevaluation_followup_validation.py](reevaluation_followup_validation.py) | 後続再評価の読み取り専用検証 |
| [reevaluation_followup_report.py](reevaluation_followup_report.py) | 検証後の比較表・報告を作成 |
| [reevaluation_followup_finish.py](reevaluation_followup_finish.py) | 後続処理を監視し、検証・報告を実施 |

## 通知・レポート・発表資料

| スクリプト | 役割 |
| --- | --- |
| [notify_progress.py](notify_progress.py) | 定期的な進捗通知 |
| [monitor_experiments.py](monitor_experiments.py) | 実験の停止・異常を監視 |
| [experiment_events.py](experiment_events.py) | 実行時イベントの通知処理 |
| [notify_reevaluation.py](notify_reevaluation.py) | 指定再評価の終了通知 |
| [update_experiment_report.py](update_experiment_report.py) | 継続更新レポートとスナップショットを更新 |
| [draft_after_experiment.py](draft_after_experiment.py) | 実験完了後に資料作成AIを一度起動し、完了後に通知 |

## 従来の実行入口

| スクリプト | 役割 |
| --- | --- |
| [run_baseline.py](run_baseline.py) | 従来のbaseline／Self-Refine実行 |
| [analyze.py](analyze.py) | 従来のJSONL集計 |
| [run_local_coder.py](run_local_coder.py) | 従来のローカルLLM用の代替実装 |

新規の介入比較実験は、設定駆動の `automate_experiment`／`run_experiment` が入口です。`__init__.py` はPythonパッケージ定義で、実行コマンドではありません。
