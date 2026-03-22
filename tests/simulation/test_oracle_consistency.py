"""
Test: Oracle consistency — validate §3.3 regime switching.
"""

import pytest

from simulation.core.oracles import Oracle, OraclePool, OracleReading
from simulation.core.rng import DeterministicRNG
from simulation.modules.prevention.protocol_adapter import PreventionProtocolAdapter


@pytest.fixture
def rng():
    return DeterministicRNG(seed=99)


@pytest.fixture
def adapter():
    return PreventionProtocolAdapter(
        epsilon_consistency=0.15,
        delta_t_int=30.0,
        theta_self_induced=0.5,
        recurrence_decay=0.9,
        coverage_floor=0.1,
        recurrence_threshold=3,
    )


class TestOracleConsistency:
    """§3.3: Two regimes based on Δ_oracle vs ε_consistency."""

    def test_two_classes_consistent(self, adapter, rng):
        """Two oracle classes, small delta → consistent → valid TA."""
        pool = OraclePool()
        pool.add(Oracle("o1", "optical", rng.fork("o1"), noise_sigma=0.01))
        pool.add(Oracle("o2", "thermal", rng.fork("o2"), noise_sigma=0.01))

        readings = pool.read_all(true_intensity=0.6, timestamp=0.0)
        ta = adapter.validate_threat_activation(1, "ch", 0.0, readings)

        assert ta.is_valid
        assert ta.is_consistent
        assert not ta.informational
        assert ta.intensity > 0

    def test_two_classes_inconsistent(self, adapter, rng):
        """Two classes, large bias → inconsistent → informational."""
        pool = OraclePool()
        pool.add(Oracle("o1", "optical", rng.fork("o1"), noise_sigma=0.01, bias=0.0))
        pool.add(Oracle("o2", "thermal", rng.fork("o2"), noise_sigma=0.01, bias=0.3))

        readings = pool.read_all(true_intensity=0.5, timestamp=0.0)
        ta = adapter.validate_threat_activation(1, "ch", 0.0, readings)

        assert ta.is_valid  # still 2 classes
        assert not ta.is_consistent
        assert ta.informational

    def test_single_class_invalid(self, adapter, rng):
        """Only one oracle class → invalid TAₖ (§9.5)."""
        pool = OraclePool()
        pool.add(Oracle("o1", "optical", rng.fork("o1")))
        pool.add(Oracle("o2", "optical", rng.fork("o2")))  # same class

        readings = pool.read_all(true_intensity=0.7, timestamp=0.0)
        ta = adapter.validate_threat_activation(1, "ch", 0.0, readings)

        assert not ta.is_valid

    def test_three_classes_consistent(self, adapter, rng):
        """Three classes, tight noise → consistent, intensity = min."""
        pool = OraclePool()
        pool.add(Oracle("o1", "optical", rng.fork("o1"), noise_sigma=0.002))
        pool.add(Oracle("o2", "thermal", rng.fork("o2"), noise_sigma=0.002))
        pool.add(Oracle("o3", "lidar", rng.fork("o3"), noise_sigma=0.002))

        readings = pool.read_all(true_intensity=0.5, timestamp=0.0)
        ta = adapter.validate_threat_activation(1, "ch", 0.0, readings)

        assert ta.is_valid
        assert ta.is_consistent
        assert ta.intensity == min(r.intensity for r in readings)

    def test_oracle_dropout(self, adapter, rng):
        """High dropout → may lose class coverage → could become invalid."""
        pool = OraclePool()
        pool.add(Oracle("o1", "optical", rng.fork("o1"), dropout_rate=0.99))
        pool.add(Oracle("o2", "thermal", rng.fork("o2"), dropout_rate=0.99))

        # With 99% dropout, very likely both drop → no readings
        readings = pool.read_all(true_intensity=0.6, timestamp=0.0)
        ta = adapter.validate_threat_activation(1, "ch", 0.0, readings)

        # Should be invalid if too few classes survive
        if len({r.oracle_class for r in readings}) < 2:
            assert not ta.is_valid
