"""Two-stage notification experiment runner; publication uses a separate wrapper."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import time
import urllib.request
from dotenv import load_dotenv
from harness.notification_ablation import CONDITIONS, SCHEMA, SETTINGS, HOST, RecordedClient, build_prompt, wire_body, schedule, features, validate_response, validate_history
from harness.independent_4 import immutable_json, read_checkpoint, digest, code_hash, strict_request, levels
from harness.code_extractor import extract_code
from harness.llm_clients import SYSTEM_PROMPT
from harness.measurement_isolation import isolated_evaluate, profile
from harness.reevaluation_checkpoint import canonical
from harness.run_state import atomic_json, file_lock, RunTracker
from scripts.measurement_ban_sources import ROOT, sha
from scripts.run_independent_4 import check_server, active_runs
from scripts.analyze_notification_ablation import save_stage

def assert_frozen(plan, *, protected=False):
    if digest({k: v for k, v in plan.items() if k != 'plan_sha256'}) != plan['plan_sha256']:
        raise ValueError('plan hash mismatch')
    if profile() != plan['evaluator']:
        raise ValueError('evaluator profile drift')
    for name, h in plan['implementation'].items():
        if sha(ROOT / name) != h:
            raise ValueError('implementation drift: ' + name)
    if protected:
        for name, h in plan['preparation_artifacts'].items():
            if sha(ROOT / plan['analysis_dir'] / name) != h:
                raise ValueError('frozen preparation changed: ' + name)
        for name, h in plan['protected_inputs'].items():
            if sha(ROOT / name) != h:
                raise ValueError('protected historical source changed: ' + name)

def request_attempt(plan, case, condition, index, history, directory, client, execution_index, position, *, request=strict_request, executor=isolated_evaluate, server_probe=check_server):
    directory.mkdir(parents=True, exist_ok=True, mode=448)
    previous = history[-1]
    task = __import__('tasks').get_task(case['task_id'])
    if condition not in CONDITIONS or previous['primary']['L3'] or not 1 <= index <= 3:
        raise ValueError('unreachable generation')
    prompt = build_prompt(condition, task, previous)
    from harness.notification_ablation import paired_seed
    seed = paired_seed(case, index)
    body = wire_body(case['model_spec'], prompt, seed)
    req = {'plan_sha256': plan['plan_sha256'], 'case_id': case['case_id'], 'condition': condition, 'round': index, 'execution_index': execution_index, 'nominal_position': position, 'wire_body': body, 'timeout_sec': 600, 'parallel_requests': 1, 'initial_fingerprint': digest(case['initial'])}
    paths = {kind: directory / (kind + '.json') for kind in ['request', 'response', 'evaluation', 'evaluation_started', 'record', 'failure', 'server_before']}
    if paths['request'].exists():
        if read_checkpoint(paths['request']) != req:
            raise ValueError('saved request mismatch')
        if not paths['response'].exists():
            raise RuntimeError('ambiguous request: automatic replay prohibited')
    else:
        if any((paths[k].exists() for k in ['response', 'evaluation', 'record', 'evaluation_started', 'failure'])):
            raise ValueError('orphan checkpoint')
        check = server_probe(client, plan['model_digests'][case['model_spec']])
        immutable_json(paths['server_before'], {'model_spec': case['model_spec'], 'digest_verified': plan['model_digests'][case['model_spec']], 'server': check, 'checked_at_utc': datetime.now(timezone.utc).isoformat()})
        immutable_json(paths['request'], req)
        try:
            response = request(client, prompt, seed, 0.7)
        except Exception as error:
            immutable_json(paths['failure'], {'exception_type': type(error).__name__, 'ambiguous_request': True, 'automatic_retry': False})
            raise
        immutable_json(paths['response'], response)
    response = read_checkpoint(paths['response'])
    validate_response(response, case['model_spec'])
    code = extract_code(response['raw_output'])
    if not paths['evaluation'].exists():
        if paths['evaluation_started'].exists():
            raise RuntimeError('ambiguous evaluation: stop for review')
        immutable_json(paths['evaluation_started'], {'code_sha256': code_hash(code)})
        immutable_json(paths['evaluation'], executor(code, case['task_id']))
    evaluated = read_checkpoint(paths['evaluation'])
    if evaluated.get('runtime_status') != 'completed':
        raise RuntimeError('evaluation infrastructure failure')
    primary = json.loads(canonical(evaluated))['primary']
    levels(primary)
    if primary['error_category'] == 'unknown_error' and (not (primary['failure_stage'] == 'exec' and (not primary['L0']) and primary.get('exception_type'))):
        raise RuntimeError('unresolved evaluator classification')
    row = {k: case[k] for k in ['case_id', 'model_spec', 'task_id', 'base_seed', 'initial_error']}
    row.update(condition=condition, round=index, seed=seed, execution_index=execution_index, nominal_position=position, initial_fingerprint=digest(case['initial']), input_prompt_sha256=code_hash(prompt), wire_body_sha256=digest(body), previous_code_sha256=code_hash(previous['code']), code_sha256=code_hash(code), code=code, primary=primary, diagnostic_policy_version=plan['diagnostic_policy_version'] if condition == 'R2' else 'none', tokens_in=response['tokens_in'], tokens_out=response['tokens_out'], generation_seconds=response['generation_seconds'], evaluation_seconds=evaluated.get('seconds', 0) + evaluated.get('build_seconds', 0), finish_reason=response['finish_reason'], features=features(previous, code, primary, history), parameters_accepted_by_api=True, model_exception_annotation=primary.get('exception_type', '') if primary['error_category'] == 'unknown_error' else '')
    if paths['record'].exists():
        if read_checkpoint(paths['record']) != row:
            raise ValueError('saved record mismatch')
    else:
        immutable_json(paths['record'], row)
    return row

def probe_models(plan, clients, output, phase):
    result = {}
    for model in sorted(clients):
        version = check_server(clients[model], plan['model_digests'][model])
        result[model] = {'digest_verified': plan['model_digests'][model], 'server': version}
        if phase == 'start':
            request = urllib.request.Request(HOST + '/api/show', data=json.dumps({'model': model.removeprefix('ollama:')}).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=30) as response:
                show = json.load(response)
            p = output / 'private/model_metadata' / (code_hash(model) + '.json')
            if p.exists():
                if read_checkpoint(p) != show:
                    raise ValueError('model metadata drift on resume')
            else:
                immutable_json(p, show)
    atomic_json(output / ('model_check_' + phase + '.json'), result)
    return result

def write_raw(output, records):
    path = output / 'raw.jsonl'
    temporary = output / 'raw.jsonl.tmp'
    temporary.write_text(''.join((json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n' for r in records)))
    temporary.chmod(384)
    temporary.replace(path)

def execute(output):
    plan = read_checkpoint(output / 'manifest.json')
    public = ROOT / plan['analysis_dir']
    if read_checkpoint(public / 'manifest.json') != plan or plan['schema'] != SCHEMA or plan['settings'] != SETTINGS:
        raise ValueError('manifest/config drift')
    cases = read_checkpoint(output / 'private/initials.json')
    if digest(cases) != plan['initials_sha256'] or len(cases) != 545:
        raise ValueError('fixed initial set drift')
    planned = schedule(cases)
    if digest(planned) != plan['schedule_sha256']:
        raise ValueError('schedule drift')
    tests = json.loads((public / 'preflight_tests.json').read_text())
    if tests.get('passed') is not True or tests.get('implementation') != plan['implementation']:
        raise ValueError('required preflight regression tests missing or stale')
    assert_frozen(plan, protected=True)
    with file_lock(ROOT / '.cache/automate_experiment.lock', nonblocking=True), file_lock(output / 'driver.lock', nonblocking=True):
        if active_runs():
            raise RuntimeError('another generation experiment active')
        load_dotenv(ROOT / '.env')
        clients = {m: RecordedClient(m.removeprefix('ollama:'), HOST + '/v1', 'ollama', ollama=True) for m in plan['model_digests']}
        probe_models(plan, clients, output, 'start')
        lookup = {c['case_id']: c for c in cases}
        histories = {(c['case_id'], a): [deepcopy(c['initial'])] for c in cases for a in CONDITIONS}
        records = []
        slots = []
        stage1_saved = False
        with RunTracker(output, plan['run_id'], root=ROOT) as tracker:
            try:
                for slot in planned:
                    if slot['round'] == 2 and (not stage1_saved):
                        assert_frozen(plan, protected=True)
                        probe_models(plan, clients, output, 'stage1')
                        if len(records) != 1635:
                            raise ValueError('stage1 barrier incomplete')
                        frozen = save_stage(plan, cases, records, 1, public, extra_checks={'protected_sources_unchanged': True, 'model_digests_verified': True, 'parameter_acceptance_evidence': '1635 exact wire requests and successful API responses'})
                        stage1private = output / 'private/stage1_records.json'
                        if stage1private.exists():
                            if read_checkpoint(stage1private) != records:
                                raise ValueError('stage1 records changed')
                        else:
                            immutable_json(stage1private, records)
                        stage1_saved = True
                    case = lookup[slot['case_id']]
                    condition = slot['condition']
                    key = (case['case_id'], condition)
                    directory = output / 'private/attempts' / case['case_id'] / condition / f'round_{slot['round']}'
                    if histories[key][-1]['primary']['L3']:
                        if (directory / 'request.json').exists():
                            raise ValueError('request after success')
                        skip = {'case_id': case['case_id'], 'condition': condition, 'round': slot['round'], 'status': 'skipped_after_success'}
                        directory.mkdir(parents=True, exist_ok=True, mode=448)
                        if (directory / 'skip.json').exists():
                            if read_checkpoint(directory / 'skip.json') != skip:
                                raise ValueError('skip checkpoint mismatch')
                        else:
                            immutable_json(directory / 'skip.json', skip)
                        slots.append(skip)
                        continue
                    assert_frozen(plan)
                    tracker.update(phase='notification_ablation_stage1' if slot['round'] == 1 else 'notification_ablation_stage2', model=case['model_spec'], task=case['task_id'], seed=case['base_seed'], recorded=len(records), planned=4905)
                    row = request_attempt(plan, case, condition, slot['round'], histories[key], directory, clients[case['model_spec']], len(records) + 1, slot['nominal_position'])
                    records.append(row)
                    histories[key].append({'code': row['code'], 'primary': row['primary']})
                    write_raw(output, records)
                    slots.append({'case_id': case['case_id'], 'condition': condition, 'round': slot['round'], 'status': 'generated', 'execution_index': len(records)})
                    progress = {'status': 'running', 'run_id': plan['run_id'], 'phase': 'stage1' if slot['round'] == 1 else 'stage2', 'completed_requests': len(records), 'completed_round1_requests': sum((r['round'] == 1 for r in records)), 'successful_condition_paths': sum((h[-1]['primary']['L3'] for h in histories.values())), 'current_model': case['model_spec'], 'max_requests': 4905, 'updated_at_utc': datetime.now(timezone.utc).isoformat()}
                    atomic_json(output / 'progress.json', progress)
                    if len(records) % 10 == 0:
                        print(json.dumps(progress), flush=True)
                if not stage1_saved:
                    raise ValueError('missing stage1 report')
                assert_frozen(plan, protected=True)
                probe_models(plan, clients, output, 'final')
                for key, history in histories.items():
                    validate_history(lookup[key[0]], key[1], history, [r for r in records if (r['case_id'], r['condition']) == key], complete=True)
                if len(slots) != 4905 or len({(s['case_id'], s['condition'], s['round']) for s in slots}) != 4905:
                    raise ValueError('missing/duplicate planned slots')
                if read_checkpoint(output / 'private/stage1_records.json') != [r for r in records if r['round'] == 1]:
                    raise ValueError('stage1 changed during stage2')
                if [json.loads(l) for l in (output / 'raw.jsonl').read_text().splitlines()] != records:
                    raise ValueError('raw record mismatch')
                packet_count = len(list((output / 'private/attempts').glob('*/*/*/request.json')))
                if packet_count != len(records) or list((output / 'private/attempts').glob('*/*/*/failure.json')):
                    raise ValueError('orphan/failed API requests')
                from scripts.measurement_ban_report import write_csv
                write_csv(public / 'generation_disposition.csv', slots)
                final = save_stage(plan, cases, records, 3, public, extra_checks={'protected_sources_unchanged': True, 'model_digests_verified': True, 'planned_slots': 4905, 'skipped_after_success': 4905 - len(records), 'stage1_unchanged': True, 'api_failures': 0, 'runtime_failures': 0})
                status = {'status': 'completed_verified', 'run_id': plan['run_id'], 'actual_requests': len(records), 'stage1_requests': 1635, 'tokens_in': sum((r['tokens_in'] for r in records)), 'tokens_out': sum((r['tokens_out'] for r in records)), 'successful_paths': {a: sum((h[-1]['primary']['L3'] for (key, c), h in histories.items() if c == a)) for a in CONDITIONS}, 'old_results_unchanged': True, 'git_operations_performed': False, 'thesis_updated': False, 'plan_sha256': plan['plan_sha256'], 'final_manifest_sha256': sha(public / 'final/manifest.json')}
                immutable_json(public / 'completion.json', status)
                atomic_json(output / 'progress.json', status)
                tracker.finish(status='completed', recorded=len(records), published=False)
                print(json.dumps(status, ensure_ascii=False), flush=True)
            except BaseException as error:
                failure = {'status': 'stopped_for_review', 'exception_type': type(error).__name__, 'completed_requests': len(records), 'run_id': plan['run_id'], 'automatic_retry': False, 'records_preserved': True}
                atomic_json(output / 'progress.json', failure)
                atomic_json(public / 'interruption.json', failure)
                raise
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if not output.resolve().is_relative_to((ROOT / 'results').resolve()) or not output.name.startswith('notification_ablation_'):
        raise ValueError('new pilot results directory required')
    execute(output)
