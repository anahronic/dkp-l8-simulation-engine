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
| `answer` | an AI explanation labelled unverified, or a deterministic report summary (`answer_kind`) |
| `no_sources` | the pinned corpus has nothing on the question (not the same as an UNKNOWN lab result, nor a failure) |
| `needs_parameters` | a calculation is possible but parameters are missing; `missing: [...]` lists them |
| `proposal` | a lab run is prepared: `proposal` holds the request for confirmation (below) |
| `refused` | outside the Keeper's role (e.g. asked to decide a value conflict or set a norm): the answer lists the options and who decides |

`citations` lists only the trusted fragments the answer actually cites, in order of first use; every retrieved fragment
is listed in `provenance.retrieved`.

When the final answer is flagged `uncited_answer` and fragments were retrieved, the optional
`found_sources` array contains at most three trusted fragment records with the same fields as
`citations`: `cite`, `fid`, `url`, `heading`, `source_type`, `status`, `revision`. Retrieval order
is preserved except that fragments explicitly named in the question (e.g. `F-001`, `Q-065`,
`WORK-CYCLE §7`) come first. The field is absent for cited answers or when no fragments were retrieved.
The panel should show these links as **found sections** chips, separate from citations. They
are a hand-off for checking the sources, not evidence for the model's statements: `citations`
is unchanged and `uncited_answer` remains. The gateway appends one deterministic line:

- Russian (`ru`, including regional variants): `Ответ не привязан к источникам. Найденные разделы для проверки: [F-001]; [...]`
- English (also the fallback for other languages): `The answer is not tied to sources. Found sections to check: [F-001]; [...]`

The same field and line appear in the SSE `final` response. `keeper.eval_answers.check()` accepts
an expected cite in either array and records `cite_via: "citation"` or `"found_source"`, preferring
a citation if both match (`null` when neither matches or no citation is required). This source
availability check does not verify the model's claims.

Flags (deterministic post-checks of the model output): `unknown_citation` (removed), `unverified_quote` (quotation
marks removed; this does not verify the resulting paraphrase), `number_not_in_result` (diagnostic helper only; `/explain` now uses a trusted template), `tool_rejected` (the model asked for a tool or
arguments outside the contract), `truncated`, `uncited_answer` (no statement is tied to a source),
`empty_model_answer` (the model gave nothing; a fixed message is shown), `open_author_question` (an UNRESOLVED
author question is among the sources: the server appends that neither the lab nor the Keeper chooses a reading and
the author decides, with its citation).

### Published intake rule for S-LAB-08

A question with a calculation verb (посчитай, рассчитай, calculate, compute, simulate ...) and a roster term (смены,
круглосуточно, 24/7, график, покрытие, shift, roster, coverage, staff ...) is handled without the model: the number of
workers ("12 работников", "20 workers"), the staff needed every hour ("3 человека на смене каждый час", "4 people on duty
every hour") and the horizon ("14 дней", "7 days") are read literally from the question (`keeper/guardrails.py`,
`INTAKE`).  All three found: state `proposal` (origin `user` for them); otherwise `needs_parameters` with `missing`.
The model may still call `propose_run` for other phrasings, but **the same field parser** must
bind each proposed value to its role. Workers, days and constant hourly demand use `INTAKE`;
a number elsewhere (including a protocol id) is not evidence. Repeated equal values for one
role are allowed; distinct competing values require clarification. Negative/decimal/id tails
are not parsed as positive integers. Known fields outside this grammar or mismatched values
return `missing` and no executable proposal; unknown schema keys are rejected. No unparsed model suggestion is labelled `user`. Defaults and
modelling hypotheses remain separate. The visitor may explicitly edit fields before submission.

With `"stream": true` the response is `text/event-stream`: `event: status` (`{"state": "retrieving"|"generating"|"checking"}`),
`event: final` (the full JSON above). Only statuses are sent before the post-checked final answer; raw model
text is never emitted as a delta.  Closing the connection cancels the generation.

### Proposal (state `proposal`)

```json
{"module": "work_cycle", "scenario": "S-LAB-08",
 "request": {"schema": "dkp-lab-input/1", "module": "work_cycle", "variants": [{"name": "visitor", "input": {...}}]},
 "fields": [{"key": "workers", "value": 12, "origin": "user", "label": "...", "type": "int", "min": 1, "max": 1000},
            {"key": "work_hours", "value": 8, "origin": "default", "label": "..."},
            {"key": "phase_offsets", "value": "staggered", "origin": "hypothesis", "label": "...", "note": "..."}],
 "validation": {"ok": true, "problems": []},
 "note": "Research run of the lab (alpha). Not a calibrated model; not for real enforcement."}
```

`origin` is `user` (value bound to its field by the published parser), `default` (module default) or `hypothesis` (a modelling assumption the
visitor may change).  The widget shows the fields editable, then — only after the visitor confirms — posts
`request` (with edits) to `POST /api/lab/v1/jobs`, follows `GET /api/lab/v1/jobs/{id}`, and shows the result card built
from the lab report itself (not from the model text). Keyed submissions require a private
`X-Idempotency-Token` generated and retained before the first POST; see `lab_server/API.md`.

## POST /explain

```json
{"job_id": "...", "token": "...", "lang": "ru"}
```

The gateway reads the completed report with the visitor's token and returns a deterministic
summary: labelled output paths, status counts, FAIL/UNKNOWN checks with requirement ids,
check names, explanations and available provision citations. It does not call the model;
added numbers, swapped values, refusal and model outages cannot alter this answer.
`coverage.covered_percent` is computed with Decimal from `coverage.covered_fraction × 100`
and labelled with that origin. No other derived model quantities are accepted.

Response: as `/ask`, with `state: "answer"`, `answer_kind: "deterministic_summary"`,
`result_id`, and structured `summary: {module, result_id, variants: {name: {outputs, counts, issues}}}`.
`provenance.model` and `model_digest` are null. The report card and authorized report/export
routes remain available independently. The old numeric-overlap postcheck is only a diagnostic
helper, not permission to display generated numerical claims.

Ordinary `/ask` answers have `answer_kind: "unverified_explanation"` and a visible label.
Citations identify supplied fragments; even a real citation does not establish that a claim
is supported. Removing quotation marks is not verification of a paraphrase.

For S-LAB-08 proposals and work_cycle reports, Q-012 is bound to WORKCYCLE-3-02/8.1-01 and
Q-013 to WORKCYCLE-5.1-01/8.2-02. Their UNRESOLVED notices use pinned corpus fragments,
independently of retrieval rank (report binding considers all checks, including PASS).
WITHDRAWN questions are excluded. These bindings do not resolve the questions. Other open
question notices still depend on retrieval; this is not a guarantee of finding every relevant
question. A corpus missing the known question fragments cannot supply their citations.

## GET /health

`{"ok": bool, "model": {"name", "digest", "loaded": bool}, "corpus_version", "instructions_version", "busy": int,
"queue_limit": int}` — no server parameters beyond these.

## Limits (defaults, configurable)

One generation at a time (`MAX_CONCURRENT=1`), at most 8 waiting (`MAX_WAITING`), then `busy`; per-IP 6 asks/minute;
generation at most 700 tokens and 150 s; retrieval passes at most 5 fragments (about 1500 characters each) to the model.

## Retention

The gateway keeps a private JSONL log of provenance per request (request id, time, hashes of question and answer,
retrieved fids, tool calls, flags, job ids) for 30 days.  Question texts are not logged.  Nothing is published.
