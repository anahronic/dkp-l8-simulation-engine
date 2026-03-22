"""
Test: Adversarial Incentive Audit — DKP-1-PREVENTION-001 v1.0 Phase 2.

Validates 10 adversarial scenarios probing rational-exploit vectors.
All tests use fixed seeds; outputs are deterministic.

Each test class maps to one scenario.  Invariant constants are imported
from adversarial_scenarios (audit-defined thresholds) and the tests assert
protocol-level guarantees.  Where a discontinuity or structural risk is
detected, the test *documents* it (assertion proves detection) instead of
demanding the system be free of the phenomenon.
"""

from __future__ import annotations

import json
import os
import statistics

import pytest

from simulation.run_prevention_simulation import run_simulation
from simulation.core.metrics_adversarial import (
    compute_adversarial_metrics,
    temporal_spd_profile,
    linkage_spd_sweep,
    se_ta_boundary_sweep,
)
from simulation.modules.prevention.adversarial_scenarios import (
    risk_farming_config,
    ta_inflation_config,
    partial_suppression_config,
    timing_arbitrage_config,
    attribution_split_config,
    early_prevention_config,
    oracle_degradation_config,
    oracle_oscillation_stable_config,
    oracle_oscillation_noisy_config,
    linkage_sweep_config,
    boundary_se_ta_config,
    SPD_GROWTH_RATE_THRESHOLD,
    ORACLE_MIN_SPD,
)
from simulation.modules.prevention.protocol_adapter import (
    PreventionProtocolAdapter,
    ThreatActivation,
)
from simulation.core.oracles import OracleReading


# ── Shared helpers ──────────────────────────────────────────────────────

def _load_records(output_dir: str):
    with open(os.path.join(output_dir, "metrics.json")) as f:
        return json.load(f)


def _spd_records(records):
    return [r for r in records if r["metric_name"] == "SPD"]


def _make_consistent_ta(intensity: float = 0.8) -> ThreatActivation:
    """Return a valid, consistent ThreatActivation for direct adapter tests."""
    readings = [
        OracleReading("o1", "optical", intensity + 0.05, 0.9, 0.0),
        OracleReading("o2", "thermal", intensity - 0.05, 0.9, 0.0),
    ]
    return ThreatActivation(
        event_id=1,
        risk_channel="intrusion",
        timestamp=0.0,
        intensity=intensity - 0.05,          # conservative: min(readings)
        oracle_readings=readings,
        oracle_classes_used={"optical", "thermal"},
        is_valid=True,
        is_consistent=True,
        delta_oracle=0.10,
        informational=False,
    )


def _fresh_adapter(**overrides) -> PreventionProtocolAdapter:
    defaults = dict(
        epsilon_consistency=0.15,
        delta_t_int=30.0,
        theta_self_induced=0.5,
        recurrence_decay=0.9,
        coverage_floor=0.1,
        recurrence_threshold=3,
    )
    defaults.update(overrides)
    return PreventionProtocolAdapter(**defaults)


# ══════════════════════════════════════════════════════════════════════
# Scenario 1 — Risk Farming
# ══════════════════════════════════════════════════════════════════════

class TestRiskFarming:
    """
    INVARIANT: SPD per event must decrease over time as recurrence decay
    (§9.3) degrades T_k toward 0 across repeated cycles.
    """

    @pytest.fixture(scope="class")
    def run_result(self):
        cfg = risk_farming_config(seed=1001, num_days=30)
        summary = run_simulation(cfg)
        records = _load_records("/tmp/dkp-l8-risk-farming")
        return summary, records

    def test_total_spd_is_finite_and_positive(self, run_result):
        """Some prevention is rewarded even in high-frequency scenario."""
        summary, _ = run_result
        assert summary["total_spd_value"] > 0, "Expected genuine prevention to earn SPD"
        assert summary["total_spd_value"] < float("inf")

    def test_recurrence_decay_observable(self, run_result):
        """
        Mean SPD in the last time-bucket must be strictly less than the first.
        Proves §9.3 recurrence decay is active and drives reward toward zero.
        """
        _, records = run_result
        buckets = temporal_spd_profile(records, num_buckets=4)
        first_bucket_mean = buckets[0]
        last_bucket_mean  = buckets[3]

        # First bucket should have higher mean SPD than last
        # (T_k ≈ 1.0 early → T_k ≈ 0 late)
        assert last_bucket_mean < first_bucket_mean, (
            f"Expected recurrence decay: last bucket mean "
            f"({last_bucket_mean:.6f}) should be < first ({first_bucket_mean:.6f})"
        )

    def test_spd_growth_rate_below_threshold(self, run_result):
        """
        Total SPD in second half ≤ SPD_GROWTH_RATE_THRESHOLD × first half.
        Must not grow; must stay bounded or decrease.
        """
        _, records = run_result
        spd_recs = _spd_records(records)
        if not spd_recs:
            pytest.skip("No SPD records")

        timestamps = [r["timestamp"] for r in spd_recs]
        midpoint = (min(timestamps) + max(timestamps)) / 2.0

        first_half = sum(r["value"] for r in spd_recs if r["timestamp"] <= midpoint)
        second_half = sum(r["value"] for r in spd_recs if r["timestamp"] > midpoint)

        if first_half == 0.0:
            assert second_half == 0.0
            return

        growth_rate = second_half / first_half
        assert growth_rate <= SPD_GROWTH_RATE_THRESHOLD, (
            f"SPD growth rate {growth_rate:.4f} exceeds threshold "
            f"{SPD_GROWTH_RATE_THRESHOLD}. "
            f"Risk farming exploit: recurrence decay may be insufficient."
        )


# ══════════════════════════════════════════════════════════════════════
# Scenario 2 — TA Inflation
# ══════════════════════════════════════════════════════════════════════

class TestTAInflation:
    """
    INVARIANT: S_k = clamp(0,1,(TA-SE)/TA) — inflation does not bypass [0,1].
    High TA with proportional SE keeps S_k stable; SPD cannot grow unboundedly.
    """

    @pytest.fixture(scope="class")
    def run_result(self):
        cfg = ta_inflation_config(seed=1002, intensity_lo=0.8, intensity_hi=1.0)
        summary = run_simulation(cfg)
        records = _load_records("/tmp/dkp-l8-ta-inflation")
        return summary, records

    def test_s_k_always_in_unit_interval(self, run_result):
        """All S_k values must be in [0.0, 1.0] — §3.6 clamp invariant."""
        _, records = run_result
        bad = [
            (r["event_id"], r["details"].get("S_k"))
            for r in _spd_records(records)
            if not (0.0 <= r["details"].get("S_k", 0.0) <= 1.0 + 1e-9)
        ]
        assert not bad, f"S_k out of [0,1]: {bad[:5]}"

    def test_inflation_does_not_produce_negative_spd(self, run_result):
        """No negative SPD under inflated TA — covers all detail fields too."""
        _, records = run_result
        for r in _spd_records(records):
            assert r["value"] >= 0.0, f"Negative SPD detected: {r}"
            for key in ("W_k", "S_k", "A_k", "C_k", "T_k"):
                v = r["details"].get(key, 0.0)
                assert v >= 0.0, f"Negative {key}={v} in record {r['event_id']}"

    def test_spd_bounded_by_threat_weight(self, run_result):
        """
        SPD_k ≤ W_k always (all other factors ≤ 1).
        Inflating TA cannot push SPD above the channel weight ceiling.
        """
        _, records = run_result
        for r in _spd_records(records):
            d = r["details"]
            W_k = d.get("W_k", 0.0)
            assert r["value"] <= W_k + 1e-9, (
                f"SPD_k={r['value']} > W_k={W_k} (should be impossible)"
            )


# ══════════════════════════════════════════════════════════════════════
# Scenario 3 — Partial Suppression Loop
# ══════════════════════════════════════════════════════════════════════

class TestPartialSuppression:
    """
    Tests that the runner's per-event attribution budget (F-01) prevents
    over-attribution, AND documents the raw-adapter structural risk.
    """

    @pytest.fixture(scope="class")
    def run_result(self):
        cfg = partial_suppression_config(seed=1003)
        summary = run_simulation(cfg)
        records = _load_records("/tmp/dkp-l8-partial-suppression")
        return summary, records

    def test_sum_a_k_per_event_never_exceeds_one(self, run_result):
        """
        Per-event budget (F-01): sum of A_k across all actors for one threat
        event must not exceed 1.0.
        """
        _, records = run_result
        from collections import defaultdict
        by_event = defaultdict(list)
        for r in _spd_records(records):
            by_event[r["event_id"]].append(r["details"].get("A_k", 0.0))

        for event_id, a_values in by_event.items():
            total_a = sum(a_values)
            assert total_a <= 1.0 + 1e-9, (
                f"Event {event_id}: Σ A_k = {total_a:.6f} > 1.0 — "
                "attribution budget violation"
            )

    def test_structural_over_attribution_via_direct_adapter(self):
        """
        STRUCTURAL RISK — detect (not fix): the adapter alone allows two actors
        to each claim positive SPD for *independent* suppressions of the same TA,
        even when their combined implied suppression exceeds TA.

        The runner mitigates this via F-01; the raw adapter does not.
        This test documents the structural risk.
        """
        adapter = _fresh_adapter()
        ta_intensity = 0.8
        ta = _make_consistent_ta(intensity=ta_intensity + 0.05)
        # Use the actual ta.intensity from the TA object (min of readings)
        actual_ta = ta.intensity  # ≈ 0.75

        # Actor A: SE_intensity = actual_ta * 0.25  (75 % suppression rate)
        se_a = actual_ta * 0.25
        # Actor B: SE_intensity = actual_ta * 0.35  (65 % suppression rate)
        se_b = actual_ta * 0.35

        # Both compute against the same TA independently (adapter sees each alone)
        spd_a = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=se_a, se_time=5.0,
            actor_id="actor-a", attribution_share=1.0, linkage_score=0.0,
        )
        # Reset recurrence counter so actor B is not penalised by actor A's count
        adapter._pattern_counts.clear()

        spd_b = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=se_b, se_time=5.0,
            actor_id="actor-b", attribution_share=1.0, linkage_score=0.0,
        )

        # Both actors earn positive SPD independently
        assert spd_a.SPD_k > 0, "Actor A should earn positive SPD"
        assert spd_b.SPD_k > 0, "Actor B should earn positive SPD"

        # Combined implied suppression exceeds actual TA
        suppression_a = actual_ta - se_a  # > 0
        suppression_b = actual_ta - se_b  # > 0
        total_claimed = suppression_a + suppression_b
        # STRUCTURAL RISK flagged:
        assert total_claimed > actual_ta, (
            f"Over-attribution condition NOT triggered: "
            f"total_claimed={total_claimed:.4f}, ta={actual_ta:.4f}. "
            "Test setup error."
        )
        # Test PASSES: risk is correctly detected and documented.


# ══════════════════════════════════════════════════════════════════════
# Scenario 4 — Timing Arbitrage
# ══════════════════════════════════════════════════════════════════════

class TestTimingArbitrage:
    """
    Within the valid window, SPD is flat w.r.t. timing (S_k is intensity-based).
    The cliff at Δt_int is correct protocol behaviour — flagged as a risk.
    """

    def test_timing_inside_window_does_not_affect_spd(self):
        """
        SPD must be identical for two SE times that are both inside [0, Δt_int].
        Timing should not be an exploitable lever within the window.
        """
        adapter = _fresh_adapter(delta_t_int=30.0)
        ta = _make_consistent_ta(intensity=0.8)

        # se_time = 1.0 (just entered window)
        spd_early = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=1.0,
            actor_id="actor-001", attribution_share=1.0, linkage_score=0.0,
        )
        adapter._pattern_counts.clear()

        # se_time = 29.0 (near window end)
        spd_late = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=29.0,
            actor_id="actor-001", attribution_share=1.0, linkage_score=0.0,
        )

        # S_k is intensity-based only → SPD should be equal inside window
        assert spd_early.SPD_k == spd_late.SPD_k, (
            f"Timing arbitrage window: SPD differs for se_time=1.0 "
            f"({spd_early.SPD_k}) vs se_time=29.0 ({spd_late.SPD_k})"
        )

    def test_timing_cliff_at_delta_t_int_flagged(self):
        """
        DISCONTINUITY FLAGGED: at se_time = Δt_int + ε, temporal_valid flips
        False → SPD drops to 0.  Both sides tested and documented.
        """
        adapter = _fresh_adapter(delta_t_int=30.0)
        ta = _make_consistent_ta(intensity=0.8)

        # Inside window: se_time = 29.9 (ta_time=0, dt=29.9 ≤ 30)
        spd_inside = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=29.9,
            actor_id="actor-001", attribution_share=1.0, linkage_score=0.0,
        )
        adapter._pattern_counts.clear()

        # Outside window: se_time = 30.1 (dt=30.1 > 30)
        spd_outside = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=30.1,
            actor_id="actor-001", attribution_share=1.0, linkage_score=0.0,
        )

        assert spd_inside.SPD_k > 0.0, "SPD should be positive inside window"
        assert spd_outside.SPD_k == 0.0, "SPD must be zero outside window (temporal cliff)"

        # Discontinuity is confirmed — gradient is effectively infinite
        # FLAGGED: this is a known discontinuity risk

    def test_early_timing_valid_window_lower_bound(self):
        """SE at exactly dt=0 is NOT valid (strict inequality: dt > 0)."""
        adapter = _fresh_adapter(delta_t_int=30.0)
        ta = _make_consistent_ta(intensity=0.8)

        # se_time = 0.0 == ta.timestamp → dt = 0, temporal_valid = False
        spd = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=0.0,    # ta.timestamp = 0.0
            actor_id="actor-001", attribution_share=1.0, linkage_score=0.0,
        )
        assert spd.SPD_k == 0.0, "dt=0 must yield zero SPD (temporal window requires dt>0)"


# ══════════════════════════════════════════════════════════════════════
# Scenario 5 — Attribution Splitting
# ══════════════════════════════════════════════════════════════════════

class TestAttributionSplitting:
    """
    INVARIANT: Σ A_k per event ≤ 1.0 always.
    Splitting across N actors with shares 1/N is equivalent to 1 actor with share 1.0.
    """

    def test_single_actor_full_attribution(self):
        """1 actor with attribution_share=1.0 earns full SPD."""
        adapter = _fresh_adapter()
        ta = _make_consistent_ta(intensity=0.8)

        spd = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=5.0,
            actor_id="actor-single", attribution_share=1.0, linkage_score=0.0,
        )
        assert spd.A_k == 1.0
        assert spd.SPD_k > 0.0

    def test_two_actors_half_share_sums_to_full(self):
        """
        Two actors each with share=0.5 must produce combined SPD equal to
        one actor with share=1.0 (assuming identical effectiveness).
        """
        adapter = _fresh_adapter()
        ta = _make_consistent_ta(intensity=0.8)

        spd_single = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=5.0,
            actor_id="actor-single", attribution_share=1.0, linkage_score=0.0,
        )
        adapter._pattern_counts.clear()

        spd_a = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=5.0,
            actor_id="actor-a", attribution_share=0.5, linkage_score=0.0,
        )
        adapter._pattern_counts.clear()

        spd_b = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.4, se_time=5.0,
            actor_id="actor-b", attribution_share=0.5, linkage_score=0.0,
        )

        combined = spd_a.SPD_k + spd_b.SPD_k
        # Tolerance of 1e-5 accounts for per-result round(SPD_k, 6) rounding
        assert abs(combined - spd_single.SPD_k) < 1e-5, (
            f"Split attribution: combined={combined:.8f} ≠ single={spd_single.SPD_k:.8f}"
        )

    def test_budget_exhausted_for_subsequent_actors(self):
        """
        In the full runner, per-event budget = 1.0.  After first actor claims
        attribution_share=1.0, subsequent actors receive A_k=0.
        """
        cfg = attribution_split_config(seed=1005)
        run_simulation(cfg)
        records = _load_records("/tmp/dkp-l8-attribution-split")

        from collections import defaultdict
        by_event = defaultdict(list)
        for r in _spd_records(records):
            by_event[r["event_id"]].append(r["details"].get("A_k", 0.0))

        for eid, a_vals in by_event.items():
            total_a = sum(a_vals)
            assert total_a <= 1.0 + 1e-9, f"Event {eid}: Σ A_k={total_a:.6f} > 1.0"

        assert len(by_event) > 0, "Expected at least one positive-SPD event"


# ══════════════════════════════════════════════════════════════════════
# Scenario 6 — Early Prevention
# ══════════════════════════════════════════════════════════════════════

class TestEarlyPrevention:
    """
    INVARIANT: Reward(pre-TA) = 0 AND Reward(post-TA) > 0.
    Flagged: this creates an incentive to delay prevention until after TA.
    """

    def test_pre_ta_prevention_earns_zero(self):
        """
        SE at se_time < ta.timestamp → dt < 0 → temporal_valid = False → SPD = 0.
        """
        adapter = _fresh_adapter()
        ta = _make_consistent_ta(intensity=0.8)   # ta.timestamp = 0.0

        spd = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.2, se_time=-1.0,       # BEFORE TA registration
            actor_id="actor-early", attribution_share=1.0, linkage_score=0.0,
        )
        assert spd.SPD_k == 0.0, (
            "Pre-TA prevention must earn zero reward (temporal_valid requires dt>0)"
        )

    def test_post_ta_prevention_earns_positive(self):
        """SE at se_time ∈ (ta.timestamp, ta.timestamp + Δt_int] earns positive SPD."""
        adapter = _fresh_adapter()
        ta = _make_consistent_ta(intensity=0.8)

        spd = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.2, se_time=5.0,        # AFTER TA, within window
            actor_id="actor-late", attribution_share=1.0, linkage_score=0.0,
        )
        assert spd.SPD_k > 0.0, "Post-TA prevention should earn positive SPD"

    def test_incentive_gap_flagged(self):
        """
        FLAGGED: protocol creates incentive to delay action until TA is registered.
        Genuine early prevention (before TA) earns 0; delayed prevention earns SPD.
        This documents the gap — not a protocol bug but an audit finding.
        """
        adapter = _fresh_adapter()
        ta = _make_consistent_ta(intensity=0.8)

        spd_early = adapter.compute_spd(
            event_id=1, zone_id="z", ta=ta,
            se_intensity=0.2, se_time=-5.0,
            actor_id="actor", attribution_share=1.0, linkage_score=0.0,
        )
        adapter._pattern_counts.clear()

        spd_post = adapter.compute_spd(
            event_id=2, zone_id="z", ta=ta,
            se_intensity=0.2, se_time=1.0,
            actor_id="actor", attribution_share=1.0, linkage_score=0.0,
        )

        # Document the gap: early=0, post>0
        early_is_zero  = spd_early.SPD_k == 0.0
        post_is_positive = spd_post.SPD_k > 0.0

        assert early_is_zero,     "Early prevention should be zero (expected)"
        assert post_is_positive,  "Post-TA prevention should be positive (expected)"
        # AUDIT FINDING: agents are incentivised to delay prevention until after TA.


# ══════════════════════════════════════════════════════════════════════
# Scenario 7 — Oracle Degradation
# ══════════════════════════════════════════════════════════════════════

class TestOracleDegradation:
    """
    INVARIANT: TA_intensity ≥ 0; SPD ≥ 0.
    Degraded oracles increase informational rate but must not produce negative SPD.
    """

    @pytest.fixture(scope="class")
    def run_result(self):
        cfg = oracle_degradation_config(seed=1007)
        summary = run_simulation(cfg)
        records = _load_records("/tmp/dkp-l8-oracle-degradation")
        return summary, records

    def test_all_spd_non_negative(self, run_result):
        """SPD must never go negative regardless of oracle degradation."""
        _, records = run_result
        for r in records:
            assert r["value"] >= ORACLE_MIN_SPD, (
                f"Negative SPD detected: {r['value']} in event {r['event_id']}"
            )

    def test_degraded_oracles_increase_informational_rate(self, run_result):
        """
        Degraded oracles (high noise) push delta_oracle > epsilon more often,
        downgrading more events to informational.
        """
        summary, records = run_result
        info_count     = summary["informational_events"]
        total_metric   = summary["total_metric_records"]

        # Run stable config for comparison (same seed, low noise)
        stable_cfg     = oracle_oscillation_stable_config(seed=1007)
        stable_summary = run_simulation(stable_cfg)
        stable_info    = stable_summary["informational_events"]
        stable_total   = stable_summary["total_metric_records"]

        degraded_info_rate = info_count / total_metric if total_metric else 0.0
        stable_info_rate   = stable_info / stable_total if stable_total else 0.0

        assert degraded_info_rate >= stable_info_rate, (
            f"Degraded oracle informational rate ({degraded_info_rate:.4f}) "
            f"should be ≥ stable ({stable_info_rate:.4f})"
        )

    def test_simulation_completes_without_error(self, run_result):
        """Full simulation with degraded oracles must complete."""
        summary, _ = run_result
        assert summary["total_metric_records"] >= 0


# ══════════════════════════════════════════════════════════════════════
# Scenario 8 — Oracle Oscillation
# ══════════════════════════════════════════════════════════════════════

class TestOracleOscillation:
    """
    INVARIANT: SPD variance must remain finite/bounded when oracle quality
    alternates between consistent and informational regimes.
    """

    @pytest.fixture(scope="class")
    def both_runs(self):
        cfg_stable = oracle_oscillation_stable_config(seed=1008)
        cfg_noisy  = oracle_oscillation_noisy_config(seed=1008)
        sum_stable = run_simulation(cfg_stable)
        sum_noisy  = run_simulation(cfg_noisy)
        rec_stable = _load_records("/tmp/dkp-l8-oracle-oscillation-stable")
        rec_noisy  = _load_records("/tmp/dkp-l8-oracle-oscillation-noisy")
        return (sum_stable, rec_stable), (sum_noisy, rec_noisy)

    def test_variance_finite_in_both_regimes(self, both_runs):
        """Both stable and noisy regimes produce finite SPD variance."""
        (_, rec_s), (_, rec_n) = both_runs

        vals_s = [r["value"] for r in _spd_records(rec_s)]
        vals_n = [r["value"] for r in _spd_records(rec_n)]

        for vals, label in [(vals_s, "stable"), (vals_n, "noisy")]:
            if len(vals) > 1:
                var = statistics.variance(vals)
                assert var < float("inf"), f"Infinite variance in {label} regime"
                assert var >= 0.0

    def test_noisy_regime_has_lower_total_spd(self, both_runs):
        """
        High noise increases informational events (SPD=0), so total SPD must
        be ≤ stable total.  Validates that oracle degradation is not exploited.
        """
        (sum_s, _), (sum_n, _) = both_runs
        assert sum_n["total_spd_value"] <= sum_s["total_spd_value"] + 1e-6, (
            f"Noisy SPD ({sum_n['total_spd_value']}) > stable ({sum_s['total_spd_value']}). "
            "Oracle degradation may be exploitable."
        )

    def test_all_spd_values_non_negative_in_oscillation(self, both_runs):
        """No negative SPD in either regime."""
        (_, rec_s), (_, rec_n) = both_runs
        for r in _spd_records(rec_s) + _spd_records(rec_n):
            assert r["value"] >= 0.0


# ══════════════════════════════════════════════════════════════════════
# Scenario 9 — Linkage Threshold Sensitivity
# ══════════════════════════════════════════════════════════════════════

class TestLinkageThresholdSensitivity:
    """
    DISCONTINUITY FLAGGED: linkage_score > θ triggers T_k = 0 (step function §9.1).
    Below θ: SPD follows recurrence profile.
    At θ + ε: SPD drops immediately to 0.
    """

    @pytest.fixture(scope="class")
    def sweep_results(self):
        """Sweep linkage_score from 0.45 to 0.55 at fine resolution."""
        adapter = _fresh_adapter(theta_self_induced=0.5)
        ta = ThreatActivation(
            event_id=1, risk_channel="intrusion", timestamp=0.0,
            intensity=0.7,
            oracle_readings=[
                OracleReading("o1", "optical", 0.72, 0.9, 0.0),
                OracleReading("o2", "thermal", 0.70, 0.9, 0.0),
            ],
            oracle_classes_used={"optical", "thermal"},
            is_valid=True, is_consistent=True, delta_oracle=0.02, informational=False,
        )
        results = linkage_spd_sweep(
            adapter=adapter, ta=ta,
            se_intensity=0.35, se_time=5.0,
            actor_id="sweep-actor", attribution_share=1.0,
            linkage_values=[round(0.45 + i * 0.01, 3) for i in range(11)],
        )
        return results

    def test_below_theta_earns_positive_spd(self, sweep_results):
        """linkage_score = 0.45 to 0.49 must earn positive SPD (< θ = 0.5)."""
        for ls in [0.45, 0.46, 0.47, 0.48, 0.49]:
            assert sweep_results[ls] > 0.0, (
                f"linkage_score={ls} < theta=0.5 should give positive SPD, "
                f"got {sweep_results[ls]}"
            )

    def test_at_theta_boundary_earns_positive(self, sweep_results):
        """linkage_score = θ exactly is NOT > θ → T_k > 0 → SPD > 0."""
        assert sweep_results[0.50] > 0.0, (
            "linkage_score=0.50 == theta (not strictly greater) must earn positive SPD"
        )

    def test_above_theta_earns_zero(self, sweep_results):
        """linkage_score > θ → T_k = 0 → SPD = 0 (§9.1 strict threshold)."""
        for ls in [0.51, 0.52, 0.53, 0.54, 0.55]:
            assert sweep_results[ls] == 0.0, (
                f"linkage_score={ls} > theta=0.5 must give SPD=0, "
                f"got {sweep_results[ls]}"
            )

    def test_discontinuity_flagged_at_theta(self, sweep_results):
        """
        DISCONTINUITY FLAGGED: SPD jumps from positive to 0 at a single epsilon
        crossing of theta.  An adversary can exploit by keeping linkage at 0.5.
        """
        spd_at_theta     = sweep_results[0.50]   # positive
        spd_above_theta  = sweep_results[0.51]   # zero

        assert spd_at_theta > spd_above_theta, (
            "Expected discontinuity: SPD at theta should be > SPD above theta"
        )
        # AUDIT: cliff at theta = 0.5 is a known exploit boundary.
        # An actor who keeps linkage_score at exactly 0.5 maximises T_k.


# ══════════════════════════════════════════════════════════════════════
# Scenario 10 — SE ≥ TA Boundary
# ══════════════════════════════════════════════════════════════════════

class TestSETABoundary:
    """
    DISCONTINUITY FLAGGED: at SE = TA, S_k drops to 0 (§3.6).
    The transition SE < TA → SE ≥ TA is an abrupt cliff in the reward function.
    """

    @pytest.fixture(scope="class")
    def sweep_results(self):
        """Sweep SE ∈ [0.90 TA, 1.10 TA] across the boundary."""
        adapter = _fresh_adapter()
        ta = ThreatActivation(
            event_id=1, risk_channel="intrusion", timestamp=0.0,
            intensity=0.70,
            oracle_readings=[
                OracleReading("o1", "optical", 0.72, 0.9, 0.0),
                OracleReading("o2", "thermal", 0.70, 0.9, 0.0),
            ],
            oracle_classes_used={"optical", "thermal"},
            is_valid=True, is_consistent=True, delta_oracle=0.02, informational=False,
        )
        results = se_ta_boundary_sweep(
            adapter=adapter, ta=ta, ta_intensity=0.70,
            se_fractions=[round(0.90 + i * 0.01, 3) for i in range(21)],
            se_time=5.0, actor_id="sweep-actor", attribution_share=1.0,
        )
        return results

    def test_below_boundary_earns_positive_spd(self, sweep_results):
        """SE < TA (fraction < 1.0) must earn positive SPD."""
        for frac in [0.90, 0.95, 0.99]:
            assert sweep_results[frac] > 0.0, (
                f"SE/TA={frac} < 1.0: expected positive SPD, got {sweep_results[frac]}"
            )

    def test_at_and_above_boundary_earns_zero(self, sweep_results):
        """SE ≥ TA (fraction ≥ 1.00) must earn zero SPD (§3.6 invariant)."""
        for frac in [1.00, 1.01, 1.05, 1.10]:
            assert sweep_results[frac] == 0.0, (
                f"SE/TA={frac} ≥ 1.0: expected SPD=0, got {sweep_results[frac]}"
            )

    def test_discontinuity_is_abrupt_cliff(self, sweep_results):
        """
        DISCONTINUITY FLAGGED: SPD(SE=0.99×TA) > 0 but SPD(SE=1.00×TA) = 0.
        This is a known one-sided cliff in the reward signal.
        """
        spd_just_below  = sweep_results[0.99]
        spd_at_boundary = sweep_results[1.00]

        assert spd_just_below  > 0.0, "Just below boundary: expected positive SPD"
        assert spd_at_boundary == 0.0, "At boundary: expected zero SPD"
        # AUDIT: the cliff from SPD>0 to SPD=0 in a single epsilon step
        # is detectable and represents a potential gaming boundary.

    def test_boundary_run_produces_zero_total_spd(self):
        """
        Full simulation with se_ge_ta_probability=1.0 must yield total_spd=0.0.
        Every intervention generates SE ≥ TA → S_k = 0 → SPD = 0.
        """
        cfg = boundary_se_ta_config(seed=1010)
        summary = run_simulation(cfg)
        assert summary["total_spd_value"] == 0.0, (
            f"Expected total_spd=0 with se_ge_ta_probability=1.0, "
            f"got {summary['total_spd_value']}"
        )
