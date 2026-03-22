"""
Actor models — simulated subjects that intervene in zones (§3.4).

Each actor has a *strategy* that determines how (and whether) they respond
to threat activations.  The protocol requires Subject-linked Interventions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from simulation.core.rng import DeterministicRNG


class ActorStrategy(str, Enum):
    PATROL = "patrol"          # always responds, moderate effectiveness
    WEAK = "weak"              # sometimes responds, low effectiveness
    PASSIVE = "passive"        # never responds
    ADVERSARIAL = "adversarial"  # may induce threats
    OPTIMIZER = "optimizer"    # responds strategically for max SPD


@dataclass
class InterventionResult:
    actor_id: str
    responded: bool
    suppression_intensity: float  # how much risk was reduced
    timestamp: float
    linkage_score: float = 0.0   # §9.1: continuous linkage [0,1], compared against θ


@dataclass
class Actor:
    actor_id: str
    strategy: ActorStrategy
    rng: DeterministicRNG
    effectiveness: float = 0.7     # base suppression capability [0,1]
    response_rate: float = 0.9     # probability of responding
    self_induce_rate: float = 0.0  # probability of self-inducing threat
    attribution_share: float = 1.0 # Aₖ for this actor
    effectiveness_range: tuple = None  # F-08: per-strategy (lo, hi) multiplier

    def decide_intervention(
        self,
        threat_intensity: float,
        timestamp: float,
    ) -> InterventionResult:
        """Decide whether to intervene and how effectively."""

        if self.strategy == ActorStrategy.PASSIVE:
            return InterventionResult(
                actor_id=self.actor_id,
                responded=False,
                suppression_intensity=0.0,
                timestamp=timestamp,
            )

        if self.strategy == ActorStrategy.ADVERSARIAL:
            # Adversarial actors sometimes induce threats (flagged)
            if self.rng.uniform() < self.self_induce_rate:
                return InterventionResult(
                    actor_id=self.actor_id,
                    responded=True,
                    suppression_intensity=threat_intensity * self.effectiveness * 0.5,
                    timestamp=timestamp,
                    linkage_score=1.0,  # §9.1: high linkage → T_k = 0
                )

        # For patrol, weak, optimizer, adversarial (non-inducing)
        if self.rng.uniform() > self.response_rate:
            return InterventionResult(
                actor_id=self.actor_id,
                responded=False,
                suppression_intensity=0.0,
                timestamp=timestamp,
            )

        # Effectiveness varies by strategy — configurable via effectiveness_range
        eff = self.effectiveness
        if self.effectiveness_range is not None:
            eff *= self.rng.uniform_range(*self.effectiveness_range)

        suppression = threat_intensity * min(1.0, eff)

        return InterventionResult(
            actor_id=self.actor_id,
            responded=True,
            suppression_intensity=suppression,
            timestamp=timestamp,
            linkage_score=0.0,
        )
