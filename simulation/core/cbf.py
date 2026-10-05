"""
Contextual Baseline Field (CBF) — PREVENTION §3.11 / §9.2 (hypothesis H-CBF).

CBFᵢ is an audit-only reference: it never feeds SPDₖ.  The registry keeps
count, mean and M2 (Welford) of the *observed* TA intensity per
zone × risk channel, i.e. of what the oracles reported for valid and
consistent activations, not of the scenario's hidden truth.

Two dispersion estimates are reported under explicit names:
    std_population = sqrt(M2 / n)        (n >= 1)
    std_sample     = sqrt(M2 / (n - 1))  (n >= 2, else null)
Neither is used by any admission decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextualBaselineField:
    zone_id: str
    risk_channel: str
    sample_count: int = 0
    baseline_mean: float = 0.0
    m2: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_populated(self) -> bool:
        return self.sample_count > 0

    @property
    def std_population(self) -> Optional[float]:
        return math.sqrt(self.m2 / self.sample_count) if self.sample_count >= 1 else None

    @property
    def std_sample(self) -> Optional[float]:
        return math.sqrt(self.m2 / (self.sample_count - 1)) if self.sample_count >= 2 else None

    def update(self, x: float) -> None:
        self.sample_count += 1
        delta = x - self.baseline_mean
        self.baseline_mean += delta / self.sample_count
        self.m2 += delta * (x - self.baseline_mean)

    def to_audit_record(self) -> Dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "risk_channel": self.risk_channel,
            "source": "observed_ta_intensity",
            "estimator": "welford_count_mean_m2",
            "sample_count": self.sample_count,
            "baseline_mean": self.baseline_mean,
            "m2": self.m2,
            "std_population": self.std_population,
            "std_sample": self.std_sample,
        }


class CBFRegistry:
    """Baselines per zone × risk channel.  Audit-only — never an SPD input."""

    def __init__(self) -> None:
        self._baselines: Dict[str, ContextualBaselineField] = {}

    @staticmethod
    def _key(zone_id: str, risk_channel: str) -> str:
        return f"{zone_id}|{risk_channel}"

    def get(self, zone_id: str, risk_channel: str) -> Optional[ContextualBaselineField]:
        return self._baselines.get(self._key(zone_id, risk_channel))

    def update(self, zone_id: str, risk_channel: str, observed_intensity: float) -> None:
        key = self._key(zone_id, risk_channel)
        cbf = self._baselines.get(key)
        if cbf is None:
            cbf = ContextualBaselineField(zone_id=zone_id, risk_channel=risk_channel)
            self._baselines[key] = cbf
        cbf.update(observed_intensity)

    def all_records(self) -> List[Dict[str, Any]]:
        return [self._baselines[k].to_audit_record() for k in sorted(self._baselines)]
