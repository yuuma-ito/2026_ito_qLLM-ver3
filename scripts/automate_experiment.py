"""Run, verify and publish a shared Ollama experiment in one command."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

from harness.experiment import has_api_failure, load_config, validate_config
from harness.run_state import RunTracker, file_lock
from scripts.compare_experiments import write_comparison
from scripts.experiment_events import emit_event
from scripts.sanity_check import check_results

ROOT = Path(__file__).resolve().parent.parent
HOST = "http://127.0.0.1:11435"
ARTIFACTS = (
    "experiment_config.json", "manifest.json", "sanity_report.json",
    "automation_report.json", "summary_by_condition.csv", "summary_by_model.csv",
    "summary_by_task.csv", "summary_by_difficulty.csv", "rescue_rates_by_error.csv",
    "degradation_cases.csv", "baseline_regressions.csv", "timeout_summary.csv",
    "cost_runtime_summary.csv",
    "comparison_by_condition.csv", "comparison_report.md",
)


def report_artifacts():
    from scripts.update_experiment_report import REPORT, SNAPSHOT, collect_run, render_report
    if not (ROOT / REPORT).exists() and not (ROOT / SNAPSHOT).exists():
        return []
    previous = json.loads(git("show", f"HEAD:{SNAPSHOT}"))
    current = json.loads((ROOT / SNAPSHOT).read_text())
    datetime.fromisoformat(current['captured_at'])
    expected = dict(previous, captured_at=current['captured_at'],
                    runs=[collect_run(run, ROOT) for run in previous['runs']])
    original = git("show", f"HEAD:{REPORT}")
    if current != expected or (ROOT / REPORT).read_text().strip() != render_report(original, previous, expected).strip():
        raise RuntimeError("Report changes are not generated aggregates; publication stopped.")
    return [str(REPORT), str(SNAPSHOT)]


def run(command, *, env=None, capture=False, pass_fds=()):
    return subprocess.run(command, cwd=ROOT, env=env, check=True, text=True,
                          pass_fds=pass_fds,
                          stdout=subprocess.PIPE if capture else None)


def git(*args):
    return run(["git", *args], capture=True).stdout.strip()


@contextmanager
def experiment_lock(root=ROOT):
    path = root / ".cache" / "automate_experiment.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another automated experiment is running.") from exc
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def output_path(config, root=ROOT):
    path = Path(config.get("output_dir", f"results/{config['experiment_id']}"))
    path = (root / path).resolve()
    results = (root / "results").resolve()
    if not path.is_relative_to(results) or path == results:
        raise ValueError("Automation output_dir must be a directory inside results/.")
    return path


def prepare_config(source, new_run=False, root=ROOT):
    config = load_config(source)
    plan = validate_config(config)
    if not plan["seeds"] or not plan["tasks"]:
        raise ValueError("At least one seed and task are required.")
    if any(not model.startswith(("ollama:", "mock")) for model in plan["models"]):
        raise ValueError("Automation accepts only shared Ollama or mock models.")
    if new_run:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", config["experiment_id"]):
            raise ValueError("--new-run requires a simple experiment_id.")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        config["experiment_id"] += "_" + stamp
        config["output_dir"] = "results/" + config["experiment_id"]
    output_path(config, root)
    return config


def preflight(config):
    models = [m.split(":", 1)[1] for m in config["models"] if m.startswith("ollama:")]
    if not models:
        return {}
    data = {}
    for name in ("version", "tags"):
        with urllib.request.urlopen(HOST + "/api/" + name, timeout=10) as response:
            data[name] = json.load(response)
    available = {m["name"] for m in data["tags"]["models"]}
    missing = set(models) - available
    if missing:
        raise RuntimeError(f"Shared server is missing models: {sorted(missing)}. No models will be installed.")
    return {"base_url": HOST + "/v1", "version": data["version"],
            "models": [m for m in data["tags"]["models"] if m["name"] in models],
            "reasoning_effort": "none", "max_tokens": 1024, "parallel_requests": 1}


def verify(config, output):
    report = check_results(config, output / "raw.jsonl")
    problems = list(report["errors"])
    problems.extend(report["warnings"])
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines() if line.strip()]
    if any(r.get("experiment_id") != config["experiment_id"] for r in rows):
        problems.append("Output contains records from another experiment.")
    for index, row in enumerate(rows):
        if has_api_failure(row):
            problems.append(f"Unresolved API/unknown failure in record {index}.")
    for name in ARTIFACTS:
        if name not in {"automation_report.json", "experiment_config.json"} and not (output / name).is_file():
            problems.append(f"Missing artifact: {name}")
    return {"passed": not problems, "problems": problems, "sanity": report}


def require_clean_checkout(output):
    allowed = {str((output / name).relative_to(ROOT)) for name in ARTIFACTS}
    allowed.update(report_artifacts())
    if git("diff", "--cached", "--name-only"):
        raise RuntimeError("Commit or isolate staged changes before automatic publication.")
    changed = set(git("diff", "--name-only").splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard").splitlines())
    if (changed | untracked) - allowed:
        raise RuntimeError("Commit or isolate unrelated changes before automatic publication.")
    branch = git("branch", "--show-current")
    if not branch:
        raise RuntimeError("Publication requires a named branch.")
    git("remote", "get-url", "origin")
    return branch


def publish(output, experiment_id, branch):
    # Keep the report updater from changing either file while Git stages the pair.
    with file_lock(ROOT / '.cache' / 'experiment_report.lock'):
        return _publish(output, experiment_id, branch)


def _publish(output, experiment_id, branch):
    # Stage an explicit artifact list. Never stage raw outputs or other user files.
    paths = [str((output / name).relative_to(ROOT)) for name in ARTIFACTS]
    paths += report_artifacts()
    if git("diff", "--cached", "--name-only"):
        raise RuntimeError("Unexpected staged changes; automatic commit stopped.")
    allowed = set(paths)
    changed = set(git("diff", "--name-only").splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard").splitlines())
    if (changed | untracked) - allowed:
        raise RuntimeError("Unrelated changes appeared during the experiment; publication stopped.")
    git("add", "-f", "--", *paths)
    staged = set(git("diff", "--cached", "--name-only").splitlines())
    if staged - allowed:
        raise RuntimeError("Unexpected staged files; publication stopped.")
    if staged:
        git("-c", "user.name=yuuma-ito", "-c", "user.email=23tc011@tc.nanzan-u.ac.jp",
            "commit", "-m", f"data: record verified experiment {experiment_id}")
    # A failed push leaves the local commit intact. No force push or automatic merge.
    run(["git", "push", "origin", branch])
    print(f"Published {git('rev-parse', '--short', 'HEAD')} to origin/{branch}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/shared_three_models_quick.json")
    parser.add_argument("--new-run", action="store_true", help="Use a fresh timestamped experiment/output directory")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without network, tests, writes or publication")
    parser.add_argument("--no-publish", action="store_true", help="Run and verify without committing or pushing")
    parser.add_argument("--notify", choices=("none", "email", "slack"), default="email",
                        help="Immediate completion/failure notifications; default email")
    args = parser.parse_args(argv)
    try:
        config = prepare_config(Path(args.config).resolve(), args.new_run, ROOT)
        output = output_path(config, ROOT)
        plan = validate_config(config)
        print(f"Experiment: {config['experiment_id']}\nRecords: {plan['planned_records']}\nOutput: {output}", flush=True)
        if args.dry_run:
            print(f"Sequential requests; shared endpoint {HOST}; publish={not args.no_publish}")
            return 0
        with experiment_lock(ROOT) as shared_lock:
            with RunTracker(output, config["experiment_id"], root=ROOT) as tracker:
                tracker.update(phase="checkout", notification_transport=args.notify)
                try:
                    branch = require_clean_checkout(output) if not args.no_publish else ""
                    tracker.update(phase="tests")
                    env = dict(os.environ, OLLAMA_HOST=HOST, OLLAMA_BASE_URL=HOST, OMP_NUM_THREADS="1",
                               QLLM_EVENT_TRANSPORT="none")
                    env.pop("QLLM_RUN_TOKEN", None)
                    run([sys.executable, "-m", "pytest", "tests/", "-q"], env=env)
                    tracker.update(phase="preflight")
                    server = preflight(config)
                    output.mkdir(parents=True, exist_ok=True)
                    saved_config = output / "experiment_config.json"
                    if saved_config.exists() and json.loads(saved_config.read_text()) != config:
                        raise RuntimeError("Saved config differs. Use --new-run for a different experiment.")
                    saved_config.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
                    tracker.update(phase="generating")
                    env.update(QLLM_RUN_TOKEN=tracker.token, QLLM_EVENT_TRANSPORT=args.notify)
                    # Keep the shared-server lock in the child if this supervisor is killed.
                    run([sys.executable, "-u", "-m", "scripts.run_experiment", "--config", str(saved_config)],
                        env=env, pass_fds=(shared_lock.fileno(),))
                    tracker.update(phase="verifying")
                    report = verify(config, output)
                    report["shared_server"] = server
                    report["tests_passed"] = True
                    (output / "automation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                    if not report["passed"]:
                        raise RuntimeError("Verification failed: " + "; ".join(report["problems"]))
                    history = [p for p in (ROOT / "results").glob("*") if p.is_dir() and (p / "manifest.json").exists()]
                    write_comparison(history, output)
                    if not args.no_publish:
                        tracker.update(phase="publishing")
                        from scripts.update_experiment_report import REPORT, SNAPSHOT, update_report
                        if (ROOT / REPORT).exists() and (ROOT / SNAPSHOT).exists():
                            update_report(ROOT)
                        publish(output, config["experiment_id"], branch)
                    tracker.finish("completed", phase="completed", published=not args.no_publish)
                    emit_event(output, "completed", args.notify, root=ROOT)
                    print("Automation completed; verification PASS.")
                except BaseException as exc:
                    from harness.run_state import read_state
                    phase = read_state(output, ROOT)["phase"]
                    interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit))
                    event = "interrupted" if interrupted else "publish_failed" if phase == "publishing" else "failed"
                    tracker.finish("interrupted" if interrupted else "failed", failure_type=type(exc).__name__, terminal_event=event)
                    emit_event(output, event, args.notify, root=ROOT)
                    raise
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Automation stopped: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Automation interrupted; runtime state and records are preserved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
