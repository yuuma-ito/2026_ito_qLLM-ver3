"""Describe B4-versus-repair outcome gaps using saved text; no generation/scoring.

Missing finish reasons remain missing. Features describe traces, not causal effects.
"""
import ast
from collections import Counter,defaultdict
from datetime import datetime,timezone
import csv,hashlib,json
from pathlib import Path
from scripts.measurement_ban_sources import ROOT,load_sources,sha
from scripts.measurement_ban_report import write_csv
from scripts import analyze_verified_rescues as base
from harness.independent_4 import read_checkpoint

DATA=ROOT/'docs/analysis/measurement_ban_corrected_20261104'
OUT=ROOT/'docs/analysis/b4_observed_gap_20261104'
LABEL={'self_refine':'R','execution_feedback':'F','self_debugging':'D'}

def read(p):return list(csv.DictReader(p.open()))
def identity(r):return r['model_spec'],r['task_id'],int(r['base_seed'])
def ast_hash(code):
    try:return hashlib.sha256(ast.dump(ast.parse(code),include_attributes=False).encode()).hexdigest()
    except (SyntaxError,ValueError):return None

def flags(code):
    out={k:False for k in ['legacy_Aer_import','legacy_execute_import','wrong_QFT_import','AerSimulator_import']}
    try:tree=ast.parse(code)
    except (SyntaxError,ValueError):return out
    for n in ast.walk(tree):
        if isinstance(n,ast.ImportFrom):
            names={a.name for a in n.names}
            out['legacy_Aer_import']|=n.module=='qiskit' and 'Aer' in names
            out['legacy_execute_import']|=n.module=='qiskit' and 'execute' in names
            out['wrong_QFT_import']|=n.module=='qiskit.circuit' and 'QFT' in names
            out['AerSimulator_import']|=n.module in ['qiskit_aer','qiskit_aer.simulators'] and 'AerSimulator' in names
    return out

def analyze(paths):
    cases=[];attempts=[];groups=defaultdict(dict)
    for key,rr in sorted(paths.items()):
        model,task,seed,c=key
        if rr[0]['success']:continue
        assert [r['round'] for r in rr]==list(range(len(rr))) and len(rr)<=4
        assert not any(r['success'] for r in rr[:-1])
        groups[(model,task,seed)][c]=rr
        hs=[r['hash'] for r in rr];ah=[ast_hash(r['code']) for r in rr]
        additional=rr[1:]
        initial_flags=flags(rr[0]['code']);final_flags=flags(rr[-1]['code'])
        case={'model_spec':model,'task_id':task,'base_seed':seed,'condition':c,'initial_error':rr[0]['error'],
              'success':rr[-1]['success'],'stop_round':rr[-1]['round'],'additional_requests':len(additional),
              'tokens_in':sum(r['tokens_in'] for r in additional),'tokens_out':sum(r['tokens_out'] for r in additional),
              'known_finish_requests':sum(r['finish'] is not None for r in additional),
              'known_length_requests':sum(r['finish']=='length' for r in additional),
              'output_cap_requests':sum(r['tokens_out']==1024 for r in additional),
              'has_exact_repeat':any(hs[i] in hs[:i] for i in range(1,len(rr))),
              'has_ast_repeat':any(ah[i] is not None and ah[i] in ah[:i] for i in range(1,len(rr))),
              'all_rounds_same_ast':ah[0] is not None and all(h==ah[0] for h in ah),
              'all_rounds_same_error':len({r['error'] for r in rr})==1,'final_error':rr[-1]['error'],
              **{'initial_'+k:v for k,v in initial_flags.items()},**{'final_'+k:v for k,v in final_flags.items()}}
        cases.append(case)
        for i,r in enumerate(additional,1):
            attempts.append({'model_spec':model,'task_id':task,'base_seed':seed,'condition':c,'round':i,
                'success':r['success'],'error':r['error'],'tokens_in':r['tokens_in'],'tokens_out':r['tokens_out'],
                'finish_reason':r['finish'] or 'not_recorded','reached_output_cap':r['tokens_out']==1024,
                'exact_repeat':hs[i] in hs[:i],'ast_repeat':ah[i] is not None and ah[i] in ah[:i],
                'code_sha256':hs[i],'previous_code_sha256':hs[i-1],**flags(r['code'])})
    assert len(groups)==545 and all(set(g)=={'R','F','D','B4'} for g in groups.values())
    for g in groups.values():
        if len({r[0]['hash'] for r in g.values()})!=1 or len({r[0]['error'] for r in g.values()})!=1:
            raise ValueError('shared initial differs')
    matched=[]
    for key,g in sorted(groups.items()):
        for c in ['R','F','D']:
            b=g['B4'][-1]['success'];r=g[c][-1]['success']
            matched.append({'model_spec':key[0],'task_id':key[1],'base_seed':key[2],'comparator':c,
                'initial_error':g[c][0]['error'],'B4_success':b,'repair_success':r,
                'outcome':'both' if b and r else 'B4_only' if b else 'repair_only' if r else 'neither',
                'net_gap':int(b)-int(r)})
    strata=[]
    for fields in [(),('model_spec',),('task_id',),('initial_error',),('model_spec','task_id')]:
        grouping='_'.join(fields) or 'overall';gg=defaultdict(list)
        for row in matched:gg[(row['comparator'],*(row[f] for f in fields))].append(row)
        for key,rs in sorted(gg.items()):
            count=Counter(r['outcome'] for r in rs)
            strata.append({'grouping':grouping,'comparator':key[0],**dict(zip(fields,key[1:])),
                'initial_failures':len(rs),**{k:count[k] for k in ['both','B4_only','repair_only','neither']},
                'net_gap':sum(r['net_gap'] for r in rs)})
    case_map={(r['model_spec'],r['task_id'],r['base_seed'],r['condition']):r for r in cases}
    features=[]
    attrs=['has_exact_repeat','has_ast_repeat','all_rounds_same_ast','all_rounds_same_error',
           'initial_legacy_Aer_import','final_legacy_Aer_import','initial_legacy_execute_import','final_legacy_execute_import',
           'initial_wrong_QFT_import','final_wrong_QFT_import','final_AerSimulator_import']
    for c in ['R','F','D']:
        for outcome in ['all','B4_only','repair_only','both','neither']:
            rows=[r for r in matched if r['comparator']==c and (outcome=='all' or r['outcome']==outcome)]
            for cond in [c,'B4']:
                rr=[case_map[(*identity(r),cond)] for r in rows]
                features.append({'comparator':c,'outcome':outcome,'condition':cond,'groups':len(rr),
                    **{a:sum(r[a] for r in rr) for a in attrs},
                    **{a:sum(r[a] for r in rr) for a in ['additional_requests','known_finish_requests','known_length_requests','output_cap_requests','tokens_in','tokens_out']},
                    'groups_with_known_length':sum(r['known_length_requests']>0 for r in rr),
                    'groups_with_output_cap':sum(r['output_cap_requests']>0 for r in rr)})
    return cases,attempts,matched,strata,features

def main():
    manifest=json.loads((DATA/'manifest.json').read_text())
    for p,h in manifest['inputs'].items():
        if sha(ROOT/p)!=h:raise ValueError('input drift')
    data=load_sources();rr=read(DATA/'reachable_rounds.csv');paired=read(DATA/'core/paired_records.csv')
    lookup={r['record_key']:r for r in paired if r['condition_id'] in LABEL}
    suffixes={};paths=defaultdict(list)
    finishes={(r['record_key'],int(r['round'])):r['api_finish_reason'] or None for r in read(ROOT/'docs/analysis/reevaluation_followup_20261015/partial_new_rounds.csv')}
    for r in rr:
        if r['record_key'] not in lookup:continue
        row=lookup[r['record_key']];i=int(r['round']);key=(*identity(r),LABEL[row['condition_id']])
        if r['origin']=='saved_prefix':a=data['raw'][base.identity(row)][i];code=a['extracted_code'];finish=None
        else:
            if r['record_key'] not in suffixes:
                p=ROOT/'.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial'/r['record_key']/'completed.json'
                suffixes[r['record_key']]={a['round']:a for a in json.loads(p.read_text())['suffix']}
            a=suffixes[r['record_key']][i];code=a['code'];finish=finishes[(r['record_key'],i)]
        if hashlib.sha256(code.encode()).hexdigest()!=r['code_sha256']:raise ValueError('code hash drift')
        paths[key].append({'round':i,'code':code,'hash':r['code_sha256'],'error':r['new_error_category'],
            'success':r['new_L3']=='True','tokens_in':int(r['tokens_in']),'tokens_out':int(r['tokens_out']),'finish':finish})
    latest=json.loads((DATA/'followup_public_result.json').read_text())
    follow=read_checkpoint(ROOT/latest['output_dir']/'private/completed.json')
    repeat={(r['model_spec'],r['task_id'],int(r['base_seed']),int(r['round'])):r for r in read(DATA/'repetitions.csv')}
    for row in data['B4_records']:
        rounds=follow['rounds'] if row['baseline_record_key']==follow['baseline_record_key'] else row['rounds']
        for a in rounds:
            if hashlib.sha256(a['extracted_code'].encode()).hexdigest()!=a['code_sha256']:
                raise ValueError('B4 code hash drift')
            i=a['round'];r=repeat.get((*identity(row),i));success=a['primary']['L3'] if i==0 else r['L3']=='True'
            error=a['primary']['error_category'] if success==a['primary']['L3'] else 'interface_mismatch'
            paths[(*identity(row),'B4')].append({'round':i,'code':a['extracted_code'],'hash':a['code_sha256'],
                'error':error,'success':success,'tokens_in':int(a['tokens_in']),'tokens_out':int(a['tokens_out']),
                'finish':a.get('finish_reason') if i else None})
    for path in paths.values():path.sort(key=lambda r:r['round'])
    cases,attempts,matched,strata,features=analyze(paths)
    OUT.mkdir(parents=True,exist_ok=True)
    for name,rows in [('case_features',cases),('attempt_features',attempts),('matched_outcomes',matched),('gap_by_stratum',strata),('features_by_outcome',features)]:write_csv(OUT/(name+'.csv'),rows)
    assert len(cases)==545*4 and len(matched)==545*3
    actual={c:sum(r['success'] for r in cases if r['condition']==c) for c in ['R','F','D','B4']}
    assert actual=={'R':96,'F':183,'D':179,'B4':216}
    result={'created_at_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'added_successes':actual,
        'scope':'保存コードを文字列/ASTとして読む記述分析。モデル呼出・生成コード実行・再採点なし。',
        'causal_effect_identified':False,'finish_reason_limit':'R/F/D保存prefixはfinish_reason未記録。部分追試suffixだけ実測。tokens_out==1024は別の代理指標であり打切りと断定しない。',
        'code_features_limit':'AST一致はコメント・書式を除く文字構造の一致。API名特徴だけから失敗原因や意味的同値性を認定しない。',
        'inputs':{**manifest['inputs'],str((DATA/'manifest.json').relative_to(ROOT)):sha(DATA/'manifest.json'),
            **{str((DATA/n).relative_to(ROOT)):sha(DATA/n) for n in ['reachable_rounds.csv','core/paired_records.csv','repetitions.csv','followup_public_result.json']},
            str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__)),
            'tasks/t4_bv.py':sha(ROOT/'tasks/t4_bv.py')},
        'outputs':{p.name:sha(p) for p in OUT.iterdir() if p.suffix in ['.csv','.txt'] or p.name=='case_reviews.json'}}
    (OUT/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'added_successes':actual,'overall_gaps':[r for r in strata if r['grouping']=='overall'],'output':str(OUT)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
