"""1 (model, task, seed) の生成・評価と介入ループ。

ver2 では初期生成を条件間で共有できるよう InitialAttempt を導入した。
これにより seed 非対応モデルでも baseline / 各介入が同じ初期コードから分岐する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib

from harness.code_extractor import extract_code
from harness.evaluator import EvalResult, evaluate
from harness.interventions import build_intervention_prompt, intervention_feedback_type
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
    L3: bool
    L2_distance: float
    n_qubits_actual: int
    gate_count: int
    error_category: str
    error_message: str
    elapsed_sec: float
    tokens_in: int
    tokens_out: int
    # 既存互換 + ver2 metadata
    mode: str = "baseline"
    intervention: str = "baseline"
    experiment_id: str = ""
    condition_id: str = "baseline"
    model_spec: str = ""
    base_seed: int | None = None
    n_rounds: int = 1
    first_success_round: int = -1
    rounds: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    estimated_cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "model": self.model,
            "model_spec": self.model_spec or self.model,
            "task_id": self.task_id,
            "seed": self.seed,
            "base_seed": self.seed if self.base_seed is None else self.base_seed,
            "raw_output": self.raw_output,
            "extracted_code": self.extracted_code,
            "L0": self.L0,
            "L1": self.L1,
            "L2": self.L2,
            "L3": self.L3,
            "L2_distance": self.L2_distance,
            "n_qubits_actual": self.n_qubits_actual,
            "gate_count": self.gate_count,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "elapsed_sec": self.elapsed_sec,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "total_tokens": self.total_tokens or (self.tokens_in + self.tokens_out),
            "estimated_cost_usd": self.estimated_cost_usd,
            "mode": self.mode,
            "intervention": self.intervention,
            "experiment_id": self.experiment_id,
            "condition_id": self.condition_id,
            "n_rounds": self.n_rounds,
            "first_success_round": self.first_success_round,
            "rounds": self.rounds,
        }
        return data


def generate_initial(client, task: Task, seed: int, temperature: float = 0.7) -> InitialAttempt:
    """条件間で共有する初期生成を 1 回だけ行う。"""
    gen: Generation = client.generate(
        user_prompt=task.prompt_text,
        seed=seed,
        temperature=temperature,
        task=task,
    )
    if gen.error:
        return InitialAttempt(generation=gen, code="", evaluation=None, seed=seed)
    code = extract_code(gen.raw_text)
    return InitialAttempt(generation=gen, code=code, evaluation=evaluate(code, task), seed=seed)


def _round_meta(
    round_index: int,
    seed: int,
    gen: Generation,
    ev: EvalResult | None,
    feedback_type: str,
    code: str = "",
) -> dict[str, Any]:
    if ev is None:
        return {
            "round": round_index,
            "round_seed": seed,
            "feedback_type": feedback_type,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest() if code else "",
            "extracted_code": code,
            "actual_distribution": None,
            "L0": False,
            "L1": False,
            "L2": False,
            "L3": False,
            "L2_distance": float("nan"),
            "error_category": "api_error",
            "error_message": gen.error,
            "tokens_in": gen.tokens_in,
            "tokens_out": gen.tokens_out,
            "total_tokens": gen.tokens_in + gen.tokens_out,
            "elapsed_sec": gen.elapsed_sec,
        }
    return {
        "round": round_index,
        "round_seed": seed,
        "feedback_type": feedback_type,
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest() if code else "",
        "extracted_code": code,
        "actual_distribution": ev.actual_distribution,
        "L0": ev.L0,
        "L1": ev.L1,
        "L2": ev.L2,
        "L3": ev.L3,
        "L2_distance": ev.L2_distance,
        "error_category": ev.error_category,
        "error_message": ev.error_message,
        "tokens_in": gen.tokens_in,
        "tokens_out": gen.tokens_out,
        "total_tokens": gen.tokens_in + gen.tokens_out,
        "elapsed_sec": gen.elapsed_sec,
    }


def _record_from_attempt(
    client,
    task: Task,
    initial: InitialAttempt,
    *,
    model_spec: str = "",
    experiment_id: str = "",
    condition_id: str = "baseline",
) -> RunRecord:
    gen = initial.generation
    ev = initial.evaluation
    if ev is None:
        return RunRecord(
            model=client.model_id,
            model_spec=model_spec,
            task_id=task.id,
            seed=initial.seed,
            base_seed=initial.seed,
            raw_output="",
            extracted_code="",
            L0=False,
            L1=False,
            L2=False,
            L3=False,
            L2_distance=float("nan"),
            n_qubits_actual=0,
            gate_count=0,
            error_category="api_error",
            error_message=gen.error,
            elapsed_sec=gen.elapsed_sec,
            tokens_in=gen.tokens_in,
            tokens_out=gen.tokens_out,
            total_tokens=gen.tokens_in + gen.tokens_out,
            mode="baseline",
            intervention="baseline",
            experiment_id=experiment_id,
            condition_id=condition_id,
            n_rounds=1,
            first_success_round=-1,
            rounds=[_round_meta(0, initial.seed, gen, None, "none", initial.code)],
        )
    return RunRecord(
        model=client.model_id,
        model_spec=model_spec,
        task_id=task.id,
        seed=initial.seed,
        base_seed=initial.seed,
        raw_output=gen.raw_text,
        extracted_code=initial.code,
        L0=ev.L0,
        L1=ev.L1,
        L2=ev.L2,
        L3=ev.L3,
        L2_distance=ev.L2_distance,
        n_qubits_actual=ev.n_qubits_actual,
        gate_count=ev.gate_count,
        error_category=ev.error_category,
        error_message=ev.error_message,
        elapsed_sec=gen.elapsed_sec,
        tokens_in=gen.tokens_in,
        tokens_out=gen.tokens_out,
        total_tokens=gen.tokens_in + gen.tokens_out,
        mode="baseline",
        intervention="baseline",
        experiment_id=experiment_id,
        condition_id=condition_id,
        n_rounds=1,
        first_success_round=0 if ev.L2 else -1,
        rounds=[_round_meta(0, initial.seed, gen, ev, "none", initial.code)],
    )


def run_one(
    client,
    task: Task,
    seed: int,
    temperature: float = 0.7,
    *,
    model_spec: str = "",
    experiment_id: str = "",
    condition_id: str = "baseline",
    initial: InitialAttempt | None = None,
) -> RunRecord:
    """baseline 1 サンプル実行。initial を渡すと共有初期生成を再利用する。"""
    initial = initial or generate_initial(client, task, seed, temperature)
    return _record_from_attempt(
        client,
        task,
        initial,
        model_spec=model_spec,
        experiment_id=experiment_id,
        condition_id=condition_id,
    )


def run_intervention(
    client,
    task: Task,
    seed: int,
    intervention: str,
    max_rounds: int = 3,
    temperature: float = 0.7,
    *,
    model_spec: str = "",
    experiment_id: str = "",
    condition_id: str | None = None,
    initial: InitialAttempt | None = None,
) -> RunRecord:
    """共有初期生成から介入を最大 max_rounds 回適用する。

    round 0 は初期生成、round 1..max_rounds が修正介入。
    round seed は base_seed + round とし、必ずログへ残す。
    """
    if intervention == "baseline":
        return run_one(
            client,
            task,
            seed,
            temperature,
            model_spec=model_spec,
            experiment_id=experiment_id,
            condition_id=condition_id or "baseline",
            initial=initial,
        )
    if intervention not in {"self_refine", "execution_feedback", "self_debugging"}:
        raise ValueError(f"Unknown intervention: {intervention}")

    initial = initial or generate_initial(client, task, seed, temperature)
    base = _record_from_attempt(
        client,
        task,
        initial,
        model_spec=model_spec,
        experiment_id=experiment_id,
        condition_id=condition_id or intervention,
    )
    base.mode = intervention
    base.intervention = intervention
    base.condition_id = condition_id or intervention

    # 初回 API エラー / 初回 L2 成功なら介入不要
    if initial.evaluation is None or initial.evaluation.L2:
        base.rounds[0]["feedback_type"] = "none"
        return base

    rounds_meta = list(base.rounds)
    total_in = base.tokens_in
    total_out = base.tokens_out
    total_elapsed = base.elapsed_sec
    first_success = -1
    last_gen = initial.generation
    last_code = initial.code
    last_ev = initial.evaluation
    used = 1

    for correction_round in range(1, max_rounds + 1):
        prompt = build_intervention_prompt(intervention, task, last_code, last_ev)
        round_seed = seed + correction_round
        gen: Generation = client.generate(
            user_prompt=prompt,
            seed=round_seed,
            temperature=temperature,
            task=task,
        )
        used += 1
        total_in += gen.tokens_in
        total_out += gen.tokens_out
        total_elapsed += gen.elapsed_sec

        if gen.error:
            rounds_meta.append(
                _round_meta(
                    correction_round,
                    round_seed,
                    gen,
                    None,
                    intervention_feedback_type(intervention),
                    "",
                )
            )
            break

        code = extract_code(gen.raw_text)
        ev = evaluate(code, task)
        rounds_meta.append(
            _round_meta(
                correction_round,
                round_seed,
                gen,
                ev,
                intervention_feedback_type(intervention),
                code,
            )
        )
        last_gen, last_code, last_ev = gen, code, ev
        if ev.L2:
            first_success = correction_round
            break

    return RunRecord(
        model=client.model_id,
        model_spec=model_spec,
        task_id=task.id,
        seed=seed,
        base_seed=seed,
        raw_output=last_gen.raw_text,
        extracted_code=last_code,
        L0=last_ev.L0,
        L1=last_ev.L1,
        L2=last_ev.L2,
        L3=last_ev.L3,
        L2_distance=last_ev.L2_distance,
        n_qubits_actual=last_ev.n_qubits_actual,
        gate_count=last_ev.gate_count,
        error_category=last_ev.error_category,
        error_message=last_ev.error_message,
        elapsed_sec=total_elapsed,
        tokens_in=total_in,
        tokens_out=total_out,
        total_tokens=total_in + total_out,
        mode=intervention,
        intervention=intervention,
        experiment_id=experiment_id,
        condition_id=condition_id or intervention,
        n_rounds=used,
        first_success_round=first_success,
        rounds=rounds_meta,
    )


def run_refine(
    client,
    task: Task,
    seed: int,
    max_rounds: int = 3,
    temperature: float = 0.7,
) -> RunRecord:
    """ver1 互換ラッパー。

    ver1 の max_rounds は「初期生成を含む総生成回数」だったため、
    ver2 の execution_feedback に max_rounds-1 回の修正として写像する。
    """
    corrections = max(0, max_rounds - 1)
    rec = run_intervention(
        client,
        task,
        seed,
        intervention="execution_feedback",
        max_rounds=corrections,
        temperature=temperature,
        condition_id="refine",
    )
    rec.mode = "refine"
    rec.intervention = "execution_feedback"
    return rec
