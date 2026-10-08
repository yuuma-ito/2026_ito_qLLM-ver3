"""Conservative read-time migration; original JSONL and measured metrics stay intact."""
from __future__ import annotations

import re

FAILURE_STAGES = {"parse", "import", "exec", "build", "evaluate", "api_call", "unknown"}


def exception_name(message: str) -> str:
    match = re.match(r"^([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception|Timeout)):", message or "")
    return match.group(1) if match else ""


def normalize_attempt(attempt: dict) -> dict:
    out = dict(attempt)
    if "failure_stage" in out:
        return out
    category = out.get("error_category", "")
    message = out.get("error_message", "") or ""
    exception = exception_name(message)
    stage = "unknown"
    if out.get("generation_error") or out.get("timeout_flag") or category in {"api_timeout", "api_error"}:
        stage = "api_call"
    elif category == "syntax":
        stage = "parse"
    elif category == "import_error":
        stage = "build" if out.get("L0") else "import"
        if stage == "build":
            category = "build_error"
    elif category == "build_error":
        stage = "build"
    elif category == "interface_mismatch":
        stage = "build" if out.get("L0") else "exec"
    elif category in {"wrong_output", "bit_order_error", "qubit_count_mismatch"}:
        stage = "evaluate"
    elif category == "unknown_error" and out.get("L0") is False:
        stage = "exec"
        if exception == "AttributeError" and ("has no attribute" in message or re.search(r"Attribute .+ is not defined", message)):
            category = "interface_mismatch"
    elif category == "unknown_error" and out.get("L0"):
        stage = "evaluate"
    out.update(failure_stage=stage, exception_type=exception,
               error_message=message, error_category=category,
               failure_metadata_source="legacy_inference_v1")
    if category != attempt.get("error_category", ""):
        out["original_error_category"] = attempt.get("error_category", "")
    return out


def normalize_record(record: dict) -> dict:
    out = normalize_attempt(record)
    out["rounds"] = [normalize_attempt(r) for r in record.get("rounds", [])]
    return out
