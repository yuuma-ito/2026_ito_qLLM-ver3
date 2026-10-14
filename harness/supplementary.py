"""Partial auxiliary oracles, independent of task.mock_correct_code.

These diagnostics never modify the primary L0--L3 result.
"""
from __future__ import annotations

import numpy as np

SUPPLEMENT_VERSION = "coherent_oracles_v2"

ADDITIONAL_TASKS = {"T3a_DJ_constant": 3, "T3b_DJ_balanced": 3, "T4_BV_011": 4,
                    "T5_Grover_11": 2, "T8_QPE_001": 4, "T9_Ansatz_001": 2}


def _embed(matrix, qubit, width):
    result = np.array([[1]], complex)
    for q in reversed(range(width)):
        result = np.kron(result, matrix if q == qubit else np.eye(2))
    return result


def _cx(control, target, width):
    indices = np.arange(2 ** width)
    return np.eye(2 ** width)[:, indices ^ (((indices >> control) & 1) << target)]


def reference_operator(task_id):
    """Analytic prescribed whole circuit, no Qiskit/task mocks used."""
    n = ADDITIONAL_TASKS[task_id]
    h = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
    x = np.array([[0, 1], [1, 0]], complex)
    if task_id == "T9_Ansatz_001":
        def ry(theta):
            c, s = np.cos(theta / 2), np.sin(theta / 2)
            return np.array([[c, -s], [s, c]])
        return (_embed(ry(np.pi/5), 1, n) @ _embed(ry(np.pi/6), 0, n) @ _cx(0, 1, n)
                @ _embed(ry(np.pi/3), 1, n) @ _embed(ry(np.pi/4), 0, n))
    if task_id == "T5_Grover_11":
        uniform = np.ones(4) / 2
        diffusion = 2 * np.outer(uniform, uniform) - np.eye(4)
        return diffusion @ np.diag([1, 1, 1, -1]) @ np.kron(h, h)
    if task_id == "T8_QPE_001":
        counting_h = np.kron(np.kron(h, h), h)
        kickback = np.diag(np.exp(1j * (np.pi/2) * np.r_[np.zeros(8), np.arange(8)]))
        iqft = fourier_reference(3, inverse=True, include_preparation=False)
        return np.kron(np.eye(2), iqft) @ kickback @ np.kron(np.eye(2), counting_h) @ _embed(x, 3, n)
    initial = _embed(x, n - 1, n)
    for q in range(n):
        initial = _embed(h, q, n) @ initial
    oracle = np.eye(2 ** n)
    if task_id != "T3a_DJ_constant":
        oracle = _cx(1, n - 1, n) @ _cx(0, n - 1, n)
    final = np.eye(2 ** n)
    for q in range(n - 1):
        final = _embed(h, q, n) @ final
    return final @ oracle @ initial


def fidelity_cutoff(distance: float) -> float:
    """Exact conversion for normalized pure states, 0 < distance <= sqrt(2)."""
    if not 0 < distance <= np.sqrt(2):
        raise ValueError("pure-state distance must lie in (0, sqrt(2)]")
    return float((1 - distance * distance / 2) ** 2)


def pure_fidelity(actual, expected) -> float:
    a, b = np.asarray(actual, complex), np.asarray(expected, complex)
    if a.ndim != 1 or a.shape != b.shape:
        raise ValueError("matching pure-state vectors required")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("finite vectors required")
    if not np.isclose(np.vdot(a, a).real, 1, atol=1e-10, rtol=0) or not np.isclose(np.vdot(b, b).real, 1, atol=1e-10, rtol=0):
        raise ValueError("normalized vectors required")
    return float(np.clip(abs(np.vdot(a, b)) ** 2, 0, 1))


def coherent_operator_check(actual, expected, distance=0.05) -> dict:
    """All bases + both quadratures of every anchor-0 coherence.

    Exact equality on this set determines a unitary up to one global phase.
    At finite tolerance this is a partial diagnostic, not a diamond-norm bound.
    """
    a, b = np.asarray(actual, complex), np.asarray(expected, complex)
    if a.shape != b.shape or a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError("matching square operators required")
    n = len(a)
    for operator in (a, b):
        if not np.all(np.isfinite(operator)) or not np.allclose(operator.conj().T @ operator, np.eye(n), atol=1e-10, rtol=0):
            raise ValueError("unitary operators required")
    basis = np.eye(n, dtype=complex)
    probes = [(f"basis_{j}", basis[:, j]) for j in range(n)]
    probes += [(f"coherent_0_{j}_{phase}", (basis[:, 0] + value * basis[:, j]) / np.sqrt(2))
               for j in range(1, n) for phase, value in (("real", 1), ("imag", 1j))]
    scores = [(name, pure_fidelity(a @ state, b @ state)) for name, state in probes]
    cutoff = fidelity_cutoff(distance)
    worst = min(scores, key=lambda row: row[1])
    return {"status": "pass" if worst[1] > cutoff else "fail", "probe_count": len(probes),
            "minimum_fidelity": worst[1], "worst_probe": worst[0], "strict_fidelity_cutoff": cutoff,
            "process_fidelity": float(abs(np.trace(b.conj().T @ a) / n) ** 2)}


def fourier_reference(n_qubits: int, *, inverse=False, include_preparation=True):
    n = 2 ** n_qubits
    indices = np.arange(n)
    dft = np.exp((-1 if inverse else 1) * 2j * np.pi * np.outer(indices, indices) / n) / np.sqrt(n)
    # Whole build_circuit spec: input preparation X(q0), followed by DFT.
    return dft[:, indices ^ 1] if include_preparation else dft


def auxiliary_checks(qc, task_id: str, distance=0.05) -> dict:
    from qiskit.quantum_info import Operator, DensityMatrix
    out = {"version": SUPPLEMENT_VERSION, "changes_primary": False}
    if task_id in ADDITIONAL_TASKS:
        out["scope"] = "fixed_state_and_prescribed_whole_unitary"
        if qc.num_qubits != ADDITIONAL_TASKS[task_id] or any(item.operation.name == "measure" for item in qc.data):
            return {**out, "status": "not_applicable", "reason": "unmeasured expected-width circuit required"}
        expected_op = reference_operator(task_id)
        try:
            rho = DensityMatrix.from_instruction(qc).data
            expected = expected_op[:, 0]
            fid = float(np.clip(np.vdot(expected, rho @ expected).real, 0, 1))
            purity = float(np.trace(rho @ rho).real)
            pure = bool(np.isclose(purity, 1, atol=1e-10, rtol=0))
            state = {"fidelity": fid, "purity": purity, "strict_fidelity_cutoff": fidelity_cutoff(distance) if pure else None,
                     "status": ("pass" if fid > fidelity_cutoff(distance) else "fail") if pure else "diagnostic_only"}
            try:
                transform = coherent_operator_check(Operator(qc).data, expected_op, distance)
            except MemoryError:
                raise
            except Exception as error:
                transform = {"status": "not_applicable", "reason": type(error).__name__}
            return {**out, "status": state["status"], "state": state, "transform": transform}
        except MemoryError:
            raise
        except Exception as error:
            return {**out, "status": "not_applicable", "reason": type(error).__name__}
    if task_id in {"T6_QFT_001", "T7_IQFT_001"}:
        out["scope"] = "whole_preparation_plus_transform_unitary"
        if qc.num_qubits != 3:
            return {**out, "status": "not_applicable", "reason": "requires three qubits"}
        try:
            op = Operator(qc).data
            return {**out, **coherent_operator_check(op, fourier_reference(3, inverse=task_id.startswith("T7")), distance)}
        except Exception as error:
            return {**out, "status": "not_applicable", "reason": type(error).__name__}
    if task_id in {"T1_Bell", "T2_GHZ"}:
        n = 2 if task_id == "T1_Bell" else 3
        out["scope"] = "fixed_prepared_state_density_fidelity"
        if qc.num_qubits != n or any(item.operation.name == "measure" for item in qc.data):
            return {**out, "status": "not_applicable", "reason": "unmeasured expected-width circuit required"}
        expected = np.zeros(2 ** n, complex)
        expected[0] = expected[-1] = 1 / np.sqrt(2)
        try:
            rho = DensityMatrix.from_instruction(qc).data
            fid = float(np.clip(np.vdot(expected, rho @ expected).real, 0, 1))
            purity = float(np.trace(rho @ rho).real)
            # Mixed-state fidelity is reported, not converted to pure-state distance.
            pure = bool(np.isclose(purity, 1, atol=1e-10, rtol=0))
            return {**out, "fidelity": fid, "purity": purity,
                    "status": ("pass" if fid > fidelity_cutoff(distance) else "fail") if pure else "diagnostic_only",
                    "strict_fidelity_cutoff": fidelity_cutoff(distance) if pure else None}
        except Exception as error:
            return {**out, "status": "not_applicable", "reason": type(error).__name__}
    return {**out, "status": "not_implemented", "reason": "no independent auxiliary specification for this task"}
