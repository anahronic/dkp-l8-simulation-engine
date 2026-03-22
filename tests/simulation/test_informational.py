"""
Test: Informational mode — §3.3.2 / §12 oracle inconsistency handling.

When Δ_oracle > ε_consistency, SPDₖ = informational (no reward).
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


class TestInformationalMode:
    """§3.3.2: Oracle inconsistency → informational downgrade."""

    def test_inconsistent_produces_informational(self, adapter):
        """Large oracle spread → informational, SPD = 0."""
        readings = [
            OracleReading("o1", "optical", 0.3, 0.0, 0.9),
            OracleReading("o2", "thermal", 0.8, 0.0, 0.9),
        ]
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert ta.informational

        spd = adapter.compute_spd(
            event_id=1,
            zone_id="z1",
            ta=ta,
            se_intensity=0.1,
            se_time=5.0,
            actor_id="actor-001",
            attribution_share=1.0,
            linkage_score=0.0,
        )

        assert spd.informational
        assert spd.SPD_k == 0.0

    def test_consistent_not_informational(self, adapter):
        """Tight oracle spread → NOT informational."""
        readings = [
            OracleReading("o1", "optical", 0.50, 0.0, 0.95),
            OracleReading("o2", "thermal", 0.52, 0.0, 0.95),
        ]
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert not ta.informational
        assert ta.is_consistent

    def test_borderline_consistency(self, adapter):
        """Δ just under ε → still consistent."""
        # ε = 0.15, use delta = 0.14 to avoid float-precision edge
        readings = [
            OracleReading("o1", "optical", 0.50, 0.0, 0.95),
            OracleReading("o2", "thermal", 0.64, 0.0, 0.95),
        ]
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert ta.is_consistent  # Δ = 0.14 ≤ ε = 0.15

    def test_just_over_epsilon(self, adapter):
        """Δ slightly above ε → inconsistent → informational."""
        readings = [
            OracleReading("o1", "optical", 0.50, 0.0, 0.95),
            OracleReading("o2", "thermal", 0.66, 0.0, 0.95),
        ]
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert not ta.is_consistent
        assert ta.informational
