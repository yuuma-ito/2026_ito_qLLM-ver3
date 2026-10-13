from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from tests.test_repair_costs import records, attempt
from scripts.analyze_third_round import analyze_third_round, verify_third_round, write_third_round_analysis


def late_records():
    rows=records()
    for row in rows:
        if row['base_seed']==0 and row['intervention']=='execution_feedback':
            row['rounds']=[attempt(1,0,100,10),attempt(2,1,20,2),
                           attempt(2,2,30,3),attempt(4,3,40,4)]
            row.update(L0=True,L1=True,L2=True,L3=True,first_success_round=3)
            for key in ['tokens_in','tokens_out','total_tokens','elapsed_sec']:
                row[key]=sum(r[key] for r in row['rounds'])
    return rows


def overall(result,condition):
    return next(r for r in result['third_round_summary'] if r['scope']=='pooled'
                and r['grouping']=='overall' and r['intervention']==condition)


def test_denominator_includes_failures_and_excludes_initial_and_early_success():
    rows=late_records(); before=deepcopy(rows)
    result=analyze_third_round(rows)
    assert rows==before and verify_third_round(result)
    f=overall(result,'execution_feedback');d=overall(result,'self_debugging')
    assert (f['eligible_count'],f['rescued_count'],f['third_round_tokens'])==(1,1,40)
    assert (d['eligible_count'],d['rescued_count'],d['third_round_tokens'])==(1,0,20)
    assert d['tokens_per_new_rescue']==''
    assert len(result['late_round_trajectories'])==4
    assert len(analyze_third_round(records())['eligible_trials'])==1
    rules=[r for r in result['candidate_rule_checks'] if r['scope']=='pooled'
           and r['intervention']=='execution_feedback']
    assert next(r for r in rules if r['rule']=='stop_on_repeated_category')['lost_rescues']==1
    assert next(r for r in rules if r['rule']=='continue_only_with_net_stage_improvement')['lost_rescues']==0


def test_shared_late_pair_is_counted_once():
    rows=late_records()
    row=next(r for r in rows if r['base_seed']==0 and r['intervention']=='self_debugging')
    row['rounds'][-1].update(L2=True,L3=True,structure_match=True,error_category='ok')
    row.update(L2=True,L3=True,structure_match=True,first_success_round=3)
    result=analyze_third_round(rows)
    assert result['overlap']['both_late']==1
    assert result['overlap']['unique_late_pairs']==1
    assert len(result['late_rescues'])==2


@pytest.mark.parametrize('problem',['missing_round','metadata','duplicate'])
def test_inconsistent_saved_records_are_rejected(problem):
    rows=late_records()
    row=next(r for r in rows if r['base_seed']==0 and r['intervention']=='execution_feedback')
    if problem=='missing_round':row['rounds'].pop(2)
    elif problem=='metadata':row['first_success_round']=-1
    else:rows.append(deepcopy(row))
    with pytest.raises(ValueError):analyze_third_round(rows)


def test_tampered_rule_costs_and_summary_are_rejected():
    result=analyze_third_round(late_records())
    result['candidate_rule_checks'][0]['saved_tokens']+=1
    with pytest.raises(ValueError,match='Rule cost'):verify_third_round(result)
    result=analyze_third_round(late_records())
    overall(result,'execution_feedback')['rescued_count']+=1
    with pytest.raises(ValueError):verify_third_round(result)


def test_changed_parent_artifact_is_rejected_before_output(tmp_path):
    source=Path(__file__).resolve().parents[1]/'docs/analysis/repair_limits_20261013'
    parent=tmp_path/'parent';shutil.copytree(source,parent)
    (parent/'cap_summary.csv').write_text('tampered')
    output=tmp_path/'rejected'
    with pytest.raises(ValueError,match='artifact changed'):
        write_third_round_analysis(parent/'manifest.json',output)
    assert not output.exists()
