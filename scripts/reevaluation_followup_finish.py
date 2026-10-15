"""Independent monitor: publish ten-minute counts, then verify and report.

Does not generate code, retry failed work, send mail, or perform Git operations.
The existing parent watcher owns the single final Slack notification.
"""
import fcntl
from datetime import datetime, timezone
import json
import time

from harness.run_state import atomic_json, file_lock
from scripts.followup_reevaluation import publish
from scripts.reevaluation_followup_validation import SOURCE, WORK, PRIVATE


def driver_active(path):
    if not path.exists():
        return False
    with path.open("r") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def run():
    with file_lock(PRIVATE / "finish.lock", nonblocking=True):
        while True:
            path = PRIVATE / "partial/progress.json"
            progress = json.loads(path.read_text()) if path.exists() else {"completed": 0, "planned": 293}
            active = driver_active(PRIVATE / "partial/driver.lock")
            if not active:
                if progress.get("status") != "completed":
                    atomic_json(PRIVATE / "finish_status.json", {**progress, "status": "needs_investigation",
                                "reason": "部分追試プロセスが全ケース完了前に停止。再試行せず原因確認が必要。"})
                    return 1
                break
            published = json.loads((PRIVATE / "progress.json").read_text())
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(published["updated_at_utc"])).total_seconds()
            if published["stage"] == "partial_rerun" and age >= 600:
                publish(SOURCE, "partial_rerun", "running", progress["completed"], progress["planned"])
            snapshot = json.loads((WORK.parent.parent / "experiment_report_snapshot.json").read_text())
            previous = snapshot.get("reevaluation_followup_20261015", {})
            stamp = previous.get("captured_at_utc")
            if not stamp or (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() >= 600:
                from scripts.reevaluation_followup_report import refresh_report
                refresh_report({"status": "部分再実験中（未完了）", "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                                "partial_completed": progress["completed"], "partial_planned": progress["planned"],
                                "new_generations": sum(1 for _ in (PRIVATE / "partial").glob("*/round_*_request.json")),
                                "generation_cap": 773, "sample_groups": 50})
            time.sleep(30)
        sample = json.loads((WORK / "unchanged_sanity_report.json").read_text())
        if sample["status"] != "passed":
            raise ValueError("変更なし抽出確認が未完了")
        publish(SOURCE, "unchanged_check", "completed", sample["groups"], sample["groups"])
        publish(SOURCE, "reporting", "running", 0, 1)
        from scripts.reevaluation_followup_report import run as report
        summary = report()
        publish(SOURCE, "reporting", "completed", 1, 1)
        atomic_json(PRIVATE / "finish_status.json", {"status": "completed", "summary": summary})
        return 0


if __name__ == "__main__":
    raise SystemExit(run())
