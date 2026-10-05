# Audit report — DKP-1-PREVENTION-001 research bench, Phase 3

- **Date:** 2026-10-05
- **Engine:** v2.0.0 (see CHANGELOG.md). v1 = commit `a9d3cdf`, tag `v1.0-a9d3cdf`.
- **Reproduce:** `python -m simulation.phase3_report` writes `phase3_results.json`
  with the config digest and seed of every run. The main scenario:
  `python -m simulation.run_prevention_simulation --config simulation/configs/prevention_childcare_v0_2.yaml`.
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
| S2 TA inflation: "PASS, inflation does not amplify reward" | Only the true intensity range was raised. SE was computed as TA·(1 − eff), so S = eff by construction; the test could not fail. | Unverified in v1; re-tested as S2 |
| S6 early prevention: "dominant strategy is to delay" | The runner never produced an action before TA; the result came from a direct call with `se_time = −1`. No harm or cost model. | Claim withdrawn; S6 measures the effect only |
| S7 oracle degradation | `bias_range` was never passed to the sensors. | Unverified in v1; re-tested as S7 |
| S10 / D-01: "discontinuity at SE = TA" | S = clamp(0, 1, 1 − SE/TA) is continuous there; there is a kink, not a jump. The label `fully_suppressed` meant the opposite (no measured reduction). | Corrected (S10) |
| S5: "Σ A ≤ 1 holds" | True, but the share went to the first subject in list order, and an ineligible subject could consume the budget. | Fixed; S5 compares rules |

Defects that affected every v1 number: the Δt_int window never bound (the SE time was
drawn inside it); subject ids merged across zones; records were rounded to 6 digits.

## 2. Design of Phase 3

All scenarios are overlays on `configs/prevention_childcare_v0_2.yaml`: one zone, 10 days,
tick 3600 s, Δt_int 30 s, default rule `ambiguity_zero`. Each states what is varied
independently and what the attacker controls. The adapter receives observations only;
truth is kept in each record's `truth` block for evaluation.

## 3. Results

### S1 — risk farming (seed 3001)

An adversarial subject creates threats (rate 0.1 per channel per hour; 154 threats) and
suppresses them. The evaluator sees an observed linkage score; detection probability varies.

| Variant | SPD to creator on own threats | SPD to other subjects | Ambiguity | Honest Tₖ < 1 |
|---|---:|---:|---:|---:|
| detection 1.0 | 0.000 | 8.218 | 0.611 | 0.930 |
| detection 0.8 | 0.005 | 7.205 | 0.629 | 0.930 |
| detection 0.0 | 0.797 | 2.466 | 0.729 | 0.930 |
| detection 0.0, recurrence per zone, 1-day window | 1.647 | 9.933 | 0.729 | 0.846 |

Reading. The farmer's own gain stays small here because other subjects also respond to its
threats and shared events end in ambiguity. Undetected farming still cuts the other
subjects' reward by 70 % (8.218 → 2.466), through ambiguity on the farmed events. Detection
decides the outcome; the recurrence rule does not limit farming in this scenario (the same
0.930 in all detection variants), and a daily window raises both the farmer's and the others'
reward.

### S2 — TA inflation (seed 3002)

| Variant | Total SPD | Mean S | Mean TA (positive) | Informational events |
|---|---:|---:|---:|---:|
| baseline | 11.889 | 0.689 | 0.519 | 41 |
| (a) true intensity raised to [0.8, 1.0] | 13.240 | 0.775 | 0.864 | 41 |
| (b) +0.1 on TA readings of 2 of 4 classes | 10.247 | 0.728 | 0.552 | 179 |
| (b) +0.1 on TA readings of all 4 classes | 13.531 | 0.754 | 0.610 | 41 |
| (c) +0.1 on TA and SE readings, all classes | 10.084 | 0.560 | 0.619 | 41 |

Reading. (1) "S is a ratio, so inflation cancels" holds only without measurement noise:
with absolute sensor noise, min-aggregated TA is biased down and max-aggregated SE up,
and the effect is larger at low intensity, so even honest higher intensities raise S.
(2) A TA-only bias on all classes raised reward by 13.8 % and was not caught by the
consistency check, because a uniform shift leaves Δ_oracle unchanged. (3) The same bias
on 2 of 4 classes was mostly caught (informational events ×4.4). Whether an attacker
can control the stated sensor classes is outside the bench.

### S3 — joint suppression (seed 3003)

One Sₖ per event, shares among eligible subjects. Max Σ A per event = 1.0 in both runs.
With claims 1.0 the ambiguity fraction is 0.524 and total SPD 10.608; with claims 0.4 it
is 0.070 and 30.511. Under `ambiguity_zero` the reward depends strongly on the claims,
and the protocol does not say how claims are established.

### S4 — window Δt_int (seed 3004)

| Δt_int (s) | 10 | 30 | 60 | 120 | 600 |
|---|---:|---:|---:|---:|---:|
| Total SPD | 29.495 | 10.478 | 2.140 | 1.969 | 1.969 |
| Outside window (records) | 572 | 210 | 86 | 0 | 0 |
| Ambiguity fraction | 0.043 | 0.576 | 0.839 | 0.962 | 0.966 |

Reading. A wider window admits more subjects per event and therefore more ambiguity, so
under `ambiguity_zero` reward falls as the window widens. Δt_int (§14) and the attribution
rule cannot be calibrated separately.

### S5 — attribution rules (seed 3005)

| Rule | Total SPD | Actor order reversed |
|---|---:|---:|
| ambiguity_zero | 8.879 | 8.879 |
| proportional | 48.628 | 48.628 |
| list_order (v1) | 50.917 | 42.706 |

Only `list_order` depends on the order of the subject list.

### S6 — early prevention (seed 3006)

Slow sensors (measurement 2–6 s, arrival 5–15 s) and a fast subject (0–3 s).

| t₀ basis | Interventions before t₀ | Temporal-window zeros | TA non-positive (records) | No measured reduction | Total SPD |
|---|---:|---:|---:|---:|---:|
| measurement | 229 | 40 | 65 | 251 | 2.329 |
| registration (arrival) | 353 | 114 | 71 | 206 | 2.776 |

Reading. An intervention before the sensors sample the threat lowers the measured TA, so
early prevention is recognized little or not at all — consistent with PREVENTION §1
("not through absence of realized harm"). The bench has no harm or cost model and makes no
claim about dominant strategies. Taking t₀ from record arrival instead of measurement
multiplies temporal-window failures by 2.85: an artefact of the time basis, not of the
subjects' behaviour.

### S7 — oracle degradation (seed 3007)

| Variant | Total SPD | Informational events | Invalid events | Stale TA (records) |
|---|---:|---:|---:|---:|
| clean | 9.807 | 55 | 0 | 0 |
| bias ±0.15 (now applied) | 7.989 | 156 | 0 | 0 |
| bias, noise 0.25, dropout 0.2 | 1.098 | 280 | 12 | 0 |
| arrival delay up to 20 s (lidar TTL 5 s) | 0.177 | 3 | 306 | 760 |

Stale data now has weight zero (ORACLE §9) and ends in INVALID; it is never smoothed.

### S8 — oracle noise (seed 3008)

Noise σ 0.02: total SPD 14.642, no informational events. σ 0.25: 0.388, 316 of 324
events informational.

### S9 — linkage threshold (adapter level)

Observed linkage 0.45, 0.49, 0.5 → SPD 0.75; 0.500001, 0.51, 0.55 → 0. A real step at θ
(strict ">").

### S10 — SE/TA continuity (adapter level)

SE/TA 0.99 → S 0.01; 0.999 → 0.001; 0.9999 → 0.0001; 1.0 → 0. Continuous.

### Main scenario (3 zones × 30 days, seed 42)

7034 records: POSITIVE 743, ZERO_MERIT 1867 (1781 outside the window, 78 temporal, 8 no
measured reduction), INFORMATIONAL 1027, NO_ATTRIBUTION 3397 (ambiguity fraction 0.566).
Total SPD 31.196. 96.1 % of recognized interventions had Tₖ < 1 under the v1 recurrence rule.

## 4. Questions these results raise for the protocol text

These are questions for the author and for UPGRADE proposals, not changes made by the bench.

1. **§6, §12 — several subjects on one threat.** With `ambiguity_zero`, joint prevention
   is mostly unrewarded; with other rules, the outcome depends on claims the protocol does
   not define. An attribution rule is needed (audit item S2).
2. **§3.6, §14 — Δt_int and attribution interact** (S4).
3. **§9.3 — whose pattern counts.** The v1 rule decays routine honest work; detection, not
   decay, limited farming in S1.
4. **§3.3 — a uniform bias is invisible to Δ_oracle** (S2). Independent calibration of
   sensors belongs to ORACLE.
5. **§3.6 — which time is t₀** (measurement or registration) must be fixed (S6).
6. **§3.5 — how SE readings aggregate** is not defined (H-SE-2).

## 5. Not verified

Independent reproduction by other executors; ZKP verification (placeholder only); causal
inference (claims and linkage are scenario inputs); any domain other than this synthetic
one; any operational use of the outputs.
