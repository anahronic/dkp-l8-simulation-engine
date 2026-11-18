# DKP red-team validation of the v3 remediation proposals (2026-11-18)

Scope: the 18 cases, 14 collisions and remediation plan T1–T8 of the independent critic's adversarial registry v3
(`audit-v3/DKP_adversarial_audit_registry_v3.xlsx`, SHA-256 `6cb827ac0f24d4f5e0c1d5d88d579b4f92b7d423102ae4bb9965a3845f0b3fda`,
verified), against the audited release `Dikenocracy SYNERGY and 35 PROTOCOLS.txt` (SHA-256 `8f379137…94f8` = World
`aad3e86` `SHA256SUMS.txt`, verified). The author's proposals file cited by the critic (`430be128…46ed2`) was **not
supplied**; the author's proposals are taken from the registry's column "Предложение автора (сводно)".

**What this validation is:** checks of rule logic with synthetic, deterministic models (`dkp8/redteam.py`, 44 scenarios,
16 tests) plus verification of every cited passage against the audited text. **What it is not:** empirical validation,
calibration or proof of real-world safety. Software correctness ≠ normative consistency ≠ empirical calibration ≠
enforceability.

## 1. Method

1. **Text verification.** Every line range cited by the critic was read in the audited TXT. All citations matched (some
   ranges are offset by 1–2 lines; content identical). Two places where the critic's reading is incomplete are recorded in
   §4 (C13, C11).
2. **Dependency graph** (section 2): case → collision → proposal (T-package) → protocol/section → invariants → consumers.
3. **Per proposal:** at least a valid-operation, an adversarial and a partial-failure scenario; compound attacks where two
   individually acceptable mechanisms combine. Blast radius computed where a number is meaningful; otherwise UNKNOWN,
   which is treated as blocking.
4. **Stop rule.** A proposal that breaks another invariant is BLOCKED and its dependent branch stops; no frozen document
   is edited to make a candidate pass; failed variants are kept in the record.
5. **Verdicts:** PASS · CONDITIONAL_PASS · BLOCKED · NEEDS_AUTHOR_DECISION (patches); CONFIRMED_CONTRADICTION ·
   SPECIFICATION_GAP · IMPLEMENTATION_GAP · EMPIRICAL_GAP · UNPROVEN_HYPOTHESIS · RESOLVED (findings).

Reproduce: `python -m dkp8 redteam [--json out.json]`; `python -m pytest tests/dkp8/test_redteam.py` (engine repository).

## 2. Dependency graph (cases ↔ collisions ↔ packages ↔ texts ↔ invariants)

```
T2 Canonical State Manifest (case 6, 18) ──carrier for──> every cancellation in T1 and the electorate in T4
  T1 cancellations: C2/case 8 (Code 8.1, 8.2, 7.3) · C14/case 4 (Code A.1 273) · C9/case 16 (A.3.3) · C1/case 15 (A.1a)
                    · C12/case 17 (A.4 council)            invariants: no collective punishment (ANTITERROR 3776),
                                                           JUSTICE 8 targeted isolation, IDENTITY 1729-1733 proportionality,
                                                           PATCH 4.1 no fallback authority, ORACLE 12 B(t) informational
  T4 electorate (C6/case 5, case 18) <── genesis convention (T2) ──> DKP8-Q-01 signing authority, Q-001
  T5 failure domains / N_eff (C7/cases 3, 17) ──> CRISIS PATCH null-output, RESILIENCE 8409, ORACLE 11/13 states,
                    C11 (A.2 stake vs ORACLE 11) ──> DKP8-Q-02 independent nodes (same graph rule)
  T3/T6 attribution (case 1, C13, case 2, case 12) ──> IDENTITY 4/4.1/1722, IMPACT, ERROR, EPISTEMIC-TRANSITIONS
  T7 boundaries (cases 7, 9, 10, 11, 14; C3, C5, C8, C10) ──> EXIT, INTEROP, SCOPE, LABOR, TIME (+ DTI erratum)
```

Second-order dependencies discovered: T1-b (liability bound) depends on a JUSTICE proportionality coefficient that the
corpus does not define; T3-b (resource limit) has no authorized issuer; T5-a makes *every* N_eff-gated enforcement
unsatisfiable until N_eff_min is calibrated — consistent with fail-closed, but it means no PTL-gated enforcement exists.

## 3. Executed scenarios (44)

| Package | Scenario id | Kind | Result |
|---|---|---|---|
| T1 | T1-KS-current | adversarial: aggressor shields behind population | regional Kill Switch affects 999,880 uninvolved of 1,000,000 → **BLOCKED** (existing rule) |
| T1 | T1-10x-on-collateral | valid | liability = 10 × proven damage even from own collateral → **BLOCKED** variant |
| T1 | T1-collateral-bounded / -insufficient | valid / partial failure | liability ≤ proven damage, no spill-over; unpaid damage stays a claim → CONDITIONAL_PASS |
| T1 | T1-Bt-trigger-current | **compound**: case 3 sensor manipulation + global trigger | 3 of 10 inputs shifted push the stand-in aggregate below 0.68 while the true state is above it; 190 regions disconnected → **BLOCKED**, blast radius GLOBAL |
| T1 | T1-Bt-diagnostic | adversarial | no enforcement path → CONDITIONAL_PASS (needs T2) |
| T1 | T1-DMS-current / -removed | adversarial: staged seizure of own node | half of all stakes burned, insider gains → **BLOCKED**; removed → no collective loss |
| T1 | T1-authority-* (5) | partial failure (System Failure) | A.1a six-node control and A.4 council create authority → **BLOCKED**; ORACLE 14 deferral, enumerated infrastructure operations, external operators → PASS in scope |
| T2 | T2-valid / -forged / -competing-histories / -rollback | valid / adversarial | forged = UNAUTHORIZED; fork and rollback = NON_ENFORCEABLE; no tie-break by time, owner or node |
| T2 | T2-signer-capture | adversarial: 3 of 5 authorizers captured | chain VALID — **UNTESTABLE internally**; legitimacy rests on the declared founding convention |
| T3 | T3-distributed-evasion | adversarial: 50 actors × 0.04 below threshold 0.10 | NO_ATTRIBUTION for all, impact (2.0) recorded, no liability on the unidentified → PASS for the attribution rule; cumulative harm unaddressed |
| T3 | T3-resource-cap / -cap-as-sanction | compound / adversarial | prospective cap has no authorized issuer → NEEDS_AUTHOR_DECISION; cap addressed to residents below survival floor → **BLOCKED** |
| T4 | T4-deactivation-no-snapshot / -snapshot | adversarial: deactivate 10 dissenters | without snapshot 60% becomes 90% and passes → **BLOCKED**; with snapshot fails (60%) |
| T4 | T4-sybil-no-owner-graph / -owner-graph | adversarial: 40 Sybil nodes | without owner graph passes (82.9%) → **BLOCKED**; with owner graph fails — only if ownership is truthful (UNKNOWN residual) |
| T4 | T4-blocking-minority | partial failure (deadlock) | 63% < 67%: status quo, no authority created |
| T4 | T4-fork-compulsory / -ownership-stays | adversarial / valid | majority branch takes non-consenting assets → **BLOCKED**; ownership stays → CONDITIONAL_PASS |
| T5 | T5-common-firmware / -independent / -unknown-provenance | adversarial / valid / partial | 3 sensors with common firmware → N_eff 1; independent → 3; unknown provenance adds nothing (fail-closed) |
| T5 | T5-state-no-threshold | partial failure | N_eff_min undefined → NULL_OUTPUT (nothing enforceable) |
| T5 | T5-local-degradation / -hidden-systemic | partial / adversarial: selective routing | independent domain frozen alone; shared root makes it systemic → NULL_OUTPUT; routing cannot hide it |
| T5 | T5-manual-restore | adversarial | consortium restore request refused |
| T5 | T5-C11-roles | adversarial: poor complainant | detection automatic and wealth-independent; the stake still gates contesting an exclusion → CONDITIONAL_PASS |
| T6 | T6-shared-assumptions / -disagreement | adversarial / partial | same assumptions = one model (informational); independent disagreement → UNATTRIBUTABLE, no averaging |
| T6 | T6-recovery / -recovery-proposal | partial failure | auto-promotion of halt-time outputs → **BLOCKED** variant; re-adjudication with records kept → PASS |
| T6 | T6-reserve-lawfare | adversarial: 100 claims, 10 reversals | 90 refused without reversal; reserve exhausted; funding rule UNKNOWN → NEEDS_AUTHOR_DECISION |
| T7 | T7-ubr / -coordination / -dti-operand | adversarial / partial / boundary | survival access independent of score; 2 of 4 coordination signs → no sanction; DTI operands follow the clarified convention, untyped → inactive |

## 4. Negative results and corrections to the critic

| Item | Critic v3 | This review | Why |
|---|---|---|---|
| **C13** IDENTITY §4 ↔ §4.1 | CONFIRMED internal contradiction, P0 | **RESOLVED for outputs; residual SPECIFICATION_GAP**, P3 | §4.1 d) (TXT 1698–1700) states that the "critical system violation" characterisation does not override epistemic boundaries, and §4.1 b) forbids enforcement cascades on NO_ATTRIBUTION. The defect left is terminological (the protocol calls its own prescribed output a violation; consequences undefined). |
| **10× on the aggressor's collateral** (case 8 alternative b) | "10x lives in the aggressor's stake" | **BLOCKED** | ratio 10 to proven damage violates proportional liability (IDENTITY 1731) regardless of whose collateral pays; needs an explicit JUSTICE coefficient |
| **C11** | collision of two arbitration modes | **SPECIFICATION_GAP**, not a contradiction | ORACLE 11 starts automatically; Code A.2 does not say whose stake or that the stake gates detection; roles are separable (T5-c) |
| **C10, C3** | Code supremacy and programmatic provisions | SPECIFICATION_GAP | supremacy is limited to participating jurisdictions; the status of programme articles needs an author classification |
| **A.6** (not in v3) | — | NEEDS_AUTHOR_DECISION | automatic burning of all stakes + 20-year ban is unbounded by the size of the violation (same question as 8.2) |
| **Code 7.3 burning** | targeted burning within proven damage | NEEDS_AUTHOR_DECISION | burning destroys value without compensating victims; restitution vs burning is normative |

## 5. Second-order risk analysis

| Protective change | New control point / dependency | Failure cascade risk | Mitigation in the candidate |
|---|---|---|---|
| Canonical State Manifest (T2) | genesis authorizers; manifest replicas | quorum capture undetectable; conflicting manifests freeze all dependent enforcement (availability cost) | conflicts fail closed; capture declared as founding assumption; fork for root changes |
| Electorate snapshot (T4) | validator/ownership registry | registrar censorship; hidden ownership | registry hash in manifest; formal criteria only; residual declared |
| Failure-domain N_eff (T5) | provenance graph registry | false supplier declarations; graph custody | presumption of dependency for unknown/disputed provenance; cross-calibration |
| Targeted consequences (T1) | attribution standard, jurisdiction | weaker deterrence; long claims | declared cost; no spill-over to third parties |
| Mercy deferral (T1-g) | list of external confirmation channels | capture of external channels | fail-closed without positive confirmation; channels outside the system and public |
| Resource limit (T3-b) | an issuer that does not exist | becoming a disguised collective sanction | not proposed until an issuer is defined; person-addressed variants BLOCKED |
| Compensation reserve (T6-c) | funding source | exhaustion by lawfare | payouts only on formal reversal; priority for life-critical; not proposed until funded |

## 6. UNTESTED and missing coverage

| Item | Why untested | Evidence needed |
|---|---|---|
| Validator cartel formation over time, adversarial node deactivation at scale | requires an electorate definition and real registry dynamics | the electorate rule (T4-a) and a registry history |
| Compromised calibration metadata, replay of signed bundles | bundle verification exists (`dkp8.bundle`), but no authority/genesis to bind it to | DKP8-Q-01 decision |
| Incomplete event archives, fraudulent authorizations in UPGRADE | no operational archive or upgrade process | an archive and a recorded upgrade |
| Real B(t) manipulation thresholds | no B(t) model (Q-017) | model + PTL data |
| Causal identifiability bounds for real impacts | no causal models registered | model registry + data |
| T7 (birth, coordination, UBR) beyond rule logic | legal capacity and medical criteria are empirical/normative | author criteria + L8 calibration |

Nothing above is claimed safe where it is untested; such items stay NON_ENFORCEABLE (see
`normative-candidates/2026-11-18/enforcement-pathways.json`).
