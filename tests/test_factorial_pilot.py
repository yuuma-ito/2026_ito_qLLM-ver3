"""Authored inputs, local checkpoints and fake API responses only."""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace
import pytest

from harness.factorial_pilot import (sample_cases,schedule,build_prompt,paired_seed,features,
                                     CONDITIONS,FOOTER,EXPLANATION,RecordedClient,validate_response,validate_history)
from harness.independent_4 import digest,code_hash
from scripts.run_factorial_pilot import request_attempt
from scripts.analyze_factorial_pilot import aggregates
from tasks import get_task


def primary(success=False):
    return {'L0':True,'L1':True,'L2':success,'L3':success,'structure_match':True,
            'error_category':'ok' if success else 'wrong_output','failure_stage':'evaluate',
            'exception_type':'','error_message':'authored evaluation','L2_distance':0.0 if success else .5,
            'actual_distribution':None}


def case(index=0):
    initial={'round':0,'code':'x = 0','hash':code_hash('x = 0'),'primary':primary(),
             'error':'wrong_output','success':False,'tokens_in':1,'tokens_out':1,'finish':None}
    return {'case_id':digest(index),'model_spec':'ollama:fixture','task_id':'T1_Bell','base_seed':index,
            'initial_error':'wrong_output','historical_outcome':'neither','initial':initial}


def response(code,model='fixture'):
    text='```python\n'+code+'\n```'
    return {'raw_output':text,'tokens_in':10,'tokens_out':5,'generation_seconds':.1,'finish_reason':'stop',
            'response':{'model':model,'usage':{'prompt_tokens':10,'completion_tokens':5},
                        'choices':[{'finish_reason':'stop','message':{'content':text}}]}}


def plan():
    return {'plan_sha256':'fixture_plan','model_digests':{'ollama:fixture':'digest'},
            'diagnostic_policy_version':'diagnostic_policy_v2_structure_qubits'}


def probe(*a):return {'version':'fixture'}


def population():
    result=[]
    for i in range(545):
        result.append({'case_id':digest(i),'model_spec':f'model{i%5}','task_id':f'task{i%10}',
                       'base_seed':i//10,'initial_error':f'error{i%4}','historical_outcome':str(i%4)})
    return result


def test_outcome_blind_sampling_reproduces_strata_models_tasks_and_identity():
    pop=population();a=sample_cases(pop);b=sample_cases(list(reversed(pop)))
    assert [c['case_id'] for c in a]==[c['case_id'] for c in b]
    assert len(a)==len({c['case_id'] for c in a})==100
    assert len({c['model_spec'] for c in a})==5 and len({c['task_id'] for c in a})==10
    swapped=[dict(c,historical_outcome='all_changed') for c in pop]
    assert [c['case_id'] for c in sample_cases(swapped)]==[c['case_id'] for c in a]
    assert {(c['model_spec'],c['initial_error']) for c in a}=={(c['model_spec'],c['initial_error']) for c in pop}
    with pytest.raises(ValueError,match='duplicate'):sample_cases(pop+[pop[0]])


def test_seeds_are_paired_new_and_stage1_positions_balanced():
    selected=sample_cases(population());slots=schedule(selected)
    assert len(slots)==1200 and len({(s['case_id'],s['condition'],s['round']) for s in slots})==1200
    assert len({s['seed'] for s in slots})==300 and min(s['seed'] for s in slots)>=1_000_000
    for c in selected:
        for r in [1,2,3]:assert len({s['seed'] for s in slots if s['case_id']==c['case_id'] and s['round']==r})==1
    assert set(Counter((s['condition'],s['nominal_position']) for s in slots if s['round']==1).values())=={25}
    assert [s['round'] for s in slots[:400]]==[1]*400


def test_prompt_information_contract_and_common_output():
    previous={'code':'# CODE_SENTINEL','primary':dict(primary(),L0=False,error_message='DIAGNOSTIC_SENTINEL')}
    prompts={a:build_prompt(a,get_task('T1_Bell'),previous) for a in CONDITIONS}
    assert all(p.endswith(FOOTER) for p in prompts.values())
    assert 'CODE_SENTINEL' not in prompts['A'] and 'DIAGNOSTIC_SENTINEL' not in prompts['A']
    assert 'CODE_SENTINEL' in prompts['B'] and 'DIAGNOSTIC_SENTINEL' not in prompts['B']
    assert all('DIAGNOSTIC_SENTINEL' in prompts[a] for a in ['C','D'])
    assert EXPLANATION not in prompts['C'] and EXPLANATION in prompts['D']
    other={'code':'another','primary':primary(True)}
    assert build_prompt('A',get_task('T1_Bell'),previous)==build_prompt('A',get_task('T1_Bell'),other)


def test_exact_wire_settings_are_passed_to_api_without_fallback():
    captured=[];client=RecordedClient.__new__(RecordedClient);client.model_id='fixture'
    client._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:captured.append(kwargs))))
    client._create('authored prompt',.7,1234567)
    assert captured==[{'model':'fixture','messages':[{'role':'system','content':__import__('harness.llm_clients',fromlist=['SYSTEM_PROMPT']).SYSTEM_PROMPT},{'role':'user','content':'authored prompt'}],
                       'temperature':.7,'max_tokens':1024,'reasoning_effort':'none','seed':1234567}]


def test_condition_own_history_and_stop_without_cross_condition_code(tmp_path):
    c=case();hist={a:[deepcopy(c['initial'])] for a in ['C','D']};records={a:[] for a in hist};prompts=[]
    for r in [1,2]:
        for a in ['C','D']:
            def request(client,prompt,seed,temp):prompts.append((a,r,prompt));return response(f'{a}_marker = {r}')
            def executor(*args):return {'runtime_status':'completed','primary':primary(r==2)}
            row=request_attempt(plan(),c,a,r,hist[a],tmp_path/a/str(r),None,len(prompts)+1,1,request=request,executor=executor,server_probe=probe)
            records[a].append(row);hist[a].append({'code':row['code'],'primary':row['primary']})
    for a,r,prompt in prompts:
        if r==2:assert f'{a}_marker' in prompt and ('D_marker' if a=='C' else 'C_marker') not in prompt
    for a in hist:
        validate_history(c,a,hist[a],records[a],complete=True)
        with pytest.raises(ValueError,match='unreachable'):request_attempt(plan(),c,a,3,hist[a],tmp_path/a/'3',None,99,1)


def test_ambiguous_request_is_saved_and_never_automatically_replayed(tmp_path):
    c=case();calls=[]
    def timeout(*a):calls.append(1);raise TimeoutError('authored timeout')
    for expected in [TimeoutError,RuntimeError]:
        with pytest.raises(expected):request_attempt(plan(),c,'A',1,[c['initial']],tmp_path,None,1,1,request=timeout,server_probe=probe)
    assert len(calls)==1 and (tmp_path/'failure.json').exists() and not (tmp_path/'record.json').exists()


@pytest.mark.parametrize('mutation',['usage','finish','model','cap'])
def test_missing_or_inconsistent_api_metrics_are_rejected(mutation):
    r=response('x=1')
    if mutation=='usage':r['tokens_in']=11
    elif mutation=='finish':r['finish_reason']=None
    elif mutation=='model':r['response']['model']='other'
    else:r['tokens_out']=1025;r['response']['usage']['completion_tokens']=1025
    with pytest.raises(ValueError):validate_response(r,'ollama:fixture')


def test_stage_analysis_reconciles_shared_pairs_repeats_and_failed_token_cost(tmp_path):
    cases=[case(i) for i in [0,1]];records=[];histories={(c['case_id'],a):[deepcopy(c['initial'])] for c in cases for a in CONDITIONS}
    targets={'A':1,'B':4,'C':2,'D':1}
    stage1=None
    for rnd in [1,2,3]:
        for c in cases:
            for a in CONDITIONS:
                hist=histories[c['case_id'],a]
                if hist[-1]['primary']['L3']:continue
                def request(*args):return response('x = 0' if a=='B' else f'x = {rnd}')
                def executor(*args):return {'runtime_status':'completed','primary':primary(rnd>=targets[a])}
                row=request_attempt(plan(),c,a,rnd,hist,tmp_path/c['case_id']/a/str(rnd),None,len(records)+1,1,request=request,executor=executor,server_probe=probe)
                records.append(row);hist.append({'code':row['code'],'primary':row['primary']})
        if rnd==1:stage1=aggregates(cases,records,1)
    final=aggregates(cases,records,3)
    assert len(stage1['paths'])==8 and len(stage1['structural_stagnation'])==8
    totals={r['condition']:r for r in final['summary'] if r['grouping']=='overall'}
    assert {a:r['successes'] for a,r in totals.items()}=={'A':2,'B':0,'C':2,'D':2}
    assert totals['B']['requests']==6 and totals['B']['same_failed_ast_requests']==6
    assert totals['B']['total_tokens']==totals['B']['failed_request_tokens']==90
    pair=next(r for r in final['paired_success'] if r['grouping']=='overall' and r['left']=='B')
    assert pair['right_only']==2 and pair['left_only']==pair['both']==0
    damaged=deepcopy(records);damaged[0]['seed']+=1
    with pytest.raises(ValueError,match='seed'):aggregates(cases,damaged,3)
    with pytest.raises(ValueError,match='duplicate'):aggregates(cases,records+[records[0]],3)
