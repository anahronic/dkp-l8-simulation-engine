"""
Time contract of the simulation (hypothesis H-TIME-1).

    simulation clock     SI seconds since the start of simulated day 0
    tick                 fixed step of ``tick_seconds``; ticks partition the civil day
    civil day            DKP-0-TIME-001 base unit; reported as DTI-Day (= JDN)

DKP-0-TIME-001 defines only days (§4.1) and does not define sub-day units.
The tick length, event offsets and sensor delays are therefore scenario
hypotheses, declared in the config and listed in the run manifest.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict

from simulation.core.config import SECONDS_PER_DAY


@dataclass(frozen=True)
class TimeBase:
    tick_seconds: float
    ticks_per_day: int
    start_dti_day: int

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "TimeBase":
        return cls(
            tick_seconds=float(cfg["time"]["tick_seconds"]),
            ticks_per_day=int(cfg["simulation"]["ticks_per_day"]),
            start_dti_day=int(cfg["time"]["start_dti_day"]),
        )

    def tick_start(self, tick: int) -> float:
        """Simulation time (s) at which a tick begins."""
        return tick * self.tick_seconds

    def dti_day(self, t_seconds: float) -> int:
        """DKP-0-TIME-001 DTI-Day containing simulation time t."""
        return self.start_dti_day + int(math.floor(t_seconds / SECONDS_PER_DAY))
