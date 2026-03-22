"""
Event engine — generates and processes threat activation events.

Protocol-agnostic: produces timestamped events, delegates interpretation
to the protocol adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from simulation.core.rng import DeterministicRNG


class EventType(str, Enum):
    THREAT_ACTIVATION = "threat_activation"
    INTERVENTION = "intervention"
    SUPPRESSION = "suppression"
    ORACLE_READING = "oracle_reading"
    TICK = "tick"


@dataclass
class SimEvent:
    event_id: int
    event_type: EventType
    timestamp: float
    zone_id: str
    payload: Dict[str, Any] = field(default_factory=dict)


class EventEngine:
    """
    Generates threat activation events at configurable rates.

    Each tick, for each zone, the engine probabilistically activates
    threats on configured risk channels.
    """

    def __init__(self, rng: DeterministicRNG) -> None:
        self._rng = rng
        self._event_counter = 0

    def generate_threats(
        self,
        zone_id: str,
        risk_channels: List[str],
        timestamp: float,
        threat_rate: float = 0.3,
        intensity_range: tuple = (0.1, 1.0),
    ) -> List[SimEvent]:
        """Generate threat activations for one tick in one zone."""
        events = []
        for channel in risk_channels:
            if self._rng.uniform() < threat_rate:
                self._event_counter += 1
                intensity = self._rng.uniform_range(*intensity_range)
                events.append(SimEvent(
                    event_id=self._event_counter,
                    event_type=EventType.THREAT_ACTIVATION,
                    timestamp=timestamp,
                    zone_id=zone_id,
                    payload={
                        "risk_channel": channel,
                        "true_intensity": intensity,
                    },
                ))
        return events

    def next_id(self) -> int:
        self._event_counter += 1
        return self._event_counter
