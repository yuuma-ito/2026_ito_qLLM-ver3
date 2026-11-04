"""Independent packet reconciliation and eight-part final report; no generation."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path

from harness.factorial_pilot import CONDITIONS,build_prompt,wire_body,paired_seed,schedule
from harness.independent_4 import read_checkpoint,digest,immutable_json,code_hash
from harness.code_extractor import extract_code
from harness.measurement_isolation import profile
from scripts.measurement_ban_sources import ROOT,sha
from scripts.measurement_ban_report import write_csv
from scripts.run_factorial_pilot import assert_frozen,notify
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
    for left,right in [('A','B'),('B','C'),('C','D')]:
        counts=Counter((outcomes[c['case_id'],left],outcomes[c['case_id'],right]) for c in cases)
        comparisons.append({'stage':cap,'left':left,'right':right,'both':counts[True,True],
                            'left_only':counts[True,False],'right_only':counts[False,True],'neither':counts[False,False]})
    return summary,comparisons,structrows


def verify_and_report(output,*,send_notification=False):
    plan=read_checkpoint(output/'manifest.json');public=ROOT/plan['analysis_dir']
    complete=read_checkpoint(public/'completion.json')
    if complete['status']!='completed_verified':raise ValueError('generation incomplete')
    assert_frozen(plan,protected=True)
    cases=read_checkpoint(output/'private/initials.json');lookup={c['case_id']:c for c in cases}
    records=[json.loads(line) for line in (output/'raw.jsonl').read_text().splitlines()]
    if len(records)!=complete['actual_requests'] or not 400<=len(records)<=1200:raise ValueError('request count mismatch')
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
    if executed!=records or len(executed)+skips!=1200:raise ValueError('all planned requests not accounted for')
    if len(list((output/'private/attempts').glob('*/*/*/request.json')))!=len(records):raise ValueError('unexpected request packet')
    if any(not h[-1]['primary']['L3'] and len(h)!=4 for h in histories.values()):raise ValueError('incomplete unsuccessful path')
    if len([r for r in records if r['round']==1])!=400 or read_checkpoint(output/'private/stage1_records.json')!=[r for r in records if r['round']==1]:raise ValueError('stage1 boundary drift')
    for phase in ['start','stage1','final']:
        checks=json.loads((output/('model_check_'+phase+'.json')).read_text())
        if {m:r['digest_verified'] for m,r in checks.items()}!=plan['model_digests']:raise ValueError('phase model check missing')
    from scripts.factorial_pilot_sources import load_current
    from harness.factorial_pilot import sample_cases
    population,_,_=load_current();selected=sample_cases(population)
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
    checks={'passed':True,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':plan['plan_sha256'],
            'initials_independently_reconstructed':100,'initials_false_L3':100,'condition_paths':400,
            'stage1_requests':400,'total_requests':len(records),'skipped_slots_after_success':skips,
            'planned_slots_accounted':1200,'missing':0,'duplicates':0,'unexpected':0,
            'packet_hashes':packet_hashes,'wire_prompts_and_own_history_verified':True,
            'tokens_and_finish_reasons_recomputed':True,'paired_outcomes_and_ast_metrics_recomputed':True,
            'protected_old_sources_verified':len(plan['protected_inputs']),'models_verified_before_stage1_after_stage1_and_after_stage2':True,
            'git_operations_performed':False,'thesis_updated':False,'model_requests_in_validation':0,'generated_code_executions_in_validation':0,
            'validator_sha256':sha(Path(__file__))}
    final=public/'independent_review';final.mkdir(exist_ok=False)
    write_csv(final/'stage1_and_final_summary.csv',[dict(stage=cap,**r) for cap,ss in recomputed.items() for r in ss.values()])
    write_csv(final/'paired_success.csv',pairwise);write_csv(final/'structural_checks.csv',struct)
    lines=['B4と修正介入の成功率差に関する追加実験：最終報告',f'実験ID: {plan["run_id"]}',
           '100初期失敗組の探索的予備実験。A/B/C/Dは既存のB4/R/F/Dとは別の条件。主実験・卒論・図表・要旨は未変更。コミット・pushなし。','',
           '1. 追加1回目のL3成功率']
    for a,r in recomputed[1].items():lines.append(f"{a}: {r['successes']}/100 ({r['successes']}%)")
    lines.extend(['','2. 最大3回の累積追加成功率'])
    for a,r in recomputed[3].items():lines.append(f"{a}: {r['successes']}/100 ({r['successes']}%)、{r['requests']}要求")
    lines.extend(['','3. 条件間の共通成功・片側成功'])
    for r in pairwise:lines.append(f"追加{r['stage']}回上限 / {r['left']}-{r['right']}: 共通{r['both']}、左のみ{r['left_only']}、右のみ{r['right_only']}、双方失敗{r['neither']}")
    lines.extend(['','4. コード構造の再出力率'])
    for cap,ss in recomputed.items():
        for a,r in ss.items():
            valid=r['ast_comparable_requests'];n=r['same_failed_ast_requests']
            lines.append(f"追加{cap}回上限 / {a}: 同じ失敗AST {n}/{valid}有効対 ({100*n/valid:.1f}%)、全{r['requests']}要求、構造変化{r['ast_changed_requests']}、解析不能{r['requests']-valid}" if valid else f"追加{cap}回上限 / {a}: 有効AST対0、全{r['requests']}要求")
    lines.extend(['ASTはコメント・書式・位置を除いたPython構造。任意入力での意味的同値性ではない。Aも観察上の直前出力との比較であり、直前コードを入力したことは意味しない。','',
                  '5. tokens・生成終了理由'])
    for a,r in recomputed[3].items():
        gain=r['successes'];tokens=r['total_tokens']
        lines.append(f"{a}: 入力{r['tokens_in']}・出力{r['tokens_out']}・合計{tokens} tokens、tokens/成功={tokens/gain if gain else '未定義（成功0）'}、失敗要求への消費{r['failed_request_tokens']}、最終未救済経路への消費{r['never_success_path_tokens']}、length={r['finish_length']}/{r['requests']}、1024到達={r['output_at_1024']}/{r['requests']}")
    lines.extend(['終了理由lengthと出力1024到達を区別。全終了理由はstage1/finish_reasons.csvとfinal/finish_reasons.csv。初期生成の旧消費は新規消費に含めない。','',
                  '6. モデル別・初期失敗類型別・タスク別'])
    subgroup=list(csv.DictReader((public/'final/summary.csv').open()))
    for grouping in ['model_spec','initial_error','task_id']:
        for value in sorted({r['group'] for r in subgroup if r['grouping']==grouping}):
            rows={r['condition']:r for r in subgroup if r['grouping']==grouping and r['group']==value}
            n=rows['A']['initial_failures'];lines.append(f"{grouping} / {value} (n={n}): "+'、'.join(f"{a}={rows[a]['successes']}" for a in CONDITIONS)+('；少数層' if int(n)<10 else ''))
    lines.extend(['','7. 既存のB4優位に関連する観測'])
    for cap in [1,3]:
        values=recomputed[cap]
        acount=values['A']['successes'];other=max(values[a]['successes'] for a in ['B','C','D'])
        if acount>other:
            lines.append(f'追加{cap}回上限ではAがB/C/Dすべてを上回った。この標本では独立再生成の高い成績という観測が再現された。')
        elif acount==other:
            lines.append(f'追加{cap}回上限ではAが同率首位であり、独立再生成の厳密な優位は確認していない。')
        else:
            lines.append(f'追加{cap}回上限ではAより成功数の多い修正条件がある。旧B4の順位がこの標本でも一律に再現されたとはいえない。')
        for left,right,label in [('A','B','前回コード提示'),('B','C','診断追加'),('C','D','説明・原因分析指示追加')]:
            delta=values[right]['successes']-values[left]['successes']
            lines.append(f"追加{cap}回上限 / {label}: {right}−{left}={delta:+d}組（{delta:+d}ポイント）。同じ標本内の観測差であり、一般的な優劣を確定しない。")
    lines.extend(['独立再生成Aが高ければ旧B4と整合する観測、高くなければ旧B4の優位がこの条件・標本では再現されない観測として、そのまま報告する。',
                  '反復・構造変化・消費の対応は記述的関連。累積経路が条件ごとに分岐するため、単一要素だけの直接的・機構的因果効果と断定しない。','',
                  '8. 未解明の点と追加検証',
                  '100組の探索的予備実験で、小さな差の確証、全545組への推定、未知のモデル・タスク・seedへの一般化は未検証。抽出率が均一でないため、標本率を母集団率と同一視しない。',
                  'seed対応は乱数列の完全一致の証明ではない。APIが設定付き要求を受理した記録を保存したが、サーバ内部の乱数実装を直接検証したものではない。',
                  '同要求回数でも入力長と出力の使い方が違う。同tokens予算での比較と別seedでの再現確認は別途必要であり、今回は事後追加しない。',
                  '説明の質、診断文の各成分、モデルの前回コードへの固執を完全には分離できない。AST一致はその機構を証明しない。',
                  '差の方向にかかわらず全条件・全事前指定層を保持し、都合のよい層だけで有意差を主張しない。',
                  '400要求の第1段階レポートを確定してから、同じ設定・対象で失敗経路のみをround2,3へ継続した。',
                  '独立検証：全1200予定枠、要求・応答・評価・入力ハッシュ、初期集合、自己履歴、停止・上限、tokens、対応表とAST指標を照合した。既存固定データと卒論は不変。'])
    (final/'final_report.txt').write_text('\n'.join(lines)+'\n')
    immutable_json(final/'validation_report.json',checks)
    immutable_json(final/'manifest.json',{'plan_sha256':plan['plan_sha256'],'outputs':{p.name:sha(p) for p in final.iterdir() if p.is_file()},'status':'completed_verified'})
    if send_notification:
        one=', '.join(f"{a}={r['successes']}%" for a,r in recomputed[1].items())
        three=', '.join(f"{a}={r['successes']}%" for a,r in recomputed[3].items())
        notify(plan,'independent_final_report',f"予備実験の独立検証と最終8項目レポートを作成しました。追加1回: {one}。最大3回: {three}。計{len(records)}要求、旧結果・卒論不変、コミット・pushなし。全対応表・AST・tokens・終了理由を保存。最終報告: {final/'final_report.txt'}")
    print(json.dumps({'status':'completed_verified','stage1':{a:r['successes'] for a,r in recomputed[1].items()},'final':{a:r['successes'] for a,r in recomputed[3].items()},'requests':len(records),'report':str(final/'final_report.txt')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--notify',action='store_true');args=p.parse_args()
    verify_and_report(args.output if args.output.is_absolute() else ROOT/args.output,send_notification=args.notify)
