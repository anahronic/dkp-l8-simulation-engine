"""
Event engine — generates threat activations.

Each zone owns its own engine (RNG fork), so adding a zone never changes
the events of another zone.  Event time is drawn uniformly inside the tick;
it is ground truth and is never passed to the protocol adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from simulation.core.rng import DeterministicRNG


@dataclass(frozen=True)
class ThreatEvent:
    event_id: str
    zone_id: str
    risk_channel: str
    tick: int
    event_time: float           # truth: physical activation time (s)
    true_intensity: float       # truth
    induced_by: Optional[str]   # truth: actor that created the threat, if any


class EventEngine:
    def __init__(self, zone_id: str, rng: DeterministicRNG) -> None:
        self._zone_id = zone_id
        self._rng = rng
        self._counter = 0

    def _new(self, channel: str, tick: int, tick_start: float, tick_seconds: float,
             intensity_range: Tuple[float, float], induced_by: Optional[str]) -> ThreatEvent:
        self._counter += 1
        return ThreatEvent(
            event_id=f"{self._zone_id}:{self._counter:06d}",
            zone_id=self._zone_id,
            risk_channel=channel,
            tick=tick,
            event_time=tick_start + self._rng.uniform() * tick_seconds,
            true_intensity=self._rng.uniform_range(*intensity_range),
            induced_by=induced_by,
        )

    def natural(self, channel: str, tick: int, tick_start: float, tick_seconds: float,
                activation_rate: float, intensity_range: Tuple[float, float]) -> Optional[ThreatEvent]:
        """One activation draw for a channel in this tick."""
        if self._rng.uniform() < activation_rate:
            return self._new(channel, tick, tick_start, tick_seconds, intensity_range, None)
        return None

    def induced(self, channel: str, tick: int, tick_start: float, tick_seconds: float,
                intensity_range: Tuple[float, float], actor_id: str) -> ThreatEvent:
        """A threat created by an actor (risk farming)."""
        return self._new(channel, tick, tick_start, tick_seconds, intensity_range, actor_id)
