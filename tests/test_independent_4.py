"""No real model requests: independent B4 protocol, accounting and recovery."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import independent_4 as b4
from harness.interventions import INTERVENTIONS, build_initial_prompt
from scripts import run_independent_4 as driver
from scripts.analyze_independent_4 import analyze
from tasks import get_task


@pytest.fixture
def config():
    return json.loads((b4.ROOT/'configs/independent_4_full.json').read_text())


def primary(passed=False):
    return dict(L0=True, L1=True, L2=passed, L3=passed, structure_match=True,
                failure_stage='completed' if passed else 'evaluate', error_category='ok' if passed else 'wrong_output')


def case(passed=False, seed=0):
    code = '# PREVIOUS_PRIVATE_CODE_AND_ERROR\n'
    initial = dict(round=0, generation_number=1, round_seed=seed, reused=True,
                   code_sha256=b4.code_hash(code), extracted_code=code, primary=primary(passed),
                   tokens_in=100, tokens_out=20, generation_seconds=4., evaluation_seconds=None,
                   evaluation_source='fixed.csv', source_dir='results/old', baseline_record_key='key'+str(seed))
    return dict(model_spec='ollama:test', task_id='T1_Bell', base_seed=seed, source_dir='results/old',
                baseline_record_key='key'+str(seed), task_difficulty='easy', initial=initial)


def run(tmp_path, config, c, outcomes):
    calls, evaluated = [], []
    def request(client, prompt, seed, temperature):
        calls.append(dict(prompt=prompt, seed=seed))
        return dict(raw_output='```python\n# NEW_CODE\n```', tokens_in=10, tokens_out=5,
                    generation_seconds=2., finish_reason='stop')
    def executor(code, task):
        evaluated.append(code)
        return dict(runtime_status='completed', primary=primary(outcomes[len(evaluated)-1]), seconds=.5, build_seconds=.2)
    return b4.run_case(c, config, None, tmp_path, request=request, executor=executor), calls, evaluated


def test_historical_five_conditions_not_extended():
    assert INTERVENTIONS == ('baseline','self_refine','execution_feedback','self_debugging','preventive_spec')


def test_initial_success_reuses_everything_without_request_or_evaluation(tmp_path, config):
    c=case(True)
    result,calls,ev=run(tmp_path,config,c,[])
    assert not calls and not ev
    assert result['rounds']==[c['initial']]
    assert result['first_success_round']==0 and result['final_success']


def test_stateless_prompt_seeds_and_stop_at_first_success(tmp_path, config):
    c=case()
    result,calls,_=run(tmp_path,config,c,[False,True,False])
    assert len(calls)==2 and len(result['rounds'])==3
    assert result['first_success_round']==2
    assert [r['generation_number'] for r in result['rounds']]==[1,2,3]
    expected=build_initial_prompt('baseline',get_task(c['task_id']))
    assert all(call['prompt']==expected for call in calls)
    assert all('PREVIOUS_PRIVATE_CODE_AND_ERROR' not in call['prompt'] for call in calls)
    assert len({call['seed'] for call in calls})==2
    assert result['rounds'][0]==c['initial']
    # Both new outputs are deliberately identical; repetition is measured, not dropped.
    assert result['rounds'][-1]['repeated_code']


def test_all_failures_stop_after_four_total_generations(tmp_path,config):
    result,calls,_=run(tmp_path,config,case(),[False]*3)
    assert len(calls)==3 and len(result['rounds'])==4
    assert not result['final_success'] and result['first_success_round'] is None


def test_completed_resume_never_repeats_model_or_evaluation(tmp_path,config):
    result,_,_=run(tmp_path,config,case(),[True])
    def forbidden(*a,**k):raise AssertionError('no repeat side effect')
    again=b4.run_case(case(),config,None,tmp_path,request=forbidden,executor=forbidden)
    assert again==result


def test_timeout_or_connection_ambiguity_never_retries(tmp_path,config):
    calls=[]
    def fail(*args):
        calls.append(1)
        raise TimeoutError('no response; do not replay')
    with pytest.raises(TimeoutError):
        b4.run_case(case(),config,None,tmp_path,request=fail)
    with pytest.raises(RuntimeError,match='ambiguous request'):
        b4.run_case(case(),config,None,tmp_path,request=fail)
    assert len(calls)==1 and not (tmp_path/'completed.json').exists()


def test_infrastructure_failure_not_counted_as_wrong_output(tmp_path,config):
    def request(*a):return dict(raw_output='code',tokens_in=1,tokens_out=1,generation_seconds=1.)
    with pytest.raises(RuntimeError,match='infrastructure'):
        b4.run_case(case(),config,None,tmp_path,request=request,executor=lambda *a:{'runtime_status':'wall_timeout'})
    assert not (tmp_path/'completed.json').exists()


@pytest.mark.parametrize('wrong', [dict(L0=False,L1=True), dict(L1=False,L2=True), dict(L2=False,L3=True),dict(L3=True,structure_match=False)])
def test_cumulative_levels_and_structure_are_required(wrong):
    p=primary(True);p.update(wrong)
    with pytest.raises(ValueError):b4.levels(p)


def test_seed_mapping_is_stable_unique_and_separate_from_old_seeds(config):
    seeds=[b4.seed_for(m,t,s,r,config['seed_namespace']) for m in config['models'] for t in config['tasks']
           for s in config['seeds'] for r in (1,2,3)]
    assert len(seeds)==len(set(seeds))==3000
    assert min(seeds)>=1_000_000 and max(seeds)<2**31
    assert b4.seed_for('m','t',0,1)==b4.seed_for('m','t',0,1)


def test_strict_request_has_no_unsupported_seed_fallback():
    calls=[]
    def create(*args):
        calls.append(args)
        raise ValueError('seed unsupported')
    with pytest.raises(ValueError):b4.strict_request(SimpleNamespace(_create=create),'task',123,.7)
    assert len(calls)==1


def test_usage_and_response_model_are_required():
    response=SimpleNamespace(usage=None,model='test')
    with pytest.raises(RuntimeError,match='usage'):
        b4.strict_request(SimpleNamespace(_create=lambda *a:response,model_id='test'),'x',1,.7)


def test_tampered_shared_initial_and_nonconsecutive_round_rejected(tmp_path,config):
    c=case();result,_,_=run(tmp_path,config,c,[True])
    bad=deepcopy(result);bad['rounds'][0]['tokens_in']+=1
    with pytest.raises(ValueError,match='initial history'):b4.validate_record(bad,c,config)
    bad=deepcopy(result);bad['rounds'][1]['round']=3
    with pytest.raises(ValueError,match='round'):b4.validate_record(bad,c,config)
    bad=deepcopy(result);bad['rounds'].append(deepcopy(bad['rounds'][-1]));bad['rounds'][-1]['round']=2
    with pytest.raises(ValueError):b4.validate_record(bad,c,config)
    bad=deepcopy(result);bad['experiment_id']='another-run'
    with pytest.raises(ValueError,match='run identity'):b4.validate_record(bad,c,config)


def test_public_analysis_costs_exclude_shared_initial_and_detect_missing_duplicates(tmp_path,config):
    c=case();result,_,_=run(tmp_path,config,c,[True])
    refs={b4.identity(c):{label:[deepcopy(c['initial'])] for label in ('P','R','F','D')}}
    for label in ('R','F','D'):
        refs[b4.identity(c)][label].append(deepcopy(result['rounds'][1]))
    analysis=analyze([result],[c],refs,config)
    row=next(r for r in analysis['summary'] if r['condition']=='B4' and r['generation_cap']==4 and r['grouping']=='overall')
    assert row['additional_tokens']==15 and row['tokens_per_added_success']==15
    assert row['additional_generation_seconds']==2
    assert analysis['sanity']['shared_initial_tokens_counted_once']==120
    assert sum(r['initial_failure_groups'] for r in analysis['overlap'])==1
    assert next(r for r in analysis['overlap'] if r['B4_success'] and r['F_success'] and r['D_success'])['initial_failure_groups']==1
    with pytest.raises(ValueError,match='missing'):analyze([],[c],refs,config)
    with pytest.raises(ValueError,match='duplicate'):analyze([result,result],[c],refs,config)
    extra=deepcopy(result);extra['base_seed']=99
    with pytest.raises(ValueError,match='unexpected'):analyze([extra],[c],refs,config)


def test_unapproved_execution_does_not_create_output_or_clients(tmp_path,config):
    with pytest.raises(ValueError,match='human-reviewed'):
        driver.execute(config,{'plan_sha256':'reviewed'},[],None,tmp_path/'results/new',root=tmp_path)
    assert not (tmp_path/'results').exists()


def test_held_shared_lock_prevents_execution(tmp_path,config):
    from harness.run_state import file_lock
    with file_lock(tmp_path/'.cache/automate_experiment.lock'):
        assert driver.shared_lock_busy(tmp_path)
        with pytest.raises(RuntimeError,match='Another process'):
            driver.execute(config,{'plan_sha256':'yes'},[],'yes',tmp_path/'results/new',root=tmp_path)


def test_missing_checkpoint_hash_is_rejected(tmp_path,config):
    run(tmp_path,config,case(True),[])
    (tmp_path/'completed.json.integrity.json').unlink()
    with pytest.raises(ValueError,match='integrity'):b4.run_case(case(True),config,None,tmp_path)


def test_saved_response_is_evaluated_once_without_regeneration(tmp_path,config):
    c=case();calls=[]
    def request(*a):
        calls.append(1)
        return dict(raw_output='code',tokens_in=2,tokens_out=3,generation_seconds=1.)
    def fail(*a):raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        b4.run_case(c,config,None,tmp_path,request=request,executor=fail)
    with pytest.raises(RuntimeError,match='ambiguous evaluation'):
        b4.run_case(c,config,None,tmp_path,request=request,executor=fail)
    assert len(calls)==1


def test_raw_fixture_corruption_is_detected(tmp_path,config):
    result,_,_=run(tmp_path,config,case(True),[])
    (tmp_path/'completed.json').write_text('{}')
    with pytest.raises(ValueError,match='integrity'):
        b4.run_case(case(True),config,None,tmp_path)


def test_approval_parser_has_no_execute_by_default(monkeypatch,tmp_path):
    prepared=[]
    monkeypatch.setattr(driver,'prepare',lambda *a,**k:prepared.append(True))
    monkeypatch.setattr(driver,'execute',lambda *a,**k:pytest.fail('no experiment allowed'))
    assert driver.main([])==0 and prepared==[True]
    with pytest.raises(SystemExit):driver.main(['--execute','--new-run'])


def test_live_owner_blocks_even_with_matching_approval(tmp_path,config,monkeypatch):
    monkeypatch.setattr(driver,'active_runs',lambda *a:['other-experiment'])
    with pytest.raises(RuntimeError,match='another experiment'):
        driver.execute(config,{'plan_sha256':'reviewed'},[],'reviewed',tmp_path/'results/new',root=tmp_path)


def test_fixed_cohort_read_only_compatibility(config,monkeypatch):
    # Real public/private source hashes and the 1,000 initial-code mapping;
    # model/evaluation functions must remain unused in this read-only audit.
    settings=json.loads((b4.ROOT/config['sources']['settings']).read_text())
    if any(not (b4.ROOT/source['source_dir']/'raw.jsonl').exists() for source in settings['sources']):
        pytest.skip('private raw inputs are not distributed; public fixture tests still run')
    monkeypatch.setattr(driver,'make_client',lambda *a:pytest.fail('no model requests'))
    monkeypatch.setattr(b4,'isolated_evaluate',lambda *a:pytest.fail('no generated-code execution'))
    cases,evidence,_=b4.load_cohort(config)
    assert len(cases)==1000 and sum(not c['initial']['primary']['L3'] for c in cases)==545
    assert evidence['evaluator']['primary_version']=='evaluation_policy_v4'
    assert evidence['evaluator']['sampling']['seed_simulator']==42


def test_caps_and_costs_include_unresolved_cases_but_no_shared_initial(tmp_path,config):
    c=case(False,0);d=case(True,1)
    failed,_,_=run(tmp_path/'failed',config,c,[False]*3)
    preserved,_,_=run(tmp_path/'passed',config,d,[])
    refs={}
    for cc,rr in [(c,failed),(d,preserved)]:
        refs[b4.identity(cc)]={label:deepcopy(rr['rounds']) for label in ('R','F','D')}
        refs[b4.identity(cc)]['P']=[deepcopy(cc['initial'])]
    a=analyze([failed,preserved],[c,d],refs,config)
    rr={r['generation_cap']:r for r in a['summary'] if r['condition']=='B4' and r['grouping']=='overall'}
    assert [rr[i]['final_L3_successes'] for i in (1,2,3,4)]==[1,1,1,1]
    assert [rr[i]['additional_tokens'] for i in (1,2,3,4)]==[0,15,30,45]
    assert rr[4]['tokens_per_added_success'] is None
    assert rr[4]['evaluation_time_measured_requests']==3
    assert a['sanity']['shared_initial_tokens_counted_once']==240
    assert len(a['overlap'])==8 and next(r for r in a['overlap'] if r['success_pattern']=='none')['initial_failure_groups']==1
    assert 'PREVIOUS_PRIVATE' not in json.dumps(a)


def test_actual_client_payload_is_fresh_and_seeded_on_every_request(monkeypatch):
    from harness.llm_clients import make_client,SYSTEM_PROMPT
    client=make_client('ollama:qwen3.5:4b')
    requests=[]
    response=SimpleNamespace(model=client.model_id,usage=SimpleNamespace(prompt_tokens=10,completion_tokens=20),
                             choices=[SimpleNamespace(message=SimpleNamespace(content='code'),finish_reason='stop')],
                             model_dump=lambda **kw:{'model':'qwen3.5:4b'})
    def create(**kwargs):requests.append(kwargs);return response
    client._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    prompt=build_initial_prompt('baseline',get_task('T1_Bell'))
    for seed in [1234567,3456789]:b4.strict_request(client,prompt,seed,.7)
    assert len(requests)==2
    assert [r['seed'] for r in requests]==[1234567,3456789]
    assert all(r['messages']==[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':prompt}] for r in requests)
    assert all(r['reasoning_effort']=='none' and r['max_tokens']==1024 for r in requests)


def test_over_limit_response_is_not_accepted_as_an_experiment_attempt():
    response=SimpleNamespace(model='test',usage=SimpleNamespace(prompt_tokens=1,completion_tokens=1025))
    with pytest.raises(RuntimeError,match='token limit'):
        b4.strict_request(SimpleNamespace(model_id='test',_create=lambda *a:response),'x',1,.7)


def test_b4_notification_counts_one_condition_and_uses_primary_L3(tmp_path,config):
    from scripts.notify_progress import snapshot,message,overview
    config=deepcopy(config)
    config.update(models=['ollama:test'],tasks=['T1_Bell'],seeds=[0,1],experiment_id='b4-test',output_dir='results/b4-test')
    out=tmp_path/config['output_dir'];out.mkdir(parents=True)
    (out/'experiment_config.json').write_text(json.dumps(config))
    records=[]
    for seed,passed in [(0,True),(1,False)]:
        records.append(dict(model_spec='ollama:test',task_id='T1_Bell',base_seed=seed,
                            condition_id='independent_4',experiment_id='b4-test',final_success=passed))
    (out/'raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    p=snapshot(config,tmp_path)
    assert p['planned']==p['recorded']==2 and p['unexpected']==0
    assert p['passed_L3']==1 and p['failed_L3']==1
    text=message(p,'Asia/Tokyo')
    assert 'L3成功: 1件' in text and 'L2成功' not in text
    assert 'b4-test' in overview('Asia/Tokyo',tmp_path)
