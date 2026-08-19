# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このリポジトリの性格と「対」になる場所

南山大学 横山研の卒業研究、**伊藤悠真**（GitHub: `yuuma-ito`、学籍 2023TC011）のテーマ「量子×生成 AI（LLM 生成 Qiskit コードの評価）」の**実験ハーネスと実験データの正本**。リポジトリ名 `2026_ito_qLLM`、プロジェクト内部名 `qiskit-llm-eval`。private（org `yokoyama-lab`）。

**対になる場所（重要）**: このリポジトリは、横山研の卒研指導ワークスペース（先生専用の Overleaf monorepo `2026_term_reports_ai`、学生ごとの `氏名/` ディレクトリで卒論 `thesis_repo/` や指導メモを管理）と**対**になっている。

- 卒論本文（LaTeX）・指導メモ・要旨はあちらの `伊藤悠真/thesis_repo/`・`伊藤悠真/*.md` 側にある。
- **2026-06-30 にハーネスを github へ一本化**。それまで Overleaf 側にあった `伊藤悠真/qiskit-llm-eval/` は削除済みで、**ハーネス本体・実験データの正本はこのリポジトリ**。
- したがって「ハーネスを直す・実験を回す・生成物を見る」のは**ここ**。卒論原稿を直すのは Overleaf 側。両者の `CLAUDE.md` 冒頭に相互参照を置いてある。

## 構成

- `harness/` — 評価ロジック（`llm_clients.py` クラウド3社+Claude CLI+ローカルLLM 統一IF / `code_extractor.py` / `evaluator.py` L0–L3 判定 / `refine.py` Self-Refine プロンプト / `runner.py` baseline・refine 実行）
- `tasks/` — 評価タスク10種（T1_Bell〜T9_Ansatz、T3 は a/b）
- `scripts/` — `run_baseline.py`（baseline/`--refine`）, `analyze.py`（baseline vs refine 集計）, `run_local_coder.py`（ローカルLLM n=10 反復ランナー）
- `tests/` — pytest 自己テスト（evaluator / clients / refine）
- `results/` — 実験データ（`exp*.jsonl` と `local_*.jsonl`）と集計レポート（`*_report.md`）。`findings.md` に知見を集約
- `findings.md` — 卒論反映用の知見メモ（baseline vs Self-Refine の結果・モデル能力依存・退行解釈など）

## コマンド

```bash
pip install -r requirements.txt
cp .env.example .env                 # API キー（ローカルLLM のみなら不要）
pytest tests/ -v                     # 自己テスト
python -m scripts.run_baseline --mock --seeds 1 --out results/mock.jsonl   # APIキー不要の動作確認
# 本実行・ローカルLLM・Self-Refine の手順は README.md 参照
```


## ver2 実験の標準入口（重要）

新規の介入比較実験では、ver1 互換の `scripts/run_baseline.py --refine` ではなく、**config 駆動の ver2 runner** を使用する。

```bash
# まず計画確認（モデル呼び出しなし）
python -m scripts.run_experiment --config experiments/intervention_compare_v2.json --dry-run

# 本実行: resume → sanity check → 集計まで自動
python -m scripts.run_experiment --config experiments/intervention_compare_v2.json
```

ver2 の比較条件は `baseline / self_refine / execution_feedback / self_debugging`。各 `(model, task, seed)` で **同じ初期生成を共有してから条件分岐**する。Task Level は現段階では使用しない。

実験後は `results/<experiment_id>/` の `manifest.json`, `sanity_report.json`, `paired_effects.csv`, `rescue_rates.csv`, `success_by_round.csv` を確認すること。既存レコードはキーでスキップして resume するため、手動で同じ JSONL に重複追記しない。

詳細な変更点・ファイル説明・介入仕様は `README.md` を正本とする。

## Git の注意

- コミットメッセージは `feat:` `fix:` `docs:` `chore:` `data:` 形式。
- `results/` は基本 gitignore だが、共有する実験データ（jsonl）と集計/診断レポート（md）は追跡する（`.gitignore` 参照。mock 等は除く）。
- API キー（`.env`）はコミット禁止。
