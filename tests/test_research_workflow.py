"""Provenance, claim corruption detection and read-only experiment planning."""
from copy import deepcopy
import json
from pathlib import Path
import zipfile

import pytest

from harness.experiment import build_manifest
from harness.research_registry import compatibility, sha256
from scripts import check_research_claims as claims
from scripts import experiment_preflight as preflight
from scripts import research_ledger as ledger


def save(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')
    return path


@pytest.fixture
def config():
    return dict(experiment_id='planned', models=['mock'], tasks=['T1_Bell'], seeds=[0, 1],
                temperature=0.7, max_rounds=3,
                conditions=['baseline', 'self_refine', 'execution_feedback', 'self_debugging', 'preventive_spec'],
                generation_settings={'max_tokens': 1024}, output_dir='results/planned')


def complete_manifest(config):
    return dict(schema_version='2.1', evaluator_version='v4', diagnostic_policy_version='v2',
                evaluator_fingerprints={'evaluator': 'a'}, prompt_fingerprints={'system': 'b'},
                evaluation_sampling={'shots': 8192}, model_digests={'mock': 'a' * 64},
                environment={'qiskit': '2', 'qiskit_aer': '0.17'}, elapsed_sec=3600,
                sanity_passed=True, config=config)


def test_request_upper_bound_and_no_output_creation(config, tmp_path):
    before = list(tmp_path.rglob('*'))
    report = preflight.check(config, tmp_path, new_run=True)
    assert report['planned_initial_groups'] == 2
    assert report['planned_condition_records'] == 10
    assert report['model_request_upper_bound'] == 22
    assert report['duration_estimate']['status'] == 'unavailable'
    assert list(tmp_path.rglob('*')) == before


def test_existing_output_blocks_new_run_but_resume_requires_saved_config(config, tmp_path):
    save(tmp_path, 'results/planned/experiment_config.json', config)
    assert not preflight.check(config, tmp_path)['passed']
    assert preflight.check(config, tmp_path, new_run=True)['passed']
    assert preflight.check(config, tmp_path, resume=True)['passed']
    changed = dict(config, temperature=0.9)
    assert not preflight.check(changed, tmp_path, resume=True)['passed']


def test_pair_selection_does_not_expand_to_cartesian_grid(config, tmp_path):
    config['pairs'] = [dict(model='mock', task='T1_Bell', seed=1)]
    result = preflight.check(config, tmp_path)
    assert result['planned_initial_groups'] == 1
    assert result['planned_condition_records'] == 5
    assert result['model_request_upper_bound'] == 11


def test_missing_evidence_never_means_comparable(config):
    result = compatibility(config, {}, config, {})
    assert result['status'] == 'unknown' and 'evaluator_version' in result['unknown']
    manifest = complete_manifest(config)
    assert compatibility(config, manifest, config, manifest)['status'] == 'matched'
    changed = deepcopy(manifest)
    changed['evaluator_version'] = 'v3'
    assert 'evaluator_version' in compatibility(config, manifest, config, changed)['different']
    changed = deepcopy(manifest)
    changed['model_digests'] = {}
    assert 'model_digests' in compatibility(config, manifest, config, changed)['unknown']
    changed = deepcopy(manifest)
    changed['prompt_fingerprints'] = {'system': None}
    assert 'prompt_fingerprints' in compatibility(config, changed, config, changed)['unknown']


def test_overlap_count_and_timing_require_verified_matching_workload(config, tmp_path, monkeypatch):
    previous = dict(config, experiment_id='old', output_dir='results/old')
    save(tmp_path, 'results/old/experiment_config.json', previous)
    manifest = complete_manifest(previous)
    save(tmp_path, 'results/old/manifest.json', manifest)
    save(tmp_path, 'results/old/automation_report.json', {'passed': True})
    monkeypatch.setattr(preflight, 'build_manifest', lambda *_: complete_manifest(config))
    report = preflight.check(config, tmp_path)
    assert report['overlaps'][0]['overlapping_condition_records'] == 10
    assert report['overlaps'][0]['overlapping_initial_groups'] == 2
    assert report['duration_estimate']['lower_hours'] == 1
    manifest['evaluator_version'] = 'old'
    save(tmp_path, 'results/old/manifest.json', manifest)
    assert preflight.check(config, tmp_path)['duration_estimate']['status'] == 'unavailable'


def test_resume_with_api_failure_is_blocked(config, tmp_path):
    save(tmp_path, 'results/planned/experiment_config.json', config)
    row = dict(experiment_id='planned', condition_id='baseline', model_spec='mock', task_id='T1_Bell',
               base_seed=0, L2=False, rounds=[{'generation_error': 'private'}])
    (tmp_path / 'results/planned/raw.jsonl').write_text(json.dumps(row) + '\n')
    report = preflight.check(config, tmp_path, resume=True)
    assert not report['passed'] and 'private' not in json.dumps(report)


def test_ledger_preserves_missing_hypothesis_and_old_version(config, tmp_path):
    save(tmp_path, 'results/planned/experiment_config.json', config)
    save(tmp_path, 'results/planned/manifest.json', {'evaluator_version': 'old'})
    save(tmp_path, 'configs/research_registry.json', {'entries': []})
    result = ledger.build(tmp_path)
    row = result['entries'][0]
    assert row['hypothesis'] is None
    assert row['kind'] is None
    assert row['evaluation']['evaluator_version'] == 'old'
    assert row['planned_records'] == 10
    assert 'hypothesis: 未登録' in row['issues']


def test_ledger_separates_generation_and_frozen_reanalysis(config, tmp_path):
    save(tmp_path, 'results/planned/experiment_config.json', config)
    save(tmp_path, 'results/planned/manifest.json', {'evaluator_version': 'old'})
    save(tmp_path, 'docs/fixed/manifest.json', {'evaluator_version': 'new'})
    save(tmp_path, 'configs/research_registry.json', {'entries': [dict(
        id='fixed', kind='reanalysis', parents=['planned'], manifest='docs/fixed/manifest.json',
        generation_manifest='results/planned/manifest.json')]})
    row = next(r for r in ledger.build(tmp_path)['entries'] if r['id'] == 'fixed')
    assert row['evaluation']['evaluator_version'] == 'new'
    assert row['generation_evaluation']['evaluator_version'] == 'old'
    assert row['parents'] == ['planned']


def test_cyclic_and_duplicate_registry_is_rejected(tmp_path):
    for entries in ([dict(id='a', parents=['b']), dict(id='b', parents=['a'])], [dict(id='a'), dict(id='a')]):
        save(tmp_path, 'configs/research_registry.json', {'entries': entries})
        with pytest.raises(ValueError):
            ledger.build(tmp_path)


def write_document(path, numerator='2', denominator='5', percent='40.0%'):
    def cell(s):
        return '<w:tc><w:p><w:r><w:t>' + s + '</w:t></w:r></w:p></w:tc>'
    def row(values):
        return '<w:tr>' + ''.join(cell(s) for s in values) + '</w:tr>'
    xml = ('<w:document xmlns:w="' + claims.NS['w'] + '"><w:body>'
           + '<w:p><w:r><w:t>成功' + numerator + '/' + denominator + '組</w:t></w:r></w:p>'
           + '<w:tbl>' + row(['条件', '失敗数', '成功数', '率'])
           + row(['F', denominator, numerator, percent]) + '</w:tbl></w:body></w:document>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', xml)


@pytest.fixture
def evidence(tmp_path):
    csv_path = tmp_path / 'summary.csv'
    csv_path.write_text('condition,numerator,denominator\nF,2,5\n')
    doc = tmp_path / 'thesis.docx'
    write_document(doc)
    def ref(column):
        return dict(csv='summary.csv', where={'condition': 'F'}, column=column)
    spec = dict(scope='registered test table and prose', sources={'summary.csv': sha256(csv_path)}, claims=[
        dict(id='table', type='table', document='thesis.docx', headers=['条件', '失敗数', '成功数', '率'],
             rows=[['F', ref('denominator'), ref('numerator'), dict(ratio=[ref('numerator'), ref('denominator')], scale=100, digits=1, suffix='%')]]),
        dict(id='text', type='text', document='thesis.docx', pattern=r'成功(?P<value>[0-9]+/[0-9]+)組',
             value=dict(join=[ref('numerator'), ref('denominator')], separator='/'))])
    assert claims.audit(spec, tmp_path)['passed']
    return spec, tmp_path


@pytest.mark.parametrize('numerator,denominator,percent', [('3','5','40.0%'),('2','6','40.0%'),('2','5','50.0%')])
def test_detects_changed_manuscript_count_denominator_or_rate(evidence, numerator, denominator, percent):
    spec, root = evidence
    write_document(root / 'thesis.docx', numerator, denominator, percent)
    assert not claims.audit(spec, root)['passed']


def test_detects_changed_snapshot_hash_and_duplicate_aggregate_rows(evidence):
    spec, root = evidence
    p = root / 'summary.csv'
    p.write_text(p.read_text() + 'F,2,5\n')
    report = claims.audit(spec, root)
    assert not report['passed']
    assert report['results'][0]['status'] == '不一致'
    assert report['results'][1]['status'] == '根拠不足'


def test_removed_numeric_claim_cannot_silently_pass(evidence):
    spec, root = evidence
    spec['claims'][1]['pattern'] = r'存在しない箇所(?P<value>[0-9]+)'
    assert claims.audit(spec, root)['results'][-1]['status'] == '不一致'


def test_missing_source_and_outside_repository_are_not_verified(evidence):
    spec, root = evidence
    (root / 'summary.csv').unlink()
    assert not claims.audit(spec, root)['passed']
    spec['sources'] = {'../outside.csv': 'a' * 64}
    with pytest.raises(ValueError):
        claims.audit(spec, root)


def test_frozen_manifest_detects_changed_supporting_output(evidence):
    spec, root = evidence
    extra = root / 'support.csv'
    extra.write_text('count\n5\n')
    manifest = save(root, 'manifest.json', {'outputs': {'support.csv': sha256(extra)}})
    spec['sources']['manifest.json'] = sha256(manifest)
    spec['manifest_checks'] = [dict(path='manifest.json', mapping='outputs', base='.')]
    assert claims.audit(spec, root)['passed']
    extra.write_text('count\n6\n')
    report = claims.audit(spec, root)
    assert not report['passed']
    assert next(r for r in report['results'] if r['id'] == 'manifest:manifest.json')['status'] == '不一致'


def test_model_snapshot_enables_only_declared_reference_estimate(config, tmp_path, monkeypatch):
    previous = dict(config, experiment_id='old', output_dir='results/old')
    save(tmp_path, 'results/old/experiment_config.json', previous)
    save(tmp_path, 'results/old/manifest.json', complete_manifest(previous))
    save(tmp_path, 'results/old/automation_report.json', {'passed': True})
    current = complete_manifest(config)
    current.pop('model_digests')
    monkeypatch.setattr(preflight, 'build_manifest', lambda *_: deepcopy(current))
    assert preflight.check(config, tmp_path)['duration_estimate']['status'] == 'unavailable'
    save(tmp_path, 'digests.json', {'model_digests': {'mock': 'a' * 64}})
    report = preflight.check(config, tmp_path, model_snapshot='digests.json')
    assert report['duration_estimate']['lower_hours'] == 1
    assert report['model_digest_evidence']['sha256'] == sha256(tmp_path / 'digests.json')
    assert any('現時点' in s for s in report['warnings'])


def test_live_experiment_blocks_additional_generation_plan(config, tmp_path):
    from harness.run_state import RunTracker
    with RunTracker(tmp_path / 'results/live', 'live', root=tmp_path):
        report = preflight.check(config, tmp_path, new_run=True)
    assert not report['passed']
    assert report['blockers']
