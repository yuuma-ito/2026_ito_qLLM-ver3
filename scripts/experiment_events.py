"""At most one delivery attempt per runtime event; delivery never stops a run."""
import hashlib
from pathlib import Path
import sys
import time

from dotenv import load_dotenv

from harness.run_state import ROOT, atomic_json, file_lock, read_state

LABELS = {"completed": "実験完了", "failed": "実験失敗", "interrupted": "実験中断",
          "running": "実験進行中",
          "api_failure": "API障害を記録", "publish_failed": "コミット・プッシュ失敗",
          "stalled": "長時間進捗なし", "heartbeat_stale": "状態更新の停滞"}


def emit_event(output: Path, event: str, transport: str, *, root: Path = ROOT, occurrence=None):
    if transport == "none":
        return True
    state = read_state(output, root)
    if not state:
        return False
    identity = state["token"] + ":" + event
    if occurrence is not None:
        identity += ":" + str(occurrence)
    key = hashlib.sha256(identity.encode()).hexdigest()
    path = root / ".cache" / "notification_events" / (key + ".json")
    with file_lock(path.with_suffix(".lock")):
        if path.exists():
            import json
            return json.loads(path.read_text())["status"] == "accepted"
        atomic_json(path, {"experiment_id": state["experiment_id"], "event": event,
                           "status": "attempting", "attempted_at": time.time()})
        try:
            from scripts.notify_progress import deliver, message, snapshot
            load_dotenv(root / ".env")
            title = LABELS[event]
            text = title + "\n実験: " + state["experiment_id"] + "\n段階: " + state["phase"]
            saved = Path(output) / "experiment_config.json"
            if saved.exists():
                import json
                text = title + "\n" + message(snapshot(json.loads(saved.read_text()), root), "Asia/Tokyo")
            deliver(text, state["experiment_id"], transport)
            status = "accepted"
        except (OSError, ValueError, RuntimeError, KeyError):
            print(f"Event notification failed ({event}); experiment records are preserved.", file=sys.stderr)
            status = "failed"
        atomic_json(path, {"experiment_id": state["experiment_id"], "event": event,
                           "status": status, "attempted_at": time.time()})
        return status == "accepted"
