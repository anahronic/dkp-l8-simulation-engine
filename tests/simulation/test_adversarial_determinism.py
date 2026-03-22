"""
Test: Adversarial Incentive Audit — Determinism (Phase 2).

All 10 adversarial scenarios must produce bit-exact output when run
twice with the same seed.  This ensures the adversarial audit results
are reproducible and the analysis is trustworthy.

Requirements:
    - Fixed seeds throughout
    - Identical total_spd across two runs
    - Identical subject_totals across two runs
"""

from __future__ import annotations

import pytest

from simulation.run_prevention_simulation import run_simulation
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
)


# ── Helper ──────────────────────────────────────────────────────────────

def _assert_deterministic(cfg1: dict, cfg2: dict, scenario: str) -> None:
    """Run two identical configs and assert bit-exact output."""
    r1 = run_simulation(cfg1)
    r2 = run_simulation(cfg2)

    assert r1["total_spd_value"] == r2["total_spd_value"], (
        f"[{scenario}] total_spd mismatch: {r1['total_spd_value']} != "
        f"{r2['total_spd_value']}"
    )
    assert r1["subject_totals"] == r2["subject_totals"], (
        f"[{scenario}] subject_totals mismatch"
    )
    assert r1["positive_spd_events"] == r2["positive_spd_events"], (
        f"[{scenario}] positive_spd_events mismatch"
    )
    assert r1["informational_events"] == r2["informational_events"], (
        f"[{scenario}] informational_events mismatch"
    )


# ── Determinism tests — one per scenario ────────────────────────────────

class TestAdversarialDeterminism:
    """All 10 adversarial scenarios must be bit-exact across two runs."""

    def test_risk_farming_deterministic(self):
        """Scenario 1 — Risk Farming: same seed → identical output."""
        _assert_deterministic(
            risk_farming_config(seed=1001, num_days=15),
            risk_farming_config(seed=1001, num_days=15),
            "risk_farming",
        )

    def test_ta_inflation_deterministic(self):
        """Scenario 2 — TA Inflation: same seed → identical output."""
        _assert_deterministic(
            ta_inflation_config(seed=1002),
            ta_inflation_config(seed=1002),
            "ta_inflation",
        )

    def test_partial_suppression_deterministic(self):
        """Scenario 3 — Partial Suppression: same seed → identical output."""
        _assert_deterministic(
            partial_suppression_config(seed=1003),
            partial_suppression_config(seed=1003),
            "partial_suppression",
        )

    def test_timing_arbitrage_deterministic(self):
        """Scenario 4 — Timing Arbitrage: same seed → identical output."""
        _assert_deterministic(
            timing_arbitrage_config(seed=1004, se_delay_min=1.0),
            timing_arbitrage_config(seed=1004, se_delay_min=1.0),
            "timing_arbitrage",
        )

    def test_attribution_split_deterministic(self):
        """Scenario 5 — Attribution Splitting: same seed → identical output."""
        _assert_deterministic(
            attribution_split_config(seed=1005),
            attribution_split_config(seed=1005),
            "attribution_split",
        )

    def test_early_prevention_deterministic(self):
        """Scenario 6 — Early Prevention: same seed → identical output."""
        _assert_deterministic(
            early_prevention_config(seed=1006),
            early_prevention_config(seed=1006),
            "early_prevention",
        )

    def test_oracle_degradation_deterministic(self):
        """Scenario 7 — Oracle Degradation: same seed → identical output."""
        _assert_deterministic(
            oracle_degradation_config(seed=1007),
            oracle_degradation_config(seed=1007),
            "oracle_degradation",
        )

    def test_oracle_oscillation_stable_deterministic(self):
        """Scenario 8a — Oracle Oscillation (stable): same seed → identical output."""
        _assert_deterministic(
            oracle_oscillation_stable_config(seed=1008),
            oracle_oscillation_stable_config(seed=1008),
            "oracle_oscillation_stable",
        )

    def test_oracle_oscillation_noisy_deterministic(self):
        """Scenario 8b — Oracle Oscillation (noisy): same seed → identical output."""
        _assert_deterministic(
            oracle_oscillation_noisy_config(seed=1008),
            oracle_oscillation_noisy_config(seed=1008),
            "oracle_oscillation_noisy",
        )

    def test_linkage_sweep_deterministic(self):
        """Scenario 9 — Linkage Sweep: same seed → identical output."""
        _assert_deterministic(
            linkage_sweep_config(seed=1009),
            linkage_sweep_config(seed=1009),
            "linkage_sweep",
        )

    def test_boundary_se_ta_deterministic(self):
        """Scenario 10 — SE ≥ TA Boundary: same seed → identical output."""
        _assert_deterministic(
            boundary_se_ta_config(seed=1010),
            boundary_se_ta_config(seed=1010),
            "boundary_se_ta",
        )


class TestCrossSeedIndependence:
    """Different seeds must produce different (non-identical) outputs where stochastic."""

    def test_different_seeds_produce_different_spd(self):
        """Seeds 1001 and 9999 must produce different total SPD values."""
        r1 = run_simulation(risk_farming_config(seed=1001, num_days=5))
        r2 = run_simulation(risk_farming_config(seed=9999, num_days=5))
        # Different seeds should almost certainly produce different RNG paths
        # (extremely unlikely to be identical for a 30-tick run)
        assert r1["total_spd_value"] != r2["total_spd_value"], (
            "Different seeds produced identical total_spd — RNG may be broken"
        )

    def test_risk_farming_three_way_determinism(self):
        """Run risk farming three times with same seed: all results must match."""
        cfg_fn = lambda: risk_farming_config(seed=5555, num_days=5)
        r1 = run_simulation(cfg_fn())
        r2 = run_simulation(cfg_fn())
        r3 = run_simulation(cfg_fn())

        assert r1["total_spd_value"] == r2["total_spd_value"] == r3["total_spd_value"]
        assert r1["total_metric_records"] == r2["total_metric_records"] == r3["total_metric_records"]
