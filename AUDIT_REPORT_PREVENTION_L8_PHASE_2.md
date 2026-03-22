# Audit Report — DKP-L8-SIMULATION-ENGINE — Phase 2
## Adversarial Incentive Audit

**Protocol:** DKP-1-PREVENTION-001 v1.0 (Frozen)
**Predecessor:** AUDIT_REPORT_PREVENTION_L8.md (Phase 1 — compliance findings F-01…F-12)
**Phase 2 Scope:** Adversarial incentive analysis — rational-agent exploit detection
**Date:** 2026-03-21
**Determinism seed range:** 1001–1010, 5555, 9999

---

## 1. Scope

### Protocol
DKP-1-PREVENTION-001 v1.0 (frozen) — §3–§9 reward pipeline.

### Layer
L8 — simulation only.  No production ZKP, no live oracle feeds.

### Objective
Determine whether rational agents can exploit the current reward formula
to accumulate disproportionate SPD.  All 10 adversarial scenario classes
defined in the TASK SPEC are tested.

### Out of scope
- Protocol modification
- SPD formula changes
- New enforcement rules

---

## 2. Scenarios Tested

| # | Scenario | Config | Seed |
|---|----------|--------|------|
| S1 | Risk Farming | `adversarial/risk_farming.yaml` | 1001 |
| S2 | TA Inflation | `adversarial/ta_inflation.yaml` | 1002 |
| S3 | Partial Suppression Loop | `adversarial/partial_suppression.yaml` | 1003 |
| S4 | Timing Arbitrage | `adversarial/timing_arbitrage.yaml` | 1004 |
| S5 | Attribution Splitting | `adversarial/attribution_split.yaml` | 1005 |
| S6 | Early Prevention | `adversarial/early_prevention.yaml` | 1006 |
| S7 | Oracle Degradation | `adversarial/oracle_degradation.yaml` | 1007 |
| S8 | Oracle Oscillation | `adversarial/oracle_oscillation.yaml` | 1008 |
| S9 | Linkage Threshold Sensitivity | `adversarial/linkage_sweep.yaml` | 1009 |
| S10 | SE ≥ TA Boundary | `adversarial/boundary_se_ta.yaml` | 1010 |

---

## 3. Results Table

| Scenario | Status | Risk Level | Key Result |
|----------|--------|------------|------------|
| S1 Risk Farming | MITIGATED | **MEDIUM** | SPD decays via §9.3 (bucket means: 0.126→0.008); finite accumulation |
| S2 TA Inflation | PASS | LOW | S_k ∈ [0,1] enforced; inflation does not amplify reward |
| S3 Partial Suppression | STRUCTURAL RISK | **MEDIUM** | F-01 mitigates at runner; raw adapter allows over-attribution |
| S4 Timing Arbitrage | PASS (cliff flagged) | **MEDIUM** | SPD flat inside window; abrupt cliff at Δt_int |
| S5 Attribution Splitting | PASS | LOW | Σ A_k ≤ 1.0 per event; split = single actor in expectation |
| S6 Early Prevention | INCENTIVE GAP | **MEDIUM** | Reward(pre-TA)=0 ∧ Reward(post-TA)>0 → delay incentive |
| S7 Oracle Degradation | PASS | LOW | 85.6% informational under high noise; SPD ≥ 0 always |
| S8 Oracle Oscillation | PASS | LOW | Variance bounded (stable: 0.02153, noisy: 0.02148) |
| S9 Linkage Threshold | DISCONTINUITY | **MEDIUM** | Cliff at θ=0.5: SPD(0.50)>0, SPD(0.51)=0 |
| S10 SE ≥ TA Boundary | DISCONTINUITY | LOW | total_spd=0.0 at se_ge_ta=1.0; cliff documented |

---

## 4. Detected Failure Modes

### FM-01: Finite Risk Farming Accumulation (MEDIUM)

**Description:** With activation_rate=0.95 over 30 days × 8 ticks, a high-frequency
actor accumulates `total_spd = 49.847921` despite recurrence decay.

**§9.3 protection active:** SPD per event decays observable across time buckets:

```
Bucket 1 (ticks 0–59):   mean SPD = 0.12567  ← highest
Bucket 2 (ticks 60–119): mean SPD = 0.01694
Bucket 3 (ticks 120–179): mean SPD = 0.02215
Bucket 4 (ticks 180–239): mean SPD = 0.00813 ← lowest
```

Decay confirmed: bucket[3] < bucket[0] (invariant HOLDS).

**Reproducibility:** seed=1001, 30 days, 8 ticks/day — deterministic.

**Conditions:** High activation rate (≥0.9), consistent oracle environment.

**Impact:** Rational agent farming at maximum rate reaches a finite asymptote
(T_k → 0) but accumulates meaningful SPD during the early high-reward phase.
An agent who exploits multiple fresh pattern keys (by varying
`risk_channel` across channels) can extend the high-T_k phase.

---

### FM-02: Partial Suppression Over-Attribution at Adapter Level (MEDIUM)

**Description:** The `PreventionProtocolAdapter.compute_spd()` processes each
actor independently against the same ThreatActivation.  Two actors can each
claim suppression against the original TA without cross-actor awareness.

**Example (verified in test):**
- TA intensity = 0.75
- Actor A: se_intensity = 0.1875 (75% suppression) → SPD_k > 0
- Actor B: se_intensity = 0.2625 (65% suppression) → SPD_k > 0
- Combined implied suppression = 0.5625 + 0.4875 = 1.0500 > TA = 0.75 ← over-attribution

**Mitigation:** The runner's per-event budget (F-01) limits Σ A_k ≤ 1.0,
which in practice means only the first responding actor earns attribution in
a multi-actor event.  `over_attribution_events = 0` in all runner-level tests.

**Residual risk:** If the attribution budget is relaxed at a future layer,
the adapter-level structural risk re-emerges.

**Reproducibility:** Deterministic — test `test_structural_over_attribution_via_direct_adapter`.

---

### FM-03: Early Prevention Incentive Gap (MEDIUM)

**Description:** The temporal validity constraint requires:

```
temporal_valid = (0 < se_time − ta_time ≤ Δt_int)
```

If `se_time < ta_time`, `temporal_valid = False → SPD = 0`.

This means an actor who genuinely prevents a threat *before* it is formally
registered by the oracle system earns zero reward.  The same actor waiting
until after TA registration earns positive SPD.

**Verified:**
- `compute_spd(se_time=−1.0)` → SPD_k = 0.0
- `compute_spd(se_time=+1.0)` → SPD_k > 0.0

**Impact:** Rational agents are incentivised to delay visible intervention
until the TA is registered.  Proactive prevention (before TA) is not rewarded.

**Reproducibility:** Deterministic — tests `test_pre_ta_prevention_earns_zero`
and `test_incentive_gap_flagged`.

---

### FM-04: Linkage Threshold Cliff (MEDIUM)

**Description:** The §9.1 tamper factor uses a strict-greater-than check:

```python
if linkage_score > theta_self_induced:
    return 0.0   # T_k = 0
```

This creates a step function:

```
linkage_score  │  SPD_k
───────────────┼─────────
 0.45 – 0.50   │  0.05000  (positive — T_k = 1.0)
 0.51 – 0.55   │  0.00000  (zero — T_k = 0.0)
```

**Exploit:** An actor who can precisely control their reported `linkage_score`
will anchor at exactly `theta_self_induced = 0.50` to maximise T_k while
being "borderline" on the self-induced dimension.

**Reproducibility:** Deterministic sweep `test_above_theta_earns_zero` /
`test_at_theta_boundary_earns_positive`.

**Note:** This is intended protocol behaviour per §9.1.  The cliff is the
enforcement mechanism.  Audit flags it as a boundary-gaming risk.

---

### FM-05: Temporal Window Cliff at Δt_int (MEDIUM)

**Description:** The temporal window check is binary:

```python
temporal_valid = 0 < dt <= delta_t_int
```

At `se_time = ta_time + 29.9`: SPD_k > 0.
At `se_time = ta_time + 30.1`: SPD_k = 0.

The gradient is effectively infinite at the boundary.

**Impact:** Minimal time-shift (0.2s) converts a positive-SPD event to zero.
This is a correct enforcement mechanism, but the abrupt nature means small
clock drift or measurement error can suppress legitimate reward.

**Reproducibility:** Deterministic — `test_timing_cliff_at_delta_t_int_flagged`.

---

## 5. Discontinuity Analysis

### D-01: SE ≥ TA Boundary

```
SE/TA = 0.99  → S_k = 0.010, SPD_k > 0
SE/TA = 1.00  → S_k = 0.000, SPD_k = 0   ← cliff
SE/TA = 1.01  → S_k = 0.000, SPD_k = 0
```

The reward drops discontinuously from a small positive value to zero.

Full simulation with `se_ge_ta_probability = 1.0`:
- `total_spd_value = 0.0`
- `zero_spd_events = 58`
- `positive_spd_events = 0`

**Classification:** Expected protocol property.  Not exploitable (over-suppressing
does not help the actor).  Logged as boundary risk for measurement sensitivity.

---

### D-02: Linkage Threshold at θ = 0.5

```
linkage_score = 0.500  →  T_k > 0, SPD > 0
linkage_score = 0.501  →  T_k = 0, SPD = 0
```

Gradient: `|ΔSPD / Δlinkage_score|` = 0.05 / 0.001 = 50 SPD/unit.

**Classification:** Boundary exploitation risk.  Agent with precise control
of `linkage_score` can game the exact boundary.

---

### D-03: Temporal Window at Δt_int = 30.0

```
se_time = ta_time + 29.9  →  temporal_valid = True,  SPD > 0
se_time = ta_time + 30.0  →  temporal_valid = True,  SPD > 0      (≤ 30 is valid)
se_time = ta_time + 30.1  →  temporal_valid = False, SPD = 0
```

**Classification:** Correct enforcement.  Clock/measurement sensitivity risk.
A 0.1-unit timing error at the boundary flips the reward.

---

## 6. Incentive Stability

### Per-Scenario Analysis

| Scenario | Rational Convergence to Exploit? |
|----------|----------------------------------|
| S1 Risk Farming | CONDITIONAL — finite accumulation; early cycles are high-value |
| S2 TA Inflation | NO — S_k cancels inflation; ratio-based formula is robust |
| S3 Partial Suppression | CONDITIONAL — mitigated by F-01; raw adapter structurally vulnerable |
| S4 Timing Arbitrage | NO (inside window); CONDITIONAL at cliff |
| S5 Attribution Splitting | NO — budget strictly enforced |
| S6 Early Prevention | CONDITIONAL — delay-until-TA is a rational strategy |
| S7 Oracle Degradation | NO — actors benefit from consistent oracles, not degraded ones |
| S8 Oracle Oscillation | NO — variance bounded; no exploit path via oscillation |
| S9 Linkage Threshold | CONDITIONAL — θ-boundary pinning is rational |
| S10 SE ≥ TA Cliff | NO — over-suppression gives zero reward; no incentive to exceed TA |

### Global Assessment

**Do rational actors converge to exploit?**

> **CONDITIONAL**

Three exploit vectors produce CONDITIONAL instability:

1. **Risk-farming + channel cycling** — actor maxes out high-T_k early phase across
   all 6 channels before decay sets in.  Cannot be made truly unbounded (§9.3 guarantees)
   but is not zero.

2. **Early prevention delay** — proactive actors are penalised vs reactive actors who
   wait for TA registration.  Dominant strategy is to delay visible action.

3. **Linkage threshold pinning** — adversarial actors who control `linkage_score`
   precisely can anchor at θ to avoid tamper-factor zeroing.

---

## 7. Open Risks

| ID | Description | Severity | Mitigation in Place |
|----|-------------|----------|---------------------|
| OR-01 | Early prevention incentive gap | MEDIUM | None — structural protocol property |
| OR-02 | Linkage score pinning at θ boundary | MEDIUM | Rate limiting (if deployed); no L8 fix |
| OR-03 | Partial suppression at adapter level | MEDIUM | F-01 runner budget (mitigated in runner) |
| OR-04 | High-frequency early-phase risk farming | LOW | §9.3 decay asymptotically effective |
| OR-05 | Temporal cliff measurement sensitivity | LOW | None within protocol scope |
| OR-06 | SE/TA boundary cliff | LOW | Expected behaviour; not adversarially exploitable |

---

## 8. New Files Delivered

### Scenario module (1)
| File | Purpose |
|------|---------|
| `simulation/modules/prevention/adversarial_scenarios.py` | 10 scenario config generators + invariant constants |

### Config files (10)
| File |
|------|
| `simulation/configs/adversarial/risk_farming.yaml` |
| `simulation/configs/adversarial/ta_inflation.yaml` |
| `simulation/configs/adversarial/partial_suppression.yaml` |
| `simulation/configs/adversarial/timing_arbitrage.yaml` |
| `simulation/configs/adversarial/attribution_split.yaml` |
| `simulation/configs/adversarial/early_prevention.yaml` |
| `simulation/configs/adversarial/oracle_degradation.yaml` |
| `simulation/configs/adversarial/oracle_oscillation.yaml` |
| `simulation/configs/adversarial/linkage_sweep.yaml` |
| `simulation/configs/adversarial/boundary_se_ta.yaml` |

### Analysis utilities (1)
| File | Purpose |
|------|---------|
| `simulation/core/metrics_adversarial.py` | Phase 2 metric computations (temporal profile, sweeps, efficiency) |

### Test files (2)
| File | Tests |
|------|-------|
| `tests/simulation/test_adversarial_incentives.py` | 31 scenario tests across 10 classes |
| `tests/simulation/test_adversarial_determinism.py` | 13 determinism tests |

---

## 9. Test Results

```
93 passed in 2.07s
```

| Test File | Tests | Status |
|-----------|-------|--------|
| test_adversarial_incentives.py | 31 | ALL PASS |
| test_adversarial_determinism.py | 13 | ALL PASS |
| (all Phase 1 tests) | 49 | ALL PASS |
| **Total** | **93** | **ALL PASS** |

### Key Numerical Evidence

```
S1 Risk Farming — seed 1001, 30 days, 8 ticks/day:
  total_spd             = 49.847921
  positive_spd_events   = 860
  bucket means [Q1–Q4]  = [0.126, 0.017, 0.022, 0.008]   ← decay confirmed

S2 TA Inflation — seed 1002, intensity [0.8–1.0]:
  total_spd             = 31.779100
  attribution_efficiency = 0.307039   (T_k decay reduces to ~30%)

S3 Partial Suppression — seed 1003:
  over_attribution_events (runner) = 0    ← F-01 mitigates
  over_attribution_events (adapter) = 1   ← structural risk confirmed

S7 Oracle Degradation — seed 1007, noise=0.25, dropout=0.20:
  total_spd             = 8.291741
  informational_fraction = 0.856631  (85.7% of events degraded)

S8 Oracle Oscillation — seed 1008:
  stable total_spd      = 32.827777, variance = 0.02153
  noisy  total_spd      = 3.523009,  variance = 0.02148  ← bounded

S9 Linkage Sweep — theta=0.5:
  SPD at linkage=0.50   = 0.050000   ← positive (at boundary)
  SPD at linkage=0.51   = 0.000000   ← step function cliff

S10 SE ≥ TA — se_ge_ta_probability=1.0:
  total_spd             = 0.000000   ← all events → fully_suppressed
```

---

## 10. Conclusion

### System Classification

> **CONDITIONALLY STABLE**

The DKP-1-PREVENTION-001 v1.0 reward pipeline as implemented in
`dkp-l8-simulation-engine` is not freely exploitable.  The core formula
`SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ` enforces meaningful constraints:

- **S_k** is bounded [0,1] and normalises by TA intensity — TA inflation is harmless
- **T_k** decays to 0 via §9.3 — risk farming is finite and asymptotically self-limiting
- **A_k** is budget-capped ≤ 1 per event (F-01) — attribution splitting is controlled
- **C_k** requires valid oracle coverage — oracle manipulation reduces reward

However, three CONDITIONAL exploit vectors are not fully closed:

1. **OR-01** — Early prevention delay: a rational actor waits for TA registration before
   intervening, sacrificing the prevention value of proactive action.

2. **OR-02** — Linkage boundary pinning: a rational adversarial actor anchors
   `linkage_score` at exactly θ to maintain T_k > 0 while being "borderline" on the
   self-induced dimension.

3. **OR-04** — Risk farming early phase: across multiple fresh channels, the high-T_k
   early cycles produce meaningful SPD before decay activates.

None of these produce *unbounded* reward.  None represent a complete break of the
protocol's enforcement model.  All are deterministic, reproducible, and disclosed.

### Protocol Integrity

- Protocol semantics: UNCHANGED
- SPD formula: UNCHANGED
- All 12 Phase 1 findings: remain FIXED
- All 93 tests: PASS

---

*End of Phase 2 audit report.*
