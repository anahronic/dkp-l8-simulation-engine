"""
Oracle models — simulated PTL sensor sources (§3.3).

Oracles produce intensity readings for threat activations.  Each oracle
belongs to one *class* (optical, thermal, lidar, access, …).  The protocol
requires ≥ 2 independent classes for a valid TAₖ.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from simulation.core.rng import DeterministicRNG


@dataclass
class OracleReading:
    oracle_id: str
    oracle_class: str
    intensity: float
    timestamp: float
    confidence: float  # [0,1] — coverage quality


class Oracle:
    """Single simulated sensor source."""

    def __init__(
        self,
        oracle_id: str,
        oracle_class: str,
        rng: DeterministicRNG,
        noise_sigma: float = 0.05,
        bias: float = 0.0,
        dropout_rate: float = 0.0,
    ) -> None:
        self.oracle_id = oracle_id
        self.oracle_class = oracle_class
        self._rng = rng
        self.noise_sigma = noise_sigma
        self.bias = bias
        self.dropout_rate = dropout_rate

    def read(self, true_intensity: float, timestamp: float) -> Optional[OracleReading]:
        """Produce a noisy reading, or None if sensor drops out."""
        if self._rng.uniform() < self.dropout_rate:
            return None  # sensor degradation
        noisy = true_intensity + self.bias + self._rng.gauss(0, self.noise_sigma)
        noisy = max(0.0, noisy)  # intensities non-negative
        conf = max(0.0, min(1.0, 1.0 - self.dropout_rate - abs(self.bias)))
        return OracleReading(
            oracle_id=self.oracle_id,
            oracle_class=self.oracle_class,
            intensity=noisy,
            timestamp=timestamp,
            confidence=conf,
        )


class OraclePool:
    """Manages a set of oracles for a zone."""

    def __init__(self) -> None:
        self._oracles: Dict[str, Oracle] = {}

    def add(self, oracle: Oracle) -> None:
        self._oracles[oracle.oracle_id] = oracle

    def read_all(self, true_intensity: float, timestamp: float) -> List[OracleReading]:
        readings = []
        for oracle in self._oracles.values():
            r = oracle.read(true_intensity, timestamp)
            if r is not None:
                readings.append(r)
        return readings

    @property
    def oracles(self) -> Dict[str, Oracle]:
        return dict(self._oracles)

    def classes(self) -> set:
        return {o.oracle_class for o in self._oracles.values()}
