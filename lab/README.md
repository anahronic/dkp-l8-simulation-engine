# Dikenocracy Protocol Lab

A laboratory of the provisions of the Dikenocracy protocols: a registry of every
provision with an exact quote, modules that check computable provisions on declared
cases, and a web page that runs the same code in the browser.

The lab wraps the verified PREVENTION bench (`simulation/`, v2.1.1) without changing
it: the bench's code, configs and results are byte-for-byte those of tag `v2.1.1`.

## What a result means

| Property | Question | Where it is shown |
|---|---|---|
| Compliance | Are the checked provisions met in this experiment? | `PASS` / `FAIL` / `UNKNOWN` / `NOT_APPLICABLE` per provision |
| Model validity | Which data and assumptions link the model to a real system? | declared hypotheses of the module; `causal_note` |
| Readiness for use | Formal admission (calibration, independent review)? | never granted: `operational_use: false` |

`UNKNOWN` and provisions not covered by an experiment never count as `PASS`.
`NOT_APPLICABLE` always carries a reason. No summary says "the protocol passed"
unless every provision of the document was applicable and passed.

## Parts

| Path | Content |
|---|---|
| `lab/corpus/world-aad3e86/` | byte copies of the 39 Markdown documents of anahronic/World at `aad3e86`, pinned in `CORPUS.json` |
| `lab/registry/protocol_catalog.json` | generated catalog: kinds, layers, sections, references, unresolved dependencies |
| `lab/registry/requirements/*.json` | one file per document: provisions with verbatim quote, section, kind, inputs, criterion, numeric source, dependencies, coverage |
| `lab/core/` | input schema, check statuses, run identity, reports, replay packages |
| `lab/modules/` | installed modules: `prevention`, `time`, `work_cycle`, `failure_chain` |
| `lab/api.py` | functions used by the browser worker and by a server |
| `lab/tools/` | catalog builder, registry checker, coverage sync, Codex drafting prompt, web bundle |

## Commands

```
python -m lab catalog                          # coverage of every document
python -m lab modules
python -m lab example work_cycle --out wc.zip  # run module examples as variants
python -m lab run request.json --out pkg.zip
python -m lab replay pkg.zip                   # recompute; compare input_id and result_id
python -m lab.tools.check_registry             # verbatim quotes, sections, ids, coverage rules
python -m lab.tools.sync_coverage --check      # registry coverage = module declarations
python -m lab.tools.build_catalog              # verify the corpus pin, rebuild the catalog
```

## Registry

Provisions were drafted by an OpenAI Codex agent from one document at a time
(`lab/tools/codex/requirements_prompt.md`, structured output) and are machine-checked:
every `quote` must occur verbatim in the pinned text, every `section` must be a heading
of the document, ids are unique.  Coverage is never typed by hand: modules declare what
they implement (`implements`), `sync_coverage` writes it into the registry, and a test
checks that every declared check is actually emitted when the module's examples run.
Drafted interpretations are proposals for review, not readings accepted by the author.

## Identity and replay

A result document has an `input_id` (lab and engine code digests, registry digest,
corpus commit, module version, resolved inputs) and a `result_id` (outputs, checks and
summaries).  A replay package (zip) holds the request, the result, reports in English
and Russian, provenance (machine, runtime, time — not part of any id) and SHA256SUMS.
The same request gives the same ids in CPython on Windows and Linux and in Pyodide
(CPython compiled to WebAssembly) in the browser.

## Browser runtime

`python -m lab.tools.build_web_bundle DIR` writes `lab-bundle.zip` and
`lab-bundle.json`.  The web page (repository anahronic/Dikenocracy,
`website/projects/protocol-lab/`) loads Pyodide from jsDelivr, verifies the bundle
digest and runs `lab.api` in a Web Worker.  Inputs stay in the browser.

## Gaps

See [MODEL_GAPS.md](MODEL_GAPS.md).
