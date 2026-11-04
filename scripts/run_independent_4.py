"""B4 preflight and explicitly approved, locked execution. No Git operations."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import urllib.request

from dotenv import load_dotenv
from harness.independent_4 import (ROOT, CONDITION, code_hash, digest, identity, immutable_json,
                                  load_cohort, read_checkpoint, run_case, sha, validate_record)
from harness.llm_clients import make_client
from harness.run_state import RunTracker, atomic_json, file_lock, observation


def write_csv(path, rows):
    import csv
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


def active_runs(root=ROOT):
    result = []
    for p in (root / '.cache/run_states').glob('*.json'):
        state = json.loads(p.read_text())
        if not str(state.get('output', '')).startswith(str(root / 'results')):
            continue
        if state.get('status') in {'completed', 'failed', 'interrupted'}:
            continue
        if observation(state) in {'running', 'stalled', 'heartbeat_stale'}:
            result.append(state['experiment_id'])
    return result


def shared_lock_busy(root=ROOT):
    p = root / '.cache/automate_experiment.lock'
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def build_plan(config, *, root=ROOT):
    cases, evidence, _ = load_cohort(config, root)
    failures = [c for c in cases if not c['initial']['primary']['L3']]
    if len(failures) != config['expected_initial_failures']:
        raise ValueError('initial failures changed; investigate before approval')
    per_model = []
    for model in config['models']:
        selected = [c for c in failures if c['model_spec'] == model]
        per_model.append(dict(model_spec=model, initial_groups=sum(c['model_spec'] == model for c in cases),
                              initial_failures=len(selected), max_new_requests=len(selected)*3,
                              historical_input_tokens_scaled_3x=sum(c['initial']['tokens_in'] for c in selected)*3,
                              historical_total_tokens_scaled_3x=sum(c['initial']['tokens_in']+c['initial']['tokens_out'] for c in selected)*3,
                              historical_generation_seconds_scaled_3x=sum(c['initial']['generation_seconds'] for c in selected)*3))
    files = ['harness/independent_4.py', 'scripts/run_independent_4.py', 'scripts/analyze_independent_4.py',
             'prompts/system.txt', 'harness/llm_clients.py', 'harness/interventions/prompts.py',
             'scripts/independent_4_progress.py', 'scripts/notify_progress.py']
    static = dict(config=config, inputs=evidence['inputs'], model_digests=evidence['model_digests'],
                  evaluator=evidence['evaluator'], initial_groups=len(cases), initial_successes=len(cases)-len(failures),
                  initial_failures=len(failures), max_new_requests=len(failures)*3,
                  completion_token_cap=len(failures)*3*1024, per_model=per_model,
                  implementation={name: sha(root/name) for name in files},
                  initial_evidence=[dict(baseline_record_key=c['baseline_record_key'], model_spec=c['model_spec'],
                                         task_id=c['task_id'], base_seed=c['base_seed'],
                                         code_sha256=c['initial']['code_sha256'], L3=c['initial']['primary']['L3']) for c in cases])
    return dict(**static, plan_sha256=digest(static), status='prepared_not_authorized',
                captured_at_utc=datetime.now(timezone.utc).isoformat(),
                live_experiments=active_runs(root), shared_generation_lock_busy=shared_lock_busy(root),
                new_llm_requests=0, generated_code_executions=0), cases


def prepare(config, output, *, root=ROOT):
    plan, cases = build_plan(config, root=root)
    output.mkdir(parents=True, exist_ok=True)
    atomic_json(output/'plan.json', plan)
    write_csv(output/'initial_groups.csv', [dict(**{k:c[k] for k in ('model_spec', 'task_id', 'base_seed', 'source_dir', 'baseline_record_key')},
                                                   initial_L3=c['initial']['primary']['L3'],
                                                   initial_error_category=c['initial']['primary']['error_category'],
                                                   code_sha256=c['initial']['code_sha256']) for c in cases])
    write_csv(output/'per_model_budget.csv', plan['per_model'])
    print(json.dumps({k:plan[k] for k in ('status','plan_sha256','initial_groups','initial_successes','initial_failures',
                                         'max_new_requests','completion_token_cap','live_experiments','shared_generation_lock_busy')}, ensure_ascii=False))
    return plan


def check_server(client, expected):
    # Metadata-only probes, only during explicitly authorized execution.
    host = client.base_url.removesuffix('/v1')
    with urllib.request.urlopen(host+'/api/tags', timeout=15) as response:
        tags = json.load(response)
    tags = {m['name']:m['digest'] for m in tags['models']}
    if tags.get(client.model_id) != expected:
        raise ValueError('server model digest differs from frozen cohort')
    with urllib.request.urlopen(host+'/api/version', timeout=15) as response:
        return json.load(response)


def execute(config, plan, cases, approved_hash, output, *, root=ROOT):
    if approved_hash != plan['plan_sha256']:
        raise ValueError('human-reviewed plan hash is required; no generation started')
    if not output.resolve().is_relative_to((root/'results').resolve()) or output.name in {Path(c['source_dir']).name for c in cases}:
        raise ValueError('new results destination required')
    with file_lock(root/'.cache/automate_experiment.lock', nonblocking=True), \
         file_lock(root/'.cache/independent_4/driver.lock', nonblocking=True):
        if active_runs(root):
            raise RuntimeError('another experiment is active; refusing new generation')
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        runtime_config=dict(config, experiment_id=output.name, output_dir=str(output.relative_to(root)))
        manifest_path = output/'manifest.json'
        if manifest_path.exists():
            saved = read_checkpoint(manifest_path)
            if saved['plan_sha256'] != plan['plan_sha256'] or saved.get('run_id') != output.name:
                raise ValueError('resume plan drift')
            if read_checkpoint(output/'experiment_config.json') != runtime_config:
                raise ValueError('resume configuration drift')
        else:
            if any(output.iterdir()):
                raise ValueError('nonempty destination without matching manifest')
            immutable_json(manifest_path, dict(plan, status='execution_authorized',run_id=output.name,
                                               approved_plan_sha256=approved_hash))
            immutable_json(output/'experiment_config.json', runtime_config)
        private = root/'.cache/independent_4'/output.name
        private.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw = output/'raw.jsonl'
        existing = []
        if raw.exists():
            with raw.open() as f:
                existing = [json.loads(line) for line in f if line.strip()]
        known = {identity(c):c for c in cases}
        seen = set()
        for r in existing:
            k = identity(r)
            if k not in known or k in seen:
                raise ValueError('duplicate/unexpected existing B4 result')
            validate_record(r, known[k], runtime_config)
            checkpoint = read_checkpoint(private/known[k]['baseline_record_key']/'completed.json')
            if checkpoint != r:
                raise ValueError('raw/checkpoint mismatch')
            seen.add(k)
        client, current_model = None, None
        with RunTracker(output, output.name, root=root) as tracker, raw.open('a') as handle:
            tracker.update(notification_transport='email')
            raw.chmod(0o600)
            for c in cases:
                if identity(c) in seen:
                    continue
                tracker.update(phase='independent_generation', model=c['model_spec'], task=c['task_id'],
                               seed=c['base_seed'], condition=CONDITION, recorded=len(seen))
                if not c['initial']['primary']['L3'] and current_model != c['model_spec']:
                    if current_model:
                        check_server(client, plan['model_digests'][current_model])
                    client = make_client(c['model_spec'])
                    current_model = c['model_spec']
                    version = check_server(client, plan['model_digests'][current_model])
                    atomic_json(private/'server_metadata.json', {'version':version, 'last_checked_model':current_model})
                r = run_case(c, runtime_config, client, private/c['baseline_record_key'])
                handle.write(json.dumps(r, ensure_ascii=False)+'\n')
                handle.flush()
                os.fsync(handle.fileno())
                seen.add(identity(c))
            if current_model:
                check_server(client, plan['model_digests'][current_model])
            tracker.update(phase='validation', recorded=len(seen))
            from scripts.analyze_independent_4 import analyze_saved
            analyze_saved(output, runtime_config, cases, root=root)
            tracker.finish(status='completed', recorded=len(seen), published=False)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', default='configs/independent_4_full.json')
    p.add_argument('--preflight-output', type=Path, default=Path('docs/analysis/independent_4_preflight'))
    p.add_argument('--execute', action='store_true', help='requires explicit human review first')
    p.add_argument('--approved-plan-sha256')
    run = p.add_mutually_exclusive_group()
    run.add_argument('--new-run', action='store_true')
    run.add_argument('--resume', type=Path)
    args = p.parse_args(argv)
    config = json.loads((ROOT/args.config).read_text())
    if not args.execute:
        if args.new_run or args.resume or args.approved_plan_sha256:
            p.error('execution flags require --execute; default only prepares a plan')
        prepare(config, ROOT/args.preflight_output)
        return 0
    if not args.approved_plan_sha256 or not (args.new_run or args.resume):
        p.error('--execute requires --approved-plan-sha256 and --new-run or --resume')
    load_dotenv(ROOT/'.env')
    plan, cases = build_plan(config)
    output = ROOT/args.resume if args.resume else ROOT/'results'/(
        config['experiment_id']+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    execute(config, plan, cases, args.approved_plan_sha256, output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
