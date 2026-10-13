from copy import deepcopy
import math
import hashlib
import json

import pytest

from scripts.analyze_repair_costs import analyze_costs, round_cost, verify_costs, write_cost_analysis


def attempt(level,round_index,tokens,elapsed,code='initial'):
    return dict(round=round_index,L0=level>=1,L1=level>=2,L2=level>=3,L3=level==4,
        structure_match=level==4,code_sha256=code,failure_stage='unknown',exception_type='',
        error_category='ok' if level==4 else 'wrong_output',tokens_in=tokens//2,tokens_out=tokens-tokens//2,
        total_tokens=tokens,elapsed_sec=elapsed,connection_retries=0)


def records():
    rows=[]
    # initial failure: F rescues in 1 round, D fails in 3; initial success: no repair.
    for seed in [0,1]:
        initial=attempt(4 if seed else 1,0,100,10)
        for condition in ['baseline','self_refine','execution_feedback','self_debugging','preventive_spec']:
            rounds=[deepcopy(initial)]
            if condition=='preventive_spec':rounds=[attempt(4 if seed==0 else 1,0,50,5,'preventive')]
            elif seed==0 and condition!='baseline':
                count=1 if condition=='execution_feedback' else 3
                rounds += [attempt(4 if condition=='execution_feedback' else 2,n,20,2,'changed') for n in range(1,count+1)]
            last=rounds[-1]
            rows.append(dict(experiment_id='source',model_spec='model',task_id='task',seed=seed,base_seed=seed,
                intervention=condition,task_difficulty='hard',rounds=rounds,
                first_success_round=next((r['round'] for r in rounds if r['L3']),-1),
                **{k:v for k,v in last.items() if k not in ['round','connection_retries','tokens_in','tokens_out','total_tokens','elapsed_sec']},
                **{k:sum(r[k] for r in rounds) for k in ['tokens_in','tokens_out','total_tokens','elapsed_sec']}))
    return rows


def overall(result,condition):
    return next(r for r in result['cost_summary'] if r['scope']=='pooled' and r['grouping']=='overall' and r['intervention']==condition)


def test_shared_initial_excluded_and_deduplicated_without_mutating_records():
    rows=records();before=deepcopy(rows)
    result=analyze_costs(rows)
    assert rows==before and verify_costs(result)
    f=overall(result,'execution_feedback');d=overall(result,'self_debugging');p=overall(result,'preventive_spec')
    assert f['cost_total_tokens']==20 and f['cost_elapsed_sec']==2 and f['charged_rounds']==1
    assert f['rescued_count']==1 and f['all_cost_per_rescue_total_tokens']==20
    assert f['success_round_1']==1 and f['success_round_2']==f['success_round_3']==0
    assert d['cost_total_tokens']==60 and d['unrescued_cost_total_tokens']==60
    assert d['all_cost_per_rescue_total_tokens']=='' and d['unrescued_cost_share_total_tokens']==1
    assert d['partial_improvement_count']==1  # Still below L3; cost is not declared worthless.
    assert p['cost_kind']=='independent_generation' and p['cost_total_tokens']==100
    assert p['charged_rounds']==2 and p['rescued_count']==p['regressed_count']==1
    assert result['accounting']['unique_recorded_generation_rounds']==11
    assert result['accounting']['duplicated_initial_round_rows']==6
    assert result['accounting']['unique_generation_totals']['total_tokens']==440
    assert result['accounting']['stored_record_totals']['total_tokens']==1040
    workflow=next(r for r in result['workflow_summary'] if r['scope']=='pooled' and r['grouping']=='overall' and r['intervention']=='execution_feedback')
    assert workflow['total_tokens']==220 and workflow['final_L3_success']==2
    assert workflow['tokens_per_final_success']==110
    assert all(t['cost_total_tokens']==0 for t in result['trial_costs'] if t['baseline_L3'] and t['cost_kind']=='repair_additional')


def test_cohort_costs_are_paired_and_recovery_is_counted_once():
    rows=records()
    f=next(r for r in rows if r['seed']==0 and r['intervention']=='execution_feedback')
    f['rounds'][1]['connection_retries']=2
    result=analyze_costs(rows)
    cohort=next(r for r in result['fd_cost_summary'] if r['scope']=='pooled' and r['grouping']=='overall' and r['cohort']=='feedback_only')
    assert cohort['mean_D_minus_F_tokens']==40 and cohort['mean_D_minus_F_sec']==4
    assert result['accounting']['generation_rounds_with_recovery']==1
    assert result['accounting']['recorded_connection_retries']==2


@pytest.mark.parametrize('changes',[dict(total_tokens=-1),dict(elapsed_sec=float('nan')),
    dict(elapsed_sec=float('inf')),dict(tokens_in=True),dict(tokens_in=1.5),dict(total_tokens=99)])
def test_invalid_metrics_rejected(changes):
    a=attempt(1,0,100,10);a.update(changes)
    with pytest.raises(ValueError):round_cost(a)


@pytest.mark.parametrize('problem',['record_total','initial_cost','continued_after_success','history','partition'])
def test_invalid_accounting_and_early_stop_rejected(problem):
    rows=records();f=next(r for r in rows if r['seed']==0 and r['intervention']=='execution_feedback')
    if problem=='record_total':f['elapsed_sec']+=1
    elif problem=='initial_cost':
        f['rounds'][0]['elapsed_sec']+=1;f['elapsed_sec']+=1
    elif problem=='continued_after_success':
        f['rounds'].append(attempt(4,2,20,2,'changed'))
        for k in ['tokens_in','tokens_out','total_tokens','elapsed_sec']:f[k]+=f['rounds'][-1][k]
    elif problem=='history':f['rounds'][-1]['round']=2;f['first_success_round']=2
    else:
        result=analyze_costs(rows);overall(result,'execution_feedback')['cost_total_tokens']+=1
        with pytest.raises(ValueError):verify_costs(result)
        return
    with pytest.raises(ValueError):analyze_costs(rows)


def test_all_attempt_cost_per_rescue_includes_unsuccessful_repairs():
    rows=records()
    # Add a second initial-failure pair, with F failing all three rounds.
    more=[deepcopy(r) for r in rows if r['seed']==0]
    for r in more:
        r.update(seed=2,base_seed=2)
        if r['intervention']=='execution_feedback':
            r['rounds']=[attempt(1,0,100,10),*[attempt(2,n,20,2,'changed') for n in [1,2,3]]]
            r.update(L0=True,L1=True,L2=False,L3=False,structure_match=False,first_success_round=-1)
            for k in ['tokens_in','tokens_out','total_tokens','elapsed_sec']:r[k]=sum(a[k] for a in r['rounds'])
    result=analyze_costs(rows+more);f=overall(result,'execution_feedback')
    assert f['all_cost_per_rescue_total_tokens']==80
    assert f['rescued_only_mean_cost_total_tokens']==20
    assert math.isclose(f['unrescued_cost_share_total_tokens'],0.75)


def test_verified_source_guards_and_public_cost_files(tmp_path,monkeypatch):
    from scripts.analyze_reach_levels import analyze_levels
    from scripts.analyze_stratified_effects import write_analysis
    from scripts.analyze_discordant_repairs import write_comparison
    rows=records()
    for r in rows:r['raw_output']='PRIVATE GENERATED CODE'
    source=tmp_path/'results/source';source.mkdir(parents=True)
    config=dict(experiment_id='source')
    (source/'raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    (source/'experiment_config.json').write_text(json.dumps(config))
    (source/'manifest.json').write_text('{"schema_version":"2.1"}')
    (source/'automation_report.json').write_text('{"passed":true}')
    run=dict(experiment_id='source',source_dir='results/source',config=config,records=len(rows),
             raw_sha256=hashlib.sha256((source/'raw.jsonl').read_bytes()).hexdigest(),**analyze_levels(rows))
    snapshot=dict(runs=[run],pooled=dict(experiment_id='pooled',verified=True,records=len(rows),
                 **analyze_levels([dict(r,experiment_id='pooled') for r in rows])))
    path=tmp_path/'snapshot.json';path.write_text(json.dumps(snapshot))
    for module in ['analyze_stratified_effects','analyze_discordant_repairs','analyze_repair_costs']:
        monkeypatch.setattr('scripts.'+module+'.verify',lambda *args:dict(passed=True))
    strata=tmp_path/'strata';write_analysis(path,strata,root=tmp_path)
    comparisons=tmp_path/'comparison';write_comparison(strata/'manifest.json',comparisons,root=tmp_path)
    output=tmp_path/'costs';result=write_cost_analysis(comparisons/'manifest.json',output,root=tmp_path)
    assert result['accounting']['unique_generation_totals']['total_tokens']==440
    assert all('PRIVATE GENERATED CODE' not in p.read_text() for p in output.iterdir())
    assert json.loads((output/'sanity_report.json').read_text())['passed']
    (source/'raw.jsonl').write_text('{}\n')
    with pytest.raises(ValueError,match='Raw hash changed'):
        write_cost_analysis(comparisons/'manifest.json',tmp_path/'rejected',root=tmp_path)
    assert not (tmp_path/'rejected').exists()
