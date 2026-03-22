"""
Contextual Baseline Field (CBF) — §3.11 / §9.2 placeholder.

CBFᵢ is an audit-only reference structure that captures the baseline
behavioral context of a zone.  It is NOT a reward input — it exists
solely for post-hoc anomaly analysis and drift detection.

This is an L8 simulation placeholder.  Production implementations
should populate CBF from real zone telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextualBaselineField:
    """
    Audit-only baseline snapshot for one zone — §3.11, §9.2.

    Fields:
        zone_id:       Zone this baseline belongs to
        risk_channel:  Risk channel being baselined
        baseline_mean: Historical mean threat intensity
        baseline_std:  Historical std deviation
        sample_count:  Number of observations in baseline window
        metadata:      Additional audit data (timestamps, version, etc.)
    """
    zone_id: str
    risk_channel: str
    baseline_mean: float = 0.0
    baseline_std: float = 0.0
    sample_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_populated(self) -> bool:
        """True if baseline has at least one observation."""
        return self.sample_count > 0

    def to_audit_record(self) -> Dict[str, Any]:
        """Serialise for audit log — no raw behavioral data."""
        return {
            "zone_id": self.zone_id,
            "risk_channel": self.risk_channel,
            "baseline_mean": round(self.baseline_mean, 6),
            "baseline_std": round(self.baseline_std, 6),
            "sample_count": self.sample_count,
            "metadata": self.metadata,
        }


class CBFRegistry:
    """
    In-memory registry of contextual baselines per zone × risk channel.

    Audit-only — values here MUST NOT feed into SPDₖ calculation.
    """

    def __init__(self) -> None:
        self._baselines: Dict[str, ContextualBaselineField] = {}

    def _key(self, zone_id: str, risk_channel: str) -> str:
        return f"{zone_id}:{risk_channel}"

    def get(self, zone_id: str, risk_channel: str) -> Optional[ContextualBaselineField]:
        return self._baselines.get(self._key(zone_id, risk_channel))

    def update(
        self,
        zone_id: str,
        risk_channel: str,
        observed_intensity: float,
    ) -> None:
        """Update running baseline with a new observation (Welford's algorithm)."""
        key = self._key(zone_id, risk_channel)
        cbf = self._baselines.get(key)
        if cbf is None:
            cbf = ContextualBaselineField(zone_id=zone_id, risk_channel=risk_channel)
            self._baselines[key] = cbf

        cbf.sample_count += 1
        n = cbf.sample_count
        delta = observed_intensity - cbf.baseline_mean
        cbf.baseline_mean += delta / n
        if n > 1:
            delta2 = observed_intensity - cbf.baseline_mean
            # Running variance via Welford
            cbf.baseline_std = (
                ((n - 2) / (n - 1)) * cbf.baseline_std ** 2 + delta * delta2 / n
            ) ** 0.5

    def all_records(self) -> List[Dict[str, Any]]:
        """Export all baselines as audit records."""
        return [cbf.to_audit_record() for cbf in self._baselines.values()]
