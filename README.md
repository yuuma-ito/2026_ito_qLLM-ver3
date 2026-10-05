# Qiskit LLM Code Generation Harness

## 概要

量子回路コードの生成において、モデル・タスク難度・誤り種別・介入条件ごとに、生成品質と介入効果を比較する研究用ハーネスです。生成した Qiskit コードを実行・評価し、JSONL と分析 CSV に記録します。

このリポジトリは新ハーネス仕様に基づく実験用です。APIヒントの ablation、H0〜H3、exp4 は実装対象に含みません。詳細は [docs/new_harness_spec.md](docs/new_harness_spec.md) を参照してください。

## 対象モデル・タスク・条件

**モデル**（config上は `model_spec`、Ollamaに渡す際は `ollama:` を外した名前を使用）:

- `ollama:qwen2.5-coder:3b`
- `ollama:qwen2.5-coder:7b`
- `ollama:qwen2.5-coder:14b`

**タスク**：T1，T2，T3a，T3b，T4，T5，T6，T7，T8，T9 の計10タスクです。難度は次のように分類します。

| 難度 | タスク |
| --- | --- |
| easy（易） | `T1_Bell`，`T2_GHZ` |
| medium（中） | `T3a_DJ_constant`，`T3b_DJ_balanced`，`T4_BV_011`，`T5_Grover_11` |
| hard（難） | `T6_QFT_001`，`T7_IQFT_001`，`T8_QPE_001`，`T9_Ansatz_001` |

Full experiments の seed は 0〜9 です。比較する条件は次の5種類です。

- `baseline`：介入なし。初回生成のみ。
- `self_refine`：自己修正。モデル自身がコードを見直して修正します。
- `execution_feedback`：実行結果フィードバック。評価器のエラーや結果を使って修正します。
- `self_debugging`：自己デバッグ。説明・原因分析・修正を行います。
- `preventive_spec`：予防的仕様プロンプト。生成前に注意事項を追加し、修正 round を行わず1回だけ生成します。

`preventive_spec` は生成前介入であり、生成後に修正する3条件とは性質が異なります。

## セットアップ

以下は各コマンドを1行ずつ実行してください。

Linux / macOS:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
python -m pip install -r requirements.txt
```

Ollama を別途起動し、実験に使うモデルが利用可能なことを確認してください。設定済みの Ollama 実験ではクラウド API キーを必要としません。`.env` に実キーを保存・公開しないでください。

## Ollamaの接続設定

通常のローカル Ollama は `http://127.0.0.1:11434` を使います。何も設定しない場合もこのポートへ接続します。

s3 の共有 Ollama を使う場合は `http://127.0.0.1:11435` を指定します。Linux / macOS / s3 のシェルで次を実行してください。

```bash
export OLLAMA_HOST=http://127.0.0.1:11435
```

接続先で利用できるモデルを確認します。

```bash
curl http://127.0.0.1:11435/api/tags
```

このハーネスは `OLLAMA_BASE_URL` が設定されていればそれを優先し、未設定なら `OLLAMA_HOST` を接続先として使います。どちらも未設定なら既定の `http://127.0.0.1:11434` です。Ollama の REST 確認は `/api/tags`、ハーネスの生成要求は OpenAI 互換の `/v1` endpoint を利用します。

Windows PowerShell では次のように設定・確認できます。

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11435"
```

```powershell
Invoke-RestMethod http://127.0.0.1:11435/api/tags
```

## Quick debug

小規模確認には `configs/quick_debug.json` を使います。1モデル × 2タスク × 2 seed × 5条件で、合計20 records を計画します。

```bash
python -m scripts.run_experiment --config configs/quick_debug.json
```

実行後、JSONL が20件あることを確認します。

```bash
wc -l results/quick_debug/raw.jsonl
```

期待値:

```text
20 results/quick_debug/raw.jsonl
```

CSV の出力を確認します。

```bash
ls results/quick_debug/*.csv
```

JSONL の先頭 record を整形して確認します。

```bash
head -n 1 results/quick_debug/raw.jsonl | python -m json.tool
```

## Full experiments

以下は大規模実験です。Quick debug と設定・出力先を確認した後、必要な場合だけ各コマンドを個別に実行してください。

```bash
python -m scripts.run_experiment --config configs/full_qwen3b.json
```

```bash
python -m scripts.run_experiment --config configs/full_qwen7b.json
```

```bash
python -m scripts.run_experiment --config configs/full_qwen14b.json
```

```bash
python -m scripts.run_experiment --config configs/full_all_models.json
```

## 評価指標

- `L0`：生成コードが構文・必須インターフェースの条件を満たすか。
- `L1`：回路を構築し、タスクに応じた評価処理を実行できるか。
- `L2`：出力分布または状態ベクトルが期待値と許容距離内で一致するか。
- `structure_match`：回路構造の妥当性。利用可能なタスク別構造条件に合うかを独立に記録します。
- `L3`：`L0`，`L1`，`L2`，`structure_match` がすべて真の場合のみ真です。

```text
L3 = L0 and L1 and L2 and structure_match
```

API 呼び出しで `api_timeout` が起きた場合は、コード品質の失敗ではなく実行安定性の失敗として記録します。timeout record の `timeout_flag` は `true` です。

## 出力ファイル

実験ごとの出力先に、主に次のファイルを保存します。

- `raw.jsonl`：条件ごとの最終結果、round 履歴、生成コード、評価値、token・実行時間、timeout 状態、round 0 と最終 round の差分を含む JSON Lines。
- `manifest.json`：実験設定・再現性に関する情報。
- `sanity_report.json`：出力 record の整合性確認結果。

各 record には `task_difficulty`，`structure_match`，`code_lines`，`gate_count`，`circuit_depth` などを保存します。round 0 と最終 round のコード差分は `code_diff_round0_final`、指標差分は `metric_diff_round0_final` です。

## 分析CSV

実験後の分析では、出力先に次の CSV を生成します。

- `summary_by_condition.csv`：介入条件別の集計。
- `summary_by_model.csv`：モデル別の集計。
- `summary_by_task.csv`：タスク別の集計。
- `summary_by_difficulty.csv`：難度別の集計。
- `rescue_rates_by_error.csv`：baseline の失敗を介入が救出した割合を失敗類型別に集計。
- `degradation_cases.csv`：修正過程での評価段階低下の一覧。
- `baseline_regressions.csv`：baseline 成功から介入失敗に変わったケースの一覧。
- `timeout_summary.csv`：`api_timeout` と `timeout_flag` の別集計。
- `cost_runtime_summary.csv`：token 数、実行時間、コード行数、ゲート数、回路深さ等の集計。

`rescued`（救出）は baseline が `L2=False` で介入後が `L2=True` のケースです。`degradation_in_rounds`（修正過程での悪化）は修正型条件内で最終 round の評価段階が初期 round より低下したケースです。対象は `self_refine`，`execution_feedback`，`self_debugging` です。`baseline_regression`（baseline 成功から介入失敗への退行）は baseline が `L2=True` で介入後が `L2=False` となったケースです。`preventive_spec` も paired 比較に含みます。

既存 `raw.jsonl` を再分析する場合:

```bash
python -m scripts.analyze_interventions results/quick_debug/raw.jsonl
```

価格設定がない場合、cost は0ではなく `null` です。

## 構造チェックと制約

既存タスク定義にある量子ビット数とゲート数範囲を利用します。タスク定義に測定数・古典ビット数・測定要否が明示されていない場合、それらを一律に0とは要求しません。分布評価では、生成回路に測定がなければ評価用コピーに測定を追加し、測定があれば既存測定を保ちます。

全タスクに対する完全なゲート種・深さ oracle はありません。等価な回路を不当に失敗にしないため、厳密なゲート列一致は要求しません。`bit_order_error`（ビット順序誤り）はビット反転後に期待分布と一致するかで判定するヒューリスティックです。それ以外の出力不一致は `wrong_output` とします。

## GitHub公開時の注意

`.env`、API キー、個人用の設定ファイル、実験結果の `raw.jsonl` を公開しないでください。`.gitignore` は `.env`，`.venv/`，`__pycache__/`，`*.pyc`，`results/**/raw.jsonl`，`logs/`，`.cache/` を除外します。公開前に追加・変更ファイルに秘密情報が含まれないことを確認してください。

## 仕様書

実験条件、record schema、失敗類型と優先順位、timeout、差分、CSV、config の詳細は [docs/new_harness_spec.md](docs/new_harness_spec.md) に記載しています。
