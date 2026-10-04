# Qiskit LLM Code Generation Harness

Qiskitコード生成におけるモデル別・タスク難度別の成功率、失敗類型、介入効果を比較する実験ハーネスです。確定仕様は [docs/new_harness_spec.md](docs/new_harness_spec.md) を参照してください。

## 対象

- Models: `ollama:qwen2.5-coder:3b`, `ollama:qwen2.5-coder:7b`, `ollama:qwen2.5-coder:14b`
- Tasks: existing T1–T9 task set (10 tasks)
- Seeds: 0–9 in full configs
- Conditions: `baseline`, `self_refine`, `execution_feedback`, `self_debugging`, `preventive_spec`

`preventive_spec` は生成前に注意事項を追加して一度だけ生成する予防型介入です。修正roundを使う3つのrefinement条件とは性質が異なります。

Task difficulty is `easy` (T1, T2), `medium` (T3a, T3b, T4, T5), or `hard` (T6–T9); exact task IDs are documented in the specification.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Install and start Ollama separately, then ensure the three configured model tags are available locally. The harness does not create `.env` or require cloud API keys for the configured Ollama models.

## Quick debug

The quick config plans exactly 20 records (1 model × 2 tasks × 2 seeds × 5 conditions):

```bash
python -m scripts.run_experiment --config configs/quick_debug.json
```

The run writes `raw.jsonl`, `manifest.json`, `sanity_report.json`, and the analysis CSVs under `results/quick_debug/`.

## Full experiments

```bash
python -m scripts.run_experiment --config configs/full_qwen3b.json
python -m scripts.run_experiment --config configs/full_qwen7b.json
python -m scripts.run_experiment --config configs/full_qwen14b.json
python -m scripts.run_experiment --config configs/full_all_models.json
```

Full configurations are provided for reproducibility; do not run them as part of a quick debug check.

## Evaluation and records

L0 checks code/interface validity, L1 checks evaluability, L2 checks the expected output, and `structure_match` checks available structural constraints. L3 is always:

```text
L3 = L0 and L1 and L2 and structure_match
```

Each JSONL record includes task difficulty, condition, final and per-round metrics, timeout status, code/gate/depth counts, and a unified code diff and metric diff between round 0 and the final round. API timeout is reported as `api_timeout` and analyzed separately from code-quality outcomes.

## Analysis outputs

The analyzer writes:

- `summary_by_condition.csv`
- `summary_by_model.csv`
- `summary_by_task.csv`
- `summary_by_difficulty.csv`
- `rescue_rates_by_error.csv`
- `degradation_cases.csv`
- `baseline_regressions.csv`
- `timeout_summary.csv`
- `cost_runtime_summary.csv`

Run analysis again for an existing result file with:

```bash
python -m scripts.analyze_interventions results/quick_debug/raw.jsonl
```

`rescued` compares baseline L2 failure with intervention L2 success. `degradation_in_rounds` compares the initial and final stage scores within correction conditions only. `baseline_regression` compares baseline final L2 success with intervention final L2 failure, including `preventive_spec`. The CSV labels these separately; the legacy ambiguous label `regressed` is not used.

## Structure checks and limitations

The current task definitions provide qubit-count and gate-count-range checks, but not complete gate-family or depth oracles. Classical-bit and in-circuit measurement constraints are enforced only when a task definition explicitly provides them; unspecified requirements are left unconstrained. For distribution evaluation, the evaluator adds measurements to a copy only when the generated circuit has no measurements, preserving circuits that already measure. Structure matching does not require exact gate-sequence equality. Bit-order errors are detected heuristically when bit-reversing the expected distribution matches the observed distribution; other mismatches remain `wrong_output`.

Cost is null when no pricing is configured. Runtime, tokens, code lines, gate count, and depth are still summarized. See `docs/new_harness_spec.md` for the record schema, timeout rules, failure-category priority, and exact task mapping.
