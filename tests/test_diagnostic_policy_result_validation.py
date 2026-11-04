"""Synthetic public CSV rows: verify independent counts and reject mutations."""
from copy import deepcopy
import pytest
from scripts.validate_diagnostic_policy_results import verify_summary


def synthetic_cohort():
    rounds=[];paired=[];summary=[]
    for label,condition in [('B','baseline'),('P','preventive_spec'),('R','self_refine'),('F','execution_feedback'),('D','self_debugging')]:
        for seed in range(1000):
            success=seed<455;stop=3 if not success and label in ['R','F','D'] else 0
            key=f'{label}-{seed}'
            for i in range(stop+1):
                rounds.append({'record_key':key,'round':str(i),'model_spec':'authored','task_id':'fixture',
                               'base_seed':str(seed),'condition_id':condition,'code_sha256':f'authored-{seed}',
                               'new_L3':str(success),'tokens_in':'1','tokens_out':'1','generation_seconds':'0.1'})
            if label!='B':paired.append({'record_key':key,'final_success':str(success),'initial_success':str(success),'stop_round':str(stop)})
        requests=1000 if label=='P' else 1635 if label in ['R','F','D'] else 0
        summary.append({'condition':label,'generation_cap':'4' if label in ['R','F','D'] else '1','grouping':'overall','group':'all',
                        'groups':'1000','initial_failures':'545','final_L3_successes':'455','successes_from_initial_failure':'0',
                        'regressed':'0','total_generation_opportunities':'2635' if label in ['R','F','D'] else '1000',
                        'additional_requests':str(requests),'additional_tokens':str(requests*2),
                        'additional_generation_seconds':str(requests*.1)})
    return rounds,paired,summary


def test_independent_reconstruction_accepts_consistent_synthetic_cohort():
    assert len(verify_summary(*synthetic_cohort()))==5000


@pytest.mark.parametrize('mutation',['success','cost','duplicate'])
def test_independent_reconstruction_rejects_bad_public_data(mutation):
    rounds,paired,summary=synthetic_cohort()
    if mutation=='success':summary[3]['final_L3_successes']='456'
    elif mutation=='cost':
        target=next(r for r in rounds if r['condition_id']=='execution_feedback' and r['round']=='1')
        target['tokens_in']='2'
    else:rounds.append(deepcopy(rounds[-1]))
    with pytest.raises(ValueError):verify_summary(rounds,paired,summary)
