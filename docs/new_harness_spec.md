# 新ハーネス仕様

## 1. 目的と対象範囲

本仕様は、Qiskit による量子回路コード生成実験で、モデル・タスク難度・失敗類型・介入条件ごとの生成品質、介入効果、実行コストを比較するハーネスを定義します。APIヒント ablation、H0〜H3、exp4 は本実装の対象外です。

## 2. 対象モデル・タスク・難度・seed

config の `model_spec` では provider prefix の `ollama:` を含む形式を使います。Ollama API に渡す際には prefix を外します。

- `ollama:qwen2.5-coder:3b` → `qwen2.5-coder:3b`
- `ollama:qwen2.5-coder:7b` → `qwen2.5-coder:7b`
- `ollama:qwen2.5-coder:14b` → `qwen2.5-coder:14b`

既存の T1〜T9 を使用します。T3 は T3a と T3b に分かれるため、合計10タスクです。

| `task_difficulty` | `task_id` |
| --- | --- |
| `easy`（易） | `T1_Bell`，`T2_GHZ` |
| `medium`（中） | `T3a_DJ_constant`，`T3b_DJ_balanced`，`T4_BV_011`，`T5_Grover_11` |
| `hard`（難） | `T6_QFT_001`，`T7_IQFT_001`，`T8_QPE_001`，`T9_Ansatz_001` |

Full experiments の seed は両端を含む0〜9です。

## 3. 介入条件

5条件を比較します。

- `baseline`（介入なし）：初回生成と評価を1回行います。
- `self_refine`（自己修正）：初回生成後、モデル自身の見直しに基づいて最大 `max_rounds` 回修正します。
- `execution_feedback`（実行結果フィードバック）：初回生成後、評価器のエラー・実行結果を提示して最大 `max_rounds` 回修正します。
- `self_debugging`（自己デバッグ）：説明・原因分析・修正の手順を使って最大 `max_rounds` 回修正します。
- `preventive_spec`（予防的仕様プロンプト）：共通注意事項を初期 prompt に加えて1回だけ生成します。修正 round はありません。

`preventive_spec` は生成前介入で、生成後に修正する3条件とは性質が異なります。baseline と初期 prompt が異なるため、同一の初期コードを共有しません。一方、`baseline_regression` の paired 比較には含めます。修正型3条件は共通初期生成を使い、paired 比較を行います。

`preventive_spec` に追加する共通 prompt:

> 量子コード生成では以下の点に注意してください。
>
> 1. 指定された関数名と戻り値形式を必ず守ること。
> 2. Qiskitに存在しないAPIを使用しないこと。
> 3. 量子ビット数と古典ビット数を一致させること。
> 4. 測定結果のビット順序に注意すること。
> 5. 期待される測定分布または状態ベクトルと一致する回路を作ること。
> 6. 不要なゲートを追加しないこと。
> 7. 指定されたインターフェースを必ず実装すること。

## 4. 評価指標と structure_match

評価段階を個別に保存します。

- `L0`：生成コードの構文と必須インターフェースが有効です。
- `L1`：回路を構築し、タスクの評価処理を実行できます。
- `L2`：測定分布または状態ベクトルがタスク期待値としきい値内で一致します。
- `structure_match`（回路構造の妥当性）：L2とは独立した構造妥当性指標です。
- `L3`：すべての前段階を満たす総合成功指標です。

必ず次式で `L3` を計算します。

```text
L3 = L0 and L1 and L2 and structure_match
```

したがって、`L2=False` かつ `L3=True` となる記録は許しません。

`structure_match` は、可能な範囲で以下を確認します。

1. 量子ビット数がタスク期待値と一致する。
2. 古典ビット数または測定数が、明示されたタスク要件と一致する。
3. 主要ゲート種が期待範囲に含まれる（タスク固有 oracle がある場合）。
4. ゲート数または回路深さがタスク許容範囲内である（oracle がある場合）。
5. 測定が必要なタスクでは、測定が適切に含まれる。

現行タスク定義では測定要否、期待測定数、期待古典ビット数が未指定の場合があります。その場合、測定数や古典ビット数に制約を推定して加えず、一律に古典ビット数0を要求しません。タスクに明示がある場合のみ、その要件に反しないことを検査します。分布評価は、生成回路に測定がないときだけ評価用コピーへ測定を追加します。生成回路に測定がある場合は既存の測定を保ち、二重追加しません。

既存 task oracle のゲート数範囲は回路ゲートを対象とし、測定操作を数えません。生成コードの測定を含む総操作数は、分析指標 `gate_count` として別途記録します。タスク固有 oracle がないゲート種・深さについては、一律の制限を作りません。等価な回路を不当に失敗させないよう、厳密なゲート列の完全一致は要求しません。

## 5. 失敗類型と優先順位

各最終 record に主因の `error_category` を1つ保存します。発生段階を優先し、`build_circuit()` 内の例外は型にかかわらず `build_error` とします。評価まで到達した場合、構造不一致、ビット順序誤り、出力不一致の順に主因を選びます。原因分類は次のとおりです。

1. `api_timeout`（APIタイムアウト）
2. `syntax`（構文エラー）
3. `import_error`（import エラー）
4. `interface_mismatch`（関数名・引数・戻り値形式等の不一致）
5. `build_error`（Qiskit 回路構築中の例外）
6. `qubit_count_mismatch`（量子ビット数、または明確な古典ビット数・測定数の不一致）
7. `bit_order_error`（ビット順序誤り）
8. `wrong_output`（実行可能だが出力分布・状態が期待と不一致）
9. `unknown_error`（上記に分類できないエラー）

関数名、戻り値形式、必須関数未定義などは `interface_mismatch` とします。Qiskit 回路生成中の例外は `build_error` です。ビット列を反転すると期待分布としきい値内で一致する場合に限り `bit_order_error` とします。自動判定が難しい出力不一致はまず `wrong_output` にします。

## 6. API timeout

timeout は実験全体ではなく、LLM 生成呼び出し単位で既存 API request timeout を使って判定します。API timeout はコード品質の失敗でなく実行安定性の失敗です。timeout が起きた条件も必ず record に保存します。

修正 round 中に timeout が起きた場合、そこまでの round 履歴を残し、timeout round を最終 round として追加します。最終評価では次を記録します。

- `L0 = false`
- `L1 = false`
- `L2 = false`
- `structure_match = false`
- `L3 = false`
- `error_category = api_timeout`
- `timeout_flag = true`

実験全体を打ち切る上限時間は設けません。timeout record を resume 時に黙って破棄しません。`timeout_summary.csv` で timeout を別集計します。

## 7. JSONL record と round 差分

各 record に次の項目を保存します。

`experiment_id`，`model_spec`，`task_id`，`task_difficulty`，`seed`，`temperature`，`condition_id`，`intervention`，`rounds`，`L0`，`L1`，`L2`，`structure_match`，`L3`，`L2_distance`，`failure_stage`，`error_category`，`exception_type`，`error_message`，`tokens_in`，`tokens_out`，`total_tokens`，`elapsed_sec`，`code_lines`，`gate_count`，`circuit_depth`，`first_success_round`，`final_success`，`timeout_flag`。

各 round に生成コードと評価指標を保持します。さらに次を保存します。

- `code_diff_round0_final`：round 0 と最終 round の unified diff 文字列。
- `metric_diff_round0_final`：可能な限り、各指標の `from`，`to`，数値指標の `delta`。

metric diff には `L0`，`L1`，`L2`，`structure_match`，`L3`，`failure_stage`，`error_category`，`exception_type`，`L2_distance`，`code_lines`，`gate_count`，`circuit_depth` の変化を含めます。`final_success` は最終 `L3` 成功、`first_success_round` は初めて `L3` 成功した round です。

価格設定がない場合の cost は数値0ではなく JSON `null` です。分析でも pricing が設定されない cost は空欄または `null` とし、0とは扱いません。

## 8. paired 効果：救出・修正過程の悪化・baseline 退行

3種類を別の概念・CSVで集計します。

- `rescued`（救出）：対応する baseline の最終 `L2=False`、介入条件の最終 `L2=True`。
- `degradation_in_rounds`（修正過程での悪化）：同じ介入条件内で最終 round の `stage_score` が初期 round より低いこと。対象は `self_refine`，`execution_feedback`，`self_debugging` のみです。`baseline` と `preventive_spec` は修正 round がないため対象外です。
- `baseline_regression`（baseline 成功から介入失敗への退行）：同じ `model_spec`，`task_id`，`seed` の baseline 最終 `L2=True` かつ介入最終 `L2=False`。対象は `self_refine`，`execution_feedback`，`self_debugging`，`preventive_spec` です。

`preventive_spec` は baseline と初期 prompt が異なりますが、介入によって baseline 成功ケースを失敗にしたかを見るため `baseline_regression` の paired 比較に含めます。これは生成前介入であり、修正型介入とは性質が異なることを README と CSV の説明に明記します。

`degradation_in_rounds` の段階点 `stage_score` は次のとおりです。

| score | 評価状態 |
| --- | --- |
| 0 | `L0=False` |
| 1 | `L0=True`，`L1=False` |
| 2 | `L0=True`，`L1=True`，`L2=False` |
| 3 | `L0=True`，`L1=True`，`L2=True`，`structure_match=False` |
| 4 | `L0=True`，`L1=True`，`L2=True`，`structure_match=True` |

`final_stage_score < initial_stage_score` のときだけ `degradation_in_rounds` と判定します。曖昧な名前 `regressed` は使いません。

## 9. 分析CSV

実験の出力ディレクトリに次の CSV を書き出します。

- `summary_by_condition.csv`：条件別。
- `summary_by_model.csv`：モデル別。
- `summary_by_task.csv`：タスク別。
- `summary_by_difficulty.csv`：難度別。
- `rescue_rates_by_error.csv`：baseline の失敗類型別 rescue 率。
- `degradation_cases.csv`：修正過程での悪化ケース。
- `baseline_regressions.csv`：baseline 退行ケース。
- `timeout_summary.csv`：API timeout の別集計。
- `cost_runtime_summary.csv`：token 数、経過秒、コード行数、ゲート数、回路深さ、および利用可能なら cost。

pricing の有無にかかわらず `tokens_in`，`tokens_out`，`total_tokens`，`elapsed_sec`，`code_lines`，`gate_count`，`circuit_depth` を集計します。pricing がないとき cost は `null` です。

## 10. config と quick_debug

Full config:

- `configs/full_qwen3b.json`
- `configs/full_qwen7b.json`
- `configs/full_qwen14b.json`
- `configs/full_all_models.json`

`configs/quick_debug.json` は小規模確認専用で、次の20条件組み合わせを計画します。

- model: `ollama:qwen2.5-coder:3b`
- tasks: `T1_Bell`，`T3a_DJ_constant`
- seeds: 0，1
- conditions: `baseline`，`self_refine`，`execution_feedback`，`self_debugging`，`preventive_spec`
- temperature: 0.7
- max rounds: 3
- output: `results/quick_debug`

実装時の動作確認では quick_debug のみを使い、Full experiments は実行しません。

## 11. GitHub 公開時の注意

`.env`，`.venv/`，`__pycache__/`，`*.pyc`，`results/**/raw.jsonl`，`logs/`，`.cache/` を Git から除外します。API キーや個人の実験データを含むファイルを commit/push しません。

## 12. 現行 oracle の制約

現行タスク定義には量子ビット数とゲート数範囲がありますが、全タスクに対するゲート種、古典レジスタ、測定数、回路深さの完全な oracle はありません。未指定要件を推測で制約にせず、利用可能な oracle の範囲だけを確認します。`bit_order_error` はビット反転後の分布比較によるヒューリスティックです。これらの制約を超える完全な構造検証を行うとは主張しません。


### 失敗した段階と原因の記録

`failure_stage` は失敗した段階、`error_category` は失敗原因を表します。最終recordと各roundに両方を保存し、`exception_type`（例外型名）と `error_message`（例外メッセージ）も記録します。例外のない判定失敗では `exception_type` は空文字です。成功時は `error_category = ok`、`failure_stage = unknown`、`exception_type` は空文字とします。

段階は `parse` / `import` / `exec` / `build` / `evaluate` / `api_call` / `unknown`。原因は `syntax` / `import_error` / `interface_mismatch` / `build_error` / `wrong_output` / `bit_order_error` / `qubit_count_mismatch` / `api_timeout` / `unknown_error` です。

- 構文解析失敗は `parse` / `syntax`、トップレベルのimport失敗は `import` / `import_error`。
- `exec()` 中の存在しない属性・メソッドへの `AttributeError` は `exec` / `interface_mismatch`。GHZ seed 6 self_debugging の `result.counts` はこの分類に該当し、接続障害・タイムアウトには含めません。
- `build_circuit()` 内の例外は、トップレベルから呼び出された場合も `build` / `build_error`。戻り値が QuantumCircuit でない場合は `build` / `interface_mismatch`。
- 出力・構造の不一致は `evaluate`。モデル呼び出し障害は `api_call` で、タイムアウトの原因は `api_timeout`、それ以外の未分類障害は `unknown_error` とし、`generation_error` も保持します。

既存の原因別分析は `error_category` を使用します。追加の `failure_stage_summary.csv` は最終recordの失敗だけをモデル・条件・段階・原因・例外型別に数えます（roundは重複加算しません）。

スキーマ2.1から新規生成記録にこれらのフィールドを保存します。旧JSONLは書き換えず、読み込み時に保存済みの原因・例外メッセージ・L0/L1情報から保守的に補います。補った記録には `failure_metadata_source = legacy_inference_v1` を付け、原因を変更した場合は `original_error_category` も保持します。保存情報で特定できない段階・例外型は `unknown`・空文字です。評価結果・生成コード・seedは変更せず、再生成・再評価は行いません。稼働中の旧プロセスは旧形式の保存を続けますが、レポート・通知・集計・再検証は補完後の分類を使用します。

`exec` 段階の `QiskitError: No counts for experiment ...` は、countsも保存した状態ベクトルもないResultに `get_counts()` を呼んだインターフェース誤用として `interface_mismatch` に分類します。他のQiskitErrorを一律にこの分類へ移しません。`build_circuit()` 内で同じ例外が生じた場合は `build / build_error` です。DJ constant seed 9 の観測例と介入候補は [分類確認記録](dj_seed9_failure_classification.json) に保存しました。LLMへの介入効果は未検証です。
