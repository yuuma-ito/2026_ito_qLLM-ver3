"""Authored/mock-only tests for the bounded diagnostic continuation."""
from copy import deepcopy
import pytest
from harness.diagnostic_prompts import build_intervention_prompt
from harness.independent_4 import code_hash,digest
from harness.llm_clients import SYSTEM_PROMPT
from scripts.reevaluation_impact_audit import event
from scripts.run_diagnostic_policy_followup import continue_case,validate_result
from tasks import get_task


def fixture(branch=1):
    primary={'L0':True,'L1':True,'L2':False,'L3':False,'structure_match':False,
             'error_category':'qubit_count_mismatch','failure_stage':'evaluate',
             'error_message':'expected 4 qubits, got 3','L2_distance':1.0}
    prefix=[{'round':i,'round_seed':6+i,'extracted_code':'# authored prefix',
             'code_sha256':code_hash('# authored prefix'),'primary':deepcopy(primary),
             'tokens_in':10,'tokens_out':5,'generation_seconds':.1,'origin':'saved_prefix','reused':True} for i in range(branch)]
    case={'record_key':'test','model_spec':'ollama:fixture','task_id':'T4_BV_011',
          'base_seed':6,'condition_id':'execution_feedback','branch_generation_round':branch,
          'prefix_fingerprints':[digest(a) for a in prefix],
          'first_v2_prompt_sha256':code_hash(build_intervention_prompt('execution_feedback',get_task('T4_BV_011'),'# authored prefix',event(primary))),
          'temperature':.7,'generation_settings':{'max_tokens':1024}}
    return case,prefix,{'plan_sha256':'fixed','system_sha256':code_hash(SYSTEM_PROMPT)}


@pytest.mark.parametrize('branch,outcomes',[(1,[True]),(1,[False,True]),(1,[False,False,False]),(2,[False,True]),(2,[False,False])])
def test_preserve_prefix_seed_stop_and_idempotent_completion(tmp_path,branch,outcomes):
    case,prefix,plan=fixture(branch);before=deepcopy(prefix);calls=[]
    def request(client,prompt,seed,temp):
        calls.append((prompt,seed,temp))
        return {'raw_output':'```python\n# authored correction\n```','tokens_in':20,'tokens_out':5,'generation_seconds':.1,'finish_reason':'stop'}
    def evaluate(code,task):
        success=outcomes[len(calls)-1]
        p=deepcopy(prefix[-1]['primary']);p.update(L2=success,L3=success,structure_match=True,error_category='ok' if success else 'wrong_output')
        return {'runtime_status':'completed','primary':p}
    result=continue_case(case,prefix,plan,None,tmp_path,request=request,executor=evaluate)
    assert prefix==before and result['rounds'][:branch]==prefix
    assert [c[1] for c in calls]==list(range(6+branch,6+branch+len(outcomes)))
    assert result['new_requests']==len(outcomes) and result['final_success']==outcomes[-1]
    def forbidden(*a):pytest.fail('completed requests must not repeat')
    assert continue_case(case,prefix,plan,None,tmp_path,request=forbidden,executor=forbidden)==result
    damaged=deepcopy(result);damaged['rounds'][-1]['round_seed']+=1
    with pytest.raises(ValueError,match='seed drift'):validate_result(damaged,case,prefix,plan)
    damaged=deepcopy(result);damaged['rounds'][branch]['input_prompt_sha256']='wrong'
    with pytest.raises(ValueError,match='prompt/policy drift'):validate_result(damaged,case,prefix,plan)


def test_ambiguous_request_stops_without_automatic_resend(tmp_path):
    case,prefix,plan=fixture();calls=[]
    def timeout(*a):calls.append(1);raise TimeoutError('authored timeout')
    with pytest.raises(TimeoutError):continue_case(case,prefix,plan,None,tmp_path,request=timeout)
    with pytest.raises(RuntimeError,match='ambiguous request'):continue_case(case,prefix,plan,None,tmp_path,request=timeout)
    assert len(calls)==1


def test_runtime_failure_is_not_counted_as_model_failure_or_repeated(tmp_path):
    case,prefix,plan=fixture()
    def request(*a):return {'raw_output':'# authored','tokens_in':10,'tokens_out':3,'generation_seconds':.1}
    def failure(*a):return {'runtime_status':'worker_crash'}
    with pytest.raises(RuntimeError,match='infrastructure'):continue_case(case,prefix,plan,None,tmp_path,request=request,executor=failure)
    def forbidden(*a):pytest.fail('saved response/evaluation must not repeat')
    with pytest.raises(RuntimeError,match='infrastructure'):continue_case(case,prefix,plan,None,tmp_path,request=forbidden,executor=forbidden)
    assert not (tmp_path/'completed.json').exists()
