"""Independent report counters on synthetic data, no APIs or code execution."""
from copy import deepcopy
import pytest
from scripts.finish_factorial_pilot import summarize_independently,structure


def fixture():
    cases=[{'case_id':str(i),'initial':{'code':'x = 0'}} for i in [0,1]]
    records=[]
    for c in cases:
        for a in ['A','B','C','D']:
            success=(a=='A' and c['case_id']=='0') or (a=='C' and c['case_id']=='1')
            records.append({'case_id':c['case_id'],'condition':a,'round':1,'code':'x = 0' if a in ['B','D'] else 'x = 1',
                            'primary':{'L3':success},'tokens_in':20,'tokens_out':1024 if a=='D' else 5,
                            'finish_reason':'length' if a=='D' else 'stop'})
    return cases,records


def test_independent_summary_counts_pairing_failed_cost_and_ast_repeats():
    cases,records=fixture();summary,pairs,_=summarize_independently(cases,records,1)
    assert {a:r['successes'] for a,r in summary.items()}=={'A':1,'B':0,'C':1,'D':0}
    assert summary['D']['failed_request_tokens']==2088 and summary['D']['finish_length']==summary['D']['output_at_1024']==2
    assert summary['B']['same_failed_ast_requests']==2 and summary['A']['ast_changed_requests']==2
    assert pairs[0]=={'stage':1,'left':'A','right':'B','both':0,'left_only':1,'right_only':0,'neither':1}
    assert pairs[1]['right_only']==1
    damaged=deepcopy(records);damaged[0]['tokens_in']+=1
    assert summarize_independently(cases,damaged,1)[0]['A']['tokens_in']==summary['A']['tokens_in']+1


def test_independent_summary_rejects_a_missing_condition_path():
    cases,records=fixture()
    with pytest.raises(ValueError,match='missing path'):summarize_independently(cases,records[1:],1)


def test_ast_only_parses_and_ignores_comments_and_format():
    assert structure('x=0 # comment')==structure('x = 0')
    assert structure('x=0')!=structure('x=1')
    assert structure('invalid (') is None
    assert structure('raise AssertionError("must not execute")') is not None
