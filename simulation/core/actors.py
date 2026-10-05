"""
Actor models — simulated subjects that intervene in zones (PREVENTION §3.4).

Profiles come from the scenario config (domain.actors); nothing about an
actor is fixed in code.  Actor ids are unique across zones
(``<zone_id>/<profile>``), so recurrence counters and subject totals never
merge different subjects.

Adversarial actors with ``self_induce_rate > 0`` *create* threats in their
own zone and then suppress them (risk farming).  Whether the evaluator
detects this linkage is decided by the observation model in the runner; the
actor itself never reports a linkage score.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from simulation.core.rng import DeterministicRNG


class ActorStrategy(str, Enum):
    PATROL = "patrol"            # responds often, moderate effectiveness
    WEAK = "weak"                # responds sometimes, low effectiveness
    PASSIVE = "passive"          # never responds
    ADVERSARIAL = "adversarial"  # may create threats and suppress them
    OPTIMIZER = "optimizer"      # fast and effective responder


@dataclass(frozen=True)
class ActorProfile:
    name: str
    strategy: ActorStrategy
    effectiveness: float
    effectiveness_range: Optional[Tuple[float, float]]
    response_rate: float
    response_delay_seconds: Tuple[float, float]
    attribution_claim: float
    self_induce_rate: float

    @classmethod
    def from_config(cls, name: str, spec: Dict[str, Any]) -> "ActorProfile":
        rng_range = spec["effectiveness_range"]
        return cls(
            name=name,
            strategy=ActorStrategy(spec["strategy"]),
            effectiveness=float(spec["effectiveness"]),
            effectiveness_range=None if rng_range is None else (float(rng_range[0]), float(rng_range[1])),
            response_rate=float(spec["response_rate"]),
            response_delay_seconds=(float(spec["response_delay_seconds"][0]),
                                    float(spec["response_delay_seconds"][1])),
            attribution_claim=float(spec["attribution_claim"]),
            self_induce_rate=float(spec["self_induce_rate"]),
        )


@dataclass(frozen=True)
class Intervention:
    actor_id: str
    time: float           # simulation seconds
    effectiveness: float  # fraction of the current intensity removed, [0, 1]


class Actor:
    def __init__(self, actor_id: str, profile: ActorProfile, rng: DeterministicRNG) -> None:
        self.actor_id = actor_id
        self.profile = profile
        self._rng_response = rng.fork("response")
        self._rng_create = rng.fork("create")

    @property
    def strategy(self) -> ActorStrategy:
        return self.profile.strategy

    @property
    def attribution_claim(self) -> float:
        return self.profile.attribution_claim

    def creates_threat(self) -> bool:
        """Risk farming: does this actor create a threat on a channel this tick?"""
        if self.profile.strategy != ActorStrategy.ADVERSARIAL or self.profile.self_induce_rate <= 0.0:
            return False
        return self._rng_create.uniform() < self.profile.self_induce_rate

    def decide(self, event_time: float, own_threat: bool) -> Optional[Intervention]:
        """Decide whether and when to intervene on a threat that began at event_time."""
        p = self.profile
        if p.strategy == ActorStrategy.PASSIVE:
            return None
        if not own_threat and self._rng_response.uniform() >= p.response_rate:
            return None
        delay = self._rng_response.uniform_range(*p.response_delay_seconds)
        eff = p.effectiveness
        if p.effectiveness_range is not None:
            eff *= self._rng_response.uniform_range(*p.effectiveness_range)
        return Intervention(actor_id=self.actor_id, time=event_time + delay,
                            effectiveness=max(0.0, min(1.0, eff)))
