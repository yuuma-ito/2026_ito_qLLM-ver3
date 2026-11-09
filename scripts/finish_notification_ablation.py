"""Reconcile saved request/response/evaluation packets without new generation."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path

from harness.notification_ablation import CONDITIONS,COMPARISONS,build_prompt,wire_body,paired_seed,schedule
from harness.independent_4 import read_checkpoint,digest,immutable_json,code_hash
from harness.code_extractor import extract_code
from harness.measurement_isolation import profile
from scripts.measurement_ban_sources import ROOT,sha
from scripts.measurement_ban_report import write_csv
from scripts.run_notification_ablation import assert_frozen
from tasks import get_task


def structure(code):
    try:return hashlib.sha256(ast.dump(ast.parse(code),include_attributes=False).encode()).hexdigest()
    except (SyntaxError,ValueError,TypeError,RecursionError):return None


def summarize_independently(cases,records,cap):
    paths={(c['case_id'],a):[] for c in cases for a in CONDITIONS}
    for r in records:
        if r['round']<=cap:paths[r['case_id'],r['condition']].append(r)
    summary={};outcomes={};structrows=[]
    for a in CONDITIONS:
        n=successes=requests=tokens_in=tokens_out=failed_tokens=unrescued_tokens=valid=changed=repeated=length=cap_count=0
        for case in cases:
            rr=paths[case['case_id'],a]
            if not rr:raise ValueError('missing path in independent summary')
            passed=rr[-1]['primary']['L3'];outcomes[case['case_id'],a]=passed
            n+=1;successes+=passed;requests+=len(rr)
            previous=case['initial']['code']
            for r in rr:
                tokens_in+=r['tokens_in'];tokens_out+=r['tokens_out']
                failed_tokens+=(r['tokens_in']+r['tokens_out']) if not r['primary']['L3'] else 0
                unrescued_tokens+=(r['tokens_in']+r['tokens_out']) if not passed else 0
                before,after=structure(previous),structure(r['code']);assessable=before is not None and after is not None
                valid+=assessable;changed+=assessable and before!=after
                repeat=assessable and before==after and not r['primary']['L3'];repeated+=repeat
                length+=r['finish_reason']=='length';cap_count+=r['tokens_out']==1024
                structrows.append({'stage':cap,'case_id':case['case_id'],'condition':a,'round':r['round'],
                                   'comparable':assessable,'changed':assessable and before!=after,'same_failed_ast':repeat})
                previous=r['code']
        summary[a]={'condition':a,'initial_failures':n,'successes':successes,'success_rate':successes/n,
                    'requests':requests,'tokens_in':tokens_in,'tokens_out':tokens_out,'total_tokens':tokens_in+tokens_out,
                    'failed_request_tokens':failed_tokens,'never_success_path_tokens':unrescued_tokens,
                    'ast_comparable_requests':valid,'ast_changed_requests':changed,'same_failed_ast_requests':repeated,
                    'finish_length':length,'output_at_1024':cap_count}
    comparisons=[]
    for left,right in COMPARISONS:
        counts=Counter((outcomes[c['case_id'],left],outcomes[c['case_id'],right]) for c in cases)
        comparisons.append({'stage':cap,'left':left,'right':right,'both':counts[True,True],
                            'left_only':counts[True,False],'right_only':counts[False,True],'neither':counts[False,False]})
    return summary,comparisons,structrows


def verify_and_report(output):
    plan=read_checkpoint(output/'manifest.json');public=ROOT/plan['analysis_dir']
    complete=read_checkpoint(public/'completion.json')
    if complete['status']!='completed_verified':raise ValueError('generation incomplete')
    assert_frozen(plan,protected=True)
    cases=read_checkpoint(output/'private/initials.json');lookup={c['case_id']:c for c in cases}
    records=[json.loads(line) for line in (output/'raw.jsonl').read_text().splitlines()]
    if len(records)!=complete['actual_requests'] or not 1635<=len(records)<=4905:raise ValueError('request count mismatch')
    saved={(r['case_id'],r['condition'],r['round']):r for r in records}
    if len(saved)!=len(records):raise ValueError('duplicate raw record')
    histories={(c['case_id'],a):[c['initial']] for c in cases for a in CONDITIONS}
    executed=[];skips=0;packet_hashes={}
    for slot in schedule(cases):
        case=lookup[slot['case_id']];a=slot['condition'];i=slot['round'];key=(case['case_id'],a)
        folder=output/'private/attempts'/case['case_id']/a/f'round_{i}'
        if histories[key][-1]['primary']['L3']:
            skip=read_checkpoint(folder/'skip.json')
            if skip!={'case_id':case['case_id'],'condition':a,'round':i,'status':'skipped_after_success'} or (folder/'request.json').exists():raise ValueError('invalid skipped request')
            skips+=1;continue
        row=saved[case['case_id'],a,i]
        request=read_checkpoint(folder/'request.json');response=read_checkpoint(folder/'response.json')
        evaluation=read_checkpoint(folder/'evaluation.json');record=read_checkpoint(folder/'record.json')
        model=read_checkpoint(folder/'server_before.json')
        if record!=row or request['execution_index']!=len(executed)+1 or row['execution_index']!=len(executed)+1 or row['nominal_position']!=slot['nominal_position']:
            raise ValueError('record sequence or execution order mismatch')
        prompt=build_prompt(a,get_task(case['task_id']),histories[key][-1])
        if request['wire_body']!=wire_body(case['model_spec'],prompt,paired_seed(case,i)) or row['input_prompt_sha256']!=code_hash(prompt):
            raise ValueError('own previous history or wire settings mismatch')
        if request['timeout_sec']!=600 or request['parallel_requests']!=1 or request['plan_sha256']!=plan['plan_sha256']:
            raise ValueError('runtime setting drift')
        if row['initial_fingerprint']!=digest(case['initial']) or row['seed']!=paired_seed(case,i):raise ValueError('initial/seed drift')
        if extract_code(response['raw_output'])!=row['code'] or code_hash(row['code'])!=row['code_sha256']:
            raise ValueError('response code mismatch')
        if evaluation['primary']!=row['primary'] or evaluation['runtime_status']!='completed':raise ValueError('evaluation packet mismatch')
        usage=response['response']['usage']
        if response['response']['model']!=case['model_spec'].removeprefix('ollama:') or model['digest_verified']!=plan['model_digests'][case['model_spec']]:raise ValueError('model identity mismatch')
        if usage['prompt_tokens']!=row['tokens_in'] or usage['completion_tokens']!=row['tokens_out'] or row['tokens_out']>1024:
            raise ValueError('usage mismatch')
        if not row['finish_reason'] or row['finish_reason']!=response['response']['choices'][0]['finish_reason']:
            raise ValueError('finish reason missing or inconsistent')
        if len(histories[key])!=i:raise ValueError('unreachable history')
        histories[key].append({'code':row['code'],'primary':row['primary']});executed.append(row)
        for name in ['request','response','evaluation','record','server_before']:
            p=folder/(name+'.json');packet_hashes[str(p.relative_to(ROOT))]=sha(p)
    if executed!=records or len(executed)+skips!=4905:raise ValueError('all planned requests not accounted for')
    if len(list((output/'private/attempts').glob('*/*/*/request.json')))!=len(records):raise ValueError('unexpected request packet')
    if any(not h[-1]['primary']['L3'] and len(h)!=4 for h in histories.values()):raise ValueError('incomplete unsuccessful path')
    if len([r for r in records if r['round']==1])!=1635 or read_checkpoint(output/'private/stage1_records.json')!=[r for r in records if r['round']==1]:raise ValueError('stage1 boundary drift')
    for phase in ['start','stage1','final']:
        checks=json.loads((output/('model_check_'+phase+'.json')).read_text())
        if {m:r['digest_verified'] for m,r in checks.items()}!=plan['model_digests']:raise ValueError('phase model check missing')
    from scripts.factorial_pilot_sources import load_current
    from harness.notification_ablation import ordered_cases
    population,_,_=load_current();selected=ordered_cases(population)
    if digest(selected)!=plan['initials_sha256']:raise ValueError('independent source initial/sample reconstruction drift')
    recomputed={};pairwise=[];struct=[]
    for cap,folder in [(1,public/'stage1'),(3,public/'final')]:
        manifest=read_checkpoint(folder/'manifest.json')
        for name,h in manifest['outputs'].items():
            if sha(folder/name)!=h:raise ValueError('stage artifact drift')
        summary,pairs,features=summarize_independently(cases,records,cap)
        published=list(csv.DictReader((folder/'summary.csv').open()));published_pairs=list(csv.DictReader((folder/'paired_success.csv').open()))
        for a,metrics in summary.items():
            actual=next(r for r in published if r['condition']==a and r['grouping']=='overall')
            for metric,n in metrics.items():
                if metric!='condition' and abs(float(actual[metric])-n)>1e-8:raise ValueError('independent aggregate mismatch: '+metric)
        for r in pairs:
            actual=next(x for x in published_pairs if x['grouping']=='overall' and x['left']==r['left'] and x['right']==r['right'])
            if any(int(actual[k])!=r[k] for k in ['both','left_only','right_only','neither']):raise ValueError('paired outcome mismatch')
        recomputed[cap]=summary;pairwise.extend(pairs);struct.extend(features)
    checks = dict(passed=True, checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  plan_sha256=plan['plan_sha256'], initials_reconstructed=545, condition_paths=1635,
                  stage1_requests=1635, total_requests=len(records), skipped_slots_after_success=skips,
                  planned_slots_accounted=4905, missing=0, duplicates=0, unexpected=0,
                  api_failures=0, runtime_failures=0, packet_hashes=packet_hashes,
                  wire_prompts_and_own_history_verified=True, tokens_and_finish_reasons_recomputed=True,
                  paired_outcomes_and_ast_metrics_recomputed=True, protected_old_sources_verified=len(plan['protected_inputs']),
                  models_verified_before_stage1_after_stage1_and_after_stage2=True,
                  model_requests_in_validation=0, generated_code_executions_in_validation=0,
                  validator_sha256=sha(Path(__file__)))
    final = public/'packet_verification'
    if final.exists():
        pinned = read_checkpoint(final/'manifest.json')
        for name, h in pinned['outputs'].items():
            if sha(final/name) != h:
                raise ValueError('Existing packet verification drift')
        if pinned['plan_sha256'] != plan['plan_sha256']:
            raise ValueError('Verification plan changed')
        return read_checkpoint(final/'sanity_report.json')
    final.mkdir()
    write_csv(final/'stage1_and_final_summary.csv', [dict(stage=cap, **r)
              for cap, ss in recomputed.items() for r in ss.values()])
    write_csv(final/'paired_success.csv', pairwise)
    write_csv(final/'structural_checks.csv', struct)
    immutable_json(final/'sanity_report.json', checks)
    lines = ['失敗通知・詳細診断実験：全保存パケットの照合結果', f'実験ID: {plan["run_id"]}',
             f'要求{len(records)}、成功後の省略{skips}。全4905枠を照合。欠落・重複・予定外記録・API障害・評価基盤障害0。',
             '初期545組を出典から再構成し、要求・応答・評価・自己履歴・モデルdigest・seed・停止規則を照合した。',
             '独立した集計処理で対応成否・AST・消費を再計算。採点の再実行やモデルの内部状態の検証は行っていない。']
    for cap, ss in recomputed.items():
        lines.append(f'追加{cap}回上限')
        for condition, metrics in ss.items():
            lines.append(f"{condition}: {metrics['successes']}/545、{metrics['requests']}要求、{metrics['total_tokens']} tokens")
    lines += ['主評価は追加1回の通知有無・詳細診断有無。累積差は後続経路も異なる方策の比較。',
              '旧R/F/Dとは同一でない。既存100組と独立な追加標本として合算しない。',
              '未知の課題・seedへの一般化、内的な失敗理解、各診断成分の因果機序は未検証。']
    (final/'report.txt').write_text('\n'.join(lines)+'\n')
    immutable_json(final/'manifest.json', dict(plan_sha256=plan['plan_sha256'], status='completed_verified',
        outputs={p.name:sha(p) for p in final.iterdir() if p.is_file()}))
    return checks


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    checks = verify_and_report(args.output if args.output.is_absolute() else ROOT/args.output)
    print(json.dumps({k:v for k,v in checks.items() if k != 'packet_hashes'}, ensure_ascii=False))
