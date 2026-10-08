"""Evaluate generated Qiskit code and separate semantic from structural validity."""
from __future__ import annotations

import dataclasses
import inspect
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from harness.failure_metadata import missing_counts_result
from tasks import Task


@dataclass
class EvalResult:
    L0: bool = False
    L1: bool = False
    L2: bool = False
    structure_match: bool = False
    L3: bool = False
    L2_distance: float = float("nan")
    gate_count: int = 0
    circuit_depth: int = 0
    n_qubits_actual: int = 0
    n_clbits_actual: int = 0
    error_category: str = ""
    error_message: str = ""
    failure_stage: str = "unknown"
    exception_type: str = ""
    actual_distribution: Optional[dict[str, float]] = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _inside_build(error: Exception, ns: dict) -> bool:
    function_code = getattr(ns.get("build_circuit"), "__code__", None)
    tb = error.__traceback__
    while tb is not None:
        if function_code is not None and tb.tb_frame.f_code is function_code:
            return True
        tb = tb.tb_next
    return False


def _exec_code(code: str, res: EvalResult) -> tuple[bool, dict, str, str]:
    ns: dict = {}
    res.failure_stage = "parse"
    try:
        compiled = compile(code, "<generated>", "exec")
    except SyntaxError as e:
        res.exception_type = type(e).__name__
        return False, ns, "syntax", str(e)
    res.failure_stage = "exec"
    try:
        exec(compiled, ns)
    except ImportError as e:
        res.failure_stage = "build" if _inside_build(e, ns) else "import"
        res.exception_type = type(e).__name__
        return False, ns, "build_error" if res.failure_stage == "build" else "import_error", str(e)
    except Exception as e:
        res.exception_type = type(e).__name__
        if _inside_build(e, ns):
            res.failure_stage = "build"
            cat = "build_error"
        else:
            cat = "interface_mismatch" if isinstance(e, AttributeError) or missing_counts_result(type(e).__name__, str(e)) else "unknown_error"
        return False, ns, cat, f"{type(e).__name__}: {e}"
    if "build_circuit" not in ns or not callable(ns["build_circuit"]):
        return False, ns, "interface_mismatch", "build_circuit() is missing or not callable"
    try:
        sig = inspect.signature(ns["build_circuit"])
        if any(p.default is inspect.Parameter.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) for p in sig.parameters.values()):
            return False, ns, "interface_mismatch", "build_circuit() requires arguments"
    except (TypeError, ValueError):
        pass
    return True, ns, "", ""


def _try_build(ns: dict, res: EvalResult) -> tuple[Optional[Any], str, str]:
    res.failure_stage = "build"
    try:
        qc = ns["build_circuit"]()
    except Exception as e:
        res.exception_type = type(e).__name__
        return None, "build_error", f"{type(e).__name__}: {e}"
    from qiskit import QuantumCircuit
    if not isinstance(qc, QuantumCircuit):
        return None, "interface_mismatch", "build_circuit() must return QuantumCircuit"
    return qc, "", ""


def _run_distribution(qc, shots: int = 8192) -> dict[str, float]:
    from qiskit import transpile
    from qiskit_aer import AerSimulator
    qc_meas = qc.copy()
    # Preserve an explicitly measured circuit. Add measurements only when the
    # generated circuit has none, so existing classical registers are not doubled.
    if not any(item.operation.name == "measure" for item in qc_meas.data):
        qc_meas.measure_all()
    sim = AerSimulator()
    tqc = transpile(qc_meas, sim)
    counts = sim.run(tqc, shots=shots).result().get_counts()
    total = sum(counts.values())
    return {k.replace(" ", ""): v / total for k, v in counts.items()}


def _run_statevector(qc) -> np.ndarray:
    from qiskit.quantum_info import Statevector
    return Statevector.from_instruction(qc).data


def _tvd(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def _statevector_distance(actual: np.ndarray, expected: np.ndarray) -> float:
    inner = np.vdot(actual, expected)
    if abs(inner) < 1e-12:
        return float(np.linalg.norm(actual - expected))
    return float(np.linalg.norm(np.exp(-1j * np.angle(inner)) * actual - expected))


def _bit_reversed_distribution(dist: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for bits, prob in dist.items():
        out[bits[::-1]] = out.get(bits[::-1], 0.0) + prob
    return out


def evaluate(code: str, task: Task) -> EvalResult:
    res = EvalResult()
    ok, ns, cat, msg = _exec_code(code, res)
    if not ok:
        res.error_category, res.error_message = cat, msg
        return res
    res.L0 = True
    qc, cat, msg = _try_build(ns, res)
    if qc is None:
        res.error_category, res.error_message = cat, msg
        return res

    try:
        res.n_qubits_actual = qc.num_qubits
        res.n_clbits_actual = qc.num_clbits
        res.gate_count = len(qc.data)
        res.circuit_depth = int(qc.depth() or 0)
    except Exception as e:
        res.exception_type = type(e).__name__
        res.error_category, res.error_message = "build_error", f"{type(e).__name__}: {e}"
        return res

    res.failure_stage = "evaluate"
    measurement_count = sum(item.operation.name == "measure" for item in qc.data)
    structural_gate_count = sum(item.operation.name != "measure" for item in qc.data)
    structure_errors: list[str] = []
    if res.n_qubits_actual != task.n_qubits:
        res.error_category = "qubit_count_mismatch"
        res.error_message = f"expected {task.n_qubits} qubits, got {res.n_qubits_actual}"
        structure_errors.append(res.error_message)

    if task.expected_classical_bits is not None and res.n_clbits_actual != task.expected_classical_bits:
        structure_errors.append(
            f"expected {task.expected_classical_bits} classical bits, got {res.n_clbits_actual}"
        )
    if task.expected_measurement_count is not None and measurement_count != task.expected_measurement_count:
        structure_errors.append(
            f"expected {task.expected_measurement_count} measurements, got {measurement_count}"
        )
    if task.measurement_required is True and measurement_count == 0:
        structure_errors.append("task requires in-circuit measurements")
    elif task.measurement_required is False and measurement_count > 0:
        structure_errors.append("task does not allow in-circuit measurements")
    if structure_errors and not res.error_message:
        res.error_category = "qubit_count_mismatch"
        res.error_message = "; ".join(structure_errors)

    # Only enforce classical-bit/measurement constraints when task metadata
    # explicitly supplies them. Unspecified requirements are unconstrained.
    res.structure_match = not structure_errors
    if task.expected_gate_count_range is not None:
        lo, hi = task.expected_gate_count_range
        # Existing task ranges describe circuit gates, not readout operations.
        res.structure_match = res.structure_match and lo <= structural_gate_count <= hi

    try:
        if task.expected_kind == "distribution":
            actual = _run_distribution(qc)
            res.actual_distribution = actual
            res.L1 = True
            expected = task.expected_distribution or {}
            res.L2_distance = _tvd(actual, expected)
            if res.L2_distance >= task.threshold:
                reverse_distance = _tvd(actual, _bit_reversed_distribution(expected))
                if reverse_distance < task.threshold and res.error_category != "qubit_count_mismatch":
                    res.error_category = "bit_order_error"
                    res.error_message = f"distribution matches bit-reversed expectation (TVD={reverse_distance:.6g})"
        elif task.expected_kind == "statevector":
            actual_sv = _run_statevector(qc)
            expected_sv = np.array(task.expected_statevector, dtype=complex)
            res.L1 = True
            res.L2_distance = _statevector_distance(actual_sv, expected_sv) if actual_sv.shape == expected_sv.shape else float("inf")
        else:
            res.error_category, res.error_message = "unknown_error", f"unknown expected_kind: {task.expected_kind}"
            return res
    except Exception as e:
        res.exception_type = type(e).__name__
        res.error_category, res.error_message = "unknown_error", f"{type(e).__name__}: {e}"
        return res

    res.L2 = res.L2_distance < task.threshold
    res.L3 = res.L0 and res.L1 and res.L2 and res.structure_match
    if res.error_category == "":
        if res.n_qubits_actual != task.n_qubits:
            res.error_category = "qubit_count_mismatch"
        elif not res.L2:
            res.error_category, res.error_message = "wrong_output", "output differs from expected result"
        elif not res.structure_match:
            res.error_category, res.error_message = "unknown_error", "circuit structure is outside the accepted bounds"
        else:
            res.error_category = "ok"
    if res.error_category == "ok":
        res.failure_stage = "unknown"
    return res
