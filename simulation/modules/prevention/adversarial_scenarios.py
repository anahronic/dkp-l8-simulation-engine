"""
Adversarial scenarios — Phase 3 (2026-10-05, revised for 2.1.0), replacing the Phase 2 set.

Every scenario is an overlay on the main scenario config
(configs/prevention_childcare_v0_2.yaml), so the world is declared once.
Each one states what is varied *independently* and what the attacker
controls, because the Phase 2 scenarios did not (see AUDIT_REPORT Phase 3):

    S1  risk_farming        an adversarial subject creates threats and suppresses them;
                            the evaluator sees only an observed linkage score
    S2  ta_inflation        (a) truth scaled  (b) biased TA measurement only
                            (c) biased TA and SE measurements
    S3  joint_suppression   several subjects on one threat; one event-level S, Σ A ≤ 1
    S4  timing_window       Δt_int swept; the window now binds
    S5  attribution_rules   ambiguity_zero / proportional / list_order; actor order reversed
    S6  early_prevention    fast subject vs slow sensors; t₀ by measurement vs registration
    S7  oracle_degradation  bias (now applied), noise, dropout; TTL stress
    S8  oracle_oscillation  low vs high noise
    S9  linkage_threshold   adapter-level sweep through θ (a real step)
    S10 se_ta_continuity    adapter-level sweep of SE/TA through 1 (continuous)
    S11 ttl_reference       TTL applied per signal vs re-applied at the decision instant
    S12 channel_isolation   one channel's activation rate changed; other channels compared
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, List

from simulation.core.config import deep_merge, load_config

MAIN_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "configs", "prevention_childcare_v0_2.yaml")


def base_config(seed: int, num_days: int = 10, num_zones: int = 1, tag: str = "scenario") -> Dict[str, Any]:
    cfg = load_config(MAIN_CONFIG)
    return deep_merge(cfg, {
        "scenario": {"id": f"childcare_v0_2.{tag}"},
        "simulation": {"seed": seed, "num_days": num_days, "num_zones": num_zones},
        "output": {"directory": f"simulation/outputs/phase3/{tag}"},
    })


def _with(cfg: Dict[str, Any], overlay: Dict[str, Any], tag: str) -> Dict[str, Any]:
    out = deep_merge(cfg, overlay)
    out["scenario"]["id"] = f"{cfg['scenario']['id']}.{tag}"
    out["output"]["directory"] = f"{cfg['output']['directory']}/{tag}"
    return out


def _all_actors(cfg: Dict[str, Any], **fields: Any) -> Dict[str, Any]:
    return {"domain": {"actors": {name: dict(fields) for name in cfg["domain"]["actors"]}}}


# ── S1 risk farming ─────────────────────────────────────────────────────

def risk_farming(seed: int = 3001, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s1_risk_farming")
    farm = deep_merge(base, {"domain": {"include_adversarial": True,
                                        "actors": {"adversarial_actor": {"self_induce_rate": 0.1}}}})
    return {
        "detect_0.8": _with(farm, {}, "detect_0.8"),
        "detect_0.0": _with(farm, {"oracles": {"linkage_detection": {"detection_probability": 0.0}}},
                            "detect_0.0"),
        "detect_1.0": _with(farm, {"oracles": {"linkage_detection": {"detection_probability": 1.0}}},
                            "detect_1.0"),
        "detect_0.0_decay_1.0": _with(farm, {
            "oracles": {"linkage_detection": {"detection_probability": 0.0}},
            "protocol": {"recurrence": {"decay": 1.0}}}, "detect_0.0_decay_1.0"),
        "detect_0.0_retrospective": _with(farm, {
            "oracles": {"linkage_detection": {"detection_probability": 0.0}},
            "protocol": {"recurrence": {"history": "retrospective"}}}, "detect_0.0_retrospective"),
        "detect_0.0_window_1d": _with(farm, {
            "oracles": {"linkage_detection": {"detection_probability": 0.0}},
            "protocol": {"recurrence": {"key": ["actor", "zone", "channel"], "window_seconds": 86400}}},
            "detect_0.0_window_1d"),
    }


# ── S2 TA inflation ─────────────────────────────────────────────────────

def ta_inflation(seed: int = 3002, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s2_ta_inflation")
    classes = base["oracles"]["classes"]
    scaled = {"domain": {"channels": {ch: {"intensity_range": [0.8, 1.0]} for ch in base["domain"]["channels"]}}}
    return {
        "baseline": _with(base, {}, "baseline"),
        "a_truth_scaled": _with(base, scaled, "a_truth_scaled"),
        "b_ta_bias_2_classes": _with(base, {"attack": {"oracle_bias": {
            "classes": classes[:2], "bias": 0.1, "phase": "ta"}}}, "b_ta_bias_2_classes"),
        "b_ta_bias_all_classes": _with(base, {"attack": {"oracle_bias": {
            "classes": list(classes), "bias": 0.1, "phase": "ta"}}}, "b_ta_bias_all_classes"),
        "c_both_bias_all_classes": _with(base, {"attack": {"oracle_bias": {
            "classes": list(classes), "bias": 0.1, "phase": "both"}}}, "c_both_bias_all_classes"),
    }


# ── S3 joint suppression ────────────────────────────────────────────────

def joint_suppression(seed: int = 3003, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s3_joint_suppression")
    return {
        "claims_1.0": _with(base, {}, "claims_1.0"),
        "claims_0.4": _with(base, _all_actors(base, attribution_claim=0.4), "claims_0.4"),
    }


# ── S4 timing window ────────────────────────────────────────────────────

def timing_window(seed: int = 3004, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s4_timing_window")
    return {f"dt_{int(dt)}s": _with(base, {"protocol": {"delta_t_int_seconds": dt}}, f"dt_{int(dt)}s")
            for dt in (10.0, 30.0, 60.0, 120.0, 600.0)}


# ── S5 attribution rules ────────────────────────────────────────────────

def _reversed_actors(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Reverse the declared actor order (the only order the engine uses)."""
    out = copy.deepcopy(cfg)
    out["domain"]["actor_order"] = list(reversed(cfg["domain"]["actor_order"]))
    return out


def attribution_rules(seed: int = 3005, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s5_attribution_rules")
    out = {}
    for rule in ("ambiguity_zero", "proportional", "list_order"):
        cfg = _with(base, {"protocol": {"attribution_rule": rule}}, rule)
        out[rule] = cfg
        rev = _reversed_actors(cfg)
        rev["scenario"]["id"] += ".reversed"
        rev["output"]["directory"] += "_reversed"
        out[f"{rule}_reversed"] = rev
    return out


# ── S6 early prevention ─────────────────────────────────────────────────

def early_prevention(seed: int = 3006, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s6_early_prevention")
    slow = {"oracles": {"measurement_delay_seconds": [2.0, 6.0], "arrival_delay_seconds": [5.0, 15.0],
                        "ttl_seconds": {c: 60 for c in base["oracles"]["classes"]}},
            "domain": {"actors": {"optimizer_actor": {"response_delay_seconds": [0.0, 3.0]}}}}
    return {
        "basis_measurement": _with(base, deep_merge(slow, {"protocol": {"ta_time_basis": "measurement"}}),
                                   "basis_measurement"),
        "basis_registration": _with(base, deep_merge(slow, {"protocol": {"ta_time_basis": "registration"}}),
                                    "basis_registration"),
    }


# ── S7 oracle degradation ───────────────────────────────────────────────

def oracle_degradation(seed: int = 3007, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s7_oracle_degradation")
    return {
        "clean": _with(base, {}, "clean"),
        "bias_only": _with(base, {"oracles": {"bias_range": [-0.15, 0.15]}}, "bias_only"),
        "degraded": _with(base, {"oracles": {"bias_range": [-0.15, 0.15], "noise_sigma": 0.25,
                                             "dropout_rate": 0.2}}, "degraded"),
        "slow_arrival_ttl": _with(base, {"oracles": {"arrival_delay_seconds": [0.1, 20.0]}},
                                  "slow_arrival_ttl"),
    }


# ── S8 oracle oscillation ───────────────────────────────────────────────

def oracle_oscillation(seed: int = 3008, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s8_oracle_oscillation")
    return {
        "noise_0.02": _with(base, {"oracles": {"noise_sigma": 0.02}}, "noise_0.02"),
        "noise_0.25": _with(base, {"oracles": {"noise_sigma": 0.25}}, "noise_0.25"),
    }


# ── S11 TTL reference ───────────────────────────────────────────────────

def ttl_reference(seed: int = 3011, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s11_ttl_reference")
    tight = {"oracles": {"ttl_seconds": {c: 5 for c in base["oracles"]["classes"]}}}
    return {
        "signal": _with(base, {"protocol": {"ttl_reference": "signal"}}, "signal"),
        "decision": _with(base, {"protocol": {"ttl_reference": "decision"}}, "decision"),
        "signal_ttl_5s": _with(base, deep_merge(tight, {"protocol": {"ttl_reference": "signal"}}),
                               "signal_ttl_5s"),
        "decision_ttl_5s": _with(base, deep_merge(tight, {"protocol": {"ttl_reference": "decision"}}),
                                 "decision_ttl_5s"),
    }


# ── S12 channel isolation ───────────────────────────────────────────────

ISOLATION_CHANNEL = "unauthorized_adult_proximity"


def channel_isolation(seed: int = 3012, num_days: int = 10) -> Dict[str, Dict[str, Any]]:
    base = base_config(seed, num_days, tag="s12_channel_isolation")
    return {
        "baseline": _with(base, {}, "baseline"),
        "one_channel_rate_x3": _with(base, {"domain": {"channels": {ISOLATION_CHANNEL: {"activation_rate": 0.75}}}},
                                     "one_channel_rate_x3"),
    }


SIMULATED: Dict[str, Any] = {
    "S1_risk_farming": risk_farming,
    "S2_ta_inflation": ta_inflation,
    "S3_joint_suppression": joint_suppression,
    "S4_timing_window": timing_window,
    "S5_attribution_rules": attribution_rules,
    "S6_early_prevention": early_prevention,
    "S7_oracle_degradation": oracle_degradation,
    "S8_oracle_oscillation": oracle_oscillation,
    "S11_ttl_reference": ttl_reference,
    "S12_channel_isolation": channel_isolation,
}

# S9 and S10 are adapter-level sweeps; see simulation/phase3_report.py.
LINKAGE_SWEEP: List[float] = [0.45, 0.49, 0.5, 0.500001, 0.51, 0.55]
SE_TA_FRACTIONS: List[float] = [0.9, 0.99, 0.999, 0.9999, 1.0, 1.0001, 1.01]
