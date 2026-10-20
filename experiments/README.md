# 旧実験設定（experiments）

従来の介入比較設定を保持するフォルダです。現在の標準設定は [configs](../configs/README.md)、実験結果の保存先は [results](../results/README.md) です。

[intervention_compare_v2.json](intervention_compare_v2.json) は、`qwen2.5-coder:7b`、全タスク、seed 0〜9、baselineと3種類の修正条件を指定した設定です。修正条件の上限は3回です。

過去の設定を確認する際に参照してください。既存実験で実際に使った設定の根拠は、その結果フォルダ内の `experiment_config.json` です。
