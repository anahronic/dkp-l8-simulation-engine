"""
Test: Attribution budget — §6 enforcement of Σ Aₖ ≤ 1 per event.

Proves that per-event attribution never exceeds 1.0 regardless of how
many actors respond to the same threat.
"""

import pytest

from simulation.core.oracles import OracleReading
from simulation.modules.prevention.protocol_adapter import PreventionProtocolAdapter


@pytest.fixture
def adapter():
    return PreventionProtocolAdapter(
        epsilon_consistency=0.15,
        delta_t_int=30.0,
        theta_self_induced=0.5,
        recurrence_decay=0.9,
        coverage_floor=0.1,
        recurrence_threshold=3,
        threat_weights={"test_channel": 1.0},
    )


def _make_valid_ta(adapter):
    readings = [
        OracleReading("o1", "optical", 0.6, 0.0, 0.95),
        OracleReading("o2", "thermal", 0.62, 0.0, 0.95),
    ]
    return adapter.validate_threat_activation(1, "test_channel", 0.0, readings)


def _budget_allocate(shares):
    """Simulate the runner's per-event attribution budget logic."""
    remaining = 1.0
    actual = []
    for s in shares:
        a = min(s, remaining)
        remaining -= a
        actual.append(round(a, 10))
    return actual, round(remaining, 10)


class TestAttributionBudget:
    """§6: Σ Aₖ ≤ 1 per event."""

    def test_single_actor_full_share(self):
        """One actor with A=1.0 → valid, gets full share."""
        actual, residual = _budget_allocate([1.0])
        assert actual == [1.0]
        assert residual == 0.0

    def test_two_actors_within_budget(self):
        """Two actors with 0.4 + 0.3 → valid, residual 0.3."""
        actual, residual = _budget_allocate([0.4, 0.3])
        assert actual == [0.4, 0.3]
        assert abs(residual - 0.3) < 1e-9

    def test_two_actors_exceeds_budget(self):
        """Two actors with 0.8 + 0.7 → second actor clamped to 0.2."""
        actual, residual = _budget_allocate([0.8, 0.7])
        assert actual[0] == 0.8
        assert abs(actual[1] - 0.2) < 1e-9
        assert abs(residual) < 1e-9

    def test_three_actors_all_full(self):
        """Three actors with 1.0, 1.0, 1.0 → first gets 1.0, others get 0."""
        actual, residual = _budget_allocate([1.0, 1.0, 1.0])
        assert actual[0] == 1.0
        assert actual[1] == 0.0
        assert actual[2] == 0.0

    def test_budget_through_adapter(self, adapter):
        """End-to-end: two actors sharing one event, budget enforced."""
        ta = _make_valid_ta(adapter)

        remaining = 1.0
        shares = [0.8, 0.7]
        spd_results = []

        for i, proposed_share in enumerate(shares):
            actual_share = min(proposed_share, remaining)
            remaining -= actual_share

            if actual_share <= 0.0:
                continue

            spd = adapter.compute_spd(
                event_id=1,
                zone_id="z1",
                ta=ta,
                se_intensity=0.1,
                se_time=5.0,
                actor_id=f"actor-{i:03d}",
                attribution_share=actual_share,
                linkage_score=0.0,
            )
            spd_results.append(spd)

        assert len(spd_results) == 2
        total_A = sum(s.A_k for s in spd_results)
        assert total_A <= 1.0 + 1e-9
        assert spd_results[0].A_k == 0.8
        assert abs(spd_results[1].A_k - 0.2) < 1e-6

    def test_integration_no_event_exceeds_budget(self):
        """Full runner: no event in metrics has Σ A_k > 1.0."""
        from simulation.run_prevention_simulation import run_simulation
        from simulation.core.metrics import MetricsCollector
        import json
        import os

        cfg = {
            "simulation": {
                "seed": 55555,
                "num_zones": 1,
                "num_days": 1,
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
            "oracles": {"noise_sigma": 0.05, "dropout_rate": 0.0, "bias_range": [0.0, 0.0]},
            "output": {"directory": "/tmp/dkp-l8-attribution-test"},
        }

        summary = run_simulation(cfg)

        # Read metrics and check per-event Σ A_k
        metrics_path = "/tmp/dkp-l8-attribution-test/metrics.json"
        with open(metrics_path) as f:
            records = json.load(f)

        from collections import defaultdict
        event_attribution = defaultdict(float)
        for r in records:
            if r["metric_name"] == "SPD":
                event_attribution[r["event_id"]] += r["details"].get("A_k", 0.0)

        for event_id, total_a in event_attribution.items():
            assert total_a <= 1.0 + 1e-9, f"Event {event_id} has Σ A_k = {total_a} > 1.0"
