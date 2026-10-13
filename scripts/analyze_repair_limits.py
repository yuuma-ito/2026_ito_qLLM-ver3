"""Replay saved repair prefixes; do not generate or re-evaluate any code."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path

from scripts.analyze_reach_levels import REPAIRS
from scripts.analyze_repair_costs import DIMENSIONS, GROUPINGS, METRICS, equal_cost, round_cost
from scripts.analyze_interventions import _write
from scripts.automate_experiment import verify


def key(row):
    return (row['source_experiment_id'],row['model_spec'],row['task_id'],row['base_seed'])


def analyze_limits(trials, ledger):
    """Require complete three-round histories or early stopping at L3 success."""
    baseline={};repair={};seen=set()
    for item in ledger:
        round_cost(item)
        identity=(*key(item),item['intervention'],item['round'])
        if identity in seen:raise ValueError('Duplicate generation round')
        seen.add(identity)
        if item['intervention']=='baseline':
            if item['round']!=0 or key(item) in baseline:raise ValueError('Invalid baseline round')
            baseline[key(item)]=item
    for trial in trials:
        identity=(*key(trial),trial['intervention'])
        if identity in repair:raise ValueError('Duplicate condition trial')
        repair[identity]=trial
        if type(trial['baseline_L3']) is not bool or type(trial['final_L3']) is not bool:
            raise ValueError('Outcome must be boolean')
    if not baseline:raise ValueError('No baseline trials')
    for identity in baseline:
        paired=[repair.get((*identity,c)) for c in (*REPAIRS,'preventive_spec')]
        if any(r is None for r in paired):raise ValueError('Incomplete condition set')
        first=paired[0]
        if any(r['baseline_L3']!=first['baseline_L3'] or any(r[d]!=first[d] for d in DIMENSIONS) for r in paired):
            raise ValueError('Baseline metadata mismatch')
    if any(key(r) not in baseline for r in trials) or any(key(r) not in baseline for r in ledger):
        raise ValueError('Unexpected source identity')
    rounds=defaultdict(list)
    for item in ledger:
        if item['intervention'] in REPAIRS:
            if item['round']<1:raise ValueError('Shared round 0 must not be charged as repair')
            rounds[(*key(item),item['intervention'])].append(item)
    prefixes=[];rescues=[]
    for identity,trial in sorted(repair.items()):
        condition=trial['intervention']
        if condition not in REPAIRS:continue
        items=sorted(rounds[identity],key=lambda r:r['round'])
        success=trial['first_success_round']
        if trial['baseline_L3']:
            if items or not trial['final_L3'] or success!=0:raise ValueError('Initial success was repaired')
        else:
            expected=success if trial['final_L3'] else 3
            if trial['final_L3'] and not 1<=success<=3:raise ValueError('Invalid repair success round')
            if not trial['final_L3'] and success!=-1:raise ValueError('Failed trial has success round')
            if [r['round'] for r in items]!=list(range(1,expected+1)):
                raise ValueError('Incomplete or post-success repair history')
        totals={k:sum(r[k] for r in items) for k in METRICS}
        if len(items)!=trial['charged_rounds'] or not equal_cost(totals,{k:trial['cost_'+k] for k in METRICS}):
            raise ValueError('Trial cost differs from ledger')
        initial=baseline[key(trial)]
        for cap in range(4):
            charged=[r for r in items if r['round']<=cap]
            added=[r for r in items if r['round']==cap]
            rescued=not trial['baseline_L3'] and 0<success<=cap
            row={k:trial[k] for k in ('source_experiment_id','model_spec','task_id','base_seed',*DIMENSIONS[1:],'intervention')}
            row.update(cap=cap,n_pairs=1,initial_success=int(trial['baseline_L3']),
                baseline_failure=int(not trial['baseline_L3']),rescued=int(rescued),
                final_success=int(trial['baseline_L3'] or rescued),unrescued=int(not trial['baseline_L3'] and not rescued),
                charged_rounds=len(charged),marginal_attempted=int(bool(added)),
                marginal_rescued=int(not trial['baseline_L3'] and success==cap and cap>0))
            for metric in METRICS:
                row['cost_'+metric]=sum(r[metric] for r in charged)
                row['marginal_cost_'+metric]=sum(r[metric] for r in added)
                row['workflow_'+metric]=initial[metric]+row['cost_'+metric]
            prefixes.append(row)
        if not trial['baseline_L3'] and trial['final_L3']:
            rescues.append(dict(**{k:trial[k] for k in ('source_experiment_id','model_spec','task_id','base_seed','task_difficulty','seed_block','baseline_error_category','intervention')},
                first_success_round=success,cumulative_tokens=totals['total_tokens'],cumulative_sec=totals['elapsed_sec'],
                successful_round_tokens=items[-1]['total_tokens'],successful_round_sec=items[-1]['elapsed_sec']))
    groups=defaultdict(list)
    for row in prefixes:
        for scope,source in [('source',row['source_experiment_id']),('pooled','')]:
            for grouping,fields in GROUPINGS.items():
                groups[(scope,source,grouping,row['intervention'],row['cap'],tuple(row[f] for f in fields))].append(row)
    summaries=[]
    additive=('n_pairs','initial_success','baseline_failure','rescued','final_success','unrescued','charged_rounds',
              'marginal_attempted','marginal_rescued',*[p+k for p in ('cost_','marginal_cost_','workflow_') for k in METRICS])
    for (scope,source,grouping,condition,cap,values),items in sorted(groups.items()):
        row=dict(scope=scope,source_experiment_id=source,grouping=grouping,**dict.fromkeys(DIMENSIONS,''),intervention=condition,cap=cap)
        row.update(zip(GROUPINGS[grouping],values))
        row.update({k:sum(r[k] for r in items) for k in additive})
        row['rescue_rate']=row['rescued']/row['baseline_failure'] if row['baseline_failure'] else ''
        row['marginal_rescue_rate']=row['marginal_rescued']/row['marginal_attempted'] if row['marginal_attempted'] else ''
        for metric in ('total_tokens','elapsed_sec'):
            row['cost_per_cumulative_rescue_'+metric]=row['cost_'+metric]/row['rescued'] if row['rescued'] else ''
            row['marginal_cost_per_new_rescue_'+metric]=row['marginal_cost_'+metric]/row['marginal_rescued'] if row['marginal_rescued'] else ''
        summaries.append(row)
    result=dict(cap_summary=summaries,cap_trials=prefixes,rescued_at_round=rescues)
    verify_limits(result)
    return result


def verify_limits(result):
    summaries=result['cap_summary'];additive=['n_pairs','initial_success','baseline_failure','rescued','charged_rounds','marginal_attempted','marginal_rescued','cost_total_tokens','cost_elapsed_sec','marginal_cost_total_tokens','marginal_cost_elapsed_sec','workflow_total_tokens','workflow_elapsed_sec']
    chains=defaultdict(dict)
    for row in summaries:
        if row['initial_success']+row['baseline_failure']!=row['n_pairs'] or row['rescued']+row['unrescued']!=row['baseline_failure'] or row['initial_success']+row['rescued']!=row['final_success']:
            raise ValueError('Outcome partition mismatch')
        chains[(row['scope'],row['source_experiment_id'],row['grouping'],row['intervention'],tuple(row[k] for k in DIMENSIONS))][row['cap']]=row
    for caps in chains.values():
        if set(caps)!={0,1,2,3}:raise ValueError('Missing cap')
        if caps[0]['rescued'] or caps[0]['cost_total_tokens'] or caps[0]['cost_elapsed_sec']:raise ValueError('Cap 0 has repair cost')
        for cap in [1,2,3]:
            before,after=caps[cap-1],caps[cap]
            if after['rescued']-before['rescued']!=after['marginal_rescued'] or after['charged_rounds']-before['charged_rounds']!=after['marginal_attempted']:
                raise ValueError('Marginal outcome mismatch')
            if after['marginal_attempted']!=before['unrescued']:raise ValueError('At-risk denominator mismatch')
            for metric in METRICS:
                if not math.isclose(after['cost_'+metric]-before['cost_'+metric],after['marginal_cost_'+metric],rel_tol=1e-9,abs_tol=1e-6):
                    raise ValueError('Marginal cost mismatch')
    for scope,source,condition,cap in {(r['scope'],r['source_experiment_id'],r['intervention'],r['cap']) for r in summaries}:
        selected=[r for r in summaries if (r['scope'],r['source_experiment_id'],r['intervention'],r['cap'])==(scope,source,condition,cap)]
        total=next(r for r in selected if r['grouping']=='overall')
        for grouping in GROUPINGS:
            for k in additive:
                if not math.isclose(sum(r[k] for r in selected if r['grouping']==grouping),total[k],rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Stratum partition mismatch')
    for condition in REPAIRS:
        for cap in range(4):
            total=next(r for r in summaries if r['scope']=='pooled' and r['grouping']=='overall' and r['intervention']==condition and r['cap']==cap)
            sources=[r for r in summaries if r['scope']=='source' and r['grouping']=='overall' and r['intervention']==condition and r['cap']==cap]
            for k in additive:
                if not math.isclose(sum(r[k] for r in sources),total[k],rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Source partition mismatch')
    return True


def render_report(result):
    names={'self_refine':'R','execution_feedback':'F','self_debugging':'D'}
    def val(n):return '—' if n=='' else f'{n:,.1f}'
    def cumulative(grouping,scope='pooled'):
        lines=['| モデル／難度／出典 | 条件 | 上限 | 初期未達 | 累積救出 | 累積救出率 | 累積追加tokens | 累積追加時間（時間） | 最終L3成功 |',
            '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        for r in result['cap_summary']:
            if r['scope']!=scope or r['grouping']!=grouping or r['cap']==0:continue
            label='／'.join(str(r[k]).removeprefix('ollama:') for k in ['source_experiment_id','model_spec','task_difficulty'] if r[k]) or '統合'
            lines.append('| '+' | '.join([label,names[r['intervention']],str(r['cap']),str(r['baseline_failure']),str(r['rescued']),val(r['rescue_rate']*100 if r['rescue_rate']!='' else '')+'%',f"{r['cost_total_tokens']:,}",val(r['cost_elapsed_sec']/3600),str(r['final_success'])])+' |')
        return lines
    content=['# 修正上限1回 2回 3回の救出と追加コスト','',
        '保存済みの最大3回修正の履歴を各上限で区切り、L3救出数とround 1以降の生成コストを再集計した。同じ記録の途中までを使った比較であり、上限を変更した新しい実験は行っていない。上限0は共有初期生成のみ、1・2・3は修正回数の上限を表す。初期L3成功例は無修正で保持し、成功して終了済みの例に存在しない後続roundを補わない。','',
        '累積救出率は初期未達を分母とする。各roundの限界救出率は、そのround直前まで未達で実際に修正を行った組数を分母とする。「限界追加コスト／新規救出」は、そのroundで未救出だった例のコストも含む。上限別の行は同じ履歴を共有するため、足して独立標本数や実験費用を計算しない。','',
        '## 全体の上限別比較','',*cumulative('overall'),'','## 2回目 3回目で増えた救出とコスト','',
        '| 条件 | 修正round | 直前まで未達 | 新規救出 | 限界救出率 | 当該round追加tokens | 当該round追加時間（時間） | tokens／新規救出 | 秒／新規救出 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for r in result['cap_summary']:
        if r['scope']=='pooled' and r['grouping']=='overall' and r['cap']>0:
            content.append('| '+' | '.join([names[r['intervention']],str(r['cap']),str(r['marginal_attempted']),str(r['marginal_rescued']),val(r['marginal_rescue_rate']*100 if r['marginal_rescue_rate']!='' else '')+'%',f"{r['marginal_cost_total_tokens']:,}",val(r['marginal_cost_elapsed_sec']/3600),val(r['marginal_cost_per_new_rescue_total_tokens']),val(r['marginal_cost_per_new_rescue_elapsed_sec'])])+' |')
    content+=['','## モデル別','',*cumulative('model'),'','## 難度別','',*cumulative('difficulty'),'','## 元実験別','',*cumulative('overall',scope='source'),'','## 解釈と制約','',
        '追加roundが救出した件数と追加コストを併記して、どこまで修正するかの検討材料とする。少数分母や救出0件の層では、コスト／救出は定義できず空欄とする。初期未達の割合はモデル・難度・出典で異なり、全体の傾向をすべての層へ適用しない。部分改善や段階低下はこの救出コスト指標には含まれず、前段の到達水準分析と合わせて解釈する。','',
        '時間は保存されたLLM要求のelapsed_secであり、評価器・解析の実行時間を含まない。接続回復待機、共有サーバ負荷、モデルロード、診断文処理差、実施時期とseedブロックの影響を含む。一般的な最適上限・優劣・統計的有意差は断定しない。','',
        'Pは独立した1回の初期生成であり、この修正上限比較の対象外。[Pを含む生成コスト分析](../repair_costs_20261013/findings.md)では救出・退行・全生成費用を別に保存している。','',
        '## 出典と再現','',
        '[検証済みコスト分析](../repair_costs_20261013/README.md)のtrial_costs.csvとgeneration_ledger.csvを使用した。元rawのhashと保存設定、固定出典、親成果物のhashを照合し、上限3の結果が前段の救出数・コスト・ワークフロー全体と一致することを検証した。新規生成・生成コードの再評価・元記録の変更は行っていない。','',
        'cap_summary.csvは統合・出典別の全8区分、cap_trials.csvは各対応組の上限別結果、rescued_at_round.csvは救出した例の初回成功roundと観測コストを保存する。モデル×難度、seedブロック、失敗類型別の限界コストもcap_summary.csvで確認できる。共有初期生成（初期失敗も含む）のコストを1回加えたworkflow列は、単一条件を選ぶ場合の全体コストであり、修正追加分と区別する。','',
        '```bash','.venv/bin/python -m scripts.analyze_repair_limits \\',
        '  --cost-manifest docs/analysis/repair_costs_20261013/manifest.json \\',
        '  --out-dir docs/analysis/<新しい保存先>','```','']
    return '\n'.join(content)


def read_csv(path,boolean_fields=()):
    integer_fields={'base_seed','round','connection_retries','first_success_round','charged_rounds','cost_tokens_in','cost_tokens_out','cost_total_tokens','tokens_in','tokens_out','total_tokens'}
    float_fields={'elapsed_sec','cost_elapsed_sec'}
    with path.open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.DictReader(handle))
    for row in rows:
        for k in integer_fields&row.keys():row[k]=int(row[k])
        for k in float_fields&row.keys():row[k]=float(row[k])
        for k in boolean_fields:
            if row[k] not in ('True','False'):raise ValueError('Invalid boolean field')
            row[k]=row[k]=='True'
    return rows


def write_limit_analysis(cost_manifest,output,root=Path.cwd()):
    cost_manifest,output,root=Path(cost_manifest),Path(output),Path(root)
    if output.exists():raise ValueError('Use a new analysis directory')
    previous=json.loads(cost_manifest.read_text());snapshot_path=root/previous['fixed_snapshot']
    if hashlib.sha256(snapshot_path.read_bytes()).hexdigest()!=previous['snapshot_sha256']:raise ValueError('Fixed snapshot changed')
    snapshot=json.loads(snapshot_path.read_text());runs={r['experiment_id']:r for r in snapshot['runs']}
    if {s['experiment_id'] for s in previous['sources']}!=set(runs):raise ValueError('Source set changed')
    for artifact in previous['artifacts']:
        if hashlib.sha256((cost_manifest.parent/artifact['path']).read_bytes()).hexdigest()!=artifact['sha256']:raise ValueError('Cost artifact changed')
    for src in previous['sources']:
        source=(root/src['source_dir']).resolve()
        if not source.is_relative_to((root/'results').resolve()):raise ValueError('Source outside results')
        run=runs[src['experiment_id']];config=json.loads((source/'experiment_config.json').read_text())
        if config!=src['config'] or config!=run['config']:raise ValueError('Source configuration changed')
        if hashlib.sha256((source/'raw.jsonl').read_bytes()).hexdigest()!=src['raw_sha256'] or src['raw_sha256']!=run['raw_sha256']:raise ValueError('Raw hash changed')
        if not json.loads((source/'automation_report.json').read_text())['passed'] or not verify(config,source)['passed']:raise ValueError('Unverified source')
    trials=read_csv(cost_manifest.parent/'trial_costs.csv',('baseline_L3','final_L3'))
    ledger=read_csv(cost_manifest.parent/'generation_ledger.csv')
    result=analyze_limits(trials,ledger)
    prior=read_csv(cost_manifest.parent/'cost_summary.csv');workflows=read_csv(cost_manifest.parent/'workflow_summary.csv')
    summary_key=lambda r:(r['scope'],r['source_experiment_id'],r['grouping'],r['intervention'],tuple(r[k] for k in DIMENSIONS))
    lookup={summary_key(r):r for r in prior};workflow_lookup={summary_key(r):r for r in workflows}
    for row in result['cap_summary']:
        if row['cap']!=3:continue
        old=lookup[summary_key(row)];workflow=workflow_lookup[summary_key(row)]
        for new,previous_field in [('rescued','rescued_count'),('final_success','final_L3_success'),('charged_rounds','charged_rounds'),('cost_total_tokens','cost_total_tokens'),('cost_elapsed_sec','cost_elapsed_sec')]:
            if not math.isclose(row[new],float(old[previous_field]),rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Cap 3 differs from full cost analysis')
        for metric in METRICS:
            if not math.isclose(row['workflow_'+metric],float(workflow[metric]),rel_tol=1e-9,abs_tol=1e-6):raise ValueError('Workflow endpoint mismatch')
    output.mkdir(parents=True);artifacts=[]
    for name,rows in result.items():
        p=output/(name+'.csv');fields=list(rows[0]) if rows else ['source_experiment_id','intervention','first_success_round']
        _write(p,rows,fields);artifacts.append(dict(path=p.name,rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    p=output/'README.md';p.write_text(render_report(result));artifacts.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    manifest=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),analysis_version='repair_limits_v1',
        analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cost_manifest=str(cost_manifest),cost_manifest_sha256=hashlib.sha256(cost_manifest.read_bytes()).hexdigest(),
        fixed_snapshot=previous['fixed_snapshot'],snapshot_sha256=previous['snapshot_sha256'],sources=previous['sources'],
        records=previous['records'],caps=[0,1,2,3],artifacts=artifacts,generated_new_code=False,reevaluated_generated_code=False,
        interpretation='Observed prefix replay, not new experiments under different limits.')
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (output/'sanity_report.json').write_text(json.dumps(dict(passed=True,sources_reverified=True,source_hashes_unchanged=True,
        cost_artifacts_match=True,complete_repair_histories=True,marginal_costs_and_rescues_match=True,
        source_and_stratum_totals_match=True,cap3_matches_full_costs=True,workflow_endpoint_matches=True),indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cost-manifest',required=True);parser.add_argument('--out-dir',required=True)
    args=parser.parse_args();result=write_limit_analysis(args.cost_manifest,args.out_dir)
    for r in result['cap_summary']:
        if r['scope']=='pooled' and r['grouping']=='overall':
            print(json.dumps({k:r[k] for k in ['intervention','cap','rescued','cost_total_tokens','cost_elapsed_sec','marginal_rescued']},ensure_ascii=False))


if __name__=='__main__':main()
