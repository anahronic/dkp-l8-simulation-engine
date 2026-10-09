"""
DISPUTE AND CORRECTION module — scenario S-LAB-04.

DKP-1-IMPACT-001 (Iᵢ, boundary flag, Rᵢ, Xᵢ, Uᵢ) → DKP-1-IDENTITY-001 (binding, proxies,
NO_ATTRIBUTION) → DKP-1-JUSTICE-001 (domains, distribution, re-evaluation limits, dispute
exception) → DKP-4-ERROR-001 (appeal, R0–R4, status quo, bond, recomputation, rollback) →
DKP-1-EPISTEMIC-BOUNDARIES-001 §7.2 (original kept, new evaluation, delta).

Every step is a §6.3 message in one ``EventLog`` (minutes; DTI-Days of 1440 minutes from
``start_dti_day``).  The reference chain below implements the texts; declared ``faults``
switch single rules off.  The checker recomputes Iᵢ from the observation messages, the
justice domains and the ERROR timing from the inputs, and judges the log — including the
provenance of every decision and action.

Causality is given on input (contributions of Subjects); the lab checks a declared causal
binding, it does not infer one.  Consequence amounts are not computed: the texts give no
amount function (JUSTICE §6, §7), and the lab does not invent one.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message, epistemic_problems
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.run import canonical_json, sha256_text
from lab.core.schema import LabInputError
from lab.modules.failure_chain import DATA_TYPES, TTL_TEXT
from lab.modules.time import canonical, dy_doy

DAY = 1440
APPEAL_WINDOW_DAYS = 30            # ERROR §7
STATUS_QUO_MAX_DAYS = 7            # ERROR §7
DOMAINS = ("restitution", "restriction", "isolation", "exclusion")      # JUSTICE §5
ENFORCING = ("restriction", "isolation", "exclusion")
PROXY_KINDS = ("smart_contract", "autonomous_agent", "script")          # IDENTITY §5
SUBJECT_KINDS = ("human", "legal_entity", "collective", "ai_system") + PROXY_KINDS
CATEGORIES = ("E1", "E2", "E3", "E4", "E5")
ALLEGATIONS = ("none", "oracle_inconsistency", "scope_violation", "measurement_integrity")

FAULTS = {
    "late_appeal_accepted": "a non-E1 appeal after 30 DTI-Days is accepted",
    "e1_time_barred": "an E1 appeal after 30 DTI-Days is rejected as late",
    "suspension_over_7_days": "the status quo suspension lasts until verification, beyond 7 DTI-Days",
    "mutate_original": "recomputation overwrites the original decision record",
    "retaliate": "filing an appeal adds a restriction on the appellant",
    "keep_bond": "the bond is not returned after a confirmed error",
    "proxy_as_subject": "a smart contract or agent is bound as an independent Subject",
    "enforce_no_attribution": "enforcement proceeds on NO_ATTRIBUTION",
    "suppress_by_uncertainty": "a boundary crossing within the uncertainty envelope is not flagged",
    "override_flag": "JUSTICE inverts the reversibility flag it receives from IMPACT",
    "partial_binding": "the IDENTITY binding omits temporal persistence and higher-order attribution flags",
    "exclusion_erases_history": "exclusion erases the historical attribution of the excluded Subject",
    "final_output": "a Justice decision is marked final (no dispute allowed)",
    "refuse_appealable": "an appeal against an appealable decision is refused as 'not appealable'",
}
EXCLUSION_EFFECTS = ["removal from system participation", "loss of system-provided privileges",
                     "persistence of historical attribution"]                                      # JUSTICE §9


# shared definitions (declared readings) -------------------------------------------
def emitted_r(irreversible: bool, polarity: str) -> bool:
    """Rᵢ as IMPACT emits it.  IMPACT §4 calls Rᵢ 'a boolean indicator of physical or informational
    irreversibility' and does not say which value means what; JUSTICE §6/§8 do (True = reversible).
    'true_means_reversible' (default): both protocols use the JUSTICE polarity; 'true_means_irreversible':
    both use the plain reading of the IMPACT name; 'mixed': IMPACT the plain reading, JUSTICE its own
    (finding F-006, an undefined polarity, not a defect of either text)."""
    return (not irreversible) if polarity == "true_means_reversible" else bool(irreversible)


def justice_reversible(r_flag: bool, polarity: str) -> bool:
    """How JUSTICE reads a received Rᵢ."""
    return (not r_flag) if polarity == "true_means_irreversible" else bool(r_flag)


def impact(s0: float, s1: float, bound: float, u: float, irreversible: bool, faults=(),
           polarity: str = "true_means_reversible") -> Dict[str, Any]:
    """IMPACT §5: Iᵢ = (Sᵢ(t₁) − Sᵢ(t₀)) / Bᵢ; |Iᵢ| ≥ 1 flags a boundary crossing; Xᵢ on crossing (§8).
    Uᵢ: independent ±u on both states propagated linearly (H-DC-2).  Rᵢ by the declared polarity (H-DC-5)."""
    i = (s1 - s0) / bound
    ui = 2 * u / abs(bound)
    crossing = abs(i) >= 1
    if "suppress_by_uncertainty" in faults and abs(i) - ui < 1:
        crossing = False
    return {"I": round(i, 12), "B": bound, "R": emitted_r(irreversible, polarity), "X": crossing, "U": round(ui, 12),
            "boundary_crossing": crossing,
            "level_reached": (s1 >= bound) if bound > 0 else (s1 <= bound)}      # diagnostic, finding F-005


def bind(subjects: List[Dict[str, Any]], contributions: List[float], faults=()) -> Dict[str, float]:
    """IDENTITY §5–§6: proxies pass their contribution to the originator; weights proportional."""
    raw: Dict[str, float] = {}
    for s, c in zip(subjects, contributions):
        who = s["id"]
        if s["kind"] in PROXY_KINDS and "proxy_as_subject" not in faults:
            who = s["originator"]
        raw[who] = raw.get(who, 0.0) + c
    total = sum(raw.values())
    return {k: round(v / total, 12) for k, v in sorted(raw.items()) if v > 0} if total > 0 else {}


def received_flag(imp: Dict[str, Any], r: Dict[str, Any]) -> bool:
    """The Rᵢ JUSTICE works with: IMPACT's flag unchanged (IMPACT §11), unless a fault overrides it."""
    return (not imp["R"]) if "override_flag" in r["faults"] else bool(imp["R"])


def justice_domains(imp: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Optional[bool]]:
    """JUSTICE §6–§9 triggers; the received Rᵢ is read by the declared polarity (H-DC-5)."""
    reversible = justice_reversible(received_flag(imp, r), r["r_polarity"])
    margin = None if r["safe_margin"] < 0 else abs(imp["I"]) >= r["safe_margin"]
    if r["repeated_harm"] or r["mitigation_insufficient"] or margin:
        restriction: Optional[bool] = True
    else:
        restriction = None if margin is None else False
    return {
        "restitution": bool(reversible and r["mitigation_possible"]),
        "restriction": restriction,
        "isolation": bool((not reversible) or imp["X"] or r["systemic_risk"]),
        "exclusion": bool(r["persistent_axiom_violation"] or r["mitigation_and_isolation_failed"]
                          or r["refuses_compliance"]),
    }


def dispute_exception(r: Dict[str, Any]) -> bool:
    """JUSTICE §11 Dispute Exception Clause: conditions a) new admissible data, b) allegation,
    c) submitted through ERROR (always true here)."""
    a = r["appeal_new_data"]
    b = r["appeal_allegation"] != "none"
    return (a and b) if r["dispute_exception_reading"] == "all_conditions" else (a or b)


def dti(r: Dict[str, Any], t: int) -> Dict[str, Any]:
    d = r["start_dti_day"] + t // DAY
    return {"dti_day": d, "dy": canonical(*dy_doy(d))}


def md(validity: str, confidence: str, consistency: str, scope: str, reval: bool = False) -> Dict[str, Any]:
    return {"validity_state": validity, "confidence_state": confidence, "consistency_state": consistency,
            "scope_ref": scope, "revalidation_required": reval, "dispute_allowed": True}


# reference chain -------------------------------------------------------------------
def run_chain(r: Dict[str, Any]) -> Tuple[EventLog, Dict[str, Dict[str, Any]], Dict[str, Any]]:
    faults = set(r["faults"])
    log = EventLog("minute", tie_rule="order: measurement < evaluation < decision < action < notice; then event_id")
    store: Dict[str, Dict[str, Any]] = {}             # mutable records (the 'database'); the log keeps digests
    seq = {"n": 0}
    ORDER = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    scope = f"scenario/{r['data_type']}"
    ttl = TTL_TEXT[r["data_type"]]
    H = r["impact_horizon_minutes"]
    t_dec = H

    def put(kind, source, at, value=None, prov=(), epistemic=None, measured=None, decided=None, unit=None, unc=None,
            record=False):
        seq["n"] += 1
        eid = f"{source.lower()}-{seq['n']:03d}"
        m = log.append(Message(event_id=eid, kind=kind, source=source, arrived_at=at, measured_at=measured,
                               decided_at=decided, value=value, unit=unit, uncertainty=unc, epistemic=epistemic,
                               provenance=tuple(prov), order=ORDER[kind]))
        if record:
            store[eid] = copy.deepcopy({"event_id": eid, "value": value, "provenance": list(prov), "epistemic": epistemic})
            put("notice", "REGISTRY", at, {"recorded": eid, "digest": sha256_text(canonical_json(store[eid]))}, (eid,))
        return m

    contributions = [s["contribution"] for s in r["subjects"]]
    recorded_contrib = r["recorded_contributions"] or contributions

    def evaluate_chain(at, s1_msg, s0_msg, contrib, label):
        imp = impact(s0_msg.value, s1_msg.value, r["bound"], r["uncertainty"], r["irreversible"], faults,
                     r["r_polarity"])
        m_imp = put("evaluation", "IMPACT", at, imp, (s0_msg.event_id, s1_msg.event_id),
                    md("VALID", "SUFFICIENT_DATA", "CONSISTENT", scope), record=True)
        if r["attribution_threshold"] < 0:
            att = {"status": "BLOCKED", "reason": "minimum attribution confidence is defined by DKP-8-SIMULATION-001 "
                   "calibration, which does not exist", "weights": {}}
            emd = md("INVALID", "INSUFFICIENT_DATA", "UNRESOLVED", scope)
        elif r["attribution_confidence"] < r["attribution_threshold"]:
            att = {"status": "NO_ATTRIBUTION", "reason": f"confidence {r['attribution_confidence']} below threshold "
                   f"{r['attribution_threshold']}", "weights": {}}
            emd = md("INVALID", "INSUFFICIENT_DATA", "CONSISTENT", scope)
        else:
            att = {"status": "BOUND", "weights": bind(r["subjects"], contrib, faults),
                   "confidence": r["attribution_confidence"]}
            att["subjects"] = sorted(att["weights"])
            if "partial_binding" not in faults:                                                     # JUSTICE §3.2
                att["temporal_persistence"] = {"from_minute": 0, "to_minute": H, "repeated": bool(r["repeated_harm"])}
                att["higher_order_flags"] = sorted(f"{x['id']} -> {x['originator']}" for x in r["subjects"] if x["originator"] != "none")
            emd = md("VALID", "SUFFICIENT_DATA", "CONSISTENT", scope)
        m_att = put("evaluation", "IDENTITY", at, att, (m_imp.event_id,), emd, record=True)
        if att["status"] != "BOUND":
            put("notice", "L8-AUDIT", at, {"logged": m_att.event_id, "status": att["status"]}, (m_att.event_id,))
            if imp["boundary_crossing"]:
                put("notice", "L8-AUDIT", at, {"investigation_priority": "elevated", "attribution": "not predetermined"},
                    (m_att.event_id,))
            if att["status"] == "NO_ATTRIBUTION" and "enforce_no_attribution" not in faults:
                return m_imp, m_att, None
            if att["status"] == "BLOCKED":
                return m_imp, m_att, None
        doms = justice_domains(imp, r)
        weights = att["weights"] or bind(r["subjects"], contrib, faults)
        got = received_flag(imp, r)
        dec = {"label": label, "domains": doms, "shares": weights,
               "amounts": "not computed: no amount function in JUSTICE §6-§9",
               "flag": {"emitted_by_impact": imp["R"], "received": got,
                        "read_as": "reversible" if justice_reversible(got, r["r_polarity"]) else "irreversible",
                        "contract": "JUSTICE §6/§8: Rᵢ = True reversible, Rᵢ = False irreversible; no conversion (IMPACT §11)"}}
        if doms["exclusion"]:
            dec["exclusion_effects"] = EXCLUSION_EFFECTS[:2] + (["historical attribution erased"] if "exclusion_erases_history" in faults
                                                                else EXCLUSION_EFFECTS[2:])
        dmd = md("VALID", "SUFFICIENT_DATA", "CONSISTENT", scope, reval=True)
        if "final_output" in faults:
            dmd["dispute_allowed"] = False
        m_dec = put("decision", "JUSTICE", at, dec, (m_imp.event_id, m_att.event_id), dmd, decided=at, record=True)
        return m_imp, m_att, m_dec

    s0 = put("observation", "PTL", 0, r["s0"], measured=0, unit="model unit", unc=r["uncertainty"])
    s1 = put("observation", "PTL", H, r["s1_recorded"], measured=H, unit="model unit", unc=r["uncertainty"])
    imp1, att1, dec1 = evaluate_chain(t_dec, s1, s0, recorded_contrib, "original")
    put("notice", "ERROR", t_dec, {"state": "R0", **dti(r, t_dec)}, (s1.event_id,))
    active: Dict[str, str] = {}                        # enforcing domain -> action event id
    if dec1 is not None:
        for d in ENFORCING:
            if dec1.value["domains"][d]:
                a = put("action", "ENFORCEMENT", t_dec, {"apply": d, "subjects": sorted(dec1.value["shares"])},
                        (dec1.event_id,), decided=t_dec)
                active[d] = a.event_id
        if dec1.value["domains"]["restitution"]:
            put("notice", "JUSTICE", t_dec, {"restitution_obligation": dec1.value["shares"],
                                             "amount": "not computed"}, (dec1.event_id,))

    out = {"ttl": ttl, "t_dec": t_dec, "decision_1": dec1.event_id if dec1 else None, "final_decision": None,
           "appeal": None, "state": "R0", "bond": None, "active_final": None}
    if r["appeal_after_minutes"] < 0 or dec1 is None:
        out["active_final"] = sorted(active)
        out["final_decision"] = dec1.event_id if dec1 else None
        return log, store, out

    # ERROR: appeal ------------------------------------------------------------------
    ta = t_dec + r["appeal_after_minutes"]
    days = r["appeal_after_minutes"] / DAY
    appeal = put("notice", "APPELLANT", ta, {"appellant": r["appellant"], "decision": dec1.event_id,
                                             "category": r["appeal_category"],
                                             "references_decision": r["appeal_references_decision"],
                                             "evidence": r["appeal_has_evidence"], "new_data": r["appeal_new_data"],
                                             "allegation": r["appeal_allegation"], "bond": "posted", **dti(r, ta)},
                 (dec1.event_id,))
    out["appeal"] = appeal.event_id
    if "retaliate" in faults:
        put("action", "ENFORCEMENT", ta, {"apply": "restriction", "subjects": [r["appellant"]], "reason": "appeal"},
            (appeal.event_id,), decided=ta)
    # ERROR §3.2: a decision is appealable if it affects rights, access, assets or status, is derived from protocol
    # execution and is not marked irreversible by a higher-layer rule
    affects = any(bool(x) for x in dec1.value["domains"].values())
    if not (affects and not r["higher_layer_irreversible"]) or "refuse_appealable" in faults:
        put("notice", "ERROR", ta, {"state": "NOT_APPEALABLE", "reason": "marked irreversible by a higher-layer rule"
                                    if r["higher_layer_irreversible"] else "affects no right, access, asset or status", **dti(r, ta)},
            (appeal.event_id,))
        out.update(state="NOT_APPEALABLE", active_final=sorted(active), final_decision=dec1.event_id)
        return log, store, out
    formal = r["appeal_references_decision"] and r["appeal_has_evidence"]
    late = days > APPEAL_WINDOW_DAYS
    if r["appeal_category"] == "E1":
        late = late and "e1_time_barred" in faults
    else:
        late = late and "late_appeal_accepted" not in faults
    if not formal or late:
        put("notice", "ERROR", ta, {"state": "REJECTED_PROCEDURAL", "late": late, "formal": formal,
                                    "prejudice": "none", "bond": "returned (procedural rejection)", **dti(r, ta)},
            (appeal.event_id,))
        out.update(state="REJECTED_PROCEDURAL", active_final=sorted(active), final_decision=dec1.event_id)
        return log, store, out
    put("notice", "ERROR", ta, {"state": "R1", **dti(r, ta)}, (appeal.event_id,))

    # verification and its evidence
    new_obs = None
    if r["appeal_category"] == "E1":
        new_obs = put("observation", "PTL", ta, r["s1_true"], measured=H, unit="model unit", unc=r["uncertainty"],
                      prov=(appeal.event_id,))
        confirmed = abs(r["s1_true"] - r["s1_recorded"]) > 2 * r["uncertainty"]
    elif r["appeal_category"] == "E3":
        confirmed = bind(r["subjects"], recorded_contrib) != bind(r["subjects"], contributions)
    else:
        confirmed = r["declared_verification_outcome"] == "confirmed"
    tv = ta + r["verification_days"] * DAY
    # JUSTICE §11: periodic re-evaluation no more often than the minimum TTL; a qualifying dispute is exempt
    period = r["periodic_reevaluation_minutes"]
    last_eval = t_dec + ((ta - t_dec) // period) * period
    if ta - last_eval < ttl and not dispute_exception(r):
        tv = max(tv, last_eval + ttl)

    # status quo suspension (MAY): reversible contested decision, from validation, at most 7 DTI-Days
    if r["status_quo_suspension"] and active and r["enforcement_reversible"]:
        end = tv if "suspension_over_7_days" in faults else min(tv, ta + STATUS_QUO_MAX_DAYS * DAY)
        put("action", "ENFORCEMENT", ta, {"suspend": sorted(active), "until": end}, (appeal.event_id,), decided=ta)
        put("action", "ENFORCEMENT", end, {"resume": sorted(active)}, (appeal.event_id,), decided=end)

    if not confirmed:
        put("notice", "ERROR", tv, {"state": "REJECTED_UNFOUNDED", "bond": "audit costs", **dti(r, tv)},
            (appeal.event_id,))
        out.update(state="REJECTED_UNFOUNDED", bond="audit costs", active_final=sorted(active),
                   final_decision=dec1.event_id)
        return log, store, out

    evidence = new_obs.event_id if new_obs else appeal.event_id
    put("notice", "ERROR", tv, {"state": "R2", "validated_by": ["PTL", "protocol audit"], **dti(r, tv)},
        (evidence, appeal.event_id))
    out["bond"] = "kept" if "keep_bond" in faults else "returned"
    put("notice", "ERROR", tv, {"bond": out["bond"]}, (appeal.event_id,))
    s1_new = new_obs if new_obs else s1
    contrib_new = contributions if r["appeal_category"] == "E3" else recorded_contrib
    if "mutate_original" in faults:
        imp = impact(r["s0"], s1_new.value, r["bound"], r["uncertainty"], r["irreversible"], faults,
                         r["r_polarity"])
        store[dec1.event_id]["value"] = {**dec1.value, "label": "recomputed in place", "domains": justice_domains(imp, r),
                                         "shares": bind(r["subjects"], contrib_new, faults)}
        dec2_value, dec2_id = store[dec1.event_id]["value"], dec1.event_id
    else:
        _, _, dec2 = evaluate_chain(tv, s1_new, s0, contrib_new, "recomputed")
        if dec2 is None:
            dec2_value, dec2_id = None, None
        else:
            dec2_value, dec2_id = dec2.value, dec2.event_id
            delta = {d: [dec1.value["domains"][d], dec2.value["domains"][d]] for d in DOMAINS
                     if dec1.value["domains"][d] != dec2.value["domains"][d]}
            put("notice", "EB-DISPUTE", tv, {"delta": delta, "old": dec1.event_id, "new": dec2.event_id},
                (dec1.event_id, dec2.event_id))
    # R3: apply the recomputed Justice outcome — roll back what no longer applies, log irreversible effects
    new_domains = dec2_value["domains"] if dec2_value else {d: False for d in DOMAINS}
    for d in sorted(active):
        if not new_domains.get(d):
            put("action", "ENFORCEMENT", tv, {"lift": d}, (dec2_id or appeal.event_id,), decided=tv)
            put("notice", "ERROR", tv, {"irreversible_effect": f"{d} in force from minute {t_dec} to {tv}",
                                        "compensation": "owed where possible; amount function not defined"},
                (active[d],))
    for d in ENFORCING:
        if new_domains.get(d) and d not in active:
            put("action", "ENFORCEMENT", tv, {"apply": d, "subjects": sorted(dec2_value["shares"])},
                (dec2_id,), decided=tv)
    put("notice", "ERROR", tv, {"state": "R3", **dti(r, tv)}, (dec2_id or appeal.event_id,))
    out["state"] = "R3"
    if r["residual_dispute"]:
        put("notice", "ERROR", tv, {"state": "R4", **dti(r, tv)}, (appeal.event_id,))
        out["state"] = "R4"
    out["active_final"] = sorted(d for d in ENFORCING if new_domains.get(d))
    out["final_decision"] = dec2_id
    return log, store, out


# checker ---------------------------------------------------------------------------
def verdict(rid, check, ok, ok_text, bad_text, evidence=None):
    return CheckResult(rid, check, PASS if ok else FAIL, ok_text if ok else bad_text, evidence=evidence or {})


def na(rid, check, what, why):
    return CheckResult(rid, check, NOT_APPLICABLE, what, applicability=why)


def run_checks(r, log: EventLog, store, out) -> List[CheckResult]:
    msgs = log.messages()
    by = lambda kind=None, source=None: [m for m in msgs if (kind is None or m.kind == kind)
                                          and (source is None or m.source == source)]
    get = log.get
    res: List[CheckResult] = []
    imps, atts, decs = by("evaluation", "IMPACT"), by("evaluation", "IDENTITY"), by("decision", "JUSTICE")
    actions = by("action", "ENFORCEMENT")
    err = [m for m in by("notice", "ERROR") if "state" in m.value]
    # ERROR §3.2 appealable decision
    apps = [m for m in msgs if m.source == "APPELLANT"]
    if apps:
        d0 = get(apps[0].value["decision"])
        derived = {get(p).source for p in d0.provenance} <= {"IMPACT", "IDENTITY"}
        appealable = any(bool(x) for x in d0.value["domains"].values()) and derived and not r["higher_layer_irreversible"]
        refused = any(m.value.get("state") == "NOT_APPEALABLE" for m in msgs if m.source == "ERROR")
        res.append(verdict("ERROR-3.2-01", "appealable_definition", appealable != refused,
                           "the decision affects rights or access, derives from protocol execution and is not marked irreversible "
                           "by a higher-layer rule: the appeal was admitted" if appealable else
                           "the decision is marked irreversible by a higher-layer rule: the appeal was not admitted",
                           "the appeal was handled against the §3.2 definition"))
    else:
        res.append(na("ERROR-3.2-01", "appealable_definition", "appeals", "no appeal filed"))
    # JUSTICE Dispute Exception Clause: Core Invariant #3, no output is final
    outs = [m for m in msgs if m.epistemic is not None]
    bad = [m.event_id for m in outs if m.epistemic.get("dispute_allowed") is not True]
    res.append(verdict("JUSTICE-DisputeExceptionClause-03", "no_final_output", not bad,
                       f"none of {len(outs)} IMPACT, IDENTITY and JUSTICE outputs is final: each allows dispute and re-evaluation",
                       f"{len(bad)} outputs marked final"))
    states = [m.value["state"] for m in err]

    # IMPACT ---------------------------------------------------------------------------
    bad = []
    for m in imps:
        s0, s1 = (get(p) for p in m.provenance)
        expect = (s1.value - s0.value) / r["bound"]
        if abs(m.value["I"] - expect) > 1e-9:
            bad.append({"evaluation": m.event_id, "I": m.value["I"], "expected": expect})
    res.append(verdict("IMPACT-5-01", "impact_formula", not bad,
                       f"Iᵢ = (Sᵢ(t₁) − Sᵢ(t₀)) / Bᵢ recomputed from the observation messages for {len(imps)} evaluations",
                       f"{len(bad)} impact values differ from the §5 formula", {"violations": bad}))
    crossing = [m for m in imps if abs(m.value["I"]) >= 1]
    if crossing:
        miss = [m.event_id for m in crossing if not m.value["boundary_crossing"]]
        res.append(verdict("IMPACT-5-03", "boundary_flag", not miss, "every |Iᵢ| ≥ 1 is flagged as a boundary crossing",
                           f"{len(miss)} crossings not flagged", {"evaluations": miss}))
        miss = [m.event_id for m in crossing if not m.value["X"]]
        res.append(verdict("IMPACT-8-03", "externality_on_crossing", not miss, "Xᵢ = True on every boundary crossing",
                           f"{len(miss)} crossings without Xᵢ", {"evaluations": miss}))
        near = [m for m in crossing if abs(m.value["I"]) - m.value["U"] < 1]
        if near:
            miss = [m.event_id for m in near if not m.value["boundary_crossing"]]
            res.append(verdict("IMPACT-9-03", "uncertainty_does_not_suppress", not miss,
                               "crossings inside the uncertainty envelope are still flagged",
                               f"{len(miss)} crossings suppressed because of uncertainty", {"evaluations": miss}))
        else:
            res.append(na("IMPACT-9-03", "uncertainty_does_not_suppress", "suppression by uncertainty",
                          "no crossing lies within its uncertainty envelope"))
    else:
        why = "no |Iᵢ| ≥ 1 in this experiment"
        res.append(na("IMPACT-5-03", "boundary_flag", "boundary crossing flag", why))
        res.append(na("IMPACT-8-03", "externality_on_crossing", "externality on crossing", why))
        res.append(na("IMPACT-9-03", "uncertainty_does_not_suppress", "suppression by uncertainty", why))
    miss = [m.event_id for m in imps if not all(k in m.value for k in ("I", "B", "R", "X", "U"))]
    res.append(verdict("IMPACT-10-01", "impact_fields", not miss, "every impact output carries Iᵢ, Bᵢ, Rᵢ, Xᵢ, Uᵢ",
                       f"{len(miss)} impact outputs lack fields"))
    res.append(verdict("IMPACT-ReversibilityFlagR_-01", "r_is_irreversibility",
                       all(isinstance(m.value["R"], bool) and m.value["R"] == emitted_r(r["irreversible"], r["r_polarity"])
                           for m in imps),
                       f"Rᵢ is a boolean reversibility indicator under the declared polarity '{r['r_polarity']}' "
                       "(§4 does not fix the polarity)",
                       "Rᵢ is not a boolean or does not follow the declared polarity"))

    # IDENTITY -------------------------------------------------------------------------
    na_atts = [m for m in atts if m.value["status"] == "NO_ATTRIBUTION"]
    blocked = [m for m in atts if m.value["status"] == "BLOCKED"]

    def downstream_actions(src: str) -> List[str]:
        """Actions whose provenance chain reaches the message ``src``."""
        hit = []
        for a in actions:
            stack, seen = list(a.provenance), set()
            while stack:
                p = stack.pop()
                if p == src:
                    hit.append(a.event_id)
                    break
                if p not in seen:
                    seen.add(p)
                    stack.extend(get(p).provenance)
        return hit
    if blocked:
        res.append(CheckResult("IDENTITY-4.1-01", "no_attribution_output", UNKNOWN,
                               "the minimum attribution confidence is defined by DKP-8-SIMULATION-001 calibration, "
                               "which does not exist; admissibility cannot be decided and the chain is blocked",
                               evidence={"attribution": [m.event_id for m in blocked]}))
    elif r["attribution_confidence"] < r["attribution_threshold"]:
        ok = bool(na_atts) and all(m.epistemic["confidence_state"] == "INSUFFICIENT_DATA" for m in na_atts)
        res.append(verdict("IDENTITY-4.1-01", "no_attribution_output", ok,
                           "confidence below the declared threshold gives NO_ATTRIBUTION with INSUFFICIENT_DATA",
                           "confidence below the threshold did not give NO_ATTRIBUTION"))
    else:
        res.append(na("IDENTITY-4.1-01", "no_attribution_output", "NO_ATTRIBUTION output",
                      "attribution confidence meets the declared threshold"))
    if na_atts:
        cascade = sorted({a for m in na_atts for a in downstream_actions(m.event_id)})
        res.append(verdict("IDENTITY-4.1-02", "no_enforcement_cascade", not cascade,
                           "no enforcement action derives from a NO_ATTRIBUTION output",
                           f"{len(cascade)} enforcement actions derive from NO_ATTRIBUTION", {"actions": cascade}))
        logged = all(any(n.value.get("logged") == m.event_id for n in by("notice", "L8-AUDIT")) for m in na_atts)
        res.append(verdict("IDENTITY-4.1-03", "no_attribution_logged_deferred", logged and not cascade,
                           "NO_ATTRIBUTION logged for L8 audit; enforcement deferred",
                           "NO_ATTRIBUTION not logged or enforcement not deferred"))
        significant = [m for m in na_atts if get(m.provenance[0]).value["boundary_crossing"]]
        if significant:
            inv = all(any(n.value.get("investigation_priority") == "elevated" and m.event_id in n.provenance
                          for n in by("notice", "L8-AUDIT")) for m in significant)
            res.append(verdict("IDENTITY-4.1-04", "investigation_trigger", inv,
                               "NO_ATTRIBUTION on a boundary crossing raised investigation priority (H-DC-4)",
                               "no investigation trigger for a significant NO_ATTRIBUTION"))
        else:
            res.append(na("IDENTITY-4.1-04", "investigation_trigger", "investigation on significant NO_ATTRIBUTION",
                          "no NO_ATTRIBUTION on a boundary crossing"))
    else:
        why = "no NO_ATTRIBUTION output in this experiment"
        for rid, chk in (("IDENTITY-4.1-02", "no_enforcement_cascade"), ("IDENTITY-4.1-03", "no_attribution_logged_deferred"),
                         ("IDENTITY-4.1-04", "investigation_trigger")):
            res.append(na(rid, chk, "handling of NO_ATTRIBUTION", why))
    bound_atts = [m for m in atts if m.value["status"] == "BOUND"]
    proxies = {s["id"] for s in r["subjects"] if s["kind"] in PROXY_KINDS}
    if bound_atts and proxies:
        bad = sorted({p for m in bound_atts for p in m.value["weights"] if p in proxies})
        res.append(verdict("IDENTITY-5-03", "proxies_not_subjects", not bad,
                           "no smart contract, agent or script is bound as an independent Subject",
                           f"proxies bound as Subjects: {bad}"))
        ok = True
        for m in bound_atts:
            for s, c in zip(r["subjects"], contributions_for(r, atts.index(m))):
                if s["kind"] in PROXY_KINDS and c > 0 and s["originator"] not in m.value["weights"]:
                    ok = False
        res.append(verdict("IDENTITY-5-04", "proxy_actions_to_originator", ok,
                           "contributions of proxies are attributed to their originating Subjects",
                           "a proxy contribution is not attributed to its originator"))
    else:
        why = "no proxy Subject among the bound contributions" if bound_atts else "no binding in this experiment"
        res.append(na("IDENTITY-5-03", "proxies_not_subjects", "proxy Subjects", why))
        res.append(na("IDENTITY-5-04", "proxy_actions_to_originator", "proxy attribution", why))
    if bound_atts:
        bad = []
        for m in bound_atts:
            exp = bind(r["subjects"], contributions_for(r, atts.index(m)))
            got = m.value["weights"]
            if set(exp) != set(got) or any(abs(exp[k] - got[k]) > 1e-9 for k in exp):
                bad.append(m.event_id)
        res.append(verdict("IDENTITY-6-01", "proportional_weights", not bad,
                           "responsibility weights are proportional to the declared causal contributions",
                           "weights not proportional to contributions"))
    else:
        res.append(na("IDENTITY-6-01", "proportional_weights", "distribution of responsibility", "no binding"))

    # JUSTICE --------------------------------------------------------------------------
    if decs:
        bad = []
        for m in decs:
            srcs = {get(p).source for p in m.provenance}
            if not srcs <= {"IMPACT", "IDENTITY"}:
                bad.append(m.event_id)
        for rid in ("JUSTICE-2-02", "JUSTICE-2-03"):
            res.append(verdict(rid, "justice_inputs", not bad,
                               "every Justice decision derives only from IMPACT outputs and IDENTITY bindings (provenance)",
                               f"{len(bad)} decisions read other sources"))
        bad = [m.event_id for m in decs if set(m.value["domains"]) != set(DOMAINS)]
        res.append(verdict("JUSTICE-5-02", "all_domains_evaluated", not bad, "all four domains evaluated in every decision",
                           "a domain was not evaluated"))
        need = ("subjects", "weights", "temporal_persistence", "higher_order_flags")
        bad = [m.event_id for m in decs if not all(k in get(m.provenance[1]).value for k in need)]
        res.append(verdict("JUSTICE-3.2-01", "binding_contents", not bad,
                           "every decision rests on a binding with Subjects, responsibility weights, temporal persistence and "
                           "higher-order attribution flags", f"{len(bad)} decisions on an incomplete binding"))
        exc = [m for m in decs if m.value["domains"].get("exclusion")]
        if exc:
            bad = [m.event_id for m in exc if m.value.get("exclusion_effects") != EXCLUSION_EFFECTS]
            res.append(verdict("JUSTICE-9-02", "exclusion_consequences", not bad,
                               "exclusion removes participation and system privileges and keeps historical attribution",
                               f"{len(bad)} exclusions with other consequences"))
        else:
            res.append(na("JUSTICE-9-02", "exclusion_consequences", "exclusion", "no exclusion applies"))
        bad = [m.event_id for m in decs if not {get(p).source for p in m.provenance} <= {"IMPACT", "IDENTITY"}
               or (m.value.get("flag") and m.value["flag"]["received"] != get(m.provenance[0]).value["R"])]
        res.append(verdict("JUSTICE-13-02", "isolation_breach_critical", not bad,
                           "JUSTICE took IMPACT metrics and IDENTITY attribution as given: no cross-layer breach",
                           f"{len(bad)} decisions reinterpreted impact or attribution: a critical architectural breach"))
        # JUSTICE §6/§8 are checked literally on the flag JUSTICE received: Rᵢ = True means reversible, whatever
        # reading the run declares (the reading is not allowed to change what the check calls compliant)
        expected = {}
        for m in decs:
            imp = get(m.provenance[0]).value
            reversible = bool(m.value.get("flag", {}).get("received", imp["R"]))
            expected[m.event_id] = {
                "restitution": reversible and r["mitigation_possible"],
                "isolation": (not reversible) or imp["X"] or r["systemic_risk"],
                "exclusion": r["persistent_axiom_violation"] or r["mitigation_and_isolation_failed"] or r["refuses_compliance"]}
        for rid, d in (("JUSTICE-6-01", "restitution"), ("JUSTICE-8-01", "isolation"), ("JUSTICE-9-01", "exclusion")):
            bad = [m.event_id for m in decs if bool(m.value["domains"][d]) != bool(expected[m.event_id][d])]
            res.append(verdict(rid, f"{d}_trigger", not bad,
                               f"{d} applied exactly when its §{rid.split('-')[1]} conditions hold on the received Rᵢ "
                               "(True = reversible, as JUSTICE §6/§8 state)",
                               f"{d} trigger wrong in {bad}: the adapter read Rᵢ against JUSTICE §6/§8 "
                               f"(declared polarity '{r['r_polarity']}')"))
        # hand-over: JUSTICE must not override the flag (IMPACT §11)
        bad = [m.event_id for m in decs if m.value.get("flag") and
               m.value["flag"]["received"] != get(m.provenance[0]).value["R"]]
        res.append(verdict("IMPACT-11-01", "no_flag_override", not bad,
                           "every Justice decision used the reversibility flag exactly as IMPACT emitted it",
                           f"{len(bad)} decisions overrode the IMPACT flag (IMPACT §11)"))
        # chain contract: the flag IMPACT emits must mean, under the only stated polarity (JUSTICE §6/§8), the declared
        # physical reversibility
        bad = [m.event_id for m in decs if get(m.provenance[0]).value["R"] != (not r["irreversible"])]
        res.append(verdict("JUSTICE-3.1-01", "flag_contract", not bad,
                           f"the IMPACT flag (Rᵢ = {get(decs[0].provenance[0]).value['R']}) means what JUSTICE reads: the impact "
                           f"is {'ir' if r['irreversible'] else ''}reversible",
                           f"IMPACT emitted Rᵢ = {get(decs[0].provenance[0]).value['R']} for an "
                           f"{'ir' if r['irreversible'] else ''}reversible impact; under JUSTICE §6/§8 it means the opposite "
                           "(IMPACT §4 fixes no polarity: F-006)"))
        if r["safe_margin"] < 0 and not (r["repeated_harm"] or r["mitigation_insufficient"]):
            res.append(CheckResult("JUSTICE-7-01", "restriction_trigger", UNKNOWN,
                                   "'axiom-defined safe margins' have no numeric value in the corpus; whether the "
                                   "impact exceeds them cannot be decided"))
        else:
            ok = all(bool(m.value["domains"]["restriction"]) == bool(
                r["repeated_harm"] or r["mitigation_insufficient"] or
                (r["safe_margin"] >= 0 and abs(get(m.provenance[0]).value["I"]) >= r["safe_margin"])) for m in decs)
            res.append(verdict("JUSTICE-7-01", "restriction_trigger", ok, "restriction applied exactly when a §7 condition holds",
                               "restriction trigger wrong"))
        restit = [m for m in decs if m.value["domains"]["restitution"]]
        if restit:
            res.append(CheckResult("JUSTICE-6-02", "restitution_outputs", UNKNOWN,
                                   "restitution applies, but mitigation scope, obligations and time limits need an "
                                   "amount function the texts do not give; the lab computes shares only"))
        else:
            res.append(na("JUSTICE-6-02", "restitution_outputs", "restitution computation", "restitution does not apply"))
        multi = [m for m in decs if len(m.value["shares"]) > 1]
        if multi:
            bad = []
            for m in multi:
                att = get(m.provenance[1]).value
                for k, v in m.value["shares"].items():
                    if abs(v - att["weights"].get(k, -1)) > 1e-9:
                        bad.append({"decision": m.event_id, "subject": k})
            res.append(verdict("JUSTICE-10-01", "proportional_distribution", not bad,
                               "consequence shares equal responsibility weights; no Subject above its contribution",
                               f"{len(bad)} shares differ from responsibility weights"))
        else:
            res.append(na("JUSTICE-10-01", "proportional_distribution", "distribution among Subjects",
                          "one responsible Subject"))
    else:
        why = "no Justice decision (attribution blocked or NO_ATTRIBUTION)"
        for rid, chk in (("JUSTICE-3.2-01", "binding_contents"), ("JUSTICE-9-02", "exclusion_consequences"),
                         ("JUSTICE-13-02", "isolation_breach_critical"),
                         ("JUSTICE-2-02", "justice_inputs"), ("JUSTICE-2-03", "justice_inputs"),
                         ("JUSTICE-5-02", "all_domains_evaluated"), ("JUSTICE-6-01", "restitution_trigger"),
                         ("JUSTICE-7-01", "restriction_trigger"), ("JUSTICE-8-01", "isolation_trigger"),
                         ("JUSTICE-9-01", "exclusion_trigger"), ("JUSTICE-6-02", "restitution_outputs"),
                         ("JUSTICE-10-01", "proportional_distribution")):
            res.append(na(rid, chk, "Justice evaluation", why))
    ttl = out["ttl"]
    res.append(verdict("JUSTICE-11-02", "periodic_not_faster_than_ttl", r["periodic_reevaluation_minutes"] >= ttl,
                       f"scheduled re-evaluation every {r['periodic_reevaluation_minutes']} min; minimum TTL {ttl} min",
                       f"scheduled re-evaluation every {r['periodic_reevaluation_minutes']} min is faster than the "
                       f"minimum TTL {ttl} min"))

    # ERROR ----------------------------------------------------------------------------
    appeal = get(out["appeal"]) if out["appeal"] else None
    if appeal is None:
        why = "no appeal in this experiment" if r["appeal_after_minutes"] < 0 else "no Justice decision to appeal"
        for rid, chk in ERROR_CHECKS:
            res.append(na(rid, chk, "appeal handling", why))
        for rid, chk in (("JUSTICE-DisputeExceptionClause-01", "dispute_not_blocked_by_ttl"),
                         ("JUSTICE-DisputeExceptionClause-02", "dispute_exception_conditions")):
            res.append(na(rid, chk, "dispute exception", why))
        res += dispute_checks(r, log, store, out, None)
        return res
    days = (appeal.arrived_at - out["t_dec"]) / DAY
    formal = r["appeal_references_decision"] and r["appeal_has_evidence"]
    rejected = "REJECTED_PROCEDURAL" in states
    res.append(verdict("ERROR-7-01", "appeal_fields", (not formal) == rejected or (formal and days > APPEAL_WINDOW_DAYS),
                       "appeals are validated exactly when they reference the decision, carry evidence and a category",
                       "formal requirements not applied"))
    if r["appeal_category"] != "E1":
        if days > APPEAL_WINDOW_DAYS:
            res.append(verdict("ERROR-7-02", "appeal_window", rejected,
                               f"appeal after {days:g} DTI-Days rejected (window 30)",
                               f"appeal after {days:g} DTI-Days accepted (window 30)"))
        else:
            res.append(verdict("ERROR-7-02", "appeal_window", formal == ("R1" in states),
                               f"appeal after {days:g} DTI-Days handled within the 30-day window",
                               "an appeal within the window was not handled"))
        res.append(na("ERROR-7-03", "e1_no_limitation", "E1 exception", "the appeal is not of category E1"))
    else:
        res.append(na("ERROR-7-02", "appeal_window", "30-day window", "E1 appeals have no limitation period"))
        if days > APPEAL_WINDOW_DAYS:
            res.append(verdict("ERROR-7-03", "e1_no_limitation", not rejected or not formal,
                               f"E1 appeal after {days:g} DTI-Days accepted", f"E1 appeal after {days:g} DTI-Days barred as late"))
        else:
            res.append(na("ERROR-7-03", "e1_no_limitation", "E1 exception", "the appeal is within 30 DTI-Days"))
    susp = [a for a in actions if "suspend" in a.value]
    if susp:
        bad = [a.event_id for a in susp if a.value["until"] - a.arrived_at > STATUS_QUO_MAX_DAYS * DAY
               or "R1" not in states or not r["enforcement_reversible"]]
        res.append(verdict("ERROR-7-04", "status_quo_suspension", not bad,
                           "status quo suspension after validation, of a reversible decision, at most 7 DTI-Days",
                           "status quo suspension beyond 7 DTI-Days or without validation", {"suspensions": bad}))
    else:
        res.append(na("ERROR-7-04", "status_quo_suspension", "status quo suspension",
                      "no suspension (optional, or nothing to suspend)"))
    retaliation = [a.event_id for a in actions if appeal.event_id in a.provenance and "apply" in a.value]
    if rejected:
        res.append(verdict("ERROR-7-05", "procedural_rejection_without_prejudice", not retaliation,
                           "procedural rejection without new measures", "rejection with new measures"))
    else:
        res.append(na("ERROR-7-05", "procedural_rejection_without_prejudice", "procedural rejection",
                      "the appeal met the formal requirements"))
    res.append(verdict("ERROR-11-02", "no_retaliation", not retaliation, "no measure derives from the act of appealing",
                       f"{len(retaliation)} measures derive from the appeal", {"actions": retaliation}))
    if "R2" in states:
        r2 = next(m for m in err if m.value["state"] == "R2")
        via_ptl = any(get(p).kind == "observation" or p == appeal.event_id for p in r2.provenance)
        res.append(verdict("ERROR-5-03", "r2_validated", via_ptl and r2.value.get("validated_by") == ["PTL", "protocol audit"],
                           "R2 reached with PTL evidence and protocol audit", "R2 without PTL validation"))
        res.append(verdict("ERROR-6-02", "bond_returned", out["bond"] == "returned", "bond returned in full after R2",
                           "bond not returned after a confirmed error"))
        res.append(na("ERROR-6-03", "bond_to_audit", "bond for unfounded appeals", "the error was confirmed"))
        recomputed = [m for m in decs if m.arrived_at >= r2.arrived_at]
        res.append(verdict("ERROR-8-01", "recompute_after_confirmation", bool(recomputed),
                           "affected outputs recomputed after R2 (new IMPACT, IDENTITY and JUSTICE messages)",
                           "no recomputation after R2"))
        if recomputed:
            d2 = recomputed[0]
            imp2, att2 = get(d2.provenance[0]), get(d2.provenance[1])
            if r["appeal_category"] == "E1":
                corrected = any(get(p).kind == "observation" and get(p).arrived_at >= appeal.arrived_at
                                for p in imp2.provenance)
            elif r["appeal_category"] == "E3":
                corrected = att2.value["weights"] == bind(r["subjects"], [s["contribution"] for s in r["subjects"]])
            else:
                corrected = imp2.arrived_at >= appeal.arrived_at
            res.append(verdict("ERROR-8-04", "justice_uses_corrected_inputs", corrected,
                               "the re-invoked Justice decision derives from the corrected inputs",
                               "re-invoked Justice did not use corrected inputs"))
            d1 = get(out["decision_1"])
            lifted = {a.value["lift"] for a in actions if "lift" in a.value}
            should = {d for d in ENFORCING if d1.value["domains"][d] and not d2.value["domains"][d]}
            res.append(verdict("ERROR-8-02", "rollback_reversible", lifted == should,
                               f"measures no longer supported were lifted: {sorted(should) or 'none'}",
                               f"lifted {sorted(lifted)}, expected {sorted(should)}"))
            logged = {n.value["irreversible_effect"].split(" ")[0] for n in by("notice", "ERROR") if "irreversible_effect" in n.value}
            if should:
                res.append(verdict("ERROR-8-03", "irreversible_logged", logged >= should,
                                   "elapsed effects of lifted measures logged with a compensation note (amount undefined)",
                                   "irreversible effects not logged"))
            else:
                res.append(na("ERROR-8-03", "irreversible_logged", "irreversible effects", "no measure was lifted"))
            harsher = [d for d in DOMAINS if d2.value["domains"][d] and not d1.value["domains"][d]]
            if retaliation:
                res.append(CheckResult("ERROR-8-05", "no_new_penalties", FAIL, "ERROR handling added measures",
                                       evidence={"actions": retaliation}))
            elif harsher:
                res.append(CheckResult("ERROR-8-05", "no_new_penalties", UNKNOWN,
                                       f"the recomputed Justice outcome adds {harsher}; whether a harsher recomputed "
                                       "outcome is a 'new penalty' introduced by ERROR is not stated (open question Q-021)",
                                       evidence={"added_domains": harsher}))
            else:
                res.append(PASS_CHECK("ERROR-8-05", "no_new_penalties", "the correction added no measure"))
            final = set(out["active_final"])
            res.append(verdict("ERROR-2-05", "request_not_override",
                               final == {d for d in ENFORCING if d2.value["domains"][d]},
                               "the enforced measures after correction are exactly those of the recomputed Justice decision",
                               "ERROR changed the outcome beyond the recomputed Justice decision"))
        else:
            for rid, chk in (("ERROR-8-04", "justice_uses_corrected_inputs"), ("ERROR-8-02", "rollback_reversible"),
                             ("ERROR-8-03", "irreversible_logged"), ("ERROR-8-05", "no_new_penalties"),
                             ("ERROR-2-05", "request_not_override")):
                res.append(CheckResult(rid, chk, FAIL if "mutate_original" in r["faults"] else UNKNOWN,
                                       "no recomputed Justice decision exists"))
        r3 = [m for m in err if m.value["state"] == "R3"]
        res.append(verdict("ERROR-5-04", "r3_requires_correction", bool(r3) and bool(
            [a for a in actions if a.arrived_at == r3[0].arrived_at] or decs[-1].arrived_at == r3[0].arrived_at),
            "R3 recorded with the corrective actions and recomputation of the same DTI-Day", "R3 without correction"))
        if "R4" in states:
            res.append(verdict("ERROR-5-05", "r4_after_r3", states.index("R4") > states.index("R3"),
                               "R4 follows a completed correction with the appeal unresolved", "R4 before correction"))
        else:
            res.append(na("ERROR-5-05", "r4_after_r3", "residual dispute", "no residual dispute declared"))
    else:
        for rid, chk in (("ERROR-5-03", "r2_validated"), ("ERROR-6-02", "bond_returned"), ("ERROR-8-01", "recompute_after_confirmation"),
                         ("ERROR-8-04", "justice_uses_corrected_inputs"), ("ERROR-8-02", "rollback_reversible"),
                         ("ERROR-8-03", "irreversible_logged"), ("ERROR-2-05", "request_not_override"),
                         ("ERROR-5-04", "r3_requires_correction"), ("ERROR-5-05", "r4_after_r3")):
            res.append(na(rid, chk, "correction", "the error was not confirmed"))
        if "REJECTED_UNFOUNDED" in states:
            res.append(verdict("ERROR-6-03", "bond_to_audit", out["bond"] == "audit costs",
                               "bond of an unfounded appeal used for audit costs", "bond not handled"))
        else:
            res.append(na("ERROR-6-03", "bond_to_audit", "bond for unfounded appeals", "the appeal was not rejected as unfounded"))
        if retaliation:
            res.append(CheckResult("ERROR-8-05", "no_new_penalties", FAIL, "ERROR handling added measures"))
        else:
            res.append(na("ERROR-8-05", "no_new_penalties", "penalties introduced by correction", "no correction"))
    bad = [m.event_id for m in err if "dti_day" not in m.value or not m.provenance]
    res.append(verdict("ERROR-10-01", "case_logged", not bad, "every error state is logged with DTI-Day and provenance",
                       f"{len(bad)} error states without DTI-Day or anchoring"))
    # JUSTICE §11 dispute exception
    if "R1" in states:
        period, ttl = r["periodic_reevaluation_minutes"], out["ttl"]
        last_eval = out["t_dec"] + ((appeal.arrived_at - out["t_dec"]) // period) * period
        within = appeal.arrived_at - last_eval < ttl
        if within:
            a, b = r["appeal_new_data"], r["appeal_allegation"] != "none"
            both, either = a and b, a or b
            qualifies = both if r["dispute_exception_reading"] == "all_conditions" else either
            r2_or_rej = next((m for m in err if m.value["state"] in ("R2", "REJECTED_UNFOUNDED")), None)
            waited = r2_or_rej is not None and r2_or_rej.arrived_at > appeal.arrived_at + r["verification_days"] * DAY
            if qualifies:
                res.append(verdict("JUSTICE-DisputeExceptionClause-01", "dispute_not_blocked_by_ttl", not waited,
                                   "a qualifying dispute was processed without waiting for the TTL",
                                   "a qualifying dispute waited for the TTL"))
            else:
                res.append(na("JUSTICE-DisputeExceptionClause-01", "dispute_not_blocked_by_ttl", "TTL exemption",
                              f"the dispute does not qualify under the reading '{r['dispute_exception_reading']}'"))
            if both != either:
                res.append(CheckResult("JUSTICE-DisputeExceptionClause-02", "dispute_exception_conditions", UNKNOWN,
                                       "the dispute satisfies only one of a) new admissible data and b) an allegation; "
                                       "whether a)-c) are joint or alternative conditions decides whether the TTL "
                                       f"applies (open question Q-020); computed under '{r['dispute_exception_reading']}'",
                                       evidence={"new_data": a, "allegation": r["appeal_allegation"], "waited_for_ttl": waited}))
            else:
                res.append(verdict("JUSTICE-DisputeExceptionClause-02", "dispute_exception_conditions",
                                   waited != qualifies,
                                   f"both readings agree: the exception {'applies' if qualifies else 'does not apply'}, "
                                   "and the dispute was handled accordingly",
                                   "the dispute was not handled as both readings require"))
        else:
            for rid, chk in (("JUSTICE-DisputeExceptionClause-01", "dispute_not_blocked_by_ttl"),
                             ("JUSTICE-DisputeExceptionClause-02", "dispute_exception_conditions")):
                res.append(na(rid, chk, "TTL exemption for disputes", "the dispute arrives after the TTL of the last evaluation"))
    else:
        for rid, chk in (("JUSTICE-DisputeExceptionClause-01", "dispute_not_blocked_by_ttl"),
                         ("JUSTICE-DisputeExceptionClause-02", "dispute_exception_conditions")):
            res.append(na(rid, chk, "dispute exception", "the appeal was not validated"))
    res += dispute_checks(r, log, store, out, appeal)
    return res


def contributions_for(r: Dict[str, Any], index: int) -> List[float]:
    """Contributions behind the index-th attribution: the recorded ones first; the true ones after an E3 correction."""
    true = [s["contribution"] for s in r["subjects"]]
    recorded = r["recorded_contributions"] or true
    if index == 0:
        return recorded
    return true if r["appeal_category"] == "E3" else recorded


def PASS_CHECK(rid, check, text):
    return CheckResult(rid, check, PASS, text)


ERROR_CHECKS = [("ERROR-7-01", "appeal_fields"), ("ERROR-7-02", "appeal_window"), ("ERROR-7-03", "e1_no_limitation"),
                ("ERROR-7-04", "status_quo_suspension"), ("ERROR-7-05", "procedural_rejection_without_prejudice"),
                ("ERROR-11-02", "no_retaliation"), ("ERROR-5-03", "r2_validated"), ("ERROR-6-02", "bond_returned"),
                ("ERROR-6-03", "bond_to_audit"), ("ERROR-8-01", "recompute_after_confirmation"),
                ("ERROR-8-04", "justice_uses_corrected_inputs"), ("ERROR-8-02", "rollback_reversible"),
                ("ERROR-8-03", "irreversible_logged"), ("ERROR-8-05", "no_new_penalties"),
                ("ERROR-2-05", "request_not_override"), ("ERROR-5-04", "r3_requires_correction"),
                ("ERROR-5-05", "r4_after_r3"), ("ERROR-10-01", "case_logged")]


def dispute_checks(r, log, store, out, appeal) -> List[CheckResult]:
    """EPISTEMIC-BOUNDARIES §7.2 for the Justice decision under appeal."""
    res: List[CheckResult] = []
    msgs = log.messages()
    if appeal is None or "R2" not in [m.value.get("state") for m in msgs if m.source == "ERROR"]:
        why = "no confirmed dispute in this experiment"
        for rid, chk in (("EB-7.2-01", "dispute_preserves_original"), ("EB-7.2-02", "dispute_new_evaluation"),
                         ("EB-7.2-03", "dispute_recomputes"), ("EB-7.2-04", "dispute_delta")):
            res.append(na(rid, chk, "dispute processing", why))
        return res
    d1 = out["decision_1"]
    digest = next(m.value["digest"] for m in msgs if m.source == "REGISTRY" and m.value["recorded"] == d1)
    res.append(verdict("EB-7.2-01", "dispute_preserves_original", sha256_text(canonical_json(store[d1])) == digest,
                       "the original Justice decision record is unchanged", "the original decision was changed in place"))
    new = out["final_decision"]
    res.append(verdict("EB-7.2-02", "dispute_new_evaluation", bool(new) and new != d1,
                       "the dispute produced a new decision event", "no new decision event"))
    if new and new != d1:
        prov = log.get(new).provenance
        upstream = [log.get(p) for p in prov]
        fresh = any(m.arrived_at >= appeal.arrived_at for m in upstream)
        res.append(verdict("EB-7.2-03", "dispute_recomputes", fresh,
                           "the new decision was recomputed from inputs evaluated after the dispute",
                           "the new decision reuses pre-dispute inputs"))
    else:
        res.append(CheckResult("EB-7.2-03", "dispute_recomputes", FAIL, "no recomputation recorded"))
    delta = [m for m in msgs if m.source == "EB-DISPUTE"]
    res.append(verdict("EB-7.2-04", "dispute_delta", bool(delta), "a comparative delta between decisions was produced",
                       "no comparative delta"))
    return res


IMPLEMENTS = {
    "IMPACT-5-01": ("impact_formula", "IMPLEMENTED", None),
    "IMPACT-5-03": ("boundary_flag", "IMPLEMENTED", None),
    "IMPACT-8-03": ("externality_on_crossing", "PARTIAL", "Reads 'boundary crossing' in §8 as the §5 flag; system-boundary scope is not modelled."),
    "IMPACT-9-03": ("uncertainty_does_not_suppress", "IMPLEMENTED", None),
    "IMPACT-10-01": ("impact_fields", "IMPLEMENTED", None),
    "IMPACT-ReversibilityFlagR_-01": ("r_is_irreversibility", "PARTIAL", "Physical reversibility is declared on input (the §7 criteria are not computable); polarity per H-DC-5 (F-006)."),
    "IDENTITY-4.1-01": ("no_attribution_output", "PARTIAL", "The threshold comes from a calibration that does not exist; without a declared threshold the chain is blocked (UNKNOWN)."),
    "IDENTITY-4.1-02": ("no_enforcement_cascade", "IMPLEMENTED", None),
    "IDENTITY-4.1-03": ("no_attribution_logged_deferred", "IMPLEMENTED", None),
    "IDENTITY-4.1-04": ("investigation_trigger", "PARTIAL", "'Significant impact' read as a boundary crossing (H-DC-4)."),
    "IDENTITY-5-03": ("proxies_not_subjects", "IMPLEMENTED", None),
    "IDENTITY-5-04": ("proxy_actions_to_originator", "PARTIAL", "Counter-bindings are not modelled."),
    "IDENTITY-6-01": ("proportional_weights", "PARTIAL", "Causal contributions are given on input."),
    "JUSTICE-2-02": ("justice_inputs", "IMPLEMENTED", None),
    "JUSTICE-2-03": ("justice_inputs", "IMPLEMENTED", None),
    "JUSTICE-5-02": ("all_domains_evaluated", "IMPLEMENTED", None),
    "IMPACT-11-01": ("no_flag_override", "PARTIAL", "Only the reversibility flag hand-over is observed."),
    "JUSTICE-3.1-01": ("flag_contract", "PARTIAL", "The reversibility flag only; physical reversibility is declared."),
    "JUSTICE-6-01": ("restitution_trigger", "PARTIAL", "Rᵢ polarity from JUSTICE §6; IMPACT §4 leaves it open (F-006); mitigation possibility is an input."),
    "JUSTICE-6-02": ("restitution_outputs", "PARTIAL", "Amounts and time limits need an amount function the texts do not give: UNKNOWN."),
    "JUSTICE-7-01": ("restriction_trigger", "PARTIAL", "Safe margins have no numeric value: UNKNOWN unless declared."),
    "JUSTICE-8-01": ("isolation_trigger", "PARTIAL", "Rᵢ polarity from JUSTICE §8; IMPACT §4 leaves it open (F-006); systemic risk is an input."),
    "JUSTICE-9-01": ("exclusion_trigger", "PARTIAL", "Trigger conditions are inputs."),
    "JUSTICE-10-01": ("proportional_distribution", "IMPLEMENTED", None),
    "JUSTICE-11-02": ("periodic_not_faster_than_ttl", "IMPLEMENTED", None),
    "JUSTICE-DisputeExceptionClause-01": ("dispute_not_blocked_by_ttl", "PARTIAL", "Two readings of the conditions a)-c) (open question Q-020)."),
    "JUSTICE-DisputeExceptionClause-03": ("no_final_output", "IMPLEMENTED", None),
    "ERROR-3.2-01": ("appealable_definition", "PARTIAL", "'Marked irreversible by a higher-layer rule' is a declared flag."),
    "JUSTICE-3.2-01": ("binding_contents", "PARTIAL", "Persistence and higher-order flags are built from the scenario (harm window, proxies)."),
    "JUSTICE-9-02": ("exclusion_consequences", "IMPLEMENTED", None),
    "JUSTICE-13-02": ("isolation_breach_critical", "PARTIAL", "A breach is a decision on other sources or an overridden IMPACT flag."),
    "JUSTICE-DisputeExceptionClause-02": ("dispute_exception_conditions", "PARTIAL", "Two readings of the conditions a)-c) (open question Q-020)."),
    "ERROR-2-05": ("request_not_override", "IMPLEMENTED", None),
    "ERROR-5-03": ("r2_validated", "PARTIAL", "Verification of E2, E4, E5 is declared on input; E1 and E3 are modelled."),
    "ERROR-5-04": ("r3_requires_correction", "IMPLEMENTED", None),
    "ERROR-5-05": ("r4_after_r3", "IMPLEMENTED", None),
    "ERROR-6-02": ("bond_returned", "IMPLEMENTED", None),
    "ERROR-6-03": ("bond_to_audit", "IMPLEMENTED", None),
    "ERROR-7-01": ("appeal_fields", "IMPLEMENTED", None),
    "ERROR-7-02": ("appeal_window", "IMPLEMENTED", None),
    "ERROR-7-03": ("e1_no_limitation", "IMPLEMENTED", None),
    "ERROR-7-04": ("status_quo_suspension", "IMPLEMENTED", None),
    "ERROR-7-05": ("procedural_rejection_without_prejudice", "IMPLEMENTED", None),
    "ERROR-8-01": ("recompute_after_confirmation", "IMPLEMENTED", None),
    "ERROR-8-02": ("rollback_reversible", "PARTIAL", "Enforcement measures are treated as reversible unless declared otherwise."),
    "ERROR-8-03": ("irreversible_logged", "PARTIAL", "Compensation amounts are not defined; only the log entry is checked."),
    "ERROR-8-04": ("justice_uses_corrected_inputs", "IMPLEMENTED", None),
    "ERROR-8-05": ("no_new_penalties", "PARTIAL", "A harsher recomputed outcome gives UNKNOWN (open question Q-021)."),
    "ERROR-10-01": ("case_logged", "IMPLEMENTED", None),
    "ERROR-11-02": ("no_retaliation", "IMPLEMENTED", None),
    "EB-7.2-01": ("dispute_preserves_original", "IMPLEMENTED", None),
    "EB-7.2-02": ("dispute_new_evaluation", "IMPLEMENTED", None),
    "EB-7.2-03": ("dispute_recomputes", "PARTIAL", "Admissibility of new data is the appeal's evidence only."),
    "EB-7.2-04": ("dispute_delta", "IMPLEMENTED", None),
}

SUBJECT = {"type": "object", "fields": {
    "id": {"type": "str"},
    "kind": {"type": "enum", "values": list(SUBJECT_KINDS)},
    "contribution": {"type": "number", "min": 0, "max": 10 ** 9},
    "originator": {"type": "str", "default": "none"},
}}


class DisputeCorrectionModule(LabModule):
    id = "dispute_correction"
    version = "1.2.0"
    title = {"en": "Dispute and correction (S-LAB-04)", "ru": "Спор и исправление (S-LAB-04)"}
    summary = {"en": "A measurement or an attribution was wrong: is the appeal accepted in time, is the decision "
                     "recomputed without new penalties, is the original kept and the difference shown?",
               "ru": "Измерение или привязка были ошибочны: принимается ли апелляция в срок, пересчитывается ли "
                     "решение без новых наказаний, сохраняется ли оригинал и показана ли разница?"}
    protocols = ["DKP-1-IMPACT-001", "DKP-1-IDENTITY-001", "DKP-1-JUSTICE-001", "DKP-4-ERROR-001",
                 "DKP-1-EPISTEMIC-BOUNDARIES-001"]
    example_order = ["measurement_error_corrected", "same_with_faulty_chain", "late_e3_appeal", "late_e1_appeal",
                     "unfounded_appeal", "no_attribution", "calibration_missing", "proxy_attribution",
                     "harsher_recomputation", "polarity_true_irreversible", "polarity_mixed", "impact_example_s13", "dispute_within_ttl_all",
                     "dispute_within_ttl_either"]
    implements = IMPLEMENTS
    alternative_examples = ["polarity_true_irreversible", "polarity_mixed", "dispute_within_ttl_either"]
    tests = ["tests/lab/test_dispute_correction_module.py"]
    causal_note = {"en": "Causal contributions of Subjects are given on input: the lab checks a declared causal binding; "
                         "it does not infer causality from measurements.",
                   "ru": "Причинный вклад субъектов задан на входе: лаборатория проверяет объявленную причинную связь, "
                         "а не выводит её из измерений."}
    hypotheses = [
        {"id": "H-DC-1", "source": "hypothesis", "text": {
            "en": "One impact channel; the reference bound Bᵢ is declared on input (AXIOMS give no numeric bounds).",
            "ru": "Один канал воздействия; граница Bᵢ задаётся на входе (AXIOMS не дают числовых границ)."}},
        {"id": "H-DC-2", "source": "hypothesis", "text": {
            "en": "Uᵢ = 2u/|Bᵢ| for independent ±u on both states; an E1 error is confirmed when the corrected and the "
                  "recorded value differ by more than 2u (their envelopes do not overlap).",
            "ru": "Uᵢ = 2u/|Bᵢ| при независимых ±u обоих состояний; ошибка E1 подтверждается, если исправленное и "
                  "записанное значения различаются больше чем на 2u (интервалы не пересекаются)."}},
        {"id": "H-DC-3", "source": "hypothesis", "text": {
            "en": "Enforcement measures (restriction, isolation, exclusion) are reversible unless declared otherwise; "
                  "elapsed time under a measure is an irreversible effect.",
            "ru": "Меры (ограничение, изоляция, исключение) обратимы, если не объявлено иное; прошедшее под мерой "
                  "время — необратимый эффект."}},
        {"id": "H-DC-4", "source": "hypothesis", "text": {
            "en": "'Significant impact' (IDENTITY §4.1 c) is read as a boundary crossing |Iᵢ| ≥ 1.",
            "ru": "'Существенное воздействие' (IDENTITY §4.1 c) понимается как пересечение границы |Iᵢ| ≥ 1."}},
        {"id": "H-DC-5", "source": "text", "text": {
            "en": "Polarity of Rᵢ: IMPACT §4 does not fix it, JUSTICE §6/§8 do (True = reversible). Default "
                  "'true_means_reversible' applies the JUSTICE polarity in both protocols; 'true_means_irreversible' "
                  "applies the plain reading of the IMPACT name in both; 'mixed' shows what an implementation that "
                  "follows each text separately does (finding F-006).",
            "ru": "Полярность Rᵢ: IMPACT §4 её не фиксирует, JUSTICE §6/§8 фиксируют (True = обратимо). По умолчанию "
                  "'true_means_reversible' — полярность JUSTICE в обоих протоколах; 'true_means_irreversible' — бытовое "
                  "прочтение названия в IMPACT в обоих; 'mixed' — что делает реализация, которая следует каждому "
                  "тексту по отдельности (находка F-006)."}},
        {"id": "H-DC-6", "source": "alternative", "text": {
            "en": "Dispute exception (JUSTICE §11): 'all_conditions' — a), b) and c) together (the list after 'provided'); "
                  "'data_or_allegation' — a) or b), with c).",
            "ru": "Исключение для споров (JUSTICE §11): 'all_conditions' — a), b) и c) вместе (список после "
                  "'provided'); 'data_or_allegation' — a) или b), вместе с c)."}},
    ]
    inputs = {
        "data_type": {"type": "enum", "values": list(DATA_TYPES), "default": "co2", "source": "text",
                      "label": {"en": "Data type (TTL for JUSTICE §11)", "ru": "Тип данных (TTL для JUSTICE §11)"}},
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of the decision", "ru": "DTI-Day решения"}},
        "impact_horizon_minutes": {"type": "int", "min": 1, "max": 10 ** 6, "default": 60, "unit": "min", "source": "user",
                                   "label": {"en": "Impact horizon Δt", "ru": "Горизонт Δt"}},
        "s0": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 0.40, "source": "user",
               "label": {"en": "S(t₀)", "ru": "S(t₀)"}},
        "s1_recorded": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 0.95, "source": "user",
                        "label": {"en": "S(t₁) as recorded", "ru": "S(t₁) записанное"}},
        "s1_true": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 0.55, "source": "user",
                    "label": {"en": "S(t₁) true (revealed by an E1 appeal)", "ru": "S(t₁) истинное (раскрывается апелляцией E1)"}},
        "uncertainty": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0.01, "source": "user",
                        "label": {"en": "Measurement uncertainty ±u", "ru": "Погрешность измерения ±u"}},
        "bound": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 0.5, "source": "missing",
                  "label": {"en": "Reference bound Bᵢ (no numeric value in AXIOMS)", "ru": "Граница Bᵢ (в AXIOMS нет числа)"}},
        "irreversible": {"type": "bool", "default": False, "source": "user",
                         "label": {"en": "Impact is physically irreversible", "ru": "Воздействие физически необратимо"}},
        "r_polarity": {"type": "enum", "values": ["true_means_reversible", "true_means_irreversible", "mixed"],
                       "default": "true_means_reversible", "source": "text",
                       "label": {"en": "Polarity of Rᵢ (H-DC-5)", "ru": "Полярность Rᵢ (H-DC-5)"}},
        "subjects": {"type": "list", "min_items": 1, "max_items": 12, "items": SUBJECT, "source": "user",
                     "default": [{"id": "plant", "kind": "legal_entity", "contribution": 3, "originator": "none"},
                                 {"id": "logistics", "kind": "legal_entity", "contribution": 1, "originator": "none"}],
                     "label": {"en": "Subjects and declared causal contributions", "ru": "Субъекты и заявленный причинный вклад"}},
        "recorded_contributions": {"type": "list", "min_items": 0, "max_items": 12,
                                   "items": {"type": "number", "min": 0, "max": 10 ** 9}, "default": [], "source": "user",
                                   "label": {"en": "Contributions as recorded ([] = correct; differs for an E3 error)",
                                             "ru": "Вклад как записан ([] = верно; отличается при ошибке E3)"}},
        "attribution_confidence": {"type": "number", "min": 0, "max": 1, "default": 0.95, "source": "user",
                                   "label": {"en": "Attribution confidence", "ru": "Уверенность привязки"}},
        "attribution_threshold": {"type": "number", "min": -1, "max": 1, "default": 0.9, "source": "missing",
                                  "label": {"en": "Minimum attribution confidence (-1: calibration missing)",
                                            "ru": "Минимальная уверенность привязки (-1: калибровки нет)"}},
        "safe_margin": {"type": "number", "min": -1, "max": 10 ** 6, "default": -1, "source": "missing",
                        "label": {"en": "Safe margin for |Iᵢ| (-1: not defined by AXIOMS)",
                                  "ru": "Безопасный запас для |Iᵢ| (-1: AXIOMS не определяют)"}},
        "mitigation_possible": {"type": "bool", "default": True, "source": "user",
                                "label": {"en": "Mitigation or repair physically possible", "ru": "Смягчение или ремонт возможны"}},
        "repeated_harm": {"type": "bool", "default": False, "source": "user",
                          "label": {"en": "Repeated harmful behaviour detected", "ru": "Повторное вредное поведение"}},
        "mitigation_insufficient": {"type": "bool", "default": False, "source": "user",
                                    "label": {"en": "Mitigation capacity insufficient", "ru": "Недостаточно возможностей смягчения"}},
        "systemic_risk": {"type": "bool", "default": False, "source": "user",
                          "label": {"en": "Behaviour presents systemic risk", "ru": "Поведение создаёт системный риск"}},
        "persistent_axiom_violation": {"type": "bool", "default": False, "source": "user",
                                       "label": {"en": "Persistent violation of non-negotiable axioms", "ru": "Устойчивое нарушение аксиом"}},
        "mitigation_and_isolation_failed": {"type": "bool", "default": False, "source": "user",
                                            "label": {"en": "Mitigation and isolation failed", "ru": "Смягчение и изоляция не помогли"}},
        "refuses_compliance": {"type": "bool", "default": False, "source": "user",
                               "label": {"en": "Refuses or cannot comply", "ru": "Отказ или неспособность исполнять"}},
        "enforcement_reversible": {"type": "bool", "default": True, "source": "hypothesis",
                                   "label": {"en": "Contested decision reversible (H-DC-3)", "ru": "Оспариваемое решение обратимо (H-DC-3)"}},
        "appellant": {"type": "str", "default": "plant", "source": "user",
                      "label": {"en": "Appellant (a bound Subject)", "ru": "Заявитель (привязанный субъект)"}},
        "appeal_after_minutes": {"type": "int", "min": -1, "max": 10 ** 7, "default": 14400, "unit": "min", "source": "user",
                                 "label": {"en": "Appeal filed after the decision (-1: none)", "ru": "Апелляция после решения (-1: нет)"}},
        "higher_layer_irreversible": {"type": "bool", "default": False, "source": "user",
                                      "label": {"en": "The decision is marked irreversible by a higher-layer rule (ERROR §3.2)",
                                                "ru": "Решение помечено необратимым правилом верхнего слоя (ERROR §3.2)"}},
        "appeal_category": {"type": "enum", "values": list(CATEGORIES), "default": "E1", "source": "user",
                            "label": {"en": "Alleged error category", "ru": "Категория ошибки"}},
        "appeal_references_decision": {"type": "bool", "default": True, "source": "user",
                                       "label": {"en": "Appeal references the decision", "ru": "Апелляция ссылается на решение"}},
        "appeal_has_evidence": {"type": "bool", "default": True, "source": "user",
                                "label": {"en": "Appeal carries PTL-indexed evidence", "ru": "Апелляция содержит данные PTL"}},
        "appeal_new_data": {"type": "bool", "default": True, "source": "user",
                            "label": {"en": "Introduces new admissible data", "ru": "Вносит новые допустимые данные"}},
        "appeal_allegation": {"type": "enum", "values": list(ALLEGATIONS), "default": "measurement_integrity", "source": "user",
                              "label": {"en": "Allegation", "ru": "Утверждение"}},
        "declared_verification_outcome": {"type": "enum", "values": ["confirmed", "unfounded"], "default": "confirmed",
                                          "source": "user", "label": {"en": "Outcome for E2/E4/E5 (not modelled)",
                                                                      "ru": "Итог для E2/E4/E5 (не моделируются)"}},
        "verification_days": {"type": "int", "min": 0, "max": 3650, "default": 5, "unit": "DTI-Day", "source": "user",
                              "label": {"en": "Verification takes", "ru": "Проверка занимает"}},
        "status_quo_suspension": {"type": "bool", "default": True, "source": "user",
                                  "label": {"en": "Use the status quo suspension (ERROR §7, optional)",
                                            "ru": "Применить приостановку статус-кво (ERROR §7, по усмотрению)"}},
        "residual_dispute": {"type": "bool", "default": False, "source": "user",
                             "label": {"en": "Appeal remains unresolved after correction (R4)", "ru": "Спор не разрешён после исправления (R4)"}},
        "periodic_reevaluation_minutes": {"type": "int", "min": 1, "max": 10 ** 7, "default": 1440, "unit": "min",
                                          "source": "user", "label": {"en": "Scheduled re-evaluation every",
                                                                      "ru": "Плановая переоценка каждые"}},
        "dispute_exception_reading": {"type": "enum", "values": ["all_conditions", "data_or_allegation"],
                                      "default": "all_conditions", "source": "alternative",
                                      "label": {"en": "Dispute exception reading (H-DC-6)", "ru": "Чтение исключения для споров (H-DC-6)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [s["id"] for s in r["subjects"]]
        if len(set(ids)) != len(ids):
            p.append("input.subjects: duplicate id")
        for s in r["subjects"]:
            if s["kind"] in PROXY_KINDS and s["originator"] not in ids:
                p.append(f"input.subjects: proxy {s['id']!r} needs an originator among the Subjects")
            if s["kind"] in PROXY_KINDS and s["originator"] in ids and \
                    next(x for x in r["subjects"] if x["id"] == s["originator"])["kind"] in PROXY_KINDS:
                p.append(f"input.subjects: originator of {s['id']!r} must not be a proxy")
        if sum(s["contribution"] for s in r["subjects"]) <= 0:
            p.append("input.subjects: at least one positive contribution")
        if r["recorded_contributions"] and len(r["recorded_contributions"]) != len(r["subjects"]):
            p.append("input.recorded_contributions: one value per Subject, or []")
        if r["bound"] == 0:
            p.append("input.bound: must not be 0 (Iᵢ divides by Bᵢ)")
        if r["appellant"] not in ids:
            p.append("input.appellant: must be one of the Subjects")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, store, out = run_chain(r)
        checks = run_checks(r, log, store, out)
        msgs = log.messages()
        imps = [m.value for m in msgs if m.source == "IMPACT"]
        decs = [m for m in msgs if m.source == "JUSTICE" and m.kind == "decision"]
        outputs = {
            "impact": imps,
            "attribution": [m.value for m in msgs if m.source == "IDENTITY"],
            "decisions": [{"event_id": m.event_id, **m.value} for m in decs],
            "error_states": [m.value for m in msgs if m.source == "ERROR" and "state" in m.value],
            "final_state": out["state"], "bond": out["bond"], "measures_in_force": out["active_final"],
            "event_log": {"time_unit": log.time_unit, "tie_rule": log.tie_rule, "messages": len(log),
                          "digest": log.digest()},
            "messages": [m.as_dict() for m in msgs],
        }
        return ModuleResult(outputs=outputs, checks=checks, explain=self.explain(r, imps, decs, out))

    def explain(self, r, imps, decs, out) -> List[Dict[str, str]]:
        e: List[Dict[str, str]] = []
        if imps:
            i = imps[0]
            e.append({"en": f"Impact Iᵢ = ({r['s1_recorded']:g} − {r['s0']:g}) / {r['bound']:g} = {i['I']:.6g}; "
                            f"boundary crossing: {i['boundary_crossing']}; Rᵢ = {i['R']} ({r['r_polarity']}).",
                      "ru": f"Воздействие Iᵢ = ({r['s1_recorded']:g} − {r['s0']:g}) / {r['bound']:g} = {i['I']:.6g}; "
                            f"пересечение границы: {i['boundary_crossing']}; Rᵢ = {i['R']} ({r['r_polarity']})."})
            if i["level_reached"] and not i["boundary_crossing"]:
                e.append({"en": "S(t₁) has reached the level Bᵢ, yet |Iᵢ| < 1: the §5 formula treats Bᵢ as a scale, "
                                "not as a level (finding F-005).",
                          "ru": "S(t₁) достигло уровня Bᵢ, но |Iᵢ| < 1: формула §5 трактует Bᵢ как масштаб, а не "
                                "уровень (находка F-005)."})
            if (r["s0"], r["s1_recorded"], r["bound"]) == (426.91, 427.0, 450):
                e.append({"en": "This is the input of the non-normative example IMPACT §13, which states Iᵢ ≈ 0.004; "
                                "the §5 formula gives 0.0002 (0.004 ≈ change / (Bᵢ − S(t₁)); finding F-005).",
                          "ru": "Это вход ненормативного примера IMPACT §13, где указано Iᵢ ≈ 0.004; формула §5 даёт "
                                "0.0002 (0.004 ≈ изменение / (Bᵢ − S(t₁)); находка F-005)."})
        for m in decs:
            on = [d for d, v in m.value["domains"].items() if v]
            unk = [d for d, v in m.value["domains"].items() if v is None]
            e.append({"en": f"Justice ({m.value['label']}): domains {on or 'none'}"
                            + (f"; undecidable: {unk}" if unk else "") + f"; shares {m.value['shares']}.",
                      "ru": f"Правосудие ({m.value['label']}): домены {on or 'нет'}"
                            + (f"; не решаемо: {unk}" if unk else "") + f"; доли {m.value['shares']}."})
        if r["r_polarity"] == "mixed" and decs:
            e.append({"en": "Mixed polarity: IMPACT emits Rᵢ by the plain reading of its name (True = irreversible), "
                            "JUSTICE reads it by §6/§8 (True = reversible), so restitution and isolation swap "
                            "(finding F-006: IMPACT does not fix the polarity).",
                      "ru": "Смешанная полярность: IMPACT выдаёт Rᵢ по бытовому прочтению названия (True = необратимо), "
                            "JUSTICE читает по §6/§8 (True = обратимо) — возмещение и изоляция меняются местами "
                            "(находка F-006: IMPACT не фиксирует полярность)."})
        e.append({"en": f"ERROR: final state {out['state']}; bond {out['bond'] or '—'}; measures in force: "
                        f"{out['active_final'] or 'none'}.",
                  "ru": f"ERROR: итоговое состояние {out['state']}; залог {out['bond'] or '—'}; действующие меры: "
                        f"{out['active_final'] or 'нет'}."})
        return e

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        decs = outputs["decisions"]
        return {"I_recorded": outputs["impact"][0]["I"] if outputs["impact"] else None,
                "domains_original": ",".join(d for d, v in decs[0]["domains"].items() if v) if decs else "—",
                "domains_final": ",".join(d for d, v in decs[-1]["domains"].items() if v) if decs else "—",
                "final_state": outputs["final_state"], "measures_in_force": ",".join(outputs["measures_in_force"] or []) or "—"}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        base: Dict[str, Any] = {"repeated_harm": True}
        proxy = [{"id": "operator", "kind": "human", "contribution": 0, "originator": "none"},
                 {"id": "router", "kind": "smart_contract", "contribution": 2, "originator": "operator"},
                 {"id": "plant", "kind": "legal_entity", "contribution": 2, "originator": "none"}]
        return {
            "measurement_error_corrected": dict(base),
            "same_with_faulty_chain": {**base, "faults": ["retaliate", "keep_bond", "mutate_original", "suspension_over_7_days"],
                                       "verification_days": 10},
            "late_e3_appeal": {**base, "appeal_category": "E3", "recorded_contributions": [4, 0],
                               "appeal_after_minutes": 40 * DAY},
            "late_e1_appeal": {**base, "appeal_after_minutes": 40 * DAY},
            "unfounded_appeal": {**base, "s1_true": 0.95},
            "no_attribution": {**base, "attribution_confidence": 0.6, "s1_recorded": 1.0, "s0": 0.0},
            "calibration_missing": {**base, "attribution_threshold": -1},
            "proxy_attribution": {**base, "subjects": proxy, "appellant": "plant", "appeal_after_minutes": -1},
            "harsher_recomputation": {**base, "s1_recorded": 0.55, "s1_true": 0.95},
            "polarity_true_irreversible": {**base, "r_polarity": "true_means_irreversible"},
            "polarity_mixed": {**base, "r_polarity": "mixed"},
            "impact_example_s13": {"s0": 426.91, "s1_recorded": 427.0, "s1_true": 427.0, "bound": 450,
                                   "uncertainty": 0.01, "appeal_after_minutes": -1},
            "dispute_within_ttl_all": {**base, "appeal_after_minutes": 1440 + 30, "appeal_allegation": "none",
                                       "verification_days": 0},
            "dispute_within_ttl_either": {**base, "appeal_after_minutes": 1440 + 30, "appeal_allegation": "none",
                                          "verification_days": 0,
                                          "dispute_exception_reading": "data_or_allegation"},
            "exclusion": {**base, "persistent_axiom_violation": True, "appeal_after_minutes": -1},
            "higher_layer_irreversible": {**base, "higher_layer_irreversible": True},
            "faulty_justice_record": {**base, "persistent_axiom_violation": True, "appeal_after_minutes": -1,
                                      "faults": ["partial_binding", "exclusion_erases_history", "final_output"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "proxy_without_originator": {"subjects": [{"id": "bot", "kind": "smart_contract", "contribution": 1,
                                                       "originator": "nobody"}], "appellant": "bot"},
            "zero_bound": {"bound": 0},
            "unknown_appellant": {"appellant": "stranger"},
            "contributions_mismatch": {"recorded_contributions": [1, 2, 3]},
        }
