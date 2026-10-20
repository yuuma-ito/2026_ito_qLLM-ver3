# 実験・評価の処理本体（harness）

LLMによるQiskitコード生成、介入による修正、生成コードの評価、実験状態の保存を実装する Python パッケージです。実行の入口は [scripts](../scripts/README.md) にあります。

| ファイル | 役割 |
| --- | --- |
| [experiment.py](experiment.py) | 実験設定の読み込み、条件と出典情報の管理 |
| [runner.py](runner.py) | 初期生成と条件別の修正・評価の制御 |
| [llm_clients.py](llm_clients.py) | 各LLM接続とmock応答の共通インターフェース |
| [code_extractor.py](code_extractor.py) | モデル応答からPythonコードを抽出 |
| [evaluator.py](evaluator.py)・[readout.py](readout.py) | L0〜L3評価、出力表現の処理 |
| [isolated_evaluation.py](isolated_evaluation.py)・[isolated_worker.py](isolated_worker.py)・[sandbox_policy.py](sandbox_policy.py) | 生成コードを別プロセスで評価する処理と制約 |
| [interventions/prompts.py](interventions/prompts.py)・[refine.py](refine.py) | 条件別プロンプトと診断文の組み立て |
| [failure_metadata.py](failure_metadata.py) | 失敗段階・原因・例外情報の分類と旧記録の補完 |
| [run_state.py](run_state.py) | 実行状態・共有ロックの管理 |
| [reevaluation_plan.py](reevaluation_plan.py)・[reevaluation_checkpoint.py](reevaluation_checkpoint.py) | 保存コード再評価の計画と再開情報 |
| [supplementary.py](supplementary.py) | 補助的な評価情報の取得 |

評価の仕様と保存形式は [ハーネス仕様](../docs/new_harness_spec.md)、評価器の版と出力表現は [評価仕様](../docs/evaluator_readout.md) を参照してください。変更時の検証対象は [tests](../tests/README.md) で確認できます。
