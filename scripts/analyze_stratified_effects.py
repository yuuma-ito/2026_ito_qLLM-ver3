"""Compare verified saved evaluations by source, model, difficulty and seed.

No model calls or generated-code execution. A fixed presentation snapshot guards
source identities and raw hashes; CSVs contain aggregate statistics only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from scripts.analyze_reach_levels import INTERVENTIONS, LEVELS, REPAIRS, analyze_levels, reached
from scripts.analyze_interventions import _write
from scripts.automate_experiment import verify
from scripts.sanity_check import _load_rows

GROUPINGS = {
    "overall": (), "model": ("model_spec",), "difficulty": ("task_difficulty",),
    "seed": ("base_seed",), "seed_block": ("seed_block",),
    "model_difficulty": ("model_spec", "task_difficulty"),
    "model_seed_block": ("model_spec", "seed_block"),
    "model_difficulty_seed_block": ("model_spec", "task_difficulty", "seed_block"),
    "model_seed": ("model_spec", "base_seed"),
    "model_difficulty_seed": ("model_spec", "task_difficulty", "base_seed"),
    "model_difficulty_error": ("model_spec", "task_difficulty", "baseline_error_category"),
}
DIMENSIONS = ("model_spec", "task_difficulty", "base_seed", "seed_block", "baseline_error_category")
COUNTS = (
    "n_pairs", "baseline_L2_success", "baseline_L2_failure", "baseline_L3_success", "baseline_L3_failure",
    "final_L2_success", "final_L3_success", "L2_rescued", "L3_rescued", "L2_regressed", "L3_regressed",
    "stage_improved", "stage_unchanged", "stage_worsened", "partial_improvement",
    "remaining_L3_failure", "initial_L3_success_unmodified", "repair_attempted",
)
RATES = {
    "L2_rescue_rate": ("L2_rescued", "baseline_L2_failure"),
    "L3_rescue_rate": ("L3_rescued", "baseline_L3_failure"),
    "partial_improvement_rate": ("partial_improvement", "baseline_L3_failure"),
    "stage_worsening_rate": ("stage_worsened", "n_pairs"),
    "L3_regression_rate": ("L3_regressed", "baseline_L3_success"),
    "final_L3_success_rate": ("final_L3_success", "n_pairs"),
}


def analyze_strata(records):
    sources = defaultdict(list)
    identities = set()
    for row in records:
        source = row["experiment_id"]
        seed = int(row.get("base_seed", row["seed"]))
        identity = (row["model_spec"], row["task_id"], seed, row["intervention"])
        if identity in identities:
            raise ValueError("Overlapping source model/task/seed/condition")
        identities.add(identity)
        sources[source].append(row)
    if not sources:
        raise ValueError("No source records")
    for rows in sources.values():
        analyze_levels(rows)  # validates levels, complete pairs and shared round 0

    groups = defaultdict(Counter)
    overlaps = defaultdict(Counter)
    final_errors = Counter()
    for source, rows in sources.items():
        pairs = defaultdict(dict)
        for row in rows:
            seed = int(row.get("base_seed", row["seed"]))
            if not 0 <= seed <= 19:
                raise ValueError("This analysis requires seed 0--19")
            pairs[(row["model_spec"], row["task_id"], seed)][row["intervention"]] = row
        for (model, task, seed), conditions in pairs.items():
            baseline = conditions["baseline"]
            start = LEVELS.index(reached(baseline))
            dims = dict(model_spec=model, task_difficulty=baseline["task_difficulty"], base_seed=seed,
                        seed_block="0-9" if seed < 10 else "10-19",
                        baseline_error_category=baseline["error_category"])
            for condition, row in conditions.items():
                if row["task_difficulty"] != dims["task_difficulty"]:
                    raise ValueError("Difficulty mismatch within pair")
                for scope, source_id in (("source", source), ("pooled", "")):
                    final_errors[(scope, source_id, model, dims["task_difficulty"], dims["seed_block"],
                                  condition, row["failure_stage"], row["error_category"])] += 1
            for condition in INTERVENTIONS:
                row = conditions[condition]
                end = LEVELS.index(reached(row))
                repair = condition in REPAIRS
                rounds = row["rounds"]
                counts = dict(n_pairs=1,
                    baseline_L2_success=int(baseline["L2"]), baseline_L2_failure=int(not baseline["L2"]),
                    baseline_L3_success=int(baseline["L3"]), baseline_L3_failure=int(not baseline["L3"]),
                    final_L2_success=int(row["L2"]), final_L3_success=int(row["L3"]),
                    L2_rescued=int(not baseline["L2"] and row["L2"]),
                    L3_rescued=int(not baseline["L3"] and row["L3"]),
                    L2_regressed=int(baseline["L2"] and not row["L2"]),
                    L3_regressed=int(baseline["L3"] and not row["L3"]),
                    stage_improved=int(end > start), stage_unchanged=int(end == start),
                    stage_worsened=int(end < start),
                    partial_improvement=int(end > start and not row["L3"]),
                    remaining_L3_failure=int(not row["L3"]),
                    initial_L3_success_unmodified=int(repair and baseline["L3"] and len(rounds) == 1),
                    repair_attempted=int(repair and len(rounds) > 1))
                for scope, source_id in (("source", source), ("pooled", "")):
                    for name, fields in GROUPINGS.items():
                        groups[(scope, source_id, name, condition, tuple(dims[f] for f in fields))].update(counts)
            if not baseline["L3"]:
                feedback = conditions["execution_feedback"]["L3"]
                debugging = conditions["self_debugging"]["L3"]
                overlap = dict(baseline_L3_failure=1, both_rescued=int(feedback and debugging),
                               feedback_only=int(feedback and not debugging),
                               debugging_only=int(debugging and not feedback),
                               neither_rescued=int(not feedback and not debugging))
                for scope, source_id in (("source", source), ("pooled", "")):
                    for name, fields in GROUPINGS.items():
                        overlaps[(scope, source_id, name, tuple(dims[f] for f in fields))].update(overlap)
    effects = []
    for (scope, source, grouping, condition, values), counts in sorted(groups.items()):
        entry = dict(scope=scope, source_experiment_id=source, grouping=grouping,
                     **dict.fromkeys(DIMENSIONS, ""), intervention=condition,
                     comparison_kind="repair" if condition in REPAIRS else "pre_generation",
                     **{k: counts[k] for k in COUNTS})
        entry.update(zip(GROUPINGS[grouping], values))
        for name, (num, den) in RATES.items():
            entry[name] = counts[num] / counts[den] if counts[den] else ""
        entry["small_L3_failure_denominator"] = counts["baseline_L3_failure"] < 10
        effects.append(entry)
    errors = [dict(scope=k[0], source_experiment_id=k[1], model_spec=k[2], task_difficulty=k[3],
                   seed_block=k[4], intervention=k[5], failure_stage=k[6], error_category=k[7], n=n)
              for k, n in sorted(final_errors.items())]
    overlap_rows = []
    for (scope, source, grouping, values), counts in sorted(overlaps.items()):
        entry = dict(scope=scope, source_experiment_id=source, grouping=grouping,
                     **dict.fromkeys(DIMENSIONS, ""), **counts)
        entry.update(zip(GROUPINGS[grouping],values))
        overlap_rows.append(entry)
    return dict(effects=effects, final_error_counts=errors, feedback_debug_overlap=overlap_rows)


def verify_aggregates(result):
    """Reconcile each partition and source total; check paired-count identities."""
    effects = result["effects"]
    for row in effects:
        n = row["n_pairs"]
        if (row["baseline_L3_success"] + row["baseline_L3_failure"] != n
                or row["baseline_L2_success"] + row["baseline_L2_failure"] != n
                or sum(row[k] for k in ("stage_improved", "stage_unchanged", "stage_worsened")) != n
                or row["final_L3_success"] != row["baseline_L3_success"] + row["L3_rescued"] - row["L3_regressed"]
                or row["final_L2_success"] != row["baseline_L2_success"] + row["L2_rescued"] - row["L2_regressed"]
                or row["partial_improvement"] > row["stage_improved"]):
            raise ValueError("Inconsistent paired counts")
    for scope, source in {(r["scope"], r["source_experiment_id"]) for r in effects}:
        for condition in INTERVENTIONS:
            selected = [r for r in effects if (r["scope"],r["source_experiment_id"],r["intervention"]) == (scope,source,condition)]
            total = next(r for r in selected if r["grouping"] == "overall")
            for grouping in GROUPINGS:
                for count in COUNTS:
                    if sum(r[count] for r in selected if r["grouping"] == grouping) != total[count]:
                        raise ValueError("Stratified partition does not reconcile")
    for condition in INTERVENTIONS:
        total = next(r for r in effects if r["scope"] == "pooled" and r["grouping"] == "overall" and r["intervention"] == condition)
        sources = [r for r in effects if r["scope"] == "source" and r["grouping"] == "overall" and r["intervention"] == condition]
        for count in COUNTS:
            if sum(r[count] for r in sources) != total[count]:
                raise ValueError("Source totals do not reconcile")
    for overlap in result["feedback_debug_overlap"]:
        if sum(overlap[k] for k in ("both_rescued","feedback_only","debugging_only","neither_rescued")) != overlap["baseline_L3_failure"]:
            raise ValueError("Overlap counts do not reconcile")
        matches = [r for r in effects if all(r[k] == overlap[k] for k in ("scope","source_experiment_id","grouping",*DIMENSIONS))]
        left = next(r for r in matches if r["intervention"] == "execution_feedback")
        right = next(r for r in matches if r["intervention"] == "self_debugging")
        if (left["baseline_L3_failure"] != overlap["baseline_L3_failure"]
                or left["L3_rescued"] != overlap["both_rescued"] + overlap["feedback_only"]
                or right["L3_rescued"] != overlap["both_rescued"] + overlap["debugging_only"]):
            raise ValueError("Overlap does not match rescue counts")
    return True


def write_report(result, output):
    """Write reproducible readable tables and convenient filtered CSVs."""
    effects = result["effects"]
    conditions = list(REPAIRS)
    names = {"self_refine":"R", "execution_feedback":"F", "self_debugging":"D", "preventive_spec":"P"}
    def selected(grouping, scope="pooled"):
        return [r for r in effects if r["grouping"] == grouping and r["scope"] == scope]
    def rescue(row):
        n=row["baseline_L3_failure"]
        return f"{row['L3_rescued']}/{n} ({100*row['L3_rescue_rate']:.1f}%)" if n else "—（初期失敗0件）"
    def table(grouping, fields, headers, scope="pooled"):
        grouped=defaultdict(dict)
        for row in selected(grouping,scope):
            grouped[tuple(row[f] for f in fields)][row["intervention"]]=row
        lines=["| "+" | ".join([*headers,"初期未達","R救出","F救出","D救出","部分改善 R/F/D","段階低下 R/F/D"])+" |",
               "| "+" | ".join(["---"]*len(headers)+["---:"]*6)+" |"]
        for values, by_condition in sorted(grouped.items()):
            rows=[by_condition[c] for c in conditions]
            label=[str(v).removeprefix("ollama:") for v in values]
            lines.append("| "+" | ".join([*label,str(rows[0]["baseline_L3_failure"]),*[rescue(r) for r in rows],
                "/".join(str(r["partial_improvement"]) for r in rows),
                "/".join(str(r["stage_worsened"]) for r in rows)])+" |")
        return lines
    overall={r["intervention"]:r for r in selected("overall")}
    overlap=next((r for r in result["feedback_debug_overlap"] if r["scope"]=="pooled" and r["grouping"]=="overall"),
                 dict(baseline_L3_failure=0,both_rescued=0,feedback_only=0,debugging_only=0,neither_rescued=0))
    def maxima(grouping,field):
        grouped=defaultdict(list)
        for row in selected(grouping):
            if row['intervention'] in REPAIRS: grouped[row[field]].append(row)
        notes=[]
        for label, rows in sorted(grouped.items()):
            best=max(r['L3_rescued'] for r in rows)
            winners='/'.join(names[r['intervention']] for r in rows if r['L3_rescued']==best)
            notes.append(str(label).removeprefix('ollama:')+('は修正型のL3救出なし' if not best else f'は{winners}が観測最多（{best}件）'))
        return '。'.join(notes)+'。'
    equality=all(r['L2_rescued']==r['L3_rescued'] for r in effects)
    small=[r for r in selected('model_difficulty') if r['intervention']=='self_refine' and r['baseline_L3_failure']<10]
    small_note='、'.join(f"{r['model_spec'].removeprefix('ollama:')}/{r['task_difficulty']}：{r['baseline_L3_failure']}件" for r in small)
    source_count=len({r['source_experiment_id'] for r in effects if r['scope']=='source'})
    pair_count=overall['self_refine']['n_pairs']
    lines=["# モデル 難度 seed別の介入効果", "",
        f"検証済み{source_count}実験・{pair_count*5:,}件の保存済み評価を層別集計した。全体のL3救出はF {rescue(overall['execution_feedback'])}、D {rescue(overall['self_debugging'])}。モデル・難度・seedブロックの内訳を示す。統合値は混合手順の記述的結果であり、出典別集計を併記する。", "",
        "R＝自己見直し、F＝実行結果提示、D＝自己デバッグ、P＝生成前注意事項。表の救出率の分母はbaselineのL3未達件数。部分改善はbaselineから段階が上昇したものの最終L3未達の件数。段階低下はbaselineから最終評価への比較であり、途中round間の一時的悪化やL3成功からの退行とは異なる。段階低下率の分母は全対応組数。Pは別プロンプトの独立生成としてCSVで区別する。", "",
        f"L2とL3救出はこのデータでは{'一致する' if equality else '異なる場合がある'}。別の定義としてCSVに保存した。初期失敗0件の救出率は空欄。分母10件未満にはsmall_L3_failure_denominatorを付け、少数例の割合から優劣を断定しない。", "",
        "## モデル別", "", *table("model",["model_spec"],["モデル"]), "",
        maxima('model','model_spec')+"最終L3未達でも部分改善があるため、最終成功数だけで修正過程を要約しない。", "",
        "## 難度別", "", *table("difficulty",["task_difficulty"],["難度"]), "",
        maxima('difficulty','task_difficulty')+"難度は本ハーネスのタスク分類であり、普遍的な尺度ではない。baseline失敗のモデル・原因構成が異なるため、難度別の総率だけで介入の適用を決めない。", "",
        "## モデルと難度の組合せ", "", *table("model_difficulty",["model_spec","task_difficulty"],["モデル","難度"]), "",
        "モデル・難度別に救出数、部分改善、段階低下を併記した。初期失敗が10件未満の層は参考値（"+small_note+"）。初期失敗0件では救出能力を評価する分母がない。", "",
        "## seedブロック別", "", *table("model_seed_block",["model_spec","seed_block"],["モデル","base seed"]), "",
        "seedブロックは実験の出典・実施時期と対応するため、差をseedだけの効果と解釈しない。schema 2.0と2.1をまたぐモデルでは診断文処理差も交絡する。同じschemaの出典間でも実施時期・初期生成が異なる。モデル×難度×seedブロックの詳細もeffects.csvに保存した。", "",
        "## 個別seed別", "", *table("seed",["base_seed"],["base seed"]), "",
        "個別seedの対応組数はCSVのn_pairs列で確認する。モデル×難度×seedへ細分すると、タスク数による小さい分母になる。個別seedの上下動は記述的な観測であり、乱数だけによる差や独立反復に基づく有意差として解釈しない。詳細はby_model_seed.csvとeffects.csvに保存した。", "",
        "## 出典別", "", *table("model_difficulty",["source_experiment_id","model_spec","task_difficulty"],["実験ID","モデル","難度"],scope="source"), "",
        "## FとDが救出した例の重なり", "",
        f"初期未達{overlap['baseline_L3_failure']}件のうち、両条件で救出{overlap['both_rescued']}件、Fのみ{overlap['feedback_only']}件、Dのみ{overlap['debugging_only']}件、どちらでも未達{overlap['neither_rescued']}件だった。同じ救出数でも対象例がすべて一致するとは限らない。モデル・難度・seed・出典別の対応付き内訳はfeedback_debug_overlap.csvを参照。", "",
        "## 次に確認する例", "",
        "FとDの片方だけで救出した例を、baselineの失敗類型とタスクごとに確認する。部分改善が最終L3へ届かない理由、修正型の段階低下例も候補となる。追加実験の必要性は、元実験の処理差と少数分母を踏まえて判断する。", "",
        "## 出典と再現", "",
        "固定出典：[20261013T_pooled_verified](../../presentation_sources/20261013T_pooled_verified/README.md)。生JSONLのhash・保存設定・既存集計を照合し、API障害・未分類エラーがない検証済み結果だけを使用した。新規生成・生成コードの再評価は行っていない。", "",
        "[manifest.json](manifest.json)に集計時点、保存設定、元rawのhash、CSVのhashを保存。[sanity_report.json](sanity_report.json)に分割集計と出典別合計の一致を記録。effects.csvは統合と出典別の全11区分を含む。final_error_counts.csvはモデル・難度・seedブロック・出典別の最終分類を含み、okの行は成功記録である。", "",
        "```bash", ".venv/bin/python -m scripts.analyze_stratified_effects \\",
        "  --snapshot docs/presentation_sources/20261013T_pooled_verified/results_snapshot.json \\",
        "  --out-dir docs/analysis/<新しい保存先>", "```", ""]
    (output/"README.md").write_text("\n".join(lines))
    for grouping in ("model","difficulty","model_difficulty","model_seed_block","model_seed"):
        rows=selected(grouping)
        _write(output/("by_"+grouping+".csv"),rows,list(rows[0]))
    rows=selected("model_difficulty",scope="source")
    _write(output/"by_source_model_difficulty.csv",rows,list(rows[0]))


def write_analysis(snapshot_path, output, root=Path.cwd()):
    snapshot_path, output, root = Path(snapshot_path), Path(output), Path(root)
    if output.exists():
        raise ValueError("Use a new analysis directory")
    snapshot = json.loads(snapshot_path.read_text())
    if not snapshot.get("pooled", {}).get("verified"):
        raise ValueError("A verified pooled snapshot is required")
    records, sources = [], []
    for run in snapshot["runs"]:
        source = (root / run["source_dir"]).resolve()
        if not source.is_relative_to((root / "results").resolve()):
            raise ValueError("Source must be under results")
        raw = source / "raw.jsonl"
        before = raw.read_bytes()
        if not before.endswith(b"\n") or hashlib.sha256(before).hexdigest() != run["raw_sha256"]:
            raise ValueError("Raw source differs from fixed snapshot")
        config = json.loads((source / "experiment_config.json").read_text())
        saved = json.loads((source / "automation_report.json").read_text())
        if config != run["config"] or not saved.get("passed") or not verify(config, source)["passed"]:
            raise ValueError("Source config or verification mismatch")
        rows = _load_rows(raw)
        levels = analyze_levels(rows)
        if len(rows) != run["records"] or any(levels[name] != run[name] for name in levels):
            raise ValueError("Evaluations differ from fixed snapshot")
        records.extend(rows)
        if raw.read_bytes() != before:
            raise ValueError("Source changed during read")
        sources.append(dict(experiment_id=run["experiment_id"], source_dir=run["source_dir"],
                            config=config, raw_sha256=run["raw_sha256"], records=len(rows),
                            schema_version=json.loads((source / "manifest.json").read_text())["schema_version"],
                            verified=True))
    pooled_levels = analyze_levels([dict(r, experiment_id=snapshot["pooled"]["experiment_id"]) for r in records])
    if len(records) != snapshot["pooled"]["records"] or any(pooled_levels[k] != snapshot["pooled"][k] for k in pooled_levels):
        raise ValueError("Pooled evaluations differ from fixed snapshot")
    result = analyze_strata(records)
    verify_aggregates(result)
    output.mkdir(parents=True)
    artifacts = []
    for name, rows in result.items():
        p = output / (name + ".csv")
        fields = list(rows[0]) if rows else ["scope", "source_experiment_id", "grouping", *DIMENSIONS,
            "baseline_L3_failure", "both_rescued", "feedback_only", "debugging_only", "neither_rescued"]
        _write(p, rows, fields)
        artifacts.append(dict(path=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest(), rows=len(rows)))
    write_report(result,output)
    for p in sorted(output.iterdir()):
        if p.name not in {a["path"] for a in artifacts}:
            artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    manifest = dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),
                    analysis_version="stratified_effects_v1",
                    analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    fixed_snapshot=str(snapshot_path), snapshot_sha256=hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
                    records=len(records), sources=sources, grouping_dimensions=GROUPINGS,
                    generated_new_code=False, reevaluated_generated_code=False, artifacts=artifacts,
                    limitations=["Mixed schema 2.0/2.1 diagnostic handling; source and seed block are confounded.",
                                 "Seeds are generation settings, not independent statistical replicates.",
                                 "Small denominators are shown; zero-denominator rates are blank.",
                                 "Preventive specification is independent generation, not code repair."])
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (output / "sanity_report.json").write_text(json.dumps(dict(passed=True, records=len(records),
        sources_verified=True, fixed_snapshot_matches=True, partition_counts_match=True,
        source_totals_match=True, paired_identities_match=True), indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = write_analysis(args.snapshot, args.out_dir)
    print(f"Verified stratified analysis: {len(result['effects'])} effect rows")


if __name__ == "__main__":
    main()
