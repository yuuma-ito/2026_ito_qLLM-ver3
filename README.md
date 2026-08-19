# qiskit-llm-eval

量子 LLM 支援プログラミングにおける失敗類型と介入効果を、Qiskit コードの実行ベース評価で比較する卒業研究用ハーネスです。

ver2 は **ver1 を土台に拡張**しており、既存の 10 タスク・L0〜L3 evaluator・LLM client は維持したまま、介入比較・再現性・自動集計を追加しています。

## ver2 の目的

同一の `(model, task, seed)` で得た **同じ初期生成コード**から条件を分岐し、次の 4 条件を比較します。

| condition | 内容 | 外部評価情報 | 修正 round |
| --- | --- | --- | --- |
| `baseline` | 初回生成のみ | なし | 0 |
| `self_refine` | 前回コードを自己点検して修正 | 与えない | 最大 3 |
| `execution_feedback` | evaluator のエラー・実行結果を返して修正 | 与える | 最大 3 |
| `self_debugging` | 実行情報を使い、説明→原因分析→修正 | 与える | 最大 3 |

`round 0` は共有初期生成、`round 1..3` は修正介入です。L2 成功時点で停止します。

> 重要: ver1 の `Self-Refine` は実行フィードバックを返す実装だったため、ver2 の分類では `execution_feedback` に相当します。ver1 互換の `run_refine()` は残しています。

## ver1 → ver2 の主な変更点

- 4 介入条件を共通インターフェースで比較可能にした
- 条件間で **同じ初期生成コードを共有**する paired design を採用
- `experiment_id` / `condition_id` / `intervention` / `model_spec` / `base_seed` を記録
- 各 round に `round_seed` / `feedback_type` / `code_sha256` を記録
- 実験 config からワンコマンド実行できる `scripts/run_experiment.py` を追加
- 完了済みレコードをスキップする resume を追加
- 実験条件・環境・Git commit・config hash を `manifest.json` に保存
- token / elapsed time / 推定 cost を記録
- 実験終了後に sanity check を自動実行
- Rescue Rate / Regression Rate / success-by-round-k / paired gain を自動集計
- Task Level は ver2 では導入しない。既存 `task_id` をそのまま利用する

## ディレクトリ構成

```text
qiskit-llm-eval/
├── harness/
│   ├── llm_clients.py          # OpenAI / Anthropic / Google / Claude CLI / Ollama / local / Mock
│   ├── code_extractor.py       # LLM出力から Python コードを抽出
│   ├── evaluator.py            # L0 / L1 / L2 / L3 と error_category を判定
│   ├── refine.py               # ver1 execution-feedback 用診断生成（互換用にも利用）
│   ├── runner.py               # 初期生成、baseline、各介入 round の実行・記録
│   ├── experiment.py           # config検証、manifest、resume、cost推定など
│   └── interventions/
│       ├── __init__.py
│       └── prompts.py          # Self-Refine / Execution Feedback / Self-Debugging の仕様
│
├── tasks/                      # 既存 10 タスク定義
│   ├── t1_bell.py
│   ├── t2_ghz.py
│   ├── t3_dj_balanced.py
│   ├── t3_dj_constant.py
│   ├── t4_bv.py
│   ├── t5_grover.py
│   ├── t6_qft.py
│   ├── t7_iqft.py
│   ├── t8_qpe.py
│   └── t9_ansatz.py
│
├── prompts/
│   └── system.txt              # 共通 system prompt
│
├── experiments/
│   └── intervention_compare_v2.json  # ver2 の実験設定例
│
├── scripts/
│   ├── run_baseline.py         # ver1互換 runner
│   ├── analyze.py              # ver1互換集計
│   ├── run_experiment.py       # ver2 全体実行の入口
│   ├── sanity_check.py         # 結果整合性チェック
│   └── analyze_interventions.py # ver2 介入比較集計
│
├── tests/                      # pytest 自己テスト
└── results/
    └── <experiment_id>/
        ├── manifest.json
        ├── raw.jsonl
        ├── sanity_report.json
        ├── summary.csv
        ├── paired_effects.csv
        ├── rescue_rates.csv
        └── success_by_round.csv
```

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
```

API キーを使う場合だけ `.env` を編集してください。Ollama / local / Mock のみならクラウド API キーは不要です。

## 最小実行方法

### 1. config を確認

既定例:

```text
experiments/intervention_compare_v2.json
```

主な項目:

```json
{
  "experiment_id": "intervention_compare_v2",
  "models": ["ollama:qwen2.5-coder:7b"],
  "tasks": "all",
  "seeds": {"start": 0, "stop": 10},
  "temperature": 0.7,
  "max_rounds": 3,
  "conditions": [
    {"id": "baseline", "intervention": "baseline"},
    {"id": "self_refine_r3", "intervention": "self_refine", "max_rounds": 3},
    {"id": "execution_feedback_r3", "intervention": "execution_feedback", "max_rounds": 3},
    {"id": "self_debugging_r3", "intervention": "self_debugging", "max_rounds": 3}
  ],
  "output_dir": "results/intervention_compare_v2",
  "pricing": {}
}
```

`seeds.stop` は Python の `range` と同じく終端を含みません。上記は seed 0〜9 です。

### 2. まず dry-run

```bash
python -m scripts.run_experiment \
  --config experiments/intervention_compare_v2.json \
  --dry-run
```

モデル呼び出しを行わず、モデル・タスク・seed・条件・予定レコード数を確認します。

### 3. 実験を実行

```bash
python -m scripts.run_experiment \
  --config experiments/intervention_compare_v2.json
```

この 1 コマンドで次を行います。

```text
config validation
→ manifest 保存
→ 共有初期生成
→ 4条件の paired 実行
→ JSONL 保存
→ sanity check
→ 自動集計
```

同じコマンドを再実行した場合、既に存在する `(experiment_id, condition_id, model_spec, task_id, base_seed)` はスキップします。

## エージェントに実行させる場合

プロジェクト専用ディレクトリでエージェントを起動し、例えば次のように指示します。

```text
experiments/intervention_compare_v2.json を確認して dry-run し、
問題がなければ実験を実行してください。
既存結果は重複実行せず resume し、終了後に sanity_report.json と
paired_effects.csv / rescue_rates.csv を確認してください。
```

実行入口は必ず以下です。

```bash
python -m scripts.run_experiment --config experiments/intervention_compare_v2.json
```

## 共有初期生成による条件間比較

ver2 では、各 `(model, task, base_seed)` について初期生成を 1 回だけ行います。

```text
(model, task, seed)
        │
        └─ shared round 0
             ├─ baseline
             ├─ self_refine
             ├─ execution_feedback
             └─ self_debugging
```

これにより、seed を API 側で固定できないモデルでも、介入条件間で初期コードを完全に揃えられます。

各 round の `code_sha256` を保存し、sanity check でも round 0 が条件間で一致しているか確認します。

## 介入仕様

### Baseline

タスク prompt から 1 回だけコードを生成し、L0〜L3 で評価します。

### Self-Refine

外部 evaluator の結果は与えません。前回コードだけを提示し、モデル自身にタスク要件・API・量子的意味を点検して修正させます。

### Execution Feedback

前回コードに加えて evaluator が得た情報を返します。

- L0/L1: error category / error message
- qubit 不一致: expected / actual
- distribution L2 failure: expected / actual distribution
- statevector L2 failure: distance / threshold

正解コードは渡しません。

### Self-Debugging

Execution Feedback と同じ外部情報を与えたうえで、

```text
説明 → 原因分析 → 修正
```

の順序を明示的に要求します。共通 system prompt の「コードブロックのみ」という制約を維持するため、説明と原因分析は修正版コード先頭の `# DEBUG:` コメントとして 3〜6 行残させます。これにより raw output 上で Self-Debugging の説明過程を確認でき、コード自体はそのまま evaluator で実行できます。

## 評価指標

| L | 指標 | 判定 |
| --- | --- | --- |
| L0 | Python / import / interface | コードを exec し `build_circuit()` を取得可能 |
| L1 | 実行可能性 | Qiskit 上で回路を評価可能 |
| L2 | 出力一致（主指標） | TVD または状態ベクトル距離 `< task.threshold` |
| L3 | 構造的妥当性 | qubit 数・ゲート数範囲がタスク定義と一致 |

既存タスクでは主に閾値 `0.05` を使用します。正確な条件は各 `tasks/*.py` が正本です。

## 出力レコードの主なフィールド

```text
experiment_id
condition_id
intervention
model
model_spec
task_id
seed
base_seed
L0 / L1 / L2 / L3
L2_distance
error_category / error_message
n_rounds
first_success_round
tokens_in / tokens_out / total_tokens
elapsed_sec
estimated_cost_usd
rounds[]
```

`rounds[]` には以下を保存します。

```text
round
round_seed
feedback_type
code_sha256
extracted_code
actual_distribution
L0 / L1 / L2 / L3
L2_distance
error_category / error_message
tokens_in / tokens_out / total_tokens
elapsed_sec
estimated_cost_usd
```

## manifest

各実験ディレクトリの `manifest.json` に、少なくとも次を保存します。

- experiment ID
- 実行 config 全体
- config hash
- 実行日時
- Git commit hash（Git repo の場合）
- Python version
- Qiskit / Qiskit Aer version
- LLM client library versions
- 予定 records 数
- 共有初期生成数
- sanity check 結果

## token / cost

`tokens_in`, `tokens_out`, `total_tokens` は各 record と各 round に保存します。

料金はモデル価格をコードへ固定しません。価格は変動するため、必要な場合だけ config の `pricing` にその実験時点の値を明示します。

```json
"pricing": {
  "provider:model-name": {
    "input_per_million_usd": 0.0,
    "output_per_million_usd": 0.0
  }
}
```

`pricing` がないモデルの `estimated_cost_usd` は `null` です。ローカル LLM は API 課金がないため、通常は空のままで構いません。

## sanity check

実験終了時に以下を自動確認します。

- planned record がすべて存在するか
- 重複 record がないか
- 各 `(model, task, seed)` で全 condition が揃っているか
- required field が欠けていないか
- `n_rounds` と `rounds[]` の長さが一致するか
- correction round が `max_rounds` を超えていないか
- `first_success_round` と round 履歴が一致するか
- baseline に correction round がないか
- 条件間の round 0 の `code_sha256` と評価結果が一致するか
- token total が input + output と一致するか

結果は `sanity_report.json` に保存します。

単独実行もできます。

```bash
python -m scripts.sanity_check \
  --config experiments/intervention_compare_v2.json \
  --results results/intervention_compare_v2/raw.jsonl
```

## 自動集計

実験終了後に次を生成します。

### `summary.csv`

condition / model / task ごとの L0〜L3 成功率、平均 first success、token、時間、cost。

### `paired_effects.csv`

baseline に対する同一 `(model, task, seed)` 比較。

- baseline L2 rate
- intervention L2 rate
- paired gain
- Rescue Rate
- Regression Rate

Regression は、初期 round の到達段階より最終 round の到達段階が下がった場合として集計します。

### `rescue_rates.csv`

round 0 の `error_category` ごとの救出数・救出率。

### `success_by_round.csv`

`round k` までに初回 L2 成功した割合を累積集計します。

> Self-Refine の反復は独立生成ではないため、これは `pass@k` とは呼ばず `success-by-round-k` として扱います。独立候補生成の pass@k は将来の拡張対象です。

## ver1 互換コマンド

既存実験を再現するため、`run_baseline.py` / `analyze.py` は残しています。

```bash
python -m scripts.run_baseline --mock --seeds 1 --out results/mock.jsonl
python -m scripts.analyze results/mock.jsonl
```

`--refine` も互換用に使用できますが、新規の介入比較実験では `scripts.run_experiment` を使用してください。

## 自己テスト

```bash
pytest tests/ -v
```

API キーは不要です。Qiskit evaluator のテストには Qiskit / Qiskit Aer が必要です。

## 注意事項

- `.env` と API key はコミットしない
- 実験 config を変更した場合は別 experiment ID を使うか、既存結果との混在を避ける
- `manifest.json` と実験に使った config は結果と一緒に保存する
- 商用モデルは seed を直接サポートしない場合がある。そのため ver2 は共有初期生成を条件間比較の基準にする
- Task Level は現在の ver2 には含めない。将来必要になった時点で `task_id` に対するメタデータとして追加する
