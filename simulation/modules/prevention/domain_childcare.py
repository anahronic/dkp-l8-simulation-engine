"""
Domain: Childcare — concrete sandbox for DKP-1-PREVENTION-001.

Implements the 6-threat × 5-actor × 4-oracle childcare setting
described in the simulation spec.
"""

from __future__ import annotations

from typing import Dict, List

from simulation.core.actors import Actor, ActorStrategy
from simulation.core.oracles import Oracle, OraclePool
from simulation.core.rng import DeterministicRNG
from simulation.core.zones import Zone, ZoneGenerator
from simulation.modules.prevention.calibration import CHILDCARE_CALIBRATION


# ── Constants ───────────────────────────────────────────────────────────

CHILDCARE_THREATS = [
    "unauthorized_adult_proximity",
    "intrusion",
    "unattended_child_exit",
    "hazardous_trajectory",
    "dangerous_object",
    "congestion_escalation",
]

CHILDCARE_ORACLE_CLASSES = ["optical", "thermal", "lidar", "access"]

CHILDCARE_ACTOR_PROFILES = {
    "patrol_worker": {
        "strategy": ActorStrategy.PATROL,
        "effectiveness": 0.75,
        "response_rate": 0.95,
        "self_induce_rate": 0.0,
        "effectiveness_range": (0.5, 0.9),
    },
    "weak_worker": {
        "strategy": ActorStrategy.WEAK,
        "effectiveness": 0.4,
        "response_rate": 0.6,
        "self_induce_rate": 0.0,
        "effectiveness_range": (0.2, 0.6),
    },
    "passive_bystander": {
        "strategy": ActorStrategy.PASSIVE,
        "effectiveness": 0.0,
        "response_rate": 0.0,
        "self_induce_rate": 0.0,
        "effectiveness_range": None,
    },
    "adversarial_actor": {
        "strategy": ActorStrategy.ADVERSARIAL,
        "effectiveness": 0.5,
        "response_rate": 0.7,
        "self_induce_rate": 0.3,
        "effectiveness_range": None,
    },
    "optimizer_actor": {
        "strategy": ActorStrategy.OPTIMIZER,
        "effectiveness": 0.85,
        "response_rate": 0.9,
        "self_induce_rate": 0.0,
        "effectiveness_range": (0.8, 1.0),
    },
}


# ── Factory functions ───────────────────────────────────────────────────

def create_childcare_oracles(
    rng: DeterministicRNG,
    noise_sigma: float = 0.05,
    dropout_rate: float = 0.0,
    bias_range: tuple = (0.0, 0.0),
) -> OraclePool:
    """Create oracle pool with 4 sensor classes."""
    pool = OraclePool()
    for i, oracle_class in enumerate(CHILDCARE_ORACLE_CLASSES):
        bias = rng.uniform_range(*bias_range) if bias_range != (0.0, 0.0) else 0.0
        pool.add(Oracle(
            oracle_id=f"oracle-{oracle_class}-{i:02d}",
            oracle_class=oracle_class,
            rng=rng.fork(f"oracle-{oracle_class}"),
            noise_sigma=noise_sigma,
            dropout_rate=dropout_rate,
            bias=bias,
        ))
    return pool


def create_childcare_actors(
    rng: DeterministicRNG,
    include_adversarial: bool = False,
) -> List[Actor]:
    """Create actor population for one zone."""
    actors = []
    actor_count = 0
    for name, profile in CHILDCARE_ACTOR_PROFILES.items():
        if not include_adversarial and profile["strategy"] == ActorStrategy.ADVERSARIAL:
            continue
        actor_count += 1
        actors.append(Actor(
            actor_id=f"actor-{name}-{actor_count:03d}",
            strategy=profile["strategy"],
            rng=rng.fork(f"actor-{name}"),
            effectiveness=profile["effectiveness"],
            response_rate=profile["response_rate"],
            self_induce_rate=profile["self_induce_rate"],
            effectiveness_range=profile.get("effectiveness_range"),
        ))
    return actors


def create_childcare_zone(
    zone_gen: ZoneGenerator,
    label: str,
    rng: DeterministicRNG,
    include_adversarial: bool = False,
    noise_sigma: float = 0.05,
    dropout_rate: float = 0.0,
) -> tuple:
    """Create one childcare zone with oracles and actors.

    Returns: (Zone, OraclePool, List[Actor])
    """
    zone = zone_gen.create(
        label=label,
        risk_channels=CHILDCARE_THREATS,
        oracle_ids=[f"oracle-{cls}" for cls in CHILDCARE_ORACLE_CLASSES],
        metadata={"domain": "childcare"},
    )
    oracle_pool = create_childcare_oracles(
        zone.rng,
        noise_sigma=noise_sigma,
        dropout_rate=dropout_rate,
    )
    actors = create_childcare_actors(zone.rng, include_adversarial=include_adversarial)
    zone.actors = actors
    return zone, oracle_pool, actors


def get_threat_weights() -> Dict[str, float]:
    """Return §3.7 Wₖ weights for childcare domain."""
    return dict(CHILDCARE_CALIBRATION.threat_weights)
