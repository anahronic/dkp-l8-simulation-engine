"""
Test: Continuous linkage threshold — F-07.

Verifies that θ_self_induced is used as a continuous threshold
against linkage_score, not as a binary flag.
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


class TestContinuousLinkage:
    """§9.1: linkage_score > θ → T_k = 0."""

    def test_below_theta_not_zeroed(self, adapter):
        """linkage 0.4, theta 0.5 → T_k > 0 (not zeroed)."""
        T_k = adapter.compute_tamper_factor(
            linkage_score=0.4,
            risk_channel="test_channel",
            actor_id="a1",
        )
        assert T_k > 0.0

    def test_above_theta_zeroed(self, adapter):
        """linkage 0.6, theta 0.5 → T_k = 0."""
        T_k = adapter.compute_tamper_factor(
            linkage_score=0.6,
            risk_channel="test_channel",
            actor_id="a2",
        )
        assert T_k == 0.0

    def test_at_theta_not_zeroed(self, adapter):
        """linkage 0.5 == theta 0.5 → T_k > 0 (boundary: not strictly greater)."""
        T_k = adapter.compute_tamper_factor(
            linkage_score=0.5,
            risk_channel="test_channel",
            actor_id="a3",
        )
        assert T_k > 0.0

    def test_zero_linkage_not_zeroed(self, adapter):
        """linkage 0.0 → T_k > 0."""
        T_k = adapter.compute_tamper_factor(
            linkage_score=0.0,
            risk_channel="test_channel",
            actor_id="a4",
        )
        assert T_k > 0.0

    def test_full_linkage_zeroed(self, adapter):
        """linkage 1.0 → T_k = 0."""
        T_k = adapter.compute_tamper_factor(
            linkage_score=1.0,
            risk_channel="test_channel",
            actor_id="a5",
        )
        assert T_k == 0.0

    def test_spd_with_below_theta(self, adapter):
        """Full SPD pipeline with linkage below theta → SPD > 0."""
        ta = _make_valid_ta(adapter)
        spd = adapter.compute_spd(
            event_id=1,
            zone_id="z1",
            ta=ta,
            se_intensity=0.1,
            se_time=5.0,
            actor_id="a6",
            attribution_share=1.0,
            linkage_score=0.4,  # below θ=0.5
        )
        assert spd.SPD_k > 0.0
        assert spd.T_k > 0.0

    def test_spd_with_above_theta(self, adapter):
        """Full SPD pipeline with linkage above theta → SPD = 0."""
        ta = _make_valid_ta(adapter)
        spd = adapter.compute_spd(
            event_id=2,
            zone_id="z1",
            ta=ta,
            se_intensity=0.1,
            se_time=5.0,
            actor_id="a7",
            attribution_share=1.0,
            linkage_score=0.6,  # above θ=0.5
        )
        assert spd.SPD_k == 0.0
        assert spd.T_k == 0.0
