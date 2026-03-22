"""
Threat scenarios — configurable scenario generators for prevention simulation.

Each scenario defines threat generation rates, intensity distributions,
and actor response patterns for one simulation run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from simulation.core.rng import DeterministicRNG


@dataclass
class ThreatProfile:
    """Probability and intensity profile for one risk channel."""
    risk_channel: str
    activation_rate: float           # probability per tick
    intensity_range: Tuple[float, float] = (0.1, 1.0)
    recurrence_factor: float = 1.0   # modulates repeat probability


@dataclass
class Scenario:
    """Complete scenario definition."""
    name: str
    description: str
    threat_profiles: List[ThreatProfile] = field(default_factory=list)
    num_zones: int = 1
    ticks_per_day: int = 24
    num_days: int = 30
    oracle_noise_sigma: float = 0.05
    oracle_dropout_rate: float = 0.0
    oracle_bias_range: Tuple[float, float] = (0.0, 0.0)
    metadata: Dict[str, object] = field(default_factory=dict)


# ── Scenario presets ────────────────────────────────────────────────────

def baseline_scenario(
    risk_channels: List[str],
    num_zones: int = 1,
    num_days: int = 30,
) -> Scenario:
    """Standard scenario — moderate threat rates, clean oracles."""
    profiles = [
        ThreatProfile(
            risk_channel=ch,
            activation_rate=0.25,
            intensity_range=(0.2, 0.8),
        )
        for ch in risk_channels
    ]
    return Scenario(
        name="baseline",
        description="Baseline scenario — moderate threats, clean sensors",
        threat_profiles=profiles,
        num_zones=num_zones,
        num_days=num_days,
    )


def high_threat_scenario(
    risk_channels: List[str],
    num_zones: int = 1,
    num_days: int = 30,
) -> Scenario:
    """Elevated threat activation — stress-tests intervention capacity."""
    profiles = [
        ThreatProfile(
            risk_channel=ch,
            activation_rate=0.6,
            intensity_range=(0.4, 1.0),
        )
        for ch in risk_channels
    ]
    return Scenario(
        name="high_threat",
        description="Elevated threat rates — stress test",
        threat_profiles=profiles,
        num_zones=num_zones,
        num_days=num_days,
        oracle_noise_sigma=0.08,
    )


def noisy_oracle_scenario(
    risk_channels: List[str],
    num_zones: int = 1,
    num_days: int = 30,
) -> Scenario:
    """Degraded oracle quality — tests oracle consistency § 3.3."""
    profiles = [
        ThreatProfile(
            risk_channel=ch,
            activation_rate=0.3,
            intensity_range=(0.2, 0.9),
        )
        for ch in risk_channels
    ]
    return Scenario(
        name="noisy_oracle",
        description="High sensor noise — tests informational downgrades",
        threat_profiles=profiles,
        num_zones=num_zones,
        num_days=num_days,
        oracle_noise_sigma=0.20,
        oracle_dropout_rate=0.1,
        oracle_bias_range=(-0.05, 0.05),
    )


def adversarial_scenario(
    risk_channels: List[str],
    num_zones: int = 1,
    num_days: int = 30,
) -> Scenario:
    """Contains self-inducing adversarial actors — tests §9.1."""
    profiles = [
        ThreatProfile(
            risk_channel=ch,
            activation_rate=0.35,
            intensity_range=(0.3, 0.9),
        )
        for ch in risk_channels
    ]
    return Scenario(
        name="adversarial",
        description="Adversarial actors — tests self-induced risk (§9.1)",
        threat_profiles=profiles,
        num_zones=num_zones,
        num_days=num_days,
        metadata={"adversarial_actor_fraction": 0.2},
    )


def smoke_scenario(
    risk_channels: List[str],
) -> Scenario:
    """Minimal scenario for fast validation."""
    profiles = [
        ThreatProfile(
            risk_channel=ch,
            activation_rate=0.5,
            intensity_range=(0.3, 0.7),
        )
        for ch in risk_channels
    ]
    return Scenario(
        name="smoke",
        description="Smoke test — minimal run",
        threat_profiles=profiles,
        num_zones=1,
        ticks_per_day=4,
        num_days=2,
    )
