# 設定の索引

[全体の案内へ戻る](../docs/README.md)

## 今後の実験に使う設定

| ファイル | 用途 |
| --- | --- |
| [shared_five_models_quick.json](shared_five_models_quick.json) | 5モデルの小規模確認。1コマンド自動実行の標準設定 |
| [shared_five_models_full.json](shared_five_models_full.json) | 5モデル本実験、2,500件 |
| [shared_two_models_seed0_9_full.json](shared_two_models_seed0_9_full.json) | 2モデルのseed 0〜9補完、1,000件 |
| [shared_five_models_pool.json](shared_five_models_pool.json) | 既存3出典の統合元と統合先 |

自動実行の入口は `python -m scripts.automate_experiment --config configs/shared_five_models_quick.json` です。新しい追試には `--new-run` を付けます。既存実験の再開・再検証には、その実験の `results/<実験ID>/experiment_config.json` を使います。[実行・公開ルール](../AGENTS.md)も確認してください。

## 過去の実験・モデル構成を参照する設定

| ファイル | 用途 |
| --- | --- |
| [shared_three_models_quick.json](shared_three_models_quick.json)・[shared_three_models_queue.json](shared_three_models_queue.json) | 従来の3モデルの動作確認・実験キュー |
| [shared_qwen35_quick.json](shared_qwen35_quick.json) | Qwen3.5の動作確認 |
| [quick_debug.json](quick_debug.json) | 従来の小規模確認 |
| [full_all_models.json](full_all_models.json) | 従来の全モデル設定 |
| [full_qwen14b.json](full_qwen14b.json)・[full_qwen3b.json](full_qwen3b.json)・[full_qwen7b.json](full_qwen7b.json) | 従来のモデル別本実験設定 |
| [experiment_queue.json](experiment_queue.json) | 実験の順次実行設定 |

これらは履歴・再現用にも使います。新規実験のモデル選択は[AGENTS.md](../AGENTS.md)に従います。

## 通知・定期実行

| ファイル | 用途 |
| --- | --- |
| [slack_progress.cron](slack_progress.cron) | 通知、監視、レポート更新、完了後下書きの定期実行 |
| [reviewed_experiments.json](reviewed_experiments.json) | 過去の確認済み実験を通知上で扱うための記録 |

cron設定の編集だけでは実際の登録内容が変わったことにはなりません。運用手順は[トップREADME](../README.md#slackへの定時進捗通知)を参照してください。
