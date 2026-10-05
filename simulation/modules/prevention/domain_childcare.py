"""
Domain: Childcare — synthetic sandbox for DKP-1-PREVENTION-001.

Everything about the domain (channels, weights, actor profiles, sensor
classes) comes from the scenario config.  This module only assembles
zones; it holds no parameter values of its own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from simulation.core.actors import Actor, ActorProfile, ActorStrategy
from simulation.core.oracles import Oracle, OraclePool
from simulation.core.rng import DeterministicRNG
from simulation.core.zones import Zone, ZoneGenerator


def create_oracles(zone: Zone, rng: DeterministicRNG, cfg: Dict[str, Any]) -> OraclePool:
    """One oracle per declared class; bias drawn from bias_range; optional attack bias."""
    orc = cfg["oracles"]
    attack = cfg["attack"]["oracle_bias"]
    lo, hi = orc["bias_range"]
    pool = OraclePool()
    for i, cls in enumerate(orc["classes"]):
        orng = rng.fork(f"oracle-{cls}")
        bias = orng.uniform_range(lo, hi) if (lo, hi) != (0, 0) else 0.0
        attack_bias: Dict[str, float] = {}
        if attack is not None and cls in attack["classes"]:
            phases = ("ta", "se") if attack["phase"] == "both" else (attack["phase"],)
            attack_bias = {ph: float(attack["bias"]) for ph in phases}
        pool.add(Oracle(
            oracle_id=f"{zone.zone_id}/oracle-{cls}-{i:02d}",
            oracle_class=cls,
            rng=orng,
            noise_sigma=float(orc["noise_sigma"]),
            bias=bias,
            dropout_rate=float(orc["dropout_rate"]),
            measurement_delay=tuple(orc["measurement_delay_seconds"]),
            arrival_delay=tuple(orc["arrival_delay_seconds"]),
            attack_bias=attack_bias,
        ))
    return pool


def create_actors(zone: Zone, rng: DeterministicRNG, cfg: Dict[str, Any]) -> List[Actor]:
    """Actors in declared profile order; ids are unique across zones."""
    include_adv = cfg["domain"]["include_adversarial"]
    actors = []
    for name, spec in cfg["domain"]["actors"].items():
        profile = ActorProfile.from_config(name, spec)
        if profile.strategy == ActorStrategy.ADVERSARIAL and not include_adv:
            continue
        actor_id = f"{zone.zone_id}/{name}"
        actors.append(Actor(actor_id, profile, rng.fork(f"actor-{name}")))
    return actors


def create_zone(zone_gen: ZoneGenerator, label: str, cfg: Dict[str, Any]) -> Tuple[Zone, OraclePool, List[Actor]]:
    zone = zone_gen.create(
        label=label,
        risk_channels=list(cfg["domain"]["channels"]),
        oracle_ids=list(cfg["oracles"]["classes"]),
        metadata={"domain": cfg["domain"]["name"]},
    )
    pool = create_oracles(zone, zone.rng.fork("oracles"), cfg)
    actors = create_actors(zone, zone.rng.fork("actors"), cfg)
    zone.actors = actors
    return zone, pool, actors
