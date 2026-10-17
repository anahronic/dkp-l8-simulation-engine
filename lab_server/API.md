# Lab server API v1

Run with Python 3.12 and `pip install -r requirements-server.txt`. From the repository root,
start these two processes (the default database and store paths match):

```sh
python -m uvicorn lab_server.app:app --host 127.0.0.1 --port 8000
python -m lab_server.worker --db simulation/outputs/lab-server/jobs.sqlite3 --store simulation/outputs/lab-server/store
```

The API process does no simulation work. `--once` makes the worker claim and process at most
one job, then exit. `LAB_SERVER_DB` and `LAB_SERVER_STORE` override the API paths; pass the
same paths explicitly to the worker. `JOB_TIMEOUT` overrides the worker timeout in seconds.
Programmatic callers can use `create_app(db_path, store_dir, settings=None)` and
`process_one(db, store, worker_id, clock=None, inline=False, settings=None)`. Settings accept
`lab_server.Settings`, a mapping, or an object with matching attributes. Inline execution
is a serial test helper without preemptive termination; production uses spawned children.

All routes below have prefix `/api/lab/v1`. Requests and responses are JSON except the ZIP
download. Dates in job status are Unix seconds (UTC); unset values are `null`. Bodies must
be valid JSON; non-finite JSON constants are refused. Unknown request, variant, and module
input fields are rejected. Only installed module IDs and validated module data are accepted;
there is no client-selected code, shell command, file name, output path, or URL execution.

## Requests, validation, and discovery

The request schema is `dkp-lab-input/1`, with exactly these envelope keys:

```json
{
  "schema": "dkp-lab-input/1",
  "module": "work_cycle",
  "variants": [{"name": "A", "input": {}}]
}
```

Module inputs are validated by the shared core, with declared defaults made visible in the
resolved input. `input: {}` uses those defaults where available; a module may require fields.
For the S-LAB-08 `work_cycle` example, obtain `/scenarios/work_cycle` and submit its first
variant, `staffed_36`. The scenarios endpoint returns **all** examples, which can exceed the
per-request variant limit; select up to six before validating or submitting. Variant names
start with a letter or digit, contain only letters, digits, `_` or `-`, and are at most 40
characters. Names must be distinct.

| Method and route | Request | Success response |
| --- | --- | --- |
| `GET /health` | No body or token | 200, health object below |
| `GET /catalog` | No body or token | 200, unchanged `lab.api.catalog_payload()` |
| `GET /scenarios` | No body or token | 200, array of module descriptions below |
| `GET /scenarios/{module_id}` | Installed module ID | 200, `lab.api.example_request(module_id)`, in the request schema above; unknown module: 404 |
| `POST /validate` | Lab request | 200, `{"ok":true,"problems":[],"resolved":{"A":{...}}}` from `lab.api.validate_payload`; invalid: 422 with problems, no job created |

Example health response (digest and corpus values abbreviated):

```json
{
  "ok": true,
  "lab_version": "<installed version>",
  "identity": {
    "lab_version": "<installed version>", "lab_code_digest": "<sha256>",
    "registry_digest": "<sha256>", "corpus": {},
    "engine_version": "<installed version>", "engine_code_digest": "<sha256>"
  },
  "queue": {"queued": 2, "running": 1, "completed": 4, "cancelled": 0, "failed": 0},
  "worker_heartbeat_age_s": 0.2
}
```

`ok` indicates that the API and database responded; it does not assert worker availability.
Heartbeat age is the age of the newest worker heartbeat, or `null` if none is recorded.
Idle workers heartbeat too. Queue counts are aggregate counts without job IDs or inputs.
The identity object is exactly `lab.core.run.identity()`.

The catalog object has keys `lab_version`, `corpus`, `counts`, `documents`,
`unresolved_dependencies`, `ambiguous_references`, `broken_section_references`, `modules`,
and `prefixes`. A module manifest contains `id`, `version`, `title`, `summary`, `protocols`,
`inputs`, `hypotheses`, `causal_note`, `examples`, `example_kinds`, and `failure_examples`.
These are the existing lab catalog structures; `inputs` describes field types, bounds,
defaults, and sources. For example, a catalog response includes
`{"lab_version":"...","modules":[{"id":"work_cycle","inputs":{...},...}],...}`.

Example scenarios entry (titles shortened):

```json
[
  {
    "id": "work_cycle", "title": {"en": "...", "ru": "..."},
    "examples": [{"name": "staffed_36", "kind": "reference"}]
  }
]
```

Example kinds are `reference`, `counterexample`, `alternative`, or `noncompliant`.

## Jobs and tokens

`POST /jobs` takes the lab request above, validates it on the server, then enqueues it.
An optional `Idempotency-Key` header must match `[A-Za-z0-9_-]{1,64}`. When present,
`X-Idempotency-Token` is required: 32..128 base64url characters, generated from at least
32 cryptographically random bytes (e.g. `secrets.token_urlsafe(32)`). Generate and persist
this private replay proof **before the first POST**, separately from the key; reuse both
on retries. Missing/malformed proof returns 422. Keyless submission is unchanged. Success is 202:

```json
{
  "job_id": "0123456789abcdef0123456789abcdef",
  "token": "<base64url token>",
  "state": "queued",
  "links": {
    "status": "/api/lab/v1/jobs/0123456789abcdef0123456789abcdef",
    "cancel": "/api/lab/v1/jobs/0123456789abcdef0123456789abcdef/cancel",
    "report": "/api/lab/v1/jobs/0123456789abcdef0123456789abcdef/report",
    "export": "/api/lab/v1/jobs/0123456789abcdef0123456789abcdef/export"
  }
}
```

A replay of the same key, private replay proof and normalized request returns 200 with the same job ID and token,
and its current state. This also works when the queue is full and across server restarts.
The digest is SHA-256 of canonical JSON of the validated, default-resolved request;
JSON key ordering and omitted-versus-explicit defaults do not change it. Variant ordering
is retained. With the correct proof, a different normalized request returns 409. A different
proof returns a generic 409 without job id, token or state, regardless of the body. Keys
remain global until the job is purged; a visitor whose key collides must choose another key.
The key alone grants no access. IP addresses play no role in ownership (including shared IPs).
Only the proof's SHA-256 hash is stored; comparisons and insertion run under the same SQLite
writer transaction. Treat the proof as a credential, keep it out of logs and URLs, and send
it only over HTTPS. CORS permits the new header. Clients using keyed submissions must add it.
Lost responses can be recovered with the retained proof after a restart, including completed
jobs and a full queue. Without a key, repeated submissions create independent jobs.

Existing databases gain a nullable `replay_hash` column. Legacy jobs without a proof cannot
be replayed through POST /jobs (409); their previously issued job tokens still authorize all
four job routes. No proof can be attached to a legacy job by guessing its key/body.

Every `/jobs/{id}` route, including cancellation and artifacts, requires either:

```http
Authorization: Bearer <token>
```

or `X-Job-Token: <token>`. A Bearer token takes precedence when both are supplied. Tokens
are never accepted in query parameters. Missing token returns 401. A wrong token and an
unknown job both return the same 404 response. Comparison uses `hmac.compare_digest` on
token hashes. Tokens are unpadded base64url HMAC-SHA256(server_secret, job_id). Only their
SHA-256 hashes are stored in SQLite, and application code does not log tokens. Keep request
authorization headers and response bodies out of deployment logs as well.

`LAB_SERVER_SECRET` supplies the secret as UTF-8 bytes; otherwise a random 32-byte secret is
atomically created at `<store>/.secret`, with mode 0600 on systems supporting POSIX modes.
Keep this file and the database together across restarts, and use a private store directory
(Windows deployments should restrict its ACL). Do not change the secret while retained
jobs need idempotent token recovery. Multiple API processes must share the same secret.

| Method and route | Request | Success / job-specific errors |
| --- | --- | --- |
| `GET /jobs/{id}` | Token; no body | 200, status object below |
| `POST /jobs/{id}/cancel` | Token; no body needed | 200, status object; queued jobs become cancelled immediately, running jobs record a cancellation request; final jobs: 409 |
| `GET /jobs/{id}/report` | Token; no body | 200, `report.json`, `application/json`; not completed: 409 |
| `GET /jobs/{id}/export` | Token; no body | 200, ZIP, `application/zip`, `Content-Disposition: attachment; filename="lab-<id>.zip"`; not completed: 409 |

Example queued status and cancellation response shape:

```json
{
  "job_id": "0123456789abcdef0123456789abcdef",
  "state": "queued", "progress": 0.0, "message": "queued", "queue_position": 1,
  "created_at": 1792100000.0, "started_at": null, "finished_at": null,
  "error": null, "result_id": null, "input_ids": null
}
```

States are `queued`, `running`, `completed`, `cancelled`, and `failed`. Position is 1-based
among queued jobs, otherwise `null`. Progress is a fraction from 0 to 1. Messages are
informational. Once completed, `result_id` is a SHA-256 hex digest and `input_ids` is:

```json
{"request": "<whole request input_id>", "variants": {"A": "<variant input_id>"}}
```

Failed status has a string `error` (for example `"timeout"`). A running cancellation may
initially return `"state":"running","message":"cancellation requested"`; poll until
cancelled. Cancellation that wins the publication lock prevents completion; cancellation
after completion returns 409. GETs do not consume POST rate-limit tokens.

`report.json` is the shared `dkp-lab-result/1` document, for example:

```json
{
  "schema": "dkp-lab-result/1",
  "module": {"id": "work_cycle", "version": "...", "title": {}, "protocols": []},
  "identity": {}, "request": {},
  "variants": {
    "A": {"resolved_input": {}, "input_id": "...", "outputs": {}, "checks": [],
          "summary": {}, "explain": [], "result_id": "..."}
  },
  "comparison": {}, "hypotheses": [], "causal_note": null, "epistemic": {},
  "input_id": "...", "result_id": "..."
}
```

The abbreviated structures contain the same module outputs, checks, explanations, and
epistemic notes as a direct core run. The ZIP contains `request.json`, `result.json`,
`report.en.md`, `report.ru.md`, `report.html`, `provenance.json`, `REPLAY.md`, `SHA256SUMS`,
and `records/<variant>.jsonl` when the module emits records. Runtime `server` appears only
in provenance, outside every input and result ID. With the same code, corpus, and normalized
input, IDs equal CLI and browser IDs. The wrapper lives outside `lab/`, so queue/API changes
do not change `lab_code_digest`. `lab.api.run_package` shares computation and packaging
without using the browser's `_last_package` cache.

## Errors and limits

Errors use a single envelope; `problems` is optional:

```json
{"error":{"code":"invalid_input","message":"Invalid lab input","problems":["request.path: unknown key"]}}
```

| HTTP | Code | Meaning |
| --- | --- | --- |
| 400 | `bad_json` | Malformed JSON, non-finite JSON constant, or invalid Content-Length |
| 401 | `missing_token` | No job token supplied |
| 404 | `not_found` | Unknown route/module/job, wrong token, or unavailable artifact |
| 409 | `conflict` | Idempotency conflict, final-job cancellation, or artifact before completion |
| 413 | `too_large` | Body exceeds limit, checked against both Content-Length and received bytes |
| 422 | `invalid_input` | Invalid request/module input, variant limit, or missing/malformed idempotency key/proof |
| 429 | `rate_limited` | Per-IP POST token bucket exhausted; `Retry-After: 6` |
| 503 | `queue_full` | Queued-job limit reached; `Retry-After: 5` |
| 405 | `method_not_allowed` | Unsupported HTTP method |
| 500 | `internal_error` | Unexpected server failure; no exception details returned |

All POST routes consume one token, including invalid requests and cancellations. The bucket
uses the ASGI client IP (no application parsing of forwarded headers). Configure trusted
proxy handling at the ASGI server if applicable. Buckets are in memory per API process,
reset on restart, and are not a distributed limiter. Default settings:

| Setting | Default |
| --- | --- |
| `MAX_BODY_BYTES` | 262144 |
| `MAX_VARIANTS` | 8 server cap; core currently enforces the stricter limit of 6 |
| `RATE_PER_MINUTE`, `RATE_BURST` | 10, 5 |
| `MAX_QUEUED` | 50 (running jobs excluded) |
| `MAX_ATTEMPTS` | 3 expired leases |
| `JOB_TIMEOUT` | 120 seconds, including child startup and packaging |
| `LEASE_SECONDS`, `POLL_SECONDS` | 30, 0.1 seconds |
| `RETENTION_SECONDS`, `PURGE_EVERY` | 604800 (7 days), 100 worker loops |

## Restart, publication, and retention

SQLite uses WAL, a separate connection per call, and atomic writer transactions. Queued
jobs survive restarts. Claims first recover expired running leases, incrementing attempts;
the third expiry ends in `failed` with error `"lease expired 3 times"`. Thus an unrecoverable
job receives at most three execution attempts under the default setting. Cancel requests
survive crashes and end cancelled on lease recovery. Normal computation failures and
timeouts are final and are not retried automatically.

Workers renew leases and write their own heartbeat while waiting for child progress.
Each computation runs in a fresh spawn process. The supervisor terminates it on timeout,
cancellation, or loss of lease. Files are staged per lease; only a current, unexpired owner
can publish files and update the completed row while holding the SQLite writer lock.
A stale worker cannot overwrite a newer owner's package. Partial files from a publication
crash are not exposed without a completed row and can be replaced by the recovered owner.

The worker purges finished jobs older than seven days on startup/its first loop and every
100 loops thereafter. It removes job rows, their idempotency keys, report/package files,
and abandoned attempt files. Active jobs are retained. Purging requires a running worker
and is periodic, so retention is not an exact deletion deadline. A purged ID returns 404
with a supplied token. Do not serve the store directory as static content.

Packages are private to the token holder. Publishing a demonstration package is a separate,
explicit action **not provided by this API**. This implementation does not deploy a service
or alter the historical architecture-deviation document.
