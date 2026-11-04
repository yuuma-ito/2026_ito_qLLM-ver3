"""Load hash-verified historical code as TEXT for the measurement-only audit."""
import csv
import hashlib
import json
from pathlib import Path

from scripts import analyze_verified_rescues as base

ROOT=Path(__file__).resolve().parents[1]
FULL=Path('docs/analysis/reevaluation_full_20261014T141718Z/final')
FOLLOW=Path('docs/analysis/reevaluation_followup_20261015')
REACH=Path('docs/analysis/reachable_rescues_20261016')
B4=Path('docs/analysis/independent_4_completed_20261022')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_key(task,code_hash):
    return hashlib.sha256((task+'\n'+code_hash).encode()).hexdigest()


def csv_rows(path):
    with Path(path).open() as f:return list(csv.DictReader(f))


def load_sources(root=ROOT):
    inputs={}
    def json_file(path):
        inputs[str(path)]=sha(root/path)
        return json.loads((root/path).read_text())
    def table(path):
        inputs[str(path)]=sha(root/path)
        return csv_rows(root/path)
    settings=json_file(FOLLOW/'settings_manifest.json')
    raw={}
    for source in settings['sources']:
        folder=Path(source['source_dir'])
        for name,key in [('raw.jsonl','raw_sha256'),('experiment_config.json','config_sha256')]:
            path=folder/name
            if sha(root/path)!=source[key]:raise ValueError('original raw/config hash mismatch')
            inputs[str(path)]=source[key]
        with (root/folder/'raw.jsonl').open() as f:
            for line in f:
                r=json.loads(line)
                ident=(str(folder),r['model_spec'],r['task_id'],str(r['base_seed']),r['condition_id'])
                if ident in raw:raise ValueError('duplicate original condition record')
                raw[ident]={int(a['round']):a for a in r['rounds']}
    full=table(FULL/'round_comparison.csv')
    suffix=table(FOLLOW/'partial_new_rounds.csv')
    partial=table(FOLLOW/'partial_rerun_records.csv')
    mixed=table(FOLLOW/'mixed_path_records.csv')
    reachable=table(REACH/'reachable_rounds.csv')
    paths=base.build_paths(mixed,full,partial,suffix)
    source_codes={}
    for r in full:
        a=raw[base.identity(r)][int(r['round'])]
        if hashlib.sha256(a['extracted_code'].encode()).hexdigest()!=r['code_sha256']:
            raise ValueError('original code hash mismatch')
        source_codes[(r['record_key'],int(r['round']),'saved_prefix')]=a['extracted_code']
    private=Path('.cache/reevaluation_followup/reevaluation_full_20261014T141718Z/partial')
    for r in partial:
        path=private/r['record_key']/'completed.json'
        expected=(root/path.with_suffix('.sha256')).read_text().strip()
        if sha(root/path)!=expected:raise ValueError('suffix checkpoint hash mismatch')
        inputs[str(path)]=expected
        for a in json_file(path)['suffix']:
            source_codes[(r['record_key'],int(a['round']),'new_suffix')]=a['code']
    branches={r['record_key']:int(r['branch_input_round']) for r in partial}
    cases={};refs=[]
    def add_ref(scope,r,index,code,code_hash,condition=None):
        if hashlib.sha256(code.encode()).hexdigest()!=code_hash:raise ValueError('success code hash mismatch')
        key=code_key(r['task_id'],code_hash)
        entry={'key':key,'task_id':r['task_id'],'code_sha256':code_hash,'code':code}
        if key in cases and cases[key]!=entry:raise ValueError('code identity collision')
        cases[key]=entry
        refs.append({'scope':scope,'source_dir':r['source_dir'],'record_key':r['record_key'],
                     'model_spec':r['model_spec'],'task_id':r['task_id'],'base_seed':int(r['base_seed']),
                     'condition_id':condition or r['condition_id'],'round':index,'code_sha256':code_hash,'code_task_key':key})
    for r in full:
        if base.truth(r['new_L3']):
            add_ref('saved_round_v4',r,int(r['round']),source_codes[(r['record_key'],int(r['round']),'saved_prefix')],r['code_sha256'])
    for r in suffix:
        code=source_codes[(r['record_key'],int(r['round']),'new_suffix')]
        if hashlib.sha256(code.encode()).hexdigest()!=r['new_code_sha256']:raise ValueError('suffix public code hash mismatch')
        if base.truth(r['new_L3']):add_ref('followup_suffix_v4',r,int(r['round']),code,r['new_code_sha256'])
    fixed=json_file(B4/'source_manifest.json')
    b4path=Path(fixed['source_directory'])/'raw.jsonl'
    if sha(root/b4path)!=fixed['raw_sha256']:raise ValueError('B4 raw hash mismatch')
    inputs[str(b4path)]=fixed['raw_sha256']
    with (root/b4path).open() as f:b4records=[json.loads(l) for l in f if l.strip()]
    if len(b4records)!=1000:raise ValueError('B4 cohort incomplete')
    for r in b4records:
        for a in r['rounds']:
            if a['primary']['L3']:
                rr={**r,'source_dir':str(b4path.parent),'record_key':'B4:'+r['baseline_record_key']}
                add_ref('B4_shared_initial' if a['round']==0 else 'B4_new_round',rr,a['round'],a['extracted_code'],a['code_sha256'],'independent_4')
    reach_map={(r['record_key'],int(r['round'])):r for r in reachable}
    for r in mixed:
        for i,e in enumerate(paths[r['record_key']]):
            if base.truth(e['new_L3']):
                a=reach_map[(r['record_key'],i)]
                origin='new_suffix' if i>=branches.get(r['record_key'],4) else 'saved_prefix'
                add_ref('current_reachable_v4',r,i,source_codes[(r['record_key'],i,origin)],a['code_sha256'])
    if len(cases)!=1561 or len(raw)!=5000 or len(mixed)!=5000:
        raise ValueError('fixed audit coverage changed; investigate')
    return {'cases':cases,'references':refs,'inputs':inputs,'mixed':mixed,'paths':paths,
            'full':full,'raw':raw,'reachable':reachable,'B4_records':b4records,'branches':branches}
