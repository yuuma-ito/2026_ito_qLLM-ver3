# 実験比較

公開用の集計値による記述的比較です。設定・対象task/seed・promptが一致し、自動検証を通過した実験のみ成功率の差を計算します。

| 実験 | モデル | 条件 | 件数 | L2成功率 | 救済率 | 平均秒 | 前回との差(pp) | 検証 |
|---|---|---|---:|---:|---:|---:|---:|---|
| shared_three_models_full_20261008T103231611899Z | ollama:gemma4:e4b-it-qat | baseline | 100 | 65.0% | — | 53.11 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:gemma4:e4b-it-qat | execution_feedback | 100 | 87.0% | 62.9% | 106.97 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:gemma4:e4b-it-qat | preventive_spec | 100 | 32.0% | 25.7% | 54.45 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:gemma4:e4b-it-qat | self_debugging | 100 | 88.0% | 65.7% | 112.22 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:gemma4:e4b-it-qat | self_refine | 100 | 82.0% | 48.6% | 111.04 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:4b | baseline | 100 | 15.0% | — | 38.74 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:4b | execution_feedback | 100 | 56.0% | 48.2% | 148.81 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:4b | preventive_spec | 100 | 11.0% | 8.2% | 30.24 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:4b | self_debugging | 100 | 57.0% | 49.4% | 175.57 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:4b | self_refine | 100 | 33.0% | 21.2% | 152.48 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:9b | baseline | 100 | 59.0% | — | 80.49 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:9b | execution_feedback | 100 | 76.0% | 41.5% | 229.35 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:9b | preventive_spec | 100 | 25.0% | 14.6% | 79.23 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:9b | self_debugging | 100 | 80.0% | 51.2% | 251.82 | — | automation_pass |
| shared_three_models_full_20261008T103231611899Z | ollama:qwen3.5:9b | self_refine | 100 | 73.0% | 34.1% | 221.69 | — | automation_pass |

共有round 0は条件ごとの集計に含まれます。集計値の実行時間は実験全体の壁時計時間とは異なります。少数seedの差から有意差や因果効果を断定しないでください。
