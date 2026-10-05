"""
Registry of engine hypotheses — choices the protocol text does not fix.

DKP-1-PREVENTION-001 leaves several functions incompletely specified
(B5/B7 in the audit exchange).  The engine must still compute something,
so every such choice is named here, tied to the config key that selects it,
and copied into each run manifest.  None of these is a normative reading of
the protocol: each is a hypothesis of this research bench or of the scenario.

Kinds:
    engine     — a rule of the bench where the protocol is silent or ambiguous
    scenario   — a property of the synthetic world (physics, timing, actors)
"""

from __future__ import annotations

from typing import Any, Dict, List

HYPOTHESES: Dict[str, Dict[str, Any]] = {
    "H-TIME-1": {
        "kind": "scenario",
        "config": ["time.tick_seconds", "time.start_dti_day", "simulation.ticks_per_day"],
        "protocol_ref": "DKP-0-TIME-001 §4.1; PREVENTION §3.6",
        "statement": "Simulation clock is SI seconds; ticks partition the civil day; "
                     "days are reported as DTI-Day. TIME defines no sub-day unit.",
    },
    "H-TIME-2": {
        "kind": "engine",
        "config": ["protocol.ta_time_basis"],
        "protocol_ref": "PREVENTION §3.6 (TAₖ @ t₀, SEₖ @ t₁)",
        "statement": "t₀ and t₁ are taken from the readings: 'measurement' = earliest "
                     "measured_at of the fresh readings used; 'registration' = arrival of "
                     "the reading that completed the second independent class.",
    },
    "H-TIME-3": {
        "kind": "scenario",
        "config": ["oracles.measurement_delay_seconds", "oracles.arrival_delay_seconds",
                   "domain.actors.*.response_delay_seconds"],
        "protocol_ref": "EPISTEMIC-BOUNDARIES §9; ORACLE §9",
        "statement": "Event time, measurement time and arrival time are distinct; "
                     "delays are drawn from the declared ranges.",
    },
    "H-TTL": {
        "kind": "scenario",
        "config": ["oracles.ttl_seconds"],
        "protocol_ref": "ORACLE §9",
        "statement": "Each oracle class has a TTL; a reading older than its TTL at "
                     "evaluation time has weight zero and is excluded. Values are "
                     "scenario hypotheses, not borrowed from other channels.",
    },
    "H-SE-1": {
        "kind": "engine",
        "config": [],
        "protocol_ref": "PREVENTION §3.5, §3.6",
        "statement": "SEₖ_intensity is the measured residual intensity after the "
                     "interventions; SE = 0 means fully suppressed, SE >= TA means no "
                     "measured reduction.",
    },
    "H-SE-2": {
        "kind": "engine",
        "config": ["protocol.se_aggregation"],
        "protocol_ref": "PREVENTION §3.3 (defined for TA only)",
        "statement": "How fresh SE readings are aggregated; 'max' is the conservative "
                     "choice (larger residual, smaller S).",
    },
    "H-SE-3": {
        "kind": "engine",
        "config": [],
        "protocol_ref": "PREVENTION §9.5",
        "statement": "The SE measurement also needs at least two fresh independent "
                     "oracle classes.",
    },
    "H-SI-1": {
        "kind": "engine",
        "config": ["protocol.delta_t_int_seconds"],
        "protocol_ref": "PREVENTION §3.4, §3.6",
        "statement": "An intervention is a Subject-linked Intervention if it happens no "
                     "later than t₀ + Δt_int; SE is measured after the last such "
                     "intervention; the event-level check 0 < t₁ − t₀ ≤ Δt_int applies.",
    },
    "H-SUP": {
        "kind": "scenario",
        "config": ["domain.actors.*.effectiveness", "domain.actors.*.effectiveness_range"],
        "protocol_ref": "—",
        "statement": "Interventions act jointly: true intensity after them is "
                     "I × Π(1 − effᵢ) from each intervention time on.",
    },
    "H-C": {
        "kind": "engine",
        "config": ["protocol.confidence_rule", "protocol.coverage_floor"],
        "protocol_ref": "PREVENTION §3.9, §9.4",
        "statement": "Cₖ 'derived from PTL coverage': 'class_coverage' = fresh classes / "
                     "configured classes; 'mean_reported_confidence' = legacy v1 rule "
                     "(mean self-reported sensor confidence).",
    },
    "H-A-1": {
        "kind": "engine",
        "config": ["domain.actors.*.attribution_claim"],
        "protocol_ref": "PREVENTION §6, §13.5",
        "statement": "Causal linkage is treated as traceable for an intervention inside "
                     "the window on a valid, consistent TA with a confirmed SE. Each "
                     "subject's share claim is a scenario input; the bench has no "
                     "causal-inference algorithm.",
    },
    "H-A-2": {
        "kind": "engine",
        "config": ["protocol.attribution_rule"],
        "protocol_ref": "PREVENTION §6, §12; IDENTITY §4.1",
        "statement": "Only eligible subjects take part in allocation. If their claims sum "
                     "to more than 1: 'ambiguity_zero' reads this as attribution ambiguity "
                     "(§12: SPD = 0, NO_ATTRIBUTION); 'proportional' and 'list_order' are "
                     "comparison hypotheses, not normative.",
    },
    "H-T-1": {
        "kind": "engine",
        "config": ["protocol.recurrence.*"],
        "protocol_ref": "PREVENTION §9.3",
        "statement": "'repeat(TAₖ pattern)' is counted per declared key over the declared "
                     "window; one occurrence = one recognized intervention (it reached the "
                     "Tₖ stage); Tₖ = decay^max(0, n − threshold) with n including the "
                     "current occurrence. The v1 rule (key actor+channel, whole run) also "
                     "decays honest repeated work; the protocol does not say whose pattern "
                     "counts.",
    },
    "H-T-2": {
        "kind": "engine",
        "config": [],
        "protocol_ref": "PREVENTION §9.3",
        "statement": "Recurrence history lives in memory for one run only; a new id, a new "
                     "channel or a restart starts a new series.",
    },
    "H-L": {
        "kind": "scenario",
        "config": ["oracles.linkage_detection.*", "protocol.theta_self_induced"],
        "protocol_ref": "PREVENTION §9.1",
        "statement": "The evaluator sees only an observed linkage score: for a self-induced "
                     "threat it is drawn from detected_score_range with "
                     "detection_probability, otherwise from undetected_score_range.",
    },
    "H-TA0": {
        "kind": "engine",
        "config": [],
        "protocol_ref": "PREVENTION §3.6",
        "statement": "A consistent TA with intensity <= 0 is not an activation: status "
                     "INVALID, reason ta_nonpositive.",
    },
    "H-NUM": {
        "kind": "engine",
        "config": [],
        "protocol_ref": "PREVENTION §11 (deterministic and auditable)",
        "statement": "IEEE-754 binary64; records keep full precision (shortest round-trip "
                     "repr); rounding only in the human-readable summary.",
    },
    "H-CBF": {
        "kind": "engine",
        "config": [],
        "protocol_ref": "PREVENTION §3.11, §9.2",
        "statement": "CBF = Welford count/mean/M2 over observed TA intensity; population "
                     "and sample deviation reported under separate names; audit-only.",
    },
}


def active_hypotheses(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Hypotheses with the values this config selects (for the manifest)."""
    proto = cfg["protocol"]
    values = {
        "H-TIME-1": {"tick_seconds": cfg["time"]["tick_seconds"],
                     "ticks_per_day": cfg["simulation"]["ticks_per_day"],
                     "start_dti_day": cfg["time"]["start_dti_day"]},
        "H-TIME-2": {"ta_time_basis": proto["ta_time_basis"]},
        "H-TIME-3": {"measurement_delay_seconds": cfg["oracles"]["measurement_delay_seconds"],
                     "arrival_delay_seconds": cfg["oracles"]["arrival_delay_seconds"]},
        "H-TTL": {"ttl_seconds": cfg["oracles"]["ttl_seconds"]},
        "H-SE-2": {"se_aggregation": proto["se_aggregation"]},
        "H-SI-1": {"delta_t_int_seconds": proto["delta_t_int_seconds"]},
        "H-C": {"confidence_rule": proto["confidence_rule"],
                "coverage_floor": proto["coverage_floor"]},
        "H-A-1": {"claims": {k: v["attribution_claim"] for k, v in cfg["domain"]["actors"].items()}},
        "H-A-2": {"attribution_rule": proto["attribution_rule"]},
        "H-T-1": dict(proto["recurrence"]),
        "H-L": dict(cfg["oracles"]["linkage_detection"],
                    theta_self_induced=proto["theta_self_induced"]),
    }
    out = []
    for hid in sorted(HYPOTHESES):
        entry = {"id": hid, **HYPOTHESES[hid]}
        if hid in values:
            entry["value"] = values[hid]
        out.append(entry)
    return out
