from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import time

import pytest

pytest.importorskip("fastapi")

from lab_server.queue import Queue
from lab_server.worker import process_one


def test_real_spawn_completes(tmp_path, request_input):
    db, store = tmp_path / "jobs.db", tmp_path / "store"
    queue = Queue(db)
    job, _ = queue.enqueue(request_input)
    result = process_one(db, store, "spawn", settings={"JOB_TIMEOUT": 10})
    assert result["id"] == job["id"] and result["state"] == "completed", result
    assert (store / job["id"] / "report.json").is_file()
    assert (store / job["id"] / "package.zip").is_file()
    assert queue.worker_heartbeat_age() is not None


def test_real_spawn_timeout(tmp_path, request_input):
    db, store = tmp_path / "jobs.db", tmp_path / "store"
    queue = Queue(db)
    job, _ = queue.enqueue(request_input)
    before = {p.pid for p in multiprocessing.active_children()}
    result = process_one(db, store, "timeout", settings={"JOB_TIMEOUT": 0.001, "POLL_SECONDS": 0.001})
    assert result["state"] == "failed" and result["error"] == "timeout"
    assert result["report_path"] is None and not (store / job["id"] / "report.json").exists()
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_real_spawn_cancellation(tmp_path, request_input):
    db, store = tmp_path / "jobs.db", tmp_path / "store"
    queue = Queue(db)
    job, _ = queue.enqueue(request_input)
    before = {p.pid for p in multiprocessing.active_children()}
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(process_one, db, store, "cancel", settings={"JOB_TIMEOUT": 10, "POLL_SECONDS": 0.01})
        deadline = time.monotonic() + 5
        while queue.get(job["id"])["state"] == "queued" and time.monotonic() < deadline:
            time.sleep(0.002)
        assert queue.get(job["id"])["state"] == "running"
        queue.cancel(job["id"])
        result = future.result(timeout=10)
    assert result["state"] == "cancelled" and result["result_id"] is None
    assert not (store / job["id"] / "package.zip").exists()
    assert {p.pid for p in multiprocessing.active_children()} == before


def test_computation_error_is_final(tmp_path, request_input, monkeypatch):
    from lab_server import worker

    def broken(*args):
        raise ValueError("test failure")

    monkeypatch.setattr(worker, "_compute", broken)
    db = tmp_path / "jobs.db"
    Queue(db).enqueue(request_input)
    result = process_one(db, tmp_path / "store", "inline", inline=True)
    assert result["state"] == "failed" and result["error"] == "ValueError: test failure"
