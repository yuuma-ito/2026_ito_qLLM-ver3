"""Opt-in reference conformance for already constructed, trusted circuits.

This is a NEW specification, not a replacement for historical policy_v4 L3.
It never imports or executes a generated Python program. Untrusted QPY must
be loaded and checked in an isolated worker, not in the calling process.
"""
from __future__ import annotations

import numpy as np

from harness.supplementary import fourier_reference, reference_operator

REFERENCE_VERSION = 'reference_conformance_v1'
WIDTHS = {'T1_Bell': 2, 'T2_GHZ': 3, 'T3a_DJ_constant': 3,
          'T3b_DJ_balanced': 3, 'T4_BV_011': 4, 'T5_Grover_11': 2,
          'T6_QFT_001': 3, 'T7_IQFT_001': 3, 'T8_QPE_001': 4,
          'T9_Ansatz_001': 2}


def operator_distance(actual, expected):
    """Spectral distance after one trace-based global-phase alignment.

    A distance < epsilon bounds the state-vector difference for every unit
    input by epsilon, with this SAME global phase. This is a sufficient
    finite-tolerance check, not a proof of exact operator equality or the
    phase minimizing the spectral norm. Standalone circuit phases only;
    the contract does not allow dropping branch phases in controlled gates.
    """
    a, b = np.asarray(actual, complex), np.asarray(expected, complex)
    if a.ndim != 2 or a.shape != b.shape or a.shape[0] != a.shape[1]:
        raise ValueError('matching square matrices required')
    for matrix in (a, b):
        if not np.all(np.isfinite(matrix)) or not np.allclose(
                matrix.conj().T @ matrix, np.eye(len(matrix)), atol=1e-10, rtol=0):
            raise ValueError('finite unitary matrices required')
    overlap = np.vdot(a, b)
    aligned = a * np.exp(1j * np.angle(overlap))
    return float(np.linalg.norm(aligned - b, ord=2))


def _contains_measurement(qc, active=None):
    """Include measurements hidden inside composite instructions."""
    active = set() if active is None else active
    if id(qc) in active:
        raise ValueError('cyclic instruction definition')
    active.add(id(qc))
    try:
        for item in qc.data:
            op = item.operation
            if op.name == 'measure':
                return True
            definition = op.definition
            if definition is not None and _contains_measurement(definition, active):
                return True
        return False
    finally:
        active.remove(id(qc))


def check_reference(qc, task_id, threshold=0.05):
    """For Bell/GHZ check the prepared pure state, otherwise whole unitary.

    No measurements, resets, initializations or classical operations are
    accepted. Arbitrary gate-count windows are deliberately NOT used: an
    equivalent composite gate must receive the same mathematical result.
    Whole-unitary conformance is stronger than several original fixed-input
    task specifications; the names and results must remain separate.
    """
    from qiskit.quantum_info import Operator
    from qiskit.exceptions import QiskitError

    if task_id not in WIDTHS:
        raise ValueError('no reference specification for task: ' + task_id)
    if not np.isfinite(threshold) or not 0 < threshold <= 0.05:
        raise ValueError('threshold must be finite and in (0, 0.05]')
    out = {'version': REFERENCE_VERSION, 'task_id': task_id,
           'changes_historical_L3': False, 'threshold': float(threshold),
           'scope': 'prepared_pure_state' if task_id in {'T1_Bell', 'T2_GHZ'}
                    else 'whole_unitary_with_input_preparation'}
    if qc.num_qubits != WIDTHS[task_id]:
        return {**out, 'status': 'fail', 'reason': 'qubit_count_mismatch'}
    if qc.parameters:
        return {**out, 'status': 'fail', 'reason': 'unbound_parameters'}
    try:
        if _contains_measurement(qc):
            return {**out, 'status': 'fail', 'reason': 'measurement_forbidden'}
        actual = Operator(qc).data
    except QiskitError:
        return {**out, 'status': 'fail', 'reason': 'unitary_circuit_required'}
    except ValueError:
        return {**out, 'status': 'fail', 'reason': 'invalid_instruction_definition'}
    # Operator also accepts nonunitary matrices. Check every task, including
    # the state-only Bell/GHZ branch, before inspecting the first column.
    if not np.all(np.isfinite(actual)) or not np.allclose(
            actual.conj().T @ actual, np.eye(len(actual)), atol=1e-10, rtol=0):
        return {**out, 'status': 'fail', 'reason': 'unitary_circuit_required'}
    if task_id in {'T1_Bell', 'T2_GHZ'}:
        expected = np.zeros(2**qc.num_qubits, complex)
        expected[0] = expected[-1] = 1/np.sqrt(2)
        state = actual[:, 0]
        aligned = state * np.exp(1j*np.angle(np.vdot(state, expected)))
        distance = float(np.linalg.norm(aligned-expected))
        metric = 'prepared_state_distance'
    else:
        if task_id in {'T6_QFT_001', 'T7_IQFT_001'}:
            expected = fourier_reference(3, inverse=task_id.startswith('T7'))
        else:
            expected = reference_operator(task_id)
        distance = operator_distance(actual, expected)
        metric = 'aligned_operator_spectral_distance'
    return {**out, 'status': 'pass' if distance < threshold else 'fail',
            'reason': 'reference_match' if distance < threshold else 'reference_mismatch',
            'distance': distance, 'metric': metric}
