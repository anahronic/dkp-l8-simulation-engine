# Audit report — DKP-1-PREVENTION-001 research bench, Phase 3

- **Date:** 2026-10-05, revised for engine 2.1.0 the same day.
- **Engine:** 2.1.0 (see CHANGELOG.md). Earlier: 2.0.0 = tag `v2.0.0`, v1 = tag `v1.0-a9d3cdf`.
- **Reproduce:** `python -m simulation.phase3_report` writes `phase3_results.json`. Every variant there
  carries its full resolved input, `input_id` and `result_id`; the document is sealed by
  `content_sha256`. Machine-specific data go to `phase3_provenance.json`.
- **Status:** results describe a synthetic childcare scenario under the hypotheses listed
  in each run manifest. They are not statements about a real system, not an admission
  under DKP-8-SIMULATION-001 §8 and not proposals to change the protocol.

---

## 1. Why Phase 2 is superseded

Phase 2 (March 2026, v1) reported verdicts for ten adversarial scenarios. A code-level
check on 2026-10-04/05 showed that several of them did not test what their names said.

| Phase 2 | What v1 actually did | Now |
|---|---|---|
| S1 risk farming: "MITIGATED, finite accumulation (§9.3 guarantees)" | No actor created threats; honest actors at activation rate 0.95. The bound Σ T ≤ 12 holds for the bench rule ρ^max(0, n−3) on one fixed key, not for PREVENTION §9.3, which states no rate. | Unverified in v1; re-tested as S1 |
| S2 TA inflation: "PASS, inflation does not amplify reward" | Only the true intensity range was raised. SE was computed as TA·(1 − eff), so S = eff by construction. | Unverified in v1; re-tested as S2 |
| S6 early prevention: "dominant strategy is to delay" | The runner never produced an action before TA; the result came from a direct call with `se_time = −1`. No harm or cost model. | Claim withdrawn; S6 measures the effect only |
| S7 oracle degradation | `bias_range` was never passed to the sensors. | Unverified in v1; re-tested as S7 |
| S10 / D-01: "discontinuity at SE = TA" | S is continuous there (a kink, not a jump). | Corrected (S10) |
| S5: "Σ A ≤ 1 holds" | True, but shares went by list order, and an ineligible subject could consume the budget. | Fixed; S5 compares rules |

## 2. Correction of the 2.0.0 reading of S1 (review GPT 7, D1)

The 2.0.0 report said that the recurrence rule "does not limit farming" in S1, citing an
unchanged share of honest interventions with Tₖ < 1. That share does not measure the effect
of decay on income. A control run that changes only `decay` (0.9 → 1.0) on the same world
showed, in 2.0.0: −64.2 % for the creator's income on its own threats, −81.9 % for everyone
else. The corrected reading, re-measured for 2.1.0 below: decay lowers the income of the
creator *and* of the other subjects; it is not selective; detection with probability 1
removes the creator's income; fairness and a general protection against farming are not
established by these numbers.

## 3. Design

All scenarios are overlays on `configs/prevention_childcare_v0_2.yaml` (schema 3): one zone,
10 days, tick 3600 s, Δt_int 30 s, `ambiguity_zero`, `ttl_reference: signal`, recurrence
history `as_of_decision`. Each states what is varied independently and what the attacker
controls. The adapter receives observations only; truth stays in each record's `truth`
block. Random draws are addressed by purpose (H-RNG), so a variant that changes one
parameter keeps every unrelated draw; S12 checks this directly.

## 4. Results (engine 2.1.0)

### S1 — risk farming (seed 3001)

An adversarial subject creates threats (rate 0.1 per channel per hour; 123 threats) and
suppresses them. The evaluator sees an observed linkage score.

| Variant | SPD to creator on own threats | SPD to other subjects | Ambiguity | Honest Tₖ < 1 |
|---|---:|---:|---:|---:|
| detection 1.0 | 0.000 | 8.596 | 0.635 | 0.926 |
| detection 0.8 | 0.000 | 8.469 | 0.645 | 0.926 |
| detection 0.0 | 0.128 | 4.355 | 0.737 | 0.926 |
| detection 0.0, decay 1.0 (control) | 0.314 | 11.516 | 0.737 | 0 |
| detection 0.0, history retrospective | 0.128 | 4.355 | 0.737 | 0.926 |
| detection 0.0, recurrence per zone, 1-day window | 0.297 | 9.017 | 0.737 | 0.797 |

Reading. On this world decay (0.9 against 1.0) lowered the creator's income by 59.1 % and
everyone else's by 62.2 %. Undetected farming halves the other subjects' reward
(8.596 → 4.355), mainly through ambiguity on the farmed events. Detection with probability
1 removes the creator's income. The retrospective and as-of-decision histories coincide
here. Nothing here establishes fairness or a general protection against farming.

### S2 — TA inflation (seed 3002)

| Variant | Total SPD | Change | Mean S | Informational events |
|---|---:|---:|---:|---:|
| baseline | 11.872 | — | 0.726 | 59 |
| (a) true intensity raised to [0.8, 1.0] | 13.057 | +10.0 % | 0.792 | 59 |
| (b) +0.1 on TA readings of 2 of 4 classes | 11.055 | −6.9 % | 0.749 | 173 |
| (b) +0.1 on TA readings of all 4 classes | 13.417 | +13.0 % | 0.781 | 59 |
| (c) +0.1 on TA and SE readings, all classes | 9.946 | −16.2 % | 0.594 | 59 |

Reading. (1) With absolute sensor noise, min-aggregated TA is biased down and
max-aggregated SE up, more so at low intensity, so even honest higher intensities raise S.
(2) A TA-only bias on all classes raised reward by 13 % and is invisible to Δ_oracle.
(3) The same bias on 2 of 4 classes was mostly caught (informational events ×2.9).
Whether an attacker can control the stated classes is outside the bench.

### S3 — joint suppression (seed 3003)

Max Σ A per event = 1.0. Claims 1.0: ambiguity 0.569, total SPD 9.806. Claims 0.4:
ambiguity 0.092, total SPD 28.846. The protocol does not say how claims are established.

### S4 — window Δt_int (seed 3004)

| Δt_int (s) | 10 | 30 | 60 | 120 | 600 |
|---|---:|---:|---:|---:|---:|
| Total SPD | 29.400 | 11.630 | 2.942 | 2.089 | 2.089 |
| Outside window (records) | 510 | 212 | 109 | 0 | 0 |
| Ambiguity fraction | 0.059 | 0.553 | 0.793 | 0.982 | 0.982 |

Under `ambiguity_zero` a wider window admits more subjects per event and more ambiguity;
Δt_int and the attribution rule cannot be calibrated separately.

### S5 — attribution rules (seed 3005)

| Rule | Total SPD | `actor_order` reversed |
|---|---:|---:|
| ambiguity_zero | 13.417 | 13.417 |
| proportional | 49.259 | 49.259 |
| list_order | 51.401 | 42.622 |

Only `list_order` depends on the declared order.

### S6 — early prevention (seed 3006)

Slow sensors (measurement 2–6 s, arrival 5–15 s), a fast subject (0–3 s).

| t₀ basis | Interventions before t₀ | Temporal-window zeros | TA non-positive | No measured reduction | Total SPD |
|---|---:|---:|---:|---:|---:|
| measurement | 217 | 42 | 86 | 217 | 1.613 |
| registration | 344 | 140 | 86 | 175 | 1.324 |

An intervention before the sensors sample the threat lowers the measured TA, so early
prevention is recognized little or not at all (consistent with PREVENTION §1). No harm or
cost model; no claim about dominant strategies. Taking t₀ from arrival instead of
measurement multiplies temporal-window failures by 3.3: an artefact of the time basis.

### S7 — oracle degradation (seed 3007)

| Variant | Total SPD | Informational events | INVALID records |
|---|---:|---:|---:|
| clean | 9.798 | 59 | 0 |
| bias ±0.15 | 6.571 | 200 | 0 |
| bias, noise 0.25, dropout 0.2 | 0.751 | 289 | 34 |
| arrival delay up to 20 s (lidar TTL 5 s) | 0.000 | 1 | 830 |

### S8 — oracle noise (seed 3008)

σ 0.02: total SPD 15.591, no informational events. σ 0.25: 0.253, 303 informational events.

### S9 — linkage threshold; S10 — SE/TA continuity

Observed linkage 0.5 → SPD 0.75; 0.500001 → 0 (a step at θ). SE/TA 0.99 → S 0.01,
0.999 → 0.001, 0.9999 → 0.0001, 1.0 → 0 (continuous).

### S11 — TTL reference (seed 3011; review GPT 7 Q1, GPT 8 §3–§4)

| Variant | Total SPD | POSITIVE | INVALID (TA stale at decision) | Ambiguity |
|---|---:|---:|---:|---:|
| signal (default TTLs: optical/thermal 10, lidar 5, access 30 s) | 11.744 | 95 | 0 | 0.558 |
| decision | 8.920 | 30 | 590 | 0.200 |
| signal, all TTL 5 s | 11.744 | 95 | 0 | 0.558 |
| decision, all TTL 5 s | 1.695 | 4 | 670 | 0.000 |

Reading. Under `signal` a TA fresh at its own registration is used as a measurement of the
state at t₀. Under `decision` TTL is re-applied at the decision instant (the later of the
two signals' original availability times) and TA, SE, consistency, coverage, times, window
and S are recomputed. With these TTLs most decisions come later than the short TTLs allow.
TTL shorter than Δt_int does not make recognition impossible: an intervention completed
quickly is still recognized (tested). Neither mode is an accepted reading of ORACLE; the
corpus does not relate TTL to Δt_int.

### S12 — channel isolation (seed 3012; review item U5)

Tripling the activation rate of `unauthorized_adult_proximity`: all 643 records of the other
channels are identical between the two runs (threats, subjects' actions, sensor draws,
statuses, SPD), apart from the variant label in `scope_ref`.

### Main scenario (3 zones × 30 days, seed 42)

7238 records: POSITIVE 723, ZERO_MERIT 1954 (1844 outside the window, 91 temporal,
19 no measured reduction), INFORMATIONAL 1034, NO_ATTRIBUTION 3527 (ambiguity 0.569).
Total SPD 34.107. 96.2 % of recognized honest interventions had Tₖ < 1 under the v1 rule.

## 5. Questions these results raise for the protocol text

These are questions for the author and for UPGRADE proposals, not changes made by the bench.

1. **§6, §12 — several subjects on one threat.** With `ambiguity_zero`, joint prevention is
   mostly unrewarded; other rules depend on claims the protocol does not define.
2. **§3.6, §14 — Δt_int and attribution interact** (S4).
3. **§9.3 — whose pattern counts.** The v1 rule decays routine honest work; decay is not
   selective against farming; detection decides (S1).
4. **§3.3 — a uniform bias is invisible to Δ_oracle** (S2).
5. **§3.6 — which time is t₀** (S6).
6. **§3.5 — how SE readings aggregate** (H-SE-2).
7. **ORACLE §9 and PREVENTION §3.6 — at which instant TTL applies to the TA/SE pair** (S11).

## 6. Not verified

Independent reproduction by other executors; ZKP verification (placeholder only); causal
inference (claims and linkage are scenario inputs); any domain other than this synthetic
one; any operational use of the outputs.
