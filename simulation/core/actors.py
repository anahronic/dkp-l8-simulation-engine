"""
Actor models — simulated subjects that intervene in zones (PREVENTION §3.4).

Profiles come from the scenario config (domain.actors); nothing about an
actor is fixed in code.  Actor ids are unique across zones
(``<zone_id>/<profile>``), so recurrence counters and subject totals never
merge different subjects.

Each decision draws from a stream addressed by the actor and the event
(``response/<event_id>``), so an actor's behaviour on one event does not
depend on how many other events it saw (audit item U5).

Adversarial actors with ``self_induce_rate > 0`` *create* threats in their
own zone (see EventEngine.induced) and then suppress them (risk farming).
Whether the evaluator detects this linkage is decided by the observation
model in the runner; the actor itself never reports a linkage score.
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
    def __init__(self, actor_id: str, profile: ActorProfile, rng: DeterministicRNG, order: int) -> None:
        self.actor_id = actor_id
        self.profile = profile
        self.order = order            # position in domain.actor_order (used only by list_order)
        self._rng = rng

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def strategy(self) -> ActorStrategy:
        return self.profile.strategy

    @property
    def attribution_claim(self) -> float:
        return self.profile.attribution_claim

    @property
    def induces_threats(self) -> bool:
        return self.profile.strategy == ActorStrategy.ADVERSARIAL and self.profile.self_induce_rate > 0.0

    def decide(self, event_id: str, event_time: float, own_threat: bool) -> Optional[Intervention]:
        """Decide whether and when to intervene on a threat that began at event_time."""
        p = self.profile
        if p.strategy == ActorStrategy.PASSIVE:
            return None
        draws = self._rng.fork(f"response/{event_id}")
        if not own_threat and draws.uniform() >= p.response_rate:
            return None
        delay = draws.uniform_range(*p.response_delay_seconds)
        eff = p.effectiveness
        if p.effectiveness_range is not None:
            eff *= draws.uniform_range(*p.effectiveness_range)
        return Intervention(actor_id=self.actor_id, time=event_time + delay,
                            effectiveness=max(0.0, min(1.0, eff)))
