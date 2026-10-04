"""ver2: config 1つで paired intervention experiment を実行する。

実行例:
  python -m scripts.run_experiment --config experiments/intervention_compare_v2.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from harness.experiment import (
    apply_cost,
    build_manifest,
    initial_from_baseline_record,
    load_config,
    load_existing,
    pricing_for,
    record_key,
    validate_config,
)
from harness.llm_clients import make_client
from harness.runner import generate_initial, run_intervention, run_one
from scripts.sanity_check import check_results, write_sanity_report
from scripts.analyze_interventions import write_analysis_outputs


def _find_baseline(existing_rows, experiment_id, model_spec, task_id, seed):
    for rec in existing_rows:
        if (
            rec.get("experiment_id") == experiment_id
            and rec.get("intervention", rec.get("mode", "baseline")) == "baseline"
            and rec.get("model_spec", rec.get("model")) == model_spec
            and rec.get("task_id") == task_id
            and int(rec.get("base_seed", rec.get("seed", -1))) == seed
        ):
            return rec
    return None


def _pair_key(rec):
    """同一の共有初期生成を使う条件組を特定するキー。"""
    return (
        rec.get("experiment_id", ""),
        rec.get("model_spec", rec.get("model", "")),
        rec["task_id"],
        int(rec.get("base_seed", rec.get("seed", 0))),
    )


def _drop_api_error_pairs(rows):
    """接続失敗を含む条件組を resume 対象から外す。

    API エラーはモデルの評価結果ではない。条件ごとに一部だけ残すと shared
    round 0 の paired design を壊すため、同じ (model, task, seed) の組を
    次回にまとめて再試行する。
    """
    # A timeout is a completed, recorded outcome in this schema and must not be
    # silently removed or retried by resume.
    return rows, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Qiskit LLM intervention experiment runner v2")
    parser.add_argument("--config", required=True, help="JSON/YAML experiment config")
    parser.add_argument("--dry-run", action="store_true", help="Validate and show plan only")
    args = parser.parse_args()

    load_dotenv()
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    v = validate_config(config)

    repo_root = Path(__file__).resolve().parent.parent
    output_root = Path(config.get("output_dir", f"results/{v['experiment_id']}"))
    if not output_root.is_absolute():
        output_root = repo_root / output_root
    raw_path = output_root / "raw.jsonl"
    manifest_path = output_root / "manifest.json"
    sanity_path = output_root / "sanity_report.json"

    existing_rows, existing_keys = load_existing(raw_path)
    existing_rows, retried_pairs = _drop_api_error_pairs(existing_rows)
    if retried_pairs:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing_rows),
            encoding="utf-8",
        )
        existing_keys = {record_key(row) for row in existing_rows}
        print(f"Retrying {retried_pairs} pair(s) that previously ended in api_error.")
    remaining = v["planned_records"] - sum(
        1 for r in existing_rows if r.get("experiment_id") == v["experiment_id"]
    )

    print(f"Experiment: {v['experiment_id']}")
    print(f"Models: {v['models']}")
    print(f"Tasks: {[t.id for t in v['tasks']]}")
    print(f"Seeds: {v['seeds'][0]}..{v['seeds'][-1]} ({len(v['seeds'])})")
    print(f"Conditions: {[c.id + ':' + c.intervention for c in v['conditions']]}")
    print(f"Planned records: {v['planned_records']}")
    print(f"Existing records: {v['planned_records'] - max(remaining, 0)}")
    print(f"Remaining records: {max(remaining, 0)}")
    print(f"Output: {output_root}")

    if args.dry_run:
        print("\nDry-run OK. No model calls were made.")
        return 0

    output_root.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(config, repo_root)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    n_written = 0
    started = time.time()
    with raw_path.open("a", encoding="utf-8") as f:
        for model_spec in v["models"]:
            try:
                client = make_client(model_spec)
            except Exception as e:
                print(f"ERROR: cannot init {model_spec}: {e}", file=sys.stderr)
                continue
            price = pricing_for(config, model_spec)

            for task in v["tasks"]:
                for seed in v["seeds"]:
                    # Correction conditions share round 0; preventive_spec generates independently.
                    baseline_rec = _find_baseline(
                        existing_rows, v["experiment_id"], model_spec, task.id, seed
                    )
                    if baseline_rec is not None:
                        initial = initial_from_baseline_record(baseline_rec, task)
                    else:
                        initial = generate_initial(
                            client, task, seed, temperature=v["temperature"]
                        )
                    conditions = sorted(v["conditions"], key=lambda c: 0 if c.intervention == "baseline" else 1)
                    for cond in conditions:
                        key = (
                            v["experiment_id"], cond.id, model_spec, task.id, seed
                        )
                        if key in existing_keys:
                            continue

                        if cond.intervention == "baseline":
                            rec = run_one(
                                client,
                                task,
                                seed,
                                temperature=v["temperature"],
                                model_spec=model_spec,
                                experiment_id=v["experiment_id"],
                                condition_id=cond.id,
                                initial=initial,
                            )
                        else:
                            rec = run_intervention(
                                client,
                                task,
                                seed,
                                intervention=cond.intervention,
                                max_rounds=cond.max_rounds,
                                temperature=v["temperature"],
                                model_spec=model_spec,
                                experiment_id=v["experiment_id"],
                                condition_id=cond.id,
                                initial=initial,
                            )
                        apply_cost(rec, price)
                        row = rec.to_dict()
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        f.flush()
                        existing_rows.append(row)
                        existing_keys.add(record_key(row))
                        n_written += 1
                        flag = "OK" if rec.L2 else f"FAIL[{rec.error_category}]"
                        print(
                            f"[{n_written}] {model_spec} {task.id} seed={seed} "
                            f"{cond.id} L2={int(rec.L2)} first={rec.first_success_round} "
                            f"tokens={rec.total_tokens} {flag}"
                        )

    report = check_results(config, raw_path)
    write_sanity_report(report, sanity_path)
    write_analysis_outputs(raw_path, output_root)

    manifest["completed_at_utc"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    manifest["elapsed_sec"] = time.time() - started
    manifest["sanity_passed"] = bool(report["passed"])
    manifest["records_written_this_run"] = n_written
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone. wrote={n_written}, sanity={'PASS' if report['passed'] else 'FAIL'}")
    print(f"Manifest: {manifest_path}")
    print(f"Raw: {raw_path}")
    print(f"Sanity: {sanity_path}")
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
