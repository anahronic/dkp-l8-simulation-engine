"""Independent CP9 probes. Run from the engine root:
python /path/to/kt9_probes.py /path/to/corpus-839086c3df09.jsonl
No live Ollama or production server is used.
"""
import json
import secrets
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path.cwd()))

import httpx
from fastapi.testclient import TestClient

from keeper.gateway import create_app as keeper_app
from keeper.guardrails import proposal
from lab.core.run import run_request
from lab_server.app import create_app as lab_app
from lab_server.worker import process_one

request = {
    "schema": "dkp-lab-input/1",
    "module": "work_cycle",
    "variants": [{
        "name": "private",
        "input": {"workers": 12, "horizon_days": 14, "demand": [3] * 24}
    }]
}
out = {}
with TemporaryDirectory() as t:
    p = Path(t)
    db, store = p / "jobs.db", p / "store"
    app = lab_app(db, store, {"RATE_BURST": 1000})
    with TestClient(app, client=("198.51.100.10", 4000)) as a, \
         TestClient(app, client=("198.51.100.20", 5000)) as b:
        headers = {"Idempotency-Key": "run-1", "X-Idempotency-Token": secrets.token_urlsafe(32)}
        other = {**headers, "X-Idempotency-Token": secrets.token_urlsafe(32)}
        first = a.post("/api/lab/v1/jobs", json=request, headers=headers)
        second = b.post("/api/lab/v1/jobs", json=request, headers=other)
        fa, fb = first.json(), second.json()
        auth_b = {"Authorization": "Bearer " + fb.get("token", "")}
        status = b.get("/api/lab/v1/jobs/" + fa["job_id"], headers=auth_b)
        cancel = b.post(
            "/api/lab/v1/jobs/" + fa["job_id"] + "/cancel",
            headers=auth_b
        )
        out["KT9-GPT-01"] = {
            "A_submit": first.status_code,
            "B_submit": second.status_code,
            "same_job": fa.get("job_id") == fb.get("job_id"),
            "same_token": fa.get("token") == fb.get("token"),
            "B_reads_A_status": status.status_code,
            "B_cancels_A_job": cancel.status_code
        }

        # Owner cleanup keeps the next worker claim on the completed-job probe after isolation is fixed.
        a.post("/api/lab/v1/jobs/" + fa["job_id"] + "/cancel",
               headers={"Authorization": "Bearer " + fa["token"]})
        headers["Idempotency-Key"] = other["Idempotency-Key"] = "run-2"
        fa = a.post("/api/lab/v1/jobs", json=request, headers=headers).json()
        completed = process_one(db, store, "review", inline=True)
        assert completed["id"] == fa["job_id"] and completed["state"] == "completed"
        fb = b.post("/api/lab/v1/jobs", json=request, headers=other).json()
        auth_b = {"Authorization": "Bearer " + fb.get("token", "")}
        root = "/api/lab/v1/jobs/" + fa["job_id"]
        out["KT9-GPT-01"].update({
            "B_reads_A_report": b.get(root + "/report", headers=auth_b).status_code,
            "B_downloads_A_package": b.get(root + "/export", headers=auth_b).status_code
        })

question = "Our staff is 12 workers. We plan for 14 days. Explain work_cycle."
candidate = {"workers": 14, "horizon_days": 12}
result = proposal("work_cycle", candidate, question, "en")
out["KT9-GPT-02"] = {
    "question": question,
    "model_params": candidate,
    "missing": result.get("missing"),
    "accepted_fields": [
        {k: f[k] for k in ("key", "value", "origin")}
        for f in result.get("fields", [])
        if f["key"] in candidate
    ]
}

report = run_request(request)

async def fake_model(req):
    if req.url.path == "/api/show":
        return httpx.Response(200, json={"capabilities": ["completion", "tools"]})
    if req.url.path in ("/api/tags", "/api/ps"):
        return httpx.Response(200, json={
            "models": [{"name": "qwen3.5:2b", "digest": "fixture"}]
        })
    return httpx.Response(200, json={
        "message": {
            "role": "assistant",
            "content": "The report shows a deficit of 999999 workers. [WORK-CYCLE §8.1]"
        },
        "done": True, "eval_count": 20
    })

async def fake_lab(req):
    return httpx.Response(200, json=report)

with TemporaryDirectory() as t:
    app = keeper_app({
        "KEEPER_CORPUS": str(Path(sys.argv[1]).resolve()),
        "KEEPER_LOG": t,
        "OLLAMA_TRANSPORT": httpx.MockTransport(fake_model),
        "LAB_TRANSPORT": httpx.MockTransport(fake_lab),
        "RATE_BURST": 1000
    })
    with TestClient(app) as c:
        response = c.post("/api/keeper/v1/explain", json={
            "job_id": "0" * 32, "token": "fixture", "lang": "en"
        })
        data = response.json()
        out["KT9-GPT-03"] = {
            "http": response.status_code,
            "real_max_deficit": report["variants"]["private"]["outputs"]["coverage"]["max_deficit"],
            "state": data.get("state"),
            "answer": data.get("answer"),
            "flags": data.get("flags"),
            "false_number_remains": "999999" in data.get("answer", "")
        }

print(json.dumps(out, ensure_ascii=False, indent=2))


if "--check" in sys.argv:
    isolation = out["KT9-GPT-01"]
    assert isolation["A_submit"] == 202 and isolation["B_submit"] == 409
    assert not isolation["same_job"] and not isolation["same_token"]
    assert all(isolation[k] in (401, 404) for k in (
        "B_reads_A_status", "B_cancels_A_job", "B_reads_A_report", "B_downloads_A_package"))
    assert set(out["KT9-GPT-02"]["missing"]) == {"workers", "horizon_days"}
    assert not out["KT9-GPT-03"]["false_number_remains"]
    assert out["KT9-GPT-03"]["http"] == 200
