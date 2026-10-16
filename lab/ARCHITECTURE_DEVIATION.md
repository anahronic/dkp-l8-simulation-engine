# Deviation: browser-only execution instead of the server API

**Status (2026-10-16, review КТ8 TZ §9):** the server path is **implemented in code and tested, not deployed**.
Package `lab_server/` (outside `lab/`, so the HTTP wrapper and the queue do not enter `lab_code_digest`):
FastAPI routes under `/api/lab/v1` (`lab_server/API.md`), a separate worker process, a durable SQLite queue
with atomic take, lease, recovery after a lost lease, no publication by a stale worker, cancellation,
idempotency keys and per-job tokens; packages are stored per job, never in the browser bridge's
`_last_package`.  Tests: `tests/server/` (identity with CLI ids, job isolation, queue races, lease expiry,
timeout, cancellation).  The browser path is kept; both call the same `lab.api` code.  B3 is closed only
after the routes run on the server with the post-deployment check; until then this document stays the
record of what the browser-only path lacks.  The text below is the state before `lab_server/`.

**Earlier status:** OPEN DEVIATION from the lab specification §6.4–§6.5.  The specification is not
changed; the server API counts as **not implemented** until a separate decision.

## What the specification asks

§6.4: the existing Python engine behind a FastAPI API, a separate calculation process, a
durable SQLite queue (atomic take, lease, crash recovery, no double publication), visible
queue, progress, completion, cancellation and errors; Python version and dependencies fixed
after checking the server.  §6.5: routes `/api/lab/v1/catalog`, `scenarios`, `validate`,
`jobs`, `jobs/{id}`, `jobs/{id}/cancel`, `jobs/{id}/report`, `jobs/{id}/export`, `health`;
idempotency keys; access to a job limited by a session or job token; no user Python, shell,
`eval`, output paths or URLs; server-side validation independent of the browser form.

## What exists

The same `lab.api` functions run in the visitor's browser: Pyodide 314.0.7 (CPython 3.14.2
compiled to WebAssembly) in a module Web Worker, loading a deterministic bundle whose SHA-256
is checked against `lab-bundle.json`.  There is no HTTP API, no queue, no job store, no
tokens and no server-side validation.  The reason given at the time — server changes need
sudo, static hosting does not — explains the choice; it does not make the two equivalent.

## Comparison

| Aspect | Browser-only (current) | Server API (specified) |
|---|---|---|
| Where inputs go | stay in the browser | sent to and stored on the server; needs a retention rule |
| Load and cost | visitor's device; nothing on the server | server CPU and memory; queue and limits needed |
| Heavy work (ensembles, Phase 3, 30-run comparisons) | impractical: memory and time of a tab, stops when the tab closes | feasible: background worker, durable queue |
| Job history, shared and published runs | none (only downloaded packages) | possible: job ids, stored reports, public demonstration results |
| Cancellation, crash | cancel = terminate the Worker; crash loses the run | lease and recovery; status survives the page |
| Runtime control | Pyodide version pinned by URL; device and browser vary | fixed Python and pinned dependencies on one machine |
| Who ran the code | the visitor's browser; the code can be altered locally, so a package from the browser is a self-declared result (like any local CLI run) | the server; a result can carry a server attestation of which code ran (still not a calibration or admission) |
| Supply chain | Pyodide and packages loaded from jsDelivr at run time; the lab bundle is checked against a digest served by the same site (consistency, not an independent signature) | dependencies installed once and pinned; no third-party code at request time |
| Attack surface | static files only; no endpoint to flood or to leak other users' jobs | endpoints: needs rate limits, size limits, job tokens, isolation, validation |
| Privacy | strong: no inputs leave the device | depends on retention and access control |
| Deployment | static copy to the web root (no sudo) | nginx route and a systemd service (sudo), monitoring |

## Reproducibility consequences

- Same ids: for every installed module the `input_id` and `result_id` computed in Pyodide
  equal those of CPython (`lab/tools/pyodide_check.*`, CI job `browser-runtime`), and
  packages made in Chromium replay in CPython.  This holds for pure-Python code; adding a
  numerical library (for example numpy) requires the comparison to be repeated.
- Browser results cannot be distinguished from results of locally modified code: anyone who
  needs to rely on a package must replay it (`python -m lab replay`).  The same is true for
  CLI runs.  A server attestation would identify the runtime, not make the model valid.
- Long or heavy runs are not reproducible in the browser in practice because they do not
  finish there; the server would be the only place to run and publish them.

## Possible decisions (not taken)

1. Keep browser-only and amend §6.4–§6.5 explicitly (author / GPT decision).
2. Build the server API as specified and deploy it (needs sudo on the server once).
3. Hybrid: browser for interactive runs; server API for heavy ensembles, stored and
   published demonstration results; both on the same `lab.api`, with the server and the
   browser cross-checking ids.

Until a decision, the lab specification's stage B is reported as PARTIAL: interface,
export and replay done; server API, queue and job access control not done.
