"""Bounded, two-process reevaluation, with no unsafe fallback.

Do not change the historical generator's evaluate() or its feedback history.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import json
import os
import resource
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from harness.sandbox_policy import POLICY_VERSION

ROOT = Path(__file__).resolve().parent.parent


@dataclasses.dataclass(frozen=True)
class Limits:
    wall_seconds: float = 25
    cpu_seconds: int = 15
    memory_bytes: int = 2 * 1024**3
    file_bytes: int = 4 * 1024**2

    def __post_init__(self):
        if min(self.wall_seconds, self.cpu_seconds, self.memory_bytes, self.file_bytes) <= 0:
            raise ValueError("positive execution budgets required")


def profile(limits=Limits()):
    from harness.readout import EVALUATOR_VERSION
    from harness.supplementary import SUPPLEMENT_VERSION
    names = ["harness/evaluator.py", "harness/readout.py", "harness/failure_metadata.py",
             "harness/supplementary.py", "harness/sandbox_policy.py", "harness/isolated_worker.py",
             "harness/isolated_evaluation.py", "harness/reevaluation_checkpoint.py", "harness/reevaluation_plan.py", "scripts/pilot_reevaluation.py"]
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names if (ROOT / name).exists()}
    files.update({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "tasks").glob("*.py"))})
    return {"primary_version": EVALUATOR_VERSION, "supplement_version": SUPPLEMENT_VERSION,
            "sandbox_policy": POLICY_VERSION, "files": files, "limits_per_stage": dataclasses.asdict(limits),
            "python": sys.version, "packages": {name: importlib.metadata.version(name) for name in ("qiskit", "qiskit-aer", "numpy")},
            "sampling": {"shots": 8192, "seed_simulator": 42, "seed_transpiler": 42}}


def _stage(stage, payload, scratch, limits):
    staging = scratch / stage
    staging.mkdir(mode=0o700)
    runtime = staging / "runtime"
    runtime.mkdir()
    (runtime / "harness").mkdir()
    (runtime / "harness" / "__init__.py").write_text("")
    for name in ("evaluator", "readout", "failure_metadata", "supplementary", "sandbox_policy", "isolated_worker"):
        shutil.copyfile(ROOT / "harness" / (name + ".py"), runtime / "harness" / (name + ".py"))
    shutil.copytree(ROOT / "tasks", runtime / "tasks", ignore=shutil.ignore_patterns("__pycache__"))
    output = staging / "output"
    output.mkdir(mode=0o700)
    write_paths = [str(output / name) for name in ("result.json", "isolation.json", "circuit.qpy", "stdout.log", "stderr.log")]
    for path in write_paths:
        Path(path).touch(mode=0o600)
    packages = str(Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
    read_paths = ["/usr/lib", "/lib", "/lib64", "/usr/lib64", "/etc/ld.so.cache", "/dev/urandom", "/dev/null",
                  "/proc/meminfo", "/proc/cpuinfo", str(runtime), str(output), packages]
    if stage == "oracle":
        read_paths.append(payload["qpy_path"])
    request = {**payload, "stage": stage, "output": str(output), "read_paths": read_paths, "write_paths": write_paths, "limits": dataclasses.asdict(limits)}
    request_path = staging / "request.json"
    request_path.write_text(json.dumps(request))
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(runtime), "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
           "QISKIT_PARALLEL": "FALSE", "TMPDIR": str(output), "HOME": str(output)}
    start = time.monotonic()
    cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        proc = subprocess.Popen([sys.executable, "-m", "harness.isolated_worker", str(request_path)],
                                cwd=runtime, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                close_fds=True, start_new_session=True)
        timeout = False
        try:
            proc.wait(timeout=limits.wall_seconds)
        except subprocess.TimeoutExpired:
            timeout = True
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
    elapsed = time.monotonic() - start
    cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_seconds = cpu_after.ru_utime + cpu_after.ru_stime - cpu_before.ru_utime - cpu_before.ru_stime
    if timeout:
        return {"runtime_status": "wall_timeout", "stage": stage, "seconds": elapsed, "cpu_seconds": cpu_seconds}, output
    if proc.returncode:
        # Never collapse infrastructure/resource failures into model wrong_output.
        status = "cpu_limit" if proc.returncode == -signal.SIGXCPU else "worker_killed" if proc.returncode == -signal.SIGKILL else "worker_crash"
        return {"runtime_status": status, "stage": stage, "returncode": proc.returncode, "seconds": elapsed, "cpu_seconds": cpu_seconds}, output
    try:
        data = (output / "result.json").read_bytes()
        if len(data) > limits.file_bytes:
            raise ValueError("oversized worker result")
        result = json.loads(data)
        if result["runtime_status"] != "isolation_failure":
            attestation = json.loads((output / "isolation.json").read_text())
            if attestation["policy"] != POLICY_VERSION or not attestation["seccomp"] or attestation["landlock_abi"] < 3:
                raise ValueError("invalid isolation attestation")
            result["isolation"] = attestation
        return {**result, "stage": stage, "seconds": elapsed, "cpu_seconds": cpu_seconds}, output
    except (OSError, ValueError, KeyError):
        return {"runtime_status": "protocol_error", "stage": stage, "seconds": elapsed, "cpu_seconds": cpu_seconds}, output


def isolated_evaluate(code, task_id, limits=Limits()):
    if len(code.encode()) > 1024 ** 2:
        return {"runtime_status": "code_limit", "stage": "build"}
    with tempfile.TemporaryDirectory(prefix="qllm-reeval-") as directory:
        scratch = Path(directory)
        built, output = _stage("build", {"code": code}, scratch, limits)
        if built["runtime_status"] != "built":
            if built["runtime_status"] == "completed":
                # A builder may emit a model/build failure, never a successful
                # oracle result. Untrusted code can alter its own interpreter.
                primary = built.get("primary", {})
                if any(primary.get(key) is not False for key in ("L1", "L2", "L3", "structure_match")):
                    return {"runtime_status": "protocol_error", "stage": "build"}
            return built
        path = output / "circuit.qpy"
        if not path.is_file() or path.is_symlink() or path.stat().st_size > limits.file_bytes:
            return {"runtime_status": "protocol_error", "stage": "build"}
        # Copy bounded bytes, never unpickle/load untrusted circuits in parent.
        safe_qpy = scratch / "input.qpy"
        safe_qpy.write_bytes(path.read_bytes())
        result, _ = _stage("oracle", {"task_id": task_id, "qpy_path": str(safe_qpy)}, scratch, limits)
        result["build_seconds"] = built["seconds"]
        result["build_cpu_seconds"] = built["cpu_seconds"]
        return result
