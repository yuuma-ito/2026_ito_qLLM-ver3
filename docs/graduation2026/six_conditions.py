"""Six-condition display values from frozen CSVs, without experimental work."""
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT/'docs/analysis/reachable_rescues_20261016/core'
B4 = ROOT/'docs/analysis/independent_4_completed_20261022/summary.csv'
SOURCES = [CORE/'repair_summary.csv', CORE/'preventive_summary.csv', B4]
DEFINITIONS = [
    ['B','初回生成のみ','1','基準条件'],
    ['P','生成前注意事項付き生成','1','生成前介入'],
    ['R','自己見直し','4','修正介入'],
    ['F','実行結果提示','4','修正介入'],
    ['D','自己デバッグ','4','修正介入'],
    ['B4','独立再生成','4','生成機会上限をそろえた対照条件'],
]


def read(path):
    return list(csv.DictReader(path.open()))


def only(rows, **keys):
    matched = [r for r in rows if all(r[k]==v for k,v in keys.items())]
    if len(matched)!=1:
        raise ValueError(f'Expected one frozen aggregate for {keys}; got {len(matched)}')
    return matched[0]


def values():
    repairs = read(SOURCES[0]); preventive = read(SOURCES[1]); independent = read(B4)
    rr = {c:only(repairs, scope='pooled', grouping='overall', condition_id=key)
          for c,key in [('R','self_refine'),('F','execution_feedback'),('D','self_debugging')]}
    pp = only(preventive, scope='pooled', grouping='overall')
    bb = only(independent, condition='B', generation_cap='1', grouping='overall', group='all')
    b4 = only(independent, condition='B4', generation_cap='4', grouping='overall', group='all')
    assert all(int(r['pairs'])==1000 and int(r['initial_successes'])==455 and int(r['initial_failures'])==545 for r in [*rr.values(),pp])
    assert all(int(r['groups'])==1000 and int(r['initial_failures'])==545 for r in [bb,b4])
    counts = {'B':int(bb['final_L3_successes']), 'P':int(pp['final_successes']),
              **{c:int(r['final_successes']) for c,r in rr.items()}, 'B4':int(b4['final_L3_successes'])}
    for c,r in rr.items():
        other = only(independent, condition=c, generation_cap='4', grouping='overall', group='all')
        assert counts[c]==int(other['final_L3_successes'])==455+int(r['rescued'])
    assert counts['B']==455 and counts['P']==int(pp['preserved'])+int(pp['rescued'])
    assert counts['B4']==455+int(b4['successes_from_initial_failure'])
    return [{'condition':c,'successes':counts[c],'denominator':1000,'rate_percent':counts[c]/10}
            for c in ['B','P','R','F','D','B4']]


def table_rows():
    return [[r['condition'],str(r['successes']),'1,000',f"{r['rate_percent']:.1f}%"] for r in values()]
