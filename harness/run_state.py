"""Atomic local runtime state; never contains generated code or credentials."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = {"completed", "failed", "interrupted"}


def state_path(output: Path, root: Path = ROOT) -> Path:
    key = hashlib.sha256(str(Path(output).resolve()).encode()).hexdigest()[:24]
    return root / ".cache" / "run_states" / (key + ".json")


@contextmanager
def file_lock(path: Path, *, nonblocking=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        try:
            fcntl.flock(handle, flags)
        except BlockingIOError:
            raise RuntimeError("Another process owns this experiment or queue.") from None
        try:
            yield handle
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_state(output: Path, root: Path = ROOT):
    path = state_path(output, root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def process_identity(pid: int):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip() + ":" + fields[19]
    except (OSError, IndexError):
        return None


def observation(state: dict, *, now=None, stalled_after=3600, heartbeat_after=45):
    now = time.time() if now is None else now
    if state["status"] in TERMINAL:
        return state["status"]
    identity = process_identity(state["pid"])
    if identity is None or identity != state["process_identity"]:
        return "interrupted"
    if now - state["heartbeat_at"] > heartbeat_after:
        return "heartbeat_stale"
    if now - state["progress_at"] > stalled_after:
        return "stalled"
    return "running"


def update_state(output: Path, token: str, changes: dict, root: Path = ROOT):
    path = state_path(output, root)
    with file_lock(path.with_suffix(".write.lock")):
        state = read_state(output, root)
        if state is None or state["token"] != token:
            raise RuntimeError("Run state ownership changed.")
        state.update(changes)
        atomic_json(path, state)
    return state


class RunTracker:
    def __init__(self, output: Path, experiment_id: str, *, root: Path = ROOT,
                 borrowed_token=None, heartbeat_interval=5):
        self.output = Path(output).resolve()
        self.experiment_id = experiment_id
        self.root = root
        self.borrowed = borrowed_token is not None
        self.token = borrowed_token or uuid.uuid4().hex
        self.interval = heartbeat_interval
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        path = state_path(self.output, self.root)
        if self.borrowed:
            state = read_state(self.output, self.root)
            if not state or state["token"] != self.token or observation(state) != "running":
                raise RuntimeError("Managed experiment has no live owner.")
            return self
        self.lock = file_lock(path.with_suffix(".owner.lock"), nonblocking=True)
        self.lock.__enter__()
        try:
            now = time.time()
            identity = process_identity(os.getpid())
            if identity is None:
                raise RuntimeError("Cannot identify the experiment process.")
            atomic_json(path, {"experiment_id": self.experiment_id, "output": str(self.output),
                              "token": self.token, "pid": os.getpid(), "process_identity": identity,
                              "status": "running", "phase": "starting", "started_at": now,
                              "heartbeat_at": now, "progress_at": now, "recorded": 0})
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        except BaseException:
            self.lock.__exit__(None, None, None)
            raise
        return self

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            try:
                update_state(self.output, self.token, {"heartbeat_at": time.time()}, self.root)
            except (OSError, ValueError, RuntimeError):
                # The monitor detects an absent heartbeat; never overwrite another owner.
                return

    def update(self, **changes):
        if "phase" in changes or "recorded" in changes:
            changes["progress_at"] = time.time()
        return update_state(self.output, self.token, changes, self.root)

    def finish(self, status="completed", **changes):
        return self.update(status=status, finished_at=time.time(), **changes)

    def __exit__(self, exc_type, exc, traceback):
        if self.borrowed:
            return
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=self.interval + 1)
        try:
            state = read_state(self.output, self.root)
            if exc_type:
                self.finish("interrupted" if issubclass(exc_type, (KeyboardInterrupt, SystemExit)) else "failed",
                            failure_type=exc_type.__name__)
            elif state["status"] not in TERMINAL:
                self.finish()
        finally:
            self.lock.__exit__(exc_type, exc, traceback)
