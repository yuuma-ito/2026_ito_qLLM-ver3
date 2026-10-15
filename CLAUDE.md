# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

現在の作業ルールは [AGENTS.md](AGENTS.md) を参照すること。このファイルは研究背景の補足であり、過去の実験の説明を新規実験の実行指示として扱わない。設定・処理の入口は [configs/README.md](configs/README.md)・[scripts/README.md](scripts/README.md)、分析と再評価の記録は [docs/analysis/README.md](docs/analysis/README.md) を参照する。

## このリポジトリの性格と「対」になる場所

南山大学 横山研の卒業研究、**伊藤悠真**（GitHub: `yuuma-ito`、学籍 2023TC011）のテーマ「量子×生成 AI（LLM 生成 Qiskit コードの評価）」の**実験ハーネスと実験データの正本**。リポジトリ名 `2026_ito_qLLM`、プロジェクト内部名 `qiskit-llm-eval`。private（org `yokoyama-lab`）。

**対になる場所（重要）**: このリポジトリは、横山研の卒研指導ワークスペース（先生専用の Overleaf monorepo `2026_term_reports_ai`、学生ごとの `氏名/` ディレクトリで卒論 `thesis_repo/` や指導メモを管理）と**対**になっている。

- 卒論本文（LaTeX）・指導メモ・要旨はあちらの `伊藤悠真/thesis_repo/`・`伊藤悠真/*.md` 側にある。
- **2026-06-30 にハーネスを github へ一本化**。それまで Overleaf 側にあった `伊藤悠真/qiskit-llm-eval/` は削除済みで、**ハーネス本体・実験データの正本はこのリポジトリ**。
- したがって「ハーネスを直す・実験を回す・生成物を見る」のは**ここ**。卒論原稿を直すのは Overleaf 側。両者の `CLAUDE.md` 冒頭に相互参照を置いてある。

## 構成

- `harness/` — 評価ロジック（`llm_clients.py` クラウド3社+Claude CLI+ローカルLLM 統一IF / `code_extractor.py` / `evaluator.py` L0–L3 判定 / `refine.py` Self-Refine プロンプト / `runner.py` baseline・refine 実行）
- `tasks/` — 評価タスク10種（T1_Bell〜T9_Ansatz、T3 は a/b）
- `scripts/` — 設定駆動の実験・検証・集計・再評価・通知。`run_baseline.py`・`analyze.py`・`run_local_coder.py` は従来の実行入口
- `tests/` — pytest 自己テスト（evaluator / clients / refine）
- `results/` — 現行は実験ID別の保存設定・非公開raw・公開用集計・検証結果。従来のJSONL・レポートを参照する記録もある
- `findings.md` — 旧実験の卒論反映用知見メモ。現行の結果・評価方針は `docs/` のレポートと出典を参照

## コマンド

```bash
pip install -r requirements.txt
cp .env.example .env                 # API キー（ローカルLLM のみなら不要）
pytest tests/ -v                     # 自己テスト
python -m scripts.run_baseline --mock --seeds 1 --out results/mock.jsonl   # APIキー不要の動作確認
# 本実行・ローカルLLM・Self-Refine の手順は README.md 参照
```


## 現行実験の標準入口（重要）

新規の介入比較実験には、5モデルの設定と自動化ラッパーを使用する。本実験は `configs/shared_five_models_full.json`（2,500件）。既存実験の再開・再検証は、その実験の保存設定を基準とする。

```bash
# 新規5モデル動作確認の計画確認（モデル呼び出しなし）
python -m scripts.run_experiment --config configs/shared_five_models_quick.json --dry-run

# 新規5モデル動作確認：検証後のコミット・プッシュを含む
python -m scripts.automate_experiment --config configs/shared_five_models_quick.json --new-run
```

現行の比較条件は `baseline / self_refine / execution_feedback / self_debugging / preventive_spec`。各 `(model, task, seed)` でbaselineと修正型3条件は同じ初期生成を共有する。preventive_specは異なる初期プロンプトによる独立生成であり、共有初期には含めない。`experiments/intervention_compare_v2.json` は旧4条件の設定として保持する。

`scripts.run_experiment` 自体はGit操作を行わない。実験後の検証・公開は `scripts.automate_experiment` と [AGENTS.md](AGENTS.md) の規則に従う。

実験後は `results/<experiment_id>/` の `manifest.json`, `sanity_report.json`, `paired_effects.csv`, `rescue_rates.csv`, `success_by_round.csv` を確認すること。既存レコードはキーでスキップして resume するため、手動で同じ JSONL に重複追記しない。

詳細な変更点・ファイル説明・介入仕様は `README.md` を正本とする。

## Git の注意

- コミットメッセージは `feat:` `fix:` `docs:` `chore:` `data:` 形式。
- 公開対象は関連コード・設定・文書と公開用レポート・集計CSV・manifest・sanity report。必要な集計がgitignore対象なら、そのファイルだけを明示して追加する。`.gitignore` のJSONL例外は公開許可を意味しない。`raw.jsonl`・生成コード・秘密情報・仮想環境・キャッシュは公開しない。
- API キー（`.env`）はコミット禁止。
