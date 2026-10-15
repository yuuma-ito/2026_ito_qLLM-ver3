"""Authorized full saved-code reevaluation; sequential isolated batches.

No generation, external notifications, or Git operations. Original results are
read-only. Progress is mutable; final artifacts are written once in final/.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from harness.isolated_evaluation import ROOT, Limits, isolated_evaluate
from harness.reevaluation_checkpoint import Checkpoint, digest
from harness.reevaluation_plan import MAX_BATCH_ROUNDS, build_plan, execute_bounded_batch, verify_plan
from harness.run_state import atomic_json, file_lock, process_identity
from scripts.pilot_reevaluation import immutable_report, sha


def now():
    return datetime.now(timezone.utc).isoformat()


def publish_progress(output, status, summary=None):
    """Keep old experimental tables; update only this run's prose/snapshot."""
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT/"docs/analysis"):
        return  # Synthetic tests must never edit the real project report.
    report=ROOT/"docs/experiment_report_draft.md"
    snapshot=ROOT/"docs/experiment_report_snapshot.json"
    if not report.exists() or not snapshot.exists():
        return
    name=output.name
    start,end=f"<!-- saved-reevaluation:{name}:start -->",f"<!-- saved-reevaluation:{name}:end -->"
    body=f"## 保存済み5,000件の本番再評価（{name}）\n\n"
    body+=f"状態：{status['status']}。計画{status['planned_records']}記録・{status['planned_rounds']} round、保存済み{status['completed_rounds']} round。更新UTC：{status['updated_at_utc']}。"
    body+=f"[実行状態](analysis/{name}/run_status.json)と[出典・評価器manifest](analysis/{name}/manifest.json)を別保存する。主v4・補助v2を分離し、旧raw・旧評価・固定発表結果を保持する。\n\n"
    if summary:
        folder="final" if summary['status']=='completed' else 'partial'
        body+=f"採点完了{summary['complete_records']}記録・{summary['scored_rounds']} round。基盤障害{summary['runtime_failures']}件、欠落{summary['missing_rounds']} round。[比較・sanity](analysis/{name}/{folder}/summary.json)を参照する。"
        body+=f"完了記録の最終L3は旧{summary['old_final_successes_complete_subset']}→新{summary['new_final_successes']}。未分類主失敗{summary['unclassified_primary_rounds']} round、共有初期判定不一致{summary['shared_initial_judgment_mismatches']}組。"
    body+="旧feedbackで選ばれた保存コードの再採点であり、新しい介入実験ではない。LLM要求0、基盤障害時は停止。Git pushは行わない。"
    with file_lock(ROOT/'.cache/experiment_report.lock'):
        text=report.read_text()
        block=start+'\n'+body+'\n'+end
        if start in text:
            if text.count(start)!=1 or text.count(end)!=1:
                raise ValueError("reevaluation progress markers invalid")
            first,last=text.index(start),text.index(end)+len(end)
            text=text[:first]+block+text[last:]
        else:
            text+='\n\n'+block+'\n'
        current=json.loads(snapshot.read_text())
        current['saved_code_reevaluation']={**status,'source_dir':str(output.relative_to(ROOT))}
        if summary:
            current['saved_code_reevaluation']['summary']=summary
        atomic_json(snapshot,current)
        temporary=report.with_suffix('.md.tmp')
        temporary.write_text(text); temporary.replace(report)


def saved_results(checkpoint_dir):
    path = Path(checkpoint_dir) / "checkpoint.sqlite3"
    if not path.exists():
        return {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        return {key: json.loads(result) for key, result in db.execute("SELECT key,result FROM results WHERE state='completed'")}


def summarize(plan, results):
    rounds, records = [], []
    grouped = defaultdict(list)
    categories, auxiliary = Counter(), Counter()
    for case in plan["cases"]:
        result = results.get(case["key"])
        if result is None:
            grouped[case["record_key"]].append((case, None))
            continue
        grouped[case["record_key"]].append((case, result))
        primary, aux = result.get("primary", {}), result.get("auxiliary", {})
        scored = result["runtime_status"] == "completed"
        if scored:
            if primary.get("L3") != bool(primary.get("L0") and primary.get("L1") and primary.get("L2") and primary.get("structure_match")):
                raise ValueError("inconsistent L0--L3 result")
            categories[primary.get("error_category", "unknown_error")] += 1
            auxiliary[aux.get("status", "not_applicable")] += 1
        state = aux.get("state", aux)
        transform = aux.get("transform", aux if aux.get("scope") == "whole_preparation_plus_transform_unitary" else {})
        rounds.append({**{k: case[k] for k in ("key", "record_key", "source_dir", "model_spec", "task_id", "base_seed", "condition_id", "round", "is_final", "code_sha256")},
                       "runtime_status": result["runtime_status"],
                       **{"old_"+k: case["old_primary"][k] for k in ("L0", "L1", "L2", "L3", "structure_match", "error_category")},
                       **{"new_"+k: primary.get(k) if scored else None for k in ("L0", "L1", "L2", "L3", "structure_match", "error_category", "failure_stage", "exception_type", "L2_distance")},
                       "auxiliary_status": aux.get("status"), "state_fidelity": state.get("fidelity"),
                       "transform_status": transform.get("status"), "minimum_coherent_fidelity": transform.get("minimum_fidelity"),
                       "process_fidelity": transform.get("process_fidelity"),
                       "wall_seconds": result.get("seconds", 0)+result.get("build_seconds", 0),
                       "cpu_seconds": result.get("cpu_seconds", 0)+result.get("build_cpu_seconds", 0)})
    for key, history in grouped.items():
        case = history[0][0]
        complete = all(result and result["runtime_status"] == "completed" for _, result in history)
        old = [entry["old_primary"]["L3"] for entry, _ in history]
        new = [result.get("primary", {}).get("L3") if result and result["runtime_status"] == "completed" else None for _, result in history]
        records.append({"record_key": key, **{k: case[k] for k in ("source_dir", "model_spec", "task_id", "base_seed", "condition_id")},
                        "planned_rounds": len(history), "scored_rounds": sum(x is not None for x in new), "complete": complete,
                        "old_initial_success": old[0], "old_first_success_round": next((i for i, ok in enumerate(old) if ok), None),
                        "old_ever_success": any(old), "old_final_success": old[-1],
                        "new_initial_success": new[0],
                        "new_first_success_round": next((i for i, ok in enumerate(new) if ok), None) if complete else None,
                        "new_ever_success": any(new) if complete else None, "new_final_success": new[-1] if complete else None,
                        "new_regression_observed": any(new[i-1] and not new[i] for i in range(1, len(new))) if complete else None})
    groups = defaultdict(dict)
    for row in records:
        groups[(row["source_dir"], row["model_spec"], row["task_id"], row["base_seed"])][row["condition_id"]] = row
    paired = []
    for group, conditions in groups.items():
        baseline = conditions.get("baseline")
        if not baseline or not baseline["complete"]:
            continue
        for condition, row in conditions.items():
            if condition == "baseline" or not row["complete"]:
                continue
            shared = condition in {"self_refine", "execution_feedback", "self_debugging"}
            consistent = not shared or row["new_initial_success"] == baseline["new_initial_success"]
            paired.append(dict(zip(("source_dir", "model_spec", "task_id", "base_seed"), group)) | {
                "condition_id": condition, "shared_initial": shared, "initial_judgments_consistent": consistent,
                "old_baseline_final": baseline["old_final_success"], "old_intervention_final": row["old_final_success"],
                "new_baseline_final": baseline["new_final_success"], "new_intervention_final": row["new_final_success"],
                "new_final_rescue": (not baseline["new_final_success"] and row["new_final_success"]) if consistent else None,
                "new_final_regression": (baseline["new_final_success"] and not row["new_final_success"]) if consistent else None})
    summaries = []
    for model, condition in sorted({(r["model_spec"], r["condition_id"]) for r in records}):
        rows = [r for r in records if r["model_spec"] == model and r["condition_id"] == condition]
        complete = [r for r in rows if r["complete"]]
        summaries.append({"model_spec": model, "condition_id": condition, "planned": len(rows), "complete": len(complete),
                          "old_final_successes_all_planned": sum(r["old_final_success"] for r in rows),
                          "old_final_successes_complete_subset": sum(r["old_final_success"] for r in complete),
                          "new_final_successes": sum(r["new_final_success"] for r in complete),
                          "new_ever_successes": sum(r["new_ever_success"] for r in complete)})
    complete = [r for r in records if r["complete"]]
    summary = {"planned_records": plan["records"], "planned_rounds": len(plan["cases"]),
               "stored_rounds": len(rounds), "scored_rounds": sum(r["runtime_status"] == "completed" for r in rounds),
               "missing_rounds": len(plan["cases"])-len(rounds), "complete_records": len(complete),
               "runtime_failures": sum(r["runtime_status"] != "completed" for r in rounds),
               "old_final_successes_all_planned": sum(r["old_final_success"] for r in records),
               "old_final_successes_complete_subset": sum(r["old_final_success"] for r in complete),
               "new_final_successes": sum(r["new_final_success"] for r in complete),
               "new_ever_successes": sum(r["new_ever_success"] for r in complete),
               "changed_final_records": sum(r["old_final_success"] != r["new_final_success"] for r in complete),
               "new_success_old_failure": sum(not r["old_final_success"] and r["new_final_success"] for r in complete),
               "new_failure_old_success": sum(r["old_final_success"] and not r["new_final_success"] for r in complete),
               "model_failure_categories": dict(categories), "auxiliary_statuses": dict(auxiliary),
               "unclassified_primary_rounds": categories.get("unknown_error", 0),
               "shared_initial_judgment_mismatches": sum(not r["initial_judgments_consistent"] for r in paired),
               "worker_wall_seconds": sum(r["wall_seconds"] for r in rounds), "worker_cpu_seconds": sum(r["cpu_seconds"] for r in rounds),
               "llm_requests": 0, "llm_cost_usd": 0, "historical_feedback_preserved": True,
               "statistics_scope": "descriptive paired saved-path rescoring; no independent-binomial CI or pass@k"}
    return summary, rounds, records, summaries, paired


def write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def export_results(output, plan, checkpoint_dir, status, elapsed):
    results = saved_results(checkpoint_dir)
    if set(results) - {c["key"] for c in plan["cases"]}:
        raise ValueError("unexpected stored case")
    summary, rounds, records, groups, paired = summarize(plan, results)
    summary.update(status=status, elapsed_seconds=elapsed, captured_at_utc=now(), plan_sha256=digest(plan), full_5000_started=True)
    with Checkpoint(checkpoint_dir, plan) as checkpoint:
        sanity = checkpoint.sanity()
    sanity.update(runtime_failures=summary["runtime_failures"], records_complete=summary["complete_records"],
                  sources_unchanged=True, duplicate_keys=0, unclassified_primary_rounds=summary["unclassified_primary_rounds"],
                  shared_initial_judgment_mismatches=summary["shared_initial_judgment_mismatches"])
    target = output / ("final" if status == "completed" else "partial")
    if target.exists():
        if status == "completed":
            stored = json.loads((target/"summary.json").read_text())
            if stored["plan_sha256"] != digest(plan):
                raise ValueError("immutable final artifacts belong to another plan")
            return stored
        stored = json.loads((target/"summary.json").read_text())
        if stored["plan_sha256"] == digest(plan) and stored["stored_rounds"] == len(rounds):
            return stored
        raise ValueError("partial artifacts already exist; retain them and diagnose before resume")
    staging = Path(tempfile.mkdtemp(prefix=".export-", dir=output))
    for name, rows_ in (("round_comparison.csv", rounds), ("record_comparison.csv", records),
                        ("model_condition_summary.csv", groups), ("paired_effects.csv", paired)):
        write_csv(staging/name, rows_)
    immutable_report(staging/"summary.json", summary)
    immutable_report(staging/"sanity_report.json", sanity)
    artifacts = {p.name: {"sha256": sha(p), "bytes": p.stat().st_size} for p in staging.iterdir() if p.is_file()}
    immutable_report(staging/"artifact_manifest.json", {"files": artifacts, "generated_code_published": False, "raw_published": False})
    staging.rename(target)
    text = f"# 保存済みコードの本番再評価\n\n状態：{status}。主evaluation_policy_v4、補助coherent_oracles_v2。\n\n"
    text += f"全{plan['records']}記録・{len(plan['cases'])} round中、{summary['complete_records']}記録・{summary['scored_rounds']} roundを採点。基盤障害{summary['runtime_failures']}件、欠落{summary['missing_rounds']} round。\n\n"
    text += f"採点完了記録の最終L3：旧{summary['old_final_successes_complete_subset']}→新{summary['new_final_successes']}。旧失敗→新成功{summary['new_success_old_failure']}、旧成功→新失敗{summary['new_failure_old_success']}。\n\n"
    text += "主判定と状態／変換補助は別列。first/ever/finalと退行を分離した。旧feedbackで選択された保存コードの再採点であり、新feedbackによる介入実験ではない。元raw・設定・固定発表結果を保持した。LLM要求・LLM費用0。独立二項区間・pass@kは算出しない。\n\n"
    text += f"未知の主失敗分類{summary['unclassified_primary_rounds']} round、共有初期の判定不一致{summary['shared_initial_judgment_mismatches']}組。これらが残る場合は分析上の確認事項として扱う。基盤障害をwrong_outputへ算入しない。\n"
    (output/"README.md").write_text(text)
    return summary


def run_full(output, checkpoint_dir, *, plan=None, limits=Limits(), executor=isolated_evaluate):
    output, checkpoint_dir = Path(output), Path(checkpoint_dir)
    output.mkdir(parents=True, exist_ok=True)
    # The driver hash is pinned separately; existing evaluator policy is intact.
    plan = json.loads(json.dumps(plan if plan is not None else build_plan(limits=limits)))
    plan.update(purpose="authorized_full_saved_code_reevaluation", driver_sha256=sha(__file__), batch_rounds=MAX_BATCH_ROUNDS)
    status_path = output/"run_status.json"
    start = time.monotonic()
    if checkpoint_dir.is_symlink():
        raise ValueError("symlink checkpoint refused")
    checkpoint_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    checkpoint_dir.chmod(0o700)
    with file_lock(checkpoint_dir/"driver.lock", nonblocking=True):
        manifest_path = output/"manifest.json"
        public = {k: value for k, value in plan.items() if k != "cases"}
        public.update(plan_sha256=digest(plan), planned_rounds=len(plan["cases"]), checkpoint_dir=str(checkpoint_dir),
                      physical_evaluation_policy="each saved round evaluated; no code-hash result cache")
        if manifest_path.exists():
            if json.loads(manifest_path.read_text()) != public:
                raise ValueError("run manifest/profile/scope mismatch")
        else:
            immutable_report(manifest_path, public)
        with Checkpoint(checkpoint_dir, plan) as cp:
            completed = cp.sanity()["completed"]
        status = {"status":"running", "pid":os.getpid(), "process_identity":process_identity(os.getpid()),
                  "started_at_utc":now(), "updated_at_utc":now(), "planned_records":plan["records"],
                  "planned_rounds":len(plan["cases"]), "completed_rounds":completed,
                  "checkpoint_dir":str(checkpoint_dir), "plan_sha256":digest(plan), "full_5000_started":True}
        atomic_json(status_path,status)
        publish_progress(output,status)
        print(json.dumps(status),flush=True)
        try:
            for offset in range(0,len(plan["cases"]),MAX_BATCH_ROUNDS):
                if sha(__file__) != plan["driver_sha256"]:
                    raise ValueError("running driver changed")
                keys=[c["key"] for c in plan["cases"][offset:offset+MAX_BATCH_ROUNDS]]
                before=saved_results(checkpoint_dir)
                pending=iter([key for key in keys if key not in before])
                def observed_executor(code,task,execution_limits):
                    key=next(pending)
                    # Publish only safe progress metadata, never code or messages.
                    with sqlite3.connect(f"file:{checkpoint_dir/'checkpoint.sqlite3'}?mode=ro",uri=True) as db:
                        committed=db.execute("SELECT count(*) FROM results WHERE state='completed'").fetchone()[0]
                    status.update(active_key=key,completed_rounds=committed,updated_at_utc=now())
                    atomic_json(status_path,status)
                    return executor(code,task,execution_limits)
                result=execute_bounded_batch(plan,keys,checkpoint_dir,limits,observed_executor)
                status.update(status="running" if result["status"]=="batch_completed" else result["status"],
                              completed_rounds=result["sanity"]["completed"],updated_at_utc=now(),batch_offset=offset)
                atomic_json(status_path,status)
                publish_progress(output,status)
                print(json.dumps({"event":"batch",**result}),flush=True)
                if result["status"]!="batch_completed":
                    summary=export_results(output,plan,checkpoint_dir,status["status"],time.monotonic()-start)
                    publish_progress(output,status,summary)
                    return summary
            verify_plan(plan,limits)
            summary=export_results(output,plan,checkpoint_dir,"completed",time.monotonic()-start)
            if summary["missing_rounds"] or summary["runtime_failures"] or summary["complete_records"]!=plan["records"]:
                raise ValueError("full reevaluation sanity failed")
            status.update(status="completed",completed_rounds=len(plan["cases"]),updated_at_utc=now())
            atomic_json(status_path,status)
            publish_progress(output,status,summary)
            print(json.dumps({"event":"completed",**summary}),flush=True)
            return summary
        except BaseException as error:
            status.update(status="interrupted" if isinstance(error,(KeyboardInterrupt,SystemExit)) else "failed",
                          exception_type=type(error).__name__,updated_at_utc=now())
            atomic_json(status_path,status)
            publish_progress(output,status)
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--checkpoint",type=Path,required=True)
    args=parser.parse_args()
    output,checkpoint=args.output.resolve(),args.checkpoint.resolve()
    if not output.is_relative_to(ROOT/"docs/analysis") or not output.name.startswith("reevaluation_full_"):
        parser.error("output must be docs/analysis/reevaluation_full_<run-id>")
    if not checkpoint.is_relative_to(ROOT/".cache/reevaluation"):
        parser.error("checkpoint must be inside .cache/reevaluation")
    summary=run_full(output,checkpoint)
    return 0 if summary["status"]=="completed" else 1


if __name__=="__main__":
    raise SystemExit(main())
