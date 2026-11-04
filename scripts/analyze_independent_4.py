"""B4/reference comparisons from saved records only; no code execution or API."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from harness.independent_4 import (ROOT, LEVELS, identity, load_cohort, read_csv, sha,
                                  unique, validate_record, levels, read_checkpoint)
from harness.run_state import atomic_json
from scripts.run_independent_4 import write_csv
from scripts import analyze_verified_rescues as base

LABELS = {'self_refine':'R', 'execution_feedback':'F', 'self_debugging':'D', 'preventive_spec':'P'}
GROUPS = {'overall':None, 'model':'model_spec', 'task':'task_id',
          'difficulty':'task_difficulty', 'initial_failure':'initial_error_category'}


def reference_paths(config, cases, root=ROOT):
    sources = config['sources']
    mixed = base.read_csv(root/base.FOLLOWUP/'mixed_path_records.csv')
    saved = base.read_csv(root/base.FULL/'round_comparison.csv')
    partial = base.read_csv(root/base.FOLLOWUP/'partial_rerun_records.csv')
    suffix = base.read_csv(root/base.FOLLOWUP/'partial_new_rounds.csv')
    paths = base.build_paths(mixed, saved, partial, suffix)
    costs = unique(read_csv(root/sources['reachable_rounds']), lambda r:(r['record_key'],int(r['round'])))
    paired = read_csv(root/sources['paired'])
    out = {identity(c):{} for c in cases}
    for row in paired:
        key = identity(row)
        if key not in out or LABELS[row['condition_id']] in out[key]:
            raise ValueError('unexpected/duplicate comparator')
        pp = []
        for index, r in enumerate(paths[row['record_key']]):
            cost = costs[(row['record_key'], index)]
            primary = {level:base.truth(r['new_'+level]) for level in (*LEVELS,'structure_match')}
            primary.update(failure_stage=r.get('new_failure_stage','saved'), error_category=r['new_error_category'])
            levels(primary)
            pp.append(dict(round=index, primary=primary, code_sha256=cost['code_sha256'],
                           tokens_in=int(cost['tokens_in']), tokens_out=int(cost['tokens_out']),
                           generation_seconds=float(cost['generation_seconds']), evaluation_seconds=None))
        if LABELS[row['condition_id']] != 'P':
            initial = next(c['initial'] for c in cases if identity(c) == key)
            if pp[0]['code_sha256'] != initial['code_sha256'] or any(pp[0]['primary'][l] != initial['primary'][l] for l in LEVELS):
                raise ValueError('comparator does not share the verified initial')
        out[key][LABELS[row['condition_id']]] = pp
    if any(set(v) != {'P','R','F','D'} for v in out.values()):
        raise ValueError('missing reference condition')
    return out


def analyze(records, cases, references, config):
    expected = {identity(c):c for c in cases}
    actual = unique(records, identity)
    if set(actual) != set(expected):
        raise ValueError('missing/unexpected B4 groups')
    summary = defaultdict(Counter)
    first = defaultdict(Counter)
    combinations = Counter()
    pairwise = defaultdict(Counter)
    duplicates = []
    for key, c in expected.items():
        record = actual[key]
        validate_record(record, c, config)
        failed = not c['initial']['primary']['L3']
        dims = dict(c, initial_error_category=c['initial']['primary']['error_category'])
        paths = {'B':[c['initial']], 'B4':record['rounds'], **references[key]}
        for label, path in paths.items():
            for r in path:
                levels(r['primary'])
            first_index = next((i for i,r in enumerate(path) if r['primary']['L3']), None)
            first[(label, 'generation_'+str(first_index+1) if first_index is not None else 'never')]['groups'] += 1
            for cap in ([1] if label in {'B','P'} else [1,2,3,4]):
                chosen = path[:cap]
                success = any(r['primary']['L3'] for r in chosen)
                # B initial cost is reported once separately. P has its own one-shot cost.
                additional = chosen if label == 'P' else chosen[1:] if label != 'B' else []
                counts = dict(groups=1, initial_failures=int(failed), final_L3_successes=int(success),
                              successes_from_initial_failure=int(failed and success),
                              regressed=int(not failed and not success), total_generation_opportunities=len(chosen),
                              additional_requests=len(additional),
                              additional_tokens_in=sum(r['tokens_in'] for r in additional),
                              additional_tokens_out=sum(r['tokens_out'] for r in additional),
                              additional_generation_seconds=sum(r['generation_seconds'] for r in additional),
                              additional_evaluation_seconds=sum(r.get('evaluation_seconds') or 0 for r in additional),
                              evaluation_time_measured_requests=sum(r.get('evaluation_seconds') is not None for r in additional))
                for l in LEVELS:
                    counts['cumulative_'+l] = int(any(r['primary'][l] for r in chosen))
                for grouping, field in GROUPS.items():
                    summary[(label, cap, grouping, str(dims[field]) if field else 'all')].update(counts)
        if failed:
            success = {l: any(r['primary']['L3'] for r in paths[l]) for l in ('B4','F','D')}
            mask = ''.join('1' if success[l] else '0' for l in ('B4','F','D'))
            combinations[mask] += 1
            for label in ('R','F','D'):
                a = success['B4']
                bb = any(r['primary']['L3'] for r in paths[label])
                pairwise[label]['both' if a and bb else 'B4_only' if a else label+'_only' if bb else 'neither'] += 1
        for r in record['rounds'][1:]:
            duplicates.append(dict(model_spec=c['model_spec'], task_id=c['task_id'], base_seed=c['base_seed'],
                                   round=r['round'], generation_number=r['generation_number'], round_seed=r['round_seed'],
                                   code_sha256=r['code_sha256'], repeated_code=r['repeated_code'],
                                   L3=r['primary']['L3'], finish_reason=r.get('finish_reason')))
    rows = []
    for (label, cap, grouping, value), counts in sorted(summary.items()):
        n, nf = counts['groups'], counts['initial_failures']
        gain = counts['successes_from_initial_failure']
        tok = counts['additional_tokens_in'] + counts['additional_tokens_out']
        rows.append(dict(condition=label, generation_cap=cap, grouping=grouping, group=value, **counts,
                         final_L3_rate=counts['final_L3_successes']/n,
                         success_from_initial_failure_rate=gain/nf if nf else None,
                         additional_tokens=tok, tokens_per_added_success=tok/gain if gain else None,
                         seconds_per_added_success=counts['additional_generation_seconds']/gain if gain else None,
                         outcome_name='修正介入による救出' if label in {'R','F','D'} else
                                      '独立再生成による成功' if label == 'B4' else '独立初回生成'))
    pattern_names = ['none','D_only','F_only','F_D_only','B4_only','B4_D_only','B4_F_only','all_three']
    overlap = [dict(success_pattern=pattern_names[mask], B4_success=bool(mask&4), F_success=bool(mask&2), D_success=bool(mask&1),
                    initial_failure_groups=combinations[format(mask,'03b')]) for mask in range(8)]
    once_tokens = sum(c['initial']['tokens_in']+c['initial']['tokens_out'] for c in cases)
    once_seconds = sum(c['initial']['generation_seconds'] for c in cases)
    # Every stratification must reproduce its pooled denominator, outcomes and costs.
    for total in [r for r in rows if r['grouping']=='overall']:
        for grouping in GROUPS:
            partition=[r for r in rows if r['condition']==total['condition'] and r['generation_cap']==total['generation_cap']
                       and r['grouping']==grouping]
            for metric in ('groups','initial_failures','final_L3_successes','successes_from_initial_failure',
                           'additional_requests','additional_tokens','additional_generation_seconds'):
                if not math.isclose(sum(r[metric] for r in partition), total[metric], rel_tol=1e-10, abs_tol=1e-6):
                    raise ValueError('stratified count/cost reconciliation failed')
    if sum(r['initial_failure_groups'] for r in overlap)!=sum(not c['initial']['primary']['L3'] for c in cases):
        raise ValueError('overlap denominator mismatch')
    repeated=defaultdict(list)
    for r in duplicates:
        repeated[(r['model_spec'],r['task_id'],r['code_sha256'])].append(r['round_seed'])
    for r in duplicates:
        values=repeated[(r['model_spec'],r['task_id'],r['code_sha256'])]
        r.update(same_model_task_code_frequency=len(values), distinct_new_seeds_for_code=len(set(values)))
    sanity = dict(passed=True, groups=len(cases), missing=0, duplicates=0, unexpected=0,
                  initial_failures=sum(not c['initial']['primary']['L3'] for c in cases),
                  shared_initial_tokens_counted_once=once_tokens,
                  shared_initial_generation_seconds_counted_once=once_seconds,
                  max_new_requests=3*sum(not c['initial']['primary']['L3'] for c in cases),
                  actual_new_requests=sum(len(r['rounds'])-1 for r in records),
                  semantics='初期コード共通．追加コストは初回を除く．Pは独立1回生成の全コスト．',
                  comparison_limit='同じ最大要求回数でも入力情報・tokens・seed規則・出典schema・診断文と実行時期が異なる．因果効果を確定しない．')
    first_rows = [dict(condition=l,first_success_generation=k,groups=first[(l,k)]['groups'])
                  for l in ('B','P','B4','R','F','D')
                  for k in (['generation_1','never'] if l in {'B','P'} else
                            ['generation_1','generation_2','generation_3','generation_4','never'])]
    return dict(summary=rows, first_success=first_rows,
                overlap=overlap, pairwise=[dict(comparator=l, **v) for l,v in sorted(pairwise.items())],
                repetitions=duplicates, sanity=sanity)


def analyze_saved(output, config, cases=None, *, root=ROOT):
    actual=read_checkpoint(output/'experiment_config.json')
    for key,value in config.items():
        if key not in {'experiment_id','output_dir'} and actual.get(key)!=value:
            raise ValueError('analysis configuration differs from the saved run')
    if actual['experiment_id']!=output.name or (root/actual['output_dir']).resolve()!=output.resolve():
        raise ValueError('analysis output/run identity mismatch')
    config=actual
    if cases is None:
        cases, _, _ = load_cohort(config, root)
    public = output/'analysis'
    public.mkdir(parents=True, exist_ok=True)
    try:
        with (output/'raw.jsonl').open() as f:
            records = [json.loads(line) for line in f if line.strip()]
        result = analyze(records, cases, reference_paths(config, cases, root), config)
    except Exception as error:
        atomic_json(public/'sanity_report.json', {'passed':False, 'failure_type':type(error).__name__,
                                                'status':'incomplete_or_invalid; no confirmed comparison'})
        raise
    for key in ('summary','first_success','overlap','pairwise','repetitions'):
        if result[key]:
            write_csv(public/(key+'.csv'), result[key])
    atomic_json(public/'sanity_report.json', result['sanity'])
    atomic_json(public/'manifest.json', {'schema':'independent_4_analysis_v1',
                                       'raw_sha256':sha(output/'raw.jsonl'),
                                       'runner_manifest_sha256':sha(output/'manifest.json')})
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--config', default='configs/independent_4_full.json')
    args=p.parse_args(argv)
    config=json.loads((ROOT/args.config).read_text())
    analyze_saved(ROOT/args.output, config)


if __name__=='__main__':
    main()
