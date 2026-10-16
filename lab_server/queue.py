"""SQLite lease queue. Every operation owns and closes its connection."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Callable
import uuid

from lab.core.run import canonical_json, validate_request

MAX_QUEUED = 50
MAX_ATTEMPTS = 3
STATES = ("queued", "running", "completed", "cancelled", "failed")


class Conflict(Exception):
    pass


class QueueFull(Exception):
    pass


class Queue:
    def __init__(self, db, *, now: Callable[[], float] = time.time,
                 max_queued=MAX_QUEUED, max_attempts=MAX_ATTEMPTS, store=None, token_factory=None):
        self.db = str(db)
        self.now = now
        self.max_queued = max_queued
        self.max_attempts = max_attempts
        self.store = Path(store).resolve() if store is not None else None
        self.token_factory = token_factory
        Path(db).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, token_hash TEXT, idem_key TEXT UNIQUE,
                    request_digest TEXT NOT NULL, module TEXT NOT NULL, request_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('queued','running','completed','cancelled','failed')),
                    progress REAL NOT NULL DEFAULT 0, message TEXT, attempts INTEGER NOT NULL DEFAULT 0,
                    lease_id TEXT, lease_until REAL, lease_seconds REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL, started_at REAL, finished_at REAL, error TEXT,
                    result_id TEXT, input_ids TEXT, report_path TEXT, package_path TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_state_created ON jobs(state, created_at);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value REAL NOT NULL);
            """)

    @contextmanager
    def connection(self, *, write=False):
        con = sqlite3.connect(self.db, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            if write:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if write:
                con.commit()
        except BaseException:
            if write:
                con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        result["input_ids"] = json.loads(result["input_ids"]) if result["input_ids"] else None
        return result

    def enqueue(self, request, idem_key=None):
        checked = validate_request(request)
        normalized = {"schema": "dkp-lab-input/1", "module": checked["module"].id,
                      "variants": [{"name": n, "input": v} for n, v in checked["variants"].items()]}
        encoded = canonical_json(normalized)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connection(write=True) as con:
            if idem_key is not None:
                existing = con.execute("SELECT * FROM jobs WHERE idem_key=?", (idem_key,)).fetchone()
                if existing:
                    if existing["request_digest"] != digest:
                        raise Conflict("Idempotency-Key already belongs to a different request")
                    return self._row(existing), False
            if con.execute("SELECT count(*) FROM jobs WHERE state='queued'").fetchone()[0] >= self.max_queued:
                raise QueueFull("Queue is full")
            job_id = uuid.uuid4().hex
            token_hash = (hashlib.sha256(self.token_factory(job_id).encode()).hexdigest()
                          if self.token_factory else None)
            con.execute("""INSERT INTO jobs
                (id, token_hash, idem_key, request_digest, module, request_json, state, created_at, message)
                VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, 'queued')""",
                        (job_id, token_hash, idem_key, digest, normalized["module"], encoded, self.now()))
            return self._row(con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()), True

    def claim(self, worker_id, lease_seconds):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self.connection(write=True) as con:
            now = self.now()
            con.execute("""UPDATE jobs SET attempts=attempts+1,
                state=CASE WHEN cancel_requested THEN 'cancelled'
                           WHEN attempts+1 >= ? THEN 'failed' ELSE 'queued' END,
                error=CASE WHEN NOT cancel_requested AND attempts+1 >= ? THEN ? ELSE NULL END,
                finished_at=CASE WHEN cancel_requested OR attempts+1 >= ? THEN ? ELSE NULL END,
                progress=0, message='lease expired', lease_id=NULL, lease_until=NULL
                WHERE state='running' AND lease_until < ?""",
                        (self.max_attempts, self.max_attempts,
                         f"lease expired {self.max_attempts} times", self.max_attempts, now, now))
            row = con.execute("""UPDATE jobs SET state='running', lease_id=?, lease_until=?,
                lease_seconds=?, started_at=COALESCE(started_at, ?), message=?
                WHERE id=(SELECT id FROM jobs WHERE state='queued' ORDER BY created_at, rowid LIMIT 1)
                AND state='queued' RETURNING *""",
                              (uuid.uuid4().hex, now + lease_seconds, lease_seconds, now,
                               f"running on {worker_id}")).fetchone()
            return self._row(row)

    def heartbeat(self, job_id, lease_id, progress, message):
        with self.connection(write=True) as con:
            now = self.now()
            return bool(con.execute("""UPDATE jobs SET progress=?, message=?, lease_until=?+lease_seconds
                WHERE id=? AND lease_id=? AND state='running' AND NOT cancel_requested AND lease_until>=?""",
                                    (max(0, min(1, progress)), message, now, job_id, lease_id, now)).rowcount)

    def complete(self, job_id, lease_id, result_id, input_ids, report_path, package_path):
        # The lease check and filesystem publication share the writer lock. Children only stage files.
        with self.connection(write=True) as con:
            row = con.execute("SELECT * FROM jobs WHERE id=? AND lease_id=? AND state='running'",
                              (job_id, lease_id)).fetchone()
            if row is None or row["lease_until"] < self.now():
                return False
            if row["cancel_requested"]:
                con.execute("UPDATE jobs SET state='cancelled', finished_at=?, message='cancelled' WHERE id=?",
                            (self.now(), job_id))
                return False
            if self.store:
                destination = self.store / job_id
                destination.mkdir(parents=True, exist_ok=True)
                paths = []
                for source, name in ((report_path, "report.json"), (package_path, "package.zip")):
                    target = destination / name
                    Path(source).replace(target)
                    paths.append(str(target))
                report_path, package_path = paths
            return bool(con.execute("""UPDATE jobs SET state='completed', progress=1, message='completed',
                finished_at=?, result_id=?, input_ids=?, report_path=?, package_path=?
                WHERE id=? AND lease_id=? AND state='running'""",
                                    (self.now(), result_id, canonical_json(input_ids), str(report_path),
                                     str(package_path), job_id, lease_id)).rowcount)

    def _finish(self, job_id, lease_id, state, error=None):
        with self.connection(write=True) as con:
            return bool(con.execute("""UPDATE jobs SET state=CASE WHEN cancel_requested THEN 'cancelled' ELSE ? END,
                error=CASE WHEN cancel_requested THEN NULL ELSE ? END, finished_at=?,
                message=CASE WHEN cancel_requested THEN 'cancelled' ELSE ? END
                WHERE id=? AND lease_id=? AND state='running' AND lease_until>=?""",
                                    (state, error, self.now(), state, job_id, lease_id, self.now())).rowcount)

    def fail(self, job_id, lease_id, error):
        return self._finish(job_id, lease_id, "failed", error)

    def mark_cancelled(self, job_id, lease_id):
        return self._finish(job_id, lease_id, "cancelled")

    def cancel(self, job_id):
        with self.connection(write=True) as con:
            row = con.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            if row["state"] not in ("queued", "running"):
                raise Conflict("Job is already final")
            con.execute("""UPDATE jobs SET cancel_requested=1,
                state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END,
                finished_at=CASE WHEN state='queued' THEN ? ELSE finished_at END,
                message=CASE WHEN state='queued' THEN 'cancelled' ELSE 'cancellation requested' END
                WHERE id=?""", (self.now(), job_id))
            return self._row(con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def get(self, job_id):
        with self.connection() as con:
            return self._row(con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def position(self, job_id):
        with self.connection() as con:
            row = con.execute("""SELECT position FROM
                (SELECT id, row_number() OVER (ORDER BY created_at, rowid) AS position
                 FROM jobs WHERE state='queued') WHERE id=?""", (job_id,)).fetchone()
            return row[0] if row else None

    def counts(self):
        with self.connection() as con:
            return dict.fromkeys(STATES, 0) | dict(con.execute("SELECT state, count(*) FROM jobs GROUP BY state"))

    def worker_heartbeat(self, worker_id):
        with self.connection(write=True) as con:
            con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                        (f"worker:{worker_id}", self.now()))

    def worker_heartbeat_age(self):
        with self.connection() as con:
            stamp = con.execute("SELECT max(value) FROM meta WHERE key LIKE 'worker:%'").fetchone()[0]
            return max(0, self.now() - stamp) if stamp is not None else None

    def purge(self, older_than_seconds=7 * 86400):
        with self.connection(write=True) as con:
            rows = con.execute("""SELECT * FROM jobs WHERE state IN ('completed','cancelled','failed')
                AND finished_at < ?""", (self.now() - older_than_seconds,)).fetchall()
            for row in rows:
                if self.store:
                    for directory in (self.store / row["id"], self.store / ".staging" / row["id"]):
                        resolved = directory.resolve()
                        if not resolved.is_relative_to(self.store) or resolved == self.store:
                            raise ValueError("Refusing to purge outside store")
                        if directory.exists():
                            shutil.rmtree(directory)
                else:
                    for key in ("report_path", "package_path"):
                        if row[key]:
                            Path(row[key]).unlink(missing_ok=True)
                con.execute("DELETE FROM jobs WHERE id=?", (row["id"],))
            con.execute("DELETE FROM meta WHERE value < ?", (self.now() - older_than_seconds,))
            return len(rows)
