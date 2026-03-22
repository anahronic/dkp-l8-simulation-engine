"""
Zone generator — creates and manages Protected Zones (§3.1).

A zone is a physically bounded evaluation domain with its own RNG fork,
oracle set, risk channels, and actor population.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from simulation.core.rng import DeterministicRNG


@dataclass
class Zone:
    zone_id: str
    label: str
    rng: DeterministicRNG
    risk_channels: List[str] = field(default_factory=list)
    actors: list = field(default_factory=list)
    oracle_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)


class ZoneGenerator:
    """
    Protocol-agnostic zone factory.

    Each zone gets a deterministic RNG fork keyed by its id, so zone
    ordering does not affect randomness of peer zones.
    """

    def __init__(self, master_rng: DeterministicRNG) -> None:
        self._master = master_rng
        self._counter = 0

    def create(
        self,
        label: str,
        risk_channels: Optional[List[str]] = None,
        oracle_ids: Optional[List[str]] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> Zone:
        self._counter += 1
        zid = f"zone-{self._counter:04d}"
        child_rng = self._master.fork(zid)
        return Zone(
            zone_id=zid,
            label=label,
            rng=child_rng,
            risk_channels=risk_channels or [],
            oracle_ids=oracle_ids or [],
            metadata=metadata or {},
        )
