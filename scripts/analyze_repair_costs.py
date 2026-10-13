"""Account for measured generation costs without duplicating shared round 0."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

from harness.failure_metadata import normalize_record
from scripts.analyze_reach_levels import INTERVENTIONS, REPAIRS, analyze_levels, reached, LEVELS
from scripts.analyze_stratified_effects import analyze_strata, verify_aggregates
from scripts.analyze_interventions import _write
from scripts.automate_experiment import verify

METRICS = ("tokens_in", "tokens_out", "total_tokens", "elapsed_sec")
GROUPINGS = {"overall": (), "model": ("model_spec",), "difficulty": ("task_difficulty",),
    "model_difficulty": ("model_spec","task_difficulty"), "seed_block": ("seed_block",),
    "model_seed_block": ("model_spec","seed_block"),
    "model_difficulty_seed_block": ("model_spec","task_difficulty","seed_block"),
    "baseline_error": ("baseline_error_category",)}
DIMENSIONS = ("model_spec","task_difficulty","seed_block","baseline_error_category")


def round_cost(attempt):
    for key in METRICS:
        value=attempt.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError("Invalid round cost")
        if key!='elapsed_sec' and (not isinstance(value,int)):
            raise ValueError("Token count must be an integer")
    if attempt['total_tokens']!=attempt['tokens_in']+attempt['tokens_out']:
        raise ValueError("Round token sum mismatch")
    return {k:attempt[k] for k in METRICS}


def cost_sum(attempts):
    values=[round_cost(a) for a in attempts]
    return {k:sum(v[k] for v in values) for k in METRICS}


def equal_cost(left,right):
    return all(math.isclose(left[k],right[k],rel_tol=1e-9,abs_tol=1e-6) for k in METRICS)


def analyze_costs(records):
    strata=analyze_strata(records);verify_aggregates(strata)
    pairs=defaultdict(dict)
    for row in records:
        key=(row['experiment_id'],row['model_spec'],row['task_id'],row['base_seed'])
        pairs[key][row['intervention']]=row
        totals=cost_sum(row['rounds'])
        if not equal_cost(totals,round_cost(row)):
            raise ValueError("Record costs differ from round sums")
        if [a['round'] for a in row['rounds']]!=list(range(len(row['rounds']))):
            raise ValueError("Non-consecutive round history")
        success=[a['round'] for a in row['rounds'] if a['L3']]
        if row['first_success_round']!=(success[0] if success else -1):
            raise ValueError("First success round mismatch")
        if success and success[0]!=len(row['rounds'])-1:
            raise ValueError("Generation continued after first L3 success")
    trials,ledger,cohorts=[],[],[]
    for (source,model,task,seed),conditions in sorted(pairs.items()):
        baseline=conditions['baseline'];initial=round_cost(baseline['rounds'][0])
        dims=dict(source_experiment_id=source,model_spec=model,task_id=task,base_seed=seed,
            task_difficulty=baseline['task_difficulty'],seed_block='0-9' if seed<10 else '10-19',
            baseline_error_category=baseline['error_category'])
        pair_trials={}
        for condition in ('baseline',*INTERVENTIONS):
            row=conditions[condition]
            if condition=='baseline' and len(row['rounds'])!=1:
                raise ValueError("Baseline must have one generation")
            if condition=='preventive_spec' and len(row['rounds'])!=1:
                raise ValueError("Preventive specification must have one generation")
            if condition in REPAIRS:
                if not equal_cost(initial,round_cost(row['rounds'][0])):
                    raise ValueError("Shared initial generation costs differ")
                charged=row['rounds'][1:]
                if baseline['L3'] and charged:
                    raise ValueError("Initial success must not trigger repair")
            else:
                charged=row['rounds']
            for a in charged:
                ledger.append(dict(**dims,intervention=condition,round=a['round'],**round_cost(a),
                                   connection_retries=a.get('connection_retries',0)))
            if condition=='baseline':continue
            cost=cost_sum(charged)
            rescued=not baseline['L3'] and row['L3']
            outcome=('rescued' if rescued else 'unrescued' if not baseline['L3'] else
                     'regressed' if not row['L3'] else 'preserved_success')
            trial=dict(**dims,intervention=condition,
                cost_kind='repair_additional' if condition in REPAIRS else 'independent_generation',
                baseline_L3=baseline['L3'],final_L3=row['L3'],outcome=outcome,
                partial_improvement=not row['L3'] and LEVELS.index(reached(row))>LEVELS.index(reached(baseline)),
                charged_rounds=len(charged),first_success_round=row['first_success_round'],
                **{f'cost_{k}':v for k,v in cost.items()},
                connection_retries=sum(a.get('connection_retries',0) for a in charged))
            trials.append(trial);pair_trials[condition]=trial
        f,d=pair_trials['execution_feedback'],pair_trials['self_debugging']
        cohort=('initial_success' if baseline['L3'] else 'both_rescued' if f['final_L3'] and d['final_L3']
                else 'feedback_only' if f['final_L3'] else 'debugging_only' if d['final_L3'] else 'neither_rescued')
        cohorts.append(dict(**dims,cohort=cohort,
            F_cost_tokens=f['cost_total_tokens'],D_cost_tokens=d['cost_total_tokens'],
            F_cost_sec=f['cost_elapsed_sec'],D_cost_sec=d['cost_elapsed_sec'],
            F_charged_rounds=f['charged_rounds'],D_charged_rounds=d['charged_rounds'],
            D_minus_F_tokens=d['cost_total_tokens']-f['cost_total_tokens'],
            D_minus_F_sec=d['cost_elapsed_sec']-f['cost_elapsed_sec']))
    summaries=[];grouped=defaultdict(list)
    for trial in trials:
        for scope,source in [('source',trial['source_experiment_id']),('pooled','')]:
            for grouping,fields in GROUPINGS.items():
                grouped[(scope,source,grouping,trial['intervention'],tuple(trial[k] for k in fields))].append(trial)
    for (scope,source,grouping,condition,values),items in sorted(grouped.items()):
        row=dict(scope=scope,source_experiment_id=source,grouping=grouping,**dict.fromkeys(DIMENSIONS,''),
                 intervention=condition,cost_kind=items[0]['cost_kind'],n_pairs=len(items))
        row.update(zip(GROUPINGS[grouping],values))
        for outcome in ['rescued','unrescued','regressed','preserved_success']:
            chosen=[t for t in items if t['outcome']==outcome]
            row[outcome+'_count']=len(chosen)
            for metric in ['total_tokens','elapsed_sec']:
                row[outcome+'_cost_'+metric]=sum(t['cost_'+metric] for t in chosen)
        row['baseline_L3_failure']=row['rescued_count']+row['unrescued_count']
        row['final_L3_success']=row['rescued_count']+row['preserved_success_count']
        row['partial_improvement_count']=sum(t['partial_improvement'] for t in items)
        row['charged_rounds']=sum(t['charged_rounds'] for t in items)
        row['connection_retries']=sum(t['connection_retries'] for t in items)
        for metric in METRICS:
            row['cost_'+metric]=sum(t['cost_'+metric] for t in items)
        n=row['rescued_count'];failure=row['baseline_L3_failure']
        row['L3_rescue_rate']=n/failure if failure else ''
        row['mean_success_round_of_rescues']=mean(t['first_success_round'] for t in items if t['outcome']=='rescued') if n else ''
        row['success_round_1']=sum(t['outcome']=='rescued' and t['first_success_round']==1 for t in items)
        row['success_round_2']=sum(t['outcome']=='rescued' and t['first_success_round']==2 for t in items)
        row['success_round_3']=sum(t['outcome']=='rescued' and t['first_success_round']==3 for t in items)
        for metric in ['total_tokens','elapsed_sec']:
            total=row['cost_'+metric];success=row['rescued_cost_'+metric]
            row['all_cost_per_rescue_'+metric]=total/n if n else ''
            row['rescued_only_mean_cost_'+metric]=success/n if n else ''
            row['unrescued_cost_share_'+metric]=row['unrescued_cost_'+metric]/total if total else ''
            row['cost_per_final_success_'+metric]=total/row['final_L3_success'] if row['final_L3_success'] else ''
        summaries.append(row)
    fd_groups=defaultdict(list)
    for trial in cohorts:
        for scope,source in [('source',trial['source_experiment_id']),('pooled','')]:
            for grouping in ['overall','model','difficulty','model_difficulty']:
                fields=GROUPINGS[grouping]
                fd_groups[(scope,source,grouping,trial['cohort'],tuple(trial[k] for k in fields))].append(trial)
    fd_summary=[]
    for (scope,source,grouping,cohort,values),items in sorted(fd_groups.items()):
        row=dict(scope=scope,source_experiment_id=source,grouping=grouping,**dict.fromkeys(DIMENSIONS,''),cohort=cohort,n_pairs=len(items))
        row.update(zip(GROUPINGS[grouping],values))
        for k in ['F_cost_tokens','D_cost_tokens','F_cost_sec','D_cost_sec','F_charged_rounds','D_charged_rounds']:
            row['total_'+k]=sum(t[k] for t in items);row['mean_'+k]=mean(t[k] for t in items)
        for k in ['D_minus_F_tokens','D_minus_F_sec']:
            row['mean_'+k]=mean(t[k] for t in items);row['median_'+k]=median(t[k] for t in items)
        fd_summary.append(row)
    record_totals={k:sum(r[k] for r in records) for k in METRICS}
    unique_totals={k:sum(r[k] for r in ledger) for k in METRICS}
    initial_totals={k:sum(r[k] for r in ledger if r['intervention']=='baseline') for k in METRICS}
    if not equal_cost(record_totals,{k:unique_totals[k]+3*initial_totals[k] for k in METRICS}):
        raise ValueError("Shared initial generation accounting mismatch")
    accounting=dict(records=len(records),pairs=len(pairs),stored_round_rows=sum(len(r['rounds']) for r in records),
        unique_recorded_generation_rounds=len(ledger),duplicated_initial_round_rows=3*len(pairs),
        stored_record_totals=record_totals,unique_generation_totals=unique_totals,shared_initial_totals=initial_totals,
        generation_rounds_with_recovery=sum(r['connection_retries']>0 for r in ledger),
        recorded_connection_retries=sum(r['connection_retries'] for r in ledger))
    baseline_groups=defaultdict(list)
    for item in ledger:
        if item['intervention']!='baseline':continue
        for scope,source in [('source',item['source_experiment_id']),('pooled','')]:
            for grouping,fields in GROUPINGS.items():
                baseline_groups[(scope,source,grouping,tuple(item[f] for f in fields))].append(item)
    workflows=[];seen=set()
    for r in summaries:
        key=(r['scope'],r['source_experiment_id'],r['grouping'],tuple(r[f] for f in GROUPINGS[r['grouping']]))
        baseline_items=baseline_groups[key]
        base_cost={k:sum(t[k] for t in baseline_items) for k in METRICS}
        header={k:r[k] for k in ('scope','source_experiment_id','grouping',*DIMENSIONS,'n_pairs')}
        if key not in seen:
            seen.add(key)
            successes=r['n_pairs']-r['baseline_L3_failure']
            workflows.append(dict(**header,intervention='baseline',final_L3_success=successes,
                generation_rounds=len(baseline_items),**base_cost,
                tokens_per_final_success=base_cost['total_tokens']/successes if successes else '',
                seconds_per_final_success=base_cost['elapsed_sec']/successes if successes else ''))
        cost={k:r['cost_'+k]+(base_cost[k] if r['cost_kind']=='repair_additional' else 0) for k in METRICS}
        successes=r['final_L3_success']
        workflows.append(dict(**header,intervention=r['intervention'],final_L3_success=successes,
            generation_rounds=r['charged_rounds']+(len(baseline_items) if r['cost_kind']=='repair_additional' else 0),
            **cost,tokens_per_final_success=cost['total_tokens']/successes if successes else '',
            seconds_per_final_success=cost['elapsed_sec']/successes if successes else ''))
    result=dict(cost_summary=summaries,trial_costs=trials,generation_ledger=ledger,
        fd_pair_costs=cohorts,fd_cost_summary=fd_summary,workflow_summary=workflows,accounting=accounting)
    verify_costs(result)
    return result


def verify_costs(result):
    summaries=result['cost_summary'];trials=result['trial_costs']
    for r in summaries:
        if sum(r[k+'_count'] for k in ['rescued','unrescued','regressed','preserved_success'])!=r['n_pairs']:
            raise ValueError("Outcome partition mismatch")
        for metric in ['total_tokens','elapsed_sec']:
            if not math.isclose(sum(r[k+'_cost_'+metric] for k in ['rescued','unrescued','regressed','preserved_success']),r['cost_'+metric],rel_tol=1e-9,abs_tol=1e-6):
                raise ValueError("Outcome cost partition mismatch")
        if r['cost_kind']=='repair_additional' and sum(r['success_round_'+str(k)] for k in [1,2,3])!=r['rescued_count']:
            raise ValueError("Success round histogram mismatch")
    for scope,source,condition in {(r['scope'],r['source_experiment_id'],r['intervention']) for r in summaries}:
        selected=[r for r in summaries if (r['scope'],r['source_experiment_id'],r['intervention'])==(scope,source,condition)]
        total=next(r for r in selected if r['grouping']=='overall')
        for grouping in GROUPINGS:
            for metric in ['n_pairs','rescued_count','charged_rounds','cost_total_tokens','cost_elapsed_sec']:
                if not math.isclose(sum(r[metric] for r in selected if r['grouping']==grouping),total[metric],rel_tol=1e-9,abs_tol=1e-6):
                    raise ValueError("Stratum cost partition mismatch")
    for condition in INTERVENTIONS:
        total=next(r for r in summaries if r['scope']=='pooled' and r['grouping']=='overall' and r['intervention']==condition)
        source_rows=[r for r in summaries if r['scope']=='source' and r['grouping']=='overall' and r['intervention']==condition]
        chosen=[t for t in trials if t['intervention']==condition]
        for metric in ['cost_total_tokens','cost_elapsed_sec']:
            if not math.isclose(sum(t[metric] for t in chosen),total[metric],rel_tol=1e-9,abs_tol=1e-6) or not math.isclose(sum(r[metric] for r in source_rows),total[metric],rel_tol=1e-9,abs_tol=1e-6):
                raise ValueError("Trial/source cost mismatch")
    keys={(r['source_experiment_id'],r['model_spec'],r['task_id'],r['base_seed'],r['intervention'],r['round']) for r in result['generation_ledger']}
    if len(keys)!=len(result['generation_ledger']):raise ValueError("Duplicate charged generation round")
    return True


def render_report(result):
    overall=[r for r in result['cost_summary'] if r['scope']=='pooled' and r['grouping']=='overall']
    labels={'self_refine':'R','execution_feedback':'F','self_debugging':'D','preventive_spec':'P'}
    def value(v,scale=1):return '—' if v=='' else f'{v/scale:,.1f}'
    def table(grouping,scope='pooled'):
        lines=['| モデル／難度 | 条件 | 初期未達 | 救出 | 修正生成round | 追加tokens／救出 | 追加生成秒／救出 | 未救出例のtokens割合 |',
            '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        for r in result['cost_summary']:
            if r['scope']!=scope or r['grouping']!=grouping or r['cost_kind']!='repair_additional':continue
            label='／'.join(str(r[k]).removeprefix('ollama:') for k in ['source_experiment_id','model_spec','task_difficulty'] if r[k]) or '統合'
            lines.append(f"| {label} | {labels[r['intervention']]} | {r['baseline_L3_failure']} | {r['rescued_count']} | {r['charged_rounds']} | {value(r['all_cost_per_rescue_total_tokens'])} | {value(r['all_cost_per_rescue_elapsed_sec'])} | {value(r['unrescued_cost_share_total_tokens']*100 if r['unrescued_cost_share_total_tokens']!='' else '')}% |")
        return lines
    a=result['accounting']
    cohort_counts=Counter(r['cohort'] for r in result['fd_pair_costs'])
    text=['# 修正介入の救出と追加生成コスト','',
        'R＝自己見直し、F＝実行結果提示、D＝自己デバッグ。修正コストは共有初期生成のround 0を除き、round 1以降のtokensとelapsed_secを足した。金銭単価は未設定のため、円・ドルへの換算は行わない。時間はLLM要求の計測時間で、コード評価、解析、プロセス全体の経過時間を含まない。','',
        '「追加コスト／救出」は未救出例に費やした追加分も含む全修正コストを救出件数で割る。「救出例だけの平均」は成功例の修正分だけを割るため、両者を区別する。分母0の率・平均は空欄。未救出にも部分改善があるため、そのコストを無価値と断定しない。','',
        '## 全体の修正コスト','',*table('overall'),'','## 成功までの修正回数','',
        '| 条件 | round 1で救出 | round 2で救出 | round 3で救出 | 救出例の平均修正回数 | 救出例だけの平均追加tokens | 救出例だけの平均追加秒 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in overall:
        if r['cost_kind']=='repair_additional':
            text.append('| '+' | '.join([labels[r['intervention']],*[str(r['success_round_'+str(k)]) for k in [1,2,3]],value(r['mean_success_round_of_rescues']),value(r['rescued_only_mean_cost_total_tokens']),value(r['rescued_only_mean_cost_elapsed_sec'])])+' |')
    text+=['','## モデル別','',*table('model'),'','## 難度別','',*table('difficulty'),'','## モデルと難度の組合せ','',*table('model_difficulty'),'','## 元実験別','',*table('overall',scope='source'),'','## FとDの対応付きコスト比較','',
        '| 対応組の結果 | 組数 | F平均追加tokens | D平均追加tokens | F平均追加秒 | D平均追加秒 | F平均修正回数 | D平均修正回数 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in result['fd_cost_summary']:
        if r['scope']=='pooled' and r['grouping']=='overall':
            text.append('| '+' | '.join([r['cohort'],str(r['n_pairs']),*[value(r['mean_'+k]) for k in ['F_cost_tokens','D_cost_tokens','F_cost_sec','D_cost_sec','F_charged_rounds','D_charged_rounds']]])+' |')
    text+=['',f"feedback_onlyとdebugging_onlyは前段と同じ各{cohort_counts['feedback_only']}件・{cohort_counts['debugging_only']}件の対応組。both_rescuedは両条件で救出した{cohort_counts['both_rescued']}件、neither_rescuedは両条件とも未達の{cohort_counts['neither_rescued']}件。initial_successは初期成功により両条件とも無修正終了した{cohort_counts['initial_success']}件。条件の後続コードが異なり、成功時に早期停止するため、時間差を生成速度やプロンプトの単一要素だけへ帰属させない。",'',
        '## Pの独立生成コスト','',
        '| 記録件数 | 生成tokens | 生成時間（時間） | L3成功 | baseline失敗からの救出 | baseline成功からの退行 | 生成tokens／L3成功 |',
        '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    p=next(r for r in overall if r['intervention']=='preventive_spec')
    text.append('| '+' | '.join([str(p['n_pairs']),str(p['cost_total_tokens']),value(p['cost_elapsed_sec'],3600),str(p['final_L3_success']),str(p['rescued_count']),str(p['regressed_count']),value(p['cost_per_final_success_total_tokens'])])+' |')
    text+=['','Pは別プロンプトから1回生成する代替条件であり、共有初期コードへの追加修正ではない。Pの全生成コストをR/F/Dの追加コストと同じものとして順位付けしない。CSVにはPの初期失敗・成功別のコストも残す。','',
        '## 一つの条件を選ぶ場合のワークフロー全体','',
        'R/F/Dは共有初期生成を各行に1回だけ加え、BとPは各々の独立した初回生成だけを数える。初期成功も含む全体のL3成功で割るため、追加コスト／救出とは分母が異なる。各行は別々の選択肢であり、行を合計しない。モデル・難度・出典別の同じ計算はworkflow_summary.csvに保存する。','',
        '| 条件 | L3成功 | 生成round | 全生成tokens | 全生成時間（時間） | tokens／L3成功 | 秒／L3成功 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in result['workflow_summary']:
        if r['scope']=='pooled' and r['grouping']=='overall':
            text.append('| '+' | '.join([labels.get(r['intervention'],'B'),str(r['final_L3_success']),str(r['generation_rounds']),f"{r['total_tokens']:,}",value(r['elapsed_sec'],3600),value(r['tokens_per_final_success']),value(r['seconds_per_final_success'])])+' |')
    text+=['',
        '## 共有初期生成の重複除外','',
        f"保存された{a['stored_round_rows']:,}行のround履歴から、共有初期生成の重複{a['duplicated_initial_round_rows']:,}行を除くと、記録された生成roundは{a['unique_recorded_generation_rounds']:,}回となる。これはHTTP要求の総数ではなく、成功した再試行を含む生成roundの数。baselineを各組1回、Pを1回、各修正条件のround 1以降を1回ずつ数えた。",'',
        f"再接続後に結果を保存した生成roundは{a['generation_rounds_with_recovery']}回、記録された接続再試行は計{a['recorded_connection_retries']}回。elapsed_secにはこれらの要求時間・待機も含まれる。tokensは保存された応答の使用量で、失敗した要求ごとのtokensやサーバの実計算量を完全には表さない。",'',
        f"重複除外後の全生成コストは{a['unique_generation_totals']['total_tokens']:,} tokens、{a['unique_generation_totals']['elapsed_sec']/3600:.2f}時間。これは初期生成・P・全修正条件を実際に試した実験の記録合計であり、単一介入を選んだ場合の所要時間ではない。",'',
        '## 限界と出典','',
        'schema 2.0/2.1の診断文処理差、seedブロック、実施時期、共有サーバ負荷・モデルロード・接続回復の影響を含む。tokensはモデルごとのtokenizerに依存する。統合・モデル間の数値から一般的な効率の優劣や統計的有意差を断定しない。実験間の内訳と同一モデル内の対応付き比較を参照する。','',
        '[F/D救出例の比較](../feedback_debugging_discordant_20261013/findings.md)と同じ固定出典を使用した。生データ・評価値を保持し、追加生成・再評価は行わない。manifest.json、accounting.json、sanity_report.json、CSVに出典と照合結果を保存する。','',
        'cost_summary.csvは統合と出典別のモデル・難度・seedブロック・失敗類型別集計、trial_costs.csvは条件ごとの集計対象roundの合計、generation_ledger.csvは重複を除いた生成roundの台帳、fd_pair_costs.csvとfd_cost_summary.csvはF/D対応組の比較。生成コード・生の例外メッセージを含めない。','',
        '```bash','.venv/bin/python -m scripts.analyze_repair_costs \\',
        '  --source-manifest docs/analysis/feedback_debugging_discordant_20261013/manifest.json \\',
        '  --out-dir docs/analysis/<新しい保存先>','```','']
    return '\n'.join(text)


def write_cost_analysis(source_manifest,output,root=Path.cwd()):
    source_manifest,output,root=Path(source_manifest),Path(output),Path(root)
    if output.exists():raise ValueError('Use a new analysis directory')
    previous=json.loads(source_manifest.read_text())
    snapshot_path=root/previous['fixed_snapshot']
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest()!=previous['snapshot_sha256']:raise ValueError('Snapshot hash changed')
    for artifact in previous['artifacts']:
        if hashlib.sha256((source_manifest.parent/artifact['path']).read_bytes()).hexdigest()!=artifact['sha256']:raise ValueError('Source artifact changed')
    snapshot=json.loads(snapshot_path.read_text());runs={r['experiment_id']:r for r in snapshot['runs']}
    if {s['experiment_id'] for s in previous['sources']}!=set(runs):raise ValueError('Source set changed')
    records=[]
    for src in previous['sources']:
        source=(root/src['source_dir']).resolve()
        if not source.is_relative_to((root/'results').resolve()):raise ValueError('Source outside results')
        raw=source/'raw.jsonl';data=raw.read_bytes();run=runs[src['experiment_id']]
        if not data.endswith(b'\n') or hashlib.sha256(data).hexdigest()!=src['raw_sha256'] or src['raw_sha256']!=run['raw_sha256']:raise ValueError('Raw hash changed')
        config=json.loads((source/'experiment_config.json').read_text())
        if config!=src['config'] or config!=run['config']:raise ValueError('Source config changed')
        if not json.loads((source/'automation_report.json').read_text())['passed'] or not verify(config,source)['passed']:raise ValueError('Unverified source')
        rows=[normalize_record(json.loads(line)) for line in data.splitlines() if line.strip()]
        levels=analyze_levels(rows)
        if len(rows)!=run['records'] or any(levels[k]!=run[k] for k in levels):raise ValueError('Fixed evaluations changed')
        if raw.read_bytes()!=data:raise ValueError('Raw changed while reading')
        records.extend(rows)
    result=analyze_costs(records)
    total=previous['overlap_counts']
    counts=Counter(r['cohort'] for r in result['fd_pair_costs'])
    if any(counts[k]!=total[k] for k in ['both_rescued','feedback_only','debugging_only','neither_rescued']):raise ValueError('F/D cohort mismatch')
    output.mkdir(parents=True);artifacts=[]
    for name,rows in result.items():
        if name=='accounting':
            p=output/'accounting.json';p.write_text(json.dumps(rows,indent=2)+'\n')
        else:
            p=output/(name+'.csv');_write(p,rows,list(rows[0]))
        artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    p=output/'README.md';p.write_text(render_report(result));artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    m=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),analysis_version='repair_costs_v1',
        analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_analysis_manifest=str(source_manifest),source_manifest_sha256=hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        fixed_snapshot=previous['fixed_snapshot'],snapshot_sha256=previous['snapshot_sha256'],sources=previous['sources'],
        records=len(records),artifacts=artifacts,generated_new_code=False,reevaluated_generated_code=False,
        time_definition='Generation request elapsed_sec; includes connection retry waits, excludes evaluator runtime.',
        pricing='Not configured; no monetary cost conversion.')
    (output/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    (output/'sanity_report.json').write_text(json.dumps(dict(passed=True,source_hashes_unchanged=True,sources_reverified=True,
        fixed_evaluations_match=True,record_round_costs_match=True,shared_initial_costs_match=True,
        shared_initial_charged_once=True,source_and_stratum_totals_match=True,fd_cohorts_match=True),indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-manifest',required=True);parser.add_argument('--out-dir',required=True)
    args=parser.parse_args();result=write_cost_analysis(args.source_manifest,args.out_dir)
    print(json.dumps(result['accounting'],ensure_ascii=False))


if __name__=='__main__':main()
