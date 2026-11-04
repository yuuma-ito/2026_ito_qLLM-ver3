"""Independent baseline restarts with immutable, paired round-zero evidence.

This is a separate condition/runner: the five historical interventions stay unchanged.
No network calls or generated-code execution occur when importing or preparing it.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import time

from harness.code_extractor import extract_code
from harness.interventions import build_initial_prompt
from harness.isolated_evaluation import isolated_evaluate, profile
from harness.llm_clients import SYSTEM_PROMPT
from harness.run_state import atomic_json
from tasks import all_tasks, get_task

CONDITION = 'independent_4'
SCHEMA = 'independent_4_v1'
ROOT = Path(__file__).resolve().parents[1]
LEVELS = ('L0', 'L1', 'L2', 'L3')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hash(code):
    return hashlib.sha256(code.encode()).hexdigest()


def read_csv(path):
    with Path(path).open(newline='') as f:
        return list(csv.DictReader(f))


def truth(value):
    if value not in ('True', 'False'):
        raise ValueError('invalid saved boolean')
    return value == 'True'


def unique(rows, key):
    out = {}
    for row in rows:
        k = key(row)
        if k in out:
            raise ValueError('duplicate record')
        out[k] = row
    return out


def identity(row):
    return row['model_spec'], row['task_id'], int(row['base_seed'])


def levels(primary):
    """Validate cumulative reach within an attempt; never rewrite primary verdicts."""
    values = [primary[k] for k in LEVELS]
    if any(type(v) is not bool for v in values) or any(b and not a for a, b in zip(values, values[1:])):
        raise ValueError('L0-L3 are not cumulative')
    if primary['L3'] and primary.get('structure_match') is not True:
        raise ValueError('L3 requires structure_match')
    if not primary.get('failure_stage') or not primary.get('error_category'):
        raise ValueError('missing failure metadata')


def seed_for(model, task, base_seed, round_index, namespace='independent_4_v1'):
    if round_index not in (1, 2, 3):
        raise ValueError('new round must be 1..3; generation number is round+1')
    # Avoid the historical 0..22 seeds and overlapping base_seed+round requests.
    n = int(digest([namespace, model, task, base_seed, round_index])[:16], 16)
    return 1_000_000 + n % (2**31 - 1_000_000)


def validate_config(config):
    if config.get('condition_id') != CONDITION or config.get('max_generations') != 4:
        raise ValueError('only independent_4 with four total opportunities is supported')
    if config.get('generation_settings') != {'max_tokens': 1024, 'timeout_sec': 600,
                                              'reasoning_effort': 'none', 'parallel_requests': 1}:
        raise ValueError('generation settings differ from the fixed comparison')
    if config.get('temperature') != .7 or not config.get('experiment_id'):
        raise ValueError('invalid experiment id/temperature')
    tasks = config.get('tasks')
    models, seeds = config.get('models', []), config.get('seeds', [])
    if not models or not seeds or not tasks:
        raise ValueError('empty grid')
    if any(len(x) != len(set(x)) for x in (models, seeds, tasks)):
        raise ValueError('duplicate grid member')
    if any(not m.startswith('ollama:') for m in models):
        raise ValueError('this protocol requires seeded Ollama requests')
    expected = {(m, t, s) for m in models for t in tasks for s in seeds}
    new_seeds = [seed_for(*k, r, config['seed_namespace']) for k in sorted(expected) for r in (1, 2, 3)]
    if len(new_seeds) != len(set(new_seeds)):
        raise ValueError('derived seed collision; choose and review a new namespace')
    return expected


def load_cohort(config, root=ROOT):
    """Read/hash-check source evidence; never call the evaluator or any model."""
    expected = validate_config(config)
    source = config['sources']
    manifest = json.loads((root / source['core_manifest']).read_text())
    inputs = dict(manifest['inputs'])
    for name, hashed in inputs.items():
        if sha(root / name) != hashed:
            raise ValueError('fixed source hash mismatch: ' + name)
    settings = json.loads((root / source['settings']).read_text())
    old_profile = json.loads((root / source['evaluation_profile']).read_text())['evaluator']
    current = profile()
    for key in ('primary_version', 'supplement_version', 'sandbox_policy', 'files',
                'packages', 'limits_per_stage', 'sampling'):
        if current[key] != old_profile[key]:
            raise ValueError('evaluator/profile drift: ' + key)
    public = unique([r for r in read_csv(root / source['rounds'])
                     if r['condition_id'] == 'baseline' and r['round'] == '0'], identity)
    paired = read_csv(root / source['paired'])
    pairs = unique(paired, lambda r: (*identity(r), r['condition_id']))
    if set(public) != expected or set(pairs) != {(*k, c) for k in expected for c in
                                              ('self_refine', 'execution_feedback', 'self_debugging', 'preventive_spec')}:
        raise ValueError('missing/unexpected fixed group/condition')
    raw = {}
    digests = {}
    for s in settings['sources']:
        directory = root / s['source_dir']
        path = directory / 'raw.jsonl'
        if sha(path) != s['raw_sha256'] or sha(directory / 'experiment_config.json') != s['config_sha256']:
            raise ValueError('raw/config integrity mismatch')
        saved_manifest = json.loads((directory / 'manifest.json').read_text())
        if saved_manifest['prompt_fingerprints']['system_txt_sha256'] != sha(root / 'prompts/system.txt'):
            raise ValueError('baseline system prompt drift')
        if not s['initial_prompt_source_verified'] or s['generation_settings'] != config['generation_settings'] or s['temperature'] != config['temperature']:
            raise ValueError('historical generation setting mismatch')
        for model, hashed in s['model_digests'].items():
            if not hashed or (model in digests and digests[model] != hashed):
                raise ValueError('missing/inconsistent model digest')
            digests[model] = hashed
        inputs[str(path.relative_to(root))] = s['raw_sha256']
        with path.open() as f:
            records = [json.loads(line) for line in f if line.strip()]
        unique(records, lambda r: (*identity(r), r['condition_id']))
        for record in records:
            if record['condition_id'] == 'baseline':
                k = identity(record)
                if k in raw:
                    raise ValueError('overlapping raw cohort')
                if len(record['rounds']) != 1:
                    raise ValueError('baseline has extra rounds')
                raw[k] = (s['source_dir'], record['rounds'][0])
    if set(raw) != expected:
        raise ValueError('raw baseline coverage mismatch')
    cohort = []
    for k in sorted(expected):
        e = public[k]
        src, saved = raw[k]
        code = saved['extracted_code']
        if src != e['source_dir'] or code_hash(code) != e['code_sha256'] or e['runtime_status'] != 'completed':
            raise ValueError('initial source/code/runtime mismatch')
        primary = {key: truth(e['new_' + key]) for key in (*LEVELS, 'structure_match')}
        distance = float(e['new_L2_distance']) if e['new_L2_distance'] else None
        if distance is not None and not math.isfinite(distance):
            distance = None
        primary.update(failure_stage=e['new_failure_stage'], error_category=e['new_error_category'],
                       exception_type=e['new_exception_type'],
                       L2_distance=distance)
        levels(primary)
        for c in ('self_refine', 'execution_feedback', 'self_debugging', 'preventive_spec'):
            if truth(pairs[(*k, c)]['initial_success']) != primary['L3']:
                raise ValueError('fixed comparator initial verdict mismatch')
        round0 = dict(round=0, generation_number=1, round_seed=int(saved['round_seed']),
                      reused=True, code_sha256=code_hash(code), extracted_code=code,
                      primary=primary, tokens_in=int(saved['tokens_in']), tokens_out=int(saved['tokens_out']),
                      generation_seconds=float(saved['elapsed_sec']), evaluation_seconds=None,
                      evaluation_source=source['rounds'], source_dir=src,
                      baseline_record_key=e['record_key'])
        cohort.append(dict(model_spec=k[0], task_id=k[1], base_seed=k[2], source_dir=src,
                           baseline_record_key=e['record_key'],
                           task_difficulty=get_task(k[1]).task_difficulty, initial=round0))
    for name in source.values():
        inputs[name] = sha(root / name)
    return cohort, dict(inputs=inputs, model_digests=digests, evaluator=current), paired


def strict_request(client, prompt, seed, temperature):
    """Exactly one API attempt: no seed fallback and no ambiguous replay."""
    started = time.monotonic()
    response = client._create(prompt, temperature, seed)
    usage = getattr(response, 'usage', None)
    if usage is None or any(type(getattr(usage, k, None)) is not int or getattr(usage, k) < 0
                            for k in ('prompt_tokens', 'completion_tokens')):
        raise RuntimeError('missing/invalid token usage')
    if response.model != client.model_id:
        raise RuntimeError('response model mismatch')
    if usage.completion_tokens > 1024:
        raise RuntimeError('response exceeded the frozen output-token limit')
    return dict(raw_output=response.choices[0].message.content or '', response=response.model_dump(mode='json'),
                tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
                generation_seconds=time.monotonic()-started,
                finish_reason=response.choices[0].finish_reason)


def immutable_json(path, value):
    if path.exists():
        raise ValueError('refusing to overwrite checkpoint')
    atomic_json(path, value)
    path.chmod(0o600)
    atomic_json(path.with_suffix(path.suffix + '.integrity.json'), {'sha256': sha(path)})


def read_checkpoint(path):
    integrity = path.with_suffix(path.suffix + '.integrity.json')
    if not integrity.exists() or json.loads(integrity.read_text())['sha256'] != sha(path):
        raise ValueError('checkpoint integrity mismatch')
    return json.loads(path.read_text())


def validate_record(record, case, config, *, complete=True):
    if record['schema_version'] != SCHEMA or record['condition_id'] != CONDITION:
        raise ValueError('unexpected schema/condition')
    if record['experiment_id'] != config['experiment_id']:
        raise ValueError('experiment run identity mismatch')
    for key in ('model_spec', 'task_id', 'base_seed', 'baseline_record_key', 'source_dir'):
        if record[key] != case[key]:
            raise ValueError('initial group mismatch')
    rounds = record['rounds']
    if not 1 <= len(rounds) <= 4 or [r['round'] for r in rounds] != list(range(len(rounds))):
        raise ValueError('missing/duplicate/unexpected round')
    if rounds[0] != case['initial']:
        raise ValueError('shared initial history was changed')
    prompt_hash = code_hash(build_initial_prompt('baseline', get_task(case['task_id'])))
    for i, r in enumerate(rounds):
        levels(r['primary'])
        if r['generation_number'] != i+1 or code_hash(r['extracted_code']) != r['code_sha256']:
            raise ValueError('generation number/code hash mismatch')
        if any(type(r[k]) is not int or r[k] < 0 for k in ('tokens_in', 'tokens_out')) or not math.isfinite(r['generation_seconds']) or r['generation_seconds'] < 0:
            raise ValueError('invalid costs')
        if i:
            if r['reused'] or r['round_seed'] != seed_for(case['model_spec'], case['task_id'], case['base_seed'], i, config['seed_namespace']):
                raise ValueError('seed/reuse mismatch')
            if r['prompt_sha256'] != prompt_hash or r['system_sha256'] != code_hash(SYSTEM_PROMPT):
                raise ValueError('history contaminated independent prompt')
        if r['primary']['L3'] and i != len(rounds)-1:
            raise ValueError('continued after success')
    success = rounds[-1]['primary']['L3']
    if complete and not success and len(rounds) != 4:
        raise ValueError('incomplete unsuccessful independent path')
    if record['final_success'] != success:
        raise ValueError('final success mismatch')
    first = next((r['round'] for r in rounds if r['primary']['L3']), None)
    if record['first_success_round'] != first:
        raise ValueError('first success round mismatch')
    if record['first_success_generation'] != (first+1 if first is not None else None):
        raise ValueError('first success generation mismatch')


def run_case(case, config, client, directory, *, request=strict_request, executor=isolated_evaluate):
    """Reuse initial history; checkpoint each new request before any side effect."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    completed = directory / 'completed.json'
    if completed.exists():
        result = read_checkpoint(completed)
        validate_record(result, case, config)
        return result
    task = get_task(case['task_id'])
    prompt = build_initial_prompt('baseline', task)
    rows = [deepcopy(case['initial'])]
    for index in range(1, 4):
        if rows[-1]['primary']['L3']:
            break
        seed = seed_for(case['model_spec'], task.id, case['base_seed'], index, config['seed_namespace'])
        req = directory / f'round_{index}_request.json'
        resp = directory / f'round_{index}_response.json'
        evpath = directory / f'round_{index}_evaluation.json'
        started = directory / f'round_{index}_evaluation_started.json'
        data = dict(round=index, generation_number=index+1, round_seed=seed, model_spec=case['model_spec'],
                    baseline_record_key=case['baseline_record_key'], system=SYSTEM_PROMPT, user=prompt,
                    temperature=config['temperature'], generation_settings=config['generation_settings'])
        if req.exists():
            if read_checkpoint(req) != data:
                raise ValueError('request checkpoint mismatch')
            if not resp.exists():
                raise RuntimeError('ambiguous request; manual reconciliation required; no automatic retry')
        else:
            if resp.exists() or evpath.exists():
                raise ValueError('unexpected response/evaluation checkpoint')
            immutable_json(req, data)
            response = request(client, prompt, seed, config['temperature'])
            immutable_json(resp, response)
        response = read_checkpoint(resp)
        code = extract_code(response['raw_output'])
        if not evpath.exists():
            if started.exists():
                raise RuntimeError('ambiguous evaluation; manual reconciliation required')
            immutable_json(started, {'code_sha256': code_hash(code)})
            evaluated = executor(code, task.id)
            immutable_json(evpath, evaluated)
        evaluated = read_checkpoint(evpath)
        if evaluated.get('runtime_status') != 'completed':
            raise RuntimeError('infrastructure evaluation failure; not a model failure')
        primary = evaluated['primary']
        levels(primary)
        rows.append(dict(round=index, generation_number=index+1, round_seed=seed, reused=False,
                         prompt_sha256=code_hash(prompt), system_sha256=code_hash(SYSTEM_PROMPT),
                         code_sha256=code_hash(code), extracted_code=code, primary=primary,
                         tokens_in=response['tokens_in'], tokens_out=response['tokens_out'],
                         generation_seconds=response['generation_seconds'],
                         evaluation_seconds=evaluated.get('seconds', 0)+evaluated.get('build_seconds', 0),
                         finish_reason=response.get('finish_reason'),
                         repeated_code=any(r['code_sha256'] == code_hash(code) for r in rows)))
    result = {k: case[k] for k in ('model_spec', 'task_id', 'base_seed', 'source_dir', 'baseline_record_key', 'task_difficulty')}
    result.update(schema_version=SCHEMA, condition_id=CONDITION, experiment_id=config['experiment_id'],
                  rounds=rows, final_success=rows[-1]['primary']['L3'],
                  first_success_round=next((r['round'] for r in rows if r['primary']['L3']), None),
                  first_success_generation=next((r['generation_number'] for r in rows if r['primary']['L3']), None),
                  comparison_kind='independent_regeneration')
    validate_record(result, case, config)
    immutable_json(completed, result)
    return result
