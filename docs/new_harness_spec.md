# New Harness Specification

## Scope

This document defines the model-comparison harness for Qiskit code generation. It does not include API-hint ablation or the exp4 H0–H3 experiment.

## Models, tasks, difficulty, and seeds

Model specs use the `ollama:` provider prefix; the prefix is removed before the model name is sent to Ollama.

- `ollama:qwen2.5-coder:3b`
- `ollama:qwen2.5-coder:7b`
- `ollama:qwen2.5-coder:14b`

Use the existing ten T1–T9 tasks with the following metadata:

| Difficulty | Task IDs |
| --- | --- |
| easy | `T1_Bell`, `T2_GHZ` |
| medium | `T3a_DJ_constant`, `T3b_DJ_balanced`, `T4_BV_011`, `T5_Grover_11` |
| hard | `T6_QFT_001`, `T7_IQFT_001`, `T8_QPE_001`, `T9_Ansatz_001` |

Full configs run seeds 0–9, inclusive.

## Conditions

The harness compares `baseline`, `self_refine`, `execution_feedback`, `self_debugging`, and `preventive_spec`.

- `baseline`: one generation and evaluation.
- `self_refine`: initial generation followed by up to `max_rounds` self-review corrections.
- `execution_feedback`: initial generation followed by up to `max_rounds` corrections using evaluator feedback.
- `self_debugging`: initial generation followed by up to `max_rounds` explain/diagnose/repair corrections.
- `preventive_spec`: add the common preventive notice below before generation and generate/evaluate once. It is a generation-time intervention, not a correction-round intervention.

Preventive notice:

> 量子コード生成では以下の点に注意してください。
>
> 1. 指定された関数名と戻り値形式を必ず守ること。
> 2. Qiskitに存在しないAPIを使用しないこと。
> 3. 量子ビット数と古典ビット数を一致させること。
> 4. 測定結果のビット順序に注意すること。
> 5. 期待される測定分布または状態ベクトルと一致する回路を作ること。
> 6. 不要なゲートを追加しないこと。
> 7. 指定されたインターフェースを必ず実装すること。

Correction conditions share their initial generation for paired comparisons. `preventive_spec` uses a separate initial generation because its prompt differs from baseline.

## Evaluation

Keep L0 (valid code/interface), L1 (evaluable circuit), and L2 (expected distribution/statevector within the task threshold) as separate indicators. `structure_match` independently checks structural plausibility, at minimum expected qubit count and existing task gate-count bounds. Classical-bit and in-circuit measurement requirements are checked only when explicitly stated in task metadata (`expected_classical_bits`, `expected_measurement_count`, or `measurement_required`); absent metadata means no such constraint is imposed. For distribution evaluation, add measurements to a copy only if the generated circuit has no measurement operations, so explicit measurements are preserved without duplication. Circuit depth and gate count are recorded for analysis.

The current tasks do not provide a complete structural oracle for alternative equivalent decompositions. Therefore, preserve the existing per-task qubit-count and gate-count-range oracle and avoid exact gate-sequence matching. Extend with gate-family or depth bounds only when a task-specific oracle is available. Any stricter additions must accept equivalent circuits.

Always compute:

`L3 = L0 and L1 and L2 and structure_match`

## Failure categories and priority

Each final record has one primary `error_category`. Apply this precedence:

1. `api_timeout`
2. `syntax`
3. `import_error`
4. `interface_mismatch`
5. `build_error`
6. `qubit_count_mismatch`
7. `bit_order_error`
8. `wrong_output`
9. `unknown_error`

Missing/invalid required function, signature, or return form is `interface_mismatch`. Circuit construction exceptions are `build_error`. Clear qubit or classical-bit mismatch is `qubit_count_mismatch`. Use `bit_order_error` only when reversing measured bit strings makes the observed distribution match within threshold; otherwise use `wrong_output`. API timeout is an execution-stability outcome, not a code-quality failure.

## Timeout behavior

Detect timeout per LLM generation call using the existing client request timeout. Save one record for every condition. On a correction-round timeout, retain all previous round entries and append the timeout round as the final entry. The final record and timeout round must set `L0`, `L1`, `L2`, `structure_match`, and `L3` false; set `error_category` to `api_timeout` and `timeout_flag` true. Do not add a total experiment time limit or silently discard timeout records on resume.

## JSONL records

Each record stores:

`experiment_id`, `model_spec`, `task_id`, `task_difficulty`, `seed`, `temperature`, `condition_id`, `intervention`, `rounds`, `L0`, `L1`, `L2`, `structure_match`, `L3`, `L2_distance`, `error_category`, `error_message`, `tokens_in`, `tokens_out`, `total_tokens`, `elapsed_sec`, `code_lines`, `gate_count`, `circuit_depth`, `first_success_round`, `final_success`, and `timeout_flag`.

Keep generated code and evaluation metrics in each round. Add `code_diff_round0_final` as a unified diff and `metric_diff_round0_final` with from/to/delta values where numeric. Metric differences cover L0/L1/L2/structure_match/L3, error category, L2 distance, code lines, gate count, and depth. `final_success` means L3 success; `first_success_round` is the first round that reaches L3.

When no model pricing is configured, estimated cost is JSON `null`; analysis must not present it as zero.

## Paired outcomes

- `rescued`: the matched baseline final result has L2 false and the intervention final result has L2 true. `rescue_rates_by_error.csv` groups by the baseline error category.
- `degradation_in_rounds`: final `stage_score` is lower than initial `stage_score`. Apply only to `self_refine`, `execution_feedback`, and `self_debugging`.
- `baseline_regression`: matched baseline final L2 is true and intervention final L2 is false. Apply to the three correction interventions and `preventive_spec`.

Stage scores:

| Score | Condition |
| --- | --- |
| 0 | L0 false |
| 1 | L0 true, L1 false |
| 2 | L0/L1 true, L2 false |
| 3 | L0/L1/L2 true, structure_match false |
| 4 | L0/L1/L2/structure_match true |

Never use the ambiguous field/name `regressed`. `preventive_spec` is a pre-generation intervention and must be described separately from correction interventions in CSV documentation and README.

## Analysis CSVs

Write these outputs under the experiment output directory:

- `summary_by_condition.csv`
- `summary_by_model.csv`
- `summary_by_task.csv`
- `summary_by_difficulty.csv`
- `rescue_rates_by_error.csv`
- `degradation_cases.csv`
- `baseline_regressions.csv`
- `timeout_summary.csv`
- `cost_runtime_summary.csv`

The cost/runtime file always summarizes token counts, elapsed seconds, code lines, gate counts, and circuit depth. Cost remains null unless pricing is configured.

## Configs and quick debug

Full configs: `configs/full_qwen3b.json`, `configs/full_qwen7b.json`, `configs/full_qwen14b.json`, and `configs/full_all_models.json`.

`configs/quick_debug.json` uses model `ollama:qwen2.5-coder:3b`, tasks `T1_Bell` and `T3a_DJ_constant`, seeds 0 and 1, temperature 0.7, max rounds 3, all five conditions, and output directory `results/quick_debug`. It plans 20 records.

Quick debug is the only experiment to run during implementation verification. Do not run the full configs as part of implementation.

## GitHub publication

Keep the README aligned with this specification. Ignore `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `results/**/raw.jsonl`, `logs/`, and `.cache/`. Never include API keys or local environment files.

## Known structural-oracle limitation

Existing task definitions have qubit-count and gate-count-range constraints but no complete gate-family, classical-register, or circuit-depth oracle. Classical-bit and measurement requirements are not inferred when task metadata is absent. `bit_order_error` is a heuristic classification based on bit-reversed distribution comparison. Do not claim exact structure validation beyond those checks.
