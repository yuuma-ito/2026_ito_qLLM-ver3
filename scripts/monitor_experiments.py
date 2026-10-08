"""Report ongoing runs periodically and notify on completion or stalled work."""
import argparse
import json
from pathlib import Path
import time

from harness.run_state import ROOT, observation, update_state
from scripts.experiment_events import emit_event


def inspect_runs(root=ROOT, *, stalled_after=3600, progress_interval=1800,
                 transport="email", dry_run=False):
    if progress_interval <= 0:
        raise ValueError("progress_interval must be positive")
    progress_slot = int(time.time() // progress_interval)
    reports = []
    for path in sorted((root / ".cache" / "run_states").glob("*.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        output = Path(state["output"])
        if not output.is_relative_to((root / "results").resolve()):
            continue
        status = observation(state, stalled_after=stalled_after)
        reports.append({"experiment_id": state["experiment_id"], "status": status,
                        "phase": state["phase"]})
        if dry_run or state.get("notification_transport", "none") == "none":
            continue
        if status == "interrupted" and state["status"] not in {"completed", "failed", "interrupted"}:
            update_state(output, state["token"], {"status": "interrupted",
                         "finished_at": time.time(), "failure_type": "process_disappeared"}, root)
        if status == "running":
            emit_event(output, "running", transport, root=root, occurrence=progress_slot)
        elif status in {"interrupted", "failed", "completed", "stalled", "heartbeat_stale"}:
            event = state.get("terminal_event", status) if status == "failed" else status
            emit_event(output, event, transport, root=root)
    return reports


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stalled-after", type=int, default=3600)
    parser.add_argument("--progress-interval", type=int, default=1800,
                        help="Report running experiments once per interval in seconds (default: 1800)")
    parser.add_argument("--transport", choices=("none", "email", "slack"), default="email")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.stalled_after <= 0:
        parser.error("--stalled-after must be positive")
    if args.progress_interval <= 0:
        parser.error("--progress-interval must be positive")
    try:
        print(json.dumps(inspect_runs(stalled_after=args.stalled_after, progress_interval=args.progress_interval,
                                     transport=args.transport,
                                     dry_run=args.dry_run), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError):
        print("Experiment monitoring failed; check local runtime state.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
