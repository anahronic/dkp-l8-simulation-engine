"""
Test vectors — hand-calculated expected values.

Each vector pins one protocol rule to a known output.  Used by
tests/simulation/test_vectors.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class TestVector:
    __test__ = False  # not a pytest class

    name: str
    description: str
    inputs: Dict[str, Any]
    expected: Dict[str, Any]


BASIC_SPD = TestVector(
    name="basic_spd",
    description="§5: SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ",
    inputs={"W_k": 0.9, "ta_intensity": 0.8, "se_intensity": 0.2, "A_k": 1.0, "C_k": 0.95, "T_k": 1.0},
    # S = (0.8 − 0.2) / 0.8 = 0.75; SPD = 0.9 × 0.75 × 1.0 × 0.95 × 1.0 = 0.64125
    expected={"S_k": 0.75, "SPD_k": 0.64125},
)

NO_MEASURED_REDUCTION = TestVector(
    name="no_measured_reduction",
    description="§3.6: SE ≥ TA → Sₖ = 0 (no measured reduction; v1 called this 'fully_suppressed')",
    inputs={"ta_intensity": 0.5, "se_intensity": 0.6},
    expected={"S_k": 0.0},
)

ORACLE_INCONSISTENCY = TestVector(
    name="oracle_inconsistency",
    description="§3.3.2: Δ_oracle > ε → informational",
    inputs={"readings": [("optical", 0.3), ("thermal", 0.8)], "epsilon_consistency": 0.15},
    expected={"valid": True, "consistent": False},
)

SINGLE_ORACLE_CLASS = TestVector(
    name="single_oracle_class",
    description="§3.3 + §9.5: one class → invalid",
    inputs={"readings": [("optical", 0.5), ("optical", 0.52)]},
    expected={"valid": False, "reason": "single_source"},
)

CONSISTENT_ORACLE = TestVector(
    name="consistent_oracle",
    description="§3.3.1: Δ ≤ ε → TA = min(intensities)",
    inputs={"readings": [("optical", 0.50), ("thermal", 0.52), ("lidar", 0.48)], "epsilon_consistency": 0.15},
    expected={"valid": True, "consistent": True, "ta_intensity": 0.48, "delta_oracle": 0.04},
)

NO_COVERAGE = TestVector(
    name="no_coverage",
    description="§9.4: no data → invalid, SPD = 0",
    inputs={"readings": []},
    expected={"valid": False, "reason": "no_data"},
)

PARTIAL_SUPPRESSION = TestVector(
    name="partial_suppression",
    description="§3.6: Sₖ strictly between 0 and 1",
    inputs={"ta_intensity": 1.0, "se_intensity": 0.4},
    expected={"S_k": 0.6},
)

SELF_INDUCED_RISK = TestVector(
    name="self_induced_risk",
    description="§9.1: observed linkage > θ → Tₖ = 0",
    inputs={"linkage_observed": 1.0, "theta": 0.5},
    expected={"T_k": 0.0, "status": "ZERO_MERIT", "reason": "self_induced_linkage"},
)

ALL_VECTORS: List[TestVector] = [
    BASIC_SPD, NO_MEASURED_REDUCTION, ORACLE_INCONSISTENCY, SINGLE_ORACLE_CLASS,
    CONSISTENT_ORACLE, NO_COVERAGE, PARTIAL_SUPPRESSION, SELF_INDUCED_RISK,
]
