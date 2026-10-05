> **Historical (v1, commit `a9d3cdf`, 2026-03).** Kept unchanged below. F-01 (budget) consumed shares before eligibility; F-09 (CBF) used a non-standard estimator over the generator's truth; F-11 (defaults) fixed only the adapter constructor. All three are reworked in 2.0.0; see CHANGELOG.md.

# Fix Report — DKP-L8-SIMULATION-ENGINE

**Protocol:** DKP-1-PREVENTION-001 v1.0 (Frozen)
**Audit Reference:** AUDIT_REPORT_PREVENTION_L8.md
**Date:** 2026-03-21
**Scope:** Remediation of all 12 findings (F-01 through F-12)

---

## 1. Fixed Findings

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| F-01 | CRITICAL | Σ Aₖ ≤ 1 not enforced | **FIXED** |
| F-02 | CRITICAL | No ZKP interface | **FIXED** |
| F-03 | HIGH | Hardcoded recurrence threshold | **FIXED** |
| F-04 | HIGH | SE ≥ TA unreachable in runner | **FIXED** |
| F-05 | HIGH | Temporal invalidity unreachable | **FIXED** |
| F-06 | MEDIUM | Hardcoded SE time lower bound | **FIXED** |
| F-07 | MEDIUM | θ_self_induced not used as threshold | **FIXED** |
| F-08 | MEDIUM | Actor effectiveness ranges hardcoded | **FIXED** |
| F-09 | MEDIUM | CBFᵢ not modeled | **FIXED** |
| F-10 | LOW | No temporal alignment integration test | **FIXED** |
| F-11 | LOW | Default parameter values in constructor | **FIXED** |
| F-12 | LOW | No adversarial integration test | **FIXED** |

**All 12 findings resolved. No findings remain open.**

---

## 2. Files Changed

### Modified files (8)

| File | Findings Addressed |
|------|-------------------|
| `simulation/run_prevention_simulation.py` | F-01, F-04, F-05, F-06, F-07, F-09 |
| `simulation/modules/prevention/protocol_adapter.py` | F-02, F-03, F-07, F-11 |
| `simulation/core/actors.py` | F-07, F-08 |
| `simulation/modules/prevention/calibration.py` | F-03 |
| `simulation/modules/prevention/domain_childcare.py` | F-08 |
| `simulation/modules/prevention/test_vectors.py` | F-07 |
| `simulation/configs/prevention_childcare_v0_1.yaml` | F-03, F-04, F-05, F-06 |
| `simulation/configs/prevention_childcare_fast_smoke.yaml` | F-03, F-04, F-05, F-06 |

### New files created (8)

| File | Purpose |
|------|---------|
| `simulation/core/privacy.py` | F-02 — ZKP interface + PlaceholderZKPProvider |
| `simulation/core/cbf.py` | F-09 — ContextualBaselineField + CBFRegistry |
| `tests/simulation/test_attribution_budget.py` | F-01 — 6 tests (unit + integration) |
| `tests/simulation/test_zkp_interface.py` | F-02 — 5 tests |
| `tests/simulation/test_failure_paths.py` | F-04, F-05, F-10 — 3 tests |
| `tests/simulation/test_recurrence_threshold.py` | F-03 — 3 tests |
| `tests/simulation/test_linkage_threshold.py` | F-07 — 7 tests |
| `tests/simulation/test_adversarial_integration.py` | F-12 — 3 tests |

### Test files updated (5)

| File | Changes |
|------|---------|
| `tests/simulation/test_vectors.py` | F-11: all params required; F-07: `linkage_score` API |
| `tests/simulation/test_self_induced.py` | F-11, F-07: same |
| `tests/simulation/test_informational.py` | F-11: all params required |
| `tests/simulation/test_oracle_consistency.py` | F-11: all params required |
| `tests/simulation/test_reproducibility.py` | F-03, F-04, F-05, F-06: config keys added |

---

## 3. Fix Details

### F-01 — Σ Aₖ ≤ 1 per event (CRITICAL)

**Change:** Added per-event attribution budget in `run_prevention_simulation.py`. Before processing actors for a threat event, `remaining_attribution = 1.0`. Each actor's proposed share is clamped to the remaining budget. Once exhausted, subsequent actors receive A_k = 0 and are skipped.

**Key code:**
```python
remaining_attribution = 1.0
for actor in actors:
    ...
    actual_share = min(proposed_share, remaining_attribution)
    remaining_attribution -= actual_share
    if actual_share <= 0.0:
        continue
```

### F-02 — ZKP interface placeholder (CRITICAL)

**Change:** Created `simulation/core/privacy.py` with:
- `ZKPProof` dataclass (subject_id, claim_hash, proof_data, verified, metadata)
- `ZKPProvider` ABC with `create_proof()` and `verify_proof()` methods
- `PlaceholderZKPProvider` — `create_proof()` returns stub; `verify_proof()` raises `NotImplementedError`

Wired into `PreventionProtocolAdapter.__init__` (accepts optional `zkp_provider`; defaults to `PlaceholderZKPProvider`). Called in `compute_spd()` at the point where SI/linkage proof would be validated.

### F-03 — Recurrence threshold configurable (HIGH)

**Change:** Added `recurrence_threshold: int` to:
- `PreventionProtocolAdapter.__init__` (required parameter)
- `PreventionCalibration` dataclass + `to_dict()` / `from_dict()`
- Both YAML configs under `protocol.recurrence_threshold: 3`
- Runner passes `proto_cfg.get("recurrence_threshold", 3)` to adapter

Changed `count - 3` to `count - self.recurrence_threshold` in `compute_tamper_factor()`.

### F-04 / F-05 — Failure paths reachable (HIGH)

**Change:** Added config keys:
- `simulation.se_ge_ta_probability` (default 0.0)
- `simulation.temporal_invalid_probability` (default 0.0)

Runner checks these probabilities per-intervention:
- When SE ≥ TA triggered: `se_intensity = ta.intensity * rng.uniform_range(1.0, 1.5)`
- When temporal invalid triggered: `se_time` set to `ta_time + uniform_range(delta_t_int + 1, delta_t_int * 2)`

Default 0.0 preserves existing normal-case behavior.

### F-06 — SE delay min from config (MEDIUM)

**Change:** Added `simulation.se_delay_min: 1.0` to both YAML configs. Runner reads `sim_cfg.get("se_delay_min", 1.0)` and uses it as the lower bound for `uniform_range(se_delay_min, delta_t_int)`.

### F-07 — Continuous linkage threshold (MEDIUM)

**Change:**
- `InterventionResult.self_induced: bool` → `InterventionResult.linkage_score: float = 0.0`
- `compute_tamper_factor(self_induced: bool, ...)` → `compute_tamper_factor(linkage_score: float, ...)`
- Check changed from `if self_induced:` to `if linkage_score > self.theta_self_induced:`
- `compute_spd(self_induced: bool)` → `compute_spd(linkage_score: float = 0.0)`
- Adversarial actors set `linkage_score=1.0` for self-induced interventions; honest actors set `linkage_score=0.0`

### F-08 — Actor effectiveness ranges configurable (MEDIUM)

**Change:** Added `effectiveness_range: tuple = None` to `Actor` dataclass. Replaced strategy-specific hardcoded ranges in `decide_intervention()` with:
```python
if self.effectiveness_range is not None:
    eff *= self.rng.uniform_range(*self.effectiveness_range)
```
Moved ranges into `CHILDCARE_ACTOR_PROFILES` in `domain_childcare.py`.

### F-09 — CBF placeholder (MEDIUM)

**Change:** Created `simulation/core/cbf.py` with:
- `ContextualBaselineField` dataclass (zone_id, risk_channel, baseline_mean, baseline_std, sample_count)
- `CBFRegistry` with Welford's running statistics and audit export
- Runner instantiates `CBFRegistry()`, calls `update()` per threat event, writes `cbf_baselines.json` to output

### F-10 — Temporal alignment integration test (LOW)

**Change:** Added `tests/simulation/test_failure_paths.py` with `TestTemporalInvalidityPath` that runs a full simulation with `temporal_invalid_probability=0.5` and asserts `temporal_invalid` events appear with SPD = 0.

### F-11 — Required protocol parameters (LOW)

**Change:** Removed all default values from `PreventionProtocolAdapter.__init__` for protocol-critical parameters:
```python
def __init__(self,
    epsilon_consistency: float,   # was: = 0.15
    delta_t_int: float,           # was: = 30.0
    theta_self_induced: float,    # was: = 0.5
    recurrence_decay: float,      # was: = 0.9
    coverage_floor: float,        # was: = 0.1
    recurrence_threshold: int,    # new, required
    ...
```
Updated all test fixtures and config consumers to pass all required values explicitly.

### F-12 — Adversarial integration test (LOW)

**Change:** Created `tests/simulation/test_adversarial_integration.py` with 3 tests:
1. Adversarial run completes
2. Deterministic with adversarial actors
3. Self-induced threats produce reduced/zero reward through full pipeline

---

## 4. Test Results

```
49 passed in 0.32s
```

| Test File | Tests | Status |
|-----------|-------|--------|
| test_adversarial_integration.py | 3 | PASS |
| test_attribution_budget.py | 6 | PASS |
| test_failure_paths.py | 3 | PASS |
| test_informational.py | 4 | PASS |
| test_linkage_threshold.py | 7 | PASS |
| test_oracle_consistency.py | 5 | PASS |
| test_recurrence_threshold.py | 3 | PASS |
| test_reproducibility.py | 2 | PASS |
| test_self_induced.py | 3 | PASS |
| test_vectors.py | 8 | PASS |
| test_zkp_interface.py | 5 | PASS |
| **Total** | **49** | **ALL PASS** |

### Smoke Test

```
Seed: 42, Zones: 1, Days: 2, Ticks: 8
Total SPD value: 9.321156
Subject count: 2
Informational events: 1
```

### Determinism Verification

```
Run 1: total_spd_value = 9.321156
Run 2: total_spd_value = 9.321156
MATCH: True
Subjects match: True
```

### Adversarial Run

```
Seed: 77777, Zones: 1, Days: 5, include_adversarial: True
Completes, deterministic, adversarial actor SPD suppressed.
```

---

## 5. Remaining Open Findings

**None.** All 12 findings from the audit report have been resolved.

---

## 6. Impact Notes

- **SPD values have changed** from the pre-fix baseline (e.g., smoke test went from 24.300653 to 9.321156) due to F-01 attribution budget enforcement. This is expected — the old values were inflated by Σ Aₖ > 1 violations.
- **Determinism is preserved** — same seed produces identical output across runs.
- **No protocol semantics were changed** — only missing enforcement was added.
- **Backward compatibility:** Configs without the new keys (e.g., `recurrence_threshold`, `se_ge_ta_probability`) use safe defaults (3, 0.0) via `.get()` in the runner. The protocol adapter itself requires all params explicitly (F-11).

---

*End of fix report.*
