# DKP-8-SIMULATION-001 — validation report (2026-11-17)

What was verified, how, and what that does **not** show. All evidence is reproducible from the engine repository.

## 1. Verified (software)

| Claim | Evidence | Result |
|---|---|---|
| Ed25519 is RFC 8032-conformant | RFC 8032 §7.1 vectors 1–3 (public key, signature, verification); signature byte-equal to OpenSSL 3.5.5 `pkeyutl -rawin`; tampered message, flipped bit, S+L and short key rejected | pass (`test_crypto_and_canonical.py`) |
| Canonical JSON is deterministic and unambiguous | UTF-16 key order (U+1F600 before U+FF5E), floats/NaN/large ints/non-string keys refused | pass |
| Bundle structure follows §9 | each §9 section required; value without provenance refused; synthetic values force SYNTHETIC; composite index needs formula, declared PTL inputs, weights for exactly those inputs, uncertainty method, defined only in L8 | pass (`test_bundle.py`) |
| Trust levels cannot be confused | dev key → VALID_DEVELOPMENT_ONLY, unknown key, tampered body → INVALID_SIGNATURE, unsigned, revoked key/bundle; dev/test signatures never enforceable | pass |
| §10 expiry handling | at `not_after`: `validity_state INVALID`, `reason "Calibration expired"`, `remediation "Awaiting recalibration"`; calibrated values removed from outputs; recalibration (`supersedes`) restores VALID; trigger → INDETERMINATE, not enforceable | pass |
| Gate classifies every rule path | 17 synthetic dossiers give the expected decision (BLOCKED ×8, REDESIGN_REQUIRED ×1, NOT_ESTABLISHED ×6, REFUSED ×2); decisions deterministic and hash-bound; BLOCKED dominates F4 | pass (`test_gate.py`, `python -m dkp8 catalog`) |
| Fail-closed | no canonical case reaches ELIGIBLE; ELIGIBLE only with test identities + test author-decision fixtures; unsigned R3 claims rejected; reproduction mismatch blocks | pass |
| Deterministic bench reproduces | smoke scenario packed and re-run: `input_id c13d5f58…`, `result_id 77d06a9bcae39161…` (same as the pinned CI value); package byte-stable (SHA-256 `9c8aaf2f…`); tampered package refused by SHA256SUMS | pass (`test_reproduction.py`) |
| §4/§13/§14 cross-protocol rules | enforceability changes only for the covered target; divergence → ROLLBACK/HALT, missing tolerance → NOT_ESTABLISHED; dependents of SIMULATION include HABITAT etc. | pass (`test_enforcement.py`) |
| Traceability is complete | 48/48 provisions mapped, every code reference resolves, every test file exists | pass (`test_traceability.py`) |
| Review workbook filters | Chrome (1280 px and 390 px): protocol filter DKP-8 → 57 items, "depends on" DKP-8 → 1494, criticality ordering monotonic, no horizontal overflow | pass (local browser run) |

Full engine suite: 1767 passed (Windows, Python 3.12, local, 2026-11-17).

## 2. Not validated — and why

| Item | Status | Reason |
|---|---|---|
| Calibration (CALIBRATION_VALIDATED) | **NO** | no calibration value with provenance exists; no signing authority |
| Independent reproduction (INDEPENDENT_REPRODUCTION_VALIDATED) | **NO** | only R1 (same host, fresh process) and the CI matrix (R2-equivalent: different OS, same operator); no registered node (R3) |
| Real data (REAL_DATA_VALIDATED) | **NO** | no PTL dataset; every scenario is synthetic and labelled |
| Operational DKP-8 compliance | **NO** | requires the three above plus author decisions (Q-001, Q-017, Q-034, Q-035, DKP8-Q-01…03) |
| F2/F4 operational definitions | unverified | engineering definitions, not given by the corpus; author review needed |
| Physical plausibility of inputs (§5) | not computable in general | flags are declared; data-level detection needs per-quantity physical bounds |

## 3. How to re-run

```bash
python -m pytest -q tests/dkp8 tests/lab/test_review_tools.py
python -m dkp8 catalog
python -m dkp8 repro pack /tmp/smoke.zip && python -m dkp8 repro verify /tmp/smoke.zip --operator <name>
python -m dkp8 trace --md SIMULATION_REQUIREMENTS_TRACEABILITY.md
```
