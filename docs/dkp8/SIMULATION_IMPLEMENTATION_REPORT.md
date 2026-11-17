# DKP-8-SIMULATION-001 — implementation report (2026-11-17)

Engine repository `anahronic/dkp-l8-simulation-engine`, package `dkp8/` (commit `3424334`, plus the A6 review tooling in
`e021457`). This is the software side of DKP-8-SIMULATION-001 next to what already existed: the deterministic research
bench (`simulation/`, DKP-1-PREVENTION-001 on a synthetic childcare scenario) and the Protocol Lab modules
`simulation_gate`, `calibration_expiry`, `edition_finality`. Existing components were not rewritten.

**Software completion is not normative authorization or empirical validation.** No calibration value, signing
authority, independent node or PTL dataset exists; nothing here was invented to fill those gaps.

## 1. Components

| Module | DKP-8 § | What it implements |
|---|---|---|
| `dkp8.canonical` | §9, §11 | Canonical JSON = RFC 8785 subset (UTF-16 key order, no whitespace, integers ≤ 2^53−1, **no binary floats**: non-integer quantities are decimal strings). `digest()` = SHA-256 of the canonical bytes. |
| `dkp8.ed25519` | §3, §9 | Pure-Python Ed25519 (RFC 8032 §5.1); RFC 8032 test vectors 1–3 and byte equality with OpenSSL 3.5 in tests; rejects non-canonical S. |
| `dkp8.trust` + `trust-store.json` | §3, §8, §9 | Trust store `dkp-l8-trust/1`: **no authority, no node** (none is designated in the corpus); one public development key (seed derived from a published phrase → `VALID_DEVELOPMENT_ONLY`, never enforceable); revoked keys and bundles; test identities only through `with_test_identities` (flagged everywhere). |
| `dkp8.bundle` | §3-06, §4, §9, §10 | Calibration Bundle `dkp-l8-calibration-bundle/1`: target (kind, protocol, source SHA-256), issued_at, validity window, thresholds, models, aggregation (composite indices), confidence bounds, environmental assumptions, all five §10 triggers, simulation runs + gate decision hash, `supersedes`, `data_status`. Every value needs provenance (`ptl_dataset`, `author_decision`, `simulation_output`, `synthetic_fixture`); synthetic values force `SYNTHETIC` (never enforceable). `status()` → VALID / INVALID (`Calibration expired` / `Awaiting recalibration`, revoked, unsigned, superseded, not yet valid) / INDETERMINATE (trigger recorded; Q-034 not decided). `apply_to_output()` strips calibrated values unless VALID (no legacy values). `template()` for the workbench. |
| `dkp8.invariants` | §3-03, §6 | Registry of the six invariant groups with computability; checks over a declared trace: authority non-expansion and reversibility (computable), scope (partial), life (violation on increase; otherwise not a pass until the metric is defined), biosphere (needs empirical B(t) + minimum), axioms A1–A7 (declared evaluations only). |
| `dkp8.gate` | §5, §6, §7, §8, §12 | Fail-closed acceptance gate over a change dossier `dkp-l8-change-dossier/1`: §5 admissibility, invariants, F1–F4 (F2 detectors: runaway, cascade, deadlock, collapse — operational definitions listed for author review), risk envelopes, adversarial stability, empirical evidence, independent nodes, composite-index specification. Decisions BLOCKED > REDESIGN_REQUIRED > NOT_ESTABLISHED > ELIGIBLE; `deployment_mandated: false`, `override_possible: false`; override/appeal/waiver fields refuse the dossier. Decision SHA-256 for the bundle. |
| `dkp8.reproduction` | §8, §11 | Byte-stable reproduction packages of the bench (inputs, expected ids, engine identity, instructions, SHA256SUMS); verification re-runs and writes `dkp-l8-reproduction/1` records; independence levels R0–R4 (only signed R3/R4 from registered nodes count). |
| `dkp8.enforcement` | §4, §13, §14 | Enforceability map from `calibration_map.json` (7 NON-ENFORCEABLE scopes, 13 UNCALIBRATED parameters today); §13 audit divergence (tolerances with provenance or NOT_ESTABLISHED; ROLLBACK if a tested rollback exists, otherwise HALT); §14 transitive dependents to re-simulate (from the registry's normative dependencies). |
| `dkp8.composite` | §9 composite indices | Inventory of B(t), SPDI, PPDI/RED, credit risk, fatigue: what the corpus says (with sources) and the exact questions a bundle needs. No formula, weight or bound is supplied. |
| `dkp8.scenarios` | §5, §7, §12 | 17 labelled SYNTHETIC dossiers, one per rule/path (clean, authority, axiom F1, scope F1, cascade/runaway/deadlock F2, irreversible F3, externality F4, life, smoothed input, no adversarial, rollback untested, composite unspecified, override and appeal refused, historical without PTL). |
| `dkp8.traceability` | all | The 48 registry provisions → status, software completeness, code, tests, remaining work; markdown generator. |
| `python -m dkp8` | — | `status`, `trace`, `catalog`, `gate`, `bundle template/validate/sign/status`, `repro pack/verify`, `enforceability`, `dependents`, `invariants`, `composite`, `workbench` (calibration workbench: every missing L8 value by protocol + bundle templates). |
| `lab/tools/review_queue.py` | A6 | Author review workbook: filters by protocol and by dependency, ordering by an explained criticality score, phone layout. |

## 2. Status of the 48 provisions

From `SIMULATION_REQUIREMENTS_TRACEABILITY.md`: IMPLEMENTED_AND_TESTED 30 · IMPLEMENTED_UNVERIFIED 2 (F2 detectors,
F4 detection) · PARTIAL 9 · MISSING 0 · BLOCKED_BY_NORMATIVE_DECISION 5 (bundle authority, independent nodes,
composite-index models, audit tolerances) · BLOCKED_BY_EMPIRICAL_DATA 2 (PTL raw outputs, deployed behaviour) ·
NOT_COMPUTABLE 0 (axioms are tracked under 6-01 as not computable invariants).

## 3. Tests

`tests/dkp8/` 64 tests + 1 review-workbook test; full engine suite **1767 passed** (Keeper tests removed with the
Keeper: 1917 − 215 + 65). CI (`.github/workflows/tests.yml`, Linux/Windows/macOS × Python 3.10/3.12/3.13) now also runs
the synthetic catalogue and packs/re-runs a reproduction package on every OS.

## 4. Deliberate limits

- The gate checks declared traces; it does not simulate protocols beyond the existing bench and lab modules.
- Operational definitions (F2 detectors, criticality ordering) are engineering choices, listed in every decision.
- ELIGIBLE is reachable only in tests with test identities; with the canonical trust store every change is at best
  NOT_ESTABLISHED.
