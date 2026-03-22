"""
Test: Self-induced risk — §9.1 enforcement.

If linkage(subject, TAₖ) > θ → Tₖ = 0 → SPDₖ = 0.
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
        threat_weights={"test_channel": 0.9},
    )


def _make_consistent_ta(adapter, intensity=0.6):
    """Create a valid, consistent TA for testing."""
    readings = [
        OracleReading("o1", "optical", intensity, 0.0, 0.95),
        OracleReading("o2", "thermal", intensity + 0.02, 0.0, 0.95),
    ]
    return adapter.validate_threat_activation(1, "test_channel", 0.0, readings)


class TestSelfInducedRisk:
    """§9.1: Self-induced risk detection and nullification."""

    def test_self_induced_zeroes_spd(self, adapter):
        """Self-induced flag → Tₖ = 0 → SPDₖ = 0."""
        ta = _make_consistent_ta(adapter)
        assert ta.is_valid and ta.is_consistent

        spd = adapter.compute_spd(
            event_id=1,
            zone_id="z1",
            ta=ta,
            se_intensity=0.1,
            se_time=5.0,
            actor_id="actor-bad",
            attribution_share=1.0,
            linkage_score=1.0,
        )

        assert spd.T_k == 0.0
        assert spd.SPD_k == 0.0

    def test_non_self_induced_positive_spd(self, adapter):
        """Honest actor → Tₖ > 0 → SPDₖ > 0."""
        ta = _make_consistent_ta(adapter)

        spd = adapter.compute_spd(
            event_id=2,
            zone_id="z1",
            ta=ta,
            se_intensity=0.1,
            se_time=5.0,
            actor_id="actor-good",
            attribution_share=1.0,
            linkage_score=0.0,
        )

        assert spd.T_k > 0.0
        assert spd.SPD_k > 0.0

    def test_pattern_recurrence_decays_tamper(self, adapter):
        """§9.3: Repeated patterns → Tₖ ↓ (decay after 3 repetitions)."""
        ta = _make_consistent_ta(adapter)

        t_values = []
        for i in range(10):
            T_k = adapter.compute_tamper_factor(
                linkage_score=0.0,
                risk_channel="test_channel",
                actor_id="actor-repeat",
            )
            t_values.append(T_k)

        # After 3 occurrences, decay kicks in — later values should be smaller
        assert t_values[0] >= t_values[-1]
        # First 3 should be 1.0 (no decay yet)
        assert all(t == 1.0 for t in t_values[:3])
        # Later ones should be < 1.0
        assert t_values[-1] < 1.0
