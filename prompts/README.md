# 共通プロンプト（prompts）

量子コード生成時の共通指示と、予防的な注意事項を置くフォルダです。

| ファイル | 内容・参照先 |
| --- | --- |
| [system.txt](system.txt) | Qiskitのバージョン、`build_circuit()` の形式、コードの出力形式などの共通指示。[llm_clients.py](../harness/llm_clients.py) が読み込む |
| [preventive_spec.txt](preventive_spec.txt) | API・ビット数・ビット順などの注意事項。現行の予防条件が使う文面は [interventions/prompts.py](../harness/interventions/prompts.py) の `PREVENTIVE_SPEC` に定義されている |

タスク固有の指示は [tasks](../tasks/README.md)、修正条件ごとの指示は [interventions/prompts.py](../harness/interventions/prompts.py) にあります。全体の文面は [プロンプト一覧](../docs/experiment_prompts.md) で確認できます。文面を変更するときは、実際に読み込まれる定義と一覧の対応を確認してください。
