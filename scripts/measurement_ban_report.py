"""Measurement-only impact accounting; never generates missing continuations."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import csv
import hashlib
import json
from pathlib import Path

from harness.run_state import atomic_json
from scripts import analyze_verified_rescues as base
from scripts.measurement_ban_sources import ROOT, code_key, sha

LABELS={'baseline':'B','preventive_spec':'P','self_refine':'R',
        'execution_feedback':'F','self_debugging':'D','independent_4':'B4'}


def write_csv(path,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    if not fields:fields=['none']
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fields,lineterminator='\n');writer.writeheader();writer.writerows(rows)


def group_key(row):
    return row['model_spec'],row['task_id'],str(row['base_seed'])


def outcome(results,task,code_hash):
    result=results[code_key(task,code_hash)]
    if result.get('runtime_status')!='completed' or not result.get('old_primary',{}).get('L3'):
        raise ValueError('unresolved v4 reproduction; final impact is not confirmed')
    return not result['measurement_violation']


def classify_path(condition,path,saved_suffix=()):
    """Inputs are (round, saved_v4_L3, revised_L3, code_hash) tuples.

    A v4-failing attempt keeps its original diagnostic; the only feedback
    divergence is a formerly successful measured attempt. R has no external
    diagnostic and may reuse a verified same-prompt/seed saved suffix.
    """
    stop,old_success,new_success,code_hash=path[-1]
    result={'old_stop_round':stop,'old_final_success':old_success,
            'terminal_rescored_success':new_success,'invalidated_terminal':old_success and not new_success,
            'confirmed_success':new_success,'requires_new_generation':False,
            'diagnostic_changes':False,'branch_after_round':'','next_generation_round':'',
            'remaining_request_upper_bound':0,'reused_saved_R_rounds':0,
            'status':'success_unchanged' if new_success else 'failure_unchanged',
            'branch_code_sha256':code_hash if old_success and not new_success else ''}
    if not old_success or new_success:return result
    result['branch_after_round']=stop
    result['diagnostic_changes']=condition in {'execution_feedback','self_debugging'}
    if condition in {'baseline','preventive_spec'}:
        result['status']='failure_single_generation';return result
    if stop==3:
        result['status']='failure_at_budget';return result
    last=stop
    if condition=='self_refine':
        for index,old,new,hashed in saved_suffix:
            if index!=last+1:raise ValueError('nonconsecutive saved R suffix')
            last=index;result['reused_saved_R_rounds']+=1
            if new:
                result['status']='success_on_verified_saved_R_suffix'
                result['confirmed_success']=True
                return result
            if last==3:
                result['status']='failure_at_budget_after_saved_R_suffix';return result
    result.update(requires_new_generation=True,status='pending_new_generation',
                  next_generation_round=last+1,remaining_request_upper_bound=3-last)
    return result


def publish(output,data,results,manifest):
    checks=[];unresolved=[]
    for key,c in sorted(data['cases'].items()):
        r=results[key]
        ok=r.get('runtime_status')=='completed' and r.get('old_primary',{}).get('L3') is True
        if not ok:unresolved.append(key)
        if ok:
            old,new=r['old_primary'],r['primary']
            for field in ['L0','L1','L2','L2_distance']:
                if old[field]!=new[field]:raise ValueError('nonmeasurement verdict change')
            if new['L3']!=(not r['measurement_violation']):raise ValueError('measurement delta mismatch')
        checks.append({'code_task_key':key,'task_id':c['task_id'],'code_sha256':c['code_sha256'],
                       'saved_v4_L3':True,'rerun_v4_L3':r.get('old_primary',{}).get('L3',''),
                       'revised_L3':r.get('primary',{}).get('L3',''),
                       'measurement_count':r.get('measurement_count',''),
                       'measurement_violation':r.get('measurement_violation',''),
                       'runtime_status':r.get('runtime_status','missing'),'v4_reproduced':ok})
    write_csv(output/'code_rechecks.csv',checks)
    if unresolved:
        summary={'status':'blocked_unresolved_evaluation','planned_unique_code_tasks':len(checks),
                 'unresolved_unique_code_tasks':len(unresolved),'new_model_requests':0}
        atomic_json(output/'sanity_report.json',{'passed':False,**summary})
        atomic_json(output/'summary.json',summary)
        atomic_json(output/'run_status.json',summary)
        (output/'report.txt').write_text('測定禁止条件の影響調査は未確定です。実行または旧v4判定の再現に未解決の問題があり、成功数を確定しません。\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        return summary
    references=[];scopes=defaultdict(Counter)
    for ref in data['references']:
        r=results[ref['code_task_key']]
        entry={**ref,'saved_v4_L3':True,'revised_L3':not r['measurement_violation'],
               'measurement_violation':r['measurement_violation'],'measurement_count':r['measurement_count']}
        references.append(entry)
        scopes[ref['scope']]['success_occurrences']+=1
        scopes[ref['scope']]['violating_occurrences']+=r['measurement_violation']
    write_csv(output/'success_references.csv',references)
    write_csv(output/'violations.csv',[r for r in references if r['measurement_violation']])
    full_by_record=defaultdict(list)
    for r in data['full']:full_by_record[r['record_key']].append(r)
    reach={(r['record_key'],int(r['round'])):r for r in data['reachable']}
    paths=[]
    archived_R={}
    def revised(task,old,hashed):return outcome(results,task,hashed) if old else False
    for row in data['mixed']:
        key=row['record_key'];task=row['task_id'];condition=row['condition_id']
        history=[]
        for i,e in enumerate(data['paths'][key]):
            old=base.truth(e['new_L3']);hashed=reach[(key,i)]['code_sha256']
            history.append((i,old,revised(task,old,hashed),hashed))
        future=[]
        if condition=='self_refine' and history[-1][1] and not history[-1][2]:
            from harness.evaluator import EvalResult
            from harness.interventions import build_intervention_prompt
            from scripts.reevaluation_impact_audit import archived_functions
            from tasks import get_task
            if key in data['branches']:raise ValueError('R suffix provenance changed')
            original=data['raw'][base.identity(row)]
            if original[history[-1][0]]['code_sha256']!=history[-1][3]:raise ValueError('R branch code mismatch')
            source_manifest=json.loads((ROOT/row['source_dir']/'manifest.json').read_text())
            commit=source_manifest['git_commit']
            if commit not in archived_R:archived_R[commit]=archived_functions(commit)[0]
            for e in sorted(full_by_record[key],key=lambda r:int(r['round'])):
                i=int(e['round'])
                if i<=history[-1][0]:continue
                raw=original[i]
                if raw['round_seed']!=int(row['base_seed'])+i or raw['feedback_type']!='self_critique':
                    raise ValueError('R continuation seed/prompt type mismatch')
                if raw['code_sha256']!=e['code_sha256']:raise ValueError('R suffix code mismatch')
                previous=original[i-1]['extracted_code']
                old_prompt=archived_R[commit]('self_refine',get_task(task),previous,EvalResult())
                new_prompt=build_intervention_prompt('self_refine',get_task(task),previous,EvalResult())
                if old_prompt!=new_prompt:raise ValueError('R saved continuation prompt changed')
                old=base.truth(e['new_L3'])
                future.append((i,old,revised(task,old,e['code_sha256']),e['code_sha256']))
        entry=classify_path(condition,history,future)
        paths.append({'record_key':key,'source_dir':row['source_dir'],'model_spec':row['model_spec'],
                      'task_id':task,'base_seed':int(row['base_seed']),'condition_id':condition,**entry})
    for row in data['B4_records']:
        history=[]
        for a in row['rounds']:
            old=a['primary']['L3'];hashed=a['code_sha256']
            history.append((a['round'],old,revised(row['task_id'],old,hashed),hashed))
        paths.append({'record_key':'B4:'+row['baseline_record_key'],'source_dir':'results/independent_4_full_20261020T185811381595Z',
                      'model_spec':row['model_spec'],'task_id':row['task_id'],'base_seed':int(row['base_seed']),
                      'condition_id':'independent_4',**classify_path('independent_4',history)})
    if len(paths)!=6000 or len({(group_key(r),r['condition_id']) for r in paths})!=6000:
        raise ValueError('current six-condition coverage mismatch')
    write_csv(output/'path_impacts.csv',paths)
    pending=[r for r in paths if r['requires_new_generation']]
    affected=[r for r in paths if r['invalidated_terminal']]
    write_csv(output/'pending_generation.csv',pending)
    grouped=defaultdict(list)
    for row in affected:grouped[group_key(row)].append(row)
    groups=[{'model_spec':k[0],'task_id':k[1],'base_seed':int(k[2]),
             'affected_conditions':'|'.join(sorted(LABELS[r['condition_id']] for r in rr)),
             'pending_conditions':'|'.join(sorted(LABELS[r['condition_id']] for r in rr if r['requires_new_generation']))}
            for k,rr in sorted(grouped.items())]
    write_csv(output/'affected_initial_groups.csv',groups)
    summaries=[]
    for condition,label in LABELS.items():
        rr=[r for r in paths if r['condition_id']==condition]
        if len(rr)!=1000:raise ValueError('condition denominator mismatch')
        summaries.append({'condition':label,'initial_groups':len(rr),
            'old_v4_final_successes':sum(r['old_final_success'] for r in rr),
            'terminal_rescored_successes':sum(r['terminal_rescored_success'] for r in rr),
            'invalidated_terminal_successes':sum(r['invalidated_terminal'] for r in rr),
            'confirmed_reachable_successes':sum(r['confirmed_success'] for r in rr),
            'pending_generation_paths':sum(r['requires_new_generation'] for r in rr),
            'reused_saved_R_rounds':sum(r['reused_saved_R_rounds'] for r in rr),
            'minimum_additional_requests':sum(r['requires_new_generation'] for r in rr),
            'maximum_additional_requests':sum(r['remaining_request_upper_bound'] for r in rr)})
    write_csv(output/'condition_summary.csv',summaries)
    baseline=next(r for r in summaries if r['condition']=='B')
    summary={'status':'verified_impact_only','checked_at_utc':datetime.now(timezone.utc).isoformat(),
             'unique_success_code_task_pairs_checked':len(checks),
             'unique_violating_code_task_pairs':sum(r['measurement_violation'] for r in checks),
             'scopes':{k:dict(v) for k,v in scopes.items()},'condition_summary':summaries,
             'current_affected_condition_paths':len(affected),'current_affected_initial_groups':len(groups),
             'new_generation_required_paths':len(pending),
             'new_generation_required_initial_groups':len({group_key(r) for r in pending}),
             'minimum_additional_requests':len(pending),
             'maximum_additional_requests':sum(r['remaining_request_upper_bound'] for r in pending),
             'old_initial_successes':455,'corrected_initial_successes':baseline['terminal_rescored_successes'],
             'old_initial_failures':545,'corrected_initial_failures':1000-baseline['terminal_rescored_successes'],
             'new_model_requests':0,'automatic_followups':False,'reference_conformance_used':False,
             'important_limit':'terminal_rescored_successesは旧停止コードの再採点。pendingの生成を行わないため修正版プロトコルの最終成功数ではない。confirmedには同じ入力・seedが確認できたR保存suffixのみを再利用。各scopeは重複するため合算しない。'}
    atomic_json(output/'summary.json',summary)
    sanity={'passed':True,'planned_unique_code_tasks':len(checks),'completed_unique_code_tasks':len(checks),
            'missing':0,'duplicates':0,'unresolved_runtime_failures':0,'old_v4_reproduction_failures':0,
            'historical_sources_unchanged':True,'current_condition_paths':len(paths),
            'new_model_requests':0,'generated_continuations':0,'reference_conformance_used':False}
    atomic_json(output/'sanity_report.json',sanity)
    lines=['測定禁止条件だけを修正した評価器による影響調査',
           '旧評価・固定集計・生成履歴は保持。新規モデル生成と部分追試は実施していない。',
           f"成功コード×タスク {len(checks):,}組を隔離再評価し、違反は{summary['unique_violating_code_task_pairs']}組。",
           f"現行経路で影響する初期組は{len(groups)}組、条件経路は{len(affected)}件。",
           '条件：旧v4成功 → 旧停止コードの再採点成功 ／ 確認済み到達成功 ／ 後続生成が必要な経路']
    for r in summaries:lines.append(f"{r['condition']}: {r['old_v4_final_successes']} → {r['terminal_rescored_successes']} ／ {r['confirmed_reachable_successes']} ／ {r['pending_generation_paths']}")
    lines.extend([f"後続生成が必要な経路は{len(pending)}件（初期組{summary['new_generation_required_initial_groups']}組）。",
                  f"必要な追加要求数は成功時停止に依存し、最少{summary['minimum_additional_requests']}、最大{summary['maximum_additional_requests']}。今回は要求していない。",
                  f"初期成功455→{summary['corrected_initial_successes']}、初期失敗545→{summary['corrected_initial_failures']}。",
                  '原因：共通systemには測定禁止があるが、Task.measurement_requiredがNoneで、旧v4は明示メタデータの条件だけを検査していた。',
                  '修正：評価器が追加するreadoutの前に、合成命令・制御フローを含む回路内Measureを検出し、構造不適合とする。',
                  '既に失敗していた試行の診断優先順位は保持する。新たに不合格となる試行は専用の測定禁止診断を用いる。',
                  'F/Dは診断が変わるため旧suffixを再利用しない。Rは診断を入力しない固定自己点検で、前コード・seed・feedback種別が一致する保存suffixのみ再利用する。B4は失敗した候補の次から独立生成が必要となる。',
                  'Rの入力一致は当時の保存commitから再構成したテンプレートによる照合であり、当時の実送信要求の直接記録による証明ではない。',
                  '初回のみのB/Pと、上限到達済みの条件は自動的に予算を増やさない。',
                  '位相・全ユニタリ一致・原課題より強い参照条件は一切追加していない。',
                  '全件はcode_rechecks.csv、参照先と違反はsuccess_references.csv・violations.csv、条件別はcondition_summary.csv、分岐はpath_impacts.csv・pending_generation.csvを参照。',
                  '旧保存round、追試suffix、B4共有初期、現行到達履歴は重複する。scope別件数を合算して違反件数としない。',
                  '旧v4と修正版を同じ隔離QPY回路で評価した。コード×タスクの重複は一度だけ実行し、同一コードの別条件・初期組への対応を全参照台帳に保持した。'])
    (output/'report.txt').write_text('\n'.join(lines)+'\n')
    scripts=['scripts/measurement_ban_sources.py','scripts/audit_measurement_ban.py','scripts/measurement_ban_report.py']
    public_manifest={**manifest,'source_files':data['inputs'],'analysis_script_sha256':{p:sha(ROOT/p) for p in scripts},
                     'output_sha256':{p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name not in {'manifest.json','run_status.json'}},
                     'source_preservation':'original raw, histories, fixed CSVs and manifests were not overwritten'}
    atomic_json(output/'manifest.json',public_manifest)
    atomic_json(output/'run_status.json',{'status':'completed_verified','planned':len(checks),'completed':len(checks),'missing':0})
    return summary
