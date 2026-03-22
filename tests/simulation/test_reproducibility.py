"""
Test: Reproducibility — same seed must produce identical output.
"""

import pytest

from simulation.core.config import load_config
from simulation.run_prevention_simulation import run_simulation


def _make_smoke_config():
    """Inline minimal config for reproducibility test."""
    return {
        "simulation": {
            "seed": 12345,
            "num_zones": 1,
            "num_days": 2,
            "ticks_per_day": 4,
            "se_ge_ta_probability": 0.0,
            "temporal_invalid_probability": 0.0,
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
        "oracles": {
            "noise_sigma": 0.05,
            "dropout_rate": 0.0,
            "bias_range": [0.0, 0.0],
        },
        "output": {
            "directory": "/tmp/dkp-l8-repro-test",
            "write_csv": True,
            "write_json": True,
            "write_summary": True,
        },
    }


class TestReproducibility:
    """Same seed → identical output across runs."""

    def test_identical_seeds_same_output(self):
        cfg1 = _make_smoke_config()
        cfg2 = _make_smoke_config()

        summary1 = run_simulation(cfg1)
        summary2 = run_simulation(cfg2)

        assert summary1["total_spd_value"] == summary2["total_spd_value"]
        assert summary1["total_spd_events"] == summary2["total_spd_events"]
        assert summary1["positive_spd_events"] == summary2["positive_spd_events"]
        assert summary1["zero_spd_events"] == summary2["zero_spd_events"]
        assert summary1["informational_events"] == summary2["informational_events"]
        assert summary1["subject_totals"] == summary2["subject_totals"]

    def test_different_seeds_different_output(self):
        cfg1 = _make_smoke_config()
        cfg2 = _make_smoke_config()
        cfg2["simulation"]["seed"] = 99999

        summary1 = run_simulation(cfg1)
        summary2 = run_simulation(cfg2)

        # Not strictly guaranteed but overwhelmingly likely
        assert summary1["total_spd_value"] != summary2["total_spd_value"]
