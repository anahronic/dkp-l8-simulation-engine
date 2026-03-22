"""
Test: Recurrence threshold — F-03 configurable decay onset.

Verifies that the recurrence_threshold parameter controls when
pattern decay begins, not a hardcoded constant.
"""

import pytest

from simulation.modules.prevention.protocol_adapter import PreventionProtocolAdapter


class TestRecurrenceThreshold:
    """§9.3: Configurable recurrence threshold."""

    def test_threshold_3_decay_at_4th(self):
        """With threshold 3, decay starts at 4th recurrence."""
        adapter = PreventionProtocolAdapter(
            epsilon_consistency=0.15,
            delta_t_int=30.0,
            theta_self_induced=0.5,
            recurrence_decay=0.9,
            coverage_floor=0.1,
            recurrence_threshold=3,
        )

        t_values = []
        for _ in range(6):
            T_k = adapter.compute_tamper_factor(
                linkage_score=0.0,
                risk_channel="ch",
                actor_id="a1",
            )
            t_values.append(T_k)

        # First 3 should be 1.0 (no decay)
        assert all(t == 1.0 for t in t_values[:3])
        # 4th should be < 1.0 (decay starts)
        assert t_values[3] < 1.0

    def test_threshold_5_decay_at_6th(self):
        """With threshold 5, decay starts at 6th recurrence."""
        adapter = PreventionProtocolAdapter(
            epsilon_consistency=0.15,
            delta_t_int=30.0,
            theta_self_induced=0.5,
            recurrence_decay=0.9,
            coverage_floor=0.1,
            recurrence_threshold=5,
        )

        t_values = []
        for _ in range(8):
            T_k = adapter.compute_tamper_factor(
                linkage_score=0.0,
                risk_channel="ch",
                actor_id="a1",
            )
            t_values.append(T_k)

        # First 5 should be 1.0 (no decay)
        assert all(t == 1.0 for t in t_values[:5])
        # 6th should be < 1.0 (decay starts)
        assert t_values[5] < 1.0

    def test_threshold_1_immediate_decay(self):
        """With threshold 1, decay starts at 2nd recurrence."""
        adapter = PreventionProtocolAdapter(
            epsilon_consistency=0.15,
            delta_t_int=30.0,
            theta_self_induced=0.5,
            recurrence_decay=0.9,
            coverage_floor=0.1,
            recurrence_threshold=1,
        )

        t_values = []
        for _ in range(4):
            T_k = adapter.compute_tamper_factor(
                linkage_score=0.0,
                risk_channel="ch",
                actor_id="a1",
            )
            t_values.append(T_k)

        assert t_values[0] == 1.0  # 1st occurrence: no decay
        assert t_values[1] < 1.0   # 2nd occurrence: decay starts
