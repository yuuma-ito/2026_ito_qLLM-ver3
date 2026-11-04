"""Render WiNF tables from the measurement-only corrected public snapshot."""
from pathlib import Path
import csv,hashlib,json

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
DATA=ROOT/'docs/analysis/measurement_ban_corrected_20261104'

def read(name):return list(csv.DictReader((DATA/name).open()))
def main():
    rows=read('summary.csv');snapshot=json.loads((DATA/'results_snapshot.json').read_text())
    def row(c,grouping='overall',group='all'):
        rr=[r for r in rows if r['condition']==c and r['generation_cap']=='4' and r['grouping']==grouping and r['group']==group]
        if len(rr)!=1:raise ValueError((c,grouping,group))
        return rr[0]
    tables=[]
    def table(caption,label,headers,body):
        tables.extend([r'\begin{table}[tb]',r'\centering',r'\caption{'+caption+'}',r'\label{tab:'+label+'}',r'\begin{tabular}{l'+'r'*(len(headers)-1)+'}',r'\hline',' & '.join(headers)+r' \\',r'\hline',*[' & '.join(map(str,r))+r' \\' for r in body],r'\hline',r'\end{tabular}',r'\end{table}',''])
    models=[('G3','ollama:gemma3:4b'),('G4','ollama:gemma4:e4b-it-qat'),('C7','ollama:qwen2.5-coder:7b'),('Q4','ollama:qwen3.5:4b'),('Q9','ollama:qwen3.5:9b')]
    errors=[('回路構築','build_error'),('import','import_error'),('IF不適合','interface_mismatch'),('量子ビット数','qubit_count_mismatch'),('構文','syntax'),('実行時（未定義変数）','unknown_error'),('出力不一致','wrong_output')]
    for label,caption,grouping,names in [('model','モデル別の初期失敗数と追加成功数','model',models),('error','初期失敗類型別の追加成功数','initial_failure',errors)]:
        table(caption,label,['区分','分母','R','F','D','B4'],[[name,row('B4',grouping,key)['initial_failures'],*[row(c,grouping,key)['successes_from_initial_failure'] for c in ['R','F','D','B4']]] for name,key in names])
    table('F/Dの救済対象（初期失敗545組）','overlap',['共通','Fのみ','Dのみ','双方未救済'],[[snapshot['primary']['fd_overlap'][k] for k in ['both','F_only','D_only','neither']]])
    costs={r['condition_id']:r for r in snapshot['overall_costs'] if r['cap']==3}
    conditions=[('R','self_refine'),('F','execution_feedback'),('D','self_debugging')]
    table('修正追加コスト（未救済への消費も含む）','cost',['条件',r'保存$10^3$tok',r'新$10^3$tok','tok/救済','秒/救済'],[[c,f"{costs[k]['saved_prefix_tokens']/1000:.1f}",f"{costs[k]['new_suffix_tokens']/1000:.1f}",f"{costs[k]['tokens_per_rescue']:,.1f}",f"{costs[k]['seconds_per_rescue']:,.1f}"] for c,k in conditions])
    third={r['condition_id']:r for r in snapshot['third_round']}
    table('3回目の追加救済・消費と2回打切り時の損失','third',['条件','追加/未救済','千tok','要求時間h','失う割合'],[[c,f"{third[k]['additional_rescues']}/{third[k]['at_risk_after_2']}",f"{third[k]['third_round_tokens']/1000:.1f}",f"{third[k]['third_round_seconds']/3600:.2f}",f"{third[k]['loss_if_stop_at_2']*100:.1f}"+r'\%'] for c,k in conditions])
    (HERE/'tables_20261104.tex').write_text('% Measurement-only correction; sources: results_snapshot_20261104.json\n'+'\n'.join(tables).rstrip()+'\n')
    files=[DATA/n for n in ['summary.csv','pairwise.csv','overlap.csv','sanity_report.json','manifest.json','results_snapshot.json','followup_manifest.json','followup_public_result.json']]
    result={'updated_at_utc':snapshot['captured_at_utc'],'scope':'測定禁止修正版。旧固定集計を保持しB4の必要1経路を追加1要求408tokensで継続。資料生成自体はモデル呼出0。','reachable_source':str(DATA.relative_to(ROOT)),'B4_experiment_id':'independent_4_full_20261020T185811381595Z','initial_groups':1000,'initial_successes':455,'initial_failures':545,'overall':{c:row(c) for c in ['R','F','D','B4']},'B4_model_rows':[row('B4','model',key) for _,key in models],'B4_error_rows':[row('B4','initial_failure',key) for _,key in errors],'B4_pairwise':read('pairwise.csv'),'followup':snapshot['followup'],'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (HERE/'results_snapshot_20261104.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
