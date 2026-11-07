---
name: research-workflow
description: qLLM研究の実験台帳更新、登録済みの論文数値・固定出典の照合、生成前の計画チェックを実行する。実験起動・再採点・原稿の自動修正は対象外。
---

# 研究台帳・数値照合・実験前チェック

対象は `/home/23tc011/2026_ito_qLLM-ver3`。別環境では対象リポジトリを確認する。`AGENTS.md` と `docs/codex/research_workflow.md` を参照し、依頼された処理を選ぶ。

## 実行する処理

- 台帳更新: `.venv/bin/python -m scripts.research_ledger`。保存設定を自動検出し、`configs/research_registry.json` の注記と統合する。`.cache/research_ledger/ledger.md` とJSONを確認する。
- 論文の数値照合: `.venv/bin/python -m scripts.check_research_claims`。`.cache/research_claims/report.json` にある範囲・不一致・根拠不足を確認する。初期設定の対象は卒論Wordの登録済みの2表・本文4箇所であり、全文ではない。
- 実験前チェック: `.venv/bin/python -m scripts.experiment_preflight --config <対象設定>`。新しい追試なら `--new-run`、再開予定なら対象の保存設定と `--resume` を使う。設定の作成や生成APIの起動は行わない。専用schemaは対象実験の専用検査を使う。

新しい台帳注記や照合箇所の登録を依頼された場合は、実ファイルから設定・出典・分母を確認して追加する。既存の事前仮説が記録されていなければnullのままにし、結果を見て推測で補わない。生成実験、保存コードの再採点、後半の継続、統合集計を別項目にし、元ファイルを置換しない。

数値照合では表と本文を別に確認する。対象箇所の消失や一意でないCSV行を見逃さず、hashだけを更新して不一致を解消しない。評価版・分母・対象集団が変わった場合は対応づけを見直す。個別履歴CSVからの詳細算術が必要なら既存の `scripts.verify_public_research_evidence` と `research-evidence-check` の範囲を確認する。原稿の修正は別途依頼された範囲で行う。

計画チェックの0は「実行を妨げるローカルの問題なし」であり、警告・未確認事項は残り得る。保存モデルsnapshotの指定は現在のサーバ状態の証明ではない。比較条件が不明なら一致とせず、所要時間の根拠がなければ算出なしとする。成功後に打ち切る実験の最大要求数と実測要求数を混同しない。

キャッシュ内のレポートは運用情報で、論文の固定出典として扱わない。確認依頼だけで実験・再採点・通知送信・Git公開を行わない。認証情報・生成コード・任意のエラー本文はレポートに転載しない。
