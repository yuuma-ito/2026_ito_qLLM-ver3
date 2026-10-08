"""ver2 実験オーケストレーション支援。

設定検証、manifest、resume、cost 推定、sanity check 用の共通関数を提供する。
"""
from __future__ import annotations

from harness.failure_metadata import normalize_record

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

from harness.evaluator import EvalResult
from harness.interventions import INTERVENTIONS
from harness.llm_clients import Generation, OLLAMA_CONNECTION_RETRY_DELAYS
from harness.runner import InitialAttempt, RunRecord
from tasks import all_tasks, get_task


@dataclass(frozen=True)
class Condition:
    id: str
    intervention: str
    max_rounds: int = 3


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError("YAML config requires PyYAML; install requirements.txt") from e
        return yaml.safe_load(text)
    raise ValueError("Config must be .json, .yaml, or .yml")


def normalized_config(config: dict[str, Any]) -> dict[str, Any]:
    """hash 用に辞書を JSON round-trip して正規化する。"""
    return json.loads(json.dumps(config, ensure_ascii=False, sort_keys=True))


def config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(normalized_config(config), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def parse_conditions(config: dict[str, Any]) -> list[Condition]:
    raw = config.get("conditions") or list(INTERVENTIONS)
    out: list[Condition] = []
    default_rounds = int(config.get("max_rounds", 3))
    for item in raw:
        if isinstance(item, str):
            intervention = item
            cid = item
            rounds = 0 if item in {"baseline", "preventive_spec"} else default_rounds
        else:
            intervention = item["intervention"]
            cid = item.get("id", intervention)
            rounds = int(item.get("max_rounds", 0 if intervention in {"baseline", "preventive_spec"} else default_rounds))
        if intervention not in INTERVENTIONS:
            raise ValueError(f"Unknown intervention in config: {intervention}")
        if rounds < 0:
            raise ValueError(f"max_rounds must be >= 0: {cid}")
        out.append(Condition(cid, intervention, rounds))
    ids = [c.id for c in out]
    if len(ids) != len(set(ids)):
        raise ValueError("condition IDs must be unique")
    if not any(c.intervention == "baseline" for c in out):
        raise ValueError("conditions must include baseline so initial generations can be paired")
    for cond in out:
        if cond.intervention in {"baseline", "preventive_spec"} and cond.max_rounds != 0:
            raise ValueError(f"{cond.intervention} must have max_rounds=0")
    return out


def resolve_tasks(config: dict[str, Any]):
    raw = config.get("tasks", "all")
    if raw == "all" or raw is None:
        return all_tasks()
    return [get_task(tid) for tid in raw]


def resolve_seeds(config: dict[str, Any]) -> list[int]:
    raw = config.get("seeds", {"start": 0, "stop": 1})
    if isinstance(raw, int):
        return list(range(raw))
    if isinstance(raw, list):
        return [int(x) for x in raw]
    start = int(raw.get("start", 0))
    stop = int(raw["stop"])
    step = int(raw.get("step", 1))
    if step <= 0 or stop <= start:
        raise ValueError("invalid seeds range")
    return list(range(start, stop, step))


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    exp_id = str(config.get("experiment_id", "")).strip()
    if not exp_id:
        raise ValueError("experiment_id is required")
    models = config.get("models") or []
    if not isinstance(models, list) or not models:
        raise ValueError("models must be a non-empty list")
    conditions = parse_conditions(config)
    tasks = resolve_tasks(config)
    seeds = resolve_seeds(config)
    if not tasks or not seeds:
        raise ValueError("At least one task and seed are required")
    if (len(models) != len(set(models)) or len(tasks) != len({t.id for t in tasks})
            or len(seeds) != len(set(seeds))):
        raise ValueError("models, tasks and seeds must not contain duplicates")
    grid = {(m, t.id, s) for m in models for t in tasks for s in seeds}
    pairs = grid
    if "pairs" in config:
        raw_pairs = config["pairs"]
        if not isinstance(raw_pairs, list) or not raw_pairs:
            raise ValueError("pairs must be a non-empty list")
        requested = [(p["model"], p["task"], int(p["seed"])) for p in raw_pairs]
        pairs = set(requested)
        if len(pairs) != len(requested) or not pairs.issubset(grid):
            raise ValueError("pairs must be unique members of the configured model/task/seed grid")
    temperature = float(config.get("temperature", 0.7))
    if temperature < 0:
        raise ValueError("temperature must be >= 0")
    return {
        "experiment_id": exp_id,
        "models": models,
        "conditions": conditions,
        "tasks": tasks,
        "seeds": seeds,
        "temperature": temperature,
        "pair_keys": pairs,
        "planned_records": len(pairs) * len(conditions),
        "planned_initial_generations": len(pairs),
    }



def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _pkg_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _git_commit(repo: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def build_manifest(config: dict[str, Any], repo_root: str | Path) -> dict[str, Any]:
    v = validate_config(config)
    repo_root = Path(repo_root)
    return {
        "schema_version": "2.1",
        "experiment_id": v["experiment_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_hash": config_hash(config),
        "shared_initial_generation": "shared by correction conditions; preventive_spec generates independently",
        "transport_recovery": {
            "ollama_connection_retry_delays_sec": list(OLLAMA_CONNECTION_RETRY_DELAYS),
            "preserve_seed": True, "retry_timeouts": False,
            "stop_after_unrecovered_transport_failure": True,
        },
        "config": normalized_config(config),
        "planned": {
            "records": v["planned_records"],
            "unique_initial_generations": v["planned_initial_generations"],
            "models": len(v["models"]),
            "tasks": len(v["tasks"]),
            "seeds": len(v["seeds"]),
            "conditions": len(v["conditions"]),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "qiskit": _pkg_version("qiskit"),
            "qiskit_aer": _pkg_version("qiskit-aer"),
            "openai": _pkg_version("openai"),
            "anthropic": _pkg_version("anthropic"),
            "google_generativeai": _pkg_version("google-generativeai"),
        },
        "git_commit": _git_commit(repo_root),
        "prompt_fingerprints": {
            "system_txt_sha256": _file_sha256(repo_root / "prompts" / "system.txt"),
            "interventions_py_sha256": _file_sha256(repo_root / "harness" / "interventions" / "prompts.py"),
        },
    }


def record_key(rec: dict[str, Any]) -> tuple[str, str, str, str, int]:
    return (
        rec.get("experiment_id", ""),
        rec.get("condition_id", rec.get("mode", "baseline")),
        rec.get("model_spec", rec.get("model", "")),
        rec["task_id"],
        int(rec.get("base_seed", rec.get("seed", 0))),
    )


def expected_keys(plan: dict) -> set[tuple]:
    return {(plan["experiment_id"], c.id, m, t, s)
            for c in plan["conditions"] for m, t, s in plan["pair_keys"]}


def has_api_failure(row: dict, *, include_unknown=True) -> bool:
    row = normalize_record(row)
    categories = {"api_error", "api_timeout"} | ({"unknown_error"} if include_unknown else set())
    return any(attempt.get("generation_error") or attempt.get("timeout_flag") or
               attempt.get("error_category") in categories
               for attempt in [row, *row.get("rounds", [])])


def load_existing(path: str | Path) -> tuple[list[dict[str, Any]], set[tuple[str, str, str, str, int]]]:
    path = Path(path)
    if not path.exists():
        return [], set()
    rows: list[dict[str, Any]] = []
    keys = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = normalize_record(json.loads(line))
            rows.append(rec)
            keys.add(record_key(rec))
    return rows, keys


def initial_from_baseline_record(rec: dict[str, Any], task) -> InitialAttempt:
    """resume 時に baseline JSONL から共有初期生成を復元する。"""
    rec = normalize_record(rec)
    gen = Generation(
        raw_text=rec.get("raw_output", ""),
        tokens_in=int(rec.get("tokens_in", 0)),
        tokens_out=int(rec.get("tokens_out", 0)),
        elapsed_sec=float(rec.get("elapsed_sec", 0.0)),
        model_id=rec.get("model", ""),
        error=rec.get("error_message", "") if rec.get("error_category") in {"api_error", "api_timeout"} else "",
        timeout_flag=bool(rec.get("timeout_flag", False)),
    )
    rounds = rec.get("rounds") or []
    r0 = rounds[0] if rounds else {}
    gen.connection_retries = int(r0.get("connection_retries", 0))
    gen.exception_type = str(r0.get("exception_type", "")) if r0.get("failure_stage") == "api_call" else ""
    gen.error = r0.get("generation_error") or gen.error
    code = r0.get("extracted_code", rec.get("extracted_code", ""))
    if gen.error:
        ev = None
    else:
        ev = EvalResult(
            L0=bool(r0.get("L0", rec.get("L0", False))),
            L1=bool(r0.get("L1", rec.get("L1", False))),
            L2=bool(r0.get("L2", rec.get("L2", False))),
            structure_match=bool(r0.get("structure_match", rec.get("structure_match", False))),
            L3=bool(r0.get("L3", rec.get("L3", False))),
            L2_distance=float(r0.get("L2_distance", rec.get("L2_distance", float("nan")))),
            gate_count=int(rec.get("gate_count", 0)),
            circuit_depth=int(rec.get("circuit_depth", 0)),
            n_qubits_actual=int(rec.get("n_qubits_actual", 0)),
            error_category=str(r0.get("error_category", rec.get("error_category", ""))),
            error_message=str(r0.get("error_message", rec.get("error_message", ""))),
            failure_stage=str(r0.get("failure_stage", rec.get("failure_stage", "unknown"))),
            exception_type=str(r0.get("exception_type", rec.get("exception_type", ""))),
            actual_distribution=r0.get("actual_distribution"),
        )
    return InitialAttempt(gen, code, ev, int(rec.get("base_seed", rec.get("seed", 0))))


def pricing_for(config: dict[str, Any], model_spec: str) -> dict[str, float] | None:
    pricing = config.get("pricing", {}) or {}
    item = pricing.get(model_spec)
    if not item:
        return None
    return {
        "input_per_million_usd": float(item.get("input_per_million_usd", 0.0)),
        "output_per_million_usd": float(item.get("output_per_million_usd", 0.0)),
    }


def apply_cost(record: RunRecord, pricing: dict[str, float] | None) -> None:
    """料金は config で明示された場合のみ推定する（価格をコードへ固定しない）。"""
    record.total_tokens = record.tokens_in + record.tokens_out
    if pricing is None:
        record.estimated_cost_usd = None
        return
    record.estimated_cost_usd = (
        record.tokens_in * pricing["input_per_million_usd"]
        + record.tokens_out * pricing["output_per_million_usd"]
    ) / 1_000_000.0

    for r in record.rounds:
        r["estimated_cost_usd"] = (
            int(r.get("tokens_in", 0)) * pricing["input_per_million_usd"]
            + int(r.get("tokens_out", 0)) * pricing["output_per_million_usd"]
        ) / 1_000_000.0
