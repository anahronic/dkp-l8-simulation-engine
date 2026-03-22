"""
Calibration — parameter ranges and defaults for the prevention protocol.

These map directly to §14 (Simulation Layer L8) of DKP-1-PREVENTION-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class PreventionCalibration:
    """
    All configurable protocol parameters (§14).

    Defaults are conservative — production tuning requires domain
    calibration against real PTL sensor data.
    """
    # § 3.3 — Oracle consistency
    epsilon_consistency: float = 0.15

    # § 3.6 — Temporal alignment window (seconds)
    delta_t_int: float = 30.0

    # § 9.1 — Self-induced risk threshold
    theta_self_induced: float = 0.5

    # § 9.3 — Pattern recurrence decay
    recurrence_decay: float = 0.9

    # § 9.3 — Recurrence threshold (decay starts after this many occurrences)
    recurrence_threshold: int = 3

    # § 9.4 — Coverage floor
    coverage_floor: float = 0.1

    # § 3.7 — Threat severity weights per risk channel
    threat_weights: Dict[str, float] = None

    def __post_init__(self) -> None:
        if self.threat_weights is None:
            self.threat_weights = {}

    def to_dict(self) -> Dict[str, object]:
        return {
            "epsilon_consistency": self.epsilon_consistency,
            "delta_t_int": self.delta_t_int,
            "theta_self_induced": self.theta_self_induced,
            "recurrence_decay": self.recurrence_decay,
            "recurrence_threshold": self.recurrence_threshold,
            "coverage_floor": self.coverage_floor,
            "threat_weights": dict(self.threat_weights),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, object]) -> "PreventionCalibration":
        return cls(
            epsilon_consistency=float(d.get("epsilon_consistency", 0.15)),
            delta_t_int=float(d.get("delta_t_int", 30.0)),
            theta_self_induced=float(d.get("theta_self_induced", 0.5)),
            recurrence_decay=float(d.get("recurrence_decay", 0.9)),
            recurrence_threshold=int(d.get("recurrence_threshold", 3)),
            coverage_floor=float(d.get("coverage_floor", 0.1)),
            threat_weights=d.get("threat_weights", {}),
        )


# ── Preset calibrations ────────────────────────────────────────────────

CHILDCARE_CALIBRATION = PreventionCalibration(
    epsilon_consistency=0.15,
    delta_t_int=30.0,
    theta_self_induced=0.5,
    recurrence_decay=0.9,
    recurrence_threshold=3,
    coverage_floor=0.1,
    threat_weights={
        "unauthorized_adult_proximity": 0.9,
        "intrusion": 1.0,
        "unattended_child_exit": 0.95,
        "hazardous_trajectory": 0.7,
        "dangerous_object": 0.8,
        "congestion_escalation": 0.5,
    },
)

CONSERVATIVE_CALIBRATION = PreventionCalibration(
    epsilon_consistency=0.10,
    delta_t_int=20.0,
    theta_self_induced=0.3,
    recurrence_decay=0.85,
    recurrence_threshold=3,
    coverage_floor=0.15,
)

PERMISSIVE_CALIBRATION = PreventionCalibration(
    epsilon_consistency=0.25,
    delta_t_int=60.0,
    theta_self_induced=0.7,
    recurrence_decay=0.95,
    recurrence_threshold=3,
    coverage_floor=0.05,
)
