"""Literature-guided controlled checks; never executes historical generated code."""
from __future__ import annotations
import argparse,csv,hashlib,inspect,json,math,subprocess,sys,time
from pathlib import Path
from importlib.metadata import version
from datetime import datetime,timezone
import numpy as np
from harness.evaluator import evaluate,_statevector_distance,_run_statevector,EVALUATOR_VERSION
from harness.readout import ReadoutError
from tasks import all_tasks,get_task
from scripts.audit_evaluation_methods import modified_code


def overlap_fidelity(a,b):
    return float(abs(np.vdot(a,b))**2)


def wilson_interval(success,total,z=1.959963984540054):
    if total<=0 or not 0<=success<=total:raise ValueError('Invalid binomial counts')
    p=success/total;denom=1+z*z/total
    center=(p+z*z/(2*total))/denom
    half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denom
    return max(0,center-half),min(1,center+half)


def summarize_history(attempts):
    if not attempts or [r['round'] for r in attempts]!=list(range(len(attempts))):raise ValueError('Incomplete observed history')
    success=[r['round'] for r in attempts if r['L3']]
    return dict(initial_success=bool(attempts[0]['L3']),ever_success=bool(success),
        first_success_round=min(success) if success else -1,final_success=bool(attempts[-1]['L3']),
        transitions_to_failure=sum(a['L3'] and not b['L3'] for a,b in zip(attempts,attempts[1:])),
        final_rescue=not attempts[0]['L3'] and bool(attempts[-1]['L3']),
        final_regression=bool(attempts[0]['L3']) and not attempts[-1]['L3'])


def build_mock(task):
    ns={};exec(task.mock_correct_code,ns);return ns['build_circuit']()


def quantum_checks():
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector,DensityMatrix,state_fidelity,Operator
    from qiskit.circuit.library import StatePreparation
    rows=[]
    def emit(case,kind,observed,expected,passed):
        rows.append(dict(case=case,kind=kind,observed=json.dumps(observed,default=float,sort_keys=True),expected=json.dumps(expected,sort_keys=True),check_passed=bool(passed)))
    rng=np.random.default_rng(42)
    for index in range(12):
        a=rng.normal(size=8)+1j*rng.normal(size=8);a/=np.linalg.norm(a)
        b=rng.normal(size=8)+1j*rng.normal(size=8);b/=np.linalg.norm(b)
        f=overlap_fidelity(a,b);distance=_statevector_distance(a,b)
        emit(f'phase_metric_{index}','independent_fidelity',dict(distance=distance,fidelity=f,qiskit_fidelity=state_fidelity(a,b)),dict(distance_squared=2-2*math.sqrt(f)),abs(distance**2-(2-2*math.sqrt(f)))<1e-12 and abs(f-state_fidelity(a,b))<1e-12)
    for task in all_tasks():
        canonical=evaluate(task.mock_correct_code,task)
        for name,statement in [('global_phase','qc.global_phase += 1.0471975511965976'),('gate_inverse','qc.x(0); qc.x(0)'),('barrier','qc.barrier()')]:
            result=evaluate(modified_code(task.mock_correct_code,statement),task)
            emit(task.id+'_'+name,'metamorphic',dict(L2=result.L2,L3=result.L3,distance=result.L2_distance),dict(L2=True),canonical.L2 and result.L2)
    bell=QuantumCircuit(2);bell.h(0);bell.cx(0,1);bell.reset(0)
    density=DensityMatrix.from_instruction(bell)
    independent=np.diag([0.5,0,0.5,0])
    emit('partial_reset_ensemble','nonunitary',dict(diagonal=np.diag(density.data).real.tolist(),fidelity00=state_fidelity(density,Statevector.from_label('00'))),dict(diagonal=[0.5,0,0.5,0],fidelity00=0.5),np.allclose(density.data,independent))
    for name,qc in [('reset',bell),('initialize',QuantumCircuit(2))]:
        if name=='initialize':qc.initialize([1,0,0,0],range(2))
        rejected=False
        try:_run_statevector(qc)
        except ReadoutError:rejected=True
        emit(name+'_primary_rejection','nonunitary_policy',dict(rejected=rejected),dict(rejected=True),rejected)
    prepared=QuantumCircuit(2);prepared.append(StatePreparation([1/math.sqrt(2),0,0,1/math.sqrt(2)]),range(2))
    emit('unitary_state_preparation','nonunitary_policy',dict(fidelity=overlap_fidelity(_run_statevector(prepared),np.array([1,0,0,1])/math.sqrt(2))),dict(fidelity=1),np.allclose(abs(_run_statevector(prepared))**2,[0.5,0,0,0.5]))
    for task_id,sign in [('T6_QFT_001',1),('T7_IQFT_001',-1)]:
        circuit=build_mock(get_task(task_id));assert circuit.data[0].operation.name=='x';circuit.data.pop(0)
        operator=Operator(circuit).data
        dft=np.exp(sign*2j*np.pi*np.outer(np.arange(8),np.arange(8))/8)/math.sqrt(8)
        states=[np.eye(8,dtype=complex)[:,j] for j in range(8)]
        states += [np.array([1,1,0,0,0,0,0,0],complex)/math.sqrt(2),np.array([1,1j,0,0,0,0,0,0],complex)/math.sqrt(2)]
        for index,state in enumerate(states):
            fid=overlap_fidelity(operator@state,dft@state)
            emit(task_id+f'_input{index}','multiple_input',dict(fidelity=fid),dict(fidelity=1),abs(fid-1)<1e-12)
        phase_columns=np.eye(8);phase_columns[1,1]=-1;mutant=dft@phase_columns
        basis_equivalent=all(abs(overlap_fidelity(mutant@state,dft@state)-1)<1e-12 for state in states[:8])
        coherent_fidelity=overlap_fidelity(mutant@states[8],dft@states[8])
        emit(task_id+'_column_phase_mutant','multiple_input_counterexample',dict(basis_all_pass=basis_equivalent,coherent_fidelity=coherent_fidelity),dict(basis_all_pass=True,coherent_fidelity=0),basis_equivalent and coherent_fidelity<1e-12)
    for theta in [0,math.pi/7,math.pi/2,math.pi]:
        qc=QuantumCircuit(1);qc.ry(theta,0)
        expected=np.array([math.cos(theta/2),math.sin(theta/2)])
        emit(f'ry_parameter_{theta:.4f}','parameter_family',dict(fidelity=overlap_fidelity(_run_statevector(qc),expected)),dict(fidelity=1),np.allclose(_run_statevector(qc),expected))
    for task in all_tasks():
        if task.expected_kind=='distribution':
            mass=sum(task.expected_distribution.values());widths={len(k) for k in task.expected_distribution}
            valid=abs(mass-1)<1e-9 and widths=={task.n_qubits} and all(v>=0 for v in task.expected_distribution.values())
        else:
            state=np.array(task.expected_statevector);mass=float(np.vdot(state,state).real)
            valid=abs(mass-1)<1e-9 and len(state)==2**task.n_qubits and bool(np.all(np.isfinite(state)))
        emit(task.id+'_oracle_validity','oracle_validation',dict(mass=mass),dict(mass=1),valid)
    return rows


def mutation_checks():
    from qiskit.quantum_info import Statevector
    rows=[]
    for task_id in ['T1_Bell','T2_GHZ']:
        task=get_task(task_id)
        target=np.zeros(2**task.n_qubits,dtype=complex)
        target[0]=target[-1]=1/math.sqrt(2)
        for name,statement in [('delete_entanglement',None),('relative_phase','qc.z(0)'),('replace_gate','qc.x(0)')]:
            if name=='delete_entanglement':
                code='\n'.join(line for line in task.mock_correct_code.splitlines() if 'qc.cx(' not in line)
            else:code=modified_code(task.mock_correct_code,statement)
            ns={};exec(code,ns);actual=Statevector.from_instruction(ns['build_circuit']()).data
            result=evaluate(code,task);fid=overlap_fidelity(actual,target)
            assert fid<1-1e-9
            rows.append(dict(task_id=task_id,mutation=name,semantic_non_equivalent=True,state_fidelity=fid,
                primary_L2=result.L2,primary_L3=result.L3,primary_killed=not result.L3,
                supplementary_fidelity_killed=fid<0.9975,error_category=result.error_category))
    return rows


def controlled_process_checks():
    # Only trusted synthetic snippets. This demonstrates subprocess timeout,
    # not a secure sandbox or the production reevaluation executor.
    rows=[]
    for name,code in [('normal','print(1)'),('exception','raise ValueError("controlled")'),('exit','import os; os._exit(7)'),('timeout','while True: pass')]:
        start=time.monotonic();timed_out=False;returncode=None
        try:returncode=subprocess.run([sys.executable,'-c',code],capture_output=True,timeout=0.25).returncode
        except subprocess.TimeoutExpired:timed_out=True
        passed=timed_out if name=='timeout' else returncode==0 if name=='normal' else returncode!=0
        rows.append(dict(case=name,returncode=returncode,timed_out=timed_out,elapsed_sec=time.monotonic()-start,check_passed=passed,production_sandbox=False))
    return rows


def local_specification():
    from qiskit import QuantumCircuit
    from qiskit.quantum_info import Statevector,DensityMatrix,state_fidelity,Operator
    functions=[Statevector.reset,Statevector.from_instruction,Statevector._evolve_instruction,DensityMatrix._evolve_instruction,state_fidelity,Operator.__init__,QuantumCircuit.measure_all]
    return [dict(name=obj.__qualname__,signature=str(inspect.signature(obj)),module=inspect.getmodule(obj).__name__,line=inspect.getsourcelines(obj)[1],source_sha256=hashlib.sha256(inspect.getsource(obj).encode()).hexdigest()) for obj in functions]


def sampling_sensitivity():
    rows=[]
    for shots in [1024,8192,65536]:
        for seed in [10,42,99]:
            rng=np.random.default_rng(seed)
            for p in [0.5,0.548,0.55,0.552]:
                distances=np.abs(rng.binomial(shots,p,size=2000)/shots-0.5)
                for threshold in [0.01,0.05,0.1]:
                    n=int(np.sum(distances<threshold));low,high=wilson_interval(n,2000)
                    rows.append(dict(shots=shots,seed=seed,true_tvd=abs(p-0.5),threshold=threshold,repetitions=2000,accepted=n,accept_rate=n/2000,wilson_low=low,wilson_high=high))
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',required=True);args=parser.parse_args();out=Path(args.out_dir)
    if out.exists():raise ValueError('Output exists')
    start=time.monotonic();checks=quantum_checks();mutations=mutation_checks();processes=controlled_process_checks();sampling=sampling_sensitivity()
    assert all(r['check_passed'] for r in checks+processes)
    out.mkdir(parents=True)
    for name,rows in [('controlled_checks.csv',checks),('mutation_checks.csv',mutations),('controlled_process_checks.csv',processes),('sampling_sensitivity.csv',sampling)]:
        with (out/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (out/'installed_qiskit_spec.json').write_text(json.dumps(local_specification(),indent=2)+'\n')
    report=dict(passed=True,controlled_checks=len(checks),mutation_cases=len(mutations),
        primary_mutants_killed=sum(r['primary_killed'] for r in mutations),supplementary_mutants_killed=sum(r['supplementary_fidelity_killed'] for r in mutations),
        controlled_process_checks=len(processes),sampling_sensitivity_groups=len(sampling),controlled_wall_sec=time.monotonic()-start,
        evaluator_version=EVALUATOR_VERSION,historical_generated_code_executed=False,historical_scores_changed=False,
        main_5000_reevaluation_started=False,go_no_go='NO-GO',production_sandbox_verified=False,
        production_reevaluation_resume_verified=False)
    (out/'sanity_report.json').write_text(json.dumps(report,indent=2)+'\n')
    manifest=dict(captured_at_utc=datetime.now(timezone.utc).isoformat(),evaluator_version=EVALUATOR_VERSION,versions={p:version(p) for p in ['qiskit','qiskit-aer','numpy']},
        files=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in map(Path,['harness/evaluator.py','harness/readout.py','harness/experiment.py',__file__])],
        artifacts=[dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
