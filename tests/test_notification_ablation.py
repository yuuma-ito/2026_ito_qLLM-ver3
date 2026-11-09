"""Authored code and fake API packets only; never contact a live model."""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest

from harness.notification_ablation import (CONDITIONS, COMPARISONS, NOTICE, REMOVED_SENTENCE,
    build_prompt, ordered_cases, schedule, paired_seed, validate_history)
from harness.independent_4 import digest, code_hash, read_checkpoint
from harness.interventions.prompts import build_intervention_prompt
from scripts.run_notification_ablation import request_attempt
from scripts.analyze_notification_ablation import aggregates, save_stage
from scripts import complete_notification_ablation as publication
from tasks import get_task


def primary(success=False):
    return dict(L0=True, L1=True, L2=success, L3=success, structure_match=True,
                error_category='ok' if success else 'wrong_output', failure_stage='ok' if success else 'evaluate',
                exception_type='', error_message='authored fixture', L2_distance=0.0 if success else 0.5,
                actual_distribution=None)


def case(i=0, model='ollama:fixture'):
    initial = dict(round=0, code='x = 0', hash=code_hash('x = 0'), primary=primary(),
                   error='wrong_output', success=False, tokens_in=1, tokens_out=1, finish=None)
    return dict(case_id=digest(i), model_spec=model, task_id='T1_Bell', base_seed=i,
                initial_error='wrong_output', historical_outcome='neither', initial=initial)


def response(code='x = 1'):
    return dict(raw_output='```python\n'+code+'\n```', tokens_in=10, tokens_out=5,
                generation_seconds=0.1, finish_reason='stop',
                response=dict(model='fixture', usage=dict(prompt_tokens=10, completion_tokens=5),
                              choices=[dict(finish_reason='stop')]))


def plan():
    return dict(run_id='authored_fixture', plan_sha256='fixture', diagnostic_policy_version='diagnostic_policy_v2_structure_qubits',
                model_digests={'ollama:fixture':'fixture_digest'})


def make_record(tmp_path, c, condition, *, success=True):
    return request_attempt(plan(), c, condition, 1, [c['initial']], tmp_path/condition, object(), 1, 1,
        request=lambda *args: response(), executor=lambda *args: dict(runtime_status='completed', primary=primary(success)),
        server_probe=lambda *args: {'version':'fixture'})


def test_only_planned_prompt_additions_and_historical_bridge():
    c=case(); task=get_task(c['task_id']); previous=c['initial']
    old=build_intervention_prompt('self_refine', task, previous['code'], None)
    r0=build_prompt('R0', task, previous)
    r1=build_prompt('R1', task, previous)
    r2=build_prompt('R2', task, previous)
    assert r0 == old.replace(REMOVED_SENTENCE, '')
    assert r1.replace(NOTICE+'\n', '') == r0
    section=r2.split('検証器から得られた情報:\n', 1)[1].split('\n\n', 1)[0]
    assert r2.replace('検証器から得られた情報:\n'+section+'\n\n', '') == r1
    assert REMOVED_SENTENCE not in r2
    assert 'DEBUG:' not in r2


def test_all_cases_and_order_ignore_old_outcomes():
    cases=[case(i, 'ollama:m'+str(i%5)) for i in range(545)]
    ordered=ordered_cases(cases)
    changed=[dict(c, historical_outcome='changed') for c in reversed(cases)]
    assert [c['case_id'] for c in ordered] == [c['case_id'] for c in ordered_cases(changed)]
    slots=schedule(ordered)
    assert len(slots)==len({(s['case_id'],s['condition'],s['round']) for s in slots})==4905
    for model in {c['model_spec'] for c in cases}:
        ids={c['case_id'] for c in cases if c['model_spec']==model}
        for rnd in (1,2,3):
            for condition in CONDITIONS:
                counts=Counter(s['nominal_position'] for s in slots if s['case_id'] in ids and s['round']==rnd and s['condition']==condition)
                assert max(counts.values())-min(counts.values()) <= 1
    for c in cases:
        for rnd in (1,2,3):
            assert {s['seed'] for s in slots if s['case_id']==c['case_id'] and s['round']==rnd} == {paired_seed(c,rnd)}


@pytest.mark.parametrize('condition', CONDITIONS)
def test_exact_packets_reused_without_duplicate_api_call_and_mutation_detected(tmp_path, condition):
    c=case(); r=make_record(tmp_path,c,condition)
    validate_history(c,condition,[c['initial'],dict(code=r['code'],primary=r['primary'])],[r],complete=True)
    again=request_attempt(plan(),c,condition,1,[c['initial']],tmp_path/condition,object(),1,1,
        request=lambda *args: pytest.fail('saved request must not be resent'),
        executor=lambda *args: pytest.fail('saved evaluation must not be repeated'),
        server_probe=lambda *args: pytest.fail('no new metadata probe for saved packet'))
    assert again==r
    corrupted=deepcopy(r); corrupted['previous_code_sha256']='wrong'
    with pytest.raises(ValueError,match='history'):
        validate_history(c,condition,[c['initial'],dict(code=r['code'],primary=r['primary'])],[corrupted])


def test_ambiguous_failed_request_is_never_replayed(tmp_path):
    c=case(); calls=[]
    def fail(*args):
        calls.append(1)
        raise TimeoutError('authored fixture')
    args=(plan(),c,'R1',1,[c['initial']],tmp_path,object(),1,1)
    with pytest.raises(TimeoutError):
        request_attempt(*args,request=fail,server_probe=lambda *args: {})
    with pytest.raises(RuntimeError,match='automatic replay prohibited'):
        request_attempt(*args,request=fail,server_probe=lambda *args: {})
    assert len(calls)==1


def test_success_stops_further_generation(tmp_path):
    c=case(); previous=dict(code='x=1',primary=primary(True))
    with pytest.raises(ValueError,match='unreachable'):
        request_attempt(plan(),c,'R0',2,[c['initial'],previous],tmp_path,object(),2,1,
                        request=lambda *args: pytest.fail('must stop after success'))


def test_stage_reconciliation_missing_duplicate_and_frozen_drift(tmp_path):
    cases=[case(i) for i in range(3)]
    records=[make_record(tmp_path/str(i),c,a,success=(i+CONDITIONS.index(a))%2==0)
             for i,c in enumerate(cases) for a in CONDITIONS]
    data=aggregates(cases,records,1)
    assert {(r['left'],r['right']) for r in data['paired_success']}==set(COMPARISONS)
    save_stage(plan(),cases,records,1,tmp_path)
    with pytest.raises(ValueError):aggregates(cases,records[:-1],1)
    with pytest.raises(ValueError):aggregates(cases,records+[records[0]],1)
    (tmp_path/'stage1/summary.csv').write_text('deliberately damaged\n')
    with pytest.raises(ValueError,match='output drift'):save_stage(plan(),cases,records,1,tmp_path)


def test_publication_stops_before_touching_existing_staged_changes(tmp_path, monkeypatch):
    (tmp_path/'safe.txt').write_text('authored public aggregate')
    monkeypatch.setattr(publication,'ROOT',tmp_path)
    monkeypatch.setattr(publication,'assert_frozen',lambda *args,**kwargs:None)
    monkeypatch.setattr(publication,'publication_paths',lambda *args:['safe.txt'])
    calls=[]
    def fake_git(*args):
        calls.append(args)
        if args==('diff','--cached','--name-only'):return 'unrelated.txt'
        pytest.fail('must stop before Git mutation')
    monkeypatch.setattr(publication,'git',fake_git)
    with pytest.raises(RuntimeError,match='Existing staged changes'):
        publication.publish({},tmp_path,tmp_path/'job.json')
    assert len(calls)==1
