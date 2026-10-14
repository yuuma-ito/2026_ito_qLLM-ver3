import json
import math
import sqlite3

import numpy as np
import pytest

from harness.evaluator import evaluate, evaluate_circuit, _statevector_distance
from harness.isolated_evaluation import Limits, isolated_evaluate
from harness.reevaluation_checkpoint import Checkpoint
from harness.supplementary import auxiliary_checks, coherent_operator_check, fidelity_cutoff, fourier_reference, pure_fidelity
from tasks import get_task


@pytest.mark.parametrize("inverse", [False, True])
def test_old_qft_blind_spot_and_new_anchor_coherences(inverse):
    dft = fourier_reference(3, inverse=inverse, include_preparation=False)
    phases = np.eye(8); phases[2, 2] = -1
    mutant = dft @ phases
    basis = np.eye(8, dtype=complex)
    old = list(basis.T) + [(basis[:, 0] + phase * basis[:, 1]) / np.sqrt(2) for phase in (1, 1j)]
    assert all(np.isclose(pure_fidelity(mutant @ s, dft @ s), 1) for s in old)
    new = coherent_operator_check(mutant, dft)
    assert new["status"] == "fail"
    assert new["minimum_fidelity"] < 1e-12
    assert np.isclose(new["process_fidelity"], 0.5625)
    assert new["probe_count"] == 22
    assert coherent_operator_check(np.exp(0.7j) * dft, dft)["status"] == "pass"


@pytest.mark.parametrize("task_id", ["T6_QFT_001", "T7_IQFT_001"])
def test_whole_preparation_qft_reference_agrees_and_detects_mutation(task_id):
    from qiskit import QuantumCircuit
    task = get_task(task_id)
    ns = {}; exec(task.mock_correct_code, ns)
    qc = ns["build_circuit"]()
    assert auxiliary_checks(qc, task_id)["status"] == "pass"
    expected = fourier_reference(3, inverse=task_id.startswith("T7"))
    phase = np.eye(8); phase[2, 2] = -1
    mutant = QuantumCircuit(3); mutant.unitary(expected @ phase, range(3))
    assert auxiliary_checks(mutant, task_id)["status"] == "fail"
    assert evaluate_circuit(mutant, task).L3  # Primary fixed-state policy remains unchanged.
    # Column 0 (the benchmark's sole prepared output) is unchanged.
    assert pure_fidelity((expected @ phase)[:, 0], expected[:, 0]) > 0.999999


def test_exact_fidelity_threshold_detects_rounded_gap_and_boundary():
    cutoff = fidelity_cutoff(0.05)
    assert math.isclose(cutoff, 0.9975015625, abs_tol=1e-14)
    for fidelity, passes in ((0.9975008, False), (0.998, True)):
        actual = np.array([math.sqrt(fidelity), math.sqrt(1-fidelity)], complex)
        assert (_statevector_distance(actual, np.array([1, 0])) < 0.05) == passes
        assert (pure_fidelity(actual, [1, 0]) > cutoff) == passes
    # Both specifications are strict; a score equal to the stored cutoff fails.
    assert not cutoff > cutoff
    with pytest.raises(ValueError):
        pure_fidelity([2, 0], [1, 0])
    with pytest.raises(ValueError):
        fidelity_cutoff(2)
    with pytest.raises(ValueError):
        coherent_operator_check(np.diag([1, 0]), np.eye(2))


@pytest.mark.parametrize("task_id,n", [("T1_Bell", 2), ("T2_GHZ", 3)])
def test_independent_bell_ghz_phase_and_reset_oracles(task_id, n):
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(n); qc.h(0)
    for q in range(1, n): qc.cx(0, q)
    assert auxiliary_checks(qc, task_id)["status"] == "pass"
    qc.z(0)  # Same Z-basis probabilities, orthogonal relative-phase state.
    result = auxiliary_checks(qc, task_id)
    assert result["status"] == "fail" and result["fidelity"] < 1e-12
    qc.reset(0)
    result = auxiliary_checks(qc, task_id)
    assert result["status"] == "diagnostic_only"
    assert np.isclose(result["purity"], 0.5)
    assert np.isclose(result["fidelity"], 0.25)
    assert result["strict_fidelity_cutoff"] is None


def manifest():
    return {"profile": {"version": "test_v1"}, "source_hash": "source_v1", "cases": [{"key": "a", "code_sha256": "a" * 64}, {"key": "b", "code_sha256": "b" * 64}]}


def test_checkpoint_restart_duplicate_and_result_immutability(tmp_path):
    with Checkpoint(tmp_path, manifest()) as checkpoint:
        assert checkpoint.claim("a")
        checkpoint.finish("a", {"runtime_status": "completed"})
        checkpoint.claim("b")  # Simulate interruption after durable claim.
    with Checkpoint(tmp_path, manifest()) as checkpoint:
        assert not checkpoint.claim("a")
        assert checkpoint.claim("b")
        checkpoint.finish("b", {"runtime_status": "completed"})
        assert checkpoint.sanity()["missing"] == 0
        assert not checkpoint.finish("a", {"runtime_status": "completed"})
        with pytest.raises(ValueError, match="immutable"):
            checkpoint.finish("a", {"runtime_status": "changed"})


def test_checkpoint_version_source_scope_mismatch_and_lock(tmp_path):
    with Checkpoint(tmp_path, manifest()):
        with pytest.raises(RuntimeError, match="owns"):
            with Checkpoint(tmp_path, manifest()): pass
    for field in ("profile", "source_hash", "cases"):
        changed = manifest()
        changed[field] = {"version": "new"} if field == "profile" else "new" if field == "source_hash" else changed["cases"][:1]
        with pytest.raises(ValueError, match="mismatch"):
            with Checkpoint(tmp_path, changed): pass
    duplicate = manifest(); duplicate["cases"].append(duplicate["cases"][0])
    with pytest.raises(ValueError, match="duplicate"):
        Checkpoint(tmp_path, duplicate)


def test_checkpoint_hard_exit_releases_lock_and_resumes_pending(tmp_path):
    import subprocess
    import sys
    with Checkpoint(tmp_path, manifest()) as checkpoint:
        checkpoint.claim("a"); checkpoint.finish("a", {"runtime_status": "completed"})
    program = "import json,os,sys; from harness.reevaluation_checkpoint import Checkpoint; c=Checkpoint(sys.argv[1],json.loads(sys.argv[2])); c.__enter__(); c.claim('b'); os._exit(19)"
    process = subprocess.run([sys.executable, "-c", program, str(tmp_path), json.dumps(manifest())])
    assert process.returncode == 19
    with Checkpoint(tmp_path, manifest()) as checkpoint:
        assert not checkpoint.claim("a")
        assert checkpoint.claim("b")
        checkpoint.finish("b", {"runtime_status": "completed"})
        assert checkpoint.sanity()["missing"] == 0


def test_checkpoint_accepts_full_history_sized_catalog_without_execution(tmp_path):
    large = {"profile": {"version": "synthetic"}, "cases": [{"key": str(i), "code_sha256": "a" * 64} for i in range(9517)]}
    with Checkpoint(tmp_path, large) as checkpoint:
        for key in ("0", "9516"):
            checkpoint.claim(key); checkpoint.finish(key, {"runtime_status": "completed"})
        assert checkpoint.sanity()["planned"] == 9517
        assert checkpoint.sanity()["missing"] == 9515
    with Checkpoint(tmp_path, large) as checkpoint:
        assert not checkpoint.claim("0")
        assert not checkpoint.claim("9516")


def test_public_report_atomic_publish_cannot_overwrite(tmp_path):
    from scripts.pilot_reevaluation import immutable_report
    target = tmp_path / "report.json"
    immutable_report(target, {"initial": True})
    with pytest.raises(ValueError, match="immutable"):
        immutable_report(target, {"initial": False})
    assert json.loads(target.read_text()) == {"initial": True}


def test_checkpoint_corrupt_results_and_database_are_refused(tmp_path):
    with Checkpoint(tmp_path / "hashed", manifest()) as checkpoint:
        checkpoint.claim("a"); checkpoint.finish("a", {"runtime_status": "completed"})
    with sqlite3.connect(tmp_path / "hashed" / "checkpoint.sqlite3") as db:
        db.execute("UPDATE results SET result='{}'")
    with pytest.raises(ValueError, match="hash mismatch"):
        with Checkpoint(tmp_path / "hashed", manifest()): pass
    directory = tmp_path / "broken"; directory.mkdir()
    (directory / "checkpoint.sqlite3").write_bytes(b"broken database")
    with pytest.raises(sqlite3.DatabaseError):
        with Checkpoint(directory, manifest()): pass


@pytest.mark.parametrize("task_id", ["T1_Bell", "T2_GHZ", "T3a_DJ_constant", "T3b_DJ_balanced", "T4_BV_011", "T5_Grover_11", "T6_QFT_001", "T7_IQFT_001", "T8_QPE_001", "T9_Ansatz_001"])
def test_isolated_primary_matches_existing_policy_and_auxiliary(task_id):
    task = get_task(task_id)
    direct = evaluate(task.mock_correct_code, task).to_dict()
    result = isolated_evaluate(task.mock_correct_code, task_id)
    assert result["runtime_status"] == "completed", result
    assert result["primary"] == direct
    assert result["auxiliary"]["status"] == ("pass" if task_id in {"T1_Bell", "T2_GHZ", "T6_QFT_001", "T7_IQFT_001"} else "not_implemented")
    assert result["isolation"]["seccomp"] and result["isolation"]["landlock_abi"] >= 3


def test_sandbox_refuses_host_files_network_processes_and_secret_environment(tmp_path, monkeypatch):
    secret = tmp_path / "secret"; secret.write_text("private")
    monkeypatch.setenv("QLLM_TEST_SECRET", "must_not_inherit")
    source = f'''import os, socket, subprocess
from qiskit import QuantumCircuit
def build_circuit():
    assert "QLLM_TEST_SECRET" not in os.environ
    for action in [lambda: open({str(secret)!r}).read(),
                   lambda: open({str(tmp_path / 'outside')!r}, 'w'),
                   lambda: open(os.environ['TMPDIR']+'/extra_file', 'w'),
                   lambda: socket.socket(),
                   lambda: subprocess.run(['/bin/true']),
                   lambda: os.fork(), lambda: os.kill(os.getppid(), 0)]:
        try:
            action()
        except PermissionError:
            pass
        else:
            raise AssertionError('sandbox escape')
    qc = QuantumCircuit(2); qc.h(0); qc.cx(0,1)
    return qc
'''
    result = isolated_evaluate(source, "T1_Bell")
    assert result["runtime_status"] == "completed" and result["primary"]["L3"], result
    assert not (tmp_path / "outside").exists()


def test_builder_cannot_inject_oracle_success():
    source = '''import json, os
from pathlib import Path
target = Path(os.environ['TMPDIR'])/'result.json'
target.write_text(json.dumps({'runtime_status':'completed','primary':{'L1':True,'L2':True,'L3':True,'structure_match':True}}))
os._exit(0)
'''
    assert isolated_evaluate(source, "T1_Bell")["runtime_status"] == "protocol_error"


def test_monkeypatched_builder_does_not_change_fresh_oracle():
    source = '''from qiskit import QuantumCircuit
import harness.evaluator as evaluator
evaluator.evaluate_circuit = lambda *args: 'forged_success'
def build_circuit():
    return QuantumCircuit(2)
'''
    result = isolated_evaluate(source, "T1_Bell")
    assert result["runtime_status"] == "completed" and not result["primary"]["L3"]
    assert result["primary"]["error_category"] == "wrong_output"


def test_policy_denial_is_not_model_wrong_output(tmp_path):
    secret = tmp_path / "outside"; secret.write_text("private")
    code = f'''from qiskit import QuantumCircuit
value = open({str(secret)!r}).read()
def build_circuit():
    q = QuantumCircuit(2); q.h(0); q.cx(0,1)
    return q
'''
    assert evaluate(code, get_task("T1_Bell")).L3  # Existing in-process evaluator can read host files.
    result = isolated_evaluate(code, "T1_Bell")
    assert result["runtime_status"] == "policy_denied" and "primary" not in result


def test_wall_cpu_memory_crash_and_import_errors_are_separate():
    assert isolated_evaluate("import time; time.sleep(5)", "T1_Bell", Limits(wall_seconds=1.2))["runtime_status"] == "wall_timeout"
    cpu = isolated_evaluate("while True: pass", "T1_Bell", Limits(wall_seconds=6, cpu_seconds=1))
    assert cpu["runtime_status"] == "cpu_limit", cpu
    memory = isolated_evaluate("def build_circuit():\n x=bytearray(3*1024**3)", "T1_Bell")
    assert memory["runtime_status"] == "memory_limit" and "primary" not in memory
    crash = isolated_evaluate("import os; os._exit(7)", "T1_Bell")
    assert crash["runtime_status"] == "worker_crash" and crash["returncode"] == 7
    error = isolated_evaluate("import missing_reeval_fixture_module", "T1_Bell")
    assert error["runtime_status"] == "completed" and error["primary"]["error_category"] == "import_error"


def test_synthetic_pipeline_isolation_checkpoint_and_zero_execution_resume(tmp_path):
    import hashlib
    from scripts.pilot_reevaluation import run_pilot, collect_cases, sha
    source = tmp_path / "source"; source.mkdir()
    (source / "experiment_config.json").write_text('{}')
    task = get_task("T1_Bell")
    code = task.mock_correct_code
    selector = {"source_dir": str(source), "model_spec": "fixture", "task_id": task.id, "base_seed": 0, "condition_id": "baseline"}
    entry = {"round": 0, "extracted_code": code, "code_sha256": hashlib.sha256(code.encode()).hexdigest(), "L3": True}
    row = {k: v for k, v in selector.items() if k != "source_dir"}; row["rounds"] = [entry]
    raw = source / "raw.jsonl"; raw.write_text(json.dumps(row) + '\n')
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"runs": [{"source_dir": str(source), "raw_sha256": sha(raw)}]}))
    before = raw.read_bytes()
    first = run_pilot([selector], tmp_path / "checkpoint", tmp_path / "first.json", snapshot=snapshot)
    assert first["sanity"]["missing"] == 0 and first["executed_this_invocation"] == 1
    assert first["outputs"][0]["primary"]["L3"]
    assert first["histories"][0]["new_final_success"]
    def should_not_execute(*args):
        raise AssertionError("completed checkpoint must not execute again")
    resumed = run_pilot([selector], tmp_path / "checkpoint", tmp_path / "second.json", executor=should_not_execute, snapshot=snapshot)
    assert resumed["executed_this_invocation"] == 0 and raw.read_bytes() == before
    with pytest.raises(ValueError, match="immutable"):
        run_pilot([selector], tmp_path / "checkpoint", tmp_path / "first.json", executor=should_not_execute, snapshot=snapshot)
    with pytest.raises(ValueError, match="limited"):
        collect_cases([selector] * 13, snapshot)
    raw.write_text(raw.read_text() + raw.read_text())
    with pytest.raises(ValueError, match="raw hash"):
        collect_cases([selector], snapshot)


def test_sandbox_installation_failure_has_no_subprocess_fallback(tmp_path, monkeypatch):
    import harness.sandbox_policy as policy
    import harness.isolated_evaluation as isolated
    monkeypatch.setattr(policy.platform, "system", lambda: "unsupported")
    with pytest.raises(RuntimeError, match="requires Linux"):
        policy.install([], str(tmp_path), {})
    calls = []
    def refuse(stage, *args):
        calls.append(stage)
        return {"runtime_status": "isolation_failure"}, tmp_path
    monkeypatch.setattr(isolated, "_stage", refuse)
    assert isolated.isolated_evaluate("code", "T1_Bell")["runtime_status"] == "isolation_failure"
    assert calls == ["build"]
