"""Bounded, resumable suffix generation for the frozen impact manifest only."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

from harness.code_extractor import extract_code
from harness.interventions import build_intervention_prompt
from harness.interventions import build_initial_prompt
from harness.reevaluation_checkpoint import canonical
from harness.isolated_evaluation import isolated_evaluate, profile
from harness.llm_clients import OpenAICompatClient, SYSTEM_PROMPT
from harness.run_state import atomic_json, file_lock
from scripts.followup_reevaluation import publish
from scripts.pilot_reevaluation import sha
from scripts.reevaluation_followup_validation import ROOT, SOURCE, WORK, PRIVATE, PLAN_HASH, read_db, sha_text, cause
from scripts.reevaluation_impact_audit import event, identity

CHECKPOINT = PRIVATE / "partial"
HOST = "http://127.0.0.1:11435"


def now():
    return datetime.now(timezone.utc).isoformat()


def check_models(manifest, tags):
    actual = {m["name"]: m["digest"] for m in tags["models"]}
    for source in manifest["sources"]:
        for model, old in source["model_digests"].items():
            if not old or actual.get(model.removeprefix("ollama:")) != old:
                raise ValueError("保存モデルdigestとの不一致またはモデル未取得: " + model)
        if set(source["generation_settings"]) != {"max_tokens", "parallel_requests", "reasoning_effort", "timeout_sec"}:
            raise ValueError("生成設定の欠落または未対応項目")
        if source["generation_settings"] != {"max_tokens": 1024, "parallel_requests": 1, "reasoning_effort": "none", "timeout_sec": 600}:
            raise ValueError("保存生成条件と実行可能条件の不一致")
        if source["max_rounds"] != 3 or not source["initial_prompt_source_verified"]:
            raise ValueError("初期プロンプトまたは修正上限の条件不一致")


def request_once(client, prompt, seed, temperature):
    """One request; no retry or unsupported-seed fallback."""
    start = time.monotonic()
    try:
        response = client._create(prompt, temperature, seed)
    except Exception as error:
        return {"status": "api_failure", "exception_type": type(error).__name__, "error": str(error),
                "elapsed_sec": time.monotonic() - start, "tokens_in": 0, "tokens_out": 0}
    usage = getattr(response, "usage", None)
    return {"status": "received", "response": response.model_dump(mode="json"),
            "text": response.choices[0].message.content or "", "elapsed_sec": time.monotonic() - start,
            "tokens_in": getattr(usage, "prompt_tokens", 0) or 0,
            "tokens_out": getattr(usage, "completion_tokens", 0) or 0}


def validate_cases(cases, manifest):
    keys = [c["record_key"] for c in cases]
    if len(keys) != len(set(keys)) or len(cases) != manifest["cases_count"]:
        raise ValueError("部分追試対象の重複・件数不一致")
    if any(c["branch_input_round"] not in (1, 2, 3) or c["generation_cap"] != 4 - c["branch_input_round"] for c in cases):
        raise ValueError("部分追試の生成上限不正")
    if sum(c["generation_cap"] for c in cases) != manifest["generation_cap"]:
        raise ValueError("総生成上限不一致")


def run_case(case, row, prior_results, config, client, directory, *, executor=isolated_evaluate, request=request_once):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    completed = directory / "completed.json"
    if completed.exists():
        if not completed.with_suffix(".sha256").exists() or sha(completed) != completed.with_suffix(".sha256").read_text().strip():
            raise ValueError("完了checkpointのhash不一致")
        saved = json.loads(completed.read_text())
        if saved["record_key"] != case["record_key"] or saved["case"] != case:
            raise ValueError("完了checkpointの出典不一致")
        return saved
    branch = case["branch_input_round"]
    prefix = row["rounds"][:branch]
    if [sha_text(r["extracted_code"]) for r in prefix] != case["prefix_code_hashes"]:
        raise ValueError("保存prefixのコードhash不一致")
    if "prefix_input_prompt_sha256" in case:
        task = __import__('tasks').get_task(case["task_id"])
        inputs = [sha_text(build_initial_prompt("baseline", task))]
        for r in prefix[:-1]:
            primary = prior_results[case["record_key"] + ":" + str(r["round"])]["primary"]
            inputs.append(sha_text(build_intervention_prompt(case["condition_id"], task, r["extracted_code"], event(primary))))
        if inputs != case["prefix_input_prompt_sha256"]:
            raise ValueError("保存prefixの入力プロンプト不一致")
    for r in prefix:
        if r["round_seed"] != case["base_seed"] + r["round"]:
            raise ValueError("保存seed規則の不一致")
    previous_code = prefix[-1]["extracted_code"]
    previous = prior_results[case["record_key"] + ":" + str(branch - 1)]["primary"]
    if previous["L3"]:
        raise ValueError("合格prefixからの追加生成は禁止")
    suffix = []
    for index in range(branch, 4):
        prompt = build_intervention_prompt(case["condition_id"], __import__('tasks').get_task(case["task_id"]), previous_code, event(previous))
        seed = case["base_seed"] + index
        request_path = directory / f"round_{index}_request.json"
        response_path = directory / f"round_{index}_response.json"
        evaluation_path = directory / f"round_{index}_evaluation.json"
        evaluation_started = directory / f"round_{index}_evaluation_started.json"
        request_data = {"record_key": case["record_key"], "round": index, "seed": seed,
                        "model": case["model_spec"], "system": SYSTEM_PROMPT, "user": prompt,
                        "temperature": config["temperature"], "max_tokens": 1024, "reasoning_effort": "none"}
        if request_path.exists():
            if json.loads(request_path.read_text())["request"] != request_data:
                raise ValueError("checkpoint入力プロンプト不一致")
            if not response_path.exists():
                raise ValueError("応答未確認の要求あり。自動再送しない")
            response = json.loads(response_path.read_text())
        else:
            atomic_json(request_path, {"requested_at_utc": now(), "request": request_data})
            response = request(client, prompt, seed, config["temperature"])
            atomic_json(response_path, response)
        if response["status"] != "received":
            raise ValueError("生成API障害。私的応答を保存して停止。自動再試行なし")
        code = extract_code(response["text"])
        if evaluation_path.exists():
            result = json.loads(evaluation_path.read_text())
        else:
            if evaluation_started.exists():
                raise ValueError("評価開始後の未完了checkpoint。原因確認まで停止")
            atomic_json(evaluation_started, {"started_at_utc": now(), "code_sha256": sha_text(code)})
            result = executor(code, case["task_id"])
            atomic_json(evaluation_path, result)
        if result["runtime_status"] != "completed":
            raise ValueError("隔離評価の基盤障害。モデル誤答へ算入せず停止")
        if result["primary"]["error_category"] == "unknown_error":
            cause(result["primary"])  # Stop on an unaudited exception, preserving raw.
        suffix.append({"round": index, "seed": seed, "code_sha256": sha_text(code), "code": code,
                       "input_prompt_sha256": sha_text(prompt), "evaluation": result,
                       "tokens_in": response["tokens_in"], "tokens_out": response["tokens_out"],
                       "elapsed_sec": response["elapsed_sec"]})
        # Match feedback reconstructed from the canonical reevaluation checkpoint,
        # including deterministic order for tied displayed probabilities.
        previous_code, previous = code, json.loads(canonical(result))["primary"]
        if previous["L3"]:
            break
    result = {"record_key": case["record_key"], "case": case, "prefix": prefix,
              "prefix_provenance": "saved_code_and_archived_reconstructed_input; no_new_generation",
              "suffix": suffix, "suffix_provenance": "new_api_request+isolated_evaluation",
              "success": bool(previous["L3"]), "stop_round": suffix[-1]["round"], "completed_at_utc": now()}
    atomic_json(completed, result)
    completed.with_suffix(".sha256").write_text(sha(completed) + "\n")
    return result


def run():
    CHECKPOINT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with file_lock(CHECKPOINT / "driver.lock", nonblocking=True), file_lock(ROOT / ".cache/automate_experiment.lock", nonblocking=True):
        manifest_path = WORK / "settings_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        validate_cases(manifest["cases"], manifest)
        if manifest["source_plan_sha256"] != PLAN_HASH:
            raise ValueError("固定計画の不一致")
        for name, field in (("impact_cases.csv", "impact_csv_sha256"), ("round_impact_audit.csv", "round_audit_sha256"),
                            ("unchanged_sample.csv", "unchanged_sample_sha256")):
            if sha(WORK / name) != manifest[field]:
                raise ValueError("固定した影響一覧または抽出一覧が変更された")
        profile_path = CHECKPOINT / "profile.json"
        pinned = {"manifest_sha256": sha(manifest_path), "evaluator": profile(),
                  "runner_sha256": sha(Path(__file__)), "audit_sha256": sha(ROOT / "scripts/reevaluation_impact_audit.py"),
                  "feedback_serialization": "canonical_result_json_v1; archived_diagnose_unchanged"}
        if profile_path.exists() and json.loads(profile_path.read_text()) != pinned:
            raise ValueError("部分追試のprofile不一致")
        atomic_json(profile_path, pinned)
        with urllib.request.urlopen(HOST + "/api/tags", timeout=10) as response:
            tags = json.load(response)
        check_models(manifest, tags)
        atomic_json(CHECKPOINT / "model_preflight.json", {"checked_at_utc": now(), "tags": tags})
        status = json.loads((SOURCE / "run_status.json").read_text())
        plan, saved = read_db(Path(status["checkpoint_dir"]) / "checkpoint.sqlite3")
        if profile() != plan["evaluator_profile"]:
            raise ValueError("本番再評価profileとの不一致")
        prior_results = {k: json.loads(t) for k, _, _, t, _ in saved}
        raw_sources, configs = {}, {}
        for source in manifest["sources"]:
            path = ROOT / source["source_dir"]
            if sha(path / "raw.jsonl") != source["raw_sha256"] or sha(path / "experiment_config.json") != source["config_sha256"]:
                raise ValueError("元rawまたは保存設定が変更された")
            raw_sources[source["source_dir"]] = {identity(r): r for r in map(json.loads, (path / "raw.jsonl").read_text().splitlines())}
            configs[source["source_dir"]] = json.loads((path / "experiment_config.json").read_text())
        completed_count = sum((CHECKPOINT / c["record_key"] / "completed.json").exists() for c in manifest["cases"])
        publish(SOURCE, "partial_rerun", "running", completed_count, len(manifest["cases"]))
        published_at = time.monotonic()
        clients = {}
        for c in manifest["cases"]:
            if profile() != pinned["evaluator"] or sha(manifest_path) != pinned["manifest_sha256"]:
                raise ValueError("実行中に評価器または固定manifestが変更された")
            model = c["model_spec"].removeprefix("ollama:")
            if model not in clients:
                clients[model] = OpenAICompatClient(model, HOST + "/v1", "ollama", ollama=True)
            result = run_case(c, raw_sources[c["source_dir"]][identity(c)], prior_results,
                              configs[c["source_dir"]], clients[model], CHECKPOINT / c["record_key"])
            completed_count = sum((CHECKPOINT / case["record_key"] / "completed.json").exists() for case in manifest["cases"])
            atomic_json(CHECKPOINT / "progress.json", {"status": "running", "completed": completed_count,
                        "planned": len(manifest["cases"]), "updated_at_utc": now()})
            print(json.dumps({"completed": completed_count, "planned": len(manifest["cases"]),
                              "model": model, "success": result["success"], "stop_round": result["stop_round"]}), flush=True)
            if time.monotonic() - published_at >= 600:
                publish(SOURCE, "partial_rerun", "running", completed_count, len(manifest["cases"]))
                published_at = time.monotonic()
        atomic_json(CHECKPOINT / "progress.json", {"status": "completed", "completed": completed_count,
                    "planned": len(manifest["cases"]), "updated_at_utc": now()})
        publish(SOURCE, "partial_rerun", "completed", completed_count, len(manifest["cases"]))
        return completed_count


if __name__ == "__main__":
    print(json.dumps({"completed_cases": run()}))
