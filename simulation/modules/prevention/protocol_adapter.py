"""
Protocol adapter — DKP-1-PREVENTION-001 recognition pipeline.

Inputs are *observations only*: oracle readings, intervention times, share
claims and an observed linkage score.  The adapter never receives the
scenario's truth (true intensity, who induced the threat, effectiveness).

Pipeline per threat event:
    TA readings ──► assess_ta (TTL, ≥2 classes, Δ_oracle, min)       §3.3, §9.5, ORACLE §9
    interventions ─► in window? (tᵢ ≤ t₀ + Δt_int)                    §3.4  [H-SI-1]
    SE readings ──► assess_se (TTL, ≥2 classes, aggregation)          §3.5  [H-SE-1..3]
    0 < t₁ − t₀ ≤ Δt_int                                              §3.6
    Sₖ = clamp(0, 1, (TA − SE) / TA)                                  §3.6
    Tₖ: linkage > θ → 0; recurrence decay                             §9.1, §9.3 [H-L, H-T-1]
    eligibility first, then Aₖ allocation (Σ Aₖ ≤ 1)                  §6, §12 [H-A-1, H-A-2]
    SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ                                    §5

Every responding subject gets exactly one record with a machine status:
    POSITIVE        SPD > 0
    ZERO_MERIT      evaluated, recognition rule not met (reason given)
    INFORMATIONAL   oracle inconsistency (§3.3.2)
    INVALID         input not admissible (reason given)
    NO_ATTRIBUTION  eligible, but attribution not resolvable (IDENTITY §4.1)
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from simulation.core.detmath import ipow
from simulation.core.oracles import OracleReading
from simulation.core.privacy import PlaceholderZKPProvider, ZKPProvider

POSITIVE = "POSITIVE"
ZERO_MERIT = "ZERO_MERIT"
INFORMATIONAL = "INFORMATIONAL"
INVALID = "INVALID"
NO_ATTRIBUTION = "NO_ATTRIBUTION"
STATUSES = (POSITIVE, ZERO_MERIT, INFORMATIONAL, INVALID, NO_ATTRIBUTION)


# ── parameters ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProtocolParams:
    epsilon_consistency: float
    delta_t_int_seconds: float
    theta_self_induced: float
    coverage_floor: float
    ta_time_basis: str
    se_aggregation: str
    confidence_rule: str
    attribution_rule: str
    recurrence_key: Tuple[str, ...]
    recurrence_threshold: int
    recurrence_decay: float
    recurrence_window_seconds: Optional[float]
    threat_weights: Dict[str, float] = field(hash=False)
    oracle_classes: Tuple[str, ...] = ()
    ttl_seconds: Dict[str, float] = field(default_factory=dict, hash=False)
    scope_ref: str = "unspecified"

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "ProtocolParams":
        p = cfg["protocol"]
        rec = p["recurrence"]
        return cls(
            epsilon_consistency=float(p["epsilon_consistency"]),
            delta_t_int_seconds=float(p["delta_t_int_seconds"]),
            theta_self_induced=float(p["theta_self_induced"]),
            coverage_floor=float(p["coverage_floor"]),
            ta_time_basis=p["ta_time_basis"],
            se_aggregation=p["se_aggregation"],
            confidence_rule=p["confidence_rule"],
            attribution_rule=p["attribution_rule"],
            recurrence_key=tuple(rec["key"]),
            recurrence_threshold=int(rec["threshold"]),
            recurrence_decay=float(rec["decay"]),
            recurrence_window_seconds=None if rec["window_seconds"] is None else float(rec["window_seconds"]),
            threat_weights={k: float(v["weight"]) for k, v in cfg["domain"]["channels"].items()},
            oracle_classes=tuple(cfg["oracles"]["classes"]),
            ttl_seconds={k: float(v) for k, v in cfg["oracles"]["ttl_seconds"].items()},
            scope_ref=f"scenario:{cfg['scenario']['id']}",
        )


# ── signal assessment (TA and SE) ───────────────────────────────────────

@dataclass(frozen=True)
class SignalAssessment:
    kind: str                       # "TA" or "SE"
    valid: bool
    consistent: bool
    intensity: Optional[float]
    time: Optional[float]           # t₀ (TA) or t₁ (SE), per ta_time_basis
    registered_at: Optional[float]  # arrival completing the 2nd independent class
    evaluated_at: Optional[float]   # arrival of the last reading (TTL reference)
    delta_oracle: Optional[float]
    fresh_classes: Tuple[str, ...]
    stale_classes: Tuple[str, ...]
    readings_used: Tuple[OracleReading, ...]
    reason: Optional[str]

    def summary(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "consistent": self.consistent,
            "intensity": self.intensity,
            "time": self.time,
            "registered_at": self.registered_at,
            "evaluated_at": self.evaluated_at,
            "delta_oracle": self.delta_oracle,
            "fresh_classes": list(self.fresh_classes),
            "stale_classes": list(self.stale_classes),
            "reason": self.reason,
        }


def _invalid(kind: str, reason: str, evaluated_at: Optional[float] = None,
             fresh: Tuple[str, ...] = (), stale: Tuple[str, ...] = (),
             used: Tuple[OracleReading, ...] = ()) -> SignalAssessment:
    return SignalAssessment(kind=kind, valid=False, consistent=False, intensity=None, time=None,
                            registered_at=None, evaluated_at=evaluated_at, delta_oracle=None,
                            fresh_classes=fresh, stale_classes=stale, readings_used=used,
                            reason=reason)


def assess_signal(readings: Sequence[OracleReading], params: ProtocolParams, kind: str) -> SignalAssessment:
    """Apply TTL, the multi-oracle requirement and the regime rules to one signal."""
    if not readings:
        return _invalid(kind, "no_data")
    order = {c: i for i, c in enumerate(params.oracle_classes)}
    evaluated_at = max(r.received_at for r in readings)
    fresh = tuple(r for r in readings
                  if evaluated_at - r.measured_at <= params.ttl_seconds[r.oracle_class])
    all_classes = {r.oracle_class for r in readings}
    fresh_classes = tuple(sorted({r.oracle_class for r in fresh}, key=lambda c: order.get(c, len(order))))
    stale_classes = tuple(sorted(all_classes - set(fresh_classes), key=lambda c: order.get(c, len(order))))

    if len(fresh_classes) < 2:
        reason = "stale_data" if len(all_classes) >= 2 else "single_source"
        return _invalid(kind, reason, evaluated_at, fresh_classes, stale_classes, fresh)

    seen: set = set()
    registered_at = None
    for r in sorted(fresh, key=lambda r: (r.received_at, order.get(r.oracle_class, 0))):
        seen.add(r.oracle_class)
        if len(seen) == 2:
            registered_at = r.received_at
            break

    intensities = [r.intensity for r in fresh]
    delta = max(intensities) - min(intensities)
    if kind == "TA":
        consistent = delta <= params.epsilon_consistency          # §3.3.1 / §3.3.2
        intensity = min(intensities)                              # §3.3.1
        if consistent and intensity <= 0.0:                       # H-TA0
            return _invalid(kind, "nonpositive", evaluated_at, fresh_classes, stale_classes, fresh)
    else:
        consistent = True                                         # §3.3 regimes are defined for TA only
        intensity = max(intensities) if params.se_aggregation == "max" else min(intensities)

    if params.ta_time_basis == "measurement":
        t = min(r.measured_at for r in fresh)
    else:
        t = registered_at

    return SignalAssessment(kind=kind, valid=True, consistent=consistent, intensity=intensity,
                            time=t, registered_at=registered_at, evaluated_at=evaluated_at,
                            delta_oracle=delta, fresh_classes=fresh_classes,
                            stale_classes=stale_classes, readings_used=fresh, reason=None)


# ── factor functions ────────────────────────────────────────────────────

def suppression_completeness(ta_intensity: float, se_intensity: float) -> float:
    """§3.6: Sₖ = clamp(0, 1, (TA − SE) / TA); SE ≥ TA → 0.  Continuous at SE = TA."""
    if ta_intensity <= 0.0:
        raise ValueError("TA intensity must be positive (H-TA0)")
    if se_intensity >= ta_intensity:
        return 0.0
    return max(0.0, min(1.0, (ta_intensity - se_intensity) / ta_intensity))


def temporally_aligned(t0: float, t1: float, delta_t_int: float) -> bool:
    """§3.6: 0 < (t₁ − t₀) ≤ Δt_int."""
    return 0.0 < (t1 - t0) <= delta_t_int


def intervention_in_window(t_i: float, t0: float, delta_t_int: float) -> bool:
    """H-SI-1: an intervention counts if it happens no later than t₀ + Δt_int."""
    return t_i <= t0 + delta_t_int


def confidence_factor(ta: SignalAssessment, params: ProtocolParams) -> float:
    """§3.9 / §9.4: Cₖ from PTL coverage (H-C); no data → 0."""
    if not ta.readings_used:
        return 0.0
    if params.confidence_rule == "class_coverage":
        raw = len(ta.fresh_classes) / len(params.oracle_classes)
    else:
        raw = math.fsum(r.confidence for r in ta.readings_used) / len(ta.readings_used)
    return max(params.coverage_floor, min(1.0, raw))


def linkage_exceeds(linkage_observed: float, theta: float) -> bool:
    """§9.1: linkage(subject, TAₖ) > θ → Tₖ = 0."""
    return linkage_observed > theta


class RecurrenceTracker:
    """§9.3 'repeat(TAₖ pattern) → Tₖ ↓' under hypothesis H-T-1.

    Occurrences are counted per key over the window, in processing order;
    T = decay^max(0, n − threshold) where n includes the current occurrence.
    """

    def __init__(self, key_fields: Sequence[str], threshold: int, decay: float,
                 window_seconds: Optional[float]) -> None:
        self.key_fields = tuple(key_fields)
        self.threshold = threshold
        self.decay = decay
        self.window = window_seconds
        self._times: Dict[Tuple[str, ...], List[float]] = {}

    def key(self, actor_id: str, zone_id: str, channel: str) -> Tuple[str, ...]:
        parts = {"actor": actor_id, "zone": zone_id, "channel": channel}
        return tuple(parts[f] for f in self.key_fields)

    def occurrences(self, key: Tuple[str, ...], t: float) -> int:
        times = self._times.get(key, [])
        if self.window is None:
            return len(times)
        return len(times) - bisect.bisect_left(times, t - self.window)

    def factor(self, key: Tuple[str, ...], t: float) -> float:
        n = self.occurrences(key, t) + 1
        return ipow(self.decay, max(0, n - self.threshold))

    def register(self, key: Tuple[str, ...], t: float) -> None:
        bisect.insort(self._times.setdefault(key, []), t)

    def snapshot(self) -> Dict[str, int]:
        return {"|".join(k): len(v) for k, v in sorted(self._times.items())}


def allocate_attribution(claims: Sequence[Tuple[str, float]], rule: str) -> Dict[str, Tuple[float, Optional[str]]]:
    """§6 Σ Aₖ ≤ 1 among *eligible* subjects (H-A-2).  claims are in zone list order."""
    out: Dict[str, Tuple[float, Optional[str]]] = {}
    positive = [(a, c) for a, c in claims if c > 0.0]
    for a, c in claims:
        if c <= 0.0:
            out[a] = (0.0, "zero_claim")
    total = math.fsum(c for _, c in positive)
    if total <= 1.0:
        for a, c in positive:
            out[a] = (c, None)
    elif rule == "ambiguity_zero":
        for a, _ in positive:
            out[a] = (0.0, "attribution_ambiguity")
    elif rule == "proportional":
        shares = [(a, c / total) for a, c in positive]
        excess = math.fsum(s for _, s in shares) - 1.0
        if excess > 0.0:  # binary64 rounding: take the excess from the largest share
            i = max(range(len(shares)), key=lambda j: (shares[j][1], -j))
            shares[i] = (shares[i][0], shares[i][1] - excess)
        for a, s in shares:
            out[a] = (s, None)
    elif rule == "list_order":
        remaining = 1.0
        for a, c in positive:
            s = min(c, remaining)
            remaining -= s
            out[a] = (s, None) if s > 0.0 else (0.0, "budget_exhausted_list_order")
    else:  # pragma: no cover - validated by config schema
        raise ValueError(f"unknown attribution rule {rule!r}")
    return out


# ── adapter ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ObservedIntervention:
    """What the evaluator knows about one subject's intervention."""
    actor_id: str
    order: int               # position in the zone's actor list
    time: float
    claim: float
    linkage_observed: float


def _epistemic(status: str, ta: SignalAssessment, n_classes: int, scope_ref: str) -> Dict[str, Any]:
    """EPISTEMIC-BOUNDARIES §5 metadata for one output record."""
    if status == INVALID:
        validity, confidence, consistency = "INVALID", "INSUFFICIENT_DATA", "UNRESOLVED"
    elif status == NO_ATTRIBUTION:
        validity, confidence, consistency = "CONDITIONAL", "INSUFFICIENT_DATA", "CONSISTENT"
    else:
        full = len(ta.fresh_classes) == n_classes
        confidence = "SUFFICIENT_DATA" if full else "DEGRADED_SIGNAL"
        if status == INFORMATIONAL:
            validity, consistency = "CONDITIONAL", "ORACLE_CONFLICT"
        else:
            validity, consistency = "VALID", "CONSISTENT"
    return {
        "validity_state": validity,
        "confidence_state": confidence,
        "consistency_state": consistency,
        "scope_ref": scope_ref,
        "revalidation_required": True,
        "dispute_allowed": True,
    }


class PreventionProtocolAdapter:
    def __init__(self, params: ProtocolParams, zkp_provider: Optional[ZKPProvider] = None) -> None:
        self.params = params
        self.recurrence = RecurrenceTracker(params.recurrence_key, params.recurrence_threshold,
                                            params.recurrence_decay, params.recurrence_window_seconds)
        self._zkp = zkp_provider or PlaceholderZKPProvider()

    # signals
    def assess_ta(self, readings: Sequence[OracleReading]) -> SignalAssessment:
        return assess_signal(readings, self.params, "TA")

    def assess_se(self, readings: Sequence[OracleReading]) -> SignalAssessment:
        return assess_signal(readings, self.params, "SE")

    def se_measurement_start(self, ta: SignalAssessment,
                             interventions: Sequence[ObservedIntervention]) -> Optional[float]:
        """When SE is measured: after the last in-window intervention (H-SI-1)."""
        if not (ta.valid and ta.consistent):
            return None
        times = [iv.time for iv in interventions
                 if intervention_in_window(iv.time, ta.time, self.params.delta_t_int_seconds)]
        return max(times) if times else None

    # evaluation
    def evaluate_event(self, event_id: str, zone_id: str, channel: str, ta: SignalAssessment,
                       se: Optional[SignalAssessment],
                       interventions: Sequence[ObservedIntervention]) -> List[Dict[str, Any]]:
        p = self.params
        ivs = sorted(interventions, key=lambda iv: iv.order)
        recs: Dict[str, Dict[str, Any]] = {}
        for iv in ivs:
            recs[iv.actor_id] = {
                "event_id": event_id,
                "zone_id": zone_id,
                "risk_channel": channel,
                "actor_id": iv.actor_id,
                "intervention_time": iv.time,
                "claim": iv.claim,
                "linkage_observed": iv.linkage_observed,
                "status": None,
                "reason": None,
                "SPD": 0.0,
                "factors": {"W": None, "S": None, "A": None, "C": None, "T": None},
                "ta": ta.summary(),
                "se": None if se is None else se.summary(),
                "zkp": None,
            }

        def done(aid: str, status: str, reason: Optional[str]) -> None:
            recs[aid]["status"] = status
            recs[aid]["reason"] = reason

        if not ta.valid:
            for iv in ivs:
                done(iv.actor_id, INVALID, f"ta_{ta.reason}")
        elif not ta.consistent:
            for iv in ivs:
                done(iv.actor_id, INFORMATIONAL, "oracle_inconsistency")
        else:
            W = p.threat_weights[channel]
            C = confidence_factor(ta, p)
            in_window = [iv for iv in ivs if intervention_in_window(iv.time, ta.time, p.delta_t_int_seconds)]
            for iv in ivs:
                recs[iv.actor_id]["factors"].update(W=W, C=C)
                if iv not in in_window:
                    done(iv.actor_id, ZERO_MERIT, "intervention_outside_window")
            if in_window:
                recognized = self._evaluate_in_window(ta, se, in_window, W, C, zone_id, channel, recs, done)
                # §9.3: a recognized intervention is one occurrence of the pattern for its key;
                # registered after the event so subjects of one event do not affect each other
                for key in sorted({self.recurrence.key(iv.actor_id, zone_id, channel) for iv in recognized}):
                    self.recurrence.register(key, ta.time)

        n_classes = len(p.oracle_classes)
        out = []
        for iv in ivs:
            r = recs[iv.actor_id]
            r["epistemic"] = _epistemic(r["status"], ta, n_classes, p.scope_ref)
            out.append(r)
        return out

    def _evaluate_in_window(self, ta, se, in_window, W, C, zone_id, channel, recs,
                            done) -> List[ObservedIntervention]:
        """Evaluate in-window subjects; return those that reached the Tₖ stage."""
        p = self.params
        if se is None or not se.valid:
            reason = "se_no_data" if se is None else f"se_{se.reason}"
            for iv in in_window:
                done(iv.actor_id, INVALID, reason)
            return []
        if not temporally_aligned(ta.time, se.time, p.delta_t_int_seconds):
            for iv in in_window:
                done(iv.actor_id, ZERO_MERIT, "temporal_window")
            return []
        S = suppression_completeness(ta.intensity, se.intensity)
        for iv in in_window:
            recs[iv.actor_id]["factors"]["S"] = S
        if S == 0.0:
            for iv in in_window:
                done(iv.actor_id, ZERO_MERIT, "no_measured_reduction")
            return []
        if C == 0.0:
            for iv in in_window:
                done(iv.actor_id, INVALID, "no_coverage")
            return []

        eligible: List[Tuple[ObservedIntervention, float]] = []
        for iv in in_window:
            if linkage_exceeds(iv.linkage_observed, p.theta_self_induced):
                recs[iv.actor_id]["factors"]["T"] = 0.0
                done(iv.actor_id, ZERO_MERIT, "self_induced_linkage")
                continue
            T = self.recurrence.factor(self.recurrence.key(iv.actor_id, zone_id, channel), ta.time)
            recs[iv.actor_id]["factors"]["T"] = T
            if T == 0.0:
                done(iv.actor_id, ZERO_MERIT, "recurrence_underflow")
                continue
            eligible.append((iv, T))

        allocation = allocate_attribution([(iv.actor_id, iv.claim) for iv, _ in eligible], p.attribution_rule)
        for iv, T in eligible:
            proof = self._zkp.create_proof(iv.actor_id, iv.linkage_observed)   # §8 — placeholder
            recs[iv.actor_id]["zkp"] = {"provider": proof.metadata.get("provider"), "verified": proof.verified}
            A, why = allocation[iv.actor_id]
            recs[iv.actor_id]["factors"]["A"] = A
            if A <= 0.0:
                done(iv.actor_id, NO_ATTRIBUTION, why)
                continue
            spd = W * S * A * C * T
            recs[iv.actor_id]["SPD"] = spd
            if spd > 0.0:
                done(iv.actor_id, POSITIVE, None)
            else:
                done(iv.actor_id, ZERO_MERIT, "zero_weight" if W == 0.0 else "zero_product")
        return list(in_window)
