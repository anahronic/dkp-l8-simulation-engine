from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import threading

import pytest

pytest.importorskip("fastapi")

from lab.core.run import canonical_json
from lab_server.queue import Conflict, Queue, QueueFull


def test_two_workers_never_claim_the_same_job(tmp_path, request_input):
    db = tmp_path / "jobs.db"
    queue = Queue(db, max_queued=100)
    expected = {queue.enqueue(request_input)[0]["id"] for _ in range(60)}
    barrier = threading.Barrier(2)

    def worker(name):
        own = Queue(db)
        barrier.wait()
        claimed = []
        while job := own.claim(name, 30):
            claimed.append(job["id"])
            assert own.complete(job["id"], job["lease_id"], "result", {}, "report", "package")
        return claimed

    with ThreadPoolExecutor(2) as pool:
        a, b = list(pool.map(worker, ("a", "b")))
    assert set(a) | set(b) == expected
    assert not set(a) & set(b)
    assert len(a) + len(b) == len(expected)


def test_expiry_fences_all_stale_mutations(tmp_path, request_input, clock):
    queue = Queue(tmp_path / "jobs.db", now=clock)
    job, _ = queue.enqueue(request_input)
    first = queue.claim("a", 10)
    clock.advance(11)
    second = queue.claim("b", 10)
    assert second["id"] == first["id"] == job["id"]
    assert second["attempts"] == 1 and second["lease_id"] != first["lease_id"]
    assert not queue.heartbeat(job["id"], first["lease_id"], 1, "stale")
    assert not queue.complete(job["id"], first["lease_id"], "stale", {}, "r", "p")
    assert not queue.fail(job["id"], first["lease_id"], "stale")
    assert not queue.mark_cancelled(job["id"], first["lease_id"])
    assert queue.complete(job["id"], second["lease_id"], "fresh", {"a": "input"}, "r", "p")
    assert queue.get(job["id"])["result_id"] == "fresh"
    assert not queue.complete(job["id"], second["lease_id"], "twice", {}, "r", "p")


def test_expired_worker_cannot_publish_files(tmp_path, request_input, clock):
    store = tmp_path / "store"
    queue = Queue(tmp_path / "jobs.db", store=store, now=clock)
    queue.enqueue(request_input)
    old = queue.claim("a", 10)
    clock.advance(11)
    new = queue.claim("b", 10)
    report, package = tmp_path / "report", tmp_path / "package"
    report.write_text("fresh")
    package.write_bytes(b"zip")
    assert queue.complete(new["id"], new["lease_id"], "fresh", {}, report, package)
    report.write_text("stale")
    package.write_bytes(b"stale")
    assert not queue.complete(old["id"], old["lease_id"], "stale", {}, report, package)
    assert (store / new["id"] / "report.json").read_text() == "fresh"
    assert report.read_text() == "stale"


def test_attempt_limit_and_heartbeat(tmp_path, request_input, clock):
    queue = Queue(tmp_path / "jobs.db", now=clock)
    row, _ = queue.enqueue(request_input)
    job = queue.claim("a", 10)
    clock.advance(8)
    assert queue.heartbeat(job["id"], job["lease_id"], 0.5, "halfway")
    clock.advance(5)
    assert queue.claim("b", 10) is None
    clock.advance(6)
    for attempt in (1, 2):
        job = queue.claim("b", 10)
        assert job["attempts"] == attempt
        clock.advance(11)
    assert queue.claim("b", 10) is None
    final = queue.get(row["id"])
    assert final["state"] == "failed" and final["attempts"] == 3
    assert final["error"] == "lease expired 3 times"


def test_cancellation_and_final_conflict(tmp_path, request_input, clock):
    queue = Queue(tmp_path / "jobs.db", now=clock)
    queued, _ = queue.enqueue(request_input)
    assert queue.position(queued["id"]) == 1
    assert queue.cancel(queued["id"])["state"] == "cancelled"
    assert queue.position(queued["id"]) is None
    running, _ = queue.enqueue(request_input)
    job = queue.claim("a", 10)
    assert queue.cancel(running["id"])["cancel_requested"] == 1
    assert queue.get(running["id"])["state"] == "running"
    assert not queue.heartbeat(job["id"], job["lease_id"], 1, "done")
    assert queue.mark_cancelled(job["id"], job["lease_id"])
    for job_id in (queued["id"], running["id"]):
        with pytest.raises(Conflict):
            queue.cancel(job_id)
    assert queue.cancel("missing") is None


def test_cancellation_wins_completion_and_crash_recovery(tmp_path, request_input, clock):
    queue = Queue(tmp_path / "jobs.db", now=clock)
    for expire in (False, True):
        queue.enqueue(request_input)
        job = queue.claim("a", 10)
        queue.cancel(job["id"])
        if expire:
            clock.advance(11)
            assert queue.claim("b", 10) is None
        else:
            assert not queue.complete(job["id"], job["lease_id"], "r", {}, "r", "p")
        assert queue.get(job["id"])["state"] == "cancelled"


def test_idempotency_normalization_and_full(tmp_path, request_input):
    queue = Queue(tmp_path / "jobs.db", max_queued=1)
    first, created = queue.enqueue(request_input, "key")
    assert created
    replay, created = Queue(queue.db).enqueue(json.loads(first["request_json"]), "key")
    assert not created and replay["id"] == first["id"]
    assert first["request_digest"] == hashlib.sha256(canonical_json(json.loads(first["request_json"])).encode()).hexdigest()
    other = copy.deepcopy(request_input)
    other["variants"][0]["name"] = "different"
    with pytest.raises(Conflict):
        queue.enqueue(other, "key")
    with pytest.raises(QueueFull):
        queue.enqueue(request_input)


def test_simultaneous_idempotent_enqueue(tmp_path, request_input):
    queue = Queue(tmp_path / "jobs.db")
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: queue.enqueue(request_input, "shared"), range(2)))
    assert results[0][0]["id"] == results[1][0]["id"]
    assert sum(created for _, created in results) == 1


def test_purge_removes_files_but_preserves_unfinished(tmp_path, request_input, clock):
    store = tmp_path / "store"
    queue = Queue(tmp_path / "jobs.db", now=clock, store=store)
    queue.enqueue(request_input, "retained-key")
    job = queue.claim("a", 10)
    report, package = tmp_path / "r", tmp_path / "p"
    report.write_text("{}")
    package.write_bytes(b"zip")
    queue.complete(job["id"], job["lease_id"], "r", {}, report, package)
    orphan = store / ".staging" / job["id"] / "crashed-attempt"
    orphan.mkdir(parents=True)
    (orphan / "partial").write_text("partial")
    pending, _ = queue.enqueue(request_input)
    assert queue.purge() == 0
    clock.advance(7 * 86400 + 1)
    assert queue.purge() == 1
    assert queue.get(job["id"]) is None
    assert not (store / job["id"]).exists() and not orphan.exists()
    assert queue.get(pending["id"])["state"] == "queued"
    assert queue.enqueue(request_input, "retained-key")[1]
