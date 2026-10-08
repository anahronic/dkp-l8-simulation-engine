"""
IMPACT ATTRIBUTION module — DKP-1-IMPACT-001 (measurement) feeding DKP-1-IDENTITY-001 (attribution).

IMPACT turns two PTL states per channel into channel-separated outputs Iᵢ, Bᵢ, Rᵢ, Xᵢ, Uᵢ: Iᵢ = (Sᵢ(t₁) −
Sᵢ(t₀)) / Bᵢ, boundary approach and crossing, reversibility by declared formal criteria, externality with a
planetary default, deterministic uncertainty propagation, no aggregation, no higher-layer override.
IDENTITY binds every impact to Subjects through auditable chains of actions: omissions count, intent does
not; delegation transfers execution, not responsibility; smart contracts and scripts are never independent
Subjects; collectives share responsibility by contribution; dissolution does not erase history; cascades
and higher-order effects are attributed under §8-§10; no status exempts; low confidence gives NO_ATTRIBUTION
without enforcement.  Cultural and cognitive channels are fed only when the PTL emits a declared physical
proxy; whether it may is reading-dependent (F-037).

Time unit: step (one evaluation).  Two values are missing: the boundary-approach fraction (§6) and the
minimum attribution confidence (IDENTITY §4.1, "as defined by DKP-8-SIMULATION-001 calibration").
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

CHANNEL_KINDS = ("biosphere", "atmosphere", "health_proxy", "resource", "energy", "cognitive_proxy", "cultural_indicator")
NON_PHYSICAL = ("cognitive_proxy", "cultural_indicator")
BOUND_SOURCES = ("axioms", "ptl_index", "undeclared")
SUBJECT_KINDS = ("human", "legal_entity", "collective", "dao", "ai", "smart_contract", "script", "hybrid")
PROXY_KINDS = ("smart_contract", "script")           # IDENTITY §5: never independent Subjects
EXEMPTIONS = ("status", "authority", "jurisdiction", "ideology", "cultural_justification", "delegation", "time_delay")
LAYER_ACTIONS = ("alter_bound", "suppress_channel", "override_flag", "inject_weighting")

FAULTS = {
    "aggregate_score": "IMPACT emits one aggregated score",
    "modify_bound": "IMPACT rescales a reference bound",
    "no_crossing_flag": "a boundary crossing is not flagged",
    "local_default_boundary": "the system boundary defaults to local, not planetary",
    "no_externality_without_boundary": "an undefined system boundary is treated as internal",
    "nondeterministic_uncertainty": "uncertainty propagation is not reproducible",
    "accept_layer_override": "a higher-layer protocol overrides an IMPACT flag",
    "subjective_reversibility": "reversibility is set from a declared intent",
    "intent_exemption": "an unintended action is not attributed",
    "omission_ignored": "an omission is not treated as an action",
    "delegate_shift": "responsibility moves to the delegate without a validated counter-binding",
    "contract_as_subject": "a smart contract is held responsible instead of its deployer",
    "status_exemption": "a Subject is exempted for its status",
    "dissolution_erases": "a dissolved Subject's attribution is deleted",
    "equal_split": "a collective's responsibility is split equally, not by contribution",
    "force_degraded_attribution": "attribution is forced below the confidence threshold",
    "cascade_on_no_attribution": "enforcement proceeds on NO_ATTRIBUTION",
    "speculative_attribution": "a higher-order effect is attributed through speculative intent modelling",
    "identity_measures_magnitude": "the attribution record carries a sanction and a magnitude",
}


def measure(r, faults=frozenset()):
    """IMPACT §5-§10 for every channel."""
    out = {}
    for c in r["channels"]:
        if c["kind"] in NON_PHYSICAL and not c["ptl_proxy_declared"]:
            out[c["name"]] = {"emitted": False, "reason": "no PTL output for this channel"}
            continue
        if c["bound_source"] == "undeclared":
            out[c["name"]] = {"emitted": False, "reason": "no declared reference bound (§6)"}
            continue
        b = c["bound"] * (2 if "modify_bound" in faults else 1)
        i = (c["s1"] - c["s0"]) / b
        cross = abs(i) >= 1 and "no_crossing_flag" not in faults
        approach = abs(i) >= r["approach_fraction"]
        boundary = c["system_boundary"]
        if boundary == "default":
            boundary = "local" if "local_default_boundary" in faults else "planetary"
        x = cross or (boundary == "undefined" and "no_externality_without_boundary" not in faults) or \
            (boundary != "planetary" and c["spills_beyond_boundary"])
        rev_crit = c["irreversible_criterion"]
        rr = not rev_crit
        if "subjective_reversibility" in faults and c["declared_intent"] == "benign":
            rr = True
        u = c["sigma"] / b
        if "nondeterministic_uncertainty" in faults:
            import random
            u += random.random() * 1e-9
        out[c["name"]] = {"emitted": True, "I": round(i, 9), "B": b, "R": rr, "X": x, "U": round(u, 9),
                          "approach": approach, "crossing": cross, "boundary": boundary, "kind": c["kind"]}
    return out


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    for c in r["channels"]:
        put("observation", "PTL", 0, {"channel": c["name"], "s0": c["s0"], "s1": c["s1"], "sigma": c["sigma"],
                                      "proxy": c["kind"] in NON_PHYSICAL and c["ptl_proxy_declared"]})
    m = measure(r, faults)
    for name, o in m.items():
        put("evaluation", "IMPACT", 1, {"channel": name, **o})
    if "aggregate_score" in faults:
        put("evaluation", "IMPACT", 1, {"aggregate_score": round(sum(o["I"] for o in m.values() if o["emitted"]), 9)})
    for q in r["layer_requests"]:
        ok = "accept_layer_override" in faults
        put("decision", "IMPACT", 1, {"layer_request": q["action"], "by": q["protocol"], "executed": ok})
        if not ok:
            put("notice", "AUDIT", 1, {"critical_architectural_breach": q["protocol"], "action": q["action"]})
    # IDENTITY: attribution per impact channel, from IMPACT outputs only
    subj = {s["id"]: s for s in r["subjects"]}
    for ch, o in m.items():
        if not o["emitted"] or (o["I"] == 0 and not o["crossing"]):
            continue
        acts = [a for a in r["actions"] if a["channel"] == ch]
        conf = min([a["confidence"] for a in acts] or [0.0])
        if conf < r["min_attribution_confidence"] and "force_degraded_attribution" not in faults:
            put("decision", "IDENTITY", 2, {"impact": ch, "attribution": "NO_ATTRIBUTION", "confidence_state": "INSUFFICIENT_DATA",
                                            "reason": f"attribution confidence {conf} below {r['min_attribution_confidence']}"})
            put("notice", "AUDIT", 2, {"no_attribution": ch, "logged_for_l8_audit": True,
                                       "investigation_priority": "elevated" if o["crossing"] or o["approach"] else "normal"})
            continue
        shares: Dict[str, float] = {}
        chain = []
        for a in acts:
            if a["kind"] == "omission" and "omission_ignored" in faults:
                continue
            if not a["intended"] and "intent_exemption" in faults:
                continue
            if a["order"] > 1 and a["speculative"] and "speculative_attribution" not in faults:
                chain.append({"action": a["id"], "excluded": "requires speculative modelling of intent (§10)"})
                continue
            if a["order"] > 1 and not (a["within_horizon"] and a["traceable"]):
                chain.append({"action": a["id"], "excluded": "outside the horizon or not traceable (§8)"})
                continue
            who = a["subject"]
            path = [who]
            s = subj[who]
            if s["kind"] in PROXY_KINDS and "contract_as_subject" not in faults:
                who = s["deployed_by"]
                path.append(who)
            if a["delegated_by"] != "none":
                if a["counter_binding_validated"] or "delegate_shift" in faults:
                    pass
                else:
                    who = a["delegated_by"]
                    path.append(who)
            if subj[who]["exempt_claim"] != "none" and "status_exemption" in faults:
                chain.append({"action": a["id"], "excluded": f"exempted for {subj[who]['exempt_claim']}"})
                continue
            if subj[who]["dissolved"] and "dissolution_erases" in faults:
                continue
            w = 1.0 if "equal_split" in faults else a["contribution"]
            shares[who] = shares.get(who, 0.0) + w
            chain.append({"action": a["id"], "kind": a["kind"], "path": path, "attributed_to": who})
        tot = sum(shares.values())
        if "equal_split" in faults and shares:
            shares = {k: 1.0 for k in shares}
            tot = float(len(shares))
        rec = {"impact": ch, "attribution": "ATTRIBUTED" if shares else "UNATTRIBUTED",
               "weights": {k: round(x / tot, 9) for k, x in sorted(shares.items())} if tot else {},
               "chain": chain, "confidence_state": "SUFFICIENT_DATA" if conf >= r["min_attribution_confidence"] else "DEGRADED_SIGNAL"}
        if "identity_measures_magnitude" in faults:
            rec["sanction"] = "fine"
            rec["magnitude"] = o["I"]
        put("decision", "IDENTITY", 2, rec)
        if not shares:
            put("notice", "AUDIT", 2, {"critical_system_violation": ch, "reason": "unattributed impact"})
    for q in r["enforcement_requests"]:
        rec = [mm.value for mm in log.messages() if mm.source == "IDENTITY" and mm.value.get("impact") == q["impact"]]
        no_attr = bool(rec) and rec[-1]["attribution"] == "NO_ATTRIBUTION"
        ok = (not no_attr) or "cascade_on_no_attribution" in faults
        put("decision", "JUSTICE", 3, {"enforcement_on": q["impact"], "executed": ok,
                                       "reason": "deferred pending attribution resolution" if not ok else "attribution available"})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    imp = {m.value["channel"]: m.value for m in msgs if m.source == "IMPACT" and "channel" in m.value}
    chans = {c["name"]: c for c in r["channels"]}
    phys = [c for c in r["channels"] if c["kind"] not in NON_PHYSICAL and c["bound_source"] != "undeclared"]
    # IMPACT recomputed
    bad_i, bad_b, bad_x, bad_r, bad_u, bad_cross, bad_app = [], [], [], [], [], [], []
    for c in r["channels"]:
        o = imp[c["name"]]
        if c["bound_source"] == "undeclared" or (c["kind"] in NON_PHYSICAL and not c["ptl_proxy_declared"]):
            if o["emitted"]:
                bad_i.append(c["name"])
            continue
        i = (c["s1"] - c["s0"]) / c["bound"]
        if abs(o["I"] - i) > 1e-9:
            bad_i.append(c["name"])
        if o["B"] != c["bound"]:
            bad_b.append(c["name"])
        if o["crossing"] != (abs(i) >= 1):
            bad_cross.append(c["name"])
        if o["approach"] != (abs(i) >= r["approach_fraction"]):
            bad_app.append(c["name"])
        boundary = "planetary" if c["system_boundary"] == "default" else c["system_boundary"]
        want_x = abs(i) >= 1 or boundary == "undefined" or (boundary != "planetary" and c["spills_beyond_boundary"])
        if o["X"] != want_x or o["boundary"] != boundary:
            bad_x.append(c["name"])
        if o["R"] != (not c["irreversible_criterion"]):
            bad_r.append(c["name"])
        if abs(o["U"] - c["sigma"] / c["bound"]) > 1e-9:
            bad_u.append(c["name"])
    out.append(v("IMPACT-ImpactVectorI__t__t___t_-01", "normalized_change", bad_i, "Iᵢ = (Sᵢ(t₁) − Sᵢ(t₀)) / Bᵢ for every emitted channel",
                 "{n} channels computed otherwise"))
    out.append(v("IMPACT-BaselineStateS_t__-01", "baseline_state", bad_i, "S(t₀) is the measured state before the change", "{n} wrong"))
    out.append(v("IMPACT-ObservedStateS_t__-01", "observed_state", bad_i, "S(t₁) is the measured state after the change", "{n} wrong"))
    out.append(v("IMPACT-PhysicalStateVectorS_t_-01", "state_from_ptl", bad_i, "states taken from PTL observations unchanged", "{n} wrong"))
    out.append(v("IMPACT-2-01", "inputs_from_ptl", [c["name"] for c in r["channels"] if imp[c["name"]]["emitted"] and c["kind"] in NON_PHYSICAL
                                                    and not c["ptl_proxy_declared"]] + bad_i,
                 "every input originates from a PTL output", "{n} channels without PTL input"))
    out.append(v("IMPACT-6-03", "bounds_unchanged", bad_b, "reference bounds used as declared", "{n} bounds modified"))
    out.append(v("IMPACT-ReferenceBoundsB_-01", "bounds_imported", bad_b + [c["name"] for c in r["channels"] if imp[c["name"]]["emitted"]
                                                                            and c["bound_source"] == "undeclared"],
                 "bounds imported from AXIOMS or PTL indices", "{n} channels with other bounds"))
    out.append(v("IMPACT-2-02", "bound_sources", [c["name"] for c in r["channels"] if imp[c["name"]]["emitted"] and c["bound_source"] not in ("axioms", "ptl_index")],
                 "every emitted channel's bound comes from AXIOMS or a PTL index", "{n} channels with an unsourced bound"))
    out.append(v("IMPACT-6-01", "channel_declares_bound", [c["name"] for c in r["channels"] if imp[c["name"]]["emitted"] and c["bound_source"] == "undeclared"],
                 "no channel emitted without a declared bound", "{n} channels emitted without a bound"))
    out.append(v("IMPACT-5-03", "crossing_flag", bad_cross, "|Iᵢ| ≥ 1 flagged as a boundary crossing", "{n} crossings missed"))
    out.append(v("IMPACT-6-02", "boundary_approach", bad_app, f"approach flagged at |Iᵢ| ≥ {r['approach_fraction']} (declared, source missing)",
                 "{n} approaches missed"))
    out.append(v("IMPACT-ExternalityFlagX_-01", "externality_flag", bad_x, "Xᵢ set on crossings, undefined boundaries and spills", "{n} wrong"))
    out.append(v("IMPACT-8-01", "internal_external", bad_x, "internal and external impact distinguished", "{n} wrong"))
    dflt = [c for c in r["channels"] if c["system_boundary"] == "default" and imp[c["name"]]["emitted"]]
    out.append(v("IMPACT-8-02", "planetary_default", [c["name"] for c in dflt if imp[c["name"]]["boundary"] != "planetary"],
                 "system boundary defaults to planetary", "{n} channels with another default") if dflt else
               na("IMPACT-8-02", "planetary_default", "default boundaries", "every channel declares its boundary"))
    und = [c for c in r["channels"] if c["system_boundary"] == "undefined" and imp[c["name"]]["emitted"]]
    out.append(v("IMPACT-8-04", "undefined_boundary_external", [c["name"] for c in und if not imp[c["name"]]["X"]],
                 "an undefined boundary is full externality exposure", "{n} treated as internal") if und else
               na("IMPACT-8-04", "undefined_boundary_external", "undefined boundaries", "none"))
    out.append(v("IMPACT-7-01", "formal_reversibility", bad_r, "Rᵢ from the declared formal criterion, binary", "{n} wrong"))
    out.append(v("IMPACT-7-02", "no_subjective_reversibility", bad_r, "no intent-based reversibility", "{n} intent-based"))
    out.append(v("IMPACT-UncertaintyEnvelopeU_-01", "uncertainty_envelope", bad_u, "Uᵢ = σ / Bᵢ propagated from the PTL", "{n} wrong"))
    out.append(v("IMPACT-9-01", "uncertainty_propagated", bad_u, "PTL uncertainty propagated to each channel", "{n} wrong"))
    again = run(r)
    rep = [m.value["channel"] for m, m2 in zip(msgs, again.messages()) if m.source == "IMPACT" and "channel" in m.value and m.value != m2.value]
    out.append(v("IMPACT-9-02", "deterministic_propagation", rep, "two runs give identical outputs", "{n} channels differ"))
    agg = [m for m in msgs if m.source == "IMPACT" and "aggregate_score" in m.value]
    out.append(v("IMPACT-5-04", "no_cross_channel_aggregation", [1] * len(agg), "channels stay separated", "an aggregated score was produced"))
    out.append(v("IMPACT-5-02", "unaggregated_dimensionless", [1] * len(agg), "outputs unaggregated, dimensionless (Δ/B)", "aggregated output"))
    out.append(v("IMPACT-3-01", "excluded_functions", [1] * len(agg), "no scoring, aggregation, decision or attribution in IMPACT",
                 "IMPACT produced a score"))
    out.append(v("IMPACT-1-01", "measurement_only", [1] * len(agg), "IMPACT measures only", "IMPACT scored"))
    out.append(CheckResult("IMPACT-ImpactHorizon_t-01", "external_horizon", PASS, f"horizon Δt = {r['horizon']} supplied externally"))
    lr = [m.value for m in msgs if m.source == "IMPACT" and "layer_request" in m.value]
    brs = {m.value["critical_architectural_breach"] for m in msgs if m.source == "AUDIT" and "critical_architectural_breach" in m.value}
    if lr:
        out.append(v("IMPACT-11-01", "no_layer_override", [x["layer_request"] for x in lr if x["executed"]], "no higher-layer override executed",
                     "{n} overrides executed"))
        out.append(v("IMPACT-11-02", "breach_flagged", [x["layer_request"] for x in lr if x["by"] not in brs], "attempts flagged as critical breaches",
                     "{n} attempts unflagged"))
    else:
        for rid, chk in (("IMPACT-11-01", "no_layer_override"), ("IMPACT-11-02", "breach_flagged")):
            out.append(na(rid, chk, "layer requests", "none"))
    np_ = [c for c in r["channels"] if c["kind"] in NON_PHYSICAL and c["ptl_proxy_declared"]]
    if np_:
        why = (f"{len(np_)} cognitive or cultural channels fed by declared PTL proxies; ORACLE §5.3 excludes PTL outputs concerning "
               "cultural or social harm and §1 limits the PTL to physical state: whether such a proxy is admissible is not said (F-037)")
        out.append(CheckResult("IMPACT-ImpactChannel-01", "channel_inputs", UNKNOWN, why))
        out.append(CheckResult("IDENTITY-11-01", "cultural_harm_attribution", UNKNOWN, why))
    else:
        out.append(CheckResult("IMPACT-ImpactChannel-01", "channel_inputs", PASS, "every emitted channel is fed by a physical PTL quantity"))
        out.append(na("IDENTITY-11-01", "cultural_harm_attribution", "cultural or cognitive channels", "none fed"))
    # IDENTITY
    att = {m.value["impact"]: m.value for m in msgs if m.source == "IDENTITY"}
    subj = {s["id"]: s for s in r["subjects"]}
    emitted = {ch: o for ch, o in imp.items() if o["emitted"] and (o["I"] != 0 or o["crossing"])}
    exp = _expect_attribution(r, emitted)
    bad = [ch for ch in emitted if att.get(ch, {}).get("weights") != exp[ch]["weights"] or att.get(ch, {}).get("attribution") != exp[ch]["attribution"]]
    orphan = [ch for ch in emitted if exp[ch]["attribution"] == "UNATTRIBUTED"]
    out.append(v("IDENTITY-4-01", "binding_invariant", bad + orphan, "every impact bound to Subjects through traceable chains, or NO_ATTRIBUTION",
                 "{n} impacts attributed otherwise or with no attributable Subject"))
    crit = {m.value["critical_system_violation"] for m in msgs if m.source == "AUDIT" and "critical_system_violation" in m.value}
    out.append(v("IDENTITY-4-02", "unattributed_is_critical", [ch for ch in orphan if ch not in crit],
                 f"{len(orphan)} unattributed impacts flagged as critical system violations", "{n} unattributed impacts not flagged")
               if orphan else na("IDENTITY-4-02", "unattributed_is_critical", "unattributed impacts", "none"))
    out.append(v("IDENTITY-2-02", "from_impact_outputs", [ch for ch in att if ch not in emitted],
                 "attribution only for impacts IMPACT emitted", "{n} attributions without an IMPACT output"))
    out.append(v("IDENTITY-3.3-01", "intent_independent", [a["id"] for a in r["actions"] if not a["intended"] and a["channel"] in emitted
                                                            and _counted(r, a) and not _in_chain(att, a)],
                 "unintended actions attributed like intended ones", "{n} unintended actions dropped"))
    om = [a for a in r["actions"] if a["kind"] == "omission" and a["channel"] in emitted and _counted(r, a)]
    out.append(v("IDENTITY-3.2-02", "omission_is_action", [a["id"] for a in om if not _in_chain(att, a)], "causal omissions attributed as actions",
                 "{n} omissions ignored") if om else na("IDENTITY-3.2-02", "omission_is_action", "omissions", "none"))
    out.append(v("IDENTITY-3.2-01", "action_definition", bad, "interventions, omissions and sustained processes bound to Subjects", "{n} wrong"))
    out.append(v("IDENTITY-3.1-01", "functional_subjects", [s["id"] for s in r["subjects"] if s["kind"] not in SUBJECT_KINDS],
                 "humans, entities, collectives, DAOs, AI and hybrids treated as Subjects", "{n} unknown kinds"))
    dl = [a for a in r["actions"] if a["delegated_by"] != "none" and a["channel"] in emitted and _counted(r, a)]
    out.append(v("IDENTITY-5-01", "delegation_keeps_responsibility", [ch for ch in {a["channel"] for a in dl} if ch in bad],
                 "delegation moved execution, not responsibility (unless a validated counter-binding)", "{n} impacts shifted to delegates")
               if dl else na("IDENTITY-5-01", "delegation_keeps_responsibility", "delegations", "none"))
    px = [a for a in r["actions"] if subj[a["subject"]]["kind"] in PROXY_KINDS and a["channel"] in emitted and _counted(r, a)]
    if px:
        held = [a["id"] for a in px if a["subject"] in att.get(a["channel"], {}).get("weights", {})]
        out.append(v("IDENTITY-5-03", "no_independent_contracts", held, "smart contracts and scripts never held as independent Subjects",
                     "{n} contracts held responsible"))
        out.append(v("IDENTITY-5-04", "contract_to_deployer", held, "their actions attributed to the deploying Subject", "{n} not passed to deployers"))
    else:
        for rid, chk in (("IDENTITY-5-03", "no_independent_contracts"), ("IDENTITY-5-04", "contract_to_deployer")):
            out.append(na(rid, chk, "proxy subjects", "none acted"))
    ai = [a for a in r["actions"] if subj[a["subject"]]["kind"] == "ai" and a["channel"] in emitted and _counted(r, a)]
    out.append(v("IDENTITY-5-02", "ai_no_exemption", [a["id"] for a in ai if not _in_chain(att, a)], "AI actions attributed, without exemption",
                 "{n} AI actions dropped") if ai else na("IDENTITY-5-02", "ai_no_exemption", "AI actions", "none"))
    coll = [ch for ch in emitted if len(exp[ch]["weights"] or {}) > 1]
    out.append(v("IDENTITY-6-01", "proportional_distribution", [ch for ch in coll if ch in bad],
                 "shared impacts distributed by measurable causal contribution", "{n} impacts split otherwise")
               if coll else na("IDENTITY-6-01", "proportional_distribution", "shared impacts", "none"))
    ex = [s["id"] for s in r["subjects"] if s["exempt_claim"] != "none"]
    out.append(v("IDENTITY-12-01", "no_exemption", [ch for ch in emitted if ch in bad and any(e in (exp[ch]["weights"] or {}) for e in ex)],
                 "claims of status, authority, jurisdiction or delay exempt no one", "{n} impacts with an exempted Subject")
               if ex else na("IDENTITY-12-01", "no_exemption", "exemption claims", "none"))
    ds = [s["id"] for s in r["subjects"] if s["dissolved"]]
    out.append(v("IDENTITY-7-02", "dissolution_keeps_history", [ch for ch in emitted if any(d in (exp[ch]["weights"] or {}) for d in ds) and ch in bad],
                 "dissolved Subjects keep their historical attribution", "{n} attributions erased") if ds else
               na("IDENTITY-7-02", "dissolution_keeps_history", "dissolved Subjects", "none"))
    hi = [a for a in r["actions"] if a["order"] > 1 and a["channel"] in emitted]
    if hi:
        spec = [a["id"] for a in hi if a["speculative"] and _in_chain(att, a)]
        out.append(v("IDENTITY-10-02", "higher_order_conditions", spec, "higher-order effects attributed only when measurable and not speculative",
                     "{n} attributed through speculative modelling"))
        out.append(v("IDENTITY-8-01", "cascade_conditions", [a["id"] for a in hi if not (a["within_horizon"] and a["traceable"]) and _in_chain(att, a)]
                     + [a["id"] for a in hi if a["within_horizon"] and a["traceable"] and not a["speculative"] and not _in_chain(att, a)
                        and att.get(a["channel"], {}).get("attribution") == "ATTRIBUTED"],
                     "downstream impacts attributed when traceable and within the horizon", "{n} cascade attributions wrong"))
        out.append(v("IDENTITY-8-02", "foresight_irrelevant", [a["id"] for a in hi if not a["foreseeable"] and a["within_horizon"] and a["traceable"]
                                                                and not a["speculative"] and not _in_chain(att, a)
                                                                and att.get(a["channel"], {}).get("attribution") == "ATTRIBUTED"],
                     "unforeseeable downstream impacts attributed", "{n} dropped for lack of foresight"))
        out.append(v("IDENTITY-10-01", "higher_order_definition", [], "second- and third-order effects tracked by order", ""))
    else:
        for rid, chk in (("IDENTITY-10-02", "higher_order_conditions"), ("IDENTITY-8-01", "cascade_conditions"),
                         ("IDENTITY-8-02", "foresight_irrelevant"), ("IDENTITY-10-01", "higher_order_definition")):
            out.append(na(rid, chk, "higher-order effects", "none"))
    noat = [ch for ch, a in att.items() if a["attribution"] == "NO_ATTRIBUTION"]
    low = [ch for ch in emitted if exp[ch]["attribution"] == "NO_ATTRIBUTION"]
    if low:
        out.append(v("IDENTITY-4.1-01", "no_attribution_state", [ch for ch in low if ch not in noat or att[ch]["confidence_state"] != "INSUFFICIENT_DATA"],
                     f"below confidence {r['min_attribution_confidence']} (declared, source missing): NO_ATTRIBUTION with INSUFFICIENT_DATA",
                     "{n} low-confidence impacts attributed anyway"))
        out.append(v("IDENTITY-4.1-05", "no_output_priority", [ch for ch in low if att.get(ch, {}).get("confidence_state") == "DEGRADED_SIGNAL"],
                     "NO_ATTRIBUTION preferred over degraded attribution", "{n} degraded attributions"))
        enf = [m.value for m in msgs if m.source == "JUSTICE"]
        out.append(v("IDENTITY-4.1-02", "no_cascade", [e["enforcement_on"] for e in enf if e["executed"] and e["enforcement_on"] in low],
                     "no enforcement on NO_ATTRIBUTION", "{n} enforcements on NO_ATTRIBUTION") if enf else
                   na("IDENTITY-4.1-02", "no_cascade", "enforcement requests", "none"))
        logged = {m.value["no_attribution"] for m in msgs if m.source == "AUDIT" and "no_attribution" in m.value}
        pri = {m.value["no_attribution"]: m.value["investigation_priority"] for m in msgs if m.source == "AUDIT" and "no_attribution" in m.value}
        out.append(v("IDENTITY-4.1-04", "investigation_priority",
                     [ch for ch in noat if (pri.get(ch) == "elevated") != (imp[ch]["crossing"] or imp[ch]["approach"])],
                     "NO_ATTRIBUTION on significant impacts (approach or crossing) raised investigation priority, without an outcome",
                     "{n} priorities wrong"))
        out.append(v("IDENTITY-4.1-03", "logged_and_deferred", [ch for ch in noat if ch not in logged], "NO_ATTRIBUTION logged for L8 audit; enforcement deferred",
                     "{n} not logged"))
    else:
        for rid, chk in (("IDENTITY-4.1-01", "no_attribution_state"), ("IDENTITY-4.1-05", "no_output_priority"), ("IDENTITY-4.1-02", "no_cascade"),
                         ("IDENTITY-4.1-03", "logged_and_deferred"), ("IDENTITY-4.1-04", "investigation_priority")):
            out.append(na(rid, chk, "low-confidence impacts", "none"))
    leak = [ch for ch, a in att.items() if "sanction" in a or "magnitude" in a]
    out.append(v("IDENTITY-13-01", "attribution_only", leak, "attribution records carry no magnitude and no sanction", "{n} records with sanctions"))
    out.append(v("IDENTITY-1-01", "attribution_not_punishment", leak, "identity binding only", "{n} records punish"))
    return out


def _counted(r, a):
    return not (a["order"] > 1 and (a["speculative"] or not (a["within_horizon"] and a["traceable"])))


def _in_chain(att, a):
    return any(c.get("action") == a["id"] and "attributed_to" in c for c in att.get(a["channel"], {}).get("chain", []))


def _expect_attribution(r, emitted):
    subj = {s["id"]: s for s in r["subjects"]}
    out = {}
    for ch in emitted:
        acts = [a for a in r["actions"] if a["channel"] == ch]
        conf = min([a["confidence"] for a in acts] or [0.0])
        if conf < r["min_attribution_confidence"]:
            out[ch] = {"attribution": "NO_ATTRIBUTION", "weights": None}
            continue
        sh: Dict[str, float] = {}
        for a in acts:
            if not _counted(r, a):
                continue
            who = a["subject"]
            if subj[who]["kind"] in PROXY_KINDS:
                who = subj[who]["deployed_by"]
            if a["delegated_by"] != "none" and not a["counter_binding_validated"]:
                who = a["delegated_by"]
            sh[who] = sh.get(who, 0.0) + a["contribution"]
        t = sum(sh.values())
        out[ch] = {"attribution": "ATTRIBUTED" if sh else "UNATTRIBUTED", "weights": {k: round(x / t, 9) for k, x in sorted(sh.items())} if t else {}}
    return out


IMPLEMENTS = {
    "IMPACT-1-01": ("measurement_only", "PARTIAL", "Checked as: no score produced."),
    "IMPACT-2-01": ("inputs_from_ptl", "IMPLEMENTED", None),
    "IMPACT-2-02": ("bound_sources", "IMPLEMENTED", None),
    "IMPACT-3-01": ("excluded_functions", "PARTIAL", "Scoring and aggregation only."),
    "IMPACT-PhysicalStateVectorS_t_-01": ("state_from_ptl", "PARTIAL", "One component per channel."),
    "IMPACT-BaselineStateS_t__-01": ("baseline_state", "IMPLEMENTED", None),
    "IMPACT-ObservedStateS_t__-01": ("observed_state", "IMPLEMENTED", None),
    "IMPACT-ImpactHorizon_t-01": ("external_horizon", "PARTIAL", "The horizon is a declared input."),
    "IMPACT-ImpactChannel-01": ("channel_inputs", "PARTIAL", "Cognitive and cultural channels: F-037."),
    "IMPACT-ImpactVectorI__t__t___t_-01": ("normalized_change", "IMPLEMENTED", None),
    "IMPACT-ReferenceBoundsB_-01": ("bounds_imported", "PARTIAL", "Bound source is declared."),
    "IMPACT-ExternalityFlagX_-01": ("externality_flag", "IMPLEMENTED", None),
    "IMPACT-UncertaintyEnvelopeU_-01": ("uncertainty_envelope", "PARTIAL", "Uᵢ = σ/Bᵢ (H-IA-2)."),
    "IMPACT-5-02": ("unaggregated_dimensionless", "IMPLEMENTED", None),
    "IMPACT-5-04": ("no_cross_channel_aggregation", "IMPLEMENTED", None),
    "IMPACT-6-01": ("channel_declares_bound", "IMPLEMENTED", None),
    "IMPACT-6-02": ("boundary_approach", "PARTIAL", "The approach fraction is not given (source missing)."),
    "IMPACT-6-03": ("bounds_unchanged", "IMPLEMENTED", None),
    "IMPACT-7-01": ("formal_reversibility", "PARTIAL", "The formal criterion is a declared flag."),
    "IMPACT-7-02": ("no_subjective_reversibility", "IMPLEMENTED", None),
    "IMPACT-8-01": ("internal_external", "PARTIAL", "Spill beyond the boundary is declared."),
    "IMPACT-8-02": ("planetary_default", "IMPLEMENTED", None),
    "IMPACT-8-04": ("undefined_boundary_external", "IMPLEMENTED", None),
    "IMPACT-9-01": ("uncertainty_propagated", "PARTIAL", "Linear propagation (H-IA-2)."),
    "IMPACT-9-02": ("deterministic_propagation", "IMPLEMENTED", None),
    "IMPACT-11-01": ("no_layer_override", "IMPLEMENTED", None),
    "IMPACT-11-02": ("breach_flagged", "IMPLEMENTED", None),
    "IDENTITY-1-01": ("attribution_not_punishment", "PARTIAL", "Record fields only."),
    "IDENTITY-2-02": ("from_impact_outputs", "IMPLEMENTED", None),
    "IDENTITY-3.1-01": ("functional_subjects", "PARTIAL", "Subject kinds are declared."),
    "IDENTITY-3.2-01": ("action_definition", "PARTIAL", "Actions are declared with their channel."),
    "IDENTITY-3.2-02": ("omission_is_action", "IMPLEMENTED", None),
    "IDENTITY-3.3-01": ("intent_independent", "IMPLEMENTED", None),
    "IDENTITY-4-01": ("binding_invariant", "PARTIAL", "Causal chains are declared, not discovered."),
    "IDENTITY-4-02": ("unattributed_is_critical", "IMPLEMENTED", None),
    "IDENTITY-4.1-04": ("investigation_priority", "PARTIAL", "'Significant' = boundary approach or crossing (H-IA-4)."),
    "IDENTITY-4.1-01": ("no_attribution_state", "PARTIAL", "The confidence threshold is not given (source missing)."),
    "IDENTITY-4.1-05": ("no_output_priority", "IMPLEMENTED", None),
    "IDENTITY-5-01": ("delegation_keeps_responsibility", "PARTIAL", "Counter-binding validation is declared."),
    "IDENTITY-5-02": ("ai_no_exemption", "IMPLEMENTED", None),
    "IDENTITY-6-01": ("proportional_distribution", "PARTIAL", "Contributions are declared."),
    "IDENTITY-7-02": ("dissolution_keeps_history", "IMPLEMENTED", None),
    "IDENTITY-8-01": ("cascade_conditions", "PARTIAL", "Horizon and traceability are declared per action."),
    "IDENTITY-8-02": ("foresight_irrelevant", "IMPLEMENTED", None),
    "IDENTITY-10-01": ("higher_order_definition", "PARTIAL", "Order is declared."),
    "IDENTITY-10-02": ("higher_order_conditions", "PARTIAL", "Speculativeness is declared."),
    "IDENTITY-11-01": ("cultural_harm_attribution", "PARTIAL", "F-037."),
    "IDENTITY-12-01": ("no_exemption", "IMPLEMENTED", None),
    "IDENTITY-13-01": ("attribution_only", "PARTIAL", "Record fields only."),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")
NUM = {"type": "number", "min": -10 ** 9, "max": 10 ** 9}
B = {"type": "bool"}


def _lst(fields, default, label, mx=20):
    return {"type": "list", "min_items": 0, "max_items": mx, "items": {"type": "object", "fields": fields}, "default": default,
            "source": "user", "label": label}


CH = {"name": {"type": "str"}, "kind": {"type": "enum", "values": list(CHANNEL_KINDS)}, "s0": NUM, "s1": NUM,
      "bound": {"type": "number", "min": 1e-9, "max": 10 ** 9}, "bound_source": {"type": "enum", "values": list(BOUND_SOURCES), "default": "axioms"},
      "sigma": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0.0},
      "irreversible_criterion": {"type": "bool", "default": False},
      "declared_intent": {"type": "enum", "values": ["none", "benign", "hostile"], "default": "none"},
      "system_boundary": {"type": "enum", "values": ["default", "planetary", "regional", "undefined"], "default": "default"},
      "spills_beyond_boundary": {"type": "bool", "default": False},
      "ptl_proxy_declared": {"type": "bool", "default": False}}
SU = {"id": {"type": "str"}, "kind": {"type": "enum", "values": list(SUBJECT_KINDS)},
      "deployed_by": {"type": "str", "default": "none"}, "dissolved": {"type": "bool", "default": False},
      "exempt_claim": {"type": "enum", "values": ["none"] + list(EXEMPTIONS), "default": "none"}}
AC = {"id": {"type": "str"}, "subject": {"type": "str"}, "channel": {"type": "str"},
      "kind": {"type": "enum", "values": ["intervention", "omission", "sustained"], "default": "intervention"},
      "contribution": {"type": "number", "min": 0.0001, "max": 10 ** 6, "default": 1.0},
      "intended": {"type": "bool", "default": True}, "delegated_by": {"type": "str", "default": "none"},
      "counter_binding_validated": {"type": "bool", "default": False},
      "order": {"type": "int", "min": 1, "max": 3, "default": 1}, "within_horizon": {"type": "bool", "default": True},
      "traceable": {"type": "bool", "default": True}, "speculative": {"type": "bool", "default": False},
      "foreseeable": {"type": "bool", "default": True}, "confidence": {"type": "number", "min": 0, "max": 1, "default": 0.95}}


class ImpactAttributionModule(LabModule):
    id = "impact_attribution"
    version = "1.0.0"
    title = {"en": "Impact and attribution (IMPACT, IDENTITY)", "ru": "Воздействие и атрибуция (IMPACT, IDENTITY)"}
    summary = {"en": "A plant emits, a contractor dumps through a smart contract, a regulator fails to act, a coalition pumps "
                     "groundwater: does IMPACT measure each channel apart, and does IDENTITY bind every impact to the right Subjects?",
               "ru": "Завод выбрасывает, подрядчик сбрасывает через смарт-контракт, регулятор бездействует, коалиция откачивает воду: "
                     "измеряет ли IMPACT каждый канал отдельно и связывает ли IDENTITY каждое воздействие с нужными субъектами?"}
    protocols = ["DKP-1-IMPACT-001", "DKP-1-IDENTITY-001"]
    example_order = ["industrial_chain", "low_confidence", "faulty_chain"]
    noncompliant_examples = ["untraceable_impact"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_impact_attribution_module.py"]
    causal_note = {"en": "Causal chains (who did what, with which contribution) are declared inputs, not discovered by the lab.",
                   "ru": "Причинные цепочки (кто что сделал и с каким вкладом) — объявленные входы, лаборатория их не выявляет."}
    hypotheses = [
        {"id": "H-IA-1", "source": "hypothesis", "text": {
            "en": "Each action declares its channel, contribution, order and the facts §8-§10 need (horizon, traceability, speculation).",
            "ru": "Каждое действие объявляет канал, вклад, порядок и факты для §8-§10 (горизонт, прослеживаемость, спекулятивность)."}},
        {"id": "H-IA-2", "source": "hypothesis", "text": {
            "en": "Uᵢ = σ / Bᵢ: the PTL standard deviation divided by the bound (§9 names Bayesian ensembles only as an illustration).",
            "ru": "Uᵢ = σ / Bᵢ: стандартное отклонение PTL, делённое на границу (§9 упоминает байесовские ансамбли лишь как пример)."}},
        {"id": "H-IA-4", "source": "hypothesis", "text": {
            "en": "A 'significant impact event' (§4.1 c) is one that approaches or crosses its reference bound.",
            "ru": "'Значимое событие воздействия' (§4.1 c) — приближение к границе или её пересечение."}},
        {"id": "H-IA-3", "source": "hypothesis", "text": {
            "en": "Attribution confidence of an impact = the lowest confidence among its declared actions.",
            "ru": "Уверенность атрибуции воздействия = наименьшая уверенность среди его объявленных действий."}},
    ]
    inputs = {
        "horizon": {"type": "int", "min": 1, "max": 10 ** 6, "default": 365, "unit": "day", "source": "user",
                    "label": {"en": "Impact horizon Δt (external)", "ru": "Горизонт воздействия Δt (внешний)"}},
        "approach_fraction": {"type": "number", "min": 0.01, "max": 1, "default": 0.8, "source": "missing",
                              "label": {"en": "Boundary approach at |Iᵢ| ≥ (§6)", "ru": "Приближение к границе при |Iᵢ| ≥ (§6)"}},
        "min_attribution_confidence": {"type": "number", "min": 0, "max": 1, "default": 0.7, "source": "missing",
                                       "label": {"en": "Minimum attribution confidence (§4.1)", "ru": "Минимальная уверенность атрибуции (§4.1)"}},
        "channels": _lst(CH, [
            {"name": "co2_air", "kind": "atmosphere", "s0": 426.91, "s1": 427.0, "bound": 450.0, "sigma": 0.01},
            {"name": "river_pollutant", "kind": "biosphere", "s0": 10.0, "s1": 95.0, "bound": 80.0, "sigma": 2.0,
             "irreversible_criterion": True, "system_boundary": "regional", "spills_beyond_boundary": True},
            {"name": "aquifer", "kind": "resource", "s0": 100.0, "s1": 40.0, "bound": 70.0, "sigma": 1.0, "system_boundary": "undefined"},
            {"name": "dialect_use", "kind": "cultural_indicator", "s0": 0.8, "s1": 0.6, "bound": 0.5, "ptl_proxy_declared": True},
            {"name": "noise_late", "kind": "health_proxy", "s0": 40.0, "s1": 52.0, "bound": 20.0, "bound_source": "undeclared"}],
            {"en": "Impact channels (PTL states)", "ru": "Каналы воздействия (состояния PTL)"}),
        "subjects": _lst(SU, [
            {"id": "plant_co", "kind": "legal_entity"}, {"id": "contractor", "kind": "legal_entity", "dissolved": True},
            {"id": "dump_contract", "kind": "smart_contract", "deployed_by": "contractor"},
            {"id": "regulator", "kind": "human", "exempt_claim": "authority"}, {"id": "farm_coalition", "kind": "collective"},
            {"id": "farm_a", "kind": "legal_entity"}, {"id": "router_ai", "kind": "ai"}, {"id": "media_co", "kind": "legal_entity"}],
            {"en": "Subjects", "ru": "Субъекты"}),
        "actions": _lst(AC, [
            {"id": "a1", "subject": "plant_co", "channel": "co2_air"},
            {"id": "a2", "subject": "dump_contract", "channel": "river_pollutant", "contribution": 3.0, "intended": False},
            {"id": "a3", "subject": "regulator", "channel": "river_pollutant", "kind": "omission", "contribution": 1.0},
            {"id": "a4", "subject": "farm_coalition", "channel": "aquifer", "kind": "sustained", "contribution": 2.0},
            {"id": "a5", "subject": "farm_a", "channel": "aquifer", "contribution": 1.0},
            {"id": "a6", "subject": "router_ai", "channel": "aquifer", "contribution": 1.0, "delegated_by": "farm_a"},
            {"id": "a7", "subject": "plant_co", "channel": "river_pollutant", "order": 2, "contribution": 1.0, "foreseeable": False},
            {"id": "a8", "subject": "media_co", "channel": "dialect_use", "order": 3, "speculative": True},
            {"id": "a9", "subject": "media_co", "channel": "dialect_use", "order": 2}],
            {"en": "Actions (declared causal chains)", "ru": "Действия (объявленные причинные цепочки)"}),
        "layer_requests": _lst({"protocol": {"type": "str"}, "action": {"type": "enum", "values": list(LAYER_ACTIONS)}},
                               [{"protocol": "finance", "action": "inject_weighting"}, {"protocol": "justice", "action": "override_flag"}],
                               {"en": "Higher-layer requests to IMPACT", "ru": "Запросы верхних слоёв к IMPACT"}),
        "enforcement_requests": _lst({"impact": {"type": "str"}}, [{"impact": "co2_air"}],
                                     {"en": "Enforcement requests (JUSTICE consumer)", "ru": "Запросы на принуждение (потребитель JUSTICE)"}),
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ch = [c["name"] for c in r["channels"]]
        su = {s["id"]: s for s in r["subjects"]}
        for key, ids in (("channels", ch), ("subjects", list(su)), ("actions", [a["id"] for a in r["actions"]])):
            if len(set(ids)) != len(ids):
                p.append(f"input.{key}: repeated id")
            for x in ids:
                if not _ID.fullmatch(x):
                    p.append(f"input.{key}: identifier {x!r} must be lowercase letters, digits or _")
        for s in su.values():
            if s["kind"] in PROXY_KINDS and s["deployed_by"] not in su:
                p.append(f"input.subjects: {s['id']} needs a declared deployer")
        for a in r["actions"]:
            if a["subject"] not in su or a["channel"] not in ch:
                p.append(f"input.actions: {a['id']} names an unknown subject or channel")
            if a["delegated_by"] != "none" and a["delegated_by"] not in su:
                p.append(f"input.actions: {a['id']} delegated by an unknown subject")
        for q in r["enforcement_requests"]:
            if q["impact"] not in ch:
                p.append(f"input.enforcement_requests: unknown impact {q['impact']!r}")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        outputs = {"impact": [m.value for m in msgs if m.source == "IMPACT" and "channel" in m.value],
                   "attribution": [m.value for m in msgs if m.source == "IDENTITY"],
                   "enforcement": [m.value for m in msgs if m.source == "JUSTICE"],
                   "audit": [m.value for m in msgs if m.source == "AUDIT"],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": f"{sum(1 for o in outputs['impact'] if o['emitted'])} channels measured, {len(outputs['attribution'])} impacts attributed; "
                    f"violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"Измерено каналов: {sum(1 for o in outputs['impact'] if o['emitted'])}, атрибутировано воздействий: {len(outputs['attribution'])}; "
                    f"нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]), "attributed": sum(1 for a in outputs["attribution"] if a["attribution"] == "ATTRIBUTED")}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "industrial_chain": {},
            "low_confidence": {"actions": [{"id": "a1", "subject": "plant_co", "channel": "co2_air", "confidence": 0.4}]},
            "physical_only": {"channels": [{"name": "co2_air", "kind": "atmosphere", "s0": 426.91, "s1": 427.0, "bound": 450.0, "sigma": 0.01}],
                              "actions": [{"id": "a1", "subject": "plant_co", "channel": "co2_air"}]},
            "low_confidence_crossing": {"actions": [{"id": "a2", "subject": "dump_contract", "channel": "river_pollutant", "confidence": 0.3}],
                                        "enforcement_requests": [{"impact": "river_pollutant"}]},
            "benign_irreversible": {"channels": [{"name": "river_pollutant", "kind": "biosphere", "s0": 10.0, "s1": 95.0, "bound": 80.0,
                                                  "irreversible_criterion": True, "declared_intent": "benign"}],
                                    "actions": [{"id": "a2", "subject": "dump_contract", "channel": "river_pollutant"}], "enforcement_requests": []},
            "orphan_impact": {"channels": [{"name": "glacier_mass", "kind": "biosphere", "s0": 100.0, "s1": 70.0, "bound": 50.0}], "actions": [],
                              "enforcement_requests": []},
            "untraceable_impact": {"channels": [{"name": "glacier_mass", "kind": "biosphere", "s0": 100.0, "s1": 70.0, "bound": 50.0}],
                                   "actions": [{"id": "g1", "subject": "plant_co", "channel": "glacier_mass", "order": 2, "traceable": False}],
                                   "enforcement_requests": []},
            "counter_bound_delegation": {"actions": [{"id": "a6", "subject": "router_ai", "channel": "aquifer", "delegated_by": "farm_a",
                                                      "counter_binding_validated": True}]},
            "faulty_chain": {"faults": ["aggregate_score", "delegate_shift", "contract_as_subject", "status_exemption", "identity_measures_magnitude"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"unknown_subject": {"actions": [{"id": "x", "subject": "ghost", "channel": "co2_air"}]},
                "contract_without_deployer": {"subjects": [{"id": "c", "kind": "smart_contract"}]},
                "zero_bound": {"channels": [{"name": "c", "kind": "energy", "s0": 1.0, "s1": 2.0, "bound": 0.0}]}}


for _spec in ImpactAttributionModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
