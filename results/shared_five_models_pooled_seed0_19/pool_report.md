# seed 0〜19の統合集計

集計時点: 2026-10-13T05:43:00.209101+00:00

記録件数: 5000件。元の保存設定と記録は保持し、新規生成は行っていません。

| 出典実験 | seed | 件数 | baseline L2失敗 |
| --- | --- | ---: | ---: |
| shared_three_models_full_20261008T103231611899Z | {'start': 0, 'stop': 10} | 1500 | 161 |
| shared_five_models_full_20261010T041019864060Z | {'start': 10, 'stop': 20} | 2500 | 288 |
| shared_two_models_seed0_9_full_20261012T100658266051Z | {'start': 0, 'stop': 10} | 1000 | 133 |

モデル・条件別の成功率はsummary_by_model.csv、出典別の内訳はsummary_by_source.csv、失敗原因別の救済率はintervention_catalog_by_error.csvを参照してください。

- 各条件は共有round 0を含むため、5,000件は独立した5,000回の初期生成ではありません。
- seedブロック・実施時期の差を保持し、モデルの一般的優劣や統計的有意差は断定しません。
- schema 2.0と2.1を含みます。エラー分類変更はexecution_feedbackとself_debuggingの診断文にも影響します。統合値は混合手順の記述的結果であり、単一手順の介入効果とは解釈しません。
