"""Controlled readout audit; the production evaluator and saved scores are unchanged."""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from importlib.metadata import version
from harness.evaluator import _tvd
from tasks import get_task


def prepare_readout(qc):
    """Experimental full terminal-readout projection, rejecting ambiguous mappings."""
    circuit=qc.copy();mapping={};targets=set();seen=False
    for item in circuit.data:
        name=item.operation.name
        if name=='barrier':continue
        if name=='measure':
            seen=True;q=circuit.find_bit(item.qubits[0]).index;c=circuit.find_bit(item.clbits[0]).index
            if q in mapping or c in targets:raise ValueError('repeated measurement or overwritten classical bit')
            mapping[q]=c;targets.add(c)
        elif seen or item.clbits or getattr(item.operation,'condition',None) is not None:
            raise ValueError('nonterminal or classically controlled circuit')
    if not mapping:
        offset=circuit.num_clbits;circuit.measure_all()
        mapping={q:offset+q for q in range(circuit.num_qubits)}
    if len(mapping)!=circuit.num_qubits:raise ValueError('partial measurement')
    return circuit,mapping


def project_counts(counts,mapping,n_clbits):
    result=Counter()
    for key,count in counts.items():
        bits=key.replace(' ','')
        if len(bits)!=n_clbits or set(bits)-{'0','1'}:raise ValueError('unexpected count key')
        projected=''.join(bits[n_clbits-1-mapping[q]] for q in reversed(range(len(mapping))))
        result[projected]+=count
    total=sum(result.values())
    return {key:value/total for key,value in result.items()}


def fixtures():
    from qiskit import QuantumCircuit,ClassicalRegister
    expected={'10':1.0}
    for wrong in [False,True]:
        for unused in [0,1,3,7]:
            qc=QuantumCircuit(2,unused);qc.x(0 if wrong else 1)
            yield f'basis_{"wrong" if wrong else "correct"}_unused{unused}',qc,expected,not wrong
    for layout in ['identity','reverse','gapped','multiregister']:
        qc=QuantumCircuit(2)
        if layout=='multiregister':
            qc.add_register(ClassicalRegister(1,'left'));qc.add_register(ClassicalRegister(3,'right'))
        else:qc.add_register(ClassicalRegister(5 if layout=='gapped' else 2,'readout'))
        qc.x(1)
        mapping={'identity':[0,1],'reverse':[1,0],'gapped':[1,4],'multiregister':[0,3]}[layout]
        qc.measure(range(2),mapping)
        yield 'basis_correct_'+layout,qc,expected,True
    for label in ['partial','overwrite','midcircuit']:
        qc=QuantumCircuit(2,2);qc.x(1);qc.measure(0,0)
        if label=='overwrite':qc.measure(1,0)
        if label=='midcircuit':qc.x(1);qc.measure(1,1)
        yield 'ambiguous_'+label,qc,expected,None
    task=get_task('T8_QPE_001')
    for wrong in [False,True]:
        ns={};exec(task.mock_wrong_code if wrong else task.mock_correct_code,ns)
        for unused in [0,3]:
            qc=ns['build_circuit']()
            if unused:qc.add_register(ClassicalRegister(unused,'unused'))
            yield f'qpe_{"wrong" if wrong else "correct"}_unused{unused}',qc,task.expected_distribution,not wrong


def run_checks():
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    sim=AerSimulator();rows=[]
    for label,qc,expected,should_pass in fixtures():
        legacy=qc.copy()
        if not any(i.operation.name=='measure' for i in legacy.data):legacy.measure_all()
        counts=sim.run(transpile(legacy,sim,seed_transpiler=42),shots=8192,seed_simulator=42).result().get_counts()
        total=sum(counts.values());actual={k.replace(' ',''):v/total for k,v in counts.items()}
        row=dict(case=label,qubits=qc.num_qubits,original_clbits=qc.num_clbits,
                 expected_distribution=json.dumps(expected,sort_keys=True),legacy_distribution=json.dumps(actual,sort_keys=True),
                 legacy_tvd=_tvd(actual,expected),legacy_L2=_tvd(actual,expected)<0.05,
                 candidate_distribution='',candidate_tvd='',candidate_L2='',candidate_rejection='',
                 expected_candidate='reject' if should_pass is None else should_pass)
        try:
            prepared,mapping=prepare_readout(qc)
            assert prepared==legacy
            projected=project_counts(counts,mapping,prepared.num_clbits)
            row.update(candidate_distribution=json.dumps(projected,sort_keys=True),candidate_tvd=_tvd(projected,expected),candidate_L2=_tvd(projected,expected)<0.05)
            assert should_pass is not None and row['candidate_L2']==should_pass,label
        except ValueError as error:
            row['candidate_rejection']=str(error);assert should_pass is None,label
        rows.append(row)
    assert len(rows)==19
    return rows


def audit_saved(snapshot):
    """Stored distributions only; no generated code execution or score changes."""
    counts=Counter();cases=[];sources=[]
    for run in json.loads(snapshot.read_text())['runs']:
        source=Path(run['source_dir'])/'raw.jsonl';raw=source.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==run['raw_sha256']
        sources.append(dict(experiment_id=run['experiment_id'],source_dir=run['source_dir'],raw_sha256=run['raw_sha256']))
        for line in raw.splitlines():
            row=json.loads(line);task=get_task(row['task_id'])
            if task.expected_kind!='distribution':continue
            for attempt in row['rounds']:
                distribution=attempt.get('actual_distribution')
                if not distribution:continue
                widths=sorted({len(k.replace(' ','')) for k in distribution})
                counts['distribution_round_rows']+=1
                if widths!=[task.n_qubits]:
                    counts['width_mismatch_round_rows']+=1
                    cases.append(dict(source_experiment_id=run['experiment_id'],model_spec=row['model_spec'],task_id=row['task_id'],base_seed=row['base_seed'],intervention=row['intervention'],round=attempt['round'],expected_width=task.n_qubits,actual_widths=json.dumps(widths),saved_L2=attempt['L2'],saved_L3=attempt['L3'],error_category=attempt['error_category'],code_sha256=attempt.get('code_sha256',''),distribution=json.dumps(distribution,sort_keys=True)))
        assert source.read_bytes()==raw
    return dict(counts),cases,sources


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',required=True)
    parser.add_argument('--snapshot',default='docs/presentation_sources/20261013T_pooled_verified/results_snapshot.json')
    args=parser.parse_args();out=Path(args.out_dir)
    if out.exists():raise ValueError('Output already exists')
    rows=run_checks();counts,cases,sources=audit_saved(Path(args.snapshot));out.mkdir(parents=True)
    for name,data in [('controlled_cases.csv',rows),('stored_width_mismatches.csv',cases)]:
        with (out/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]) if data else ['case']);writer.writeheader();writer.writerows(data)
    report=dict(passed=True,controlled_cases=len(rows),candidate_success=sum(r['candidate_L2'] is True for r in rows),
        candidate_rejections=sum(bool(r['candidate_rejection']) for r in rows),legacy_fail_candidate_pass=sum(not r['legacy_L2'] and r['candidate_L2'] is True for r in rows),stored_counts=counts,
        evaluator_changed=False,saved_scores_changed=False,generated_code_executed=False,shots=8192,seed_simulator=42,seed_transpiler=42)
    (out/'sanity_report.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),sources=sources,fixed_snapshot=args.snapshot,
        snapshot_sha256=hashlib.sha256(Path(args.snapshot).read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),evaluator_sha256=hashlib.sha256(Path('harness/evaluator.py').read_bytes()).hexdigest(),versions={p:version(p) for p in ['qiskit','qiskit-aer']},artifacts=[dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
