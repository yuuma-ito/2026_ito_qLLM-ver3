"""One terminal notification for the user's authorized saved-code run.

Separate from the pinned evaluator/driver; never edits or resumes the run.
An uncertain SMTP result is not automatically retried, avoiding duplicate mail.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import time

from dotenv import load_dotenv
from harness.run_state import ROOT, atomic_json, file_lock
from scripts.notify_progress import send_email
from scripts.pilot_reevaluation import sha


def terminal_message(output, *, root=ROOT, stale_seconds=120):
    output = Path(output)
    status_path = output / "run_status.json"
    if not status_path.exists():
        return None
    status = json.loads(status_path.read_text())
    kind = status["status"]
    if kind == "running":
        # PIDs are namespace-local; a shared filesystem flock is authoritative.
        lock = Path(status["checkpoint_dir"]) / "driver.lock"
        checkpoint = Path(status["checkpoint_dir"]).resolve()
        if not checkpoint.is_relative_to((root / ".cache/reevaluation").resolve()):
            raise ValueError("notification checkpoint outside permitted directory")
        if not lock.exists():
            return None
        with lock.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(status["updated_at_utc"])).total_seconds()
            if age <= stale_seconds:
                return None
        kind = "interrupted"
    if kind not in {"completed", "blocked_runtime_failure", "failed", "interrupted"}:
        return None
    manifest = json.loads((output / "manifest.json").read_text())
    if status["plan_sha256"] != manifest["plan_sha256"]:
        raise ValueError("run identity mismatch")
    lines = ["保存済みコードの本番再評価", f"実行：{output.name}"]
    if kind == "completed":
        final = output / "final"
        if not (final / "artifact_manifest.json").exists():
            return None
        artifacts = json.loads((final / "artifact_manifest.json").read_text())
        for name, identity in artifacts["files"].items():
            if Path(name).name != name or sha(final / name) != identity["sha256"]:
                raise ValueError("final artifact mismatch")
        summary = json.loads((final / "summary.json").read_text())
        sanity = json.loads((final / "sanity_report.json").read_text())
        if (summary["plan_sha256"] != manifest["plan_sha256"] or sanity["manifest_sha256"] != manifest["plan_sha256"]
                or summary["missing_rounds"] or summary["runtime_failures"] or sanity["integrity"] != "ok"
                or summary["complete_records"] != summary["planned_records"]
                or summary["scored_rounds"] != summary["planned_rounds"]):
            raise ValueError("completed notification requires successful full-count sanity")
        attention = summary["unclassified_primary_rounds"] or summary["shared_initial_judgment_mismatches"]
        lines += ["状態：採点処理完了・分析要確認" if attention else "状態：全件再評価完了・sanity成功",
                  f"記録：{summary['complete_records']}/{summary['planned_records']}件・{summary['scored_rounds']}/{summary['planned_rounds']} round",
                  f"基盤障害：{summary['runtime_failures']}件・欠落：{summary['missing_rounds']} round・重複：{sanity['duplicate_keys']}件",
                  f"最終主L3成功：旧{summary['old_final_successes_complete_subset']}→新{summary['new_final_successes']}",
                  f"旧失敗→新成功：{summary['new_success_old_failure']}件・旧成功→新失敗：{summary['new_failure_old_success']}件",
                  f"未分類主失敗：{summary['unclassified_primary_rounds']} round・共有初期判定不一致：{summary['shared_initial_judgment_mismatches']}組",
                  "主判定と補助診断を分離。旧feedback経路の保存コード再採点であり、新しい介入実験ではありません。",
                  f"報告：{output / 'README.md'}", f"比較・検証：{final}"]
    else:
        lines += [f"状態：{kind}・要確認（完了ではありません）",
                  f"保存済み：{status['completed_rounds']}/{status['planned_rounds']} round",
                  "基盤障害・中断をモデルの誤答として集計せず、処理を停止しています。自動再開は行いません。",
                  f"確認先：{status_path}", f"部分結果：{output / 'partial'}"]
    lines += ["元データ・旧評価を保持。LLM追加要求とGit pushは行っていません。"]
    return kind, "\n".join(lines)


def notify_once(output, *, root=ROOT, sender=send_email):
    output = Path(output).resolve()
    if not output.is_relative_to((root / "docs/analysis").resolve()) or not output.name.startswith("reevaluation_full_"):
        raise ValueError("notification output outside authorized run area")
    notification = terminal_message(output, root=root)
    if notification is None:
        return "waiting"
    event, text = notification
    directory = root / ".cache/reevaluation_notifications"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    ledger = directory / (output.name + "_" + event + ".json")
    with file_lock(ledger.with_suffix(".lock"), nonblocking=True):
        if ledger.exists():
            return json.loads(ledger.read_text())["status"]
        state = {"status":"sending", "event":event, "output":str(output), "attempted_at_utc":datetime.now(timezone.utc).isoformat()}
        atomic_json(ledger, state)  # Persist before network; no automatic retry.
        try:
            sender(text, output.name)
        except Exception as error:
            state.update(status="delivery_unconfirmed", exception_type=type(error).__name__)
            atomic_json(ledger,state)
            return state["status"]
        state.update(status="smtp_accepted", finished_at_utc=datetime.now(timezone.utc).isoformat(), slack_delivery_confirmed=False)
        atomic_json(ledger,state)
        return state["status"]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--watch",action="store_true")
    args=parser.parse_args()
    load_dotenv(ROOT / ".env")
    while True:
        result=notify_once(args.output)
        if result!="waiting":
            print(json.dumps({"notification_status":result,"output":str(args.output)},ensure_ascii=False),flush=True)
            return 0 if result=="smtp_accepted" else 1
        if not args.watch:
            print("Notification pending: reevaluation is still running.",flush=True)
            return 0
        time.sleep(30)


if __name__=="__main__":
    raise SystemExit(main())
