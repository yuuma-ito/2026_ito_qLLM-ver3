"""Run paired generation/evaluation conditions and preserve round-level metrics."""
from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass, field
from typing import Any

from harness.code_extractor import extract_code
from harness.evaluator import EvalResult, evaluate
from harness.interventions import build_initial_prompt, build_intervention_prompt, intervention_feedback_type
from harness.llm_clients import Generation
from tasks import Task


@dataclass
class InitialAttempt:
    generation: Generation
    code: str
    evaluation: EvalResult | None
    seed: int


@dataclass
class RunRecord:
    model: str
    task_id: str
    seed: int
    raw_output: str
    extracted_code: str
    L0: bool
    L1: bool
    L2: bool
    structure_match: bool
    L3: bool
    L2_distance: float
    n_qubits_actual: int
    gate_count: int
    circuit_depth: int
    code_lines: int
    error_category: str
    error_message: str
    elapsed_sec: float
    tokens_in: int
    tokens_out: int
    mode: str = "baseline"
    intervention: str = "baseline"
    experiment_id: str = ""
    condition_id: str = "baseline"
    model_spec: str = ""
    task_difficulty: str = "medium"
    temperature: float = 0.7
    n_rounds: int = 1
    first_success_round: int = -1
    rounds: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    timeout_flag: bool = False
    final_success: bool = False
    code_diff_round0_final: str = ""
    metric_diff_round0_final: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "model_spec": self.model_spec or self.model,
            "task_id": self.task_id,
            "task_difficulty": self.task_difficulty,
            "seed": self.seed,
            "base_seed": self.seed,
            "temperature": self.temperature,
            "condition_id": self.condition_id,
            "intervention": self.intervention,
            "rounds": self.rounds,
            "L0": self.L0,
            "L1": self.L1,
            "L2": self.L2,
            "structure_match": self.structure_match,
            "L3": self.L3,
            "L2_distance": self.L2_distance,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens or (self.tokens_in + self.tokens_out),
            "elapsed_sec": self.elapsed_sec,
            "code_lines": self.code_lines,
            "gate_count": self.gate_count,
            "circuit_depth": self.circuit_depth,
            "first_success_round": self.first_success_round,
            "final_success": self.final_success,
            "timeout_flag": self.timeout_flag,
            "code_diff_round0_final": self.code_diff_round0_final,
            "metric_diff_round0_final": self.metric_diff_round0_final,
            "raw_output": self.raw_output,
            "extracted_code": self.extracted_code,
            "n_qubits_actual": self.n_qubits_actual,
            "n_rounds": self.n_rounds,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


def _code_lines(code: str) -> int:
    return len(code.splitlines()) if code else 0


def _metric_snapshot(ev: EvalResult | None, code: str) -> dict[str, Any]:
    if ev is None:
        return {"L0": False, "L1": False, "L2": False, "structure_match": False, "L3": False,
                "error_category": "api_timeout", "L2_distance": float("nan"),
                "code_lines": _code_lines(code), "gate_count": 0, "circuit_depth": 0}
    return {"L0": ev.L0, "L1": ev.L1, "L2": ev.L2, "structure_match": ev.structure_match,
            "L3": ev.L3, "error_category": ev.error_category, "L2_distance": ev.L2_distance,
            "code_lines": _code_lines(code), "gate_count": ev.gate_count, "circuit_depth": ev.circuit_depth}


def _metric_diff(initial: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    keys = ("L0", "L1", "L2", "structure_match", "L3", "error_category", "L2_distance",
            "code_lines", "gate_count", "circuit_depth")
    out = {}
    for key in keys:
        a, b = initial.get(key), final.get(key)
        delta = None
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
            if a == a and b == b:
                delta = b - a
        out[key] = {"from": a, "to": b, "delta": delta}
    return out


def _diff_code(initial: str, final: str) -> str:
    return "".join(difflib.unified_diff(initial.splitlines(keepends=True), final.splitlines(keepends=True),
                                        fromfile="round_0", tofile="final"))


def generate_initial(client, task: Task, seed: int, temperature: float = 0.7,
                     intervention: str = "baseline") -> InitialAttempt:
    gen: Generation = client.generate(user_prompt=build_initial_prompt(intervention, task), seed=seed,
                                      temperature=temperature, task=task)
    if gen.error:
        return InitialAttempt(gen, "", None, seed)
    code = extract_code(gen.raw_text)
    return InitialAttempt(gen, code, evaluate(code, task), seed)


def _round_meta(round_index: int, seed: int, gen: Generation, ev: EvalResult | None,
                feedback_type: str, code: str = "") -> dict[str, Any]:
    snap = _metric_snapshot(ev, code)
    if ev is None and not gen.timeout_flag:
        snap["error_category"] = "unknown_error"
    return {"round": round_index, "round_seed": seed, "feedback_type": feedback_type,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest() if code else "",
            "extracted_code": code, "actual_distribution": ev.actual_distribution if ev else None,
            **snap, "error_message": gen.error if gen.timeout_flag else (ev.error_message if ev else gen.error),
            "tokens_in": gen.tokens_in, "tokens_out": gen.tokens_out,
            "total_tokens": gen.tokens_in + gen.tokens_out, "elapsed_sec": gen.elapsed_sec,
            "timeout_flag": gen.timeout_flag, "generation_error": gen.error}


def _record(client, task: Task, initial: InitialAttempt, *, model_spec: str, experiment_id: str,
            condition_id: str, intervention: str, temperature: float,
            round_rows: list[dict[str, Any]] | None = None, total_in: int | None = None,
            total_out: int | None = None, elapsed: float | None = None,
            final_timeout: bool = False) -> RunRecord:
    gen, code, ev = initial.generation, initial.code, initial.evaluation
    rows = round_rows or [_round_meta(0, initial.seed, gen, ev, "none", code)]
    if final_timeout:
        final = EvalResult(error_category="api_timeout", error_message=gen.error)
        code = ""
    elif ev is None:
        final = EvalResult(error_category="api_timeout" if gen.timeout_flag else "unknown_error",
                           error_message=gen.error)
    else:
        final = ev
    # A timed-out correction is the final failed attempt but earlier history remains intact.
    if final_timeout:
        last = rows[-1]
        last.update({"L0": False, "L1": False, "L2": False, "structure_match": False, "L3": False,
                     "error_category": "api_timeout", "timeout_flag": True,
                     "L2_distance": float("nan"), "error_message": gen.error})
    initial_code = rows[0].get("extracted_code", "") if rows else code
    initial_meta = {key: rows[0].get(key) for key in (
        "L0", "L1", "L2", "structure_match", "L3", "error_category",
        "L2_distance", "code_lines", "gate_count", "circuit_depth")}
    final_meta = _metric_snapshot(final, code)
    all_tokens_in = gen.tokens_in if total_in is None else total_in
    all_tokens_out = gen.tokens_out if total_out is None else total_out
    total_elapsed = gen.elapsed_sec if elapsed is None else elapsed
    successful = [int(r["round"]) for r in rows if r.get("L3")]
    timeout_flag = final_timeout or any(r.get("timeout_flag") for r in rows)
    return RunRecord(
        model=client.model_id, model_spec=model_spec, task_id=task.id, seed=initial.seed,
        raw_output=gen.raw_text, extracted_code=code, L0=final.L0, L1=final.L1, L2=final.L2,
        structure_match=final.structure_match, L3=final.L3, L2_distance=final.L2_distance,
        n_qubits_actual=final.n_qubits_actual, gate_count=final.gate_count,
        circuit_depth=final.circuit_depth, code_lines=_code_lines(code), error_category=final.error_category,
        error_message=final.error_message, elapsed_sec=total_elapsed, tokens_in=all_tokens_in,
        tokens_out=all_tokens_out, total_tokens=all_tokens_in + all_tokens_out, mode=intervention,
        intervention=intervention, experiment_id=experiment_id, condition_id=condition_id,
        task_difficulty=task.task_difficulty, temperature=temperature, n_rounds=len(rows),
        first_success_round=min(successful) if successful else -1, rounds=rows,
        timeout_flag=timeout_flag, final_success=final.L3,
        code_diff_round0_final=_diff_code(initial_code, code),
        metric_diff_round0_final=_metric_diff(initial_meta, final_meta))


def run_one(client, task: Task, seed: int, temperature: float = 0.7, *, model_spec: str = "",
            experiment_id: str = "", condition_id: str = "baseline", initial: InitialAttempt | None = None) -> RunRecord:
    initial = initial or generate_initial(client, task, seed, temperature)
    return _record(client, task, initial, model_spec=model_spec, experiment_id=experiment_id,
                   condition_id=condition_id, intervention="baseline", temperature=temperature)


def run_intervention(client, task: Task, seed: int, intervention: str, max_rounds: int = 3,
                     temperature: float = 0.7, *, model_spec: str = "", experiment_id: str = "",
                     condition_id: str | None = None, initial: InitialAttempt | None = None) -> RunRecord:
    cid = condition_id or intervention
    if intervention == "baseline":
        return run_one(client, task, seed, temperature, model_spec=model_spec,
                       experiment_id=experiment_id, condition_id=cid, initial=initial)
    if intervention == "preventive_spec":
        attempt = generate_initial(client, task, seed, temperature, intervention=intervention)
        return _record(client, task, attempt, model_spec=model_spec, experiment_id=experiment_id,
                       condition_id=cid, intervention=intervention, temperature=temperature)
    if intervention not in {"self_refine", "execution_feedback", "self_debugging"}:
        raise ValueError(f"Unknown intervention: {intervention}")
    initial = initial or generate_initial(client, task, seed, temperature)
    base_rows = [_round_meta(0, seed, initial.generation, initial.evaluation, "none", initial.code)]
    if initial.evaluation is None or initial.generation.timeout_flag or initial.evaluation.L3:
        return _record(client, task, initial, model_spec=model_spec, experiment_id=experiment_id,
                       condition_id=cid, intervention=intervention, temperature=temperature, round_rows=base_rows)

    rows = list(base_rows)
    total_in, total_out, elapsed = initial.generation.tokens_in, initial.generation.tokens_out, initial.generation.elapsed_sec
    last_ev, last_code, last_gen = initial.evaluation, initial.code, initial.generation
    for correction_round in range(1, max_rounds + 1):
        prompt = build_intervention_prompt(intervention, task, last_code, last_ev)
        gen: Generation = client.generate(user_prompt=prompt, seed=seed + correction_round,
                                          temperature=temperature, task=task)
        total_in += gen.tokens_in; total_out += gen.tokens_out; elapsed += gen.elapsed_sec
        last_gen = gen
        if gen.error:
            rows.append(_round_meta(correction_round, seed + correction_round, gen, None,
                                    intervention_feedback_type(intervention), ""))
            failed_attempt = InitialAttempt(gen, "", None, seed)
            if gen.timeout_flag:
                return _record(client, task, failed_attempt, model_spec=model_spec, experiment_id=experiment_id,
                               condition_id=cid, intervention=intervention, temperature=temperature,
                               round_rows=rows, total_in=total_in, total_out=total_out, elapsed=elapsed,
                               final_timeout=True)
            return _record(client, task, failed_attempt, model_spec=model_spec, experiment_id=experiment_id,
                           condition_id=cid, intervention=intervention, temperature=temperature,
                           round_rows=rows, total_in=total_in, total_out=total_out, elapsed=elapsed)
        code = extract_code(gen.raw_text)
        ev = evaluate(code, task)
        rows.append(_round_meta(correction_round, seed + correction_round, gen, ev,
                                intervention_feedback_type(intervention), code))
        last_ev, last_code = ev, code
        if ev.L3:
            break
    final_attempt = InitialAttempt(last_gen, last_code, last_ev, seed)
    return _record(client, task, final_attempt, model_spec=model_spec, experiment_id=experiment_id,
                   condition_id=cid, intervention=intervention, temperature=temperature, round_rows=rows,
                   total_in=total_in, total_out=total_out, elapsed=elapsed)


def run_refine(client, task: Task, seed: int, max_rounds: int = 3, temperature: float = 0.7) -> RunRecord:
    rec = run_intervention(client, task, seed, "execution_feedback", max_rounds=max(0, max_rounds - 1), temperature=temperature, condition_id="refine")
    rec.mode = "refine"
    return rec
