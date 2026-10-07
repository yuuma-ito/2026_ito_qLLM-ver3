# 実験比較

公開用の集計値による記述的比較です。設定・対象task/seed・promptが一致し、自動検証を通過した実験のみ成功率の差を計算します。

| 実験 | モデル | 条件 | 件数 | L2成功率 | 救済率 | 平均秒 | 前回との差(pp) | 検証 |
|---|---|---|---:|---:|---:|---:|---:|---|
| shared_qwen35_quick_20261007 | ollama:qwen3.5:4b | baseline | 4 | 25.0% | — | 23.86 | — | sanity_only |
| shared_qwen35_quick_20261007 | ollama:qwen3.5:4b | execution_feedback | 4 | 100.0% | 100.0% | 41.74 | — | sanity_only |
| shared_qwen35_quick_20261007 | ollama:qwen3.5:4b | preventive_spec | 4 | 0.0% | 0.0% | 25.95 | — | sanity_only |
| shared_qwen35_quick_20261007 | ollama:qwen3.5:4b | self_debugging | 4 | 100.0% | 100.0% | 62.50 | — | sanity_only |
| shared_qwen35_quick_20261007 | ollama:qwen3.5:4b | self_refine | 4 | 50.0% | 33.3% | 70.48 | — | sanity_only |
| shared_three_models_quick_20261007T123904531170Z | ollama:gemma4:e4b-it-qat | baseline | 4 | 100.0% | — | 52.63 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:gemma4:e4b-it-qat | execution_feedback | 4 | 100.0% | — | 52.63 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:gemma4:e4b-it-qat | preventive_spec | 4 | 0.0% | — | 64.03 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:gemma4:e4b-it-qat | self_debugging | 4 | 100.0% | — | 52.63 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:gemma4:e4b-it-qat | self_refine | 4 | 100.0% | — | 52.63 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:4b | baseline | 4 | 25.0% | — | 22.71 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:4b | execution_feedback | 4 | 100.0% | 100.0% | 40.92 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:4b | preventive_spec | 4 | 0.0% | 0.0% | 25.52 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:4b | self_debugging | 4 | 100.0% | 100.0% | 61.63 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:4b | self_refine | 4 | 50.0% | 33.3% | 69.16 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:9b | baseline | 4 | 75.0% | — | 53.73 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:9b | execution_feedback | 4 | 100.0% | 100.0% | 135.21 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:9b | preventive_spec | 4 | 0.0% | 0.0% | 78.26 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:9b | self_debugging | 4 | 100.0% | 100.0% | 141.48 | — | automation_pass |
| shared_three_models_quick_20261007T123904531170Z | ollama:qwen3.5:9b | self_refine | 4 | 100.0% | 100.0% | 76.63 | — | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:gemma4:e4b-it-qat | baseline | 4 | 100.0% | — | 53.62 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:gemma4:e4b-it-qat | execution_feedback | 4 | 100.0% | — | 53.62 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:gemma4:e4b-it-qat | preventive_spec | 4 | 0.0% | — | 67.22 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:gemma4:e4b-it-qat | self_debugging | 4 | 100.0% | — | 53.62 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:gemma4:e4b-it-qat | self_refine | 4 | 100.0% | — | 53.62 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:4b | baseline | 4 | 25.0% | — | 24.59 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:4b | execution_feedback | 4 | 100.0% | 100.0% | 42.46 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:4b | preventive_spec | 4 | 0.0% | 0.0% | 25.54 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:4b | self_debugging | 4 | 100.0% | 100.0% | 64.35 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:4b | self_refine | 4 | 50.0% | 33.3% | 70.92 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:9b | baseline | 4 | 75.0% | — | 54.50 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:9b | execution_feedback | 4 | 75.0% | 0.0% | 187.89 | -25.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:9b | preventive_spec | 4 | 0.0% | 0.0% | 78.46 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:9b | self_debugging | 4 | 100.0% | 100.0% | 145.43 | +0.0 | automation_pass |
| shared_three_models_quick_20261007T123904532290Z | ollama:qwen3.5:9b | self_refine | 4 | 100.0% | 100.0% | 76.82 | +0.0 | automation_pass |

共有round 0は条件ごとの集計に含まれます。集計値の実行時間は実験全体の壁時計時間とは異なります。少数seedの差から有意差や因果効果を断定しないでください。
