"""Measurement-only impact worker; never imports reference-conformance checks."""
import json
from pathlib import Path
import sys
import tempfile

from harness.sandbox_policy import install
from harness.isolated_worker import clean


def main():
    request=json.loads(Path(sys.argv[1]).read_text())
    output=Path(request['output'])
    tempfile.tempdir=str(output)
    try:
        attestation=install(request['read_paths'],request['write_paths'],request['limits'])
    except Exception as error:
        (output/'result.json').write_text(json.dumps({'runtime_status':'isolation_failure','reason':type(error).__name__}))
        return
    (output/'isolation.json').write_text(json.dumps(attestation))
    from qiskit import qpy
    from harness.evaluator import EvalResult, _exec_code, _try_build, evaluate_circuit
    from harness.measurement_evaluator import (count_measurements, apply_measurement_ban,
                                              MeasurementInspectionError, EVALUATOR_VERSION)
    if request['stage']=='build':
        result=EvalResult()
        ok,namespace,category,message=_exec_code(request['code'],result)
        if ok:
            result.L0=True
            qc,category,message=_try_build(namespace,result)
        else:qc=None
        if qc is None:
            result.error_category,result.error_message=category,message
            if result.exception_type in {'MemoryError','PermissionError'}:
                data={'runtime_status':'memory_limit' if result.exception_type=='MemoryError' else 'policy_denied'}
            else:data={'runtime_status':'completed','primary':result.to_dict()}
        elif qc.num_qubits>8 or qc.num_clbits>64 or len(qc.data)>10000:
            data={'runtime_status':'circuit_limit'}
        else:
            with (output/'circuit.qpy').open('wb') as f:qpy.dump(qc,f)
            data={'runtime_status':'built'}
    elif request['stage']=='oracle':
        from tasks import get_task
        with Path(request['qpy_path']).open('rb') as f:circuits=qpy.load(f)
        if len(circuits)!=1:raise ValueError('one circuit required')
        qc=circuits[0]
        if qc.num_qubits>8 or qc.num_clbits>64 or len(qc.data)>10000 or qc.parameters:
            data={'runtime_status':'circuit_limit'}
        else:
            try:count=count_measurements(qc)
            except Exception as error:
                # Inspection problems are unresolved runtime results, never a
                # successful absence of measurements or a scored model error.
                data={'runtime_status':'measurement_inspection_failure','exception_type':type(error).__name__}
            else:
                old=evaluate_circuit(qc,get_task(request['task_id']))
                if old.exception_type in {'MemoryError','PermissionError'}:
                    data={'runtime_status':'memory_limit' if old.exception_type=='MemoryError' else 'policy_denied'}
                else:
                    data={'runtime_status':'completed','measurement_count':count,'measurement_violation':bool(count),
                          'old_primary':old.to_dict(),'primary':apply_measurement_ban(old,count).to_dict(),
                          'evaluator_version':EVALUATOR_VERSION,'scope':'v4_plus_common_system_measurement_ban_only'}
    else:raise ValueError('unknown stage')
    (output/'result.json').write_text(json.dumps(clean(data),allow_nan=False))


if __name__=='__main__':main()
