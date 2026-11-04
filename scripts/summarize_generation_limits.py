"""Summarize published followup finish reasons; no raw/code/API access."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/analysis/reevaluation_followup_20261015/partial_new_rounds.csv'


def summarize(rows):
    counts=Counter();seen=set()
    for r in rows:
        key=(r['record_key'],int(r['round']))
        if key in seen:raise ValueError('duplicate record/round')
        seen.add(key)
        reason=r['api_finish_reason']
        if not reason:raise ValueError('missing finish reason; not measured zero')
        counts[(r['condition_id'],reason)]+=1
    out=[]
    for condition in sorted({c for c,_ in counts}):
        reasons={reason:n for (c,reason),n in sorted(counts.items()) if c==condition}
        total=sum(reasons.values())
        out.append({'condition_id':condition,'generations':total,'finish_reasons':reasons,
                    'length_count':reasons.get('length',0),'length_rate':reasons.get('length',0)/total})
    return {'scope':'selected_partial_followup_293_cases_only', 'total_generations':len(seen),
            'conditions':out,'causal_effect_identified':False,
            'interpretation':'出力枠への依存を記述する。全実験の打切り率・説明指示の因果効果・打切りが誤答原因だったことは示さない。'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with SOURCE.open() as f:result=summarize(csv.DictReader(f))
    result['source']=str(SOURCE.relative_to(ROOT))
    result['source_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    data=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(data)
    else:print(data,end='')


if __name__=='__main__':main()
