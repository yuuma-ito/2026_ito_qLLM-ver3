"""Start the authorized follow-up once, and report safe stage progress by email."""
from __future__ import annotations

import argparse
import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from dotenv import load_dotenv

from harness.run_state import ROOT, atomic_json, file_lock
from scripts.notify_progress import send_email
from scripts.notify_reevaluation import terminal_message
from scripts.pilot_reevaluation import sha

STAGES = {
    "validation": "全件・中断前結果の検証",
    "impact_audit": "停止判断・フィードバックの影響箇所の特定",
    "partial_rerun": "影響がある経路の部分再実験",
    "unchanged_check": "変更なしケースの抽出確認",
    "reporting": "新旧結果・コストの集計と日本語報告",
}
CHECKS = ("source_integrity", "missing_duplicate_check", "partial_rerun_sanity",
          "unchanged_sample_check", "comparison_report", "related_tests")
WORKSPACE = Path("docs/analysis/reevaluation_followup_20261015")
NOTIFY_INTERVAL_SECONDS = 3 * 60 * 60


def now():
    return datetime.now(timezone.utc).isoformat()


def paths(output, root=ROOT):
    output = Path(output).resolve()
    if not output.is_relative_to(root / "docs/analysis") or not output.name.startswith("reevaluation_full_"):
        raise ValueError("unauthorized follow-up source")
    private = root / ".cache/reevaluation_followup" / output.name
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output, private


def publish(output, stage, status, completed, planned, *, root=ROOT):
    output, private = paths(output, root)
    if stage not in STAGES or status not in {"running", "completed", "blocked"}:
        raise ValueError("unknown stage/status")
    if completed < 0 or planned < 0 or completed > planned:
        raise ValueError("invalid counts")
    if status == "completed" and completed != planned:
        raise ValueError("completed stage has missing planned work")
    if stage == "reporting" and status == "completed":
        work = root / WORKSPACE
        checks = json.loads((work / "completion_checks.json").read_text())
        if any(checks.get(key) is not True for key in CHECKS) or not (work / "README.md").is_file():
            raise ValueError("follow-up completion checks missing")
    with file_lock(private / "progress.lock"):
        old = json.loads((private / "progress.json").read_text()) if (private / "progress.json").exists() else {}
        state = dict(stage=stage, status=status, completed=completed, planned=planned,
                     sequence=old.get("sequence", 0) + 1, updated_at_utc=now())
        atomic_json(private / "progress.json", state)
        # A journal preserves transitions even when stages finish between polls.
        atomic_json(private / f"event_{state['sequence']:06d}.json", state)
    return state


def notify(output, event, text, *, root=ROOT, sender=send_email):
    output, private = paths(output, root)
    if not event.replace("_", "").isalnum():
        raise ValueError("invalid event")
    ledger = private / f"notification_{event}.json"
    with file_lock(ledger.with_suffix(".lock"), nonblocking=True):
        if ledger.exists():
            return json.loads(ledger.read_text())["status"]
        state = dict(status="sending", attempted_at_utc=now(), event=event)
        atomic_json(ledger, state)
        try:
            sender(text, output.name)
        except Exception as error:
            state.update(status="delivery_unconfirmed", exception_type=type(error).__name__)
        else:
            state.update(status="smtp_accepted", slack_delivery_confirmed=False)
        atomic_json(ledger, state)
        return state["status"]


def heartbeat(output, *, root=ROOT, sender=send_email, at=None):
    output, private = paths(output, root)
    stamp = at or datetime.now(timezone.utc)
    previous = []
    for ledger in private.glob("notification_*.json"):
        data = json.loads(ledger.read_text())
        if data["event"] == "configured" or data["event"].startswith("heartbeat_"):
            previous.append(datetime.fromisoformat(data["attempted_at_utc"]))
    if previous and (stamp - max(previous)).total_seconds() < NOTIFY_INTERVAL_SECONDS:
        return "not_due"
    slot = int(stamp.timestamp()) // NOTIFY_INTERVAL_SECONDS
    state = json.loads((output / "run_status.json").read_text())
    text = (f"再評価・後続作業の定期進捗\n実行：{output.name}\n"
            f"再評価：{state['status']}、{state['completed_rounds']}/{state['planned_rounds']} round\n")
    if (private / "progress.json").exists():
        progress = json.loads((private / "progress.json").read_text())
        text += (f"後続作業：{STAGES[progress['stage']]}、{progress['status']}\n"
                 f"完了／予定：{progress['completed']}／{progress['planned']}\n"
                 f"作業状態の最終更新UTC：{progress['updated_at_utc']}\n")
    elif (private / "job.json").exists():
        text += "後続作業：AI起動済み・最初の段階報告待ち\n"
    else:
        text += "後続作業：全件再評価とsanity完了待ち（追加生成未開始）\n"
    text += f"計画：{output / 'followup_plan.md'}\n結果・停止理由：{root / WORKSPACE / 'README.md'}"
    return notify(output, f"heartbeat_{slot}", text, root=root, sender=sender)


def readiness(output, *, root=ROOT):
    event = terminal_message(output, root=root)
    if event is None:
        return "waiting"
    if event[0] != "completed":
        return "blocked"
    status = json.loads((Path(output) / "run_status.json").read_text())
    with (Path(status["checkpoint_dir"]) / "driver.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "waiting"
        fcntl.flock(lock, fcntl.LOCK_UN)
    summary = json.loads((Path(output) / "final/summary.json").read_text())
    sanity = json.loads((Path(output) / "final/sanity_report.json").read_text())
    if sanity["duplicate_keys"] or summary["unclassified_primary_rounds"] or summary["shared_initial_judgment_mismatches"]:
        return "audit_only"
    return "ready"


def launch_once(output, *, root=ROOT, sender=send_email, popen=subprocess.Popen, sleeper=time.sleep):
    output, private = paths(output, root)
    with file_lock(private / "job.lock", nonblocking=True):
        state_path = private / "job.json"
        if state_path.exists():
            return json.loads(state_path.read_text())["status"]
        ready = readiness(output, root=root)
        if ready not in {"ready", "audit_only"}:
            return ready
        plan = output / "followup_plan.md"
        if not plan.is_file():
            raise ValueError("follow-up instructions missing")
        state = dict(status="attempting", readiness=ready, started_at_utc=now(),
                     instructions_sha256=sha(plan), source=str(output), log=str(private / "codex.log"))
        atomic_json(state_path, state)  # No automatic repeat after crash or ambiguous exit.
        env = os.environ.copy()
        for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_PERMISSION_PROFILE"):
            env.pop(name, None)
        prompt = ("ユーザーが以下の作業を明示的に承認しています。日本語で作業し、指示に従い完了まで進めてください。\n"
                  + plan.read_text() + "\n独立監視がSlack報告を行うため、進捗publishを忘れないでください。"
                  "後続の新しい全件生成実験やGit pushを行わないでください。\n")
        try:
            with (private / "codex.log").open("a") as log, (private / "prompt.txt").open("w+") as request:
                request.write(prompt); request.flush(); request.seek(0)
                command = ["codex", "exec", "--sandbox", "workspace-write", "--cd", str(root),
                           "-c", 'approval_policy="never"',
                           "-c", "sandbox_workspace_write.network_access=true", "--color", "never",
                           "--output-last-message", str(private / "last_message.txt"), "-"]
                proc = popen(command, stdin=request, stdout=log, stderr=subprocess.STDOUT, env=env)
                state.update(pid=proc.pid)
                atomic_json(state_path, state)
                while proc.poll() is None:
                    heartbeat(output, root=root, sender=sender)
                    sleeper(30)
                progress_path = private / "progress.json"
                progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
                completed = proc.returncode == 0 and progress.get("stage") == "reporting" and progress.get("status") == "completed"
                if completed:
                    checks = json.loads((root / WORKSPACE / "completion_checks.json").read_text())
                    completed = all(checks.get(k) is True for k in CHECKS) and (root / WORKSPACE / "README.md").is_file()
                state.update(status="completed" if completed else "blocked", exit_code=proc.returncode)
        except Exception as error:
            state.update(status="blocked", exception_type=type(error).__name__)
        state.update(finished_at_utc=now())
        atomic_json(state_path, state)
        label = "再評価後の全作業が完了しました。定期通知を終了します。" if state['status'] == 'completed' else "再評価後の作業が停止しました（未完了）。定期通知を終了します。"
        notify(output, "finished", f"{label}\n状態：{state['status']}\n"
               f"結果・停止理由：{root / WORKSPACE / 'README.md'}\n"
               "blockedは作業未完了です。自動で同じ処理を再起動しません。Git pushは行いません。", root=root, sender=sender)
        return state["status"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--status", choices=("running", "completed", "blocked"))
    parser.add_argument("--completed", type=int, default=0)
    parser.add_argument("--planned", type=int, default=0)
    args = parser.parse_args()
    output, private = paths(args.output)
    if args.publish:
        print(json.dumps(publish(output, args.stage, args.status, args.completed, args.planned), ensure_ascii=False))
        return
    load_dotenv(ROOT / ".env")
    with file_lock(private / "watcher.lock", nonblocking=True):
        status = json.loads((output / "run_status.json").read_text())
        notify(output, "configured", "再評価後の作業とSlack進捗報告を設定しました。\n"
               f"現在：再評価{status['completed_rounds']}/{status['planned_rounds']} round、状態{status['status']}\n"
               "完了・sanity確認後に、影響箇所の特定と必要な部分再実験、変更なしケースの抽出確認を行います。\n"
               "3時間ごとに作業段階と完了件数を報告し、全作業完了時の最終通知後に定期送信を停止します。\n"
               f"指示：{output / 'followup_plan.md'}\n全件の新規生成とGit pushは行いません。")
        while True:
            try:
                result = launch_once(output)
            except BlockingIOError:
                result = "waiting"
            except Exception as error:
                notify(output, "validation_failed", "再評価後の作業は入力・完了検証で停止しました。\n"
                       f"例外種別：{type(error).__name__}\n確認先：{output}\n追加生成は開始していません。")
                raise
            if result != "waiting" or not args.watch:
                if result == "blocked" and not (private / "job.json").exists():
                    notify(output, "source_blocked", f"再評価または後続作業が停止しています。\n確認先：{output}\n追加生成の自動再試行はしません。")
                print(json.dumps({"followup_status": result}), flush=True)
                return
            heartbeat(output)
            time.sleep(30)


if __name__ == "__main__":
    main()
