# WiNF2026 発表用スライド

2026-10-28更新。ユーザー指定の10〜12分を想定した下書き。本編13枚・目安10分40秒、補足4枚、計17枚。実際の発表時間は練習と募集要項の確認後に調整する。

- [slides.pptx](slides.pptx)：編集用PowerPoint。表・図・棒グラフは編集可能なオブジェクトで構成。
- [slides.pdf](slides.pdf)：閲覧・共有用PDF、16:9。
- [speaker_notes.txt](speaker_notes.txt)：各枚の説明メモ・目安時間・質疑用説明。PowerPointのノート欄にも収録。
- [source_manifest.json](source_manifest.json)：構成・時間・固定出典SHA-256。
- [validation_report.json](validation_report.json)：数値・出典・文字欠落・フォント・ページサイズ・画像確認の記録。

題目は「量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究」。指定位置で改行する。著者・指導教員表記は要旨と同じ「2023TC011 伊藤 悠真　指導教員：横山 哲郎」、所属は「南山大学 理工学部 電子情報学科」。

## 構成

| 枚 | 内容 | 目安 |
| --- | --- | ---: |
| 1 | 題目・研究の問い | 20秒 |
| 2 | 背景と目的 | 45秒 |
| 3 | B・R・F・D・P・B4の比較条件 | 55秒 |
| 4 | 対象・設定・保存経路の由来 | 60秒 |
| 5 | 主L3・初期成功455組／失敗545組・分母 | 45秒 |
| 6 | R96・F183・D180組の救済 | 60秒 |
| 7 | Fのみ43・共通140・Dのみ40組 | 55秒 |
| 8 | 初期失敗類型別の救済 | 55秒 |
| 9 | 独立再生成B4の217組追加成功 | 60秒 |
| 10 | 未成功例も含む追加tokens／追加成功 | 50秒 |
| 11 | 3回目の救済と停止回数 | 50秒 |
| 12 | カタログに記載すべき範囲と次の検証 | 45秒 |
| 13 | まとめ | 40秒 |
| 14〜17 | モデル別表・B4/F対応とP・評価範囲・文献出典 | 質疑用 |

## 結果の出典と扱い

[現行WiNF原稿](../paper.tex)と[固定スナップショット](../results_snapshot_20261028.json)を基準とした。R/F/Dは[2026-10-16固定到達経路](../../presentation_sources/20261016T_reachable_rescues/README.md)、B4は[2026-10-22固定の完了集計](../../analysis/independent_4_completed_20261022/README.md)から反映した。

本体は元3実験の計5,000条件・1,000初期組に対する再構成経路。B4は同じ初期組に対する別の追加対照で、5,000条件に混ぜない。旧120件は別設定の既報であり合算しない。救済数とB4の追加成功を区別し、全入力の同値性・一般的優劣・因果効果・統計的有意差を主張しない。

追加tokensは共有初期を除き未成功消費を含む。R/F/Dは再構成値であり、全件新生成の実測コストや金銭費用ではない。生成機会の上限が同じでも、入力情報・実要求数・seed規則・実行時期・出典の差が残る。

## 再生成と検証

リポジトリ直下で実行する。依存はpython-pptx、Pillow、PyMuPDF、LibreOffice、IPAexGothic。既存のローカル依存キャッシュがある環境では以下を使用できる。

```bash
PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/winf2026/slides/build.py --pdf
PYTHONPATH=.cache/graduation_tools .venv/bin/python docs/winf2026/slides/validate.py
```

`--pdf`を省略するとPowerPoint・メモ・出典だけを再生成する。PDF変換はシステムのLibreOfficeを優先し、この環境では既存の `.cache/graduation_office/` を使用した。文字はIPAexGothicを使用し、PDFのフォント埋込みを検証した。PowerPointを別環境で編集する場合はフォント置換と折返しを確認する。

検証処理は全スライドの文字と表セルがPDFに含まれること、17ページ・16:9、図形と文字がスライド内に収まること、主要数値と固定出典hash、全ノートを確認する。確認画像は `.cache/winf_slides_20261028/` に生成する。再生成後は全ページを画像で確認し、検証記録のvisual_reviewを更新する。自動検証の再実行ではvisual_reviewをpendingへ戻す。

今回の資料作成では新しい実験・モデル要求・生成コード実行を行っていない。
