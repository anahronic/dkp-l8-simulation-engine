"""
Adversarial Incentive Scenarios — DKP-1-PREVENTION-001 v1.0 Audit Phase 2.

Defines 10 scenario configuration generators that probe rational-exploit
vectors in the prevention protocol.  Each scenario targets a specific
incentive vulnerability.

All configs explicitly define all protocol parameters (no implicit defaults).
Use-case: imported by tests and the Phase 2 audit reporting layer.
"""

from __future__ import annotations

from typing import Any, Dict


# ── Invariant thresholds ────────────────────────────────────────────────

# Scenario 1 — Risk Farming
# SPD in last quarter of run must be < this multiplier × first quarter mean
SPD_GROWTH_RATE_THRESHOLD: float = 1.0   # monotonic decay expected

# Scenario 4 — Timing Arbitrage
# Ratio of max-SPD to min-SPD across all timing variants must be bounded
MAX_TIMING_SPD_RATIO: float = 10.0       # SPD is timing-flat inside window

# Scenario 9 — Linkage Threshold Sensitivity
# SPD must drop to 0 at linkage_score > theta — the step IS the invariant
LINKAGE_JUMP_IS_CLIFF: bool = True       # cliff at θ is correct protocol behaviour

# Scenario 10 — SE ≥ TA Boundary
# Discontinuity at SE=TA is a known protocol property — must be flagged
BOUNDARY_DISCONTINUITY_EXPECTED: bool = True

# Scenarios 7/8 — Oracle
ORACLE_MIN_SPD: float = 0.0              # SPD must never go negative


# ── Internal helpers ────────────────────────────────────────────────────

_THREAT_CHANNELS: list[str] = [
    "unauthorized_adult_proximity",
    "intrusion",
    "unattended_child_exit",
    "hazardous_trajectory",
    "dangerous_object",
    "congestion_escalation",
]

_THREAT_WEIGHTS: Dict[str, float] = {
    "unauthorized_adult_proximity": 0.9,
    "intrusion": 1.0,
    "unattended_child_exit": 0.95,
    "hazardous_trajectory": 0.7,
    "dangerous_object": 0.8,
    "congestion_escalation": 0.5,
}


def _threat_profiles(activation_rate: float = 0.5,
                     intensity_lo: float = 0.3,
                     intensity_hi: float = 0.7) -> Dict[str, Any]:
    return {
        ch: {"activation_rate": activation_rate,
             "intensity_range": [intensity_lo, intensity_hi]}
        for ch in _THREAT_CHANNELS
    }


def _proto(*, recurrence_threshold: int = 3, recurrence_decay: float = 0.9,
           theta: float = 0.5, epsilon: float = 0.15,
           delta_t_int: float = 30.0, coverage_floor: float = 0.1
           ) -> Dict[str, Any]:
    return {
        "epsilon_consistency": epsilon,
        "delta_t_int": delta_t_int,
        "theta_self_induced": theta,
        "recurrence_decay": recurrence_decay,
        "recurrence_threshold": recurrence_threshold,
        "coverage_floor": coverage_floor,
    }


def _sim(seed: int, num_days: int = 10, ticks_per_day: int = 8,
         se_ge_ta: float = 0.0, temporal_invalid: float = 0.0,
         se_delay_min: float = 1.0) -> Dict[str, Any]:
    return {
        "seed": seed,
        "num_zones": 1,
        "num_days": num_days,
        "ticks_per_day": ticks_per_day,
        "se_ge_ta_probability": se_ge_ta,
        "temporal_invalid_probability": temporal_invalid,
        "se_delay_min": se_delay_min,
    }


def _oracles(noise_sigma: float = 0.05, dropout_rate: float = 0.0,
             bias_lo: float = 0.0, bias_hi: float = 0.0) -> Dict[str, Any]:
    return {"noise_sigma": noise_sigma, "dropout_rate": dropout_rate,
            "bias_range": [bias_lo, bias_hi]}


def _domain(threat_profiles: Dict[str, Any],
            include_adversarial: bool = False) -> Dict[str, Any]:
    return {
        "name": "childcare",
        "include_adversarial": include_adversarial,
        "threat_weights": _THREAT_WEIGHTS,
        "threat_profiles": threat_profiles,
    }


def _output(tag: str) -> Dict[str, Any]:
    return {"directory": f"/tmp/dkp-l8-{tag}"}


# ── Scenario 1: Risk Farming ────────────────────────────────────────────

def risk_farming_config(seed: int = 1001, num_days: int = 30) -> Dict[str, Any]:
    """
    Actor creates controlled threats at high frequency (activation_rate=0.95),
    partially suppressing each one.

    Exploit vector: accumulating SPD indefinitely through repeated cycles.

    Expected protection (§9.3): recurrence decay drives T_k toward 0.
    INVARIANT: mean SPD per event in the last quarter of the run must be
               strictly less than in the first quarter (decay observable).
    """
    return {
        "simulation": _sim(seed, num_days=num_days, ticks_per_day=8),
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.95,
                                           intensity_lo=0.5, intensity_hi=0.8)),
        "oracles": _oracles(),
        "output": _output("risk-farming"),
    }


# ── Scenario 2: TA Inflation ─────────────────────────────────────────────

def ta_inflation_config(seed: int = 1002, intensity_lo: float = 0.8,
                        intensity_hi: float = 1.0) -> Dict[str, Any]:
    """
    Actor inflates TA intensity before partially suppressing.

    Exploit vector: higher TA → higher SPD if formula is linear in raw TA.

    Expected protection: S_k = (TA-SE)/TA is a ratio — inflation cancels.
    INVARIANT: all S_k values read from metrics must be in [0, 1].
    """
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8),
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.6,
                                           intensity_lo=intensity_lo,
                                           intensity_hi=intensity_hi)),
        "oracles": _oracles(),
        "output": _output("ta-inflation"),
    }


# ── Scenario 3: Partial Suppression Loop ────────────────────────────────

def partial_suppression_config(seed: int = 1003) -> Dict[str, Any]:
    """
    Multiple actors each partially suppress the same threat independently.

    Structure: each actor computes SE against the original TA, not the residual.
    Combined implied suppression can exceed TA, yet each actor receives
    positive SPD.

    INVARIANT: detect events where Σ(TA-SE_k) > TA AND SPD_k > 0 for some k.
    (System-level over-attribution is a KNOWN structural property; test flags it.)
    """
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8,
                           se_ge_ta=0.0, temporal_invalid=0.0),
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.7,
                                           intensity_lo=0.4, intensity_hi=0.8)),
        "oracles": _oracles(),
        "output": _output("partial-suppression"),
    }


# ── Scenario 4: Timing Arbitrage ────────────────────────────────────────

def timing_arbitrage_config(seed: int = 1004, se_delay_min: float = 1.0) -> Dict[str, Any]:
    """
    Actor optimises around the Δt_int time boundary.

    Exploit vector: place SE just inside the window (t+Δt-ε) vs. just outside.

    INVARIANT: within the valid window [se_delay_min, Δt_int], timing alone
    does not drive SPD (S_k is intensity-based, not time-based).
    The cliff at Δt_int is expected and must be flagged.
    """
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8,
                           se_delay_min=se_delay_min),
        "protocol": _proto(delta_t_int=30.0),
        "domain": _domain(_threat_profiles(activation_rate=0.6)),
        "oracles": _oracles(),
        "output": _output("timing-arbitrage"),
    }


# ── Scenario 5: Attribution Splitting ───────────────────────────────────

def attribution_split_config(seed: int = 1005) -> Dict[str, Any]:
    """
    Tests whether 100 actors with 0.01 attribution each yield same
    total Σ A_k as 1 actor with full attribution.

    Expected: per-event budget enforcement (F-01) guarantees Σ A_k ≤ 1.
    INVARIANT: Σ A_k per event ≤ 1.0 always.
    """
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8),
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.6)),
        "oracles": _oracles(),
        "output": _output("attribution-split"),
    }


# ── Scenario 6: Early Prevention ────────────────────────────────────────

def early_prevention_config(seed: int = 1006) -> Dict[str, Any]:
    """
    Prevention action occurs BEFORE TA timestamp (se_time < ta_time).

    Exploit vector: if pre-TA prevention earns reward, actor can game timing.

    Expected protection: temporal_valid requires dt = se_time - ta_time > 0.
    INVARIANT: Reward(pre-TA) = 0 AND Reward(post-TA) > 0 → flag incentive gap.
    """
    return {
        "simulation": _sim(seed, num_days=5, ticks_per_day=4),
        "protocol": _proto(delta_t_int=30.0),
        "domain": _domain(_threat_profiles(activation_rate=0.6)),
        "oracles": _oracles(),
        "output": _output("early-prevention"),
    }


# ── Scenario 7: Oracle Degradation ──────────────────────────────────────

def oracle_degradation_config(seed: int = 1007,
                               noise_sigma: float = 0.25,
                               dropout_rate: float = 0.20,
                               bias_hi: float = 0.15) -> Dict[str, Any]:
    """
    One oracle class biased/noisy downward — tests oracle sensitivity.

    Expected behavior: delta_oracle rises, more events become informational.
    INVARIANT: TA_intensity must not collapse disproportionately; SPD ≥ 0.
    """
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8),
        "protocol": _proto(epsilon=0.15),
        "domain": _domain(_threat_profiles(activation_rate=0.6,
                                           intensity_lo=0.3, intensity_hi=0.8)),
        "oracles": _oracles(noise_sigma=noise_sigma,
                            dropout_rate=dropout_rate,
                            bias_lo=-bias_hi, bias_hi=bias_hi),
        "output": _output("oracle-degradation"),
    }


# ── Scenario 8: Oracle Oscillation ──────────────────────────────────────

def oracle_oscillation_stable_config(seed: int = 1008) -> Dict[str, Any]:
    """Stable oracle regime (low noise) for oscillation baseline."""
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8),
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.6)),
        "oracles": _oracles(noise_sigma=0.02),
        "output": _output("oracle-oscillation-stable"),
    }


def oracle_oscillation_noisy_config(seed: int = 1008) -> Dict[str, Any]:
    """Noisy oracle regime (informational) for oscillation comparison."""
    return {
        "simulation": _sim(seed, num_days=10, ticks_per_day=8),
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.6)),
        "oracles": _oracles(noise_sigma=0.25),
        "output": _output("oracle-oscillation-noisy"),
    }


# ── Scenario 9: Linkage Threshold Sensitivity ───────────────────────────

def linkage_sweep_config(seed: int = 1009) -> Dict[str, Any]:
    """
    Sweep linkage_score ∈ [0.45, 0.55] through the theta=0.5 boundary.

    Expected: T_k = 0 for linkage_score > theta (step function — §9.1).
    INVARIANT: no continuous gradient across theta — this IS a cliff,
    must be flagged as discontinuity risk.
    """
    return {
        "simulation": _sim(seed, num_days=5, ticks_per_day=4),
        "protocol": _proto(theta=0.5),
        "domain": _domain(_threat_profiles(activation_rate=0.6)),
        "oracles": _oracles(),
        "output": _output("linkage-sweep"),
    }


# ── Scenario 10: SE ≥ TA Boundary ───────────────────────────────────────

def boundary_se_ta_config(seed: int = 1010) -> Dict[str, Any]:
    """
    Sweep SE ∈ [0.95 TA, 1.05 TA] across the SE=TA threshold.

    Expected: at SE=TA, S_k=0, SPD=0 (§3.6).
    INVARIANT: transition must be flagged as a discontinuity risk
    (SPD drops to 0 the moment SE crosses TA).
    """
    return {
        "simulation": _sim(seed, num_days=5, ticks_per_day=4,
                           se_ge_ta=1.0),   # 100 % of events trigger SE≥TA
        "protocol": _proto(),
        "domain": _domain(_threat_profiles(activation_rate=0.7,
                                           intensity_lo=0.4, intensity_hi=0.6)),
        "oracles": _oracles(),
        "output": _output("boundary-se-ta"),
    }


# ── Convenience: all scenario configs as a registry ─────────────────────

SCENARIO_REGISTRY: Dict[str, Any] = {
    "risk_farming":          risk_farming_config,
    "ta_inflation":          ta_inflation_config,
    "partial_suppression":   partial_suppression_config,
    "timing_arbitrage":      timing_arbitrage_config,
    "attribution_split":     attribution_split_config,
    "early_prevention":      early_prevention_config,
    "oracle_degradation":    oracle_degradation_config,
    "oracle_oscillation":    oracle_oscillation_stable_config,
    "linkage_sweep":         linkage_sweep_config,
    "boundary_se_ta":        boundary_se_ta_config,
}
