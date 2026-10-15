# 分析・再評価の索引

<!-- reachable-rescues:20261016 -->
[現行経路の全83組・追加コスト・3回目の寄与](reachable_rescues_20261016/README.md)（2026-10-16）。R96/F183/D180救済、初期失敗545組。


[全体の案内へ戻る](../README.md)

日付は資料を作成した時点です。各資料の結論は、その出典・評価器の版・検証範囲に対応します。過去のGO／NO-GOや検証済み表記は当時の判断であり、後続処理の現在状態は各再評価記録で確認してください。

## 現行の主要分析：介入による救済率

[介入による初期失敗コードの救済](intervention_rescues_20261015/README.md)に、整備後の評価と必要な部分追試を反映した救済率を保存した。R・F・Dは共通の初期失敗545組を分母とし、モデル・タスク・初期失敗類型・修正回数別に比較する。Pは独立生成の改善・悪化として別集計する。[解釈と次の分析](intervention_rescues_20261015/findings.md)、[固定スナップショット](intervention_rescues_20261015/results_snapshot.json)も参照。

## 保存済みの旧判定に基づく介入効果分析

2026-10-13時点の5,000件の保存済み評価を使った分析です。評価器修正後の再評価結果とは分けて読みます。

| テーマ | 入口 |
| --- | --- |
| モデル・難度・seed別の救出と段階変化 | [model_difficulty_seed_20261013](model_difficulty_seed_20261013/README.md) |
| 実行結果提示F・自己デバッグDの片方だけで救出した例 | [feedback_debugging_discordant_20261013](feedback_debugging_discordant_20261013/README.md) |
| 修正にかかる追加トークン・時間 | [repair_costs_20261013](repair_costs_20261013/README.md) |
| 修正上限1・2・3回の比較 | [repair_limits_20261013](repair_limits_20261013/README.md) |
| 3回目の救出例と停止候補 | [third_round_20261013](third_round_20261013/README.md) |

各フォルダの `findings.md` は考察、CSVは詳細表、JSONは出典・検証情報です。ファイル構成の詳細は各READMEを参照してください。

## 評価器の点検・仕様確認

| テーマ | 入口 |
| --- | --- |
| 文献・公式仕様との照合、隔離実行などの課題 | [literature_reliability_20261014](literature_reliability_20261014/README.md) |
| 評価方法と全体位相補正の点検 | [evaluation_methods_20261014](evaluation_methods_20261014/README.md) |
| 修正後の確認用回路による検証 | [evaluation_methods_after_fix_20261014](evaluation_methods_after_fix_20261014/README.md) |
| 測定先・古典ビット配置への感度 | [output_representation_20261014](output_representation_20261014/README.md) |

## 再評価の準備・実行・追試記録

| 段階 | 入口 |
| --- | --- |
| 再評価の準備点検 | [reevaluation_readiness_20261014](reevaluation_readiness_20261014/README.md) |
| 準備・小規模検証に関する完了記録 | [reevaluation_completion_20261014](reevaluation_completion_20261014/README.md) |
| 5,000件の本再評価、起動・中断・後続計画の記録 | [reevaluation_full_20261014T141718Z](reevaluation_full_20261014T141718Z/README.md) |
| 後続の仕様確認・影響監査・追試の記録 | [reevaluation_followup_20261015](reevaluation_followup_20261015/README.md) |

この索引の追加では再評価や検証を実行していません。実行状況や確定件数は各フォルダのレポートを確認してください。
