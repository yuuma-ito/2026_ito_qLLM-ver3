import json
import hashlib
from pathlib import Path

import numpy as np
import pytest

from harness.supplementary import ADDITIONAL_TASKS, auxiliary_checks, reference_operator
from harness.reevaluation_plan import build_plan, execute_bounded_batch
from harness.isolated_evaluation import Limits, profile
from tasks import get_task


@pytest.mark.parametrize("task_id", sorted(ADDITIONAL_TASKS))
def test_six_auxiliary_oracles_known_correct_wrong_and_global_phase(task_id):
    task = get_task(task_id)
    for code, status in ((task.mock_correct_code, "pass"), (task.mock_wrong_code, "fail")):
        ns = {}; exec(code, ns); qc = ns["build_circuit"]()
        result = auxiliary_checks(qc, task_id)
        assert result["status"] == status
        assert result["transform"]["status"] == status
        qc.global_phase += 0.37
        assert auxiliary_checks(qc, task_id)["status"] == status


@pytest.mark.parametrize("task_id,plus,minus", [("T3a_DJ_constant", 0, 4), ("T3b_DJ_balanced", 3, 7), ("T4_BV_011", 3, 11)])
def test_ancilla_phase_reference_matches_hand_state(task_id, plus, minus):
    expected = np.zeros(2 ** ADDITIONAL_TASKS[task_id], complex)
    expected[plus], expected[minus] = 1/np.sqrt(2), -1/np.sqrt(2)
    assert np.allclose(reference_operator(task_id)[:, 0], expected)
    from qiskit import QuantumCircuit
    # Correct computational distribution with wrong ancilla phase is detected.
    qc = QuantumCircuit(ADDITIONAL_TASKS[task_id])
    for q in range(qc.num_qubits-1):
        if plus & (1 << q): qc.x(q)
    qc.h(qc.num_qubits-1)
    assert auxiliary_checks(qc, task_id)["status"] == "fail"


def test_qpe_and_grover_references_match_exact_basis_states():
    for task_id, index in (("T8_QPE_001", 10), ("T5_Grover_11", 3)):
        state = reference_operator(task_id)[:, 0]
        assert abs(state[index]) == pytest.approx(1)
        assert np.sum(abs(np.delete(state, index)) ** 2) < 1e-20


def test_ansatz_reference_matches_independent_amplitude_updates():
    state = np.array([1, 0, 0, 0], complex)
    for q, theta in ((0, np.pi/4), (1, np.pi/3), (None, 0), (0, np.pi/6), (1, np.pi/5)):
        if q is None:
            state = state[[0, 3, 2, 1]]
        else:
            before = state.copy(); c, s = np.cos(theta/2), np.sin(theta/2)
            for index in range(4):
                if not index & (1 << q):
                    other = index | (1 << q)
                    state[index] = c*before[index]-s*before[other]
                    state[other] = s*before[index]+c*before[other]
    assert np.allclose(state, reference_operator("T9_Ansatz_001")[:, 0])


def fixture_source(tmp_path):
    directory = tmp_path / "source"; directory.mkdir()
    config = {"models": ["fixture"], "tasks": ["T1_Bell"], "seeds": {"start": 0, "stop": 2},
              "conditions": ["baseline"], "max_rounds": 3}
    (directory / "experiment_config.json").write_text(json.dumps(config))
    code = get_task("T1_Bell").mock_correct_code
    rows = []
    for seed in range(2):
        entry = {"round": 0, "extracted_code": code, "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
                 **{key: True for key in ("L0", "L1", "L2", "L3", "structure_match")}, "error_category": "ok"}
        rows.append({"model_spec": "fixture", "task_id": "T1_Bell", "base_seed": seed, "condition_id": "baseline", "rounds": [entry], "extracted_code": code})
    path = directory / "raw.jsonl"
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    snapshot = tmp_path / "snapshot.json"
    def refresh():
        snapshot.write_text(json.dumps({"runs": [{"source_dir": str(directory), "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "config": config, "records": 2}]}))
    refresh()
    return path, snapshot, rows, refresh


def test_full_plan_missing_duplicate_hash_and_config_corruption(tmp_path):
    path, snapshot, rows, refresh = fixture_source(tmp_path)
    assert build_plan(snapshot)["records"] == 2
    for broken in ([rows[0]], [rows[0], rows[0]]):
        path.write_text(''.join(json.dumps(r)+'\n' for r in broken)); refresh()
        with pytest.raises(ValueError): build_plan(snapshot)
    rows[0]["rounds"][0]["code_sha256"] = "f" * 64
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows)); refresh()
    with pytest.raises(ValueError, match="code hash"): build_plan(snapshot)
    config_path = path.parent / "experiment_config.json"
    config = json.loads(config_path.read_text()); config["max_rounds"] = 2
    config_path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="config differs"): build_plan(snapshot)


def test_bounded_scheduler_stops_on_runtime_failure_and_cannot_silently_resume(tmp_path):
    path, snapshot, rows, refresh = fixture_source(tmp_path)
    plan = build_plan(snapshot)
    calls = []
    def failing(*args):
        calls.append(1); return {"runtime_status": "cpu_limit"}
    keys = [case["key"] for case in plan["cases"]]
    first = execute_bounded_batch(plan, keys, tmp_path/"cp", executor=failing)
    assert first["status"] == "blocked_runtime_failure" and len(calls) == 1
    resumed = execute_bounded_batch(plan, keys, tmp_path/"cp", executor=failing)
    assert resumed["executed"] == 0 and len(calls) == 1
    with pytest.raises(ValueError, match="1--48"):
        execute_bounded_batch(plan, keys * 25, tmp_path/"other", executor=failing)


def test_bounded_scheduler_synthetic_integration_and_resume(tmp_path):
    path, snapshot, rows, refresh = fixture_source(tmp_path)
    plan = build_plan(snapshot)
    keys = [case["key"] for case in plan["cases"]]
    first = execute_bounded_batch(plan, keys, tmp_path/"cp")
    assert first["status"] == "batch_completed" and first["sanity"]["missing"] == 0
    def forbidden(*args): raise AssertionError("duplicate execution")
    assert execute_bounded_batch(plan, keys, tmp_path/"cp", executor=forbidden)["executed"] == 0


def test_legacy_empty_code_has_explicit_missing_hash_provenance(tmp_path):
    path, snapshot, rows, refresh = fixture_source(tmp_path)
    rows[0]["extracted_code"] = rows[0]["rounds"][0]["extracted_code"] = ""
    rows[0]["rounds"][0]["code_sha256"] = ""
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows)); refresh()
    plan = build_plan(snapshot)
    assert plan["static_checks"]["legacy_empty_code_hashes"] == 1
    assert plan["cases"][0]["stored_code_sha256"] == ""
    assert plan["cases"][0]["code_sha256"] == hashlib.sha256(b"").hexdigest()
