# Changelog

## 2.0.0 — 2026-10-05

Rework after the audit exchange of 2026-10-04/05 (Claude check of v1, GPT reply 6,
Claude answer 6). Item codes refer to that exchange. v1 remains at tag `v1.0-a9d3cdf`.
Results of v1 and v2 are not comparable: the world model and several rules changed.

### Technical defects fixed (no change of protocol meaning)

- **Budget spent before eligibility (N1).** v1 deducted a subject's share before
  checking TA, the window, SE, Sₖ and Tₖ, so an ineligible first responder could take
  the whole event. Eligibility is now decided first; only eligible subjects share Aₖ.
- **Subject ids merged across zones (N4).** `actor-<profile>-<n>` restarted in every
  zone, so recurrence counters and subject totals of different people merged. Ids
  are now `<zone>/<profile>`.
- **`oracles.bias_range` ignored (N6).** Bias is now applied. Unknown config keys are
  rejected, so a declared-but-unused setting can no longer pass silently.
- **CBF estimator (L4, N7).** v1 mixed (n−2)/(n−1) with /n and depended on input order.
  Now Welford count/mean/M2 with `std_population` and `std_sample` named apart,
  fed with *observed* TA intensity (v1 used the generator's truth). Still audit-only.
- **Hidden defaults (L1, F-11).** All significant keys are required (schema v2);
  the v1 fallback W = 1.0 for a channel without weight is gone. The second source of
  truth (`calibration.py` presets) is removed; the presets survive as comparison
  overlays in `configs/comparison/example.yaml`.
- **Rounding.** Records keep full binary64 precision; v1 rounded to 6 digits, which
  turned decayed rewards into unexplained exact zeros.
- **Windows console.** The CLI no longer fails at the end of a run on a cp1252 console.
- **Cross-platform bits.** `math.log`/`math.cos` (C library) gave last-bit differences
  between Windows and Linux in v2's first runs; Box–Muller now uses
  `core/detmath.py`, decay powers use integer squaring.

### Model changes (declared as hypotheses, not as readings of the protocol)

- **Time contract (L5, N2).** Clock in seconds, ticks partition the civil day,
  DTI-Day per record; Δt_int is in seconds and actually binds (v1 drew the SE time
  inside the window, so the window never mattered). Event, measurement and arrival
  times are distinct; per-class TTL (ORACLE §9).
- **Truth isolation (N3).** The adapter receives observations only. v1 passed the
  generator's linkage flag, the actor's own share and an SE computed from the true
  suppression.
- **SE is measured** by the oracles after the interventions; interventions act jointly
  on the true intensity; one Sₖ per event.
- **Attribution (L6, §12).** Default `ambiguity_zero`: claims summing above 1 are
  attribution ambiguity → SPD = 0 → `NO_ATTRIBUTION`. `proportional` and `list_order`
  (v1 behaviour) are comparison hypotheses only.
- **Risk farming is modelled.** Adversarial subjects create threats; detection is an
  observation model.
- **Recurrence (A3).** Key, threshold, decay and window are configurable; the v1 rule
  stays the default and is reported as decaying honest work.
- **Cₖ** from class coverage by default (v1 mean self-reported confidence available).

### Added

- Machine statuses and reasons on every record; EPISTEMIC-BOUNDARIES §5 metadata.
- Run manifest: `input_id` (config digest, seed, engine code digest, spec digests),
  `result_id` (result core), provenance, hypotheses, unverified items; diagnostics in
  `run_log.json` (L3).
- Candidate comparison bench `compare_candidates.py` (B1–B4): baseline, candidates,
  pairwise and joint activation, interactions, invariants, declared metric
  directions; no selection.
- Phase 3 adversarial scenarios S1–S10 (`phase3_report.py`), replacing Phase 2.
- Spec snapshots replaced by byte copies of the canonical 2026-10-04 texts
  (PREVENTION, ORACLE, TIME, IDENTITY, IMPACT, EPISTEMIC-BOUNDARIES, SIMULATION),
  pinned in `MANIFEST.json` and re-verified on every run.
- CI on Linux, Windows and macOS; pinned smoke `result_id`.

### Removed

- v1 configs, Phase 2 scenario configs and tests built on the v1 API; `scenarios.py`
  (unused) and `calibration.py` (second source of truth).
