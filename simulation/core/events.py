"""
Event engine — generates threat activations from addressed random draws.

Every draw comes from a stream addressed by what it is for (zone, channel,
tick; for induced threats also the creating actor), never from a shared
counter.  Event ids are ``<zone>:<tick>:<channel>`` (natural) and
``<zone>:<tick>:<channel>:induced:<actor>`` (created by an actor); they are
unambiguous because names cannot contain ":" or "/" (config NAME_PATTERN,
audit item V21-N2), and the runner refuses a duplicate id.  Changing one channel's parameters therefore leaves every other
channel's threats unchanged (audit item U5), and event ids are stable
names rather than sequence numbers.

Event time is drawn uniformly inside the tick; it is ground truth and is
never passed to the protocol adapter.
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

    def _event(self, draws: DeterministicRNG, event_id: str, channel: str, tick: int,
               tick_start: float, tick_seconds: float, intensity_range: Tuple[float, float],
               induced_by: Optional[str]) -> ThreatEvent:
        return ThreatEvent(
            event_id=event_id,
            zone_id=self._zone_id,
            risk_channel=channel,
            tick=tick,
            event_time=tick_start + draws.uniform() * tick_seconds,
            true_intensity=draws.uniform_range(*intensity_range),
            induced_by=induced_by,
        )

    def natural(self, channel: str, tick: int, tick_start: float, tick_seconds: float,
                activation_rate: float, intensity_range: Tuple[float, float]) -> Optional[ThreatEvent]:
        """At most one natural activation per channel and tick."""
        draws = self._rng.fork(f"natural/{channel}/{tick}")
        if draws.uniform() < activation_rate:
            return self._event(draws, f"{self._zone_id}:{tick:06d}:{channel}", channel, tick,
                               tick_start, tick_seconds, intensity_range, None)
        return None

    def induced(self, channel: str, tick: int, tick_start: float, tick_seconds: float,
                intensity_range: Tuple[float, float], actor_name: str, actor_id: str,
                rate: float) -> Optional[ThreatEvent]:
        """Risk farming: an actor may create one threat per channel and tick."""
        draws = self._rng.fork(f"induced/{actor_name}/{channel}/{tick}")
        if draws.uniform() < rate:
            return self._event(draws, f"{self._zone_id}:{tick:06d}:{channel}:induced:{actor_name}",
                               channel, tick, tick_start, tick_seconds, intensity_range, actor_id)
        return None
