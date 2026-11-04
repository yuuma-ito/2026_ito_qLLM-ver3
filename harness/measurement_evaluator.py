"""v4 output/structure evaluation plus the EXISTING system's measurement ban.

No state, unitary, algorithm, gate-count, or reference-conformance conditions
are added. The frozen v4 implementation remains in harness.evaluator.
"""
from __future__ import annotations

from dataclasses import replace

from harness.evaluator import (EvalResult, _exec_code, _try_build,
    evaluate_circuit as evaluate_circuit_v4, SIMULATOR_SEED,
    TRANSPILER_SEED, DISTRIBUTION_SHOTS)

EVALUATOR_VERSION = 'evaluation_policy_v4_measurement_ban_v1'
MEASUREMENT_FORBIDDEN_MESSAGE = 'in-circuit measurements are forbidden by the common system instruction'


class MeasurementInspectionError(ValueError):
    """Inspection could not establish whether a circuit satisfies the ban."""


def count_measurements(qc, *, max_nodes=100000, max_depth=64):
    """Count actual Measure instructions, including blocks/definitions.

    Inspect the circuit BEFORE the evaluator adds its own readout. Merely
    allocating classical bits, naming a gate 'measure', reset, initialization,
    or a different state/unitary is not an additional violation here.
    """
    from qiskit.circuit import Measure
    active=set(); visited=0
    def walk(circuit, depth):
        nonlocal visited
        if depth > max_depth or id(circuit) in active:
            raise MeasurementInspectionError('cyclic or excessively deep instruction definition')
        active.add(id(circuit))
        count=0
        try:
            for item in circuit.data:
                visited+=1
                if visited > max_nodes:
                    raise MeasurementInspectionError('instruction inspection budget exceeded')
                operation=item.operation
                if isinstance(operation, Measure):
                    count+=1
                    continue
                blocks=getattr(operation,'blocks',None)
                if blocks is not None:
                    count+=sum(walk(block,depth+1) for block in blocks)
                else:
                    definition=operation.definition
                    if definition is not None:
                        count+=walk(definition,depth+1)
            return count
        finally:
            active.remove(id(circuit))
    return walk(qc,0)


def apply_measurement_ban(original: EvalResult, measurement_count: int) -> EvalResult:
    if type(measurement_count) is not int or measurement_count < 0:
        raise ValueError('nonnegative integer measurement count required')
    result=replace(original)
    if measurement_count:
        result.structure_match=False
        result.L3=False
        # Preserve the diagnostic priority of already failing v4 attempts.
        # This makes the patch add a constraint without replacing an earlier
        # build/output error or silently changing existing failed feedback.
        if original.L3:
            result.failure_stage='evaluate'
            result.exception_type=''
            result.error_category='interface_mismatch'
            result.error_message=f'{MEASUREMENT_FORBIDDEN_MESSAGE} (count={measurement_count})'
    return result


def evaluate_circuit(qc, task, res=None):
    count=count_measurements(qc)
    old=evaluate_circuit_v4(qc,task,res)
    return apply_measurement_ban(old,count)


def evaluate(code, task):
    result=EvalResult()
    ok,namespace,category,message=_exec_code(code,result)
    if not ok:
        result.error_category,result.error_message=category,message
        return result
    result.L0=True
    circuit,category,message=_try_build(namespace,result)
    if circuit is None:
        result.error_category,result.error_message=category,message
        return result
    return evaluate_circuit(circuit,task,result)
