"""Prepare an explicit fresh experiment for transport failures; preserve originals."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from harness.experiment import config_hash, expected_keys, has_api_failure, load_config, record_key, validate_config
from harness.run_state import ROOT


def prepare_retry(config: dict, raw: Path, *, stamp=None):
    plan = validate_config(config)
    expected = expected_keys(plan)
    failed = set()
    seen = set()
    data = raw.read_bytes()
    for line in data.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = record_key(row)
        if key not in expected or key in seen:
            raise ValueError("Retry source contains unexpected or duplicate records")
        seen.add(key)
        if has_api_failure(row, include_unknown=False):
            failed.add((key[2], key[3], key[4]))
    if not failed:
        raise ValueError("No API transport failures to retry; code evaluation failures are not retry targets")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", plan["experiment_id"]):
        raise ValueError("Retry requires a simple experiment_id")
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    retry = json.loads(json.dumps(config))
    retry["experiment_id"] = plan["experiment_id"] + "_retry_" + stamp
    retry["output_dir"] = "results/" + retry["experiment_id"]
    retry["models"] = sorted({m for m, _, _ in failed})
    retry["tasks"] = sorted({t for _, t, _ in failed})
    retry["seeds"] = sorted({s for _, _, s in failed})
    retry["pairs"] = [{"model": m, "task": t, "seed": s} for m, t, s in sorted(failed)]
    retry["retry_of"] = {"experiment_id": plan["experiment_id"], "config_hash": config_hash(config),
                         "raw_sha256": hashlib.sha256(data).hexdigest(), "pairs": len(failed)}
    validate_config(retry)
    return retry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--results", help="Original raw.jsonl; defaults to configured output")
    parser.add_argument("--out", help="New config path; defaults to .cache/retries/<experiment_id>.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(ROOT / args.config)
        raw = ROOT / args.results if args.results else ROOT / config.get("output_dir", "results/" + config["experiment_id"]) / "raw.jsonl"
        retry = prepare_retry(config, raw)
        print(f"Retry pairs: {len(retry['pairs'])}; records: {validate_config(retry)['planned_records']}")
        if not args.dry_run:
            path = ROOT / args.out if args.out else ROOT / ".cache" / "retries" / (retry["experiment_id"] + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                json.dump(retry, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print(f"Retry config: {path}")
        return 0
    except (OSError, ValueError, KeyError):
        print("Retry preparation failed; check source config/records and ensure transport failures exist.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
