import json
from types import SimpleNamespace
import pytest
from scripts.run_measurement_ban_followup import continue_case


def setup_case():
    p={'plan_sha256':'fixed','model_spec':'ollama:test','task_id':'T3a_DJ_constant','base_seed':3,
       'baseline_record_key':'key','derived_seeds':{'2':111,'3':222},'temperature':.7,
       'generation_settings':{'max_tokens':1024},'evaluator':{'primary_version':'measurement_ban'}}
    return p,[{'round':0,'primary':{'L3':False}},{'round':1,'primary':{'L3':False}}]


def helpers(outcomes):
    calls=[]
    def request(client,prompt,seed,temp):
        calls.append((prompt,seed,temp))
        return {'raw_output':'```python\n# fixture\n```','tokens_in':10,'tokens_out':5,'generation_seconds':1.,'finish_reason':'stop'}
    def executor(code,task):
        passed=outcomes[len(calls)-1]
        return {'runtime_status':'completed','primary':{'L0':True,'L1':True,'L2':passed,'structure_match':True,'L3':passed,'failure_stage':'evaluate','error_category':'ok' if passed else 'wrong_output'},'seconds':.1}
    return calls,request,executor


@pytest.mark.parametrize('outcomes,requests,final', [([True],1,True),([False,True],2,True),([False,False],2,False)])
def test_only_rounds_two_three_fresh_prompt_and_stop(tmp_path,outcomes,requests,final):
    p,prefix=setup_case();calls,req,ev=helpers(outcomes)
    result=continue_case(p,prefix,None,tmp_path,request=req,executor=ev)
    assert result['new_requests']==requests and result['final_success']==final
    assert [c[1] for c in calls]==[111,222][:requests]
    assert len({c[0] for c in calls})==1 and 'fixture' not in calls[0][0]
    assert prefix==result['rounds'][:2]
    def forbidden(*a):raise AssertionError('must not repeat completed model request')
    assert continue_case(p,prefix,None,tmp_path,request=forbidden,executor=forbidden)==result


def test_ambiguous_request_is_never_replayed(tmp_path):
    p,prefix=setup_case();calls=[]
    def fail(*a):calls.append(1);raise TimeoutError('timeout')
    with pytest.raises(TimeoutError):continue_case(p,prefix,None,tmp_path,request=fail)
    with pytest.raises(RuntimeError,match='ambiguous request'):continue_case(p,prefix,None,tmp_path,request=fail)
    assert len(calls)==1
