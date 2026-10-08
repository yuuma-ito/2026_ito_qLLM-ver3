"""Wait for an existing run to finish, then revalidate with the current harness."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from harness.experiment import has_api_failure, load_config, load_existing
from harness.run_state import atomic_json, file_lock, process_identity, read_state
from scripts.automate_experiment import ROOT, experiment_lock, output_path
from scripts.sanity_check import check_results


def completion_gate(config: dict, output: Path, root: Path = ROOT) -> tuple[str, str]:
    state = read_state(output, root)
    if not state or state.get('experiment_id') != config['experiment_id']:
        return 'blocked', 'No matching managed experiment state.'
    if process_identity(state['pid']) == state.get('process_identity') and state.get('process_identity'):
        return 'waiting', 'Original experiment process is still alive.'
    try:
        with experiment_lock(root):
            # A child can retain the experiment lock after its supervisor exits.
            report = check_results(config, output / 'raw.jsonl')
            rows, _ = load_existing(output / 'raw.jsonl')
            if not report['passed'] or report['warnings']:
                return 'blocked', 'Experiment is incomplete or sanity checks failed.'
            if any(row.get('experiment_id') != config['experiment_id'] or has_api_failure(row) for row in rows):
                return 'blocked', 'Unresolved API/unknown error or mixed experiment records.'
    except RuntimeError as exc:
        if 'Another automated experiment' in str(exc):
            return 'waiting', 'Shared experiment lock is still held.'
        raise
    return 'ready', 'All planned records are present and checks pass.'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='The existing run\'s saved experiment_config.json')
    parser.add_argument('--poll-seconds', type=float, default=60)
    parser.add_argument('--max-wait-hours', type=float, default=168)
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0 or args.max_wait_hours <= 0:
        parser.error('Polling and waiting limits must be positive.')
    source = Path(args.config).resolve()
    config = load_config(source)
    output = output_path(config)
    if source != output / 'experiment_config.json':
        parser.error('Use the saved configuration of the existing run.')
    key = hashlib.sha256(str(output).encode()).hexdigest()[:24]
    status_path = ROOT / '.cache' / 'finalizers' / (key + '.json')
    started = time.monotonic()
    def status(value, detail):
        atomic_json(status_path, dict(experiment_id=config['experiment_id'], status=value,
                                     detail=detail, updated_at=datetime.now(timezone.utc).isoformat()))
        print(f'{value}: {detail}', flush=True)
    try:
        with file_lock(status_path.with_suffix('.lock'), nonblocking=True):
            while True:
                gate, detail = completion_gate(config, output)
                if gate == 'blocked':
                    status(gate, detail)
                    return 1
                if gate == 'ready':
                    status('finalizing', detail)
                    # Complete resume already skips every recorded condition. This
                    # regenerates aggregates and revalidates/publishes, not code.
                    result = subprocess.run([sys.executable, '-u', '-m', 'scripts.automate_experiment',
                                             '--config', str(source), '--notify', 'none'], cwd=ROOT)
                    status('completed' if result.returncode == 0 else 'failed',
                           f'Automation exited with {result.returncode}.')
                    return result.returncode
                status(gate, detail)
                if time.monotonic() - started >= args.max_wait_hours * 3600:
                    status('blocked', 'Waiting limit reached; experiment left untouched.')
                    return 1
                time.sleep(args.poll_seconds)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f'Finalizer stopped: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
