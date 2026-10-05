#!/usr/bin/env python3
"""
DKP L8 research bench for DKP-1-PREVENTION-001 — CLI entry point.

Usage:
    python -m simulation.run_prevention_simulation --config CONFIG [--output-dir DIR]
    python -m simulation.run_prevention_simulation --smoke
    python -m simulation.run_prevention_simulation --config CONFIG --seed 123 --zones 5 --days 60

Every key of the config is required (schema version 2).  Output files:
    metrics.jsonl, metrics.csv, cbf_baselines.json, summary.json   result core
    config_resolved.json, run_manifest.json                        identity
    summary.txt, run_log.json                                      for humans / diagnostics
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.core.cbf import CBFRegistry
from simulation.core.config import (
    apply_cli_overrides, load_config, run_inputs, validate_config,
)
from simulation.core.events import EventEngine, ThreatEvent
from simulation.core.manifest import build_manifest
from simulation.core.rng import DeterministicRNG
from simulation.core.timebase import TimeBase
from simulation.core.zones import ZoneGenerator
from simulation.modules.prevention.domain_childcare import create_zone
from simulation.modules.prevention.hypotheses import active_hypotheses
from simulation.modules.prevention.protocol_adapter import (
    ObservedIntervention, PreventionProtocolAdapter, ProtocolParams,
)
from simulation.modules.prevention.reporting import (
    dumps, summarize, summary_text, write_records, write_text,
)

SMOKE_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "configs", "prevention_childcare_fast_smoke.yaml")


@dataclass
class RunResult:
    records: List[Dict[str, Any]]
    summary: Dict[str, Any]
    cbf: List[Dict[str, Any]]
    recurrence: Dict[str, int]
    manifest: Optional[Dict[str, Any]] = None
    output_dir: Optional[str] = None


def _intensity_at(event: ThreatEvent, interventions: List[Any]):
    """Truth: intensity over time, reduced by each intervention from its time on (H-SUP)."""
    steps = sorted((iv.time, iv.effectiveness) for iv in interventions)

    def at(t: float) -> float:
        value = event.true_intensity
        for t_i, eff in steps:
            if t_i <= t:
                value *= (1.0 - eff)
        return value
    return at


def run_simulation(cfg: Dict[str, Any], write: bool = True,
                   cli_overrides: Optional[Dict[str, Any]] = None) -> RunResult:
    """Validate the config, run the scenario, optionally write the output files."""
    validate_config(cfg)
    tb = TimeBase.from_config(cfg)
    sim = cfg["simulation"]
    channels = cfg["domain"]["channels"]
    linkage = cfg["oracles"]["linkage_detection"]
    total_ticks = sim["num_days"] * sim["ticks_per_day"]

    master = DeterministicRNG(sim["seed"])
    params = ProtocolParams.from_config(cfg)
    adapter = PreventionProtocolAdapter(params)

    zone_gen = ZoneGenerator(master)
    zones = []
    for z in range(sim["num_zones"]):
        zone, pool, actors = create_zone(zone_gen, f"{cfg['domain']['name']}-facility-{z + 1:03d}", cfg)
        zones.append((zone, pool, actors, EventEngine(zone.zone_id, zone.rng.fork("events")),
                      zone.rng.fork("linkage-observation")))

    cbf = CBFRegistry()
    records: List[Dict[str, Any]] = []
    stats = {"threats_total": 0, "threats_natural": 0, "threats_induced": 0,
             "ta_valid_consistent": 0, "ta_informational": 0, "ta_invalid": 0,
             "with_responders": 0}

    t_start = time.time()
    for tick in range(total_ticks):
        tick_start = tb.tick_start(tick)
        for zone, pool, actors, engine, link_rng in zones:
            events: List[ThreatEvent] = []
            for ch, spec in channels.items():
                rng_range = (float(spec["intensity_range"][0]), float(spec["intensity_range"][1]))
                ev = engine.natural(ch, tick, tick_start, tb.tick_seconds,
                                    float(spec["activation_rate"]), rng_range)
                if ev is not None:
                    events.append(ev)
                for actor in actors:
                    if actor.creates_threat():
                        events.append(engine.induced(ch, tick, tick_start, tb.tick_seconds,
                                                     rng_range, actor.actor_id))

            for ev in events:
                stats["threats_total"] += 1
                stats["threats_induced" if ev.induced_by else "threats_natural"] += 1

                # physics: who acts, when, how strongly (truth)
                ivs = []
                for order, actor in enumerate(actors):
                    iv = actor.decide(ev.event_time, own_threat=(ev.induced_by == actor.actor_id))
                    if iv is not None:
                        ivs.append((order, actor, iv))
                truth_at = _intensity_at(ev, [iv for _, _, iv in ivs])

                # observation: TA readings
                ta = adapter.assess_ta(pool.observe_all(truth_at, ev.event_time, "ta"))
                if ta.valid and ta.consistent:
                    stats["ta_valid_consistent"] += 1
                    cbf.update(zone.zone_id, ev.risk_channel, ta.intensity)
                elif ta.valid:
                    stats["ta_informational"] += 1
                else:
                    stats["ta_invalid"] += 1
                if not ivs:
                    continue
                stats["with_responders"] += 1

                # observation: linkage score per responder (H-L)
                observed = []
                for order, actor, iv in ivs:
                    if ev.induced_by == actor.actor_id and link_rng.uniform() < linkage["detection_probability"]:
                        score = link_rng.uniform_range(*linkage["detected_score_range"])
                    else:
                        score = link_rng.uniform_range(*linkage["undetected_score_range"])
                    observed.append(ObservedIntervention(actor.actor_id, order, iv.time,
                                                         actor.attribution_claim, score))

                # observation: SE readings after the last in-window intervention
                se_start = adapter.se_measurement_start(ta, observed)
                se = None
                if se_start is not None:
                    se = adapter.assess_se(pool.observe_all(truth_at, se_start, "se"))

                truth_eff = {actor.actor_id: iv.effectiveness for _, actor, iv in ivs}
                for rec in adapter.evaluate_event(ev.event_id, zone.zone_id, ev.risk_channel,
                                                  ta, se, observed):
                    rec["tick"] = tick
                    rec["dti_day"] = tb.dti_day(tick_start)
                    rec["truth"] = {
                        "event_time": ev.event_time,
                        "true_intensity": ev.true_intensity,
                        "self_induced": ev.induced_by is not None,
                        "own_threat": ev.induced_by == rec["actor_id"],
                        "effectiveness": truth_eff[rec["actor_id"]],
                    }
                    records.append(rec)
    elapsed = time.time() - t_start

    summary = summarize(records, stats, cfg["scenario"]["id"])
    result = RunResult(records=records, summary=summary, cbf=cbf.all_records(),
                       recurrence=adapter.recurrence.snapshot())
    if write:
        out = cfg["output"]["directory"]
        os.makedirs(out, exist_ok=True)
        write_records(out, records)
        write_text(os.path.join(out, "cbf_baselines.json"), dumps(result.cbf))
        write_text(os.path.join(out, "summary.json"), dumps(summary))
        write_text(os.path.join(out, "summary.txt"), summary_text(summary))
        write_text(os.path.join(out, "config_resolved.json"), dumps(run_inputs(cfg)))
        manifest = build_manifest(cfg, out, active_hypotheses(cfg), cli_overrides or {})
        write_text(os.path.join(out, "run_manifest.json"), dumps(manifest))
        write_text(os.path.join(out, "run_log.json"), dumps({
            "elapsed_seconds": elapsed,
            "output_dir": os.path.abspath(out),
            "finished_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "argv": sys.argv,
        }))
        result.manifest = manifest
        result.output_dir = out
    return result


# ── CLI ─────────────────────────────────────────────────────────────────

def build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DKP L8 research bench for DKP-1-PREVENTION-001")
    p.add_argument("--config", type=str, help="Path to YAML config file")
    p.add_argument("--smoke", action="store_true", help="Fast smoke test")
    p.add_argument("--seed", type=int, default=None, help="Override seed")
    p.add_argument("--zones", type=int, default=None, help="Override zone count")
    p.add_argument("--days", type=int, default=None, help="Override day count")
    p.add_argument("--output-dir", type=str, default=None, help="Override output dir")
    return p


def _safe_stdout() -> None:
    """Never fail at the end of a run because the console cannot print a character."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[List[str]] = None) -> int:
    _safe_stdout()
    args = build_cli().parse_args(argv)
    if args.smoke:
        path = SMOKE_CONFIG
    elif args.config:
        path = args.config
    else:
        print("ERROR: provide --config or --smoke", file=sys.stderr)
        return 1
    overrides = {k: v for k, v in (("seed", args.seed), ("zones", args.zones),
                                   ("days", args.days), ("output_dir", args.output_dir))
                 if v is not None}
    cfg = apply_cli_overrides(load_config(path), **overrides)
    result = run_simulation(cfg, write=True, cli_overrides=overrides)
    s, m = result.summary, result.manifest
    print("DKP L8 research bench - DKP-1-PREVENTION-001")
    print(f"  scenario:  {s['scenario_id']}  seed {cfg['simulation']['seed']}")
    print(f"  records:   {s['records_total']}  " +
          "  ".join(f"{k}={v}" for k, v in s["by_status"].items()))
    print(f"  total SPD: {s['total_spd']:.6f}")
    print(f"  input_id:  {m['input_id']}")
    print(f"  result_id: {m['result_id']}")
    print(f"  output:    {result.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
