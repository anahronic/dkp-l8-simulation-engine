# Audit Report — DKP-L8-SIMULATION-ENGINE

**Protocol Under Audit:** DKP-1-PREVENTION-001 v1.0 (Frozen)
**Engine:** DKP-L8-SIMULATION-ENGINE
**Date:** 2026-03-21
**Auditor Role:** Independent Technical Auditor
**Scope:** Full repository compliance audit

---

## 1. Summary

| Metric | Value |
|--------|-------|
| **Overall Status** | **ACCEPT WITH FIXES** |
| Critical Issues | 2 |
| High Issues | 3 |
| Medium Issues | 4 |
| Low Issues | 3 |

The engine correctly implements the core SPDₖ calculation pipeline and all primary protocol invariants. Determinism is fully verified. Two critical issues relate to missing enforcement of Σ Aₖ ≤ 1 and the absence of a ZKP interface placeholder. Three high-severity issues concern the semantic interpretation of suppression in the main loop, hidden default constants, and incomplete temporal alignment testing.

---

## 2. Protocol Compliance

### 2.1 Oracle Consistency — §3.3

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Δ_oracle = max(intensity) − min(intensity) | **PASS** | `protocol_adapter.py` L128 | Correctly computes `max(intensities) - min(intensities)` |
| ε_consistency applied | **PASS** | `protocol_adapter.py` L129 | `delta_oracle <= self.epsilon_consistency` |
| Consistent regime → min(valid intensities) | **PASS** | `protocol_adapter.py` L131–132 | `ta_intensity = min(intensities)` when consistent |
| Inconsistent regime → informational (NOT 0) | **PASS** | `protocol_adapter.py` L142 | `informational=not is_consistent` — explicitly sets informational flag |

### 2.2 Informational State

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Exists as explicit state | **PASS** | `protocol_adapter.py` L45 (`ThreatActivation.informational`), L64 (`SPDResult.informational`) | Dedicated boolean field in both data classes |
| NOT converted to zero silently | **PASS** | `protocol_adapter.py` L341–356 (`_informational_spd`) | Returns SPDResult with `informational=True`, `SPD_k=0.0`. Reason logged as "oracle_inconsistency" with delta and epsilon values |
| Propagates to metrics correctly | **PASS** | `run_prevention_simulation.py` L218 | `metric_name = "SPD_informational" if spd.informational else "SPD"` — distinct metric name. Verified: 3 informational records in smoke output with value=0.0. Summary counts them separately: `informational_events: 3` |

### 2.3 Temporal Alignment — §3.6

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| TA @ t₀ and SE @ t₁ tracked | **PASS** | `protocol_adapter.py` L155–157 | `compute_suppression(ta_intensity, se_intensity, ta_time, se_time)` takes both timestamps |
| 0 < (t₁ − t₀) ≤ Δt_int checked | **PASS** | `protocol_adapter.py` L164 | `temporal_valid = 0 < dt <= self.delta_t_int` |
| Violation → SPD = 0 | **PASS** | `protocol_adapter.py` L272 | `if not suppression.temporal_valid: return self._zero_spd(...)` with reason `"temporal_invalid"` |

**NOTE:** In the main simulation loop (`run_prevention_simulation.py` L208), `se_time` is computed as `timestamp + zone.rng.uniform_range(1.0, proto_cfg["delta_t_int"])`. The lower bound of 1.0 ensures `dt > 0`, and the upper bound of `delta_t_int` ensures `dt ≤ delta_t_int`. This means the temporal invalidity path is **unreachable from the main loop**. See Finding F-05.

### 2.4 Suppression Logic — §3.6

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Sₖ = clamp(0,1,(TA−SE)/TA) | **PASS** | `protocol_adapter.py` L181–182 | `raw = (ta_intensity - se_intensity) / ta_intensity; S_k = max(0.0, min(1.0, raw))` |
| SE ≥ TA → Sₖ = 0, SPDₖ = 0 | **PASS** | `protocol_adapter.py` L172–178 | Guard `if se_intensity >= ta_intensity` returns `S_k=0.0, fully_suppressed=True`. Compute_spd checks `if suppression.fully_suppressed` then returns zero SPD |

**NOTE:** In the main loop, `se_intensity = max(0.0, ta.intensity - intervention.suppression_intensity)`. Since `suppression_intensity ≥ 0`, we always get `se_intensity ≤ ta.intensity`. The `fully_suppressed` guard is unreachable from the runner (see Finding F-04). The guard exists correctly as a defensive measure for direct API use.

### 2.5 Core Recognition Rule — §4

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| TA(valid, consistent) ∧ SI ∧ SE required | **PARTIAL** | `protocol_adapter.py` L260–267 | Checks `ta.is_valid` and `ta.informational`. However, the explicit "SI exists" check is implicit — the runner only calls `compute_spd` when `intervention.responded == True`. The protocol adapter itself does not independently verify SI presence |
| Absence of any → no reward | **PASS** | `protocol_adapter.py` L264–267, `run_prevention_simulation.py` L199 | Invalid TA → zero SPD. Actor not responding → skipped (no SPD computed). These correctly enforce the rule |

### 2.6 Attribution — §6

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Aₖ > 0 ⇔ causal linkage traceable | **PASS** | `protocol_adapter.py` L286 | `A_k = max(0.0, min(1.0, attribution_share))` — clamps to [0,1] |
| **Σ Aₖ ≤ 1 enforced** | **FAIL** | `actors.py` L42, `run_prevention_simulation.py` L212 | Every actor has `attribution_share: float = 1.0`. In the main loop, multiple actors process the same threat event. Each gets `A_k = 1.0`. There is NO enforcement that Σ Aₖ ≤ 1 across actors for a single event. Three actors can each claim A_k = 1.0 for the same threat, yielding Σ A_k = 3.0. **Critical violation of §6** |
| No auto-normalization to 1 | **PASS** | No normalization code exists | The code does not normalize — but it also does not enforce the constraint |

### 2.7 Self-Induced Risk — §9.1

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| linkage > θ → Tₖ = 0 | **PASS** | `protocol_adapter.py` L226–227 | `if self_induced: return 0.0` |
| θ configurable | **PASS** | `protocol_adapter.py` L89 | `self.theta_self_induced` from config. Note: θ is stored but the actual comparison uses a boolean `self_induced` flag from the actor, not a continuous linkage score compared against θ. See Finding F-07 |

### 2.8 Pattern Recurrence — §9.3

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| repeat(TAₖ pattern) → Tₖ ↓ | **PASS** | `protocol_adapter.py` L230–235 | Pattern key `"{actor_id}:{risk_channel}"` tracked. Decay after 3 occurrences: `T_k = recurrence_decay ** max(0, count - 3)` |

### 2.9 Coverage Integrity — §9.4

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Low coverage → Cₖ ↓ | **PASS** | `protocol_adapter.py` L215–220 | Average confidence, floored at `coverage_floor` |
| No data → SPDₖ = 0 | **PASS** | `protocol_adapter.py` L217, L290 | Empty readings → C_k = 0.0 → `_zero_spd("no_coverage")` |

### 2.10 Multi-Oracle Requirement — §9.5

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Single oracle class → invalid TA | **PASS** | `protocol_adapter.py` L112–113 | `classes = {r.oracle_class for r in readings}; is_valid = len(classes) >= 2` |

### 2.11 Privacy — §8

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| ZKP interface or placeholder | **FAIL** | No file in repository | No ZKP module, interface, or placeholder exists anywhere in the codebase. `grep -rn "ZKP\|zkp\|zero.knowledge\|privacy" simulation/ tests/` returns empty |
| No raw behavior exposure in outputs | **PASS** | `simulation/outputs/smoke/metrics.json` inspected | Outputs contain only aggregated SPD factors, risk channels, oracle classes. No identity data, GPS, timestamps-as-locations, or behavioral logs. Actor IDs are synthetic |

### 2.12 Justice Non-Leakage — §7

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| No obligation/liability/duty creation | **PASS** | Architecture inspection | SPD records are observation-only. No enforcement, obligation, or duty creation in the output pipeline |

### 2.13 Coordinated Drift Protection — §10

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| Peer signals non-reward | **N/A** | | No peer signal mechanism in scope — single-engine simulation |
| Global floors enforced | **PARTIAL** | `protocol_adapter.py` L219 | `coverage_floor` enforced. No explicit global floor on other factors |

### 2.14 SPDₖ Calculation — §5

| Rule | Status | Evidence | Notes |
|------|--------|----------|-------|
| SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ | **PASS** | `protocol_adapter.py` L296 | `SPD_k = W_k * S_k * A_k * C_k * T_k` — exact match |
| PS_subject = Σ SPDₖ | **PASS** | `metrics.py` L38, `run_prevention_simulation.py` L238 | `add_subject_contribution(actor_id, spd.SPD_k)` — accumulates per-subject. Only called when `SPD_k > 0` |

---

## 3. Engine Architecture

### 3.1 Core vs Module Separation

| Check | Status | Evidence |
|-------|--------|----------|
| Core is protocol-agnostic | **PASS** | `simulation/core/` contains: rng, zones, oracles, actors, events, metrics, config. None imports from `simulation.modules.prevention` |
| No prevention logic in core | **PASS** | `grep -rn "prevention\|SPD\|suppression\|informational" simulation/core/` — no matches in logic code. Only EventType enum has "SUPPRESSION" as a generic type name |
| Prevention logic isolated in module | **PASS** | All protocol math is in `simulation/modules/prevention/protocol_adapter.py`. Domain specifics in `domain_childcare.py`. Calibration in `calibration.py` |

### 3.2 Coupling Issues

| Check | Status | Evidence |
|-------|--------|----------|
| Runner imports prevention module | **NOTE** | `run_prevention_simulation.py` imports `PreventionProtocolAdapter`, `domain_childcare`, `ThreatProfile` directly. This is expected for a single-protocol runner but means the runner is not protocol-agnostic |
| Actors contain protocol-adjacent logic | **NOTE** | `actors.py` has `self_induced` flag and `attribution_share` field in the core `Actor` dataclass. These are protocol concepts but are generic enough to not constitute leakage |

---

## 4. Determinism Check

### 4.1 Repeated Runs

| Run | Seed | Zones | Days | Ticks | total_spd_value |
|-----|------|-------|------|-------|-----------------|
| Run 1 | 77777 | 2 | 3 | 48 | 66.002943 |
| Run 2 | 77777 | 2 | 3 | 48 | 66.002943 |

**Subject totals comparison:**
| Subject | Run 1 | Run 2 |
|---------|-------|-------|
| actor-patrol_worker-001 | 24.804969 | 24.804969 |
| actor-optimizer_actor-004 | 35.614144 | 35.614144 |
| actor-weak_worker-002 | 5.58383 | 5.58383 |

**MD5 hash of metrics.json:** Identical across runs.

**Result: PASS — Fully deterministic.**

### 4.2 RNG Centralization

| Check | Status | Evidence |
|-------|--------|----------|
| Custom PRNG used | **PASS** | `rng.py` — xoshiro256** implementation with SHA-256 seeding |
| No `import random` | **PASS** | `grep -rn "import random\|from random" simulation/` returns empty |
| No `time.time` in randomness | **PASS** | `time.time()` is used only for elapsed wall-clock measurement in `run_prevention_simulation.py` L153, L244. Not used for seeding or randomness |
| RNG fork isolation | **PASS** | Each zone, oracle, and actor gets a deterministic fork keyed by label |

---

## 5. Test Coverage

### 5.1 Covered Cases

| Test File | Cases | Protocol Section | Status |
|-----------|-------|-----------------|--------|
| `test_vectors.py` | 8 tests | §5 SPDₖ, §3.6 suppression, §3.3 oracle, §9.1 self-induced, §9.4 coverage | All PASS |
| `test_oracle_consistency.py` | 5 tests | §3.3 regime switching, §9.5 multi-oracle, dropout | All PASS |
| `test_reproducibility.py` | 2 tests | Determinism, seed divergence | All PASS |
| `test_self_induced.py` | 3 tests | §9.1 Tₖ=0, positive honest, §9.3 recurrence decay | All PASS |
| `test_informational.py` | 4 tests | §3.3.2 informational, borderline ε, just-over ε | All PASS |

**Total: 22 tests, 22 passing.**

### 5.2 Missing Tests

| Missing Case | Protocol Section | Severity |
|-------------|-----------------|----------|
| **Temporal alignment violation through full pipeline** | §3.6 | HIGH |
| **Σ Aₖ > 1 detection/rejection** | §6 | CRITICAL |
| **CBFᵢ non-reward isolation** | §9.2, §3.11 | MEDIUM |
| **Integration test: adversarial scenario with self-induced events** | §9.1 integration | MEDIUM |
| **Pattern recurrence through full simulation** | §9.3 integration | LOW |
| **Multi-zone isolation** | §3.1 cross-zone | LOW |
| **Zero TA intensity edge case** | §3.6 edge | LOW |

---

## 6. Config Integrity

### 6.1 Thresholds From Config

| Parameter | Config Key | Default in Code | Notes |
|-----------|-----------|-----------------|-------|
| ε_consistency | `protocol.epsilon_consistency` | 0.15 | From config ✓ |
| Δt_int | `protocol.delta_t_int` | 30.0 | From config ✓ |
| θ_self_induced | `protocol.theta_self_induced` | 0.5 | From config ✓ (but see F-07) |
| recurrence_decay | `protocol.recurrence_decay` | 0.9 | From config ✓ |
| coverage_floor | `protocol.coverage_floor` | 0.1 | From config ✓ |
| Wₖ weights | `domain.threat_weights` | {} | From config ✓ |

### 6.2 Hidden Constants

| Constant | Location | Value | Concern |
|----------|----------|-------|---------|
| Recurrence decay threshold | `protocol_adapter.py` L234 | `count - 3` | Hardcoded "3 occurrences before decay starts". Not configurable |
| Default threat_rate | `events.py` L51 | `0.3` | Default parameter in function — overridden by config in runner |
| SE time lower bound | `run_prevention_simulation.py` L208 | `1.0` | Hardcoded minimum SE delay (1 tick). Not in any config |
| Actor effectiveness multiplier ranges | `actors.py` L88–92 | `0.2–0.6`, `0.8–1.0`, `0.5–0.9` | Per-strategy hardcoded. Not configurable |
| Adversarial suppression factor | `actors.py` L68 | `0.5` | Hardcoded half-effectiveness for self-induced interventions |

### 6.3 Config Snapshot

| Check | Status | Evidence |
|-------|--------|----------|
| Config snapshot saved in outputs | **PASS** | `config.py` L28–31 `save_config_snapshot()`. Verified: `simulation/outputs/smoke/config_snapshot.json` exists with full config |

---

## 7. Output Correctness

| Check | Status | Evidence |
|-------|--------|----------|
| Informational events NOT counted as valid reward | **PASS** | Informational records use `metric_name="SPD_informational"`. Summary counts them as `informational_events: 3`. They do NOT appear in `total_spd_value` (verified: manual sum of SPD records = summary total = 24.300653) |
| SPD aggregation correct | **PASS** | `subject_totals` sums only `SPD_k > 0` contributions. Verified manually |
| Metrics consistent with definitions | **PASS** | Each record contains W_k, S_k, A_k, C_k, T_k, actor_id, risk_channel — all per spec §11 outputs |

---

## 8. Spec Integrity

| Check | Status | Evidence |
|-------|--------|----------|
| Imported protocol file matches frozen spec | **PASS** | `simulation/specs/imports/DKP-1-PREVENTION-001_v1_0.md` — 249 lines, contains all 15 sections of the frozen protocol including Finality clause |
| No divergence between spec and implementation | **PARTIAL** | Divergences found: Σ Aₖ ≤ 1 not enforced (F-01), θ used as binary flag not continuous threshold (F-07), ZKP missing (F-02) |

---

## 9. Vulnerability Assessment

### 9.1 Informational Leakage into Reward

**Risk: LOW**
Informational events are recorded with `metric_name="SPD_informational"` and `SPD_k=0.0`. They are excluded from `total_spd_value` and `subject_totals` by construction (summary sums only `metric_name == "SPD"`; subject contribution only added when `SPD_k > 0`). No leakage observed.

### 9.2 Oracle Inconsistency Handling

**Risk: LOW**
Correctly implemented. Δ_oracle > ε triggers informational downgrade. The informational SPD result carries `informational=True` and `SPD_k=0.0`. No reward path exists for inconsistent oracles.

### 9.3 Temporal Misalignment Exploit

**Risk: MEDIUM**
The protocol adapter correctly rejects temporal violations (`dt > delta_t_int` or `dt ≤ 0`). However, the main simulation loop generates `se_time` within `[ta_time + 1.0, ta_time + delta_t_int]`, making temporal violations unreachable. An external caller using the adapter API would be protected, but the simulation itself never exercises this failure mode. This means the engine cannot discover temporal alignment bugs through simulation runs.

### 9.4 Self-Induced Risk Exploit

**Risk: LOW**
Self-induced flag correctly zeroes Tₖ. The adversarial actor model correctly flags self-induced interventions. However, the θ threshold (`theta_self_induced`) is accepted from config but never compared against a continuous linkage score — the check is binary (`self_induced: bool`). This is a simplification that may need revision for production L8 use.

### 9.5 Adversarial Actor Exploitability

**Risk: MEDIUM**
When `include_adversarial=False` (default), adversarial actors are excluded entirely. When enabled, the self-induced flag correctly prevents reward. However, the adversarial actor still contributes positive suppression even when self-inducing (`suppression_intensity = threat_intensity * effectiveness * 0.5`), and if the self-induced check were bypassed, it would receive SPD credit. The defense is sound but single-layered.

### 9.6 Attribution Over-Counting

**Risk: CRITICAL**
Multiple actors process the same threat event independently, each with `attribution_share=1.0`. No mechanism enforces Σ Aₖ ≤ 1. In the smoke test, 3 actors each claim full attribution for the same events, resulting in total SPD inflation. This directly violates §6.

---

## 10. Extra Validation — Mandatory Manual Cases

### Case 1: Oracle Inconsistency → Must Produce Informational

**Input:** Two oracles — optical: 0.3, thermal: 0.8 (Δ = 0.5 >> ε = 0.15)
**Observed Output:**
- `is_valid: True` (2 independent classes)
- `is_consistent: False`
- `informational: True`
- `delta_oracle: 0.5`
- `SPD_k: 0.0`
- `spd.informational: True`

**Verdict: PASS**

### Case 2: Late SE → Must Produce SPD = 0

**Input:** Valid consistent TA at t=0.0, SE at t=100.0 (>> Δt_int=30.0)
**Observed Output:**
- `SPD_k: 0.0`
- `reason: temporal_invalid`

**Verdict: PASS**

### Case 3: SE ≥ TA → Must Produce SPD = 0

**Input:** TA intensity = 0.5, SE intensity = 0.8 (SE > TA)
**Observed Output:**
- `SPD_k: 0.0`
- `reason: fully_suppressed`

**Verdict: PASS**

---

## 11. Findings Table

| ID | Issue | Severity | Location | Description | Fix |
|----|-------|----------|----------|-------------|-----|
| F-01 | **Σ Aₖ ≤ 1 not enforced** | **CRITICAL** | `actors.py` L42, `run_prevention_simulation.py` L195–212 | Every actor has `attribution_share=1.0`. Multiple actors process the same event independently. No per-event attribution budget is tracked or enforced. Σ Aₖ can exceed 1.0, violating §6. | Implement per-event attribution budget: track remaining allocation, split or cap shares so Σ Aₖ ≤ 1 per event |
| F-02 | **No ZKP interface** | **CRITICAL** | Repository-wide | §8 requires `ZKP(SIₖ, linkage)` provability. No ZKP module, interface, abstract class, or placeholder stub exists anywhere. | Add `simulation/core/privacy.py` with ZKP interface stub and integration point in protocol adapter |
| F-03 | **Hardcoded recurrence threshold** | **HIGH** | `protocol_adapter.py` L234 | The "decay after 3 occurrences" constant is hardcoded (`count - 3`). Not configurable via YAML. Should be a §14 L8 parameter. | Add `recurrence_threshold` to config and PreventionCalibration |
| F-04 | **SE ≥ TA unreachable in runner** | **HIGH** | `run_prevention_simulation.py` L205–207 | `se_intensity = max(0, ta - suppression)` guarantees `se ≤ ta`. The `fully_suppressed` path in `compute_suppression` is unreachable from the main loop. The simulation never exercises this failure mode. | Consider allowing external SE sources or modeling measurement error in SE to make this path reachable |
| F-05 | **Temporal invalidity unreachable in runner** | **HIGH** | `run_prevention_simulation.py` L208 | `se_time = timestamp + rng.uniform_range(1.0, delta_t_int)` always produces valid temporal alignment. The engine never generates temporal violations. | Add configurable probability of temporal-violation events, or model delayed/early SE scenarios |
| F-06 | **Hardcoded SE time lower bound** | **MEDIUM** | `run_prevention_simulation.py` L208 | `1.0` lower bound for SE delay is hardcoded, not in config. | Extract to config parameter: `se_delay_min` |
| F-07 | **θ_self_induced not used as threshold** | **MEDIUM** | `protocol_adapter.py` L89, L226 | Config accepts `theta_self_induced` but the actual check uses `if self_induced: return 0.0` (binary). §9.1 specifies `linkage(subject, TAₖ) > θ` — a continuous comparison. The θ value is stored but never evaluated. | Implement continuous linkage scoring with comparison against θ |
| F-08 | **Actor effectiveness ranges hardcoded** | **MEDIUM** | `actors.py` L88–92 | Strategy-specific effectiveness multiplier ranges (e.g., WEAK: 0.2–0.6) are hardcoded. Not configurable per-domain. | Extract to actor profile config or per-strategy calibration |
| F-09 | **CBFᵢ not modeled** | **MEDIUM** | Repository-wide | §3.11 defines Contextual Baseline Field as audit-only reference. No CBF implementation or placeholder exists. §9.2 baseline isolation cannot be verified. | Add CBF data structure and audit logging |
| F-10 | **No temporal alignment test in integration** | **LOW** | `tests/simulation/` | Temporal alignment is tested at the adapter unit level but not through the full simulation pipeline. Since the runner never generates temporal violations (F-05), the integration path is untested. | Add integration test that forces `se_time > ta_time + delta_t_int` |
| F-11 | **Default parameter values in constructor** | **LOW** | `protocol_adapter.py` L87–91 | Constructor has default values (0.15, 30.0, etc.) that could mask missing config keys. A missing config key would silently use defaults. | Consider making all parameters required (no defaults) to force explicit config |
| F-12 | **No adversarial integration test** | **LOW** | `tests/simulation/` | `include_adversarial` defaults to False. No test runs a full simulation with adversarial actors enabled to verify self-induced events produce Tₖ=0 through the complete pipeline. | Add `test_adversarial_integration.py` with `include_adversarial=True` |

---

## 12. Final Verdict

### **ACCEPT WITH FIXES**

The DKP-L8-SIMULATION-ENGINE correctly implements the core recognition pipeline of DKP-1-PREVENTION-001 v1.0. The SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ formula is exact. Oracle consistency, suppression logic, informational state, self-induced risk nullification, and multi-oracle requirements are all correctly enforced at the adapter level. Determinism is verified bit-exact across repeated runs.

**Required fixes before L8 simulation trust:**

1. **F-01 (CRITICAL):** Implement Σ Aₖ ≤ 1 enforcement per event. Without this, simulation SPD totals are inflated by a factor proportional to responding actor count. All existing simulation outputs must be considered invalid for attribution analysis until fixed.

2. **F-02 (CRITICAL):** Add ZKP interface placeholder. While not functionally required for simulation, the frozen spec mandates this interface. A stub with `NotImplementedError` is acceptable for L8 scope.

**Recommended fixes for simulation fidelity:**

3. **F-03 (HIGH):** Extract recurrence threshold to config.
4. **F-04 / F-05 (HIGH):** Make SE ≥ TA and temporal violation paths reachable in simulation to improve coverage of failure modes.

**All other findings (MEDIUM/LOW) are improvements that do not block simulation use but should be addressed for production readiness.**

---

*End of audit report.*
