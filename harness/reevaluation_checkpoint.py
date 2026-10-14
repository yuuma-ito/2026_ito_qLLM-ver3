"""Transactional checkpoint for saved-code reevaluation (not generation)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from harness.run_state import file_lock


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Checkpoint:
    """One writer; immutable manifest and completed results; recover claims.

    An interrupted claim is retried after the exclusive lock is reacquired.
    Completed rows are never rerun, including recorded runtime failures.
    """

    def __init__(self, directory, manifest):
        self.directory = Path(directory)
        self.manifest = manifest
        cases = manifest["cases"]
        self.cases = {case["key"]: case for case in cases}
        if len(self.cases) != len(cases):
            raise ValueError("duplicate reevaluation case")
        if not all(len(case["code_sha256"]) == 64 for case in cases):
            raise ValueError("invalid code identity")

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink() or (self.directory / "checkpoint.sqlite3").is_symlink():
            raise ValueError("symlink checkpoint refused")
        self.lock = file_lock(self.directory / "writer.lock", nonblocking=True)
        self.lock.__enter__()
        try:
            existing_database = (self.directory / "checkpoint.sqlite3").exists()
            self.db = sqlite3.connect(self.directory / "checkpoint.sqlite3")
            self.db.execute("PRAGMA synchronous=FULL")
            if self.db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("corrupt checkpoint")
            self.db.executescript("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1), manifest TEXT NOT NULL); CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, code_hash TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','completed')), result TEXT, result_hash TEXT);")
            stored = self.db.execute("SELECT manifest FROM metadata WHERE id=1").fetchone()
            if stored is None:
                if existing_database:
                    raise ValueError("missing checkpoint manifest; refuse automatic repair")
                if self.db.execute("SELECT count(*) FROM results").fetchone()[0]:
                    raise ValueError("missing checkpoint manifest")
                with self.db:
                    self.db.execute("INSERT INTO metadata VALUES (1,?)", (canonical(self.manifest),))
            elif stored[0] != canonical(self.manifest):
                raise ValueError("checkpoint source/scope/evaluator version mismatch")
            for key, code_hash, state, result, result_hash in self.db.execute("SELECT * FROM results"):
                if key not in self.cases or code_hash != self.cases[key]["code_sha256"]:
                    raise ValueError("checkpoint case identity mismatch")
                if state == "completed":
                    if not result or hashlib.sha256(result.encode()).hexdigest() != result_hash:
                        raise ValueError("checkpoint result hash mismatch")
                    if canonical(json.loads(result)) != result:
                        raise ValueError("noncanonical checkpoint result")
                elif result is not None or result_hash is not None:
                    raise ValueError("partial checkpoint result")
            # A crashed owner cannot still hold this process-scoped flock.
            with self.db:
                self.db.execute("DELETE FROM results WHERE state='pending'")
            return self
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.__exit__(None, None, None)
            raise

    def __exit__(self, *error):
        self.db.close()
        self.lock.__exit__(*error)

    def completed(self, key):
        row = self.db.execute("SELECT result FROM results WHERE key=? AND state='completed'", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def claim(self, key):
        case = self.cases[key]
        if self.completed(key) is not None:
            return False
        with self.db:
            self.db.execute("INSERT INTO results(key,code_hash,state) VALUES (?,?,'pending')", (key, case["code_sha256"]))
        return True

    def finish(self, key, result):
        text = canonical(result)
        existing = self.completed(key)
        if existing is not None:
            if canonical(existing) != text:
                raise ValueError("completed result is immutable")
            return False
        with self.db:
            updated = self.db.execute("UPDATE results SET state='completed',result=?,result_hash=? WHERE key=? AND state='pending'",
                                      (text, hashlib.sha256(text.encode()).hexdigest(), key))
            if updated.rowcount != 1:
                raise ValueError("result requires an existing claim")
        return True

    def sanity(self):
        count = self.db.execute("SELECT count(*) FROM results WHERE state='completed'").fetchone()[0]
        return {"planned": len(self.cases), "completed": count, "missing": len(self.cases) - count,
                "manifest_sha256": digest(self.manifest), "integrity": self.db.execute("PRAGMA integrity_check").fetchone()[0]}
