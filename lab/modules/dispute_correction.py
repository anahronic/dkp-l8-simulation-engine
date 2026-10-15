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
    "moralize_error": "a confirmed error is recorded as operator misconduct",
    "coercive_verification": "verification in R1 compels the appellant to disclose private records",
    "error_rewrites_ptl": "ERROR writes a corrected measurement itself instead of a new PTL observation",
    "infer_intent": "ERROR records an inference about the appellant's intent",
    "compensate_instead": "a reversible measure no longer supported is kept and compensated instead of lifted",
    "suppress_appeal": "a valid appeal is ignored (no error case opened)",
    "discretionary_override": "a reviewer lifts a measure by an override outside the recomputation",
    "moral_output": "the Justice output vector carries a moral assessment of the Subject",
    "coupled_domains": "restriction is suppressed whenever restitution applies",
    "collective_absorbs": "a collective's share absorbs its members' individual shares",
    "exempt_by_status": "Subjects with an official, jurisdictional, ideological or cultural status are left out of the outcome",
    "justice_policy": "the Justice output carries a policy directive",
    "opaque_adjustment": "a review panel adds a restriction the inputs do not trigger",
    "misclassify_as_e1": "an error of another category is classified E1 and so escapes the 30-day window",
    "seal_case": "the closed error case is sealed and no longer open to review",
    "exclusion_abandons": "exclusion also withdraws life support from the excluded Subject",
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "uncounted_case": "a closed error case is left out of the reliability count",
    "hide_statistics": "the published error statistics omit the case",
    "admit_without_standing": "an appeal from a Subject the decision does not name is admitted",
    "stale_dti_index": "the R2 and R3 records carry the DTI-Day of the appeal instead of their own",
    "admit_without_bond": "an appeal without a bond is admitted",
    "cascade_correction": "the correction also lifts a measure outside the declared case scope",
    "ignore_trigger": "a declared re-evaluation trigger is not followed by a re-evaluation",
    "act_on_stale_data": "a re-evaluation on incomplete, stale or withheld data lifts the prior outcome",
    "justice_feeds_identity": "a Justice decision is fed back into an IDENTITY record",
    "history_dependent_output": "a recomputed decision is made harsher because an earlier decision exists",
    "physical_confinement": "isolation is physical confinement although functional separation is declared feasible",
}
DEVIATIONS = {"E1": "PTL sensor, ingestion or oracle misreporting", "E2": "protocol logic executed incorrectly or out of order",
              "E3": "incorrect identity binding or responsibility assignment",
              "E4": "incorrect impact magnitude, scope or channel mapping",
              "E5": "violation of timing, escalation rules or isolation constraints"}                # ERROR §4
EXCLUSION_EFFECTS = ["removal from system participation", "loss of system-provided privileges",
                     "persistence of historical attribution"]                                      # JUSTICE §9
SURVIVAL = ("life support", "food", "water", "shelter", "medical care", "heating")                  # JUSTICE §9, A1
TRIGGER_KINDS = ("impact_change", "mitigation", "uncertainty_reduced", "boundary_shift")           # JUSTICE §11
TRIGGER_DATA = ("complete", "incomplete", "stale", "withheld")


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


OUTPUT_FIELDS = ("label", "domains", "shares", "amounts", "flag", "exclusion_effects")      # what the vector C carries
MORAL_FIELDS = ("assessment", "blame", "intent", "motive", "adjusted_by", "discretion", "subjective_weight")


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
    status = {x["id"]: x.get("status", "none") for x in r["subjects"]}          # JUSTICE §12 input

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
        shares = dict(weights)
        if "coupled_domains" in faults and doms["restitution"]:
            doms = dict(doms, restriction=False)
        if "opaque_adjustment" in faults and not doms["restriction"]:
            doms = dict(doms, restriction=True)
        if "history_dependent_output" in faults and label != "original":
            doms = dict(doms, isolation=True)
        coll = [x["id"] for x in r["subjects"] if x["kind"] == "collective" and x["id"] in shares]
        if "collective_absorbs" in faults and coll:
            shares = {coll[0]: 1.0}
        if "exempt_by_status" in faults:
            keep = {k: w for k, w in shares.items() if status.get(k, "none") == "none"}
            total = sum(keep.values())
            shares = {k: round(w / total, 12) for k, w in keep.items()} if total else {}
        got = received_flag(imp, r)
        dec = {"label": label, "domains": doms, "shares": shares,
               "amounts": "not computed: no amount function in JUSTICE §6-§9",
               "flag": {"emitted_by_impact": imp["R"], "received": got,
                        "read_as": "reversible" if justice_reversible(got, r["r_polarity"]) else "irreversible",
                        "contract": "JUSTICE §6/§8: Rᵢ = True reversible, Rᵢ = False irreversible; no conversion (IMPACT §11)"}}
        if "moral_output" in faults:
            dec["assessment"] = "reckless and irresponsible conduct"
        if "justice_policy" in faults:
            dec["policy"] = "prioritize economic recovery of the region"
        if "opaque_adjustment" in faults:
            dec["adjusted_by"] = "review panel"
        if doms["exclusion"]:
            dec["exclusion_effects"] = EXCLUSION_EFFECTS[:2] + (["historical attribution erased"] if "exclusion_erases_history" in faults
                                                                else EXCLUSION_EFFECTS[2:]) + \
                (["withdrawal of life support"] if "exclusion_abandons" in faults else [])
        dmd = md("VALID", "SUFFICIENT_DATA", "CONSISTENT", scope, reval=True)
        if "final_output" in faults:
            dmd["dispute_allowed"] = False
        m_dec = put("decision", "JUSTICE", at, dec, (m_imp.event_id, m_att.event_id), dmd, decided=at, record=True)
        if "justice_feeds_identity" in faults:
            put("notice", "IDENTITY", at, {"subject_record": sorted(shares), "adjusted_by": "Justice decision"}, (m_dec.event_id,))
        return m_imp, m_att, m_dec

    def apply(at, d, subjects, prov):
        v = {"apply": d, "subjects": subjects}
        if d == "isolation":                                  # JUSTICE §8: functional separation first
            v["form"] = "functional separation" if r["functional_separation_feasible"] and "physical_confinement" not in faults \
                else "physical confinement"
        return put("action", "ENFORCEMENT", at, v, prov, decided=at)

    s0 = put("observation", "PTL", 0, r["s0"], measured=0, unit="model unit", unc=r["uncertainty"])
    s1 = put("observation", "PTL", H, r["s1_recorded"], measured=H, unit="model unit", unc=r["uncertainty"])
    imp1, att1, dec1 = evaluate_chain(t_dec, s1, s0, recorded_contrib, "original")
    put("notice", "ERROR", t_dec, {"state": "R0", **dti(r, t_dec)}, (s1.event_id,))
    active: Dict[str, str] = {}                        # enforcing domain -> action event id
    if dec1 is not None:
        for d in ENFORCING:
            if dec1.value["domains"][d]:
                a = apply(t_dec, d, sorted(dec1.value["shares"]), (dec1.event_id,))
                active[d] = a.event_id
        if dec1.value["domains"]["restitution"]:
            put("notice", "JUSTICE", t_dec, {"restitution_obligation": dec1.value["shares"],
                                             "amount": "not computed"}, (dec1.event_id,))
        # JUSTICE §11: declared triggers lead to a re-evaluation, not more often than the minimum TTL; incomplete,
        # stale or withheld data leave the prior outcome in force
        for tg in r["reevaluation_triggers"]:
            tt = t_dec + tg["after_minutes"]
            trig = put("notice", "TRIGGER", tt, {"trigger": tg["kind"], "data": tg["data"]})
            if "ignore_trigger" in faults:
                continue
            te = max(tt, t_dec + ttl)
            kept = tg["data"] != "complete" and "act_on_stale_data" not in faults
            rv = put("evaluation", "JUSTICE", te, {"reevaluation_of": dec1.event_id, "trigger": trig.event_id, "data": tg["data"],
                                                   "prior_outcome_in_force": kept or tg["data"] == "complete",
                                                   "domains": justice_domains(imp1.value, r)},
                     (trig.event_id, dec1.event_id))
            if tg["data"] != "complete" and not kept and active:
                put("action", "ENFORCEMENT", te, {"lift": sorted(active)[0], "relief": "re-evaluation"}, (rv.event_id,), decided=te)

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
                                             "allegation": r["appeal_allegation"],
                                             "bond": "posted" if r["appeal_bond_posted"] else "none", **dti(r, ta)},
                 (dec1.event_id,))
    out["appeal"] = appeal.event_id
    classified = "E1" if "misclassify_as_e1" in faults else r["appeal_category"]
    put("notice", "ERROR", ta, {"classified": classified, "deviation": DEVIATIONS[r["appeal_category"]], **dti(r, ta)},
        (appeal.event_id,))

    def close(at, state):
        put("notice", "ERROR", at, {"case_closed": state, "record": "kept", "reviewable": "seal_case" not in faults},
            (appeal.event_id,))
        cases = [] if "uncounted_case" in faults else [appeal.event_id]
        put("notice", "ERROR-METRICS", at, {"reliability_cases": cases, "count": len(cases)}, (appeal.event_id,))
        shown = [] if "hide_statistics" in faults else [appeal.event_id]
        put("notice", "ERROR-STATS", at, {"published_cases": shown, "by_state": {state: len(shown)} if shown else {}},
            (appeal.event_id,))

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
        close(ta, "NOT_APPEALABLE")
        out.update(state="NOT_APPEALABLE", active_final=sorted(active), final_decision=dec1.event_id)
        return log, store, out
    formal = r["appeal_references_decision"] and r["appeal_has_evidence"]
    standing = r["appellant"] in dec1.value["shares"] or "admit_without_standing" in faults      # ERROR §3.3
    bonded = r["appeal_bond_posted"] or "admit_without_bond" in faults                            # ERROR §6
    late = days > APPEAL_WINDOW_DAYS
    if classified == "E1":
        late = late and "e1_time_barred" in faults
    else:
        late = late and "late_appeal_accepted" not in faults
    if formal and not late and "suppress_appeal" in faults:
        out.update(state="IGNORED", active_final=sorted(active), final_decision=dec1.event_id)
        return log, store, out
    if not formal or late or not standing or not bonded:
        put("notice", "ERROR", ta, {"state": "REJECTED_PROCEDURAL", "late": late, "formal": formal, "standing": standing,
                                    "prejudice": "none", "bond": "returned (procedural rejection)" if r["appeal_bond_posted"]
                                    else "none posted", **dti(r, ta)},
            (appeal.event_id,))
        close(ta, "REJECTED_PROCEDURAL")
        out.update(state="REJECTED_PROCEDURAL", active_final=sorted(active), final_decision=dec1.event_id)
        return log, store, out
    r1 = put("notice", "ERROR", ta, {"state": "R1", **dti(r, ta)}, (appeal.event_id,))
    put("notice", "ERROR", ta, {"case_scope": {"decision": dec1.event_id, "impact": imp1.event_id,
                                               "subjects": sorted(x["id"] for x in r["subjects"])}}, (appeal.event_id,))
    stamp = ta if "stale_dti_index" in faults else None
    if "coercive_verification" in faults:
        put("action", "ENFORCEMENT", ta, {"compel": "disclosure of private records", "subjects": [r["appellant"]],
                                          "reason": "verification"}, (r1.event_id,), decided=ta)
    if "infer_intent" in faults:
        put("notice", "ERROR", ta, {"inference": "the appellant intends to delay enforcement"}, (appeal.event_id,))
    if "error_rewrites_ptl" in faults:
        put("observation", "ERROR", ta, {"corrected_measurement": r["s1_true"]}, (appeal.event_id,), measured=H,
            unit="model unit", unc=r["uncertainty"])
    if "discretionary_override" in faults and active:
        ov = put("notice", "ERROR", ta, {"override": "reviewer lifts the measure pending review", "by": "reviewer"},
                 (appeal.event_id,))
        put("action", "ENFORCEMENT", ta, {"lift": sorted(active)[0]}, (ov.event_id,), decided=ta)

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
        put("notice", "ERROR", tv, {"state": "REJECTED_UNFOUNDED", "bond": "audit costs", **dti(r, stamp or tv)},
            (appeal.event_id,))
        close(tv, "REJECTED_UNFOUNDED")
        out.update(state="REJECTED_UNFOUNDED", bond="audit costs", active_final=sorted(active),
                   final_decision=dec1.event_id)
        return log, store, out

    evidence = new_obs.event_id if new_obs else appeal.event_id
    put("notice", "ERROR", tv, {"state": "R2", "validated_by": ["PTL", "protocol audit"], **dti(r, stamp or tv),
                                **({"cause": "operator misconduct"} if "moralize_error" in faults else {})},
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
            if "compensate_instead" in faults:
                put("notice", "ERROR", tv, {"compensation_instead_of_reversal": d, "amount": "not computed"},
                    (dec2_id or appeal.event_id,))
                new_domains = dict(new_domains, **{d: True})
                continue
            put("action", "ENFORCEMENT", tv, {"lift": d}, (dec2_id or appeal.event_id,), decided=tv)
            put("notice", "ERROR", tv, {"irreversible_effect": f"{d} in force from minute {t_dec} to {tv}",
                                        "compensation": "owed where possible; amount function not defined"},
                (active[d],))
    for d in ENFORCING:
        if new_domains.get(d) and d not in active:
            apply(tv, d, sorted(dec2_value["shares"]), (dec2_id,))
    if "cascade_correction" in faults:
        put("action", "ENFORCEMENT", tv, {"lift": "restriction", "subjects": ["subject of a linked case"],
                                          "record": "decision outside this case"}, (dec2_id or appeal.event_id,), decided=tv)
    put("notice", "ERROR", tv, {"state": "R3", **dti(r, stamp or tv)}, (dec2_id or appeal.event_id,))
    out["state"] = "R3"
    if r["residual_dispute"]:
        put("notice", "ERROR", tv, {"state": "R4", **dti(r, stamp or tv)}, (appeal.event_id,))
        out["state"] = "R4"
    close(tv, out["state"])
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
        return res + error_conduct(r, log, out) + justice_conduct(r, log)
    days = (appeal.arrived_at - out["t_dec"]) / DAY
    formal = r["appeal_references_decision"] and r["appeal_has_evidence"]
    admissible = r["appellant"] in get(out["decision_1"]).value["shares"] and r["appeal_bond_posted"]     # ERROR §3.3, §6
    rejected = "REJECTED_PROCEDURAL" in states
    res.append(verdict("ERROR-7-01", "appeal_fields", (not formal) == rejected or (formal and (days > APPEAL_WINDOW_DAYS or not admissible)),
                       "appeals are validated exactly when they reference the decision, carry evidence and a category",
                       "formal requirements not applied"))
    if r["appeal_category"] != "E1":
        if days > APPEAL_WINDOW_DAYS:
            res.append(verdict("ERROR-7-02", "appeal_window", rejected,
                               f"appeal after {days:g} DTI-Days rejected (window 30)",
                               f"appeal after {days:g} DTI-Days accepted (window 30)"))
        else:
            res.append(verdict("ERROR-7-02", "appeal_window", (formal and admissible) == ("R1" in states),
                               f"appeal after {days:g} DTI-Days handled within the 30-day window",
                               "an appeal within the window was not handled"))
        res.append(na("ERROR-7-03", "e1_no_limitation", "E1 exception", "the appeal is not of category E1"))
    else:
        res.append(na("ERROR-7-02", "appeal_window", "30-day window", "E1 appeals have no limitation period"))
        if days > APPEAL_WINDOW_DAYS:
            res.append(verdict("ERROR-7-03", "e1_no_limitation", not rejected or not formal or not admissible,
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
    return res + error_conduct(r, log, out) + justice_conduct(r, log)


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


def justice_conduct(r, log: EventLog) -> List[CheckResult]:
    """JUSTICE §4, §5, §10, §12, §13, §14 (review КТ5 reading), on every Justice decision of the run."""
    msgs = log.messages()
    get = log.get
    decs = [m for m in msgs if m.source == "JUSTICE" and m.kind == "decision"]
    res: List[CheckResult] = []
    if not decs:
        for rid, chk in (("JUSTICE-4-02", "output_vector_clean"), ("JUSTICE-5-01", "domains_independent"),
                         ("JUSTICE-10-02", "individual_accountability_kept"), ("JUSTICE-12-01", "no_exemption"),
                         ("JUSTICE-13-01", "cross_layer_isolation"), ("JUSTICE-14-01", "reproducible"),
                         ("JUSTICE-1-01", "consequences_not_punishment"), ("JUSTICE-9-04", "exclusion_scope")):
            res.append(na(rid, chk, "Justice evaluation", "no Justice decision (attribution blocked or NO_ATTRIBUTION)"))
        return res
    bad = [f"{m.event_id}: {k}" for m in decs for k in m.value if k in MORAL_FIELDS]
    res.append(verdict("JUSTICE-4-02", "output_vector_clean", not bad,
                       f"{len(decs)} output vectors carry domains, shares and the received flag only: no moral language, intent "
                       "interpretation, discretionary adjustment or subjective weighting", f"{len(bad)} such fields in C",
                       {"violations": bad[:10]}))
    clean = dict(r, faults=[])
    bad = []
    for m in decs:
        imp = get(m.provenance[0]).value
        want = justice_domains(imp, dict(clean, faults=[f for f in r["faults"] if f == "override_flag"]))
        bad += [f"{m.event_id}: {d} {m.value['domains'][d]} != {want[d]}" for d in DOMAINS if m.value["domains"][d] != want[d]]
    res.append(verdict("JUSTICE-5-01", "domains_independent", not bad,
                       "each of the four domains is decided by its own §6-§9 conditions; no domain's result depends on another's",
                       f"{len(bad)} domains decided otherwise than by their own conditions", {"violations": bad[:10]}))
    contrib = {}
    for x in r["subjects"]:
        if x["kind"] not in PROXY_KINDS:
            contrib[x["id"]] = contrib.get(x["id"], 0) + x["contribution"]
    colls = [x["id"] for x in r["subjects"] if x["kind"] == "collective"]
    if colls:
        bad = [f"{m.event_id}: {k} (contribution {c}) has no share" for m in decs for k, c in contrib.items()
               if c > 0 and k not in colls and m.value["shares"].get(k, 0) <= 0]
        res.append(verdict("JUSTICE-10-02", "individual_accountability_kept", not bad,
                           f"with collective {colls} responsible, every individual Subject with a contribution keeps its own share",
                           f"{len(bad)} individual shares nullified by collective responsibility", {"violations": bad[:10]}))
    else:
        res.append(na("JUSTICE-10-02", "individual_accountability_kept", "collective responsibility", "no collective Subject"))
    marked = [x["id"] for x in r["subjects"] if x.get("status", "none") != "none"]
    if marked:
        plain = dict(r, subjects=[dict(x, status="none") for x in r["subjects"]])
        base, _, _ = run_chain(plain)
        other = [m.value for m in base.messages() if m.source == "JUSTICE" and m.kind == "decision"]
        mine = [m.value for m in decs]
        bad = [f"decision {i}: shares or domains change with the declared status" for i, (a, b) in enumerate(zip(mine, other))
               if a["shares"] != b["shares"] or a["domains"] != b["domains"]] + ([] if len(mine) == len(other) else ["decision count"])
        res.append(verdict("JUSTICE-12-01", "no_exemption", not bad,
                           f"Subjects with a declared status ({', '.join(marked)}) receive exactly the outcome they would without it",
                           f"{len(bad)} outcomes changed by status, authority, jurisdiction, ideology or culture", {"violations": bad[:10]}))
    else:
        res.append(na("JUSTICE-12-01", "no_exemption", "exemption by status", "no Subject has a declared status"))
    bad = []
    for m in decs:
        att = get(m.provenance[1]).value
        if m.value["shares"] != att["weights"]:
            bad.append(f"{m.event_id}: shares differ from the IDENTITY weights")
        if m.value.get("flag") and m.value["flag"]["received"] != get(m.provenance[0]).value["R"]:
            bad.append(f"{m.event_id}: IMPACT flag reinterpreted")
        bad += [f"{m.event_id}: {k}" for k in m.value if k not in OUTPUT_FIELDS]
    res.append(verdict("JUSTICE-13-01", "cross_layer_isolation", not bad,
                       "impact metrics and identity attribution used as given; no policy, governance or moral field in the output",
                       f"{len(bad)} cross-layer breaches", {"violations": bad[:10]}))
    bad = []
    for m in decs:
        want = justice_domains(get(m.provenance[0]).value, clean)
        if m.value["domains"] != want:
            bad.append(f"{m.event_id}: domains not reproducible from the IMPACT input")
    again, _, _ = run_chain(r)
    if again.digest() != log.digest():
        bad.append("re-execution differs")
    res.append(verdict("JUSTICE-14-01", "reproducible", not bad,
                       f"{len(decs)} decisions recomputed from their IMPACT and IDENTITY inputs by the §6-§9 rules; re-execution identical",
                       f"{len(bad)} opaque, discretionary or non-reproducible results", {"violations": bad[:10]}))
    # JUSTICE §1 (returned after the reading of checkpoint 6): consequences, not punishment; binding, not discretionary
    ids = {m.event_id for m in decs}
    bad = [f"{m.event_id}: {k}" for m in decs for k in m.value if k in MORAL_FIELDS]
    bad += [f"{m.event_id}: {m.value['apply']} not computed by JUSTICE" for m in msgs if m.source == "ENFORCEMENT"
            and m.kind == "action" and "apply" in m.value and not set(m.provenance) & ids]
    bad += [f"{m.event_id}: override" for m in msgs if m.source == "ERROR" and "override" in m.value]
    res.append(verdict("JUSTICE-1-01", "consequences_not_punishment", not bad,
                       f"every measure applies a computed Justice consequence as given ({len(decs)} decisions); no moral label, "
                       "discretionary adjustment or measure from another source", f"{len(bad)} punitive or discretionary elements",
                       {"violations": bad[:10]}))
    exc = [m for m in decs if m.value["domains"].get("exclusion")]
    if exc:
        bad = [f"{m.event_id}: {e}" for m in exc for e in m.value.get("exclusion_effects", []) if e not in EXCLUSION_EFFECTS]
        bad += [f"{m.event_id}: {k}" for m in exc for k in m.value if k in MORAL_FIELDS]
        res.append(verdict("JUSTICE-9-04", "exclusion_scope", not bad,
                           "exclusion ends participation and system-provided privileges only, keeps history, and carries no "
                           "moral condemnation", f"{len(bad)} effects beyond the scope of exclusion", {"violations": bad[:10]}))
    else:
        res.append(na("JUSTICE-9-04", "exclusion_scope", "exclusion", "no exclusion decided"))
    return res


ERROR_STATES = ("R0", "R1", "R2", "R3", "R4", "NOT_APPEALABLE", "REJECTED_PROCEDURAL", "REJECTED_UNFOUNDED")
CLASS_CHECKS = (("ERROR-4-02", "category_e2"), ("ERROR-4-03", "category_e3"), ("ERROR-4-04", "category_e4"),
                ("ERROR-4-05", "category_e5"))
BLAME_KEYS = ("cause", "blame", "misconduct", "fault_of")


def error_conduct(r, log: EventLog, out) -> List[CheckResult]:
    """ERROR §0, §1, §2, §5 R1, §6, §9, §11: how the error case is conducted (review КТ5 reading)."""
    msgs = log.messages()
    get = log.get
    res: List[CheckResult] = []
    err = [m for m in msgs if m.source == "ERROR"]
    states = [m.value["state"] for m in err if "state" in m.value]
    appeal = get(out["appeal"]) if out["appeal"] else None
    acts = [m for m in msgs if m.kind == "action" and m.source == "ENFORCEMENT"]
    labelled = [f"{m.event_id}: {k}" for m in err for k in BLAME_KEYS if k in m.value]
    odd = [f"{m.event_id}: state {m.value['state']}" for m in err if "state" in m.value and m.value["state"] not in ERROR_STATES]
    res.append(verdict("ERROR-0-01", "errors_as_states", not (labelled or odd),
                       f"{len(states)} error records, each a state of the §5 model or a procedural outcome; none labels a "
                       "moral failure or misconduct", f"{len(labelled) + len(odd)} error records with blame labels or unknown states",
                       {"violations": (labelled + odd)[:10]}))
    infer = [f"{m.event_id}: {k}" for m in err for k in ("inference", "prediction", "intent") if k in m.value]
    res.append(verdict("ERROR-6-04", "no_prediction_or_intent", not infer,
                       "no prediction or intent inference in the error case", f"{len(infer)} predictions or intent inferences",
                       {"violations": infer[:10]}))
    overrides = [m.event_id for m in err if "override" in m.value]
    decisions = {m.event_id for m in msgs if m.source == "JUSTICE" and m.kind == "decision"}
    ruleless = [m.event_id for m in acts if not (set(m.provenance) & decisions) and not (appeal and appeal.event_id in m.provenance)]
    res.append(verdict("ERROR-11-04", "no_discretionary_override", not (overrides or ruleless),
                       f"all {len(acts)} enforcement changes derive from a Justice decision or the appeal procedure; no override",
                       f"{len(overrides) + len(ruleless)} overrides or measures without a rule-based source",
                       {"violations": (overrides + ruleless)[:10]}))
    if appeal is None:
        why = "no appeal in this experiment" if r["appeal_after_minutes"] < 0 else "no Justice decision to appeal"
        for rid, chk in (("ERROR-1-01", "procedural_non_punitive"), ("ERROR-2-04", "no_ptl_reinterpretation"),
                         ("ERROR-5-02", "r1_non_coercive"), ("ERROR-9-03", "reversibility_preferred"),
                         ("ERROR-11-01", "valid_appeal_not_suppressed"), ("ERROR-2-03", "no_new_coercive_measures"),
                         ("ERROR-9-02", "ptl_consistency_preserved"), ("ERROR-10-02", "case_reviewable")) + CLASS_CHECKS:
            res.append(na(rid, chk, "error case", why))
        return res
    # ERROR §4 (returned after the reading of checkpoint 6): the class follows the deviation, and the class sets the window
    cl = [m for m in err if "classified" in m.value]
    for rid, chk in CLASS_CHECKS:
        cat = "E" + chk[-1]
        if r["appeal_category"] != cat:
            res.append(na(rid, chk, f"{cat} errors", f"the appeal concerns a {r['appeal_category']} deviation"))
        else:
            got = cl[0].value["classified"] if cl else None
            res.append(verdict(rid, chk, got == cat,
                               f"the deviation ({DEVIATIONS[cat]}) is classified {cat} and handled under its limitation rule",
                               f"the deviation ({DEVIATIONS[cat]}) is classified {got}"))
    coercive = [a.event_id for a in acts if ({appeal.event_id} | {m.event_id for m in err}) & set(a.provenance)
                and ("apply" in a.value or "compel" in a.value)]
    res.append(verdict("ERROR-2-03", "no_new_coercive_measures", not coercive,
                       "the error case introduced no coercive measure: every measure in force comes from a Justice decision",
                       f"{len(coercive)} coercive measures introduced by the error case", {"violations": coercive[:10]}))
    closed = [m for m in err if "case_closed" in m.value]
    opened = [m for m in err if m.arrived_at >= appeal.arrived_at and "state" in m.value]
    if opened:
        bad = [m.event_id for m in closed if not m.value["reviewable"]] + ([] if closed else ["no closing record"])
        res.append(verdict("ERROR-10-02", "case_reviewable", not bad,
                           f"the error case closed in {closed[0].value['case_closed'] if closed else '-'} with its record kept and "
                           "open to post-factum review", "the closed case is not open to review", {"violations": bad[:10]}))
    else:
        res.append(na("ERROR-10-02", "case_reviewable", "closed error case", "no error case was opened"))
    punitive = [a.event_id for a in acts if ({appeal.event_id} | {m.event_id for m in err}) & set(a.provenance)
                and ("apply" in a.value or "compel" in a.value)]
    model = [x for x in states if x in ("R0", "R1", "R2", "R3", "R4")]
    disorder = [] if model == sorted(model) else [" -> ".join(model)]
    res.append(verdict("ERROR-1-01", "procedural_non_punitive", not (punitive or disorder),
                       "the error case moved through the §5 states in order and added no measure of its own",
                       f"{len(punitive) + len(disorder)} punitive measures or out-of-order states",
                       {"violations": (punitive + disorder)[:10]}))
    rewritten = [m.event_id for m in msgs if m.kind == "observation" and m.source != "PTL"]
    res.append(verdict("ERROR-2-04", "no_ptl_reinterpretation", not rewritten,
                       "every measurement in the case is a PTL observation; ERROR wrote none", f"{len(rewritten)} measurements written by ERROR",
                       {"violations": rewritten[:10]}))
    if any(m.value.get("state") == "R1" for m in err):
        res.append(verdict("ERROR-9-02", "ptl_consistency_preserved", not rewritten,
                           "the correction left the PTL record as PTL wrote it: corrected values arrive as new PTL observations",
                           f"{len(rewritten)} measurements written outside PTL", {"violations": rewritten[:10]}))
    else:
        res.append(na("ERROR-9-02", "ptl_consistency_preserved", "correction", "no verification was opened"))
    r1 = [m for m in err if m.value.get("state") == "R1"]
    if r1:
        nxt = [m.arrived_at for m in err if m.value.get("state") in ("R2", "REJECTED_UNFOUNDED")]
        end = min(nxt) if nxt else 10 ** 12
        coerced = [a.event_id for a in acts if r1[0].arrived_at <= a.arrived_at < end and ("compel" in a.value or
                   ("apply" in a.value and appeal.event_id in a.provenance))]
        res.append(verdict("ERROR-5-02", "r1_non_coercive", not coerced, "verification in R1 compelled and restricted no one",
                           f"{len(coerced)} coercive acts during verification", {"violations": coerced[:10]}))
    else:
        res.append(na("ERROR-5-02", "r1_non_coercive", "R1 verification", "the appeal did not open an error case"))
    if "R3" in states and out["final_decision"] and out["final_decision"] != out["decision_1"]:
        d1, d2 = get(out["decision_1"]), get(out["final_decision"])
        should = {d for d in ENFORCING if d1.value["domains"][d] and not d2.value["domains"][d]}
        lifted = {a.value["lift"] for a in acts if "lift" in a.value}
        paid = [m.value["compensation_instead_of_reversal"] for m in err if "compensation_instead_of_reversal" in m.value]
        bad = sorted(should - lifted) + paid
        res.append(verdict("ERROR-9-03", "reversibility_preferred", not bad,
                           f"measures no longer supported were reversed ({sorted(should) or 'none'}); compensation only for elapsed effects",
                           f"{len(bad)} measures compensated instead of reversed", {"violations": bad[:10]})
                   if should else na("ERROR-9-03", "reversibility_preferred", "reversal", "no measure is dropped by the correction"))
    else:
        res.append(na("ERROR-9-03", "reversibility_preferred", "correction", "no correction applied"))
    d1 = get(out["decision_1"])
    appealable = any(bool(x) for x in d1.value["domains"].values()) and not r["higher_layer_irreversible"]
    formal = r["appeal_references_decision"] and r["appeal_has_evidence"] and r["appeal_bond_posted"] \
        and r["appellant"] in d1.value["shares"]
    timely = r["appeal_category"] == "E1" or r["appeal_after_minutes"] / DAY <= APPEAL_WINDOW_DAYS
    if appealable and formal and timely:
        res.append(verdict("ERROR-11-01", "valid_appeal_not_suppressed", "R1" in states,
                           "the valid appeal (appealable, formal, in time) opened an error case (R1)",
                           "a valid appeal was suppressed: no R1"))
    else:
        res.append(na("ERROR-11-01", "valid_appeal_not_suppressed", "valid appeals",
                      "the appeal is not valid under §3.2, §3.3, §6 and §7 (not appealable, no standing, no bond, not formal or late)"))
    return res


def core_checks(r, log: EventLog, out) -> List[CheckResult]:
    """Clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)."""
    msgs = log.messages()
    get = log.get
    res: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return verdict(rid, chk, not bad, ok, no.format(n=len(bad)), {"violations": bad[:10]} if bad else None)
    err = [m for m in msgs if m.source == "ERROR"]
    states = [m.value["state"] for m in err if "state" in m.value]
    decs = [m for m in msgs if m.source == "JUSTICE" and m.kind == "decision"]
    acts = [m for m in msgs if m.source == "ENFORCEMENT" and m.kind == "action"]
    appeal = get(out["appeal"]) if out["appeal"] else None
    # ERROR §10, §11: every closed case counted and published
    closed = [m for m in err if "case_closed" in m.value]
    if closed:
        counted = {c for m in msgs if m.source == "ERROR-METRICS" for c in m.value["reliability_cases"]}
        bad = [m.provenance[0] for m in closed if m.provenance[0] not in counted]
        bad += [m.event_id for m in msgs if m.source == "ERROR-METRICS" and m.value["count"] != len(m.value["reliability_cases"])]
        res.append(v("ERROR-10-03", "case_in_reliability_count", bad,
                     f"{len(closed)} closed error case(s), each counted in the declared reliability count",
                     "{n} closed cases left out of the reliability count"))
        shown = {c for m in msgs if m.source == "ERROR-STATS" for c in m.value["published_cases"]}
        bad = [m.provenance[0] for m in closed if m.provenance[0] not in shown]
        bad += [m.event_id for m in msgs if m.source == "ERROR-STATS" and sum(m.value["by_state"].values()) != len(m.value["published_cases"])]
        res.append(v("ERROR-11-03", "statistics_omit_no_case", bad,
                     f"{len(closed)} closed error case(s), none omitted from the published statistics",
                     "{n} cases omitted from the published statistics"))
    else:
        for rid, chk in (("ERROR-10-03", "case_in_reliability_count"), ("ERROR-11-03", "statistics_omit_no_case")):
            res.append(na(rid, chk, "closed error cases", "no error case was closed"))
    # ERROR §3.3 and §6: admission
    if appeal is not None and decs:
        named = set(get(out["decision_1"]).value["shares"])
        admitted = "R1" in states
        res.append(verdict("ERROR-3.3-01", "appellant_named_by_decision", not admitted or appeal.value["appellant"] in named,
                           f"the claim of {appeal.value['appellant']} was " + ("admitted: the decision names the appellant" if admitted
                                                                               else "not admitted") ,
                           f"the claim of {appeal.value['appellant']} was admitted although the decision does not name it"))
        res.append(verdict("ERROR-6-01", "appeal_with_bond", not admitted or appeal.value["bond"] == "posted",
                           "the appeal was " + ("admitted with its bond posted" if admitted else "not admitted"),
                           "an appeal without a bond was admitted"))
    else:
        for rid, chk in (("ERROR-3.3-01", "appellant_named_by_decision"), ("ERROR-6-01", "appeal_with_bond")):
            res.append(na(rid, chk, "appeals", "no appeal filed" if r["appeal_after_minutes"] < 0 else "no Justice decision to appeal"))
    # ERROR §5: every state indexed by its own DTI-Day
    st = [m for m in err if "state" in m.value]
    bad = [f"{m.event_id}: {m.value['state']} day {m.value.get('dti_day')}" for m in st
           if m.value.get("dti_day") != dti(r, m.arrived_at)["dti_day"] or m.value.get("dy") != dti(r, m.arrived_at)["dy"]]
    res.append(v("ERROR-5-06", "state_dti_indexed", bad, f"{len(st)} state records, each indexed by the DTI-Day on which it arrived",
                 "{n} state records without their own DTI-Day index") if st else
               na("ERROR-5-06", "state_dti_indexed", "error states", "no error state recorded"))
    # ERROR §9: corrections stay within the declared case scope
    scope = next((m.value["case_scope"] for m in err if "case_scope" in m.value), None)
    if scope and "R2" in states:
        t2 = next(m.arrived_at for m in err if m.value.get("state") == "R2")
        mine = set(scope["subjects"])
        bad = [a.event_id for a in acts if a.arrived_at >= t2 and (set(a.value.get("subjects", [])) - mine or "record" in a.value)]
        res.append(v("ERROR-9-04", "correction_within_scope", bad,
                     f"the correction changed only measures of the case ({scope['decision']}, Subjects {sorted(mine)})",
                     "{n} corrective changes outside the declared case scope"))
    else:
        res.append(na("ERROR-9-04", "correction_within_scope", "correction", "no confirmed error was corrected"))
    # JUSTICE §11: triggers and data quality
    trig = [m for m in msgs if m.source == "TRIGGER"]
    revs = [m for m in msgs if m.source == "JUSTICE" and m.kind == "evaluation" and "reevaluation_of" in m.value]
    if trig:
        bad = [t.event_id for t in trig if not any(x.value["trigger"] == t.event_id and x.arrived_at >= t.arrived_at for x in revs)]
        res.append(v("JUSTICE-11-01", "trigger_reevaluated", bad,
                     f"{len(trig)} declared trigger(s), each followed by a re-evaluation record",
                     "{n} triggers without a re-evaluation"))
    else:
        res.append(na("JUSTICE-11-01", "trigger_reevaluated", "re-evaluation triggers", "no trigger declared"))
    weak = [x for x in revs if x.value["data"] != "complete"]
    if weak:
        ids = {x.event_id for x in weak} | {x.value["trigger"] for x in weak}
        bad = [x.event_id for x in weak if not x.value["prior_outcome_in_force"]]
        bad += [a.event_id for a in acts if set(a.provenance) & ids]
        res.append(v("JUSTICE-11-03", "weak_data_keeps_outcome", bad,
                     f"{len(weak)} re-evaluation(s) on incomplete, stale or withheld data, each leaving the prior outcome in force",
                     "{n} prior outcomes relieved on incomplete, stale or withheld data"))
    else:
        res.append(na("JUSTICE-11-03", "weak_data_keeps_outcome", "re-evaluation on weak data",
                      "no trigger with incomplete, stale or withheld data" if trig else "no trigger declared"))
    if decs:
        # JUSTICE §2: data flow IMPACT, IDENTITY -> JUSTICE only
        jids = {m.event_id for m in msgs if m.source == "JUSTICE"}
        back = [m.event_id for m in msgs if m.source in ("PTL", "IMPACT", "IDENTITY") and set(m.provenance) & jids]
        res.append(v("JUSTICE-2-01", "justice_downstream_of_impact_identity", back,
                     "data flow from IMPACT and IDENTITY into JUSTICE; no PTL, IMPACT or IDENTITY record derives from a Justice record",
                     "{n} lower-layer records derived from JUSTICE"))
        # JUSTICE §4: identical inputs, identical C (each decision against a fresh evaluation of its own inputs)
        atts = [m.event_id for m in msgs if m.source == "IDENTITY" and m.kind == "evaluation"]
        bad = []
        for d in decs:
            imp = get(d.provenance[0])
            s0v, s1v = (get(p).value for p in imp.provenance)
            fresh = dict(r, s0=s0v, s1_recorded=s1v, recorded_contributions=contributions_for(r, atts.index(d.provenance[1])),
                         appeal_after_minutes=-1, reevaluation_triggers=[], start_dti_day=r["start_dti_day"] + 37)
            f = next((m.value for m in run_chain(fresh)[0].messages() if m.source == "JUSTICE" and m.kind == "decision"), None)
            if f is None or any(f.get(k) != d.value.get(k) for k in ("domains", "shares", "flag", "exclusion_effects")):
                bad.append(f"{d.event_id}: differs from a fresh evaluation of the same inputs")
        res.append(v("JUSTICE-4-01", "same_inputs_same_vector", bad,
                     f"{len(decs)} consequence vector(s), each equal to a fresh evaluation of the same impact and responsibility "
                     "inputs at another time", "{n} vectors that depend on more than their inputs"))
    else:
        for rid, chk in (("JUSTICE-2-01", "justice_downstream_of_impact_identity"), ("JUSTICE-4-01", "same_inputs_same_vector")):
            res.append(na(rid, chk, "Justice evaluation", "no Justice decision (attribution blocked or NO_ATTRIBUTION)"))
    # JUSTICE §7: a restriction exists only against a declared risk of further harm
    restr = [a for a in acts if a.value.get("apply") == "restriction"]
    if restr:
        bad = []
        for a in restr:
            src = [get(p) for p in a.provenance if get(p).source == "JUSTICE" and get(p).kind == "decision"]
            risk = any(r["repeated_harm"] or r["mitigation_insufficient"] or
                       (r["safe_margin"] >= 0 and abs(get(d.provenance[0]).value["I"]) >= r["safe_margin"]) for d in src)
            if not risk:
                bad.append(a.event_id)
        res.append(v("JUSTICE-7-03", "restriction_against_declared_risk", bad,
                     f"{len(restr)} restriction(s), each from a Justice decision with a declared risk of further harm",
                     "{n} restrictions without a declared risk of further harm (punitive)"))
    else:
        res.append(na("JUSTICE-7-03", "restriction_against_declared_risk", "restrictions", "no restriction applied"))
    # JUSTICE §8: functional separation where declared feasible
    iso = [a for a in acts if a.value.get("apply") == "isolation"]
    if iso:
        bad = [a.event_id for a in iso if r["functional_separation_feasible"] and a.value.get("form") != "functional separation"]
        res.append(v("JUSTICE-8-03", "functional_before_physical", bad,
                     f"{len(iso)} isolation measure(s): " + ("functional separation, declared feasible" if r["functional_separation_feasible"]
                                                            else "functional separation declared infeasible; 'last resort' stays open"),
                     "{n} physical confinements where functional separation is declared feasible"))
    else:
        res.append(na("JUSTICE-8-03", "functional_before_physical", "isolation", "no isolation applied"))
    # JUSTICE §9: exclusion withdraws no essentials of survival
    exc = [m for m in decs if m.value["domains"].get("exclusion")]
    if exc:
        bad = [f"{m.event_id}: {e}" for m in exc for e in m.value.get("exclusion_effects", []) if any(k in e for k in SURVIVAL)]
        res.append(v("JUSTICE-9-03", "exclusion_keeps_survival", bad,
                     f"{len(exc)} exclusion(s); none withdraws life support, food, water, shelter, medical care or heating",
                     "{n} exclusion effects that withdraw essentials of survival"))
    else:
        res.append(na("JUSTICE-9-03", "exclusion_keeps_survival", "exclusion", "no exclusion decided"))
    return res


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
    "JUSTICE-4-02": ("output_vector_clean", "PARTIAL", "Observed as fields of the output vector."),
    "JUSTICE-5-01": ("domains_independent", "IMPLEMENTED", None),
    "JUSTICE-10-02": ("individual_accountability_kept", "PARTIAL", "A collective is a declared Subject of kind 'collective'."),
    "JUSTICE-12-01": ("no_exemption", "IMPLEMENTED", None),
    "JUSTICE-13-01": ("cross_layer_isolation", "PARTIAL", "Axiom-defined bounds are not modelled beyond the declared safe margin."),
    "JUSTICE-14-01": ("reproducible", "IMPLEMENTED", None),
    "ERROR-0-01": ("errors_as_states", "PARTIAL", "Observed as error records carrying states only, no blame or misconduct labels."),
    "ERROR-1-01": ("procedural_non_punitive", "PARTIAL", "Procedural: §5 states in order; non-punitive: no measure sourced from the "
                   "error case itself (a harsher recomputed Justice outcome is Q-021)."),
    "ERROR-2-04": ("no_ptl_reinterpretation", "PARTIAL", "Observed as measurements written by a source other than PTL; axiom "
                   "reinterpretation is not modelled beyond that."),
    "ERROR-5-02": ("r1_non_coercive", "IMPLEMENTED", None),
    "ERROR-6-04": ("no_prediction_or_intent", "PARTIAL", "Observed as explicit inference or prediction records."),
    "ERROR-9-03": ("reversibility_preferred", "IMPLEMENTED", None),
    "ERROR-11-01": ("valid_appeal_not_suppressed", "IMPLEMENTED", None),
    "ERROR-11-04": ("no_discretionary_override", "IMPLEMENTED", None),
    "EB-7.2-01": ("dispute_preserves_original", "IMPLEMENTED", None),
    "EB-7.2-02": ("dispute_new_evaluation", "IMPLEMENTED", None),
    "EB-7.2-03": ("dispute_recomputes", "PARTIAL", "Admissibility of new data is the appeal's evidence only."),
    "EB-7.2-04": ("dispute_delta", "IMPLEMENTED", None),
    # returned to work after the reading of the Codex-draft open points (review of checkpoint 6)
    "ERROR-2-03": ("no_new_coercive_measures", "PARTIAL", "Coercion is observed as measures sourced from the error case (appeal or ERROR records)."),
    "ERROR-9-02": ("ptl_consistency_preserved", "PARTIAL", "Observed as measurements written outside PTL; the ORACLE consistency rules are not re-run here."),
    "ERROR-10-02": ("case_reviewable", "PARTIAL", "Reviewability is a recorded property of the closed case; a retention horizon is not modelled."),
    "ERROR-4-02": ("category_e2", "PARTIAL", "The deviation is given by the appeal; ERROR's classification and its limitation rule are checked."),
    "ERROR-4-03": ("category_e3", "PARTIAL", "The deviation is given by the appeal; ERROR's classification and its limitation rule are checked."),
    "ERROR-4-04": ("category_e4", "PARTIAL", "The deviation is given by the appeal; ERROR's classification and its limitation rule are checked."),
    "ERROR-4-05": ("category_e5", "PARTIAL", "The deviation is given by the appeal; ERROR's classification and its limitation rule are checked."),
    "JUSTICE-1-01": ("consequences_not_punishment", "PARTIAL", "Observed as moral or discretionary fields and as measures not computed by JUSTICE."),
    "JUSTICE-9-04": ("exclusion_scope", "PARTIAL", "Effects are recorded labels; indirect lethal exposure is not modelled beyond them."),
    # clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)
    "ERROR-10-03": ("case_in_reliability_count", "PARTIAL", "Clear part only: every closed case is counted; the reliability metric stays open."),
    "ERROR-11-03": ("statistics_omit_no_case", "PARTIAL", "Clear part only: published statistics omit no case; the audience stays open."),
    "ERROR-3.3-01": ("appellant_named_by_decision", "PARTIAL", "Clear part only: admission needs a Subject the decision names; 'directly affected' stays open."),
    "ERROR-5-06": ("state_dti_indexed", "PARTIAL", "Clear part only: every state carries its own DTI-Day; timeouts stay open."),
    "ERROR-6-01": ("appeal_with_bond", "PARTIAL", "Clear part only: no appeal admitted without a bond; the bond amount stays open."),
    "ERROR-9-04": ("correction_within_scope", "PARTIAL", "Clear part only: corrective changes within the declared case scope; the error boundary stays open."),
    "JUSTICE-11-01": ("trigger_reevaluated", "PARTIAL", "Clear part only: a declared trigger is followed by a re-evaluation; the response time stays open."),
    "JUSTICE-11-03": ("weak_data_keeps_outcome", "PARTIAL", "Clear part only: data flagged incomplete, stale or withheld keep the prior outcome; detection stays open."),
    "JUSTICE-2-01": ("justice_downstream_of_impact_identity", "PARTIAL", "Clear part only: direct data flow from IMPACT and IDENTITY; 'above'/'below' and the inventory stay open."),
    "JUSTICE-4-01": ("same_inputs_same_vector", "PARTIAL", "Clear part only: identical inputs give an identical vector; the vector schema stays open."),
    "JUSTICE-7-03": ("restriction_against_declared_risk", "PARTIAL", "Clear part only: no restriction without a declared risk of further harm; the evidence stays open."),
    "JUSTICE-8-03": ("functional_before_physical", "PARTIAL", "Clear part only: no confinement where functional separation is declared feasible; feasibility and 'last resort' stay open."),
    "JUSTICE-9-03": ("exclusion_keeps_survival", "PARTIAL", "Clear part only: no withdrawal of essentials of survival; indirect effects stay open."),
}

SUBJECT = {"type": "object", "fields": {
    "id": {"type": "str"},
    "kind": {"type": "enum", "values": list(SUBJECT_KINDS)},
    "contribution": {"type": "number", "min": 0, "max": 10 ** 9},
    "originator": {"type": "str", "default": "none"},
    "status": {"type": "enum", "values": ["none", "official", "authority", "foreign_jurisdiction", "ideological", "cultural"],
               "default": "none"},
}}


class DisputeCorrectionModule(LabModule):
    id = "dispute_correction"
    version = "1.6.0"
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
                     "default": [{"id": "plant", "kind": "legal_entity", "contribution": 3, "originator": "none", "status": "none"},
                                 {"id": "logistics", "kind": "legal_entity", "contribution": 1, "originator": "none",
                                  "status": "none"}],
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
        "appeal_bond_posted": {"type": "bool", "default": True, "source": "user",
                               "label": {"en": "The appeal carries the minimal bond (ERROR §6; amount not given)",
                                         "ru": "Апелляция сопровождается минимальным залогом (ERROR §6; сумма не задана)"}},
        "functional_separation_feasible": {"type": "bool", "default": True, "source": "user",
                                           "label": {"en": "Functional separation technically feasible (JUSTICE §8)",
                                                     "ru": "Функциональное разделение технически возможно (JUSTICE §8)"}},
        "reevaluation_triggers": {"type": "list", "min_items": 0, "max_items": 10, "default": [], "source": "user",
                                  "items": {"type": "object", "fields": {
                                      "after_minutes": {"type": "int", "min": 0, "max": 10 ** 7},
                                      "kind": {"type": "enum", "values": list(TRIGGER_KINDS)},
                                      "data": {"type": "enum", "values": list(TRIGGER_DATA), "default": "complete"}}},
                                  "label": {"en": "Re-evaluation triggers {after_minutes, kind, data} (JUSTICE §11)",
                                            "ru": "Поводы для переоценки {after_minutes, kind, data} (JUSTICE §11)"}},
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
        checks = run_checks(r, log, store, out) + core_checks(r, log, out)
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
            "execution_error_appeal": {**base, "appeal_category": "E2"},
            "impact_error_appeal": {**base, "appeal_category": "E4"},
            "procedural_error_appeal": {**base, "appeal_category": "E5"},
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
            "collective_with_members": {**base, "appeal_after_minutes": -1, "appellant": "m1",
                                        "subjects": [{"id": "union", "kind": "collective", "contribution": 2},
                                                     {"id": "m1", "kind": "human", "contribution": 1},
                                                     {"id": "m2", "kind": "human", "contribution": 1}]},
            "official_subject": {**base, "appeal_after_minutes": -1, "appellant": "logistics",
                                 "subjects": [{"id": "ministry", "kind": "legal_entity", "contribution": 3, "status": "authority"},
                                              {"id": "logistics", "kind": "legal_entity", "contribution": 1}]},
            "faulty_justice_output": {**base, "appeal_after_minutes": -1, "appellant": "logistics", "repeated_harm": False,
                                      "safe_margin": 100,
                                      "subjects": [{"id": "ministry", "kind": "legal_entity", "contribution": 3, "status": "authority"},
                                                   {"id": "logistics", "kind": "legal_entity", "contribution": 1}],
                                      "faults": ["moral_output", "exempt_by_status", "justice_policy", "opaque_adjustment"]},
            "faulty_error_conduct": {**base, "faults": ["moralize_error", "coercive_verification", "infer_intent",
                                                        "error_rewrites_ptl", "discretionary_override"]},
            "appeal_without_standing": {**base, "appellant": "bystander",
                                        "subjects": [{"id": "plant", "kind": "legal_entity", "contribution": 3},
                                                     {"id": "logistics", "kind": "legal_entity", "contribution": 1},
                                                     {"id": "bystander", "kind": "human", "contribution": 0}]},
            "appeal_without_bond": {**base, "appeal_bond_posted": False},
            "reevaluation_triggers": {**base, "appeal_after_minutes": -1,
                                      "reevaluation_triggers": [{"after_minutes": 600, "kind": "mitigation", "data": "complete"},
                                                                {"after_minutes": 900, "kind": "impact_change", "data": "stale"}]},
            "isolation_without_functional_option": {**base, "appeal_after_minutes": -1, "functional_separation_feasible": False},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "proxy_without_originator": {"subjects": [{"id": "bot", "kind": "smart_contract", "contribution": 1,
                                                       "originator": "nobody"}], "appellant": "bot"},
            "zero_bound": {"bound": 0},
            "unknown_appellant": {"appellant": "stranger"},
            "contributions_mismatch": {"recorded_contributions": [1, 2, 3]},
        }
