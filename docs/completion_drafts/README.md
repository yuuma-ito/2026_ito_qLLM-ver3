# 実験完了時の自動下書き（completion_drafts）

実験完了後の資料作成処理が出力した中間発表・WiNF原稿と、その作成時点の出典・検証記録を保持するフォルダです。保存先のhashごとに下書きを分けています。

`<保存先のhash>/` 内の主な構成は次のとおりです。

| パス | 内容 |
| --- | --- |
| `midterm2026/`・`winf2026/` | 作成した原稿、PDF、進捗報告、README |
| `reference/` | 作成時に参考とした既存資料のコピー |
| `sources/`・`results_snapshot.json` | 下書きの根拠にした出典と固定スナップショット |
| `validation_report.json` | 作成資料の検証記録 |

現行の共有版は [midterm2026](../midterm2026/README.md) と [winf2026](../winf2026/README.md) です。ここにある下書きの数値・検証状態は作成時点に対応します。作成処理は [draft_after_experiment.py](../../scripts/draft_after_experiment.py) にあります。
