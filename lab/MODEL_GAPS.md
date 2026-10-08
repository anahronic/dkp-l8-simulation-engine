# Model gaps and open questions

Each entry names the place in the corpus, the affected computations, the possible
readings and what would close the gap.  The lab does not choose a norm; where it must
compute, the choice is a declared hypothesis.  The registry (`lab/registry/requirements`)
lists every provision with its coverage and gap; this file collects the cross-cutting ones.

## 1. S1 — who accepts a norm after a successful check

- **Where:** DKP-4-UPGRADE-001, DKP-8-SIMULATION-001 §8.
- **Affects:** any automatic adoption of a compared variant.
- **State:** the comparison bench reports variants side by side and selects nothing.
- **Needs:** the author's decision on the S1 procedure.

## 2. TIME — the 2000-01-01 vector

- **Where:** DKP-0-TIME-001 §9 (table: DY6815-026) against §5 and the §10 reference code
  (DTI-Day 2451545 → DY6809-306).
- **Affects:** requirement TIME-9-04; any record dated through that vector.
- **State:** the lab computes by §5/§10 and reports TIME-9-04 as `FAIL` with the tag
  `corpus_inconsistency`; it does not present either value as agreed.
- **Needs:** the pending erratum (`audit rt/TIME_erratum_2000-01-01.md`).

## 3. Causality

- **Where:** PREVENTION §6 ("causal linkage traceable"), IDENTITY §4.1, JUSTICE.
- **Affects:** attribution in every module that rewards or assigns consequences.
- **State:** share claims and linkage detection are scenario inputs; results carry the
  note "causal linkage is given on input".  Checking a given causal chain and inferring a
  chain from measurements are different tasks; only the first is implemented.
- **Needs:** a causal-inference model with its own validation, or real data.

## 4. Calibration

- **Where:** DKP-8-SIMULATION-001 §9 (signed Calibration Bundle).
- **State:** no Calibration Bundle exists; manifests, digests and reports do not replace
  one.  An expired bundle invalidates dependent results; it does not by itself mean a
  global NO_ENFORCEMENT (CRISIS PATCH conditions are separate).

## 5. Scope of a failure

- **Where:** DKP-4-CRISIS-001-PATCH.
- **State:** the global effect is the text in force; a regional variant may be studied
  only as a separately named hypothesis.

## 6. PREVENTION

- **Where:** §6 (shares), §9.3 (recurrence), §3.5/§3.6 (meaning of SE; time basis), ORACLE §9 vs §3.6 (TTL).
- **State:** the bench's hypotheses H-* (simulation/modules/prevention/hypotheses.py) stay
  unchanged; computing with them does not resolve the questions in
  AUDIT_REPORT_PREVENTION_L8_PHASE_3.md §5.

## 7. Composite indices

- **Where:** B(t) (ORACLE, SIMULATION), SPDI (HABITAT), PPDI/RED (TRANSPORT), credit risk
  (FINANCE), fatigue (WORK-CYCLE §9).
- **State:** no formulas, weights or confidence bounds are given; the lab does not
  substitute averages.  The corresponding provisions are `NOT_IMPLEMENTED` with this gap.

## 8. Missing referenced documents

- `DKP-2-ECONOMIC-001` — referenced by DKP-5-TRANSPORT-001 (system position); not in
  World `aad3e86`.  Not replaced by FINANCE.
- `DKP-PTL-REG-DATA-001` — referenced by DKP-6-RESILIENCE-001 §5.7; not in the corpus.
- `DKP-7` — "DKP-7 scope boundaries" in DKP-7-AI-SUBJECT-001: layer L7 or
  DKP-7-SCOPE-001; ambiguous, not resolved.
- **Needs:** the actual documents, or an explicit statement that they do not exist.

## 9. Interaction of rules

- **Where:** CRISIS PATCH §5.2 (automatic restoration), EPISTEMIC-TRANSITIONS (new
  admissible result required to return), sector access rules.
- **State:** restoring an enforcement mode does not make earlier decisions valid again.
  The failure-chain module (§11) models one chain — ORACLE → EPISTEMIC-BOUNDARIES →
  EPISTEMIC-TRANSITIONS → ASSETS/FINANCE; CRISIS PATCH restoration is not yet modelled.

## 10. WORK-CYCLE

- **§4.1 vs §7:** the default cycle is named, but whether other cycles are allowed is not
  stated; non-default cycles give `UNKNOWN` for §4.1, the hard limit is §7.
- **§5.1 vs §8.2:** presence 10 h and work 8 h leave exactly 2 h; the recommended 3–4 h
  recovery for high-intensity shifts cannot be added without changing presence or work.
- **Phases:** the text does not say whether workers may run Cycle6 with different
  offsets (hypothesis H-WC-1); with aligned phases continuous service is impossible.
- **§9 KPIs, §10 exceptions:** need real data and crisis scopes; not computable here.

## 11. Failure chain (S-LAB-02): stale and contradictory data

Module `failure_chain`; hypotheses H-FC-1..6 are declared in the module and shown in the UI.
Findings with minimal reproductions: [findings/](findings/README.md) (F-001 … F-004, F-018); their
classes after the semantic verification of 2026-10-07 are listed there.

- **PTL conditions → EB states (H-FC-1).** ORACLE §9 requires silence and zero weight to
  propagate "as explicit uncertainty, degradation, or halt"; EB §5 defines the states; no
  text maps one to the other.  The module's mapping: any stale class → `DEGRADED_SIGNAL`
  → `CONDITIONAL` → suspension under ETRANS §4.1.  Consequence (example `fire_ttl`): with
  the §17 TTL of 10 min, a satellite class revisiting every 90 min keeps dependent outputs
  suspended about 94 % of the time.  Needs: the mapping, or per-class rules.  → **F-003**
- **Divergence metric (H-FC-3).** ORACLE §11 says "posterior distributions … differ by more
  than 7%" without a metric or time alignment.  Comparing latest values of classes sampled
  at different times turns a real change into a divergence (example `value_drop`: the true
  value falls from 100 to 80 at step 50; ground and autonomous classes see it at once, the
  orbital class 4 steps later — a 20 % "divergence", suspension, then re-evaluation).  → **F-002**
- **Change without divergence (H-FC-5) — closed, it was a lab error.**  Checkpoint 2 reported
  that a synchronous drop (example `value_drop_in_sync`) left enforcement on the old evaluation
  without any provision failing.  The texts settle it: EB §7.1 lists "new admissible data" as a
  trigger, EB §7.2 requires a new evaluation and recomputation, ETRANS §4.2 forbids keeping an
  output active on a past VALID state once new admissible data is introduced, and JUSTICE §11
  re-evaluates when impact metrics change.  Since `failure_chain` 1.2.0 the default policy is
  `new_admissible_data`; the former reading `declared_events` fails ETRANS-4.2-01.  → **F-001**
  (IMPLEMENTATION_BUG).
- **ETRANS §4.1 list.** Listed downgrades: VALID → CONDITIONAL/INVALID, CONSISTENT →
  ORACLE_CONFLICT, SUFFICIENT_DATA → DEGRADED_SIGNAL.  Not listed: → INSUFFICIENT_DATA,
  → UNRESOLVED, CONDITIONAL → INVALID.  Under H-FC-1 these move validity and are caught
  through it; with another mapping they might not be.
- **Arbitration window.** ORACLE §11 caps arbitration at 14 days but states no consequence
  when the window passes and no exclusion procedure.  The lab measures the window itself (flag to
  resolution, or to the 14-day maximum) and reports the state after an unresolved window as UNKNOWN;
  dependent outputs stay frozen while the data disagree (H-FC-7, example `long_divergence`: 24 days of
  disagreement, window closed at 14).  → **F-018**
- **"State-based transactions"** (ORACLE §11) are not defined; the module treats penalty
  accruals and asset orders as such.
- **Reference defect:** FINANCE §11.2(b) points to "DKP-4-ERROR-001 Section 4.1" for the
  Status Quo Suspension period; ERROR §4 is the error classification, the Status Quo
  Suspension (up to 7 DTI-Days) is defined in ERROR §7.  → **F-004** (the catalog now checks
  every section reference of the corpus: 45 checked, this one broken).
- **EB §9 vs ORACLE §9.** EB: absence of new data alone does not invalidate an output when
  the environment is stable.  ORACLE: data past TTL get weight zero.  The module follows
  ORACLE for PTL data; whether a stable environment keeps a dependent output valid when its
  PTL inputs are past TTL is open.

## 12. Registry status

The registry was drafted with an OpenAI Codex agent and machine-checked (verbatim quotes,
sections, ids).  Interpretations are proposals; a human review of each document's entries
is still open.  Provisions involved in a finding, a reference FAIL or an author question were
read against the literal text (`lab/registry/verifications.json`; `interpretation_status`
TEXT_VERIFIED — not a human review).  The origin of every open point (`open_point.origin`:
normative ambiguity, architecture definition, L8 parameter, empirical model/data, external
dependency, implementation only) is a Codex draft unless an author question was verified
(`lab/registry/unresolved_classification.json`; counts in TRACEABILITY.md).  Missing
calibration, data, documents and code are not author questions; they are listed in
`lab/CALIBRATION_MAP.md` (decomposition of F-014).  Documents whose drafting is not finished are shown as "not yet registered".
