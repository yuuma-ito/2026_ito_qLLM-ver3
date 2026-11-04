# 実験・評価の処理本体（harness）

[independent_4.py](independent_4.py)は保存Bの初回を共有する独立再生成B4の専用処理．通常baselineプロンプトだけで最大3回追加し，主L3成功で停止する．既存の5条件・評価器・修正処理の挙動を変更しない．保存設定と必要ファイルは[実装・再現手順](../docs/independent_4_reproduction.txt)を参照する．

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
| [reference_conformance.py](reference_conformance.py) | 別仕様の測定禁止・純粋状態／全ユニタリ参照適合性。v4主判定には組み込まない |

評価の仕様と保存形式は [ハーネス仕様](../docs/new_harness_spec.md)、評価器の版と出力表現は [評価仕様](../docs/evaluator_readout.md) を参照してください。変更時の検証対象は [tests](../tests/README.md) で確認できます。

参照適合性検査の対象・全入力距離の意味・未実施の全件適用は[仕様](../docs/reference_conformance.txt)に記載した。信頼できる構築済み回路用の関数であり、保存モデルコードや信頼できないQPYを直接実行・読込みする入口ではない。
