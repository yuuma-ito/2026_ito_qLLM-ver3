# 検証用テスト（tests）

pytestで実行する、実験ハーネス・集計・運用処理の回帰テストを保存するフォルダです。

| 対象 | 主なファイル |
| --- | --- |
| 評価器・出力表現・失敗分類 | `test_evaluator.py`、`test_canonical_readout.py`、`test_failure_metadata.py` |
| モデル接続・介入・実験制御 | `test_clients.py`、`test_interventions_v2.py`、`test_experiment_workflow.py` |
| 集計・介入分析 | `test_pool_experiments.py`、`test_analyze_verified_rescues.py`、`test_analyze_reachable_rescue_history.py` |
| 評価器監査・再評価 | `test_evaluation_audit.py`、`test_full_reevaluation_driver.py`、`test_followup_reevaluation.py` |
| 自動化・通知・資料更新 | `test_automation.py`、`test_notify_progress.py`、`test_update_experiment_report.py`、`test_render_rescue_materials.py` |

依存関係を準備したうえで、リポジトリ直下から実行します。変更に対応するファイルを指定して検証できます。

```bash
.venv/bin/python -m pytest tests/test_evaluator.py
```

全体を検証する場合は `.venv/bin/python -m pytest tests` を使います。テスト用の一時データと、[results](../results/README.md) の研究用実験記録は区別します。
