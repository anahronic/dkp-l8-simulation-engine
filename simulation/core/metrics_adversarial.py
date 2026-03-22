"""
Adversarial Metrics — DKP-1-PREVENTION-001 v1.0 Audit Phase 2.

Computes the Phase 2 analysis metrics from raw simulation output.
All metrics are read-only derivations; no protocol logic is modified.

Metrics:
    total_spd               — Σ SPD_k (non-informational)
    spd_per_actor           — actor_id → cumulative SPD
    spd_variance            — variance of per-event SPD values
    spd_gradient_near_thresholds — max |Δ SPD| over small param perturbations
    attribution_efficiency  — Σ SPD_k / Σ (W_k × S_k × A_k × C_k)   (T_k ratio)
    temporal_sensitivity_index — fraction of events lost to temporal invalidity
    oracle_sensitivity_index   — fraction of events downgraded to informational
"""

from __future__ import annotations

import json
import os
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional


# ── Loading helpers ─────────────────────────────────────────────────────

def load_metrics_records(output_dir: str) -> List[Dict[str, Any]]:
    """Load per-event metrics records from output_dir/metrics.json."""
    path = os.path.join(output_dir, "metrics.json")
    with open(path) as f:
        return json.load(f)


def load_summary(output_dir: str) -> Dict[str, Any]:
    """Load run summary from output_dir/summary.json."""
    path = os.path.join(output_dir, "summary.json")
    with open(path) as f:
        return json.load(f)


# ── Core metric computations ────────────────────────────────────────────

def compute_adversarial_metrics(
    summary: Dict[str, Any],
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Derive all Phase 2 adversarial metrics from a completed simulation run.

    Parameters
    ----------
    summary : dict
        Output of MetricsCollector.summary() (from summary.json).
    records : list
        Full per-event records list (from metrics.json).

    Returns
    -------
    dict with keys:
        total_spd, spd_per_actor, spd_variance,
        spd_gradient_near_thresholds (placeholder — needs two runs),
        attribution_efficiency, temporal_sensitivity_index,
        oracle_sensitivity_index, over_attribution_events (count),
        informational_fraction, zero_spd_fraction.
    """
    spd_records    = [r for r in records if r["metric_name"] == "SPD"]
    info_records   = [r for r in records if r["metric_name"] == "SPD_informational"]
    total_records  = len(records)

    spd_values     = [r["value"] for r in spd_records]
    total_spd      = sum(spd_values)

    # ── spd_per_actor ──
    spd_per_actor: Dict[str, float] = defaultdict(float)
    for r in spd_records:
        aid = r.get("details", {}).get("actor_id", "unknown")
        spd_per_actor[aid] += r["value"]

    # ── spd_variance ──
    spd_variance = statistics.variance(spd_values) if len(spd_values) > 1 else 0.0

    # ── attribution_efficiency = Σ SPD / Σ (W × S × A × C) ──
    # denominator is the "potential SPD" before tamper factor
    potential_spd_sum = 0.0
    for r in spd_records:
        d = r.get("details", {})
        W = d.get("W_k", 0.0)
        S = d.get("S_k", 0.0)
        A = d.get("A_k", 0.0)
        C = d.get("C_k", 0.0)
        potential_spd_sum += W * S * A * C

    attribution_efficiency = (
        total_spd / potential_spd_sum if potential_spd_sum > 0.0 else 0.0
    )

    # ── temporal_sensitivity_index ──
    # Fraction of SPD records that were zero due to temporal invalidity
    temporal_invalid_count = sum(
        1 for r in spd_records
        if r.get("details", {}).get("reason") == "temporal_invalid"
    )
    temporal_sensitivity_index = (
        temporal_invalid_count / len(spd_records) if spd_records else 0.0
    )

    # ── oracle_sensitivity_index ──
    # Fraction of all metric events that were informational
    informational_fraction = (
        len(info_records) / total_records if total_records > 0 else 0.0
    )
    oracle_sensitivity_index = informational_fraction

    # ── over_attribution_events ──
    # Events where Σ(TA-SE_k) > TA for actors with positive SPD
    # (each actor computes se independently against original TA)
    by_event: Dict[int, List[Dict]] = defaultdict(list)
    for r in spd_records:
        by_event[r["event_id"]].append(r)

    over_attribution_count = 0
    for event_id, ev_records in by_event.items():
        positive_contributors = [r for r in ev_records if r["value"] > 0]
        if len(positive_contributors) < 2:
            continue
        # Check if multiple actors contributed with se below individual TA
        ta_intensity = positive_contributors[0].get("details", {}).get("ta_intensity", 0.0)
        implied_suppressions = []
        for r in positive_contributors:
            se = r.get("details", {}).get("se_intensity", ta_intensity)
            implied_suppressions.append(ta_intensity - se)
        total_implied = sum(s for s in implied_suppressions if s > 0)
        if ta_intensity > 0 and total_implied > ta_intensity:
            over_attribution_count += 1

    # ── zero_spd_fraction ──
    zero_spd_count = sum(1 for v in spd_values if v == 0.0)
    zero_spd_fraction = zero_spd_count / len(spd_values) if spd_values else 0.0

    # ── spd_gradient_near_thresholds ──
    # Placeholder: requires two runs with parameter variation.
    # Populated by compute_spd_gradient() below.
    spd_gradient_near_thresholds = None

    return {
        "total_spd":                     round(total_spd, 6),
        "spd_per_actor":                 {k: round(v, 6) for k, v in spd_per_actor.items()},
        "spd_variance":                  round(spd_variance, 8),
        "spd_gradient_near_thresholds":  spd_gradient_near_thresholds,
        "attribution_efficiency":        round(attribution_efficiency, 6),
        "temporal_sensitivity_index":    round(temporal_sensitivity_index, 6),
        "oracle_sensitivity_index":      round(oracle_sensitivity_index, 6),
        "over_attribution_events":       over_attribution_count,
        "informational_fraction":        round(informational_fraction, 6),
        "zero_spd_fraction":             round(zero_spd_fraction, 6),
        "total_spd_events":              len(spd_records),
        "total_informational_events":    len(info_records),
    }


def compute_spd_gradient(spd_a: float, spd_b: float,
                          param_a: float, param_b: float) -> float:
    """
    Numerical gradient: |ΔSPD| / |Δparam|.

    Use to measure sensitivity near threshold boundaries.
    Returns infinity if param delta is zero.
    """
    dp = param_b - param_a
    if abs(dp) < 1e-12:
        return float("inf")
    return abs(spd_b - spd_a) / abs(dp)


def temporal_spd_profile(
    records: List[Dict[str, Any]],
    num_buckets: int = 4,
) -> List[float]:
    """
    Split run into equal time buckets and return mean SPD per bucket.

    Used to detect recurrence-driven SPD decay across risk farming cycles.
    """
    spd_records = [r for r in records if r["metric_name"] == "SPD"]
    if not spd_records:
        return [0.0] * num_buckets

    timestamps = [r["timestamp"] for r in spd_records]
    t_min, t_max = min(timestamps), max(timestamps)
    span = t_max - t_min

    if span == 0.0:
        mean_v = statistics.mean(r["value"] for r in spd_records)
        return [mean_v] * num_buckets

    bucket_size = span / num_buckets
    buckets: List[List[float]] = [[] for _ in range(num_buckets)]

    for r in spd_records:
        idx = min(int((r["timestamp"] - t_min) / bucket_size), num_buckets - 1)
        buckets[idx].append(r["value"])

    return [
        round(statistics.mean(b), 8) if b else 0.0
        for b in buckets
    ]


def linkage_spd_sweep(
    adapter,
    ta,
    se_intensity: float,
    se_time: float,
    actor_id: str,
    attribution_share: float,
    linkage_values: Optional[List[float]] = None,
) -> Dict[float, float]:
    """
    Sweep linkage_score through theta boundary, return {linkage_score: SPD_k}.

    Requires a fresh adapter instance per call (clears recurrence counts).
    """
    if linkage_values is None:
        linkage_values = [round(0.45 + i * 0.01, 3) for i in range(11)]

    results = {}
    for ls in linkage_values:
        result = adapter.compute_spd(
            event_id=1,
            zone_id="sweep-zone",
            ta=ta,
            se_intensity=se_intensity,
            se_time=se_time,
            actor_id=actor_id,
            attribution_share=attribution_share,
            linkage_score=ls,
        )
        results[ls] = round(result.SPD_k, 8)
        # Reset recurrence counter so each linkage value gets same T_k baseline
        adapter._pattern_counts.clear()

    return results


def se_ta_boundary_sweep(
    adapter,
    ta,
    ta_intensity: float,
    se_fractions: Optional[List[float]] = None,
    se_time: float = 1.0,
    actor_id: str = "sweep-actor",
    attribution_share: float = 1.0,
) -> Dict[float, float]:
    """
    Sweep SE = fraction × TA across the SE=TA boundary.

    Returns {se_fraction: SPD_k}.
    """
    if se_fractions is None:
        se_fractions = [round(0.90 + i * 0.01, 3) for i in range(21)]  # 0.90→1.10

    results = {}
    for frac in se_fractions:
        se_intensity = frac * ta_intensity
        result = adapter.compute_spd(
            event_id=1,
            zone_id="sweep-zone",
            ta=ta,
            se_intensity=se_intensity,
            se_time=se_time,
            actor_id=actor_id,
            attribution_share=attribution_share,
            linkage_score=0.0,
        )
        results[frac] = round(result.SPD_k, 8)
        adapter._pattern_counts.clear()

    return results
