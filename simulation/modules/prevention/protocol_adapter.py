"""
Protocol adapter — DKP-1-PREVENTION-001 recognition pipeline.

Inputs are *observations only*: oracle readings, intervention times, share
claims and an observed linkage score.  The adapter never receives the
scenario's truth (true intensity, who induced the threat, effectiveness).

Pipeline per threat event:
    TA readings ──► assess (TTL, ≥2 classes, Δ_oracle, min)          §3.3, §9.5, ORACLE §9
    interventions ─► in window? (tᵢ ≤ t₀ + Δt_int)                    §3.4  [H-SI-1]
    SE readings ──► assess (TTL, ≥2 classes, aggregation)             §3.5  [H-SE-1..3]
    decision time: TTL re-applied to TA and SE if ttl_reference=decision  [H-TTL-2]
    0 < t₁ − t₀ ≤ Δt_int                                              §3.6
    Sₖ = clamp(0, 1, (TA − SE) / TA)                                  §3.6
    Tₖ: linkage > θ → 0; recurrence decay over the history            §9.1, §9.3 [H-L, H-T-1..3]
    eligibility first, then Aₖ allocation (Σ Aₖ ≤ 1)                  §6, §12 [H-A-1, H-A-2]
    SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ  (must be finite)                  §5

Evaluation has two passes (audit item U3).  ``prepare`` takes an event up to
the Tₖ stage; nothing there depends on Tₖ.  ``finalize`` builds the recurrence
history from all prepared events and then computes Tₖ, shares and SPD, so the
result does not depend on the order in which events are processed.

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


class NonFiniteResultError(ArithmeticError):
    """A factor, an SPD value or an aggregate is not a finite number (audit item U4)."""


def require_finite(name: str, value: float, where: str = "") -> float:
    if not math.isfinite(value):
        raise NonFiniteResultError(f"non-finite {name} = {value!r}{' in ' + where if where else ''}")
    return value


# ── parameters ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProtocolParams:
    epsilon_consistency: float
    delta_t_int_seconds: float
    theta_self_induced: float
    coverage_floor: float
    ta_time_basis: str
    ttl_reference: str
    se_aggregation: str
    confidence_rule: str
    attribution_rule: str
    recurrence_key: Tuple[str, ...]
    recurrence_threshold: int
    recurrence_decay: float
    recurrence_window_seconds: Optional[float]
    recurrence_history: str
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
            ttl_reference=p["ttl_reference"],
            se_aggregation=p["se_aggregation"],
            confidence_rule=p["confidence_rule"],
            attribution_rule=p["attribution_rule"],
            recurrence_key=tuple(rec["key"]),
            recurrence_threshold=int(rec["threshold"]),
            recurrence_decay=float(rec["decay"]),
            recurrence_window_seconds=None if rec["window_seconds"] is None else float(rec["window_seconds"]),
            recurrence_history=rec["history"],
            threat_weights={k: float(v["weight"]) for k, v in sorted(cfg["domain"]["channels"].items())},
            oracle_classes=tuple(cfg["oracles"]["classes"]),
            ttl_seconds={k: float(v) for k, v in sorted(cfg["oracles"]["ttl_seconds"].items())},
            scope_ref=f"scenario:{cfg['scenario']['id']}",
        )


# ── signal assessment (TA and SE) ───────────────────────────────────────

@dataclass(frozen=True)
class SignalAssessment:
    kind: str                        # "TA" or "SE"
    valid: bool
    consistent: bool
    intensity: Optional[float]
    time: Optional[float]            # t₀ (TA) or t₁ (SE), per ta_time_basis
    registered_at: Optional[float]   # arrival completing the 2nd independent fresh class
    evaluated_at: Optional[float]    # arrival of the last reading of this signal (availability)
    reference_time: Optional[float]  # instant at which TTL was applied
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
            "reference_time": self.reference_time,
            "delta_oracle": self.delta_oracle,
            "fresh_classes": list(self.fresh_classes),
            "stale_classes": list(self.stale_classes),
            "reason": self.reason,
        }


def _invalid(kind: str, reason: str, evaluated_at: Optional[float] = None,
             reference: Optional[float] = None, fresh: Tuple[str, ...] = (),
             stale: Tuple[str, ...] = (), used: Tuple[OracleReading, ...] = ()) -> SignalAssessment:
    return SignalAssessment(kind=kind, valid=False, consistent=False, intensity=None, time=None,
                            registered_at=None, evaluated_at=evaluated_at, reference_time=reference,
                            delta_oracle=None, fresh_classes=fresh, stale_classes=stale,
                            readings_used=used, reason=reason)


def assess_signal(readings: Sequence[OracleReading], params: ProtocolParams, kind: str,
                  reference: Optional[float] = None) -> SignalAssessment:
    """Apply TTL, the multi-oracle requirement and the regime rules to one signal.

    TTL reference: the arrival of the signal's own last reading (``signal``) or an
    explicit instant (``decision``).  A reading is fresh if it has arrived by the
    reference and its age there is at most its class TTL (age == TTL is fresh).
    """
    if not readings:
        return _invalid(kind, "no_data", reference=reference)
    order = {c: i for i, c in enumerate(params.oracle_classes)}
    evaluated_at = max(r.received_at for r in readings)
    ref = evaluated_at if reference is None else reference
    fresh = tuple(r for r in readings
                  if r.received_at <= ref and ref - r.measured_at <= params.ttl_seconds[r.oracle_class])
    all_classes = {r.oracle_class for r in readings}
    fresh_classes = tuple(sorted({r.oracle_class for r in fresh}, key=lambda c: order.get(c, len(order))))
    stale_classes = tuple(sorted(all_classes - set(fresh_classes), key=lambda c: order.get(c, len(order))))

    if len(fresh_classes) < 2:
        reason = "stale_data" if len(all_classes) >= 2 else "single_source"
        return _invalid(kind, reason, evaluated_at, ref, fresh_classes, stale_classes, fresh)

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
            return _invalid(kind, "nonpositive", evaluated_at, ref, fresh_classes, stale_classes, fresh)
    else:
        consistent = True                                         # §3.3 regimes are defined for TA only
        intensity = max(intensities) if params.se_aggregation == "max" else min(intensities)

    t = min(r.measured_at for r in fresh) if params.ta_time_basis == "measurement" else registered_at
    return SignalAssessment(kind=kind, valid=True, consistent=consistent, intensity=intensity,
                            time=t, registered_at=registered_at, evaluated_at=evaluated_at,
                            reference_time=ref, delta_oracle=delta, fresh_classes=fresh_classes,
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


class RecurrenceHistory:
    """§9.3 'repeat(TAₖ pattern) → Tₖ ↓' (hypotheses H-T-1, H-T-3).

    Unit of history: one occurrence per (event, key) — several subjects of one
    event that share a key count once.  An occurrence is a recognized
    intervention (it reached the Tₖ stage).

    Clock: t₀ of the event (the declared ta_time_basis, as in §3.6).
    For an event at t₀, a previous occurrence is one of *another* event with
        t₀ − W ≤ t₀' < t₀            (W = window; no lower bound if W is null)
    and, in mode ``as_of_decision``, whose decision time is not later than the
    current decision time (the evaluator could know it); in mode
    ``retrospective`` every recognized occurrence of the run counts.
    Equal t₀ is not "earlier"; event ids only make the iteration stable.
    T = decay^max(0, n_previous + 1 − threshold).
    """

    def __init__(self, key_fields: Sequence[str], threshold: int, decay: float,
                 window_seconds: Optional[float], mode: str) -> None:
        self.key_fields = tuple(key_fields)
        self.threshold = threshold
        self.decay = decay
        self.window = window_seconds
        self.mode = mode
        self._entries: Dict[Tuple[str, ...], List[Tuple[float, float, str]]] = {}
        self._sorted = True

    def key(self, actor_id: str, zone_id: str, channel: str) -> Tuple[str, ...]:
        parts = {"actor": actor_id, "zone": zone_id, "channel": channel}
        return tuple(parts[f] for f in self.key_fields)

    def add(self, key: Tuple[str, ...], t0: float, available_at: float, event_id: str) -> None:
        self._entries.setdefault(key, []).append((t0, available_at, event_id))
        self._sorted = False

    def _sort(self) -> None:
        if not self._sorted:
            for entries in self._entries.values():
                entries.sort()
            self._sorted = True

    def previous(self, key: Tuple[str, ...], t0: float, decision_at: float, event_id: str) -> int:
        self._sort()
        entries = self._entries.get(key, [])
        hi = bisect.bisect_left(entries, (t0, -math.inf, ""))
        lo = 0 if self.window is None else bisect.bisect_left(entries, (t0 - self.window, -math.inf, ""))
        n = 0
        for t, avail, eid in entries[lo:hi]:
            if eid == event_id:
                continue
            if self.mode == "as_of_decision" and avail > decision_at:
                continue
            n += 1
        return n

    def factor(self, key: Tuple[str, ...], t0: float, decision_at: float, event_id: str) -> float:
        n = self.previous(key, t0, decision_at, event_id)
        return ipow(self.decay, max(0, n + 1 - self.threshold))

    def snapshot(self) -> Dict[str, int]:
        return {"|".join(k): len(v) for k, v in sorted(self._entries.items())}


def allocate_attribution(claims: Sequence[Tuple[str, float]], rule: str) -> Dict[str, Tuple[float, Optional[str]]]:
    """§6 Σ Aₖ ≤ 1 among *eligible* subjects (H-A-2).  claims are in actor_order."""
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
    order: int               # position in domain.actor_order (used only by list_order)
    time: float
    claim: float
    linkage_observed: float


@dataclass
class PreparedEvent:
    """An event evaluated up to the Tₖ stage (first pass)."""
    event_id: str
    zone_id: str
    channel: str
    ta: SignalAssessment                 # assessment the decision uses
    t0: Optional[float]
    decision_at: Optional[float]
    W: Optional[float]
    S: Optional[float]
    C: Optional[float]
    recognized: List[ObservedIntervention]
    keys: List[Tuple[str, ...]]
    records: Dict[str, Dict[str, Any]]


def _epistemic(status: str, basis: SignalAssessment, n_classes: int, scope_ref: str) -> Dict[str, Any]:
    """EPISTEMIC-BOUNDARIES §5 metadata for one output record."""
    if status == INVALID:
        validity, confidence, consistency = "INVALID", "INSUFFICIENT_DATA", "UNRESOLVED"
    elif status == NO_ATTRIBUTION:
        validity, confidence, consistency = "CONDITIONAL", "INSUFFICIENT_DATA", "CONSISTENT"
    else:
        full = len(basis.fresh_classes) == n_classes
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
        self._zkp = zkp_provider or PlaceholderZKPProvider()
        self._incremental: List[PreparedEvent] = []
        self.history: Optional[RecurrenceHistory] = None

    def new_history(self) -> RecurrenceHistory:
        p = self.params
        return RecurrenceHistory(p.recurrence_key, p.recurrence_threshold, p.recurrence_decay,
                                 p.recurrence_window_seconds, p.recurrence_history)

    # signals (TTL at the signal's own time; used for scheduling and statistics)
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

    # first pass
    def prepare(self, event_id: str, zone_id: str, channel: str,
                ta_readings: Sequence[OracleReading], se_readings: Optional[Sequence[OracleReading]],
                interventions: Sequence[ObservedIntervention]) -> PreparedEvent:
        """Evaluate one event up to the Tₖ stage.  ``se_readings`` is None if no SE was measured."""
        p = self.params
        ta_sig = self.assess_ta(ta_readings)
        se_sig = None if se_readings is None else self.assess_se(se_readings)

        decision_at = None
        if se_sig is not None:   # a decision is made only when SE was measured
            # availability from the original arrival times, before any TTL filtering
            decision_at = max(t for t in (ta_sig.evaluated_at, se_sig.evaluated_at) if t is not None)
        at_decision = p.ttl_reference == "decision" and decision_at is not None
        if at_decision:
            ta = assess_signal(ta_readings, p, "TA", reference=decision_at)
            se = assess_signal(se_readings, p, "SE", reference=decision_at)
        else:
            ta, se = ta_sig, se_sig

        ivs = sorted(interventions, key=lambda iv: iv.actor_id)
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
                "ttl_reference": p.ttl_reference,
                "decision_at": decision_at,
                "ta": ta.summary(),
                "se": None if se is None else se.summary(),
                "ta_signal": ta_sig.summary() if at_decision else None,
                "se_signal": se_sig.summary() if at_decision else None,
                "zkp": None,
            }
        pe = PreparedEvent(event_id, zone_id, channel, ta, None, decision_at, None, None, None, [], [], recs)

        def done(aid: str, status: str, reason: Optional[str]) -> None:
            recs[aid]["status"] = status
            recs[aid]["reason"] = reason

        if not ta_sig.valid:
            pe.ta = ta_sig
            for iv in ivs:
                done(iv.actor_id, INVALID, f"ta_{ta_sig.reason}")
            return pe
        if not ta_sig.consistent:
            pe.ta = ta_sig
            for iv in ivs:
                done(iv.actor_id, INFORMATIONAL, "oracle_inconsistency")
            return pe
        if not ta.valid:          # only after TTL re-applied at decision time
            for iv in ivs:
                done(iv.actor_id, INVALID, f"ta_{ta.reason}_at_decision")
            return pe
        if not ta.consistent:     # cannot happen: dropping readings never widens Δ_oracle
            for iv in ivs:
                done(iv.actor_id, INFORMATIONAL, "oracle_inconsistency_at_decision")
            return pe

        pe.W = require_finite("W", p.threat_weights[channel], event_id)
        pe.C = confidence_factor(ta, p)
        pe.t0 = ta.time
        in_window = [iv for iv in ivs if intervention_in_window(iv.time, ta.time, p.delta_t_int_seconds)]
        for iv in ivs:
            recs[iv.actor_id]["factors"].update(W=pe.W, C=pe.C)
            if iv not in in_window:
                done(iv.actor_id, ZERO_MERIT, "intervention_outside_window")
        if not in_window:
            return pe

        if se is None:
            for iv in in_window:
                done(iv.actor_id, INVALID, "se_not_measured")
            return pe
        if not se.valid:
            suffix = "_at_decision" if at_decision and se_sig.valid else ""
            for iv in in_window:
                done(iv.actor_id, INVALID, f"se_{se.reason}{suffix}")
            return pe
        if not temporally_aligned(ta.time, se.time, p.delta_t_int_seconds):
            for iv in in_window:
                done(iv.actor_id, ZERO_MERIT, "temporal_window")
            return pe
        pe.S = suppression_completeness(ta.intensity, se.intensity)
        for iv in in_window:
            recs[iv.actor_id]["factors"]["S"] = pe.S
        if pe.S == 0.0:
            for iv in in_window:
                done(iv.actor_id, ZERO_MERIT, "no_measured_reduction")
            return pe
        if pe.C == 0.0:
            for iv in in_window:
                done(iv.actor_id, INVALID, "no_coverage")
            return pe

        hist = self.new_history()
        pe.recognized = list(in_window)
        pe.keys = sorted({hist.key(iv.actor_id, zone_id, channel) for iv in in_window})
        return pe

    # second pass
    def finalize(self, prepared: Sequence[PreparedEvent]) -> List[Dict[str, Any]]:
        """Compute Tₖ, shares and SPD for all prepared events; order-independent."""
        history = self.new_history()
        for pe in prepared:
            for key in pe.keys:
                history.add(key, pe.t0, pe.decision_at, pe.event_id)
        out: List[Dict[str, Any]] = []
        for pe in sorted(prepared, key=lambda e: e.event_id):
            self._finalize_one(pe, history)
            out.extend(pe.records[a] for a in sorted(pe.records))
        self.history = history
        return out

    def evaluate_event(self, event_id: str, zone_id: str, channel: str,
                       ta_readings: Sequence[OracleReading], se_readings: Optional[Sequence[OracleReading]],
                       interventions: Sequence[ObservedIntervention]) -> List[Dict[str, Any]]:
        """Incremental convenience: history = events passed to this method so far.

        Results depend on call order only through what was passed before; the
        runner uses prepare/finalize, which is order-independent.
        """
        pe = self.prepare(event_id, zone_id, channel, ta_readings, se_readings, interventions)
        self._incremental.append(pe)
        history = self.new_history()
        for other in self._incremental:
            for key in other.keys:
                history.add(key, other.t0, other.decision_at, other.event_id)
        self._finalize_one(pe, history)
        self.history = history
        return [pe.records[a] for a in sorted(pe.records)]

    def _finalize_one(self, pe: PreparedEvent, history: RecurrenceHistory) -> None:
        p = self.params
        recs = pe.records

        def done(aid: str, status: str, reason: Optional[str]) -> None:
            recs[aid]["status"] = status
            recs[aid]["reason"] = reason

        eligible: List[Tuple[ObservedIntervention, float]] = []
        for iv in pe.recognized:
            if linkage_exceeds(iv.linkage_observed, p.theta_self_induced):
                recs[iv.actor_id]["factors"]["T"] = 0.0
                done(iv.actor_id, ZERO_MERIT, "self_induced_linkage")
                continue
            T = history.factor(history.key(iv.actor_id, pe.zone_id, pe.channel), pe.t0,
                               pe.decision_at, pe.event_id)
            recs[iv.actor_id]["factors"]["T"] = T
            if T == 0.0:
                done(iv.actor_id, ZERO_MERIT, "recurrence_underflow")
                continue
            eligible.append((iv, T))

        eligible.sort(key=lambda e: (e[0].order, e[0].actor_id))
        allocation = allocate_attribution([(iv.actor_id, iv.claim) for iv, _ in eligible], p.attribution_rule)
        for iv, T in eligible:
            proof = self._zkp.create_proof(iv.actor_id, iv.linkage_observed)   # §8 — placeholder
            recs[iv.actor_id]["zkp"] = {"provider": proof.metadata.get("provider"), "verified": proof.verified}
            A, why = allocation[iv.actor_id]
            recs[iv.actor_id]["factors"]["A"] = A
            if A <= 0.0:
                done(iv.actor_id, NO_ATTRIBUTION, why)
                continue
            spd = pe.W * pe.S * A * pe.C * T
            require_finite("SPD", spd, pe.event_id)
            recs[iv.actor_id]["SPD"] = spd
            if spd > 0.0:
                done(iv.actor_id, POSITIVE, None)
            else:
                done(iv.actor_id, ZERO_MERIT, "zero_weight" if pe.W == 0.0 else "zero_product")

        n_classes = len(p.oracle_classes)
        for aid, r in recs.items():
            r["epistemic"] = _epistemic(r["status"], pe.ta, n_classes, p.scope_ref)
