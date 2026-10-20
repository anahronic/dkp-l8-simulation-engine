# Keeper gateway (Python 3.12)

KT10 role/data policy: [ROLE_POLICY.md](ROLE_POLICY.md). Contract and source-link origins:
[KEEPER_API.md](KEEPER_API.md). Historical 34/36 correction:
[KT10_CORRECTION_2026-10-20.md](KT10_CORRECTION_2026-10-20.md).
For the full site corpus, pass `--site /path/to/live-site/website` (the deployed
redesign source, not the widget worktree); `--site-pages` may separately specify
the main-page source. The manifest records exact revisions, file digests and route
coverage/exclusions. Private search keys require `--ru` and never become public
fragments. Corpus update is an installer build, not a visitor operation.
Build the pinned corpus: `python -m keeper.corpus build simulation/outputs/keeper-corpus`.
Set `KEEPER_CORPUS` to the resulting `corpus-<version>.jsonl` (no automatic rebuild or network retrieval).
Run: `python -m uvicorn keeper.gateway:app --host 127.0.0.1 --port 8001`; routes are under `/api/keeper/v1`.
Requires the existing server dependencies (FastAPI, httpx, uvicorn); start Ollama separately with the selected model available.
Environment/settings: `KEEPER_OLLAMA=http://127.0.0.1:11434`, `KEEPER_MODEL=qwen3.5:2b`, `KEEPER_LAB_URL=http://127.0.0.1:8000`.
`KEEPER_LOG=simulation/outputs/keeper`; keep this directory private (restrict Windows ACLs) and outside static hosting.
Limits: `MAX_CONCURRENT=1`, `MAX_WAITING=8`, `RATE_PER_MINUTE=6`, `RATE_BURST=6`, `MAX_BODY_BYTES=16384`, `TOTAL_TIMEOUT=150`.
Generation: `NUM_PREDICT=700` total reported output tokens, `NUM_CTX=8192`, `NO_SOURCE_SCORE=9.0`; all names also accept environment values.
`create_app(settings)` accepts a mapping or settings object; `OLLAMA_TRANSPORT`/`LAB_TRANSPORT` inject httpx transports for offline tests.
Only three allowlisted tools exist; no shell/code execution, URL fetching from prompts, or lab job submission. Tool data containing paths/URLs/code syntax is rejected conservatively (including slashes in search queries).
Proposals merge the first module example with explicit visitor values, validate through `lab.api`, and expose every resolved field for visitor confirmation.
Origin rule: `user` requires a value bound to its field by the published intake parser, including demand. Unsupplied schema `hypothesis`/`alternative` and H-WC-1..4 fields retain `hypothesis`; other unsupplied fields retain `default`.
Parameter gap policy: intake and model proposals share the same workers/days/constant-demand grammar. Values in the wrong role, unsupported fields and competing values require clarification (`missing`); no proposal is emitted. Repetition of the same value in a role is allowed. Explicit field edits are available before the visitor confirms a run.
Each retrieval supplies at most five 1500-character excerpts; two extra searches and three tool rounds are allowed. Explain uses labelled report fields and FAIL/UNKNOWN checks with pinned provision citations. Known Q-012/Q-013 notices for S-LAB-08 are bound to requirements independently of retrieval; general open-question notices still depend on search.
Contract gaps: omitted lang defaults to en; lang accepts 2–3-letter codes with an optional subtag; page fields are optional; relative paths are accepted but never fetched; no refusal heuristic is implemented.
SSE sends only statuses before the post-checked final answer; no raw text deltas are exposed. Before streaming, errors use HTTP status codes; after headers, transport/timeout failures use `event: error` with the same envelope (HTTP status cannot change). Disconnect closes generation.
Explain forwards only the visitor Bearer token to the configured lab; 401/404/409 are preserved, other report failures return 503 `lab_unavailable`. Short output lists mean at most 24 scalars; nested numeric outputs are flattened.
Logs retain hashes, fids, safe tool names, flag codes and job ids, never texts/arguments/tokens; startup purges entries older than 30 days. Rate limits are per process, using request.client; configure trusted proxy headers in uvicorn.
Checks remove unknown bracket citations and unverified long quote marks. Ordinary answers are visibly labelled unverified: a real citation and removal of quote marks do not prove a claim. Explain never calls Ollama: it returns `answer_kind=deterministic_summary`, the structured summary and result id, even when the model is down. The only derived percentage is Decimal(coverage.covered_fraction) × 100, with its origin labelled. The report card and package remain independent of explanation. Test: `python -m pytest -q -p no:cacheprovider tests/keeper`.


Local model metadata (2026-10-17): `qwen3.5:2b` is **Q8_0**, confirmed by `ollama show`
and the local manifest. See [model-metadata.json](model-metadata.json) for exact output,
full manifest/layer digests and sizes, and [deployment limits](../deploy/README.md).
The model layer is 2,012,012,448 bytes; all referenced blobs including the projector
sum to 2,683,398,370 bytes. These disk sizes do not predict runtime RAM or latency.

Offline KT9 probes (controlled faulty model transport, actual engine report):
`python -m keeper.probes_kt9 /path/to/corpus-839086c3df09.jsonl --check`.
JSON is written to stdout; `--check` fails on a regression. The before run used the
review's original probe before the service edits; the after probe supplies independent
visitor replay proofs per the revised Lab contract. Keyed job clients must persist
`X-Idempotency-Token` before submission; see [Lab API](../lab_server/API.md).
