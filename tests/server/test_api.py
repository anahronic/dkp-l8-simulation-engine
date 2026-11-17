import copy
import io
import json
import zipfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from lab import api
from lab.core.run import run_request
from lab_server.app import PREFIX, create_app
from lab_server.worker import process_one


def submit(client, request_input, **kwargs):
    response = client.post(PREFIX + "/jobs", json=request_input, **kwargs)
    assert response.status_code == 202, response.text
    return response.json()


def auth(job):
    return {"Authorization": "Bearer " + job["token"]}


def test_full_flow_and_cli_identity(service, request_input, monkeypatch):
    client, app, db, store = service
    sentinel = b"browser-only"
    monkeypatch.setattr(api, "_last_package", sentinel)
    validated = client.post(PREFIX + "/validate", json=request_input)
    assert validated.status_code == 200 and validated.json() == api.validate_payload(request_input)
    job = submit(client, request_input)
    headers = auth(job)
    queued = client.get(job["links"]["status"], headers=headers).json()
    assert queued["state"] == "queued" and queued["queue_position"] == 1
    for key in ("report", "export"):
        assert client.get(job["links"][key], headers=headers).status_code == 409
    process_one(db, store, "test", inline=True)
    status = client.get(job["links"]["status"], headers=headers).json()
    assert status["state"] == "completed" and status["progress"] == 1
    assert status["queue_position"] is None and status["error"] is None
    assert status["created_at"] <= status["started_at"] <= status["finished_at"]
    report = client.get(job["links"]["report"], headers=headers)
    assert report.status_code == 200
    records = {}
    direct = run_request(request_input, records_out=records)
    assert report.json() == direct
    assert status["result_id"] == direct["result_id"]
    assert status["input_ids"] == {"request": direct["input_id"],
                                    "variants": {n: v["input_id"] for n, v in direct["variants"].items()}}
    exported = client.get(job["links"]["export"], headers=headers)
    assert exported.status_code == 200 and exported.headers["content-type"] == "application/zip"
    assert "attachment" in exported.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert {"request.json", "result.json", "report.en.md", "report.ru.md", "report.html",
                "provenance.json", "REPLAY.md", "SHA256SUMS"} <= set(archive.namelist())
        assert {n for n in archive.namelist() if n.startswith("records/")} == {f"records/{n}.jsonl" for n in records}
        assert json.loads(archive.read("result.json")) == direct
        assert json.loads(archive.read("provenance.json"))["runtime"] == "server"
    assert api.last_package() == sentinel
    assert client.post(job["links"]["cancel"], headers=headers).status_code == 409
    assert app.state.queue.worker_heartbeat_age() is not None


def test_job_tokens_are_isolated_on_every_route(service, request_input):
    client, app, _, _ = service
    a, b = submit(client, request_input), submit(client, request_input)
    with TestClient(app) as other_client:
        for key, method in (("status", "get"), ("cancel", "post"), ("report", "get"), ("export", "get")):
            call = getattr(other_client, method)
            assert call(b["links"][key]).status_code == 401
            wrong = call(b["links"][key], headers=auth(a))
            unknown = call(b["links"][key].replace(b["job_id"], "unknown"), headers=auth(a))
            assert wrong.status_code == unknown.status_code == 404
            assert wrong.json() == unknown.json()
    assert client.get(a["links"]["status"], headers={"X-Job-Token": a["token"]}).status_code == 200
    assert app.state.queue.get(a["job_id"])["token_hash"] != a["token"]


@pytest.mark.parametrize("location", ["path", "code", "nested_path", "nested_code", "bad_module", "list_module", "too_many"])
def test_invalid_input_queues_nothing(service, request_input, location):
    client, app, _, _ = service
    bad = copy.deepcopy(request_input)
    if location.startswith("nested_"):
        bad["variants"][0]["input"][location[7:]] = "forbidden"
    elif location == "bad_module":
        bad["module"] = "not_installed"
    elif location == "list_module":
        bad["module"] = []
    elif location == "too_many":
        bad["variants"] = [{"name": f"v{i}", "input": request_input["variants"][0]["input"]} for i in range(7)]
    else:
        bad[location] = "forbidden"
    for endpoint in ("validate", "jobs"):
        response = client.post(PREFIX + "/" + endpoint, json=bad)
        assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_input"
        if "path" in location or "code" in location:
            assert any("unknown key" in problem for problem in response.json()["error"]["problems"])
    assert sum(app.state.queue.counts().values()) == 0


@pytest.mark.parametrize("body", [b"{", b"\xff", b'{"a":NaN}', b""])
def test_bad_json(service, body):
    response = service[0].post(PREFIX + "/jobs", content=body)
    assert response.status_code == 400 and response.json()["error"]["code"] == "bad_json"


def test_size_checks_header_and_stream(tmp_path):
    app = create_app(tmp_path / "jobs.db", tmp_path / "store", {"MAX_BODY_BYTES": 32})
    with TestClient(app) as client:
        responses = [client.post(PREFIX + "/jobs", content=b"{}", headers={"Content-Length": "33"}),
                     client.post(PREFIX + "/jobs", content=b" " * 33, headers={"Content-Length": "1"}),
                     client.post(PREFIX + "/jobs", content=iter([b" " * 20, b" " * 20]))]
        assert all(r.status_code == 413 and r.json()["error"]["code"] == "too_large" for r in responses)
        assert sum(app.state.queue.counts().values()) == 0


def test_rate_limit_all_post_routes_and_refill(tmp_path, request_input, clock):
    app = create_app(tmp_path / "jobs.db", tmp_path / "store", {"RATE_BURST": 2})
    app.state.limiter.now = clock
    with TestClient(app) as client:
        job = submit(client, request_input)
        assert client.post(PREFIX + "/validate", json=request_input).status_code == 200
        limited = client.post(job["links"]["cancel"], headers=auth(job))
        assert limited.status_code == 429 and limited.json()["error"]["code"] == "rate_limited"
        assert client.get(PREFIX + "/health").status_code == 200
        clock.advance(6)
        assert client.post(job["links"]["cancel"], headers=auth(job)).status_code == 200


def test_replay_restart_conflict_and_queue_full(tmp_path, request_input, monkeypatch):
    monkeypatch.delenv("LAB_SERVER_SECRET", raising=False)
    db, store = tmp_path / "jobs.db", tmp_path / "store"
    config = {"MAX_QUEUED": 1, "RATE_BURST": 100}
    with TestClient(create_app(db, store, config)) as client:
        first = submit(client, request_input, headers={"Idempotency-Key": "test-key", "X-Idempotency-Token": "a" * 43})
        assert (store / ".secret").is_file()
    with TestClient(create_app(db, store, config)) as client:
        replay = client.post(PREFIX + "/jobs", json=request_input, headers={"Idempotency-Key": "test-key", "X-Idempotency-Token": "a" * 43})
        assert replay.status_code == 200 and replay.json() == first
        different = copy.deepcopy(request_input)
        different["variants"][0]["name"] = "other"
        assert client.post(PREFIX + "/jobs", json=different, headers={"Idempotency-Key": "test-key", "X-Idempotency-Token": "a" * 43}).status_code == 409
        full = client.post(PREFIX + "/jobs", json=request_input)
        assert full.status_code == 503 and full.json()["error"]["code"] == "queue_full"
        assert "Retry-After" in full.headers
        assert client.get(first["links"]["status"], headers=auth(first)).status_code == 200


@pytest.mark.parametrize("key", ["", "bad key", "a" * 65, "bad/key"])
def test_invalid_idempotency_key(service, request_input, key):
    response = service[0].post(PREFIX + "/jobs", json=request_input, headers={"Idempotency-Key": key})
    assert response.status_code == 422
    assert service[1].state.queue.counts()["queued"] == 0


def test_cancel_queued_and_discovery(service, request_input):
    client, app, db, store = service
    job = submit(client, request_input)
    cancelled = client.post(job["links"]["cancel"], headers=auth(job))
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    assert process_one(db, store, "idle", inline=True) is None
    health = client.get(PREFIX + "/health").json()
    assert health["ok"] and health["identity"]["lab_version"] == health["lab_version"]
    assert health["queue"]["cancelled"] == 1 and health["worker_heartbeat_age_s"] >= 0
    assert client.get(PREFIX + "/catalog").json() == api.catalog_payload()
    scenarios = client.get(PREFIX + "/scenarios").json()
    scenario = next(s for s in scenarios if s["id"] == "work_cycle")
    assert scenario["examples"][0] == {"name": "staffed_36", "kind": "reference"}
    assert client.get(PREFIX + "/scenarios/work_cycle").json() == api.example_request("work_cycle")
    assert client.get(PREFIX + "/scenarios/unknown").status_code == 404
    assert client.get(PREFIX + "/unknown").json()["error"]["code"] == "not_found"


def test_cors_only_for_the_site_origin(service):
    """Only https://dikenocracy.com gets a CORS grant; the opaque "null" origin of the retired Keeper panel
    (2026-11-17) and other origins get none."""
    client, *_ = service
    headers = {"Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "content-type,idempotency-key,x-idempotency-token"}
    pre = client.options("/api/lab/v1/jobs", headers={"Origin": "https://dikenocracy.com", **headers})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "https://dikenocracy.com"
    assert "access-control-allow-credentials" not in pre.headers
    for origin in ("null", "https://evil.example"):
        other = client.get("/api/lab/v1/health", headers={"Origin": origin})
        assert "access-control-allow-origin" not in other.headers
        pre = client.options("/api/lab/v1/jobs", headers={"Origin": origin, **headers})
        assert "access-control-allow-origin" not in pre.headers


@pytest.mark.parametrize("host", ["198.51.100.10", "198.51.100.20"])
def test_kt9_replay_proof_is_required_on_every_route(tmp_path, request_input, host):
    db, store = tmp_path / "jobs.db", tmp_path / "store"
    config = {"RATE_BURST": 1000}
    owner = {"Idempotency-Key": "run-1", "X-Idempotency-Token": "a" * 43}
    stranger = {**owner, "X-Idempotency-Token": "b" * 43}
    app = create_app(db, store, config)
    with TestClient(app, client=("198.51.100.10", 4000)) as a, TestClient(app, client=(host, 5000)) as b:
        first = submit(a, request_input, headers=owner)
        own_b = submit(b, request_input)
        other_body = copy.deepcopy(request_input)
        other_body["variants"][0]["name"] = "other"
        for body in (request_input, other_body):
            denied = b.post(PREFIX + "/jobs", json=body, headers=stranger)
            assert denied.status_code == 409 and set(denied.json()) == {"error"}
            assert first["token"] not in denied.text and first["job_id"] not in denied.text
        for headers in ({"Idempotency-Key": "run-1"}, {**owner, "X-Idempotency-Token": "short"}):
            assert b.post(PREFIX + "/jobs", json=request_input, headers=headers).status_code == 422
        for stage in ("queued", "completed"):
            if stage == "completed":
                process_one(db, store, "test", inline=True)
            replay = a.post(PREFIX + "/jobs", json=request_input, headers=owner)
            assert replay.status_code == 200 and replay.json()["job_id"] == first["job_id"]
            assert replay.json()["token"] == first["token"] and replay.json()["state"] == stage
            assert b.post(PREFIX + "/jobs", json=request_input, headers=stranger).status_code == 409
            for key, method in (("status", "get"), ("cancel", "post"), ("report", "get"), ("export", "get")):
                assert getattr(b, method)(first["links"][key], headers=auth(own_b)).status_code == 404
        assert a.get(first["links"]["report"], headers=auth(first)).status_code == 200
        assert a.get(first["links"]["export"], headers=auth(first)).status_code == 200
    # The caller retained the proof before POST; recovery does not need the lost response or the same IP.
    with TestClient(create_app(db, store, config), client=("203.0.113.1", 6000)) as restarted:
        recovered = restarted.post(PREFIX + "/jobs", json=request_input, headers=owner)
        assert recovered.status_code == 200 and recovered.json()["token"] == first["token"]
        assert recovered.json()["state"] == "completed"
