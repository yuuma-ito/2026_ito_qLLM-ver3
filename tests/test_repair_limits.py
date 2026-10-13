from copy import deepcopy
import hashlib
import json

import pytest

from tests.test_repair_costs import records, attempt
from scripts.analyze_repair_costs import analyze_costs
from scripts.analyze_repair_limits import analyze_limits, verify_limits, write_limit_analysis


def selected(result,condition,cap):
    return next(r for r in result['cap_summary'] if r['scope']=='pooled' and r['grouping']=='overall'
                and r['intervention']==condition and r['cap']==cap)


def test_cap_prefixes_early_success_and_initial_success_are_not_extended():
    costs=analyze_costs(records());before=deepcopy(costs)
    result=analyze_limits(costs['trial_costs'],costs['generation_ledger'])
    assert costs==before and verify_limits(result)
    f0=selected(result,'execution_feedback',0);f1=selected(result,'execution_feedback',1)
    assert (f0['rescued'],f0['final_success'],f0['cost_total_tokens'])==(0,1,0)
    assert (f1['rescued'],f1['final_success'],f1['cost_total_tokens'])==(1,2,20)
    assert f1['marginal_rescue_rate']==1 and f1['workflow_total_tokens']==220
    for cap in [2,3]:
        f=selected(result,'execution_feedback',cap)
        assert f['cost_total_tokens']==20 and f['marginal_attempted']==0
        assert f['marginal_rescue_rate']=='' and f['marginal_cost_per_new_rescue_total_tokens']==''
    d=selected(result,'self_debugging',3)
    assert d['charged_rounds']==3 and d['cost_total_tokens']==60 and d['rescued']==0
    assert d['cost_per_cumulative_rescue_total_tokens']==''


def test_second_round_rescue_charges_unsuccessful_attempts_in_marginal_cost():
    rows=records()
    # F reaches L3 at round 2 for one failed pair; another remains unsuccessful.
    f=next(r for r in rows if r['seed']==0 and r['intervention']=='execution_feedback')
    f['rounds']=[attempt(1,0,100,10),attempt(2,1,20,2,'changed'),attempt(4,2,30,3,'changed')]
    f['first_success_round']=2
    for k in ['tokens_in','tokens_out','total_tokens','elapsed_sec']:f[k]=sum(a[k] for a in f['rounds'])
    more=[deepcopy(r) for r in rows if r['seed']==0]
    for r in more:
        r.update(seed=2,base_seed=2)
        if r['intervention']=='execution_feedback':
            r['rounds']=[attempt(1,0,100,10),*[attempt(2,n,20,2,'changed') for n in [1,2,3]]]
            r.update(L0=True,L1=True,L2=False,L3=False,structure_match=False,first_success_round=-1)
            for k in ['tokens_in','tokens_out','total_tokens','elapsed_sec']:r[k]=sum(a[k] for a in r['rounds'])
    costs=analyze_costs(rows+more);result=analyze_limits(costs['trial_costs'],costs['generation_ledger'])
    cap2=selected(result,'execution_feedback',2)
    assert cap2['baseline_failure']==2 and cap2['rescued']==1 and cap2['rescue_rate']==0.5
    assert cap2['marginal_attempted']==2 and cap2['marginal_rescue_rate']==0.5
    assert cap2['marginal_cost_total_tokens']==50
    assert cap2['marginal_cost_per_new_rescue_total_tokens']==50
    assert selected(result,'execution_feedback',3)['cost_total_tokens']==110


@pytest.mark.parametrize('problem',['duplicate_round','missing_round','round_zero','duplicate_trial','missing_condition','bad_cost'])
def test_corrupt_histories_and_accounting_are_rejected(problem):
    costs=analyze_costs(records());trials=costs['trial_costs'];ledger=costs['generation_ledger']
    if problem=='duplicate_round':ledger.append(deepcopy(ledger[0]))
    elif problem=='missing_round':ledger[:]=[r for r in ledger if not (r['intervention']=='self_debugging' and r['round']==2)]
    elif problem=='round_zero':next(r for r in ledger if r['intervention']=='self_debugging')['round']=0
    elif problem=='duplicate_trial':trials.append(deepcopy(trials[0]))
    elif problem=='missing_condition':trials[:]=[r for r in trials if r['intervention']!='preventive_spec']
    else:next(r for r in trials if r['intervention']=='execution_feedback')['cost_total_tokens']+=1
    with pytest.raises(ValueError):analyze_limits(trials,ledger)


def test_tampered_marginal_counts_are_rejected():
    costs=analyze_costs(records());result=analyze_limits(costs['trial_costs'],costs['generation_ledger'])
    selected(result,'execution_feedback',2)['marginal_rescued']+=1
    with pytest.raises(ValueError):verify_limits(result)


def test_public_parent_guard_and_cap3_reconciliation(tmp_path,monkeypatch):
    from scripts.analyze_reach_levels import analyze_levels
    from scripts.analyze_stratified_effects import write_analysis
    from scripts.analyze_discordant_repairs import write_comparison
    from scripts.analyze_repair_costs import write_cost_analysis
    rows=records()
    for row in rows:row['raw_output']='PRIVATE GENERATED CODE'
    p=tmp_path/'results/source';p.mkdir(parents=True)
    config=dict(experiment_id='source')
    (p/'raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (p/'experiment_config.json').write_text(json.dumps(config))
    (p/'manifest.json').write_text('{"schema_version":"2.1"}')
    (p/'automation_report.json').write_text('{"passed":true}')
    run=dict(experiment_id='source',source_dir='results/source',config=config,records=len(rows),
        raw_sha256=hashlib.sha256((p/'raw.jsonl').read_bytes()).hexdigest(),**analyze_levels(rows))
    snapshot=dict(runs=[run],pooled=dict(experiment_id='pooled',verified=True,records=len(rows),
        **analyze_levels([dict(r,experiment_id='pooled') for r in rows])))
    path=tmp_path/'snapshot.json';path.write_text(json.dumps(snapshot))
    for module in ['analyze_stratified_effects','analyze_discordant_repairs','analyze_repair_costs','analyze_repair_limits']:
        monkeypatch.setattr('scripts.'+module+'.verify',lambda *args:dict(passed=True))
    strata=tmp_path/'strata';write_analysis(path,strata,root=tmp_path)
    comparison=tmp_path/'comparison';write_comparison(strata/'manifest.json',comparison,root=tmp_path)
    costs=tmp_path/'costs';write_cost_analysis(comparison/'manifest.json',costs,root=tmp_path)
    output=tmp_path/'limits';result=write_limit_analysis(costs/'manifest.json',output,root=tmp_path)
    assert selected(result,'execution_feedback',3)['cost_total_tokens']==20
    assert all('PRIVATE GENERATED CODE' not in p.read_text() for p in output.iterdir())
    (costs/'generation_ledger.csv').write_text('changed')
    with pytest.raises(ValueError,match='artifact changed'):
        write_limit_analysis(costs/'manifest.json',tmp_path/'rejected',root=tmp_path)
    assert not (tmp_path/'rejected').exists()
