# Keeper gateway (Python 3.12)
Build the pinned corpus: `python -m keeper.corpus build simulation/outputs/keeper-corpus`.
Set `KEEPER_CORPUS` to the resulting `corpus-<version>.jsonl` (no automatic rebuild or network retrieval).
Run: `python -m uvicorn keeper.gateway:app --host 127.0.0.1 --port 8001`; routes are under `/api/keeper/v1`.
Requires the existing server dependencies (FastAPI, httpx, uvicorn); start Ollama separately with the selected model available.
Environment/settings: `KEEPER_OLLAMA=http://127.0.0.1:11434`, `KEEPER_MODEL=qwen3.5:2b`, `KEEPER_LAB_URL=http://127.0.0.1:8000`.
`KEEPER_LOG=simulation/outputs/keeper`; keep this directory private (restrict Windows ACLs) and outside static hosting.
Limits: `MAX_CONCURRENT=1`, `MAX_WAITING=8`, `RATE_PER_MINUTE=6`, `RATE_BURST=6`, `MAX_BODY_BYTES=16384`, `TOTAL_TIMEOUT=150`.
Generation: `NUM_PREDICT=700` total reported output tokens, `NUM_CTX=16384`, `NO_SOURCE_SCORE=9.0`; all names also accept environment values.
`create_app(settings)` accepts a mapping or settings object; `OLLAMA_TRANSPORT`/`LAB_TRANSPORT` inject httpx transports for offline tests.
Only three allowlisted tools exist; no shell/code execution, URL fetching from prompts, or lab job submission. Tool data containing paths/URLs/code syntax is rejected conservatively (including slashes in search queries).
Proposals merge the first module example with explicit visitor values, validate through `lab.api`, and expose every resolved field for visitor confirmation.
Origin rule: schema `hypothesis`/`alternative` plus H-WC-1..4 fields `phase_offsets`, `shift_starts`, `work_before_recovery`, `demand` override user/default origins; others are user if supplied, otherwise default.
Parameter gap policy: literal numeric overlap with the question is required; every supplied scalar must appear there. No overlap asks for supplied keys, or workers/horizon_days/demand if empty; ambiguity requires visitor review, never inferred values.
Each retrieval supplies at most five 1500-character excerpts; two extra searches and three tool rounds are allowed. Explain resolves FAIL/UNKNOWN requirement ids to pinned sections, capped at five provisions.
Contract gaps: omitted lang defaults to en; lang accepts 2–3-letter codes with an optional subtag; page fields are optional; relative paths are accepted but never fetched; no refusal heuristic is implemented.
SSE final replaces raw deltas. Before streaming, errors use HTTP status codes; after headers, transport/timeout failures use `event: error` with the same envelope (HTTP status cannot change). Disconnect closes generation.
Explain forwards only the visitor Bearer token to the configured lab; 401/404/409 are preserved, other report failures return 503 `lab_unavailable`. Short output lists mean at most 24 scalars; nested numeric outputs are flattened.
Logs retain hashes, fids, safe tool names, flag codes and job ids, never texts/arguments/tokens; startup purges entries older than 30 days. Rate limits are per process, using request.client; configure trusted proxy headers in uvicorn.
Checks remove unknown bracket citations and unverified long quote marks, and flag extra report numbers; semantic truth and value neutrality still rely on instructions and visitor judgment. Test: `python -m pytest -q -p no:cacheprovider tests/keeper`.
