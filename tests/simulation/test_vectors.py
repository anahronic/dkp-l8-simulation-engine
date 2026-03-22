"""
Test: Protocol test vectors — verify hand-calculated expected values.

Pins every protocol rule to a known-good output per the DKP-1-PREVENTION-001
v1.0 frozen spec.
"""

import pytest

from simulation.core.oracles import OracleReading
from simulation.modules.prevention.protocol_adapter import PreventionProtocolAdapter
from simulation.modules.prevention.test_vectors import (
    BASIC_SPD,
    FULL_SUPPRESSION,
    ORACLE_INCONSISTENCY,
    SINGLE_ORACLE_CLASS,
    SELF_INDUCED_RISK,
    CONSISTENT_ORACLE,
    NO_COVERAGE,
    PARTIAL_SUPPRESSION,
)


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


def _make_readings(intensities, classes):
    """Helper — create oracle readings from parallel lists."""
    return [
        OracleReading(
            oracle_id=f"oracle-{i}",
            oracle_class=classes[i],
            intensity=intensities[i],
            timestamp=0.0,
            confidence=0.95,
        )
        for i in range(len(intensities))
    ]


class TestBasicSPD:
    """§5: SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ"""

    def test_basic_spd_calculation(self, adapter):
        v = BASIC_SPD
        readings = _make_readings([0.80, 0.82], ["optical", "thermal"])
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)

        assert ta.is_valid
        assert ta.is_consistent

        spd = adapter.compute_spd(
            event_id=1,
            zone_id="zone-0001",
            ta=ta,
            se_intensity=v.inputs["se_intensity"],
            se_time=10.0,
            actor_id="actor-001",
            attribution_share=v.inputs["A_k"],
            linkage_score=0.0,
        )

        # S_k = (ta.intensity - 0.2) / ta.intensity ≈ (0.80 - 0.2) / 0.80 = 0.75
        assert abs(spd.S_k - v.expected["S_k"]) < 0.05
        assert spd.SPD_k > 0


class TestFullSuppression:
    """§3.6: SE ≥ TA → Sₖ = 0, SPDₖ = 0"""

    def test_se_exceeds_ta(self, adapter):
        v = FULL_SUPPRESSION
        supp = adapter.compute_suppression(
            ta_intensity=v.inputs["ta_intensity"],
            se_intensity=v.inputs["se_intensity"],
            ta_time=0.0,
            se_time=5.0,
        )
        assert supp.S_k == v.expected["S_k"]
        assert supp.fully_suppressed == v.expected["fully_suppressed"]


class TestOracleInconsistency:
    """§3.3.2: Δ_oracle > ε_consistency → informational"""

    def test_inconsistent_oracles(self, adapter):
        v = ORACLE_INCONSISTENCY
        readings = _make_readings(
            v.inputs["oracle_intensities"],
            v.inputs["oracle_classes"],
        )
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert ta.is_valid  # 2 classes
        assert not ta.is_consistent
        assert ta.informational == v.expected["informational"]


class TestSingleOracleClass:
    """§3.3 + §9.5: Single class → invalid TAₖ"""

    def test_single_class_invalid(self, adapter):
        v = SINGLE_ORACLE_CLASS
        readings = _make_readings(
            v.inputs["oracle_intensities"],
            v.inputs["oracle_classes"],
        )
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert ta.is_valid == v.expected["is_valid"]


class TestSelfInducedRisk:
    """§9.1: self-induced → Tₖ = 0"""

    def test_self_induced_zeroes_tamper(self, adapter):
        v = SELF_INDUCED_RISK
        T_k = adapter.compute_tamper_factor(
            linkage_score=1.0,
            risk_channel="test_channel",
            actor_id="actor-bad",
        )
        assert T_k == v.expected["T_k"]


class TestConsistentOracle:
    """§3.3.1: consistent → min intensity"""

    def test_consistent_min_intensity(self, adapter):
        v = CONSISTENT_ORACLE
        readings = _make_readings(
            v.inputs["oracle_intensities"],
            v.inputs["oracle_classes"],
        )
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, readings)
        assert ta.is_valid == v.expected["is_valid"]
        assert ta.is_consistent == v.expected["is_consistent"]
        assert abs(ta.intensity - v.expected["ta_intensity"]) < 0.01
        assert abs(ta.delta_oracle - v.expected["delta_oracle"]) < 0.01


class TestNoCoverage:
    """§9.4: no data → invalid"""

    def test_empty_readings(self, adapter):
        ta = adapter.validate_threat_activation(1, "test_channel", 0.0, [])
        assert not ta.is_valid


class TestPartialSuppression:
    """§3.6: 0 < Sₖ < 1"""

    def test_partial_suppression_value(self, adapter):
        v = PARTIAL_SUPPRESSION
        supp = adapter.compute_suppression(
            ta_intensity=v.inputs["ta_intensity"],
            se_intensity=v.inputs["se_intensity"],
            ta_time=0.0,
            se_time=5.0,
        )
        assert abs(supp.S_k - v.expected["S_k"]) < 0.001
        assert supp.fully_suppressed == v.expected["fully_suppressed"]
