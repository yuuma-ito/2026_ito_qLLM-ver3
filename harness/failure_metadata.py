"""Conservative read-time migration; original JSONL and measured metrics stay intact."""
from __future__ import annotations

import re

FAILURE_STAGES = {"parse", "import", "exec", "build", "evaluate", "api_call", "unknown"}


def exception_name(message: str) -> str:
    match = re.match(r"^([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception|Timeout)):", message or "")
    return match.group(1) if match else ""


def missing_counts_result(exception_type: str, message: str) -> bool:
    """Qiskit Result.get_counts() was called without counts/statevector data."""
    return exception_type == "QiskitError" and bool(
        re.match(r"^(?:QiskitError: )?['\"]?No counts for experiment ", message or ""))


def missing_result_data(exception_type: str, message: str) -> bool:
    """A Qiskit Result accessor was called without the required saved data."""
    return missing_counts_result(exception_type, message) or (
        exception_type == "QiskitError" and bool(
            re.match(r"^(?:QiskitError: )?['\"]?No statevector for experiment ", message or "")))


def normalize_attempt(attempt: dict) -> dict:
    out = dict(attempt)
    if "failure_stage" in out:
        if (out["failure_stage"] == "exec" and out.get("L0") is False
                and out.get("error_category") == "unknown_error"
                and not out.get("generation_error") and not out.get("timeout_flag")
                and missing_result_data(out.get("exception_type", ""), out.get("error_message", ""))):
            out.update(error_category="interface_mismatch",
                       original_error_category="unknown_error",
                       failure_metadata_source="result_data_reclassification_v1")
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
        elif missing_result_data(exception, message):
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
