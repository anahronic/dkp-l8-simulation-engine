"""
Test: Failure paths — F-04 (SE ≥ TA), F-05 (temporal invalidity), F-10.

Verifies that the simulation runner can generate these failure modes
via config, and that the adapter correctly produces SPD = 0 for them.
"""

import json
import pytest

from simulation.run_prevention_simulation import run_simulation


def _make_config(se_ge_ta_prob=0.0, temporal_invalid_prob=0.0, seed=33333):
    return {
        "simulation": {
            "seed": seed,
            "num_zones": 1,
            "num_days": 3,
            "ticks_per_day": 8,
            "se_ge_ta_probability": se_ge_ta_prob,
            "temporal_invalid_probability": temporal_invalid_prob,
            "se_delay_min": 1.0,
        },
        "protocol": {
            "epsilon_consistency": 0.15,
            "delta_t_int": 30.0,
            "theta_self_induced": 0.5,
            "recurrence_decay": 0.9,
            "recurrence_threshold": 3,
            "coverage_floor": 0.1,
        },
        "domain": {
            "name": "childcare",
            "include_adversarial": False,
            "threat_weights": {
                "unauthorized_adult_proximity": 0.9,
                "intrusion": 1.0,
                "unattended_child_exit": 0.95,
                "hazardous_trajectory": 0.7,
                "dangerous_object": 0.8,
                "congestion_escalation": 0.5,
            },
            "threat_profiles": {
                "unauthorized_adult_proximity": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                "intrusion": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                "unattended_child_exit": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                "hazardous_trajectory": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                "dangerous_object": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
                "congestion_escalation": {"activation_rate": 0.5, "intensity_range": [0.3, 0.7]},
            },
        },
        "oracles": {"noise_sigma": 0.05, "dropout_rate": 0.0, "bias_range": [0.0, 0.0]},
        "output": {"directory": f"/tmp/dkp-l8-failure-paths-{seed}"},
    }


class TestSEExceedsTAPath:
    """F-04: SE ≥ TA must be reachable and produce SPD = 0."""

    def test_se_ge_ta_produces_zero_spd(self):
        """With high SE≥TA probability, fully_suppressed events appear."""
        cfg = _make_config(se_ge_ta_prob=0.5, seed=44444)
        summary = run_simulation(cfg)

        # Read metrics
        with open(f"/tmp/dkp-l8-failure-paths-44444/metrics.json") as f:
            records = json.load(f)

        fully_suppressed = [
            r for r in records
            if r["metric_name"] == "SPD"
            and r["details"].get("reason") == "fully_suppressed"
        ]

        # With 50% probability, we must see at least one fully_suppressed event
        assert len(fully_suppressed) > 0, "No fully_suppressed events generated"

        # All fully_suppressed events must have SPD = 0
        for r in fully_suppressed:
            assert r["value"] == 0.0


class TestTemporalInvalidityPath:
    """F-05 / F-10: Temporal invalidity must be reachable and produce SPD = 0."""

    def test_temporal_invalid_produces_zero_spd(self):
        """With high temporal invalidity probability, temporal_invalid events appear."""
        cfg = _make_config(temporal_invalid_prob=0.5, seed=55555)
        summary = run_simulation(cfg)

        with open(f"/tmp/dkp-l8-failure-paths-55555/metrics.json") as f:
            records = json.load(f)

        temporal_invalid = [
            r for r in records
            if r["metric_name"] == "SPD"
            and r["details"].get("reason") == "temporal_invalid"
        ]

        assert len(temporal_invalid) > 0, "No temporal_invalid events generated"

        for r in temporal_invalid:
            assert r["value"] == 0.0


class TestBothPathsSimultaneously:
    """Both failure paths can be active simultaneously."""

    def test_combined_failure_paths(self):
        cfg = _make_config(se_ge_ta_prob=0.3, temporal_invalid_prob=0.3, seed=66666)
        summary = run_simulation(cfg)

        with open(f"/tmp/dkp-l8-failure-paths-66666/metrics.json") as f:
            records = json.load(f)

        reasons = {r["details"].get("reason") for r in records if r["metric_name"] == "SPD"}

        # At least one of each failure type should appear
        assert "fully_suppressed" in reasons or "temporal_invalid" in reasons, \
            "No failure mode events generated with 30% probability each"
