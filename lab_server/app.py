"""Private job API. Computations run only in the separate worker."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException

from lab import LAB_VERSION, api
from lab.core.run import identity
from lab.modules import MODULES
from lab_server import settings_from
from lab_server.queue import Conflict, Queue, QueueFull

PREFIX = "/api/lab/v1"


class APIError(Exception):
    def __init__(self, status, code, message, problems=None, headers=None):
        self.status, self.code, self.message = status, code, message
        self.problems, self.headers = problems, headers


def _secret(store):
    value = os.environ.get("LAB_SERVER_SECRET")
    if value:
        return value.encode()
    target = store / ".secret"
    if not target.exists():
        temporary = store / f".secret-{uuid.uuid4().hex}"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as file:
                file.write(os.urandom(32))
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(temporary, target)  # Publish a fully written secret, never overwrite it.
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)
    value = target.read_bytes()
    if not value:
        raise RuntimeError("Server secret file is empty")
    return value


class TokenBucket:
    def __init__(self, rate, burst, now=time.monotonic):
        self.rate, self.burst, self.now = rate / 60, burst, now
        self.buckets = {}
        self.lock = threading.Lock()

    def take(self, client):
        with self.lock:
            now = self.now()
            lifetime = max(60, self.burst / self.rate) if self.rate > 0 else math.inf
            self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < lifetime}
            tokens, stamp = self.buckets.get(client, (self.burst, now))
            tokens = min(self.burst, tokens + (now - stamp) * self.rate)
            allowed = tokens >= 1
            self.buckets[client] = (tokens - 1 if allowed else tokens, now)
            return allowed


def create_app(db_path, store_dir, settings=None):
    config = settings_from(settings)
    store = Path(store_dir).resolve()
    store.mkdir(parents=True, exist_ok=True)
    secret = _secret(store)

    def token(job_id):
        return base64.urlsafe_b64encode(hmac.digest(secret, job_id.encode(), "sha256")).rstrip(b"=").decode()

    queue = Queue(db_path, store=store, max_queued=config.MAX_QUEUED,
                  max_attempts=config.MAX_ATTEMPTS, token_factory=token)
    limiter = TokenBucket(config.RATE_PER_MINUTE, config.RATE_BURST)

    async def post_guard(request: Request):
        if request.method != "POST":
            return
        client = request.client.host if request.client else "unknown"
        if not limiter.take(client):
            raise APIError(429, "rate_limited", "POST rate limit exceeded", headers={"Retry-After": "6"})
        length = request.headers.get("content-length")
        if length is not None:
            try:
                length = int(length)
                if length < 0:
                    raise ValueError
            except ValueError:
                raise APIError(400, "bad_json", "Invalid Content-Length")
            if length > config.MAX_BODY_BYTES:
                raise APIError(413, "too_large", "Request body exceeds the byte limit")
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > config.MAX_BODY_BYTES:
                raise APIError(413, "too_large", "Request body exceeds the byte limit")
            body.extend(chunk)
        request.state.body = bytes(body)

    app = FastAPI(dependencies=[Depends(post_guard)])
    # The Keeper panel runs in a sandboxed iframe (opaque origin "null"); access is by bearer token, never cookies.
    app.add_middleware(CORSMiddleware, allow_origins=list(config.CORS_ORIGINS), allow_credentials=False,
                       allow_methods=["GET", "POST", "OPTIONS"],
                       allow_headers=["Content-Type", "Authorization", "X-Job-Token", "Idempotency-Key"],
                       expose_headers=["Retry-After", "Content-Disposition"], max_age=600)
    app.state.queue, app.state.settings, app.state.limiter = queue, config, limiter

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        error = {"code": exc.code, "message": exc.message}
        if exc.problems is not None:
            error["problems"] = exc.problems
        return JSONResponse({"error": error}, status_code=exc.status, headers=exc.headers)

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return await api_error(request, APIError(409, "conflict", str(exc)))

    @app.exception_handler(QueueFull)
    async def full(request, exc):
        return await api_error(request, APIError(503, "queue_full", str(exc), headers={"Retry-After": "5"}))

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return await api_error(request, APIError(exc.status_code, code, str(exc.detail), headers=exc.headers))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return await api_error(request, APIError(422, "invalid_input", "Invalid request",
                                                [str(e["msg"]) for e in exc.errors()]))

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return await api_error(request, APIError(500, "internal_error", "Internal server error"))

    def checked_body(request):
        def reject_constant(value):
            raise ValueError("Non-finite JSON constant")

        try:
            body = json.loads(request.state.body, parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise APIError(400, "bad_json", "Request body must be valid JSON")
        if isinstance(body, dict) and not isinstance(body.get("module"), str):
            raise APIError(422, "invalid_input", "Invalid lab input", ["request.module: expected string"])
        variants = body.get("variants") if isinstance(body, dict) else None
        if isinstance(variants, list) and len(variants) > min(8, config.MAX_VARIANTS):
            raise APIError(422, "invalid_input", "Invalid lab input", ["request.variants: server cap exceeded"])
        try:
            validated = api.validate_payload(body)
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise APIError(422, "invalid_input", "Invalid lab input", ["request: invalid value or type"])
        if not validated["ok"]:
            raise APIError(422, "invalid_input", "Invalid lab input", validated["problems"])
        return body, validated

    def authorized(job_id, request):
        authorization = request.headers.get("authorization", "")
        parts = authorization.split()
        supplied = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else request.headers.get("x-job-token")
        if not supplied:
            raise APIError(401, "missing_token", "A job token is required")
        job = queue.get(job_id)
        digest = hashlib.sha256(supplied.encode()).hexdigest()
        valid = hmac.compare_digest(digest, (job or {}).get("token_hash") or "0" * 64)
        if job is None or not valid:
            raise APIError(404, "not_found", "Job not found")
        return job

    def status(job):
        keys = ("state", "progress", "message", "created_at", "started_at", "finished_at",
                "error", "result_id", "input_ids")
        return {"job_id": job["id"], **{k: job[k] for k in keys}, "queue_position": queue.position(job["id"])}

    @app.get(PREFIX + "/health")
    def health():
        return {"ok": True, "lab_version": LAB_VERSION, "identity": identity(),
                "queue": queue.counts(), "worker_heartbeat_age_s": queue.worker_heartbeat_age()}

    @app.get(PREFIX + "/catalog")
    def catalog():
        return api.catalog_payload()

    @app.get(PREFIX + "/scenarios")
    def scenarios():
        return [{"id": m.id, "title": m.title,
                 "examples": [{"name": n, "kind": m.example_kind(n)} for n in m.ordered_examples()]}
                for m in MODULES.values()]

    @app.get(PREFIX + "/scenarios/{module_id}")
    def scenario(module_id: str):
        if module_id not in MODULES:
            raise APIError(404, "not_found", "Module not found")
        return api.example_request(module_id)

    @app.post(PREFIX + "/validate")
    def validate(request: Request):
        return checked_body(request)[1]

    @app.post(PREFIX + "/jobs")
    def enqueue(request: Request):
        body, _ = checked_body(request)
        key = request.headers.get("idempotency-key")
        if key is not None and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", key) is None:
            raise APIError(422, "invalid_input", "Invalid Idempotency-Key",
                           ["Idempotency-Key: expected 1..64 letters, digits, '_' or '-'"])
        job, created = queue.enqueue(body, key)
        base = f"{PREFIX}/jobs/{job['id']}"
        return JSONResponse({"job_id": job["id"], "token": token(job["id"]), "state": job["state"],
                             "links": {"status": base, "cancel": base + "/cancel", "report": base + "/report",
                                       "export": base + "/export"}}, status_code=202 if created else 200,
                            headers={"Cache-Control": "no-store"})

    @app.get(PREFIX + "/jobs/{job_id}")
    def job_status(job_id: str, request: Request):
        return JSONResponse(status(authorized(job_id, request)), headers={"Cache-Control": "no-store"})

    @app.post(PREFIX + "/jobs/{job_id}/cancel")
    def cancel(job_id: str, request: Request):
        authorized(job_id, request)
        job = queue.cancel(job_id)
        if job is None:
            raise APIError(404, "not_found", "Job not found")
        return JSONResponse(status(job), headers={"Cache-Control": "no-store"})

    def artifact(job_id, request, key, media_type, filename=None):
        job = authorized(job_id, request)
        if job["state"] != "completed":
            raise Conflict("Job is not completed")
        if not job[key] or not Path(job[key]).is_file():
            raise APIError(404, "not_found", "Job artifact not found")
        return FileResponse(job[key], media_type=media_type, filename=filename,
                            headers={"Cache-Control": "private, no-store"})

    @app.get(PREFIX + "/jobs/{job_id}/report")
    def report(job_id: str, request: Request):
        return artifact(job_id, request, "report_path", "application/json")

    @app.get(PREFIX + "/jobs/{job_id}/export")
    def export(job_id: str, request: Request):
        return artifact(job_id, request, "package_path", "application/zip", f"lab-{job_id}.zip")

    return app


app = create_app(os.environ.get("LAB_SERVER_DB", "simulation/outputs/lab-server/jobs.sqlite3"),
                 os.environ.get("LAB_SERVER_STORE", "simulation/outputs/lab-server/store"))
