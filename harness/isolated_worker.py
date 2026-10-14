"""Private worker: builder never shares an interpreter with the oracle."""
import json
import math
from pathlib import Path
import sys
import tempfile

from harness.sandbox_policy import install


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return value


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    output = Path(request["output"])
    # dill queries gettempdir() during Qiskit import. Cache the designated path
    # before restrictions; creating arbitrary scratch files remains forbidden.
    tempfile.tempdir = str(output)
    try:
        attestation = install(request["read_paths"], request["write_paths"], request["limits"])
    except Exception as error:
        (output / "result.json").write_text(json.dumps({"runtime_status": "isolation_failure", "reason": type(error).__name__ + ": " + str(error)}))
        return
    # Proof of installation is emitted before any generated-code execution.
    (output / "isolation.json").write_text(json.dumps(attestation))
    from qiskit import qpy
    from harness.evaluator import EvalResult, _exec_code, _try_build, evaluate_circuit
    if request["stage"] == "build":
        res = EvalResult()
        ok, ns, category, message = _exec_code(request["code"], res)
        if ok:
            res.L0 = True
            qc, category, message = _try_build(ns, res)
        else:
            qc = None
        if qc is None:
            res.error_category, res.error_message = category, message
            if res.exception_type in {"MemoryError", "PermissionError"}:
                result = {"runtime_status": "memory_limit" if res.exception_type == "MemoryError" else "policy_denied", "stage": "build"}
            else:
                result = {"runtime_status": "completed", "primary": res.to_dict(), "auxiliary": {"status": "not_applicable", "reason": "no circuit"}}
        elif qc.num_qubits > 8 or qc.num_clbits > 64 or len(qc.data) > 10000:
            result = {"runtime_status": "circuit_limit", "reason": "bounded QPY oracle input exceeded"}
        else:
            with (output / "circuit.qpy").open("wb") as handle:
                qpy.dump(qc, handle)
            result = {"runtime_status": "built"}
    else:
        from tasks import get_task
        from harness.supplementary import auxiliary_checks
        with Path(request["qpy_path"]).open("rb") as handle:
            circuits = qpy.load(handle)
        if len(circuits) != 1:
            raise ValueError("exactly one QPY circuit required")
        qc = circuits[0]
        if qc.num_qubits > 8 or qc.num_clbits > 64 or len(qc.data) > 10000 or qc.parameters:
            raise ValueError("QPY circuit bounds exceeded")
        task = get_task(request["task_id"])
        primary = evaluate_circuit(qc, task)
        if primary.exception_type in {"MemoryError", "PermissionError"}:
            result = {"runtime_status": "memory_limit" if primary.exception_type == "MemoryError" else "policy_denied", "stage": "oracle"}
        else:
            result = {"runtime_status": "completed", "primary": primary.to_dict(),
                      "auxiliary": auxiliary_checks(qc, task.id, task.threshold)}
    (output / "result.json").write_text(json.dumps(clean(result), allow_nan=False))


if __name__ == "__main__":
    main()
