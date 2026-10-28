"""Scientific thesis figures from frozen aggregates; no model/code execution.

Matplotlib exports PDF/SVG for standalone use and 360-dpi PNG for Office.
Run: PYTHONPATH=.cache/graduation_plot_tools:.cache/graduation_tools .venv/bin/python docs/graduation2026/thesis_figures.py
"""
from pathlib import Path
import csv
import hashlib
import json
import os
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIG_DIR = HERE/'figures'
DATA = ROOT/'docs/analysis/independent_4_completed_20261022/summary.csv'
OVERLAP = ROOT/'docs/analysis/reachable_rescues_20261016/core/fd_overlap_summary.csv'
SNAPSHOT = ROOT/'docs/presentation_sources/20261016T_reachable_rescues/results_snapshot.json'
FIGURES = [
    {'number':1, 'stem':'experiment_flow', 'caption':'共有初期コードを起点とする比較手順', 'width_mm':160},
    {'number':2, 'stem':'additional_success_rates', 'caption':'初期失敗545組に対する条件別の追加成功率', 'width_mm':160},
    {'number':3, 'stem':'fd_overlap', 'caption':'FとDの救済対象の重なり（初期失敗545組を排他的な4集合に分割）', 'width_mm':160},
]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def inputs():
    return {str(p.relative_to(ROOT)):digest(p) for p in [DATA,OVERLAP,SNAPSHOT,Path(__file__)]}


def values():
    rows=list(csv.DictReader(DATA.open()))
    overall={r['condition']:r for r in rows if r['grouping']=='overall' and r['group']=='all' and r['generation_cap']=='4'}
    rates=[{'condition':c,'added_successes':int(overall[c]['successes_from_initial_failure']),
            'denominator':int(overall[c]['initial_failures'])} for c in ['R','F','D','B4']]
    for r in rates:r['rate_percent']=100*r['added_successes']/r['denominator']
    overlap=next(r for r in csv.DictReader(OVERLAP.open()) if r['scope']=='pooled' and r['grouping']=='overall')
    parts={k:int(overlap[k]) for k in ['F_only','both','D_only','neither']}
    assert [r['added_successes'] for r in rates]==[96,183,180,217]
    assert sum(parts.values())==545 and parts['F_only']+parts['both']==183 and parts['D_only']+parts['both']==180
    return rates,parts


def build():
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.cache/thesis_matplotlib'))
    try:
        import matplotlib
    except ModuleNotFoundError:
        sys.path.insert(0,str(ROOT/'.cache/graduation_plot_tools'))
        import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Polygon
    plt.rcParams.update({'font.family':'IPAexGothic','font.size':11,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'path','axes.unicode_minus':False})
    FIG_DIR.mkdir(parents=True,exist_ok=True)
    rates,parts=values()
    def save(fig,stem):
        for ext in ['pdf','svg','png']:
            fig.savefig(FIG_DIR/(stem+'.'+ext),dpi=360,facecolor='white',bbox_inches='tight',pad_inches=.12)
        plt.close(fig)
    # Logical procedure, not a claim that the reconstructed cohort was newly generated.
    fig,ax=plt.subplots(figsize=(7.7,6.6));ax.set_xlim(0,136);ax.set_ylim(-10,110);ax.axis('off')
    def box(x,y,w,h,label,size=11,dashed=False):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.25,rounding_size=1',facecolor='white',edgecolor='black',linewidth=1,linestyle='--' if dashed else '-'))
        ax.text(x,y,label,ha='center',va='center',fontsize=size,linespacing=1.45)
    def arrow(points,dashed=False):
        for a,b in zip(points[:-2],points[1:-1]):ax.plot([a[0],b[0]],[a[1],b[1]],color='black',lw=1,linestyle='--' if dashed else '-')
        ax.annotate('',xy=points[-1],xytext=points[-2],arrowprops={'arrowstyle':'->','lw':1,'color':'black','linestyle':'--' if dashed else '-'})
    box(47,103,66,9,'モデル・タスク・seedを設定')
    box(47,88,66,12,'初期コード生成・L0〜L3評価\n同じ初期コードを各条件で共有')
    arrow([(47,98.5),(47,94)])
    ax.add_patch(Polygon([(47,80),(68,72),(47,64),(26,72)],facecolor='white',edgecolor='black'))
    ax.text(47,72,'初期L3成功？',ha='center',va='center',fontsize=11)
    arrow([(47,82),(47,80)])
    box(87,72,22,13,'初期成功\n455組\n無修正で保持',10.2)
    arrow([(68,72),(76,72)]);ax.text(71,74,'はい',fontsize=9)
    arrow([(47,64),(47,61)]);ax.text(50,62,'いいえ：初期失敗545組',fontsize=9.5)
    ax.plot([12,83],[59,59],color='black',lw=1);ax.plot([47,47],[61,59],color='black',lw=1)
    labels=['R 自己見直し\n前回コード','F 実行結果提示\n前回コード＋診断','D 自己デバッグ\n前回コード＋診断\n説明・原因分析','B4 独立再生成\n課題仕様のみ']
    for x,label in zip([12,35.5,59,82.5],labels):
        arrow([(x,59),(x,55)]);box(x,49,22,12,label,9.1)
        arrow([(x,43),(x,40)])
    ax.plot([12,82.5],[40,40],color='black',lw=1)
    arrow([(47,40),(47,37)])
    box(47,32,75,10,'各条件で最大3回の追加生成 → L0〜L3評価',10.5)
    ax.add_patch(Polygon([(47,24),(70,18),(47,12),(24,18)],facecolor='white',edgecolor='black'))
    ax.text(47,18,'L3成功 または 3回終了？',ha='center',va='center',fontsize=9.8)
    arrow([(47,27),(47,24)])
    arrow([(24,18),(4,18),(4,32),(9.5,32)])
    ax.text(6,23,'未成功・\n3回未満',ha='left',va='center',fontsize=8.5)
    box(50,3.5,91,10,'初期成功の保持・追加成功数・初期失敗類型・\n追加計算コストを集計',10.2)
    arrow([(47,12),(47,8.5)]);ax.text(50,10,'はい',fontsize=9)
    arrow([(98,72),(99,72),(99,3.5),(95.5,3.5)])
    # P branches before shared code generation and never enters the failed cohort.
    arrow([(80,103),(119,103),(119,96)],dashed=True)
    box(119,88,30,16,'P 生成前介入\n注意事項を追加\n独立に1回生成',9.6,dashed=True)
    arrow([(119,80),(119,74)],dashed=True)
    box(119,65,30,18,'L0〜L3評価\n全1,000組\n初期失敗に限定しない',9.4,dashed=True)
    arrow([(119,56),(119,48)],dashed=True)
    box(119,39,30,18,'Pを別集計\nBとの対応で\n改善・悪化を比較',9.4,dashed=True)
    ax.text(119,22,'点線：Pの独立経路',ha='center',fontsize=9)
    ax.text(50,-5,'R/F/D/B4は同じ初期コードを共有',ha='center',fontsize=9.5)
    fig.subplots_adjust(left=.01,right=.99,top=.99,bottom=.07)
    save(fig,'experiment_flow')
    # Zero-based axes and common denominator; grayscale and hatching for print.
    fig,ax=plt.subplots(figsize=(6.5,3.6))
    names=['R 自己見直し','F 実行結果提示','D 自己デバッグ','B4 独立再生成']
    ax.barh(range(4),[r['rate_percent'] for r in rates],height=.56,color=['.78','.55','.35','.9'],edgecolor='black',linewidth=.7,hatch=[None,None,None,'///'])
    for i,r in enumerate(rates):ax.text(r['rate_percent']+.8,i,f"{r['added_successes']}/545（{r['rate_percent']:.1f}%）",va='center',fontsize=10.5)
    ax.set_yticks(range(4),names);ax.invert_yaxis();ax.set_xlim(0,58)
    ax.set_xticks([0,10,20,30,40,50],[f'{i}%' for i in [0,10,20,30,40,50]])
    ax.set_xlabel('追加成功率（分母：初期失敗545組）');ax.grid(axis='x',color='.86',linewidth=.6);ax.set_axisbelow(True)
    ax.spines[['top','right','left']].set_visible(False);ax.tick_params(axis='y',length=0)
    fig.tight_layout();save(fig,'additional_success_rates')
    # Proportional disjoint segments represent the complete failed cohort.
    fig,ax=plt.subplots(figsize=(6.5,2.35));x=0
    for name,label,shade,hatch in [('F_only','Fのみ','.9','///'),('both','F/D共通','.5',None),('D_only','Dのみ','.75','\\\\'),('neither','双方未救済','.96',None)]:
        n=parts[name];ax.barh(.65,n,left=x,height=.38,color=shade,edgecolor='black',linewidth=.8,hatch=hatch)
        ax.annotate(f'{label}\n{n}組',xy=(x+n/2,.86),xytext=(x+n/2,1.14),ha='center',va='bottom',fontsize=10.5,arrowprops={'arrowstyle':'-','lw':.8})
        x+=n
    ax.set_xlim(0,545);ax.set_ylim(0,1.7);ax.set_yticks([]);ax.set_xticks([0,100,200,300,400,545]);ax.set_xlabel('初期失敗の組数（合計545組）')
    ax.spines[['left','right','top']].set_visible(False)
    ax.text(272.5,.1,f"片側救済：{parts['F_only']}＋{parts['D_only']}＝{parts['F_only']+parts['D_only']}組",ha='center',va='center',fontsize=11)
    fig.tight_layout();save(fig,'fd_overlap')
    artifacts={p.name:digest(p) for p in FIG_DIR.iterdir() if p.suffix in ['.png','.pdf','.svg']}
    manifest={'sources_sha256':inputs(),'rates':rates,'fd_overlap':parts,'flow':{'initial_groups':1000,'initial_successes':455,'initial_failures':545,'additional_cap':3,'stopping':'L3 success or cap'},'artifacts_sha256':artifacts,'figures':FIGURES,'new_generations':0,'generated_code_executions':0,'flow_scope':'論理的な比較手順。保存済み履歴と部分追試に基づく集計であり，全件新生成とは異なる。'}
    (FIG_DIR/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


def ensure():
    p=FIG_DIR/'figure_manifest.json'
    if p.exists():
        m=json.loads(p.read_text())
        if m['sources_sha256']==inputs() and all((FIG_DIR/f).exists() and digest(FIG_DIR/f)==h for f,h in m['artifacts_sha256'].items()):return m
    return build()


if __name__=='__main__':
    ensure();print('Created/verified 3 figures in PNG, PDF and SVG')
