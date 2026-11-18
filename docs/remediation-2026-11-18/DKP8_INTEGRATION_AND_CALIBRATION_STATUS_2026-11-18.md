# DKP-8 integration and calibration status (2026-11-18)

Engine `anahronic/dkp-l8-simulation-engine`; baseline `6ca6d96` (release `6ca6d96-lab`, deployed). New today: the red-team
models of the v3 remediation proposals (`dkp8/redteam.py`, `python -m dkp8 redteam`, 16 tests). Existing components
(canonical JSON, Ed25519, trust store, Calibration Bundle lifecycle, enforceability, gate, reproduction) are unchanged.

## 1. Re-run of the DKP-8 tools (2026-11-18)

| Check | Result |
|---|---|
| Full engine suite | **1783 passed** (1767 baseline + 16 red-team tests; nothing skipped or bypassed) |
| `python -m dkp8 catalog` | 17/17 synthetic dossiers give the expected decision (none ELIGIBLE with the canonical trust store) |
| `python -m dkp8 trace` | 48 provisions, unchanged: IMPLEMENTED_AND_TESTED 30 · IMPLEMENTED_UNVERIFIED 2 · PARTIAL 9 · MISSING 0 · BLOCKED_BY_NORMATIVE_DECISION 5 · BLOCKED_BY_EMPIRICAL_DATA 2 · NOT_COMPUTABLE 0 |
| `python -m dkp8 status` | trust store: 0 authorities, 0 nodes, 1 development key; 0 calibration bundles; 7 NON-ENFORCEABLE scopes, 13 UNCALIBRATED parameters |
| Reproduction | smoke package re-runs to `result_id 77d06a9b…` (R1); CI matrix per OS; no R3 node |
| `python -m dkp8 redteam` | 44 synthetic scenarios over T1–T7 (see `DKP_RED_TEAM_VALIDATION_2026-11-18.md`) |

The 48-provision statuses did not change: no new evidence (authority, node, PTL data, calibration value) exists. The
remediation audit changes *why* several blockers exist, not their status.

Status lines: SOFTWARE_COMPLETE **PARTIAL** · CANONICAL_REQUIREMENTS_COVERED **PARTIAL** · CALIBRATION_VALIDATED **NO** ·
INDEPENDENT_REPRODUCTION_VALIDATED **NO** · REAL_DATA_VALIDATED **NO** · OPERATIONAL_DKP8_COMPLIANT **NO**.
TESTED ≠ ELIGIBLE ≠ ENFORCEABLE ≠ OPERATIONAL: nothing here is eligible, enforceable or operational.

## 2. Blockers by kind

| Blocker | Kind | Source |
|---|---|---|
| No L8 signing authority (DKP8-Q-01) | normative (governance) | SIMULATION §3/§9; depends on T2 genesis convention |
| No definition of independent node / count (DKP8-Q-02) | normative + infrastructural | SIMULATION §8; depends on T4 electorate and T5 failure domains |
| Audit tolerances (DKP8-Q-03) | empirical | SIMULATION §13 |
| N_eff and N_eff_min undefined | normative (specification gap) + empirical (N_eff_min) | CRISIS PATCH 5043/5118, RESILIENCE 8409; ORACLE defines no N_eff |
| Composite indices without models (Q-017); C14 | normative + empirical | ORACLE §12; Code A.1 273 |
| Trigger suspension of bundles (Q-034) | normative | SIMULATION §10 |
| Which protocols bind now (Q-035) | normative | SIMULATION §4 |
| Who accepts a norm (Q-001) | normative | UPGRADE; depends on T2/T4 |
| PTL datasets, deployed behaviour | empirical / infrastructural | SIMULATION §5, §13 |
| Life-preservation metric, SCOPE machine form, F2 operational definitions | normative | SIMULATION §6, §7 |
| Data-level detection of unphysical/smoothed input | implementation (needs physical bounds = calibration) | SIMULATION §5 |

## 3. Outstanding decisions re-evaluated against the v3 findings (candidate answers — NOT approved)

| Question | Re-evaluation | Candidate answer for the author | Invariants it must keep |
|---|---|---|---|
| **DKP8-Q-01** signing authority | Cannot be answered before the canonical-authorization root (case 6, T2): a bundle signed by a key that no authorized manifest names has no standing. The repository owner is not an authority by ownership. | A k-of-n key set declared in the branch genesis convention and recorded in the Canonical State Manifest; rotation and revocation only by authorized manifest transitions; development/test keys never qualify. | no sovereign key; conflicts fail closed (NON_ENFORCEABLE); integrity ≠ origin ≠ validity |
| **DKP8-Q-02** independent nodes | Depends on failure domains (T5: a node sharing operator/infrastructure/implementation roots is not independent) and on the electorate rules (T4: Sybil, ownership graph). | A node counts only if its operator, infrastructure and implementation roots are disjoint from the others' in the provenance/ownership graph and it signs R3 records with a registered key; the minimum count is an author decision. | Sybil resistance; no node registrar with discretion |
| **DKP8-Q-03** audit tolerances | Purely empirical; a value chosen for test convenience is forbidden. | Calibrate per metric from deployed-vs-simulated data with stated confidence; until then NOT_ESTABLISHED (already implemented). | no invented numbers |
| **Q-001** who accepts a norm | Same root as Q-01 (T2 genesis convention) and T4 (electorate snapshot). | Acceptance = an authorized manifest transition; root changes by branching with renewed consent. | no compulsory migration; ownership does not follow the protocol |
| **Q-017** composite indices | Reinforced by C14: even a fully specified B(t) must not trigger global sanctions without a canonical transition; red team T1-Bt shows a 3-of-10-input manipulation suffices against the current rule. | Composite indices remain research/diagnostic outputs until model + bundle + a separate enforcement norm exist. | ORACLE §12; SIMULATION §9 |
| **Q-034** trigger suspends bundle? | The PATCH principle "no enforcement is strictly safer than invalid enforcement" (TXT 5180) supports suspension. | Recorded trigger → bundle INDETERMINATE and not enforceable until recalibration (what the software already does fail-closed). | fail-closed |
| **Q-035** which protocols bind now | With N_eff undefined, every enforcement gated by `N_eff ≥ N_eff_min` is unsatisfiable; no bundle exists. | None of the 16 pathways in `normative-candidates/2026-11-18/enforcement-pathways.json` is enabled; records, research and simulation continue. | — |

## 4. Relationship between the remediation findings and L8

- T5 (N_eff by failure domains) is the operational definition DKP8-Q-02 needs for nodes and the PATCH needs for PTL
  sources: one provenance-graph rule, two uses (`dkp8.redteam.n_eff`, fail-closed for unknown provenance).
- T2 (Canonical State Manifest) is the carrier for DKP8-Q-01 and Q-001; `dkp8.redteam.verify_chain` shows that integrity,
  origin and authorization are separately testable and that quorum capture is not detectable internally.
- T1-d (B(t) diagnostic) aligns the Code with what `dkp8.enforcement.enforceability` already reports (B(t) UNCALIBRATED).

## 5. DTI: author clarification, conflict with the published text, erratum candidate

### 5.1 The authoritative convention (author, 2026-11-18)

JDN 0 is the epoch anchor of the count — not a dated day and not Year 1. JDN 1 is Year 1, Day 1. Each DTI year has 360
days, numbered from 1: `DY = floor((JDN − 1) / 360) + 1`, `DOY = ((JDN − 1) mod 360) + 1`, inverse
`JDN = (DY − 1) × 360 + DOY`. Boundaries: JDN 0 = epoch, JDN 1 = DY1-001, JDN 360 = DY1-360, JDN 361 = DY2-001. No Year 0,
no alternative epoch. Days before the epoch are not defined by the clarification (implementations reject them).

**Cancelled:** the earlier assistant interpretation (JDN 0 = `DY0-001`, zero-based DY) and every conclusion of
`DTI_ERRATUM_2026-11-17.md` that relied on it (it kept the zero-based formula and only questioned the 2000-01-01 row).

### 5.2 Conflict (CONFIRMED) with the frozen DKP-0-TIME-001 (World `aad3e86`, sha256 `165008e1…`)

| Section | Published text | Conflict |
|---|---|---|
| §5.1 | `DY = floor(DTI-Day / 360)`, `DOY = (DTI-Day mod 360) + 1` | zero-based: JDN 1 → DY0-002, JDN 0 → DY0-001 |
| §5.2 | `<dy>` signed integer; example `DY6836-084` | example computed zero-based |
| §6.2 | `DTI-Day = DY × 360 + (DOY − 1)` | inverse of the zero-based form |
| §6.3 | `DY MAY be negative` | no Year 0 / pre-epoch dates in the clarification |
| §9 | 2026-01-01 DY6836-083; 2026-01-02 DY6836-084; 1970-01-01 DY6779-149; 2000-01-01 DY6815-026 | first three zero-based; the 2000-01-01 row matches neither form |
| §10 | `jdn // 360, jdn % 360 + 1`; `dy * 360 + (doy - 1)` | reference code zero-based |

Recomputed values (civil date → JDN by Fliegel–Van Flandern):

| Date | JDN | Published table | Published formula | Clarified |
|---|---|---|---|---|
| 2026-01-01 | 2461042 | DY6836-083 | DY6836-083 | **DY6837-082** |
| 2026-01-02 | 2461043 | DY6836-084 | DY6836-084 | **DY6837-083** |
| 1970-01-01 | 2440588 | DY6779-149 | DY6779-149 | **DY6780-148** |
| 2000-01-01 | 2451545 | DY6815-026 | DY6809-306 | **DY6810-305** |
| 4714 BC Nov 24 (proleptic Gregorian) | 0 | — | DY0-001 | **epoch anchor (no date)** |

### 5.3 Erratum candidate (for author approval; the protocol text is NOT changed)

- **§3 (add):** "**DTI Epoch.** DTI-Day 0 (JDN 0) is the epoch anchor of the count. It is not a dated day and has no DY or
  DOY. DTI-Year 1 begins at DTI-Day 1."
- **§5.1 (replace):** "Given a canonical `DTI-Day ≥ 1`: `DY = floor((DTI-Day − 1) / 360) + 1`; `DOY = ((DTI-Day − 1) mod 360) + 1`.
  DTI-Day 0 is the epoch anchor (§3)."
- **§5.2 (replace):** "`<dy>` is a positive integer year index (≥ 1)"; example `DY6837-083` (2026-01-02).
- **§6.2 (replace step 1–2):** "Validate `DY ≥ 1` and `DOY ∈ [1, 360]`. Compute `DTI-Day = (DY − 1) × 360 + DOY`."
- **§6.3 (replace):** "`DY` values below 1 MUST be rejected. Days before the epoch (DTI-Day < 0) are not represented in
  DY/DOY form." *(whether pre-epoch days need any representation is an open author question)*
- **§9 (replace table):** the four "Clarified" values above, plus boundary rows JDN 1 = DY1-001, JDN 360 = DY1-360,
  JDN 361 = DY2-001, JDN 0 = epoch.
- **§10 (replace):** `jdn_to_dikenocratic`: reject `jdn < 1` (epoch / pre-epoch), return `((jdn − 1) // 360 + 1, (jdn − 1) % 360 + 1)`;
  `dikenocratic_to_jdn`: validate `dy ≥ 1`, return `(dy − 1) × 360 + doy`.
- Procedure: a correction of normative content is an Upgrade (DKP-4-UPGRADE-001), not a presentation-only correction;
  the author decides the route. Affected versions: the 2026-10-04 edition of DKP-0-TIME-001 and the consolidated TXT.

### 5.4 Implementation now follows the clarification (deployed 2026-11-18, site `64945a2`)

| Implementation | State | Tests |
|---|---|---|
| Website converter `converter.js` (+ both converter pages) | clarified convention; epoch reported explicitly; pre-epoch and DY < 1 rejected; pages state that the published text awaits an erratum | `website/tools/test_converter_dti.mjs`: 36 checks (boundaries 0/1/360/361/720/721; recomputed vectors; 1600–2400 exhaustive round trip; first 5,000 days; JD-at-noon vs civil date; conflict table reported) |
| Python package `Converter DTI/converter_dti` | same | 28 tests (vectors, boundaries, epoch/pre-epoch errors, first three years, JD vs civil date, API) |
| Engine Protocol Lab (`lab/modules/time.py:dy_doy`, labels in `work_cycle`, `crisis_recovery`, `defense_envelope`, `dispute_correction`, `exit_integration`) | **unchanged on purpose**: the Lab audits the published text (TIME-5.1-01/02 check the frozen formula). Switch in one place (`dy_doy`, `from_dy_doy`, TIME checks, work-cycle label checks) after the erratum is approved. | — |
| L8 bench (`simulation/core/timebase.py`) | unaffected: uses DTI-Day = JDN only | — |

Astronomical Julian Date vs civil date (tested separately): a JD starts at noon; 2000-01-01 00:00 = JD 2451544.5, whose
integer astronomical day is 2451544, while the civil date 2000-01-01 has JDN 2451545. Civil conversion uses the civil
JDN; the epoch and the integer-day numbering are the same in both conventions.
