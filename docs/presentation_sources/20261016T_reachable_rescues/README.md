# 2026-10-16 現行救済経路の固定発表出典

5モデル・1,000初期組・5,000条件記録。初期成功455組・失敗545組。R96、F183、D180組救済。主結果は検証済み保存prefixと必要な新suffixを反映した現在の経路。集計時点はresults_snapshot.jsonのcaptured_at_utc（UTC）に記載。

[分析手順・設定差・限界](../../analysis/reachable_rescues_20261016/README.md)と[考察](findings.md)を参照。元3実験のID、保存設定hash、モデルdigest、seed範囲、ハーネス版はmanifest.jsonのsource_settingsへ固定。保存設定は各source_dir/experiment_config.json。prefix/suffix出典はmanifest.jsonのinputsにhashで記録し、私的raw/cacheの内容は収録しない。分析値は静的確認と到達経路の計算値で、全件新規実験ではない。

全83組の両条件166履歴と398修正遷移はdiscordant_cases.csv・discordant_transitions.csv。全分母はrepair_summary.csvとcost_by_cap_and_stratum.csv。費用単価未測定。Pは独立生成の別行。上限別集計は同一履歴の打切り。旧120件・旧固定5,000件は設定・評価時点を区別して保持し、混ぜない。

source_manifest.jsonは公開用コピー・スクリプト・原稿・PDFのhash、validation_report.jsonは関連テスト、本文/CSV一致、PDFビルドと目視検査の状態を記録する。生成コード・prompt本文・API応答・生例外文・秘密・rawを含まない。

再生成：`.venv/bin/python -m scripts.analyze_reachable_rescue_history`、続いて`.venv/bin/python -m scripts.render_rescue_materials`。これらは保存済み資料の読み取りと公開資料の作成のみ。PDFビルドは各資料READMEのコマンドによる。旧固定発表出典20261013T_*と10月14日検証記録は保持した。
