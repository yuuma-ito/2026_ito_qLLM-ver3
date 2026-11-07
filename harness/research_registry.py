"""Local provenance helpers. No model calls, generated code execution or scoring."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def local_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Path outside repository')
    return path


def read_json(root, name):
    value = json.loads(local_path(root, name).read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Expected JSON object')
    return value


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluation_metadata(manifest):
    evaluator = manifest.get('evaluator', {})
    if not isinstance(evaluator, dict):
        evaluator = {}
    return {
        'evaluator_version': manifest.get('evaluator_version') or evaluator.get('primary_version'),
        'diagnostic_policy_version': manifest.get('diagnostic_policy_version'),
        'evaluator_fingerprints': manifest.get('evaluator_fingerprints') or evaluator.get('files'),
        'prompt_fingerprints': manifest.get('prompt_fingerprints'),
        'evaluation_sampling': manifest.get('evaluation_sampling') or evaluator.get('sampling'),
    }


def model_digests(manifest):
    digests = dict(manifest.get('model_digests') or {})
    for model in manifest.get('shared_server', {}).get('models', []):
        if model.get('name') and model.get('digest'):
            digests[model['name']] = model['digest']
    return {name.removeprefix('ollama:'): digest for name, digest in digests.items()}


def compatibility(left_config, left_manifest, right_config, right_manifest):
    """Conservative setup comparison: missing evidence never counts as equality."""
    from harness.experiment import validate_config
    left, right = validate_config(left_config), validate_config(right_config)
    different, unknown = [], []
    fields = {
        'models': (sorted(left['models']), sorted(right['models'])),
        'conditions': ([(c.id, c.intervention, c.max_rounds) for c in left['conditions']],
                       [(c.id, c.intervention, c.max_rounds) for c in right['conditions']]),
        'temperature': (left['temperature'], right['temperature']),
        'generation_settings': (left_config.get('generation_settings'), right_config.get('generation_settings')),
        'schema_version': (left_manifest.get('schema_version'), right_manifest.get('schema_version')),
    }
    a, b = evaluation_metadata(left_manifest), evaluation_metadata(right_manifest)
    fields.update({key: (a[key], b[key]) for key in a})
    for key in ('qiskit', 'qiskit_aer'):
        fields[key] = (left_manifest.get('environment', {}).get(key), right_manifest.get('environment', {}).get(key))
    # Model digests must have evidence for every model; names alone cannot prove identity.
    a, b = model_digests(left_manifest), model_digests(right_manifest)
    names = {name.removeprefix('ollama:') for name in left['models'] + right['models']}
    if all(all(isinstance(d.get(name), str) and re.fullmatch(r'[0-9a-f]{64}', d[name])
               for name in names) for d in (a, b)):
        fields['model_digests'] = ({k: a[k] for k in names}, {k: b[k] for k in names})
    else:
        fields['model_digests'] = (None, None)
    def evidence(value):
        if value is None or value == {} or value == []:
            return False
        if isinstance(value, dict):
            return all(evidence(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return all(evidence(v) for v in value)
        return True
    for key, (a, b) in fields.items():
        if not evidence(a) or not evidence(b):
            unknown.append(key)
        elif a != b:
            different.append(key)
    return dict(status='different' if different else 'unknown' if unknown else 'matched',
                different=different, unknown=unknown)
