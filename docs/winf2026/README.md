# WiNF2026の現行共有版（2026-10-28更新）

題目：**量子LLM支援プログラミングにおける失敗類型と介入カタログの実証研究**。今後の更新でもこの表記を使用する。

研究の主題は初期失敗コードを介入がどれだけ救済できるか。主要結果は5モデルの現行到達経路：初期失敗545組にR96、F183、D180組救済。Fのみ43組・Dのみ40組の全83組を確認した。追加対照の独立再生成B4（10月22日完了集計）も反映し、初期失敗545組中217組（39.8%）が成功、最終成功672/1,000組（67.2%）だった。

- [発表スライド](slides/README.md)：本編13枚（約10分40秒）＋補足4枚。[PowerPoint](slides/slides.pptx)・[PDF](slides/slides.pdf)・発表メモ。
- [paper.pdf](paper.pdf)：共有用PDF。
- [paper.tex](paper.tex)：編集用原稿。
- [進捗報告](progress_report_draft.txt)：前回からの変更・完了作業・残る課題。
- [和文抄録](abstract.txt)：独立した共有用ファイル。著者・指導教員表記は要旨と同じ「2023TC011 伊藤 悠真　指導教員：横山 哲郎」、所属は既存の正式表記「南山大学 理工学部 電子情報学科」。

[固定発表用スナップショット・全表・出典hash](../presentation_sources/20261016T_reachable_rescues/README.md)、[B4完了集計・保存設定・検証](../analysis/independent_4_completed_20261022/README.md)と[履歴・コスト分析](../analysis/reachable_rescues_20261016/README.md)を参照。集計UTCは固定snapshot内に記録。manifestには元実験ID・保存設定hash・schema・seedを保持した。

元3実験は3モデルseed 0〜9の1,500条件記録、5モデルseed 10〜19の2,500、残り2モデルseed 0〜9の1,000。合わせて1,000初期組・5,000条件記録。検証済み保存prefixと必要な新suffix（部分追試293ケース）を反映した現在の経路を主結果とし、全件新実験とは呼ばない。新主L3は指定入力の出力と所定の構造要件に限定され、全入力の同値性は保証しない。共有初期・タスク・seed依存があり、因果効果や統計的有意差は断定しない。

追加修正コストは共有初期生成を除外し未救済への消費も含む。prefix記録値とsuffix実測値の再構成計算で、実測の費用削減とは呼ばない。金銭費用は未測定。Pは独立生成。3回目の寄与は同じ履歴の打切り比較であり、上限別独立実験ではない。

旧120件は2モデル・seed 0〜2・2条件・L2終了の既報で、主結果へ合算しない。旧20261013T_*固定発表出典・results_snapshot_20261008.json・analysis_snapshot_20261014.json（WiNF）・旧検証記録はその時点の資料として保持する。旧F/D191や片側42/42は現行値と混ぜない。更新前の現行原稿はユーザー指定の.cache/overnight_rescues_20261016/beforeにも保存されている。

## 今回の更新と出典

- [今回の固定スナップショット](results_snapshot_20261028.json)：反映時点、B4実験ID、結果表の元データ、出典SHA-256。元の固定集計は更新しない。
- [現行表](tables_20261028.tex)：モデル別・初期失敗類型別にB4列を追加。R/F/Dの救済とB4の独立再生成による追加成功を区別する。
- B4実験IDは `independent_4_full_20261020T185811381595Z`。保存設定は固定集計内の `runner_experiment_config.json`。全1,000組、欠落・重複・予定外0、sanity成功。追加roundのunknown_error 2件はコード側NameErrorであり、API障害ではない。元ログには中断時の接続エラーが残るが、保存設定で再開した完了記録を基準とする。
- B4の追加1,342要求、995,815 tokens、追加tokens／追加成功4,589.0。R/F/Dと初回込み最大4回だが、実要求数・入力情報・tokens・seed規則・実行時期・出典schema・診断文は異なる。一般的優劣や診断提示の因果効果を主張しない。
- 評価定義を現行要旨と整合：L0に構文・importのコード読込みを含め、構造命令数から測定・barrierを除く。現行評価と固定部分追試の測定・transpile seedは42。

## ビルドと確認

このディレクトリでpLaTeX・dvipdfmx・IPAexフォントを用いる。スタイルファイルは変更しない。現行表は `tables_20261028.tex` から読み込む。

```bash
platex -interaction=nonstopmode -halt-on-error paper.tex
platex -interaction=nonstopmode -halt-on-error paper.tex
dvipdfmx -p a4 -f ptex-ipaex.map -o paper.pdf paper.dvi
```

[今回の検証記録](validation_report_20261028.json)に出典hash・本文/CSV一致、引用・参照、2ページ、フォント埋込み、はみ出し、全ページ画像の確認を記録した。10月14日・16日の検証記録は当時の資料に対応する。本資料は共有用下書き。今回の作業では追加生成・生成コード再実行・通知・投稿・外部アップロードを行わない。
