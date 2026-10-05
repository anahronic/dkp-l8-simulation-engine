"""
Oracle models — simulated PTL sensor sources (PREVENTION §3.3, ORACLE §9).

Each reading carries three times (hypothesis H-TIME-3):

    event time      when the physical state existed (truth; never in a reading)
    measured_at     when the sensor sampled the state
    received_at     when the record reached the evaluator

A sensor samples the true intensity *at measured_at*, so an intervention
that happens before the sample is already visible in the measurement.
The evaluator applies the per-class TTL (ORACLE §9) to the age of each
reading; it never sees the true intensity.

Each observation draws from a stream addressed by sensor, event and phase
(``<event_id>/<phase>``): a dropout or an extra event never shifts the
noise of another measurement (audit item U5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from simulation.core.rng import DeterministicRNG

IntensityAt = Callable[[float], float]


@dataclass(frozen=True)
class OracleReading:
    oracle_id: str
    oracle_class: str
    intensity: float
    measured_at: float
    received_at: float
    confidence: float  # sensor self-reported quality in [0, 1]


class Oracle:
    """Single simulated sensor source."""

    def __init__(
        self,
        oracle_id: str,
        oracle_class: str,
        rng: DeterministicRNG,
        noise_sigma: float,
        bias: float,
        dropout_rate: float,
        measurement_delay: Tuple[float, float],
        arrival_delay: Tuple[float, float],
        attack_bias: Optional[Dict[str, float]] = None,
    ) -> None:
        self.oracle_id = oracle_id
        self.oracle_class = oracle_class
        self._rng = rng
        self.noise_sigma = noise_sigma
        self.bias = bias
        self.dropout_rate = dropout_rate
        self.measurement_delay = tuple(measurement_delay)
        self.arrival_delay = tuple(arrival_delay)
        # attack_bias: {"ta": x, "se": y} — added only for the given phase
        self.attack_bias = dict(attack_bias or {})

    def observe(self, intensity_at: IntensityAt, after: float, phase: str,
                event_id: str) -> Optional[OracleReading]:
        """Sample the state after time ``after``; None if the sensor drops out."""
        draws = self._rng.fork(f"{event_id}/{phase}")
        if draws.uniform() < self.dropout_rate:
            return None
        measured_at = after + draws.uniform_range(*self.measurement_delay)
        received_at = measured_at + draws.uniform_range(*self.arrival_delay)
        noise = draws.gauss(0.0, self.noise_sigma)
        value = intensity_at(measured_at) + self.bias + self.attack_bias.get(phase, 0.0) + noise
        conf = max(0.0, min(1.0, 1.0 - self.dropout_rate - abs(self.bias)))
        return OracleReading(
            oracle_id=self.oracle_id,
            oracle_class=self.oracle_class,
            intensity=max(0.0, value),
            measured_at=measured_at,
            received_at=received_at,
            confidence=conf,
        )


class OraclePool:
    """The sensors of one zone, in declared class order."""

    def __init__(self) -> None:
        self._oracles: Dict[str, Oracle] = {}

    def add(self, oracle: Oracle) -> None:
        self._oracles[oracle.oracle_id] = oracle

    def observe_all(self, intensity_at: IntensityAt, after: float, phase: str,
                    event_id: str) -> List[OracleReading]:
        readings = []
        for oracle in self._oracles.values():
            r = oracle.observe(intensity_at, after, phase, event_id)
            if r is not None:
                readings.append(r)
        return readings

    @property
    def oracles(self) -> Dict[str, Oracle]:
        return dict(self._oracles)

    def classes(self) -> List[str]:
        return [o.oracle_class for o in self._oracles.values()]


def constant(value: float) -> IntensityAt:
    """Helper for tests: a state that does not change over time."""
    return lambda _t: value


def make_reading(oracle_class: str, intensity: float, measured_at: float = 0.0,
                 received_at: Optional[float] = None, confidence: float = 1.0,
                 oracle_id: Optional[str] = None) -> OracleReading:
    """Helper for tests and hand vectors."""
    return OracleReading(
        oracle_id=oracle_id or f"oracle-{oracle_class}",
        oracle_class=oracle_class,
        intensity=intensity,
        measured_at=measured_at,
        received_at=measured_at if received_at is None else received_at,
        confidence=confidence,
    )


def readings_from(pairs: Sequence[Tuple[str, float]], measured_at: float = 0.0) -> List[OracleReading]:
    return [make_reading(c, v, measured_at) for c, v in pairs]
