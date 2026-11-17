# DKP-8-SIMULATION-001 — calibration gaps (2026-11-17)

What an operational L8 needs and does not have. Nothing below is filled in by software; each line names who must
supply it. Generated lists: `python -m dkp8 workbench --out <dir>` (every value by protocol, with bundle templates)
and `python -m dkp8 enforceability`.

## 1. Missing governance decisions (exact questions)

| Id | Question | Blocks |
|---|---|---|
| **DKP8-Q-01** | Who is the L8 signing authority for Calibration Bundles (§3, §9 say "signed" but not by whom)? How are its keys created, held, rotated and revoked, and who may revoke a bundle? | SIMULATION-3-06, 9-01; every enforcement (§4) |
| **DKP8-Q-02** | What is an "independent node" (§8): separate operator, organisation, implementation? How many must reproduce a result, and how are nodes registered? | SIMULATION-8-01 |
| **DKP8-Q-03** | What tolerance per metric separates acceptable from divergent deployed behaviour (§13), and how is it calibrated? | SIMULATION-13-02 |
| Q-001 | S1: who accepts a norm after a successful check (registry) | activation after ELIGIBLE |
| Q-017 | Composite indices without formulas: B(t), SPDI, PPDI/RED, credit risk, fatigue | CompositeIndices-01, HABITAT, ORACLE §12 |
| Q-034 | Does a recalibration trigger suspend a bundle before its window ends? | 10-01 (software reports INDETERMINATE) |
| Q-035 | Which protocols bind now, and do constants written in the texts need a bundle? | 4-02 |
| (new) | Life-preservation constraint (§6): which metric and tolerance is evaluated in simulation? | INV-LIFE, 6-01 |
| (new) | Machine form of the DKP-7-SCOPE conflict rules for change dossiers (which layers/domains a change may touch) | INV-SCOPE, F1 |
| (new) | F2 operational definitions (runaway, cascade, deadlock, collapse thresholds) — confirm or replace those in `dkp8.gate.OPERATIONAL` | 7-02 |

## 2. Missing values (from `lab/registry/calibration_map.json`)

- **Deferred to L8 (13):** IDENTITY minimum attribution confidence; B(t) model/aggregation/weights/calibration;
  every composite index; CRISIS durations, decay, revalidation cadence, exit sensitivity and trigger thresholds; EXIT
  cooling period and phased disengagement; SPDI model, SPDI_min, component thresholds; INFO T₁/T₂ and propagation
  thresholds; EDU competence restrictions; PREVENTION ε_consistency, Δt_int, θ thresholds, Wₖ weights; INTEGRATION
  stress-test clearance.
- **Bundle required (10 scopes):** every protocol (§4), HABITAT, INFO, EDU, CULTURE, B(t) — all NON-ENFORCEABLE or
  informational today.
- **Missing values (38)** and **external documents (2: DKP-2-ECONOMIC-001, DKP-PTL-REG-DATA-001)**: see the workbench
  output, one table per protocol.

## 3. Missing empirical inputs

- PTL datasets for historical scenarios (§5) and for every composite index input (CompositeIndices-03).
- Deployed-system behaviour for §13 audit comparison.
- Confidence bounds require measured data; none can be derived from synthetic fixtures.

## 4. Path to a first real bundle (what would have to happen, in order)

1. Answer DKP8-Q-01 and Q-001 (authority, acceptance of a norm); register the authority key in `dkp8/trust-store.json`
   by a reviewed commit.
2. Pick one target (e.g. a PREVENTION parameter, whose bench exists) and supply its values with provenance
   (`author_decision` or `ptl_dataset` with SHA-256).
3. Answer DKP8-Q-02; register nodes; collect signed R3 reproduction records of the same `result_id`.
4. Run the gate on an empirical dossier; only ELIGIBLE allows `bundle sign` by the authority.
5. Attach the bundle; `enforceability` then reports the target ENFORCEABLE until expiry or a trigger.
