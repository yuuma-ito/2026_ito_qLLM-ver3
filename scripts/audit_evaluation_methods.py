"""Controlled evaluator audit before reevaluating historical generated code."""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
from importlib.metadata import version
import numpy as np
from harness.evaluator import evaluate,_statevector_distance,EVALUATOR_VERSION
from tasks import all_tasks,get_task


def aligned_distance(actual,expected):
    """Independent phase-invariant distance from overlap magnitude."""
    return math.sqrt(max(0.0,float(np.vdot(actual,actual).real+np.vdot(expected,expected).real-2*abs(np.vdot(actual,expected)))))


def independent_ansatz():
    state=np.array([1,0,0,0],complex)
    def ry(q,angle):
        nonlocal state
        old=state.copy();c=math.cos(angle/2);s=math.sin(angle/2)
        for index in range(4):
            if not index&(1<<q):
                partner=index|(1<<q)
                state[index]=c*old[index]-s*old[partner]
                state[partner]=s*old[index]+c*old[partner]
    ry(0,math.pi/4);ry(1,math.pi/3)
    state=state[[0,3,2,1]]
    ry(0,math.pi/6);ry(1,math.pi/5)
    return state


def analytic_checks():
    rows=[]
    for task_id,sign in [('T6_QFT_001',1),('T7_IQFT_001',-1)]:
        expected=np.exp(sign*2j*np.pi*np.arange(8)/8)/math.sqrt(8)
        actual=np.array(get_task(task_id).expected_statevector)
        rows.append(dict(task_id=task_id,reference='analytic Fourier column j=1',distance=aligned_distance(actual,expected)))
    rows.append(dict(task_id='T9_Ansatz_001',reference='independent amplitude updates',distance=aligned_distance(np.array(get_task('T9_Ansatz_001').expected_statevector),independent_ansatz())))
    for row in rows:assert row['distance']<1e-7
    return rows


def modified_code(code,statement):
    return code.replace('    return qc',f'    {statement}\n    return qc')


def controlled_cases():
    for task in all_tasks():
        yield task.id+'_correct',task,task.mock_correct_code,'canonical_correct'
        yield task.id+'_wrong',task,task.mock_wrong_code,'canonical_wrong'
    for task_id in ['T6_QFT_001','T7_IQFT_001','T9_Ansatz_001']:
        task=get_task(task_id)
        for phase in [math.pi/4,math.pi/2]:
            yield f'{task_id}_globalphase{phase:.4f}',task,modified_code(task.mock_correct_code,f'qc.global_phase = {phase!r}'),'physically_equivalent'
        yield task_id+'_relativephase',task,modified_code(task.mock_correct_code,'qc.z(0)'),'relative_phase_error'
    for task_id in ['T1_Bell','T2_GHZ']:
        task=get_task(task_id)
        yield task_id+'_relativephase',task,modified_code(task.mock_correct_code,'qc.z(0)'),'different_state_same_distribution'
        wrapped=modified_code(task.mock_correct_code,'qc = QuantumCircuit(qc.num_qubits).compose(qc.to_gate(), range(qc.num_qubits))')
        yield task_id+'_composite',task,wrapped,'equivalent_structure_representation'
    task=get_task('T1_Bell')
    yield 'bell_barriers',task,modified_code(task.mock_correct_code,'[qc.barrier() for _ in range(6)]'),'equivalent_structure_representation'
    yield 'bell_measured',task,modified_code(task.mock_correct_code,'qc.measure_all()'),'measurement_forbidden_by_prompt'
    yield 'bell_unbound_parameter',task,modified_code(task.mock_correct_code,"from qiskit.circuit import Parameter; qc.ry(Parameter('theta'), 0)"),'unsupported_unbound_parameter'
    task=get_task('T5_Grover_11')
    yield 'grover_without_algorithm',task,'''from qiskit import QuantumCircuit
def build_circuit():
    qc=QuantumCircuit(2)
    qc.x(0)
    qc.x(1)
    for _ in range(6): qc.id(0)
    return qc
''','correct_output_wrong_algorithm'
    task=get_task('T6_QFT_001')
    yield 'qft_explicit_measurement',task,modified_code(task.mock_correct_code,'qc.measure_all()'),'measurement_forbidden_by_prompt'


def audit_cases():
    from qiskit.quantum_info import Statevector
    rows=[]
    for label,task,code,kind in controlled_cases():
        result=evaluate(code,task)
        ns={};exec(code,ns);qc=ns['build_circuit']()
        reference_distance='';fidelity=''
        try:
            actual=Statevector.from_instruction(qc).data
            if task.expected_kind=='statevector':expected=np.array(task.expected_statevector)
            elif task.id=='T1_Bell':expected=np.array([1,0,0,1])/math.sqrt(2)
            elif task.id=='T2_GHZ':expected=np.array([1,0,0,0,0,0,0,1])/math.sqrt(2)
            else:expected=None
            if expected is not None:
                reference_distance=aligned_distance(actual,expected);fidelity=float(abs(np.vdot(actual,expected))**2)
        except Exception:pass
        rows.append(dict(case=label,task_id=task.id,kind=kind,L0=result.L0,L1=result.L1,L2=result.L2,L3=result.L3,structure_match=result.structure_match,distance=result.L2_distance,error_category=result.error_category,failure_stage=result.failure_stage,exception_type=result.exception_type,gate_count=result.gate_count,phase_invariant_distance=reference_distance,state_fidelity=fidelity,code_sha256=hashlib.sha256(code.encode()).hexdigest()))
    assert len(rows)==38
    assert all(r['L3'] for r in rows if r['kind']=='canonical_correct')
    assert all(not r['L2'] for r in rows if r['kind']=='canonical_wrong')
    assert all(r['phase_invariant_distance']<1e-7 for r in rows if r['kind']=='physically_equivalent')
    return rows


def sampling_checks():
    rng=np.random.default_rng(42);rows=[]
    for p in [0.5,0.54,0.548,0.55,0.552,0.56]:
        estimated=rng.binomial(8192,p,size=10000)/8192
        distances=np.abs(estimated-0.5)
        rows.append(dict(probability=p,true_tvd=abs(p-0.5),shots=8192,repetitions=10000,accepted=int(np.sum(distances<0.05)),accept_rate=float(np.mean(distances<0.05)),seed=42))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',required=True);args=p.parse_args()
    out=Path(args.out_dir)
    if out.exists():raise ValueError('Output exists')
    references=analytic_checks();rows=audit_cases();sampling=sampling_checks();out.mkdir(parents=True)
    for name,data in [('controlled_cases.csv',rows),('analytic_references.csv',references),('sampling_threshold.csv',sampling)]:
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    report=dict(passed=True,controlled_cases=len(rows),canonical_correct=10,canonical_wrong=10,
        reproduced_global_phase_false_negatives=sum(not r['L2'] for r in rows if r['kind']=='physically_equivalent'),analytic_reference_checks_passed=3,
        historical_generated_code_executed=False,historical_scores_changed=False,production_evaluator_changed=False,
        evaluation_version=EVALUATOR_VERSION,full_reevaluation_ready=False)
    (out/'sanity_report.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),evaluator_version=EVALUATOR_VERSION,
        evaluator_sha256=hashlib.sha256(Path('harness/evaluator.py').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),versions={n:version(n) for n in ['numpy','qiskit','qiskit-aer']},artifacts=[dict(path=x.name,sha256=hashlib.sha256(x.read_bytes()).hexdigest()) for x in out.iterdir()])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
