#!/usr/bin/env python3
"""
Phase 3 adversarial runs — writes outputs/phase3/phase3_results.json.

    python -m simulation.phase3_report [--output-dir DIR] [--days N]

Results describe the synthetic childcare scenario under the hypotheses in
each run's config; they are not statements about any operational system.
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.core.config import config_digest
from simulation.core.oracles import readings_from
from simulation.modules.prevention.adversarial_scenarios import (
    LINKAGE_SWEEP, SE_TA_FRACTIONS, SIMULATED, base_config,
)
from simulation.modules.prevention.protocol_adapter import (
    POSITIVE, ObservedIntervention, PreventionProtocolAdapter, ProtocolParams, suppression_completeness,
)
from simulation.modules.prevention.reporting import dumps, write_text
from simulation.run_prevention_simulation import run_simulation


def _mean(xs: List[float]) -> float:
    return math.fsum(xs) / len(xs) if xs else 0.0


def run_metrics(records: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    pos = [r for r in records if r["status"] == POSITIVE]
    s_vals = [r["factors"]["S"] for r in records if r["factors"]["S"] is not None]
    early = [r for r in records if r["ta"]["time"] is not None and r["intervention_time"] < r["ta"]["time"]]
    early_status: Dict[str, int] = {}
    for r in early:
        early_status[r["status"] + ("/" + r["reason"] if r["reason"] else "")] = \
            early_status.get(r["status"] + ("/" + r["reason"] if r["reason"] else ""), 0) + 1
    return {
        "total_spd": summary["total_spd"],
        "by_status": summary["by_status"],
        "by_reason": summary["by_reason"],
        "events": summary["events"],
        "evaluation": summary["evaluation"],
        "subject_totals": summary["subject_totals"],
        "mean_S_evaluated": _mean(s_vals),
        "mean_ta_intensity_positive": _mean([r["ta"]["intensity"] for r in pos]),
        "spd_pvariance_positive": statistics.pvariance([r["SPD"] for r in pos]) if len(pos) > 1 else 0.0,
        "interventions_before_t0": len(early),
        "interventions_before_t0_by_outcome": dict(sorted(early_status.items())),
    }


def _sweep_adapter() -> PreventionProtocolAdapter:
    cfg = base_config(seed=1, tag="sweep")
    return PreventionProtocolAdapter(ProtocolParams.from_config(cfg))


def linkage_sweep() -> Dict[str, float]:
    """S9: SPD for one recognized intervention as the observed linkage crosses θ."""
    out = {}
    for score in LINKAGE_SWEEP:
        adapter = _sweep_adapter()
        ta = adapter.assess_ta(readings_from([("optical", 0.8), ("thermal", 0.82),
                                              ("lidar", 0.81), ("access", 0.8)], 0.0))
        se = adapter.assess_se(readings_from([("optical", 0.2), ("thermal", 0.2),
                                              ("lidar", 0.2), ("access", 0.2)], 5.0))
        iv = ObservedIntervention("zone-0001/patrol_worker", 0, 2.0, 1.0, score)
        rec = adapter.evaluate_event("e1", "zone-0001", "intrusion", ta, se, [iv])[0]
        out[repr(score)] = rec["SPD"]
    return out


def se_ta_sweep() -> Dict[str, float]:
    """S10: Sₖ as SE/TA crosses 1 — the function is continuous (no jump)."""
    return {repr(f): suppression_completeness(1.0, f) for f in SE_TA_FRACTIONS}


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", default="simulation/outputs/phase3")
    ap.add_argument("--days", type=int, default=10)
    args = ap.parse_args(argv)

    results: Dict[str, Any] = {"schema": "dkp-l8-phase3/1", "scenarios": {}}
    for name, factory in SIMULATED.items():
        variants = factory(num_days=args.days)
        results["scenarios"][name] = {}
        for vname, cfg in variants.items():
            res = run_simulation(cfg, write=False)
            results["scenarios"][name][vname] = {
                "config_digest": config_digest(cfg),
                "seed": cfg["simulation"]["seed"],
                "metrics": run_metrics(res.records, res.summary),
            }
            print(f"{name:22s} {vname:28s} SPD={res.summary['total_spd']:.4f}", flush=True)
    results["scenarios"]["S9_linkage_threshold"] = {"spd_by_linkage": linkage_sweep()}
    results["scenarios"]["S10_se_ta_continuity"] = {"S_by_se_over_ta": se_ta_sweep()}

    os.makedirs(args.output_dir, exist_ok=True)
    path = os.path.join(args.output_dir, "phase3_results.json")
    write_text(path, dumps(results))
    print(f"written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
