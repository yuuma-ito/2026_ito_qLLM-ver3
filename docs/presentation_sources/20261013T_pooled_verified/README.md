# 5モデルの統合集計と固定出典

固定集計時点：2026-10-13 14:45:33 JST。3実験を出典別に再検証し、5モデル・seed 0〜19の5,000件を記述的に統合した。各モデル1,000件、各モデル・条件200件。L2・L3達成2,457件、欠落・重複・予定外0件。診断文処理差を含むため、単一手順の介入効果として解釈しない。

[スナップショット](results_snapshot.json)、[出典hash](source_manifest.json)、[検証記録](validation_report.json)。旧固定出典は別ディレクトリで保持した。

| モデル | B | R | F | D | P |
| --- | ---: | ---: | ---: | ---: | ---: |
| qwen3.5:4b | 35 | 67 | 109 | 118 | 25 |
| gemma4:e4b-it-qat | 133 | 167 | 183 | 176 | 63 |
| qwen3.5:9b | 116 | 144 | 157 | 158 | 58 |
| qwen2.5-coder:7b | 132 | 148 | 158 | 155 | 129 |
| gemma3:4b | 2 | 2 | 2 | 2 | 18 |

B＝baseline、R＝自己見直し、F＝実行結果提示、D＝自己デバッグ、P＝生成前介入。修正条件は初期コードを共有し、Pは別プロンプトの独立生成。5,000件は独立した5,000回の初期生成ではない。

## 出典とファイル

- `shared_three_models_full_20261008T103231611899Z`：1500件、[保存設定](shared_three_models_full_20261008T103231611899Z/experiment_config.json)、[到達段階](shared_three_models_full_20261008T103231611899Z/level_summary.csv)、[対応付き移動](shared_three_models_full_20261008T103231611899Z/level_transitions.csv)。
- `shared_five_models_full_20261010T041019864060Z`：2500件、[保存設定](shared_five_models_full_20261010T041019864060Z/experiment_config.json)、[到達段階](shared_five_models_full_20261010T041019864060Z/level_summary.csv)、[対応付き移動](shared_five_models_full_20261010T041019864060Z/level_transitions.csv)。
- `shared_two_models_seed0_9_full_20261012T100658266051Z`：1000件、[保存設定](shared_two_models_seed0_9_full_20261012T100658266051Z/experiment_config.json)、[到達段階](shared_two_models_seed0_9_full_20261012T100658266051Z/level_summary.csv)、[対応付き移動](shared_two_models_seed0_9_full_20261012T100658266051Z/level_transitions.csv)。
- 統合：[shared_five_models_pooled_seed0_19/pool_report.md](shared_five_models_pooled_seed0_19/pool_report.md)。出典別内訳、モデル・条件・タスク・難度別結果、失敗類型別救出、累積到達・対応付き移動のCSVを保存した。

L0〜L3は累積的な到達水準。未達／L0のみ／L1まで／L2まで／L3は排他的で合計が全件数になる。段階差を等間隔の点数として平均しない。構造検証の範囲は固定スナップショットのタスク要件を参照。生成コードや認証情報は含めない。
