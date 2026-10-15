from copy import deepcopy

import pytest

from scripts.analyze_reachable_rescue_history import cost_summary, cost_value, static_delta
from tests.test_analyze_verified_rescues import cohort
from scripts.analyze_verified_rescues import analyze


def test_static_diff_does_not_execute_or_publish_code(tmp_path):
    marker = tmp_path / 'must_not_exist'
    text = f"open({str(marker)!r}, 'w').write('secret-text')\nfrom qiskit import QuantumCircuit\n"
    d = static_delta('def broken(:\n', text)
    assert not marker.exists()
    assert d['changed_import_API'] and d['changed_circuit_interface']
    assert d['before_parses'] is False and d['after_parses'] is True
    assert 'secret-text' not in str(d) and str(marker) not in str(d)


def test_zero_diff_is_retained_without_semantic_claim():
    d = static_delta('qc.h(0)', 'qc.h(0)')
    assert d['changed_lines'] == 0 and d['code_changed'] is False
    assert not d['changed_quantum_logic']
    assert 'causal_role_not_identified' in d['interpretation']


def test_cost_includes_failed_repairs_excludes_shared_initial_and_separates_origin():
    rows, paths = cohort()
    ledger, *_ = analyze(rows, paths, {'task':'easy'})
    rounds=[]
    for row in ledger:
        for i in range(row['stop_round']+1):
            rounds.append(dict(record_key=row['record_key'],round=i,
                origin='new_suffix' if i==3 else 'saved_prefix',tokens_in=2,tokens_out=3,
                tokens=5,generation_seconds=7))
    result=cost_summary(ledger,rounds)
    def pick(condition,cap):
        return next(r for r in result if r['scope']=='pooled' and r['grouping']=='overall'
                    and r['condition_id']==condition and r['cap']==cap)
    f=pick('execution_feedback',3)
    assert f['initial_failures']==1 and f['initial_successes']==1
    assert f['generation_requests']==1 and f['tokens_per_rescue']==5
    r=pick('self_refine',3)
    assert r['rescued']==0 and r['tokens_per_rescue']==''
    assert r['tokens']==r['unrescued_tokens']==15
    assert r['saved_prefix_tokens']==10 and r['new_suffix_tokens']==5
    p=pick('preventive_spec',0)
    assert p['generation_requests']==2 and p['tokens']==10
    assert p['comparison_kind']=='independent_generation'


def test_cap2_drops_only_late_rescue_and_cost_not_failed_spending():
    rows, paths=cohort()
    ledger,*_=analyze(rows,paths,{'task':'easy'})
    f=next(r for r in ledger if r['record_key']=='0:execution_feedback')
    f['stop_round']=3
    rounds=[dict(record_key=r['record_key'],round=i,origin='saved_prefix',
        tokens=10,tokens_in=4,tokens_out=6,generation_seconds=2)
        for r in ledger for i in range(r['stop_round']+1)]
    summary=cost_summary(ledger,rounds)
    fs=[r for r in summary if r['scope']=='pooled' and r['grouping']=='overall'
        and r['condition_id']=='execution_feedback']
    cap2=next(r for r in fs if r['cap']==2)
    cap3=next(r for r in fs if r['cap']==3)
    assert cap2['lost_vs_cap3']==1 and cap2['lost_fraction_of_cap3']==1
    assert cap2['unrescued_tokens']==20 and cap3['unrescued_tokens']==0
    assert cap3['tokens']-cap2['tokens']==10


@pytest.mark.parametrize('value', [-1,float('nan'),float('inf'),1.5])
def test_rejects_invalid_cost(value):
    with pytest.raises(ValueError):
        cost_value(dict(tokens_in=value,tokens_out=1,elapsed_sec=1))
