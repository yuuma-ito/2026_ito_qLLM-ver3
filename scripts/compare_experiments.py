"""Compare public summaries; compute changes only within matching experiment cohorts."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from harness.experiment import load_config, validate_config
from harness.run_state import ROOT

FIELDS = ["experiment_id", "completed_at", "cohort_id", "verification", "model_spec",
          "condition_id", "intervention", "n", "L2_rate", "rescue_rate",
          "avg_elapsed_sec", "avg_total_tokens", "previous_experiment_id", "L2_change_pp"]


def cohort(config, manifest):
    plan = validate_config(config)
    signature = {"pairs": sorted((t, s) for _, t, s in plan["pair_keys"]),
                 "conditions": [(c.id, c.intervention, c.max_rounds) for c in plan["conditions"]],
                 "temperature": plan["temperature"], "generation_settings": config.get("generation_settings", {}),
                 "prompt_fingerprints": manifest.get("prompt_fingerprints", {}),
                 "schema_version": manifest.get("schema_version"),
                 "evaluation_environment": {key: manifest.get("environment", {}).get(key)
                                            for key in ("qiskit", "qiskit_aer")},
                 "model_digest": manifest.get("comparison_model_digest")}
    # Each model has its own comparison key; duplicate model grids do not change the cohort.
    signature["pairs"] = sorted(set(signature["pairs"]))
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]


def load_summary(output: Path):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    config_path = output / "experiment_config.json"
    config = load_config(config_path) if config_path.exists() else manifest["config"]
    if not isinstance(config, dict):
        raise ValueError("Experiment config must be an object")
    plan = validate_config(config)
    if plan["experiment_id"] != manifest["experiment_id"]:
        raise ValueError("Manifest/config experiment ID mismatch")
    if not manifest.get("sanity_passed"):
        raise ValueError("Run is not complete with sanity PASS")
    verification = "sanity_only"
    model_digests = {}
    automation = output / "automation_report.json"
    if automation.exists():
        report = json.loads(automation.read_text())
        if not isinstance(report, dict):
            raise ValueError("Automation report must be an object")
        verification = "automation_pass" if report.get("passed") else "automation_failed"
        model_digests = {item["name"]: item.get("digest") for item in report.get("shared_server", {}).get("models", [])}
    grouped = {}
    with (output / "summary_by_condition.csv").open(encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            key = (item["model_spec"], item["condition_id"], item["intervention"])
            group = grouped.setdefault(key, {"n": 0, "L2_rate": 0, "avg_elapsed_sec": 0, "avg_total_tokens": 0})
            n = int(item["n"])
            if n <= 0:
                raise ValueError("Invalid comparison group size")
            group["n"] += n
            for metric in ("L2_rate", "avg_elapsed_sec", "avg_total_tokens"):
                value = float(item[metric])
                if not math.isfinite(value) or value < 0 or (metric == "L2_rate" and value > 1):
                    raise ValueError("Invalid comparison metric")
                group[metric] += value * n
    expected = {(m, c.id, c.intervention): sum(pair[0] == m for pair in plan["pair_keys"])
                for m in plan["models"] for c in plan["conditions"]
                if any(pair[0] == m for pair in plan["pair_keys"])}
    if {key: value["n"] for key, value in grouped.items()} != expected:
        raise ValueError("Comparison summary sizes do not match the experiment plan")
    rescues = {}
    with (output / "rescue_rates_by_error.csv").open(encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            key = (item["model_spec"], item["intervention"])
            group = rescues.setdefault(key, [0, 0])
            group[0] += int(item["rescued"])
            group[1] += int(item["n_baseline_failures"])
    result = []
    for (model, condition, intervention), metrics in sorted(grouped.items()):
        if metrics["n"] <= 0:
            raise ValueError("Empty comparison group")
        for metric in ("L2_rate", "avg_elapsed_sec", "avg_total_tokens"):
            metrics[metric] /= metrics["n"]
        rescued, failures = rescues.get((model, intervention), [0, 0])
        model_config = dict(config, models=[model])
        if "pairs" in config:
            model_config["pairs"] = [p for p in config["pairs"] if p["model"] == model]
        result.append({"experiment_id": manifest["experiment_id"],
                       "completed_at": manifest.get("completed_at_utc", manifest["created_at_utc"]),
                       "cohort_id": cohort(model_config, dict(manifest, comparison_model_digest=model_digests.get(model.removeprefix("ollama:")))),
                       "verification": verification,
                       "model_spec": model, "condition_id": condition, "intervention": intervention,
                       **metrics, "rescue_rate": rescued / failures if failures else "",
                       "previous_experiment_id": "", "L2_change_pp": ""})
    return result


def comparison(outputs):
    rows, skipped = [], []
    for output in sorted(set(Path(p).resolve() for p in outputs)):
        try:
            rows.extend(load_summary(output))
        except (OSError, ValueError, KeyError, TypeError):
            skipped.append(output.name)
    previous = {}
    for row in sorted(rows, key=lambda r: (r["completed_at"], r["experiment_id"])):
        key = (row["cohort_id"], row["model_spec"], row["condition_id"])
        # Only automation-verified experiments are used to calculate changes.
        if row["verification"] == "automation_pass":
            if key in previous:
                old = previous[key]
                row["previous_experiment_id"] = old["experiment_id"]
                row["L2_change_pp"] = 100 * (row["L2_rate"] - old["L2_rate"])
            previous[key] = row
    return rows, skipped


def write_comparison(outputs, destination: Path):
    rows, skipped = comparison(outputs)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "comparison_by_condition.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    lines = ["# 実験比較", "", "公開用の集計値による記述的比較です。設定・対象task/seed・promptが一致し、自動検証を通過した実験のみ成功率の差を計算します。", "",
             "| 実験 | モデル | 条件 | 件数 | L2成功率 | 救済率 | 平均秒 | 前回との差(pp) | 検証 |",
             "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for row in sorted(rows, key=lambda r: (r["completed_at"], r["experiment_id"], r["model_spec"], r["condition_id"])):
        rescue = f"{100 * row['rescue_rate']:.1f}%" if row["rescue_rate"] != "" else "—"
        change = f"{row['L2_change_pp']:+.1f}" if row["L2_change_pp"] != "" else "—"
        labels = [str(row[k]).replace("|", "\\|").replace("\n", " ") for k in ("experiment_id", "model_spec", "condition_id")]
        lines.append(f"| {' | '.join(labels)} | {row['n']} | {100 * row['L2_rate']:.1f}% | {rescue} | {row['avg_elapsed_sec']:.2f} | {change} | {row['verification']} |")
    lines.extend(["", "共有round 0は条件ごとの集計に含まれます。集計値の実行時間は実験全体の壁時計時間とは異なります。少数seedの差から有意差や因果効果を断定しないでください。"])
    if skipped:
        lines.extend(["", "未完了・不正・集計不足のため除外した出力: " + ", ".join(skipped)])
    (destination / "comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="*", help="Run directories; default is results/*")
    parser.add_argument("--out-dir", default="results/comparisons")
    args = parser.parse_args(argv)
    outputs = [ROOT / p for p in args.runs] if args.runs else [p for p in (ROOT / "results").glob("*") if p.is_dir() and (p / "manifest.json").exists()]
    rows = write_comparison(outputs, ROOT / args.out_dir)
    print(f"Comparison written: {len(rows)} model/condition groups")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
