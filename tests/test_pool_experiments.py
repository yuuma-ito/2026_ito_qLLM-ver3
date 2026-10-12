"""統合時の重複・設定差・欠落・未検証結果を公開前に拒否する。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.pool_experiments import write_pool, check_preflight


@pytest.fixture(scope='module')
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp('pool')
    for seed in (0, 1):
        output = root / 'results' / str(seed)
        config = dict(experiment_id=f'pool_source_{seed}', models=['mock-mixed'],
                      tasks=['T1_Bell'], seeds=[seed], temperature=0.7, max_rounds=1,
                      conditions=['baseline', 'self_refine', 'execution_feedback', 'self_debugging', 'preventive_spec'],
                      output_dir=str(output))
        path = root / f'{seed}.json'
        path.write_text(json.dumps(config))
        subprocess.run([sys.executable, '-m', 'scripts.run_experiment', '--config', str(path)],
                       env=dict(os.environ, OMP_NUM_THREADS='1'), capture_output=True, check=True)
        (output / 'automation_report.json').write_text('{"passed": true}')
    plan = dict(experiment_id='pooled', output_dir='results/pooled',
                models=['mock-mixed'], seeds=[0, 1], source_dirs=['results/0', 'results/1'])
    return root, plan


def test_pool_preserves_sources_and_has_balanced_records(sources):
    root, plan = sources
    before = [(root / p / 'raw.jsonl').read_bytes() for p in plan['source_dirs']]
    output = write_pool(plan, root=root)
    report = json.loads((output / 'sanity_report.json').read_text())
    assert report['passed'] and report['actual_records'] == 10
    assert not (output / 'raw.jsonl').exists()
    assert before == [(root / p / 'raw.jsonl').read_bytes() for p in plan['source_dirs']]
    assert 'source_experiment_id' in (output / 'summary_by_source.csv').read_text()
    assert 'code_diff_round0_final' not in (output / 'degradation_cases.csv').read_text()


def test_preflight_rejects_overlap_before_generation(sources, monkeypatch):
    root, plan = sources
    saved = json.loads((root / 'results/0/experiment_config.json').read_text())
    manifest = json.loads((root / 'results/0/manifest.json').read_text())
    monkeypatch.setattr('scripts.pool_experiments.build_manifest', lambda *args: manifest)
    # The two saved runs already fill the target: adding seed 0 would repeat it.
    with pytest.raises(ValueError, match='重複'):
        check_preflight(plan, saved, {}, root=root)


@pytest.mark.parametrize('problem', ['duplicate', 'missing', 'temperature', 'digest', 'catalog', 'schema', 'unverified'])
def test_pool_rejects_invalid_sources(sources, tmp_path, problem):
    import shutil
    source_root, original = sources
    shutil.copytree(source_root / 'results', tmp_path / 'results')
    plan = copy.deepcopy(original)
    plan['output_dir'] = 'results/new_pool'
    # Absolute saved paths do not affect input identity or coverage.
    output = tmp_path / 'results/1'
    if problem == 'duplicate':
        plan['source_dirs'].append(plan['source_dirs'][0])
    elif problem == 'missing':
        plan['seeds'] = [0, 1, 2]
    elif problem == 'catalog':
        path = output / 'intervention_catalog_by_error.csv'
        path.write_text(path.read_text().replace('self_refine', 'invalid'))
    elif problem == 'unverified':
        (output / 'automation_report.json').write_text('{"passed": false}')
    elif problem == 'digest':
        # Turn a valid model label into Ollama across both source configs/records.
        for name in plan['source_dirs']:
            source = tmp_path / name
            for filename in ('experiment_config.json', 'manifest.json', 'raw.jsonl',
                             'intervention_catalog_by_error_model.csv'):
                path = source / filename
                path.write_text(path.read_text().replace('mock-mixed', 'ollama:model'))
        plan['models'] = ['ollama:model']  # Missing recorded digest must block.
    else:
        path = output / 'manifest.json'
        data = json.loads(path.read_text())
        if problem == 'schema':
            data['schema_version'] = '2.0'
        else:
            data['config']['temperature'] = 0.8
            (output / 'experiment_config.json').write_text(json.dumps(data['config']))
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        write_pool(plan, root=tmp_path)
