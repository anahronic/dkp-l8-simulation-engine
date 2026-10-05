"""Shared helpers for the PREVENTION bench tests (imported by test modules)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


from simulation.core.config import deep_merge, load_config
from simulation.core.oracles import make_reading
from simulation.modules.prevention.protocol_adapter import (
    ObservedIntervention, PreventionProtocolAdapter, ProtocolParams,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN = os.path.join(ROOT, "simulation", "configs", "prevention_childcare_v0_2.yaml")
SMOKE = os.path.join(ROOT, "simulation", "configs", "prevention_childcare_fast_smoke.yaml")
CLASSES = ["optical", "thermal", "lidar", "access"]


def main_config(overlay: Optional[Dict[str, Any]] = None, days: int = 2, zones: int = 1,
                seed: int = 7, out: str = "simulation/outputs/test") -> Dict[str, Any]:
    cfg = deep_merge(load_config(MAIN), {"simulation": {"num_days": days, "num_zones": zones, "seed": seed},
                                         "output": {"directory": out}})
    return deep_merge(cfg, overlay or {})


def adapter_for(overlay: Optional[Dict[str, Any]] = None) -> PreventionProtocolAdapter:
    return PreventionProtocolAdapter(ProtocolParams.from_config(main_config(overlay)))


def ta_readings(values, t: float = 0.0):
    return [make_reading(c, v, measured_at=t) for c, v in zip(CLASSES, values)]


def iv(actor: str, order: int = 0, time: float = 2.0, claim: float = 1.0,
       linkage: float = 0.0) -> ObservedIntervention:
    return ObservedIntervention(f"zone-0001/{actor}", order, time, claim, linkage)
