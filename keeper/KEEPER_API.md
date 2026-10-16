# Keeper API v1 (contract between the widget and the gateway)

The Keeper ("Хранитель знаний") answers questions about Dikenocracy from a pinned source corpus and prepares lab runs.
It is a reference assistant of a research alpha: it does not set norms, resolve value conflicts or turn a prompt into a
rule (AI-SUBJECT §§1–2, 5–8).  Numbers, statuses and ids of a calculation come only from the lab engine.

Public base: `/api/keeper/v1` (gateway process).  The lab itself: `/api/lab/v1` (`lab_server/API.md`); the widget
calls the lab directly for jobs, so the job token stays with the visitor.

## Common

- JSON bodies, UTF-8, at most 16 KiB.  Errors: `{"error": {"code", "message"}}` with codes `bad_json` 400,
  `too_large` 413, `invalid_input` 422, `rate_limited` 429, `busy` 503 (+ `Retry-After`), `model_unavailable` 503,
  `timeout` 504.
- `lang`: a site language code (`en`, `ru`, `he`, `ar`, `de`, `es`, `fr`, `it`, `pt`, `zh`, ...); answers are written in
  that language when the model can; sources stay in their canonical language.
- Every answer carries `provenance`: `{request_id, model, model_digest, instructions_version, corpus_version,
  retrieved: [fid...], tool_calls: [{name, ok}]}`.  This is the service provenance of the AI answer, separate from
  the identity of any lab result.

## POST /ask

Request:

```json
{"question": "Можно ли сократить восстановление в кризис?", "lang": "ru",
 "page": {"url": "https://dikenocracy.com/pages/protocols/dkp-5-work-cycle-001.html", "doc_id": "DKP-5-WORK-CYCLE-001"},
 "selection": "optional text the visitor explicitly selected and chose to send (at most 2000 chars)",
 "stream": false}
```

`page` and `selection` are the only page context; the widget never sends form contents, messages, keys or hidden data.
`question` 1..1000 chars.

Response (`stream: false`):

```json
{"state": "answer",
 "answer": "text with citations like [WORK-CYCLE §7]",
 "citations": [{"cite": "WORK-CYCLE §7", "fid": "DKP-5-WORK-CYCLE-001#§7", "url": "https://...#7-recovery-invariant-hard-constraint",
                "heading": "7. Recovery Invariant (Hard Constraint)", "source_type": "protocol", "status": "normative",
                "revision": {"world_commit": "aad3e86..."}}],
 "flags": [{"code": "unverified_quote", "detail": "..."}],
 "proposal": null,
 "provenance": {"request_id": "...", "model": "qwen3.5:2b", "model_digest": "sha256:...", "instructions_version": "v1-<sha8>",
                "corpus_version": "ba5f6f3f243a", "retrieved": ["..."], "tool_calls": []}}
```

`state`:

| state | meaning |
|---|---|
| `answer` | an explanation grounded in the listed citations |
| `no_sources` | the pinned corpus has nothing on the question (not the same as an UNKNOWN lab result, nor a failure) |
| `needs_parameters` | a calculation is possible but parameters are missing; `missing: [...]` lists them |
| `proposal` | a lab run is prepared: `proposal` holds the request for confirmation (below) |
| `refused` | outside the Keeper's role (e.g. asked to decide a value conflict or set a norm): the answer lists the options and who decides |

Flags (deterministic post-checks of the model output): `unknown_citation` (removed), `unverified_quote` (quotation
marks removed, shown as paraphrase), `number_not_in_result` (explain only), `tool_rejected` (the model asked for a tool or
arguments outside the contract), `truncated`.

With `"stream": true` the response is `text/event-stream`: `event: status` (`{"state": "retrieving"|"generating"|"checking"}`),
`event: delta` (`{"text": "..."}`; raw model text, may still be corrected), `event: final` (the full JSON above; the
widget replaces the streamed text with `final.answer`).  Closing the connection cancels the generation.

### Proposal (state `proposal`)

```json
{"module": "work_cycle", "scenario": "S-LAB-08",
 "request": {"schema": "dkp-lab-input/1", "module": "work_cycle", "variants": [{"name": "visitor", "input": {...}}]},
 "fields": [{"key": "workers", "value": 12, "origin": "user", "label": "...", "type": "int", "min": 1, "max": 200},
            {"key": "shift_hours", "value": 8, "origin": "default", "label": "..."},
            {"key": "crisis_window", "value": null, "origin": "hypothesis", "label": "...", "note": "..."}],
 "validation": {"ok": true, "problems": []},
 "note": "Research run of the lab (alpha). Not a calibrated model; not for real enforcement."}
```

`origin` is `user` (taken from the question), `default` (module default) or `hypothesis` (a modelling assumption the
visitor may change).  The widget shows the fields editable, then — only after the visitor confirms — posts
`request` (with edits) to `POST /api/lab/v1/jobs`, follows `GET /api/lab/v1/jobs/{id}`, and shows the result card built
from the lab report itself (not from the model text).

## POST /explain

```json
{"job_id": "...", "token": "...", "lang": "ru"}
```

The gateway reads the completed report from the lab with the visitor's token, builds a deterministic summary (statuses,
key outputs, failed and UNKNOWN checks with their requirement ids) and asks the model to explain it with citations of the
provisions involved.  Any number in the explanation that is not in the summary is flagged `number_not_in_result`; the
widget shows the lab card as the authority.  Response: as `/ask` with `state: "answer"` and `result_id` echoed.

## GET /health

`{"ok": bool, "model": {"name", "digest", "loaded": bool}, "corpus_version", "instructions_version", "busy": int,
"queue_limit": int}` — no server parameters beyond these.

## Limits (defaults, configurable)

One generation at a time (`MAX_CONCURRENT=1`), at most 8 waiting (`MAX_WAITING`), then `busy`; per-IP 6 asks/minute;
generation at most 700 tokens and 150 s; retrieval passes at most 5 fragments (about 1500 characters each) to the model.

## Retention

The gateway keeps a private JSONL log of provenance per request (request id, time, hashes of question and answer,
retrieved fids, tool calls, flags, job ids) for 30 days.  Question texts are not logged.  Nothing is published.
