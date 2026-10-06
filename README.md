# DKP L8 research bench for DKP-1-PREVENTION-001

A deterministic simulation bench for **one** protocol: DKP-1-PREVENTION-001
(Preventive Impact Attribution). It runs the protocol's recognition pipeline on a
**synthetic** childcare-perimeter scenario and reports what the protocol text, plus
the explicitly declared hypotheses below, produce.

What it is not:

- not an admission under DKP-8-SIMULATION-001 §8 (no independent reproduction by
  other nodes, no F1–F4 classification, no Calibration Bundle);
- not an implementation of the S1 decision-origin procedure (it selects nothing);
- not a model of any real facility; outputs are not operational outputs
  (EPISTEMIC-BOUNDARIES §5.x) and carry `operational_use: false`;
- not protocol-agnostic. `core/` holds pieces that other protocol modules could
  reuse (seeded RNG with forks, platform-independent math, config schema machinery,
  manifest, time base, oracle model), but events, actors and reporting are shaped
  around threats and their suppression.

Version 2.1.1 (2026-10-06) is a patch after the independent review of 2.1.0 (tag
`v2.1.0`): it rejects ambiguous names and detects block-versus-field conflicts between
candidates; all results of the shipped scenarios are unchanged. 2.1.0 was a technical
release after the review of 2.0.0 (tag `v2.0.0`), which reworked v1 (tag `v1.0-a9d3cdf`). See
[CHANGELOG.md](CHANGELOG.md) and
[AUDIT_REPORT_PREVENTION_L8_PHASE_3.md](AUDIT_REPORT_PREVENTION_L8_PHASE_3.md).

## Pipeline

```
truth (never shown to the adapter)        observations (all the adapter sees)
───────────────────────────────────       ─────────────────────────────────────────
threat: event time, intensity, creator ─► oracle readings: value, measured_at, received_at
subjects: response time, effectiveness ─► intervention times, share claims
self-induced or not                    ─► observed linkage score (detection model)

adapter (PREVENTION):
  TA  = TTL filter (ORACLE §9) → ≥ 2 classes (§9.5) → Δ_oracle ≤ ε ? min : informational (§3.3)
  SI  = interventions with tᵢ ≤ t₀ + Δt_int                                   [H-SI-1]
  SE  = readings after the last SI → TTL → ≥ 2 classes → aggregation          [H-SE-1..3]
  ttl_reference=decision: TTL re-applied at the decision, everything recomputed [H-TTL-2]
  0 < t₁ − t₀ ≤ Δt_int  (seconds)                                             (§3.6)
  Sₖ  = clamp(0, 1, (TA − SE) / TA)                                           (§3.6)
  Tₖ  = 0 if linkage > θ (§9.1), else recurrence decay (second pass)          [H-T-1..3]
  eligibility first, then Aₖ with Σ Aₖ ≤ 1                                    (§6, §12) [H-A-2]
  SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ                                              (§5)
```

Every responding subject gets one record with a status — `POSITIVE`, `ZERO_MERIT`,
`INFORMATIONAL`, `INVALID`, `NO_ATTRIBUTION` (IDENTITY §4.1) — a reason for every
non-positive outcome, and EPISTEMIC-BOUNDARIES §5 metadata.

## Hypotheses

The protocol leaves several functions open. The bench names each choice, selects it
in the config and copies it into every run manifest. None is a normative reading.
Full text: [`simulation/modules/prevention/hypotheses.py`](simulation/modules/prevention/hypotheses.py).

| ID | Choice | Config |
|---|---|---|
| H-TIME-1 | clock in seconds; ticks partition the civil day; days as DTI-Day | `time.*` |
| H-TIME-2 | t₀/t₁ from earliest measurement or from registration | `protocol.ta_time_basis` |
| H-TIME-3 | event, measurement and arrival times differ | `oracles.*_delay_seconds` |
| H-TTL | TTL per oracle class (scenario values) | `oracles.ttl_seconds` |
| H-TTL-2 | TTL applied per signal (`signal`) or re-applied at the decision (`decision`) | `protocol.ttl_reference` |
| H-SE-1..3 | SE = measured residual; aggregation; needs 2 classes | `protocol.se_aggregation` |
| H-SI-1 | which interventions count as SI | `protocol.delta_t_int_seconds` |
| H-SUP | interventions act jointly on the true intensity | actor effectiveness |
| H-C | Cₖ from class coverage (or v1 mean confidence) | `protocol.confidence_rule` |
| H-A-1 | share claims are scenario inputs; no causal inference | actor `attribution_claim` |
| H-A-2 | Σ claims > 1 ⇒ ambiguity ⇒ SPD = 0 (§12), or comparison rules | `protocol.attribution_rule` |
| H-T-1/2 | recurrence key, threshold, decay, window; one run only | `protocol.recurrence.*` |
| H-T-3 | clock t₀; previous = other events with t₀−W ≤ t₀' < t₀; known at decision or retrospective | `protocol.recurrence.history` |
| H-RNG | every random draw addressed by purpose, never by a shared counter | `simulation.seed` |
| H-L | observed linkage score model | `oracles.linkage_detection.*` |
| H-TA0, H-NUM, H-CBF | TA ≤ 0 invalid; binary64 full precision; CBF estimator | — |

## Running

```bash
pip install -r requirements.txt

python -m simulation.run_prevention_simulation --smoke
python -m simulation.run_prevention_simulation --config simulation/configs/prevention_childcare_v0_2.yaml
python -m simulation.phase3_report                      # adversarial scenarios S1–S10
python -m simulation.compare_candidates --spec simulation/configs/comparison/example.yaml
python -m pytest -q tests/
```

Configs use schema version 3: every key is required, unknown keys are rejected, numbers
must be finite, and channel, actor and oracle-class names are identifiers
(`[A-Za-z0-9][A-Za-z0-9_-]*`): they become parts of event ids and random-stream
addresses, so the separators `:` and `/` cannot occur in them. Mapping order carries no meaning (the engine iterates sorted keys); the one
order that matters, for `attribution_rule: list_order`, is the explicit list
`domain.actor_order`. A run replayed from its `config_resolved.json`
(`--config .../config_resolved.json`) reproduces both ids. Schema 2 configs run with tag
`v2.0.0`.

## Outputs and identity

| File | Role |
|---|---|
| `metrics.jsonl`, `metrics.csv`, `cbf_baselines.json`, `summary.json` | result core → `result_id` |
| `config_resolved.json` | the configuration without the output path |
| `run_manifest.json` | `input_id` (config digest, seed, engine code digest, actual spec digests), `result_id`, provenance, hypotheses, unverified items |
| `summary.txt`, `run_log.json` | for humans / diagnostics (elapsed time, paths); never digested |

Two executors that obtain the same `result_id` from the same `input_id` have
reproduced the computation. The manifest is built from the exact bytes of the result
core, so a run without writing files (`write=False`, used by Phase 3 and the comparison)
has the same ids. A run on altered spec snapshots is refused before anything is computed.
`phase3_results.json` and `comparison.json` store the full input and both ids of every
run, name the engine code and spec digests in `package`, and are sealed by
`content_sha256` = SHA-256 of their canonical JSON without that field; machine data and
timings go to separate `*_provenance.json` files. Files are written with LF and canonical JSON; Gaussian
noise and decay powers use [`core/detmath.py`](simulation/core/detmath.py) instead of
the C library, because v2's first runs showed last-bit differences between Windows
and Linux.

## Verified environments

The smoke `result_id` is pinned in `tests/simulation/test_golden.py`.

What each piece of evidence covers:

- **CI** (`.github/workflows/tests.yml`): on each of 9 combinations (ubuntu-latest,
  windows-latest, macos-latest × CPython 3.10 / 3.12 / 3.13) it runs the test suite —
  which includes the pinned smoke `result_id` — and one smoke run. It does not run the
  30-day main scenario, Phase 3 or the comparison.
- **Main scenario, Phase 3, comparison**: reproduced locally on the two environments
  below, and independently by a reviewer on Linux (CPython 3.12.14, glibc 2.39) for
  2.1.0, with the same `result_id` values and report seals.

| Environment | Tests | Smoke / main result_id |
|---|---|---|
| Windows 10 Pro 19045, CPython 3.12.10 | pass (2.1.1) | pinned / same as 2.1.0 |
| WSL2 Ubuntu 22.04, CPython 3.10.12, glibc 2.35 | pass (2.1.1) | pinned / same as 2.1.0 |
| GitHub Actions, 9 combinations | see the `tests` workflow for the release commit; 2.1.0: 9 of 9 (run 37377377441) | pinned (golden test) |

Other environments are unverified.

## Not verified

- independent reproduction by other executors (SIMULATION §8);
- zero-knowledge proof verification (§8): `PlaceholderZKPProvider` only, recorded as unverified;
- causal inference: attribution claims and linkage observations are scenario inputs;
- any domain other than the synthetic childcare scenario;
- any operational use of the outputs.

## Specifications

`simulation/specs/imports/` holds byte copies of the canonical texts (anahronic/World
`aad3e86`, release 2026-10-04) with digests in `MANIFEST.json`; each run re-verifies
them. Changes to PREVENTION itself go through DKP-4-UPGRADE-001, not through this bench.

## Rollback

2.1.0 is tag `v2.1.0` (commit `e349e63`); 2.0.0 is tag `v2.0.0` (commit `f3c48e4`);
v1 is tag `v1.0-a9d3cdf`.
