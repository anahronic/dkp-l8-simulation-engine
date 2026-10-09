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
| `lab/modules/` | installed modules (32): `prevention`, `time`, `work_cycle`, `failure_chain`, `dispute_correction`, `contribution`, `sensor_loss`, `crisis_recovery`, `exit_integration`, `interop_failure`, `calibration_expiry`, `transport_capacity`, `economic_access`, `upgrade_lifecycle`, `internal_security`, `police_antiterror`, `axiom_constraints`, `info_truth`, `privacy_transparency`, `edu_culture`, `ai_subject`, `code_synergy`, `code_economy`, `scope_gate`, `oracle_ingestion`, `impact_attribution`, `epistemic_gate`, `audit_trace`, `simulation_gate`, `defense_envelope`, `habitat_dignity`, `resilience_structure` |
| `lab/api.py` | functions used by the browser worker and by a server |
| `lab/registry/open_questions.json` | questions that need an author decision (UNRESOLVED: normative ambiguity or architecture definition, verified against the text) and questions withdrawn after verification, linked to provisions, hypotheses and findings |
| `lab/registry/verifications.json` | semantic verification gate: findings, reference FAILs, noncompliant cases and questions read against the literal text, with verbatim quotes |
| `lab/registry/unresolved_classification.json` | Codex draft of the origin of every open point (not normative, never an author question by itself) |
| `lab/registry/calibration_map.json`, `lab/CALIBRATION_MAP.md` | decomposition of F-014: what needs a bundle, constants in the texts, parameters assigned to L8, missing values, status of each document |
| `lab/registry/traceability.json`, `lab/TRACEABILITY.md` | generated map requirement → implementation → test → gap → open question; execution matrix of the specification (stages A–G, S-LAB scenarios) |
| `lab/findings/` | findings with minimal reproductions, classified CONFIRMED_FINDING / INTERPRETATION_GAP / IMPLEMENTATION_BUG (UNVERIFIED_FINDING until verified) |
| `lab/ARCHITECTURE_DEVIATION.md` | open deviation: browser-only execution instead of the specified server API |
| `lab/tools/` | catalog builder, registry checker, coverage sync, traceability, Codex drafting prompt, web bundle |

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
python -m lab.tools.trace                      # traceability map, execution matrix, semantic gate
python -m lab.tools.calibration_map            # calibration map (F-014 decomposition)
python -m lab.tools.codex.import_classification OUT_DIR   # import a Codex draft of open-point origins
```

## Registry

Provisions were drafted by an OpenAI Codex agent from one document at a time
(`lab/tools/codex/requirements_prompt.md`, structured output) and are machine-checked:
every `quote` must occur verbatim in the pinned text, every `section` must be a heading
of the document, ids are unique.  Coverage is never typed by hand: modules declare what
they implement (`implements`), `sync_coverage` writes it into the registry, and a test
checks that every declared check is actually emitted when the module's examples run.
Every provision carries `interpretation_status` (`DRAFT_UNREVIEWED`, or `TEXT_VERIFIED` when the
semantic verification gate read its wording against the literal text — derived from
`lab/registry/verifications.json`, not a human review; no tool sets `REVIEWED` or
`CONFIRMED_BY_AUTHOR`) and `decision_status` (`UNRESOLVED` when the draft names missing
definitions or an author question links it), with `open_point.origin` saying what would close
it.  Drafted interpretations are proposals for review, not readings accepted by the author.

**Semantic verification gate.**  Before a provision leads to a FAIL in a reference example, a
normative conflict, a systemic blocker or an author question, it is read against the literal
pinned text and recorded with verbatim quotes in `lab/registry/verifications.json`;
`tests/lab/test_semantic_gate.py` refuses an unverified reference FAIL, a finding without a class,
and an author question whose origin is calibration, data, an external document or lab work.  Three
things are kept apart: the lab agent's reading, the automatic verbatim check of its quotes, and human
acceptance (none so far).  A quote shows that the words exist, not that the conclusion follows: every
finding has a kind, contradictions carry a structured analysis (subject, object, scope, conditions,
modality, priority, joint compliance) and missing definitions list the documents, terms and reference
chain searched.

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
This replaces the server API of the specification only provisionally: see
[ARCHITECTURE_DEVIATION.md](ARCHITECTURE_DEVIATION.md).

## Gaps

See [MODEL_GAPS.md](MODEL_GAPS.md).
