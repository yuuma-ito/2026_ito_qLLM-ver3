from copy import deepcopy
import hashlib
import json

import pytest

from scripts.analyze_reach_levels import analyze_levels
from scripts.analyze_stratified_effects import write_analysis
from scripts.analyze_discordant_repairs import compare_pairs, verify_comparison, write_comparison


def attempt(level,code='initial'):
    return dict(L0=level>=1,L1=level>=2,L2=level>=3,L3=level==4,structure_match=level==4,
                failure_stage='unknown' if level==4 else 'build',exception_type='',
                error_category='ok' if level==4 else 'build_error',code_sha256=code)


def records():
    rows=[]
    for seed,left,right in [(0,True,False),(1,False,True),(10,True,True),(11,False,False)]:
        for condition in ['baseline','self_refine','execution_feedback','self_debugging','preventive_spec']:
            success=left if condition=='execution_feedback' else right if condition=='self_debugging' else False
            first=attempt(1)
            final=attempt(4 if success else 3 if condition in ['execution_feedback','self_debugging'] else 1,'final')
            rounds=[dict(first,round=0)]
            if condition not in ['baseline','preventive_spec']:
                rounds.append(dict(final,round=1))
            else: final=first
            rows.append(dict(experiment_id='a' if seed<10 else 'b',model_spec='model',task_id='task',
                base_seed=seed,seed=seed,task_difficulty='hard',intervention=condition,
                first_success_round=1 if success else -1,rounds=rounds,
                source_record_sha256='hash',raw_output='PRIVATE CODE',**final))
    return rows


def test_exact_discordant_partition_and_l3_definition():
    original=records();before=deepcopy(original)
    result=compare_pairs(original)
    assert original==before
    overall=next(r for r in result['comparisons'] if r['scope']=='pooled' and r['grouping']=='overall')
    assert [overall[k] for k in ['baseline_L3_failure','both_rescued','feedback_only','debugging_only','neither_rescued']]==[4,1,1,1,1]
    assert overall['feedback_rescue_rate']==overall['debugging_rescue_rate']==0.5
    assert len(result['discordant_cases'])==2
    assert {r['winner'] for r in result['discordant_cases']}=={'F','D'}
    assert all(r['loser_final_level']=='L2' for r in result['discordant_cases'])
    assert len(result['round_trajectories'])==8
    assert verify_comparison(result)
    assert 'PRIVATE CODE' not in json.dumps(result)


@pytest.mark.parametrize('problem',['duplicate','missing','initial','difficulty'])
def test_bad_pairs_are_rejected(problem):
    rows=records()
    if problem=='duplicate':rows.append(dict(rows[0],experiment_id='other'))
    elif problem=='missing':rows.pop()
    elif problem=='initial':rows[2]['rounds'][0]['code_sha256']='different'
    else:rows[2]['task_difficulty']='easy'
    with pytest.raises(ValueError):compare_pairs(rows)


@pytest.mark.parametrize('problem',['summary','case','trace'])
def test_summary_case_and_trace_tampering_are_rejected(problem):
    result=compare_pairs(records())
    if problem=='summary':result['comparisons'][0]['feedback_only']+=1
    elif problem=='case':result['discordant_cases'].pop()
    else:result['round_trajectories'].pop()
    with pytest.raises(ValueError):verify_comparison(result)


def test_equal_rescue_conditions_produce_no_discordant_cases():
    rows=records()
    for row in rows:
        if row['intervention'] in ['execution_feedback','self_debugging']:
            row.update(attempt(4,'final'),first_success_round=1)
            row['rounds'][-1].update(attempt(4,'final'))
    result=compare_pairs(rows)
    assert not result['discordant_cases'] and not result['round_trajectories']
    assert verify_comparison(result)


def test_source_guards_and_public_serialization(tmp_path,monkeypatch):
    rows=records();runs=[]
    for source in ['a','b']:
        selected=[r for r in rows if r['experiment_id']==source]
        p=tmp_path/'results'/source;p.mkdir(parents=True)
        config=dict(experiment_id=source)
        (p/'raw.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in selected))
        (p/'experiment_config.json').write_text(json.dumps(config))
        (p/'automation_report.json').write_text('{"passed":true}')
        (p/'manifest.json').write_text('{"schema_version":"2.1"}')
        runs.append(dict(experiment_id=source,source_dir='results/'+source,config=config,records=len(selected),
            raw_sha256=hashlib.sha256((p/'raw.jsonl').read_bytes()).hexdigest(),**analyze_levels(selected)))
    snapshot=dict(runs=runs,pooled=dict(experiment_id='pooled',verified=True,records=len(rows),
        **analyze_levels([dict(r,experiment_id='pooled') for r in rows])))
    path=tmp_path/'snapshot.json';path.write_text(json.dumps(snapshot))
    monkeypatch.setattr('scripts.analyze_stratified_effects.verify',lambda *args:dict(passed=True))
    monkeypatch.setattr('scripts.analyze_discordant_repairs.verify',lambda *args:dict(passed=True))
    previous=tmp_path/'previous';write_analysis(path,previous,root=tmp_path)
    output=tmp_path/'comparison'
    result=write_comparison(previous/'manifest.json',output,root=tmp_path)
    assert len(result['discordant_cases'])==2
    assert all('PRIVATE CODE' not in p.read_text() for p in output.iterdir())
    assert all(len(r['baseline_record_sha256'])==64 for r in result['discordant_cases'])
    (previous/'feedback_debug_overlap.csv').write_text('changed')
    with pytest.raises(ValueError,match='artifact changed'):
        write_comparison(previous/'manifest.json',tmp_path/'rejected',root=tmp_path)
    assert not (tmp_path/'rejected').exists()
