"""
Test vectors — deterministic, hand-calculated expected values.

Each vector pins one protocol rule to a known-good output.
Used by the test suite to verify the protocol adapter is exact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class TestVector:
    name: str
    description: str
    inputs: Dict[str, Any]
    expected: Dict[str, Any]


# ── §5: Basic SPD calculation ───────────────────────────────────────────

BASIC_SPD = TestVector(
    name="basic_spd",
    description="§5: SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ — clean scenario",
    inputs={
        "W_k": 0.9,
        "ta_intensity": 0.8,
        "se_intensity": 0.2,
        "A_k": 1.0,
        "C_k": 0.95,
        "T_k": 1.0,
    },
    expected={
        # S_k = clamp(0, 1, (0.8 - 0.2) / 0.8) = 0.75
        "S_k": 0.75,
        # SPD = 0.9 * 0.75 * 1.0 * 0.95 * 1.0 = 0.64125
        "SPD_k": 0.64125,
    },
)


# ── §3.6: Full suppression → SPD = 0 ───────────────────────────────────

FULL_SUPPRESSION = TestVector(
    name="full_suppression",
    description="§3.6: SE ≥ TA → Sₖ = 0, SPDₖ = 0",
    inputs={
        "W_k": 1.0,
        "ta_intensity": 0.5,
        "se_intensity": 0.6,  # SE > TA
        "A_k": 1.0,
        "C_k": 1.0,
        "T_k": 1.0,
    },
    expected={
        "S_k": 0.0,
        "SPD_k": 0.0,
        "fully_suppressed": True,
    },
)


# ── §3.3.2: Oracle inconsistency → informational ───────────────────────

ORACLE_INCONSISTENCY = TestVector(
    name="oracle_inconsistency",
    description="§3.3.2: Δ_oracle > ε_consistency → SPDₖ = informational",
    inputs={
        "oracle_intensities": [0.3, 0.8],  # Δ = 0.5 >> 0.15
        "oracle_classes": ["optical", "thermal"],
        "epsilon_consistency": 0.15,
    },
    expected={
        "informational": True,
        "SPD_k": 0.0,
    },
)


# ── §3.3 + §9.5: Single oracle class → invalid ─────────────────────────

SINGLE_ORACLE_CLASS = TestVector(
    name="single_oracle_class",
    description="§3.3 + §9.5: TAₖ invalid with only 1 oracle class",
    inputs={
        "oracle_intensities": [0.5, 0.52],
        "oracle_classes": ["optical", "optical"],  # same class
    },
    expected={
        "is_valid": False,
        "SPD_k": 0.0,
    },
)


# ── §9.1: Self-induced risk → Tₖ = 0 ──────────────────────────────────

SELF_INDUCED_RISK = TestVector(
    name="self_induced_risk",
    description="§9.1: linkage(subject, TAₖ) > θ → Tₖ = 0",
    inputs={
        "W_k": 0.9,
        "ta_intensity": 0.8,
        "se_intensity": 0.2,
        "A_k": 1.0,
        "C_k": 0.95,
        "linkage_score": 1.0,  # above any reasonable θ
    },
    expected={
        "T_k": 0.0,
        "SPD_k": 0.0,
    },
)


# ── §3.3.1: Consistent regime → min intensity ──────────────────────────

CONSISTENT_ORACLE = TestVector(
    name="consistent_oracle",
    description="§3.3.1: Δ_oracle ≤ ε → TAₖ_intensity = min(intensities)",
    inputs={
        "oracle_intensities": [0.50, 0.52, 0.48],
        "oracle_classes": ["optical", "thermal", "lidar"],
        "epsilon_consistency": 0.15,
    },
    expected={
        "is_valid": True,
        "is_consistent": True,
        "ta_intensity": 0.48,  # min
        "delta_oracle": 0.04,  # 0.52 - 0.48
    },
)


# ── §9.4: No coverage → SPD = 0 ────────────────────────────────────────

NO_COVERAGE = TestVector(
    name="no_coverage",
    description="§9.4: no data → SPDₖ = 0",
    inputs={
        "oracle_intensities": [],
        "oracle_classes": [],
    },
    expected={
        "is_valid": False,
        "SPD_k": 0.0,
    },
)


# ── §3.6: Partial suppression ──────────────────────────────────────────

PARTIAL_SUPPRESSION = TestVector(
    name="partial_suppression",
    description="§3.6: Sₖ between 0 and 1",
    inputs={
        "ta_intensity": 1.0,
        "se_intensity": 0.4,
    },
    expected={
        # S_k = (1.0 - 0.4) / 1.0 = 0.6
        "S_k": 0.6,
        "fully_suppressed": False,
    },
)


# Collect all vectors for iteration
ALL_VECTORS: List[TestVector] = [
    BASIC_SPD,
    FULL_SUPPRESSION,
    ORACLE_INCONSISTENCY,
    SINGLE_ORACLE_CLASS,
    SELF_INDUCED_RISK,
    CONSISTENT_ORACLE,
    NO_COVERAGE,
    PARTIAL_SUPPRESSION,
]
