"""Audit F-only and D-only L3 rescues using fixed, verified saved evaluations."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from harness.failure_metadata import normalize_record
from scripts.analyze_reach_levels import analyze_levels, reached
from scripts.analyze_interventions import _write
from scripts.analyze_stratified_effects import analyze_strata, verify_aggregates
from scripts.automate_experiment import verify

F, D = "execution_feedback", "self_debugging"
GROUPINGS = {"overall": (), "baseline_error": ("baseline_error_category",),
             "task": ("task_id",), "model": ("model_spec",), "difficulty": ("task_difficulty",),
             "model_error": ("model_spec", "baseline_error_category"),
             "model_task": ("model_spec", "task_id")}
DIMENSIONS = ("model_spec", "task_id", "task_difficulty", "baseline_error_category")
COUNT_FIELDS = ("baseline_L3_failure", "both_rescued", "feedback_only", "debugging_only", "neither_rescued")


def compare_pairs(records):
    sources = defaultdict(list)
    for row in records:
        sources[row["experiment_id"]].append(row)
    # Validates non-overlap across sources, complete pairs, levels and shared initial code.
    strata = analyze_strata(records)
    verify_aggregates(strata)
    groups, cases, trajectories = defaultdict(Counter), [], []
    for source, rows in sources.items():
        pairs = defaultdict(dict)
        for row in rows:
            pairs[(row["model_spec"], row["task_id"], row["base_seed"])][row["intervention"]] = row
        for (model, task, seed), conditions in sorted(pairs.items()):
            baseline, feedback, debugging = (conditions[k] for k in ("baseline", F, D))
            if baseline["L3"]:
                continue
            dims = dict(model_spec=model, task_id=task, task_difficulty=baseline["task_difficulty"],
                        baseline_error_category=baseline["error_category"])
            left, right = feedback["L3"], debugging["L3"]
            counts = dict(baseline_L3_failure=1, both_rescued=int(left and right),
                          feedback_only=int(left and not right), debugging_only=int(right and not left),
                          neither_rescued=int(not left and not right))
            for scope, source_id in (("source", source), ("pooled", "")):
                for name, fields in GROUPINGS.items():
                    groups[(scope, source_id, name, tuple(dims[k] for k in fields))].update(counts)
            if left == right:
                continue
            winner, loser = (feedback, debugging) if left else (debugging, feedback)
            case_id = hashlib.sha256(json.dumps([source,model,task,seed], ensure_ascii=False).encode()).hexdigest()[:16]
            case = dict(case_id=case_id, source_experiment_id=source, **dims, base_seed=seed,
                        winner="F" if left else "D", baseline_level=reached(baseline),
                        baseline_failure_stage=baseline["failure_stage"],
                        baseline_exception_type=baseline["exception_type"],
                        winner_first_success_round=winner["first_success_round"],
                        winner_final_level=reached(winner), loser_final_level=reached(loser),
                        loser_final_error_category=loser["error_category"],
                        loser_final_failure_stage=loser["failure_stage"],
                        loser_final_exception_type=loser["exception_type"],
                        winner_round_count=len(winner["rounds"]), loser_round_count=len(loser["rounds"]))
            for label, row in (("baseline",baseline),("feedback",feedback),("debugging",debugging)):
                case[label+"_record_sha256"] = row.get("source_record_sha256", "")
                case[label+"_error_trajectory"] = " -> ".join(f"{r['round']}:{r['error_category']}" for r in row["rounds"])
            cases.append(case)
            for label, row in (("F",feedback),("D",debugging)):
                for attempt in row["rounds"]:
                    trajectories.append(dict(case_id=case_id, source_experiment_id=source,
                        model_spec=model, task_id=task, base_seed=seed, winner=case["winner"],
                        intervention=label, round=attempt["round"], round_seed=attempt.get("round_seed", ""),
                        feedback_type=attempt.get("feedback_type", ""), level=reached(attempt),
                        failure_stage=attempt["failure_stage"], error_category=attempt["error_category"],
                        exception_type=attempt["exception_type"], code_sha256=attempt.get("code_sha256", "")))
    summaries = []
    for (scope, source, grouping, values), counts in sorted(groups.items()):
        row = dict(scope=scope, source_experiment_id=source, grouping=grouping,
                   **dict.fromkeys(DIMENSIONS,""), **{k:counts[k] for k in COUNT_FIELDS})
        row.update(zip(GROUPINGS[grouping],values))
        row["feedback_rescued"] = row["both_rescued"] + row["feedback_only"]
        row["debugging_rescued"] = row["both_rescued"] + row["debugging_only"]
        row["feedback_rescue_rate"] = row["feedback_rescued"] / row["baseline_L3_failure"]
        row["debugging_rescue_rate"] = row["debugging_rescued"] / row["baseline_L3_failure"]
        row["small_denominator"] = row["baseline_L3_failure"] < 10
        summaries.append(row)
    result = dict(comparisons=summaries, discordant_cases=cases, round_trajectories=trajectories)
    verify_comparison(result)
    # Reconcile all strata shared with the preceding independent analysis.
    lookup = {(r["scope"],r["source_experiment_id"],r["grouping"],r["model_spec"],r["task_difficulty"]):r
              for r in strata["feedback_debug_overlap"] if r["grouping"] in {"overall","model","difficulty"}}
    for row in summaries:
        if row["grouping"] in {"overall","model","difficulty"}:
            expected = lookup[(row["scope"],row["source_experiment_id"],row["grouping"],row["model_spec"],row["task_difficulty"])]
            if any(row[k] != expected[k] for k in COUNT_FIELDS):
                raise ValueError("Comparison differs from prior overlap definition")
    return result


def verify_comparison(result):
    rows, cases = result["comparisons"], result["discordant_cases"]
    if not rows:
        raise ValueError("No baseline failures to compare")
    for row in rows:
        if sum(row[k] for k in COUNT_FIELDS[1:]) != row["baseline_L3_failure"]:
            raise ValueError("Overlap partition mismatch")
    for scope, source in {(r["scope"],r["source_experiment_id"]) for r in rows}:
        selected=[r for r in rows if (r["scope"],r["source_experiment_id"])==(scope,source)]
        total=next(r for r in selected if r["grouping"]=="overall")
        for grouping in GROUPINGS:
            for field in COUNT_FIELDS:
                if sum(r[field] for r in selected if r["grouping"]==grouping)!=total[field]:
                    raise ValueError("Grouping partition mismatch")
    pooled=next(r for r in rows if r["scope"]=="pooled" and r["grouping"]=="overall")
    for k in COUNT_FIELDS:
        if sum(r[k] for r in rows if r["scope"]=="source" and r["grouping"]=="overall")!=pooled[k]:
            raise ValueError("Source partition mismatch")
    if len({r["case_id"] for r in cases})!=len(cases):
        raise ValueError("Duplicate discordant case")
    winners=Counter(r["winner"] for r in cases)
    if winners["F"]!=pooled["feedback_only"] or winners["D"]!=pooled["debugging_only"]:
        raise ValueError("Case count mismatch")
    for case in cases:
        if case["winner_final_level"]!="L3" or case["loser_final_level"]=="L3" or case["winner_first_success_round"]<1:
            raise ValueError("Invalid discordant case")
        trace=[r for r in result["round_trajectories"] if r["case_id"]==case["case_id"]]
        if len(trace)!=case["winner_round_count"]+case["loser_round_count"]:
            raise ValueError("Case trajectory count mismatch")
    return True


def render_report(result):
    rows=result["comparisons"]
    total=next(r for r in rows if r["scope"]=="pooled" and r["grouping"]=="overall")
    def table(grouping,fields,labels,scope="pooled"):
        content=["| "+" | ".join([*labels,"初期未達","共通救出","Fのみ","Dのみ","どちらも未達","F救出率","D救出率"])+" |",
                 "| "+" | ".join(["---"]*len(labels)+["---:"]*7)+" |"]
        for r in rows:
            if r["grouping"]!=grouping or r["scope"]!=scope:continue
            values=[str(r[k]).removeprefix("ollama:") for k in fields]
            values.extend(str(r[k]) for k in COUNT_FIELDS)
            values.extend(f"{100*r[k]:.1f}%" for k in ("feedback_rescue_rate","debugging_rescue_rate"))
            content.append("| "+" | ".join(values)+" |")
        return content
    content=["# 実行結果提示と自己デバッグの救出例比較", "",
        f"baselineのL3未達{total['baseline_L3_failure']}件を対応付きで比較した。共通救出{total['both_rescued']}件、Fのみ{total['feedback_only']}件、Dのみ{total['debugging_only']}件、どちらも未達{total['neither_rescued']}件。片方だけで救出した例を失敗類型・タスク・モデル・出典別に整理し、保存済みround履歴の変化を確認する。", "",
        "F＝execution_feedback（実行結果提示）、D＝self_debugging（説明・原因分析・修正）。両者は同じ初期コード・初期評価を共有する。全体の救出率の分母は初期未達全件であり、選び出した片方だけの成功例ではない。表の各率も同じ行の初期未達件数を分母とする。", "",
        "## baseline失敗類型別", "", *table("baseline_error",["baseline_error_category"],["失敗類型"]), "",
        "## タスク別", "", *table("task",["task_id"],["タスク"]), "",
        "## モデル別", "", *table("model",["model_spec"],["モデル"]), "",
        "## モデルと失敗類型の組合せ", "", *table("model_error",["model_spec","baseline_error_category"],["モデル","失敗類型"]), "",
        "## 出典別", "", *table("overall",["source_experiment_id"],["実験ID"],scope="source"), "",
        "モデル×タスク、元実験別の失敗類型・モデル・タスクの全表はcomparisons.csvを参照。初期失敗がない層は行を作らず、初期未達10件未満はsmall_denominatorで参考値として明示する。片方だけの例の比率を、全体の救出率と混同しない。", "",
        "## 保存済み履歴の確認例", "",
        "各条件・baseline失敗類型からcase_id順の先頭例を示す。頻度による代表例や典型例の選定ではなく、履歴を追跡するための例示である。okは利用可能な構造要件を含むL3達成。分類の変化は記録された評価結果であり、生成コードを再実行したものではない。", "",
        "| case ID | 救出条件 | モデル／タスク／base seed | baseline類型 | Fのround履歴 | Dのround履歴 |",
        "| --- | --- | --- | --- | --- | --- |"]
    seen=set()
    for case in sorted(result["discordant_cases"],key=lambda r:r["case_id"]):
        key=(case["winner"],case["baseline_error_category"])
        if key in seen:continue
        seen.add(key)
        content.append(f"| {case['case_id']} | {case['winner']} | {case['model_spec'].removeprefix('ollama:')}／{case['task_id']}／{case['base_seed']} | {case['baseline_error_category']} | {case['feedback_error_trajectory']} | {case['debugging_error_trajectory']} |")
    content += ["", "履歴のerror_category列は各roundの失敗原因、level列は累積的な到達段階を示す。成功した条件がL3へ進む一方、もう一方が同じ類型を繰り返した例と、別の失敗類型へ移った例を区別できる。変更の具体的な原因や診断文の有効性を確定するには、別途コード・フィードバックの内容確認が必要となる。", "",
        "## 解釈と介入の使い分け", "",
        "片方だけの救出例は比較の候補であり、失敗類型から最適介入を決めるルールではない。まず全初期未達を分母とする率を見て、モデル・タスク・出典別の内訳と少数分母を確認する。別のタスク・モデルや同じ例の再生成で同じ結果が得られることは保証しない。", "",
        "schema 2.0と2.1の診断文処理差、実施時期、seedブロックが含まれる。後続roundの生成コードは条件ごとに異なり、同じ初期コードの対応付き比較でも、成功の差を説明・実行結果提示の単一要素に帰属させない。一般的優劣・統計的有意差は断定しない。Pは別プロンプトからの独立生成であり、このF/D比較の対象外。", "",
        "## 出典と再現", "",
        "[前段の層別分析](../model_difficulty_seed_20261013/README.md)と同じ検証済み固定出典を使用した。新規生成・生成コードの再評価を行わず、元の生データ・評価値は保持した。", "",
        "comparisons.csv：全初期未達の対応付き結果。discordant_cases.csv：片方だけで救出した例と元recordのhash。round_trajectories.csv：これらのF/D修正履歴の評価・分類・コードhash。公開ファイルに生成コード・生の例外メッセージ・認証情報は含めない。manifest.jsonに出典とhash、sanity_report.jsonに集計検証を保存。", "",
        "```bash", ".venv/bin/python -m scripts.analyze_discordant_repairs \\",
        "  --analysis-manifest docs/analysis/model_difficulty_seed_20261013/manifest.json \\",
        "  --out-dir docs/analysis/<新しい保存先>", "```", ""]
    return "\n".join(content)


def write_comparison(analysis_manifest,output,root=Path.cwd()):
    analysis_manifest,output,root=Path(analysis_manifest),Path(output),Path(root)
    if output.exists():raise ValueError("Use a new analysis directory")
    previous=json.loads(analysis_manifest.read_text())
    snapshot_path=root/previous["fixed_snapshot"]
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest()!=previous["snapshot_sha256"]:
        raise ValueError("Fixed snapshot hash changed")
    for item in previous["artifacts"]:
        if hashlib.sha256((analysis_manifest.parent/item["path"]).read_bytes()).hexdigest()!=item["sha256"]:
            raise ValueError("Prior analysis artifact changed")
    snapshot=json.loads(snapshot_path.read_text())
    source_runs={r["experiment_id"]:r for r in snapshot["runs"]}
    if {s["experiment_id"] for s in previous["sources"]}!=set(source_runs):
        raise ValueError("Prior analysis sources differ from fixed snapshot")
    records=[]
    for src in previous["sources"]:
        source=(root/src["source_dir"]).resolve()
        if not source.is_relative_to((root/"results").resolve()):raise ValueError("Source outside results")
        raw=source/"raw.jsonl";data=raw.read_bytes()
        if not data.endswith(b"\n") or hashlib.sha256(data).hexdigest()!=src["raw_sha256"]:
            raise ValueError("Raw source hash changed")
        run=source_runs[src["experiment_id"]]
        config=json.loads((source/"experiment_config.json").read_text())
        if config!=src["config"] or config!=run["config"] or src["raw_sha256"]!=run["raw_sha256"]:
            raise ValueError("Source config or hash differs from fixed snapshot")
        if not json.loads((source/"automation_report.json").read_text())["passed"] or not verify(config,source)["passed"]:
            raise ValueError("Source is not verified")
        rows=[]
        for line in data.splitlines(keepends=True):
            if line.strip():
                row=normalize_record(json.loads(line))
                row["source_record_sha256"]=hashlib.sha256(line).hexdigest()
                rows.append(row)
        levels=analyze_levels(rows)
        if len(rows)!=run["records"] or any(levels[k]!=run[k] for k in levels):
            raise ValueError("Evaluations differ from fixed snapshot")
        if raw.read_bytes()!=data:raise ValueError("Raw changed during analysis")
        records.extend(rows)
    result=compare_pairs(records)
    import csv
    with (analysis_manifest.parent/"feedback_debug_overlap.csv").open(encoding="utf-8-sig",newline="") as stream:
        prior=list(csv.DictReader(stream))
    total=next(r for r in result["comparisons"] if r["scope"]=="pooled" and r["grouping"]=="overall")
    prior_total=next(r for r in prior if r["scope"]=="pooled" and r["grouping"]=="overall")
    if any(total[k]!=int(prior_total[k]) for k in COUNT_FIELDS):raise ValueError("Prior overlap mismatch")
    output.mkdir(parents=True)
    artifacts=[]
    schemas={"discordant_cases":list(result["discordant_cases"][0]) if result["discordant_cases"] else ["case_id","winner"],
             "round_trajectories":list(result["round_trajectories"][0]) if result["round_trajectories"] else ["case_id","round"]}
    for name,rows in result.items():
        p=output/(name+".csv")
        _write(p,rows,list(rows[0]) if rows else schemas[name])
        artifacts.append(dict(path=p.name,rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    p=output/"README.md";p.write_text(render_report(result))
    artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    manifest=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),analysis_version="discordant_repairs_v1",
        previous_analysis_manifest=str(analysis_manifest),previous_manifest_sha256=hashlib.sha256(analysis_manifest.read_bytes()).hexdigest(),
        fixed_snapshot=previous["fixed_snapshot"],snapshot_sha256=previous["snapshot_sha256"],sources=previous["sources"],
        analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),records=len(records),
        overlap_counts={k:total[k] for k in COUNT_FIELDS},artifacts=artifacts,
        generated_new_code=False,reevaluated_generated_code=False)
    (output/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
    (output/"sanity_report.json").write_text(json.dumps(dict(passed=True,source_hashes_unchanged=True,
        sources_reverified=True,fixed_snapshot_matches=True,previous_overlap_matches=True,
        grouping_and_source_totals_match=True,discordant_case_count=len(result["discordant_cases"]),
        trajectories_match=True),indent=2)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-manifest",required=True)
    parser.add_argument("--out-dir",required=True)
    args=parser.parse_args()
    result=write_comparison(args.analysis_manifest,args.out_dir)
    print(f"Verified discordant rescues: {len(result['discordant_cases'])} cases")


if __name__=="__main__":main()
