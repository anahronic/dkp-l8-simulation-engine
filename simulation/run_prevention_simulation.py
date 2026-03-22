#!/usr/bin/env python3
"""
DKP L8 Simulation Engine — CLI entry point.

Runs a complete DKP-1-PREVENTION-001 v1.0 simulation using the
childcare domain sandbox (or any configured domain).

Usage:
    python -m simulation.run_prevention_simulation --config CONFIG
    python -m simulation.run_prevention_simulation --smoke
    python -m simulation.run_prevention_simulation --config CONFIG --seed 123 --zones 5 --days 60

Arguments:
    --config PATH     YAML config file
    --smoke           Run fast smoke test (ignores --config)
    --seed INT        Override simulation seed
    --zones INT       Override number of zones
    --days INT        Override number of simulated days
    --output-dir DIR  Override output directory
    --verbose         Print tick-level progress
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

# Ensure package root is importable when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.core.rng import DeterministicRNG
from simulation.core.zones import ZoneGenerator
from simulation.core.events import EventEngine, EventType, SimEvent
from simulation.core.metrics import MetricsCollector, MetricRecord
from simulation.core.config import load_config, save_config_snapshot, merge_cli_overrides
from simulation.modules.prevention.protocol_adapter import PreventionProtocolAdapter
from simulation.modules.prevention.domain_childcare import (
    CHILDCARE_THREATS,
    create_childcare_zone,
    get_threat_weights,
)
from simulation.modules.prevention.scenarios import ThreatProfile
from simulation.core.cbf import CBFRegistry


def build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="DKP L8 Prevention Simulation Engine",
    )
    p.add_argument("--config", type=str, help="Path to YAML config file")
    p.add_argument("--smoke", action="store_true", help="Fast smoke test")
    p.add_argument("--seed", type=int, default=None, help="Override seed")
    p.add_argument("--zones", type=int, default=None, help="Override zone count")
    p.add_argument("--days", type=int, default=None, help="Override day count")
    p.add_argument("--output-dir", type=str, default=None, help="Override output dir")
    p.add_argument("--verbose", action="store_true", help="Tick-level logging")
    return p


def resolve_config(args) -> Dict[str, Any]:
    """Load config from file or use smoke defaults."""
    if args.smoke:
        smoke_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "configs", "prevention_childcare_fast_smoke.yaml",
        )
        cfg = load_config(smoke_path)
    elif args.config:
        cfg = load_config(args.config)
    else:
        print("ERROR: Provide --config or --smoke", file=sys.stderr)
        sys.exit(1)

    # Apply CLI overrides
    overrides = {}
    if args.seed is not None:
        overrides["simulation"] = {**cfg.get("simulation", {}), "seed": args.seed}
    if args.zones is not None:
        sim = overrides.get("simulation", dict(cfg.get("simulation", {})))
        sim["num_zones"] = args.zones
        overrides["simulation"] = sim
    if args.days is not None:
        sim = overrides.get("simulation", dict(cfg.get("simulation", {})))
        sim["num_days"] = args.days
        overrides["simulation"] = sim
    if args.output_dir is not None:
        overrides["output"] = {**cfg.get("output", {}), "directory": args.output_dir}

    for key, val in overrides.items():
        cfg[key] = val

    return cfg


def run_simulation(cfg: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    """
    Execute the full simulation loop.

    Returns the summary dict.
    """
    sim_cfg = cfg["simulation"]
    proto_cfg = cfg["protocol"]
    domain_cfg = cfg["domain"]
    oracle_cfg = cfg.get("oracles", {})
    output_cfg = cfg.get("output", {})

    seed = sim_cfg["seed"]
    num_zones = sim_cfg["num_zones"]
    num_days = sim_cfg["num_days"]
    ticks_per_day = sim_cfg["ticks_per_day"]
    total_ticks = num_days * ticks_per_day

    # 1. Deterministic RNG
    master_rng = DeterministicRNG(seed)

    # 2. Protocol adapter
    adapter = PreventionProtocolAdapter(
        epsilon_consistency=proto_cfg["epsilon_consistency"],
        delta_t_int=proto_cfg["delta_t_int"],
        theta_self_induced=proto_cfg["theta_self_induced"],
        recurrence_decay=proto_cfg["recurrence_decay"],
        coverage_floor=proto_cfg["coverage_floor"],
        recurrence_threshold=proto_cfg.get("recurrence_threshold", 3),
        threat_weights=domain_cfg.get("threat_weights", {}),
    )

    # 3. Zone generator
    zone_gen = ZoneGenerator(master_rng)
    zones_data = []
    for z in range(num_zones):
        zone, oracle_pool, actors = create_childcare_zone(
            zone_gen=zone_gen,
            label=f"childcare-facility-{z+1:03d}",
            rng=master_rng.fork(f"zone-setup-{z}"),
            include_adversarial=domain_cfg.get("include_adversarial", False),
            noise_sigma=oracle_cfg.get("noise_sigma", 0.05),
            dropout_rate=oracle_cfg.get("dropout_rate", 0.0),
        )
        zones_data.append((zone, oracle_pool, actors))

    # 4. Event engine
    event_engine = EventEngine(master_rng.fork("events"))

    # 5. Metrics
    metrics = MetricsCollector()

    # 6. Threat profiles from config
    threat_profiles: Dict[str, Dict] = domain_cfg.get("threat_profiles", {})

    # 7. CBF registry — §3.11 / §9.2 audit-only baseline (F-09)
    cbf_registry = CBFRegistry()

    # 8. Failure-path probabilities (F-04, F-05) — default 0 preserves normal behavior
    se_ge_ta_probability = sim_cfg.get("se_ge_ta_probability", 0.0)
    temporal_invalid_probability = sim_cfg.get("temporal_invalid_probability", 0.0)
    se_delay_min = sim_cfg.get("se_delay_min", 1.0)  # F-06

    # ── Main simulation loop ────────────────────────────────────────────
    t_start = time.time()

    for tick in range(total_ticks):
        timestamp = float(tick)

        for zone, oracle_pool, actors in zones_data:
            # Generate threats per risk channel
            for channel in zone.risk_channels:
                tp = threat_profiles.get(channel, {})
                act_rate = tp.get("activation_rate", 0.25)
                int_range = tuple(tp.get("intensity_range", [0.2, 0.8]))

                threats = event_engine.generate_threats(
                    zone_id=zone.zone_id,
                    risk_channels=[channel],
                    timestamp=timestamp,
                    threat_rate=act_rate,
                    intensity_range=int_range,
                )

                for threat_event in threats:
                    true_intensity = threat_event.payload["true_intensity"]

                    # §3.11 / §9.2: Update CBF baseline (audit-only)
                    cbf_registry.update(zone.zone_id, channel, true_intensity)

                    # Oracle readings
                    readings = oracle_pool.read_all(true_intensity, timestamp)

                    # Validate TAₖ
                    ta = adapter.validate_threat_activation(
                        event_id=threat_event.event_id,
                        risk_channel=channel,
                        timestamp=timestamp,
                        readings=readings,
                    )

                    # §6: Per-event attribution budget — Σ Aₖ ≤ 1
                    remaining_attribution = 1.0

                    # Each actor may respond
                    for actor in actors:
                        intervention = actor.decide_intervention(
                            threat_intensity=ta.intensity,
                            timestamp=timestamp,
                        )

                        if not intervention.responded:
                            continue

                        # §6: Clamp attribution to remaining budget
                        proposed_share = actor.attribution_share
                        actual_share = min(proposed_share, remaining_attribution)
                        remaining_attribution -= actual_share

                        if actual_share <= 0.0:
                            continue  # budget exhausted for this event

                        # F-04: SE ≥ TA path — configurable escalation
                        if se_ge_ta_probability > 0.0 and zone.rng.uniform() < se_ge_ta_probability:
                            se_intensity = ta.intensity * zone.rng.uniform_range(1.0, 1.5)
                        else:
                            se_intensity = max(
                                0.0,
                                ta.intensity - intervention.suppression_intensity,
                            )

                        # F-05: Temporal invalidity path — configurable
                        if temporal_invalid_probability > 0.0 and zone.rng.uniform() < temporal_invalid_probability:
                            se_time = timestamp + zone.rng.uniform_range(
                                proto_cfg["delta_t_int"] + 1.0,
                                proto_cfg["delta_t_int"] * 2.0,
                            )
                        else:
                            se_time = timestamp + zone.rng.uniform_range(
                                se_delay_min,
                                proto_cfg["delta_t_int"],
                            )

                        # Compute SPDₖ
                        spd = adapter.compute_spd(
                            event_id=threat_event.event_id,
                            zone_id=zone.zone_id,
                            ta=ta,
                            se_intensity=se_intensity,
                            se_time=se_time,
                            actor_id=actor.actor_id,
                            attribution_share=actual_share,
                            linkage_score=intervention.linkage_score,
                        )

                        # Record metrics
                        metric_name = "SPD_informational" if spd.informational else "SPD"
                        metrics.record(MetricRecord(
                            timestamp=timestamp,
                            zone_id=zone.zone_id,
                            event_id=threat_event.event_id,
                            metric_name=metric_name,
                            value=spd.SPD_k,
                            details={
                                "W_k": spd.W_k,
                                "S_k": spd.S_k,
                                "A_k": spd.A_k,
                                "C_k": spd.C_k,
                                "T_k": spd.T_k,
                                "actor_id": spd.actor_id,
                                "risk_channel": spd.risk_channel,
                                "informational": spd.informational,
                                **spd.details,
                            },
                        ))

                        if spd.SPD_k > 0:
                            metrics.add_subject_contribution(actor.actor_id, spd.SPD_k)

        if verbose and tick % ticks_per_day == 0:
            day = tick // ticks_per_day + 1
            print(f"  Day {day}/{num_days} — {len(metrics.records)} records", flush=True)

    elapsed = time.time() - t_start

    # ── Output ──────────────────────────────────────────────────────────
    output_dir = output_cfg.get("directory", "simulation/outputs/default")
    metrics.write_outputs(output_dir)
    save_config_snapshot(cfg, output_dir)

    # §3.11: Write CBF audit records (non-reward)
    cbf_path = os.path.join(output_dir, "cbf_baselines.json")
    with open(cbf_path, "w") as f:
        json.dump(cbf_registry.all_records(), f, indent=2)

    summary = metrics.summary()
    summary["elapsed_seconds"] = round(elapsed, 3)
    summary["seed"] = seed
    summary["total_ticks"] = total_ticks
    summary["num_zones"] = num_zones

    # Write summary JSON
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()
    cfg = resolve_config(args)

    print("=" * 60)
    print("DKP L8 Simulation Engine — DKP-1-PREVENTION-001 v1.0")
    print("=" * 60)

    sim = cfg["simulation"]
    print(f"  Seed:   {sim['seed']}")
    print(f"  Zones:  {sim['num_zones']}")
    print(f"  Days:   {sim['num_days']}")
    print(f"  Ticks:  {sim['num_days'] * sim['ticks_per_day']}")
    print()

    summary = run_simulation(cfg, verbose=args.verbose)

    print()
    print("─" * 60)
    print("Run complete.")
    print(f"  Total metric records: {summary['total_metric_records']}")
    print(f"  SPD events (positive): {summary['positive_spd_events']}")
    print(f"  SPD events (zero):     {summary['zero_spd_events']}")
    print(f"  Informational events:  {summary['informational_events']}")
    print(f"  Total SPD value:       {summary['total_spd_value']}")
    print(f"  Subject count:         {summary['subject_count']}")
    print(f"  Elapsed:               {summary['elapsed_seconds']}s")
    print()

    output_dir = cfg.get("output", {}).get("directory", "simulation/outputs/default")
    print(f"  Output: {output_dir}/")
    print("─" * 60)


if __name__ == "__main__":
    main()
