"""Sequential, resumable experiment queue; stop on execution, verification or push failure."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from harness.experiment import config_hash, load_config, validate_config
from harness.run_state import ROOT, atomic_json, file_lock, observation, read_state
from scripts.automate_experiment import output_path, prepare_config


def queue_plan(source: Path, root: Path = ROOT):
    queue = load_config(source)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", queue.get("queue_id", "")):
        raise ValueError("queue_id must contain letters, numbers, underscores or hyphens")
    jobs = queue.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Queue must contain jobs")
    ids = [job["id"] for job in jobs]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", jid) for jid in ids):
        raise ValueError("Job IDs must be simple and unique")
    signatures = []
    outputs = set()
    for job in jobs:
        config = load_config(root / job["config"])
        plan = validate_config(config)
        if any(not m.startswith(("ollama:", "mock")) for m in plan["models"]):
            raise ValueError("Queue accepts shared Ollama or mock models only")
        output = output_path(config, root)
        if not job.get("new_run", False):
            if str(output) in outputs:
                raise ValueError("Jobs must not reuse the same output unless new_run is true")
            outputs.add(str(output))
        signatures.append(config_hash(config))
    signature = hashlib.sha256(json.dumps({"queue": queue, "configs": signatures}, sort_keys=True).encode()).hexdigest()
    return queue, signature


def execute_queue(source: Path, *, root: Path = ROOT, no_publish=False, dry_run=False,
                  retry_failed=False, run_job=None):
    queue, signature = queue_plan(source, root)
    notify = queue.get("notify", "email")
    if notify not in {"none", "email", "slack"}:
        raise ValueError("Invalid queue notification transport")
    if dry_run:
        for job in queue["jobs"]:
            plan = validate_config(load_config(root / job["config"]))
            print(f"{job['id']}: {plan['planned_records']} records; new_run={bool(job.get('new_run', False))}")
        return 0
    cache = root / ".cache" / "queues" / queue["queue_id"]
    state_path = cache / "state.json"
    with file_lock(cache / "queue.lock", nonblocking=True):
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["signature"] != signature or state["publish"] != (not no_publish):
                raise ValueError("Queue/config/publication policy changed; use a new queue_id")
        else:
            materialized = []
            for job in queue["jobs"]:
                # Timestamped IDs are created exactly once, then reused on resume.
                config = prepare_config(root / job["config"], job.get("new_run", False), root)
                path = cache / (job["id"] + ".json")
                atomic_json(path, config)
                materialized.append({"id": job["id"], "config": str(path), "status": "pending",
                                     "experiment_id": config["experiment_id"], "output": str(output_path(config, root))})
            state = {"queue_id": queue["queue_id"], "signature": signature, "publish": not no_publish,
                     "created_at": time.time(), "jobs": materialized}
            atomic_json(state_path, state)
        for job in state["jobs"]:
            if job["status"] == "completed":
                continue
            if job["status"] == "running":
                runtime = read_state(Path(job["output"]), root)
                if runtime and observation(runtime) in {"running", "stalled", "heartbeat_stale"}:
                    print(f"Job {job['id']} still has a live process; no overlapping run was started.")
                    return 1
                if (runtime and runtime["status"] == "completed"
                        and runtime.get("published", False) == (not no_publish)):
                    job.update(status="completed", exit_code=0, finished_at=runtime["finished_at"])
                    atomic_json(state_path, state)
                    continue
            if job["status"] == "failed" and not retry_failed:
                print(f"Queue stopped at failed job {job['id']}; inspect results, then explicitly use --retry-failed.")
                return 1
            job.update(status="running", started_at=time.time())
            atomic_json(state_path, state)
            command = [sys.executable, "-u", "-m", "scripts.automate_experiment",
                       "--config", job["config"], "--notify", notify]
            if no_publish:
                command.append("--no-publish")
            try:
                code = run_job(command) if run_job else subprocess.run(command, cwd=root).returncode
            except BaseException:
                job.update(status="failed", finished_at=time.time(), exit_code=None)
                atomic_json(state_path, state)
                raise
            job.update(status="completed" if code == 0 else "failed", finished_at=time.time(), exit_code=code)
            atomic_json(state_path, state)
            if code:
                print(f"Queue stopped at {job['id']} (exit {code}). Subsequent jobs were not started.")
                return 1
        print("Queue completed; all jobs verified" + (" and published." if not no_publish else "."))
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", default="configs/experiment_queue.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--retry-failed", action="store_true", help="Explicitly retry a failed job without erasing its records")
    args = parser.parse_args(argv)
    try:
        return execute_queue(ROOT / args.queue, no_publish=args.no_publish,
                             dry_run=args.dry_run, retry_failed=args.retry_failed)
    except (OSError, ValueError, KeyError, RuntimeError):
        print("Queue stopped; check queue/config, locks and saved queue state.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Queue interrupted; saved state is available for resume.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
