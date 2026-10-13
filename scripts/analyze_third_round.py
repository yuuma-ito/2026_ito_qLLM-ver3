"""Audit all F/D cases eligible for a third repair, including unrecovered cases."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from harness.failure_metadata import normalize_record
from scripts.analyze_reach_levels import analyze_levels, reached, LEVELS
from scripts.analyze_interventions import _write
from scripts.analyze_repair_costs import round_cost
from scripts.automate_experiment import verify

CONDITIONS=('execution_feedback','self_debugging')
GROUPINGS={'overall':(), 'baseline_error':('baseline_error_category',),
    'round2_error':('round2_error_category',), 'model':('model_spec',), 'task':('task_id',),
    'difficulty':('task_difficulty',), 'model_baseline_error':('model_spec','baseline_error_category'),
    'model_round2_error':('model_spec','round2_error_category'), 'model_task':('model_spec','task_id'),
    'task_round2_error':('task_id','round2_error_category'), 'round2_level':('round2_level',),
    'net_progress_before3':('net_progress_before3',), 'repeated_error':('same_error_in_round1_and2',)}
DIMENSIONS=('model_spec','task_id','task_difficulty','baseline_error_category','round2_error_category',
            'round2_level','net_progress_before3','same_error_in_round1_and2')


def analyze_third_round(records):
    sources=defaultdict(list)
    for row in records:sources[row['experiment_id']].append(row)
    identities=set()
    for rows in sources.values():
        analyze_levels(rows)
        for row in rows:
            identity=(row['model_spec'],row['task_id'],row['base_seed'],row['intervention'])
            if identity in identities:raise ValueError('Overlapping sources')
            identities.add(identity)
    eligible=[];traces=[]
    for row in records:
        if row['intervention'] not in CONDITIONS:continue
        rounds=row['rounds']
        if rounds[0]['L3'] or 0<row['first_success_round']<=2:continue
        if len(rounds)!=4 or [r['round'] for r in rounds]!=[0,1,2,3] or rounds[2]['L3']:
            raise ValueError('Incomplete third-round history')
        if bool(row['L3'])!=(row['first_success_round']==3) or rounds[3]['L3']!=row['L3']:
            raise ValueError('Late success metadata mismatch')
        initial,first,before,final=rounds
        start,previous,end=(LEVELS.index(reached(r)) for r in (initial,before,final))
        pair_key=[row['experiment_id'],row['model_spec'],row['task_id'],row['base_seed']]
        pair_id=hashlib.sha256(json.dumps(pair_key,ensure_ascii=False).encode()).hexdigest()[:16]
        label='F' if row['intervention']=='execution_feedback' else 'D'
        cost=round_cost(final)
        item=dict(pair_id=pair_id,case_id=pair_id+'-'+label,source_experiment_id=row['experiment_id'],
            model_spec=row['model_spec'],task_id=row['task_id'],task_difficulty=row['task_difficulty'],
            base_seed=row['base_seed'],intervention=row['intervention'],
            baseline_error_category=initial['error_category'],baseline_level=reached(initial),
            round2_error_category=before['error_category'],round2_failure_stage=before['failure_stage'],
            round2_level=reached(before),
            net_progress_before3='improved' if previous>start else 'worsened' if previous<start else 'unchanged',
            same_error_in_round1_and2=first['error_category']==before['error_category'],
            rescued_in_round3=bool(final['L3']),final_level=reached(final),final_error_category=final['error_category'],
            partial_improvement_in_round3=end>previous and not final['L3'],stage_worsened_in_round3=end<previous,
            third_round_tokens=cost['total_tokens'],third_round_sec=cost['elapsed_sec'],
            record_sha256=row.get('source_record_sha256',''),round2_code_sha256=before.get('code_sha256',''),
            round3_code_sha256=final.get('code_sha256',''),
            error_trajectory=' -> '.join(f"{r['round']}:{r['error_category']}" for r in rounds))
        eligible.append(item)
        if item['rescued_in_round3']:
            for attempt in rounds:
                traces.append(dict(case_id=item['case_id'],source_experiment_id=row['experiment_id'],
                    model_spec=row['model_spec'],task_id=row['task_id'],base_seed=row['base_seed'],
                    intervention=row['intervention'],round=attempt['round'],level=reached(attempt),
                    failure_stage=attempt['failure_stage'],error_category=attempt['error_category'],
                    exception_type=attempt['exception_type'],code_sha256=attempt.get('code_sha256','')))
    groups=defaultdict(list)
    for row in eligible:
        for scope,source in [('source',row['source_experiment_id']),('pooled','')]:
            for grouping,fields in GROUPINGS.items():
                groups[(scope,source,grouping,row['intervention'],tuple(row[k] for k in fields))].append(row)
    summaries=[]
    for (scope,source,grouping,condition,values),items in sorted(groups.items()):
        row=dict(scope=scope,source_experiment_id=source,grouping=grouping,**dict.fromkeys(DIMENSIONS,''),
                 intervention=condition,eligible_count=len(items),rescued_count=sum(r['rescued_in_round3'] for r in items),
                 third_round_tokens=sum(r['third_round_tokens'] for r in items),
                 third_round_sec=sum(r['third_round_sec'] for r in items),
                 partial_improvement_count=sum(r['partial_improvement_in_round3'] for r in items),
                 stage_worsened_count=sum(r['stage_worsened_in_round3'] for r in items))
        row.update(zip(GROUPINGS[grouping],values))
        row['unrescued_count']=row['eligible_count']-row['rescued_count']
        row['rescue_rate']=row['rescued_count']/row['eligible_count']
        row['tokens_per_new_rescue']=row['third_round_tokens']/row['rescued_count'] if row['rescued_count'] else ''
        row['seconds_per_new_rescue']=row['third_round_sec']/row['rescued_count'] if row['rescued_count'] else ''
        row['small_denominator']=row['eligible_count']<10
        summaries.append(row)
    rules=[]
    for scope,source in {('pooled',''),*[('source',r['source_experiment_id']) for r in eligible]}:
        for condition in CONDITIONS:
            items=[r for r in eligible if r['intervention']==condition and (scope=='pooled' or r['source_experiment_id']==source)]
            if not items:continue
            for name,predicate in [('stop_on_repeated_category',lambda r:r['same_error_in_round1_and2']),
                                   ('continue_only_with_net_stage_improvement',lambda r:r['net_progress_before3']!='improved')]:
                stopped=[r for r in items if predicate(r)];continued=[r for r in items if not predicate(r)]
                rules.append(dict(scope=scope,source_experiment_id=source,intervention=condition,rule=name,
                    eligible_count=len(items),stopped_count=len(stopped),continued_count=len(continued),
                    third_round_rescues=sum(r['rescued_in_round3'] for r in items),
                    lost_rescues=sum(r['rescued_in_round3'] for r in stopped),
                    retained_rescues=sum(r['rescued_in_round3'] for r in continued),
                    saved_tokens=sum(r['third_round_tokens'] for r in stopped),
                    saved_sec=sum(r['third_round_sec'] for r in stopped),
                    kept_tokens=sum(r['third_round_tokens'] for r in continued),
                    kept_sec=sum(r['third_round_sec'] for r in continued)))
    late=[r for r in eligible if r['rescued_in_round3']]
    f_ids={r['pair_id'] for r in late if r['intervention']==CONDITIONS[0]}
    d_ids={r['pair_id'] for r in late if r['intervention']==CONDITIONS[1]}
    overlap=dict(feedback_late=len(f_ids),debugging_late=len(d_ids),both_late=len(f_ids&d_ids),
                 feedback_late_only=len(f_ids-d_ids),debugging_late_only=len(d_ids-f_ids),unique_late_pairs=len(f_ids|d_ids))
    result=dict(third_round_summary=summaries,eligible_trials=eligible,late_rescues=late,
                late_round_trajectories=traces,candidate_rule_checks=sorted(rules,key=lambda r:(r['scope'],r['source_experiment_id'],r['intervention'],r['rule'])),overlap=overlap)
    verify_third_round(result)
    return result


def verify_third_round(result):
    summaries=result['third_round_summary'];eligible=result['eligible_trials']
    if len({r['case_id'] for r in eligible})!=len(eligible):raise ValueError('Duplicate eligible case')
    if len(result['late_round_trajectories'])!=4*len(result['late_rescues']):raise ValueError('Late trace count mismatch')
    for row in summaries:
        if row['rescued_count']+row['unrescued_count']!=row['eligible_count']:raise ValueError('Outcome mismatch')
    for scope,source,condition in {(r['scope'],r['source_experiment_id'],r['intervention']) for r in summaries}:
        rows=[r for r in summaries if (r['scope'],r['source_experiment_id'],r['intervention'])==(scope,source,condition)]
        overall=next(r for r in rows if r['grouping']=='overall')
        for grouping in GROUPINGS:
            for k in ['eligible_count','rescued_count','third_round_tokens','third_round_sec','partial_improvement_count','stage_worsened_count']:
                if not math.isclose(sum(r[k] for r in rows if r['grouping']==grouping),overall[k],rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Grouping partition mismatch')
    for condition in CONDITIONS:
        overall=next((r for r in summaries if r['scope']=='pooled' and r['grouping']=='overall' and r['intervention']==condition),None)
        if overall is None:continue
        sources=[r for r in summaries if r['scope']=='source' and r['grouping']=='overall' and r['intervention']==condition]
        for k in ['eligible_count','rescued_count','third_round_tokens','third_round_sec']:
            if not math.isclose(sum(r[k] for r in sources),overall[k],rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Source partition mismatch')
    for r in result['candidate_rule_checks']:
        if r['stopped_count']+r['continued_count']!=r['eligible_count'] or r['lost_rescues']+r['retained_rescues']!=r['third_round_rescues']:
            raise ValueError('Rule partition mismatch')
        overall=next(s for s in summaries if (s['scope'],s['source_experiment_id'],s['intervention'],s['grouping'])==(r['scope'],r['source_experiment_id'],r['intervention'],'overall'))
        for metric in ['tokens','sec']:
            if not math.isclose(r['saved_'+metric]+r['kept_'+metric],overall['third_round_'+metric],rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Rule cost mismatch')
    return True


def render_report(result):
    names={CONDITIONS[0]:'F',CONDITIONS[1]:'D'}
    def table(grouping,fields,headers,scope='pooled'):
        lines=['| '+' | '.join([*headers,'条件','3回目実施','3回目救出','救出率','tokens／追加救出','秒／追加救出'])+' |',
               '| '+' | '.join(['---']*(len(headers)+1)+['---:']*5)+' |']
        for r in result['third_round_summary']:
            if r['scope']!=scope or r['grouping']!=grouping:continue
            values=[str(r[k]).removeprefix('ollama:') for k in fields]
            values += [names[r['intervention']],str(r['eligible_count']),str(r['rescued_count']),f"{100*r['rescue_rate']:.1f}%",
                '—' if r['tokens_per_new_rescue']=='' else f"{r['tokens_per_new_rescue']:,.1f}",
                '—' if r['seconds_per_new_rescue']=='' else f"{r['seconds_per_new_rescue']:,.1f}"]
            lines.append('| '+' | '.join(values)+' |')
        return lines
    overlap=result['overlap']
    lines=['# 3回目だけで救出した例と継続条件の検討','',
        f"F（実行結果提示）の{overlap['feedback_late']}件、D（自己デバッグ）の{overlap['debugging_late']}件は、修正3回目で初めてL3へ達した。両条件で3回目に救出した組は{overlap['both_late']}組で、独自の初期例は計{overlap['unique_late_pairs']}組。条件別記録数と独立した初期例数を区別する。",'',
        '3回目の価値は救出した例だけでなく、2回目まで未達で3回目を実施した全例を分母として比較する。初期失敗類型と3回目直前の失敗類型を別の軸で保存した。分類は生成コードの症状であり、原因が一意に確定したことやコードが変わらなかったことを示さない。','',
        '## baseline失敗類型別','',*table('baseline_error',['baseline_error_category'],['初期類型']),'',
        '## 3回目直前の失敗類型別','',*table('round2_error',['round2_error_category'],['round 2類型']),'',
        '## モデル別','',*table('model',['model_spec'],['モデル']),'',
        '## タスク別','',*table('task',['task_id'],['タスク']),'',
        '## モデルと直前の失敗類型','',*table('model_round2_error',['model_spec','round2_error_category'],['モデル','round 2類型']),'',
        '## 2回目までの到達段階の変化','',*table('net_progress_before3',['net_progress_before3'],['初期→round 2']),'',
        'improved／unchanged／worsenedは初期評価とround 2の順序カテゴリの比較であり、等間隔の点数差ではない。部分改善がある例も、改善していない例も対象に残す。救出0件のコスト／救出は空欄。少数分母10件未満はCSVのsmall_denominatorで参考値として表示する。','',
        '## 同じ分類が続いた場合','',*table('repeated_error',['same_error_in_round1_and2'],['round 1・2の分類が同じ']),'',
        '## 停止候補の観測済み履歴による確認','',
        '次の2つは事前に使える情報だけを参照する単純な候補であり、このデータで効果が保証された運用ルールではない。同じ履歴で「停止していたら省かれた3回目コストと失われた救出」を記述的に数える。','',
        '| 候補 | 条件 | 3回目実施組 | 停止組 | 失う救出 | 残る救出 | 省かれるtokens | 省かれる要求時間（時間） |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in result['candidate_rule_checks']:
        if r['scope']=='pooled':
            label='round 1・2で同じ失敗分類なら停止' if r['rule']=='stop_on_repeated_category' else '初期からround 2へ段階上昇した例だけ継続'
            lines.append('| '+' | '.join([label,names[r['intervention']],str(r['eligible_count']),str(r['stopped_count']),str(r['lost_rescues']),str(r['retained_rescues']),f"{r['saved_tokens']:,}",f"{r['saved_sec']/3600:.2f}"])+' |')
    lines+=['','## 出典別','',*table('overall',['source_experiment_id'],['出典'],scope='source'),'','## 履歴と限界','',
        'eligible_trials.csvは3回目を実施した全条件記録、late_rescues.csvは3回目の救出記録、late_round_trajectories.csvは救出例の初期・修正1〜3回目の評価段階と分類・コードhashを保存する。モデル×タスク、タスク×直前類型、元実験別など全13区分はthird_round_summary.csvで確認する。','',
        '同じデータから見つけた探索的な継続条件であり、新しいタスク・seedでの予測や停止方策は未検証。モデル・難度・失敗構成、schema 2.0/2.1の診断文処理差、実施時期、seedブロック、共有サーバ負荷の影響を含む。全体率だけで最適介入や一般的な停止条件、因果効果、統計的有意差を断定しない。Pは独立した初回生成で修正上限比較の対象外。','',
        '[修正上限の分析](../repair_limits_20261013/findings.md)と同じ検証済み固定出典を使用した。生データ・原判定を保持し、新規生成・生成コードの再評価を行っていない。生成コードや生の例外メッセージは公開ファイルへ含めない。manifest.jsonに出典・hash、sanity_report.jsonに合計と前段結果の照合を保存する。','',
        '```bash','.venv/bin/python -m scripts.analyze_third_round \\',
        '  --limit-manifest docs/analysis/repair_limits_20261013/manifest.json \\',
        '  --out-dir docs/analysis/<新しい保存先>','```','']
    return '\n'.join(lines)


def write_third_round_analysis(limit_manifest,output,root=Path.cwd()):
    import csv
    limit_manifest,output,root=Path(limit_manifest),Path(output),Path(root)
    if output.exists():raise ValueError('Use a new analysis directory')
    previous=json.loads(limit_manifest.read_text());snapshot_path=root/previous['fixed_snapshot']
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest()!=previous['snapshot_sha256']:raise ValueError('Fixed snapshot changed')
    snapshot=json.loads(snapshot_path.read_text());runs={r['experiment_id']:r for r in snapshot['runs']}
    if {s['experiment_id'] for s in previous['sources']}!=set(runs):raise ValueError('Source set changed')
    for a in previous['artifacts']:
        if hashlib.sha256((limit_manifest.parent/a['path']).read_bytes()).hexdigest()!=a['sha256']:raise ValueError('Parent artifact changed')
    records=[]
    for src in previous['sources']:
        source=(root/src['source_dir']).resolve();run=runs[src['experiment_id']]
        if not source.is_relative_to((root/'results').resolve()):raise ValueError('Source outside results')
        data=(source/'raw.jsonl').read_bytes();config=json.loads((source/'experiment_config.json').read_text())
        if not data.endswith(b'\n') or hashlib.sha256(data).hexdigest()!=src['raw_sha256'] or src['raw_sha256']!=run['raw_sha256']:raise ValueError('Raw source changed')
        if config!=src['config'] or config!=run['config']:raise ValueError('Source config changed')
        if not json.loads((source/'automation_report.json').read_text())['passed'] or not verify(config,source)['passed']:raise ValueError('Source is not verified')
        rows=[]
        for line in data.splitlines(keepends=True):
            if line.strip():
                row=normalize_record(json.loads(line));row['source_record_sha256']=hashlib.sha256(line).hexdigest();rows.append(row)
        levels=analyze_levels(rows)
        if len(rows)!=run['records'] or any(levels[k]!=run[k] for k in levels):raise ValueError('Fixed evaluations changed')
        if (source/'raw.jsonl').read_bytes()!=data:raise ValueError('Source changed during read')
        records.extend(rows)
    result=analyze_third_round(records)
    with (limit_manifest.parent/'cap_summary.csv').open(encoding='utf-8-sig',newline='') as f:previous_rows=list(csv.DictReader(f))
    shared_groupings={'overall','model','difficulty','baseline_error'}
    for row in result['third_round_summary']:
        if row['grouping'] not in shared_groupings:continue
        old=next(r for r in previous_rows if r['scope']==row['scope'] and r['source_experiment_id']==row['source_experiment_id'] and r['grouping']==row['grouping'] and r['intervention']==row['intervention'] and r['cap']=='3' and all(r[k]==str(row[k]) for k in ['model_spec','task_difficulty','baseline_error_category']))
        for new,old_key in [('eligible_count','marginal_attempted'),('rescued_count','marginal_rescued'),('third_round_tokens','marginal_cost_total_tokens'),('third_round_sec','marginal_cost_elapsed_sec')]:
            if not math.isclose(row[new],float(old[old_key]),rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Third-round result differs from cap analysis')
    output.mkdir(parents=True);artifacts=[]
    for name,rows in result.items():
        if name=='overlap':
            p=output/'overlap.json';p.write_text(json.dumps(rows,indent=2)+'\n')
        else:
            p=output/(name+'.csv');_write(p,rows,list(rows[0]) if rows else ['case_id','intervention'])
        artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    p=output/'README.md';p.write_text(render_report(result));artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    m=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),analysis_version='third_round_v1',
        analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limit_manifest=str(limit_manifest),limit_manifest_sha256=hashlib.sha256(limit_manifest.read_bytes()).hexdigest(),
        fixed_snapshot=previous['fixed_snapshot'],snapshot_sha256=previous['snapshot_sha256'],sources=previous['sources'],
        records=len(records),overlap=result['overlap'],artifacts=artifacts,generated_new_code=False,reevaluated_generated_code=False,
        interpretation='Exploratory observed-history comparison; stopping candidates not prospectively validated.')
    (output/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    (output/'sanity_report.json').write_text(json.dumps(dict(passed=True,sources_reverified=True,source_hashes_unchanged=True,
        fixed_evaluations_match=True,parent_artifacts_match=True,third_round_matches_cap_analysis=True,
        source_and_grouping_totals_match=True,candidate_rules_partition_costs_and_outcomes=True),indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--limit-manifest',required=True);p.add_argument('--out-dir',required=True)
    args=p.parse_args();result=write_third_round_analysis(args.limit_manifest,args.out_dir)
    print(json.dumps(result['overlap'],ensure_ascii=False))


if __name__=='__main__':main()
