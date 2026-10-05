#!/usr/bin/env python3
"""
Phase 3 adversarial runs — writes phase3_results.json and phase3_provenance.json.

    python -m simulation.phase3_report [--output-dir DIR] [--days N]

phase3_results.json is self-contained (audit item R1):
    package            engine version, engine code digest, actual spec digests,
                       the reproducibility-relevant arguments (days)
    scenarios.*.*      for every variant: the full resolved input (config without
                       output path), input_id, result_id and metrics
    content_sha256     SHA-256 of canonical_json(document without this field)

Machine, Python, git commit, elapsed time and output path go to
phase3_provenance.json; they are not part of the reproducible content.

Results describe the synthetic childcare scenario under the hypotheses in
each run's config; they are not statements about any operational system.
"""

from __future__ import annotations

import argparse
import datetime
import math
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.core.config import run_inputs
from simulation.core.manifest import engine_identity, platform_provenance, seal
from simulation.core.oracles import readings_from
from simulation.modules.prevention.adversarial_scenarios import (
    ISOLATION_CHANNEL, LINKAGE_SWEEP, SE_TA_FRACTIONS, SIMULATED, base_config,
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
        k = r["status"] + ("/" + r["reason"] if r["reason"] else "")
        early_status[k] = early_status.get(k, 0) + 1
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
        ta = readings_from([("optical", 0.8), ("thermal", 0.82), ("lidar", 0.81), ("access", 0.8)], 0.0)
        se = readings_from([("optical", 0.2), ("thermal", 0.2), ("lidar", 0.2), ("access", 0.2)], 5.0)
        iv = ObservedIntervention("zone-0001/patrol_worker", 0, 2.0, 1.0, score)
        rec = adapter.evaluate_event("e1", "zone-0001", "intrusion", ta, se, [iv])[0]
        out[repr(score)] = rec["SPD"]
    return out


def se_ta_sweep() -> Dict[str, float]:
    """S10: Sₖ as SE/TA crosses 1 — the function is continuous (no jump)."""
    return {repr(f): suppression_completeness(1.0, f) for f in SE_TA_FRACTIONS}


def isolation_check(a_records: List[Dict[str, Any]], b_records: List[Dict[str, Any]],
                    changed_channel: str) -> Dict[str, Any]:
    """S12: records of channels whose parameters did not change must be identical
    (apart from epistemic.scope_ref, which names the variant)."""
    def strip(r):
        return dict(r, epistemic={k: v for k, v in r["epistemic"].items() if k != "scope_ref"})

    def other(recs):
        return {(r["event_id"], r["actor_id"]): strip(r) for r in recs if r["risk_channel"] != changed_channel}
    a, b = other(a_records), other(b_records)
    common = set(a) & set(b)
    return {
        "unchanged_channel_records_a": len(a),
        "unchanged_channel_records_b": len(b),
        "identical": a == b,
        "differing_common_records": sum(1 for k in common if a[k] != b[k]),
        "only_in_a": len(set(a) - set(b)),
        "only_in_b": len(set(b) - set(a)),
    }


def build_results(days: int) -> Dict[str, Any]:
    identity = engine_identity()
    scenarios: Dict[str, Any] = {}
    raw: Dict[str, Dict[str, Any]] = {}
    for name, factory in SIMULATED.items():
        scenarios[name] = {}
        raw[name] = {}
        for vname, cfg in factory(num_days=days).items():
            res = run_simulation(cfg, write=False)
            raw[name][vname] = res
            scenarios[name][vname] = {
                "inputs": run_inputs(cfg),
                "input_id": res.manifest["input_id"],
                "result_id": res.manifest["result_id"],
                "metrics": run_metrics(res.records, res.summary),
            }
            print(f"{name:22s} {vname:28s} SPD={res.summary['total_spd']:.4f}", flush=True)
    iso = raw["S12_channel_isolation"]
    scenarios["S12_channel_isolation"]["comparison"] = isolation_check(
        iso["baseline"].records, iso["one_channel_rate_x3"].records, ISOLATION_CHANNEL)
    scenarios["S9_linkage_threshold"] = {"spd_by_linkage": linkage_sweep()}
    scenarios["S10_se_ta_continuity"] = {"S_by_se_over_ta": se_ta_sweep()}
    return seal({
        "schema": "dkp-l8-phase3/2",
        "package": {**identity, "generator": "simulation.phase3_report", "arguments": {"days": days}},
        "scenarios": scenarios,
    })


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", default="simulation/outputs/phase3")
    ap.add_argument("--days", type=int, default=10)
    args = ap.parse_args(argv)
    t0 = time.time()
    results = build_results(args.days)
    os.makedirs(args.output_dir, exist_ok=True)
    path = os.path.join(args.output_dir, "phase3_results.json")
    write_text(path, dumps(results))
    write_text(os.path.join(args.output_dir, "phase3_provenance.json"), dumps({
        **platform_provenance(),
        "elapsed_seconds": time.time() - t0,
        "output_dir": os.path.abspath(args.output_dir),
        "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "argv": sys.argv,
        "results_content_sha256": results["content_sha256"],
    }))
    print(f"written {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
