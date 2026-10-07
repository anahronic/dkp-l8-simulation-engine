"""
POLICE AND ANTI-TERROR module — DKP-3-POLICE-001 and DKP-3-ANTITERROR-001 in one field incident.

Police (§3–§9): action only on PTL-verified active harm, a valid L2/L4 enforcement order or a threat
to critical infrastructure; absence of PTL confirmation means non-intervention; detention only to stop
harm, prevent immediate recurrence or attribute identity, time-limited, logged, reviewed; force only
when non-forceful means fail, proportional, lethal force only under the CRISIS minimum-required
conditions; every action identity-attributed and PTL-logged; crisis extensions explicitly scoped and
ending with the Crisis; statistics aggregated without identities.

Anti-terror (§4–§11): T0–T3 driven by PTL-confirmed asymmetric harm streams against civilians, states
persist only with continuous PTL refresh, T3 escalates to DKP-4-CRISIS-001; permitted actions are
event-scoped (lockdown limited to the threat zone, information isolation technical and time-limited);
actions terminate when PTL confirms cessation; logs go to DKP-1-IMPACT-001; no ideological screening,
mass surveillance, collective punishment, detention without active harm, suppression of dissent,
retrospective justification, sanctions.

Declared values the corpus lacks: detention limit (POLICE §5.1 "time-limited", no number),
thresholds of "acceptable" casualty risk (ANTITERROR §9).  Time unit: hour.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

KINDS = ("physical_harm", "terror_event", "sustained_terror", "mass_casualty", "protest_no_harm")
T_OF = {"terror_event": "T1", "sustained_terror": "T2", "mass_casualty": "T3"}
TRANK = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
AT_ACTIONS = {"interdiction", "vector_isolation", "evacuation", "neutralization", "zone_lockdown", "medical_coordination",
              "information_isolation"}
FAULTS = {
    "act_on_suspicion": "police intervene on suspicion without PTL confirmation",
    "invalid_order": "police execute an order issued outside L2/L4",
    "indefinite_detention": "a detention has no end",
    "no_review": "a detention does not trigger review by higher layers",
    "excess_force": "force above the verified threat level",
    "lethal_force": "lethal force outside the CRISIS minimum-required conditions",
    "unattributed": "a police action is not identity-attributed",
    "unscoped_extension": "police authority is extended without a declared scope",
    "no_refresh_persist": "a terror state persists through a gap in PTL refresh",
    "lockdown_beyond_zone": "a lockdown covers areas outside the threat zone",
    "content_control": "information isolation filters content",
    "no_termination": "anti-terror actions continue after PTL confirms cessation",
    "no_t3_escalation": "T3 is not escalated to CRISIS",
    "collective_responsibility": "associates of the attacker are detained",
    "suppress_dissent": "a protest without harm is designated terror",
    "retrospective": "an action starts before PTL confirmation and is justified afterwards",
    "not_forwarded": "containment logs are not forwarded to IMPACT",
    "impose_sanction": "ANTITERROR imposes an economic sanction",
}
STREAM = {"type": "object", "fields": {
    "from_hour": {"type": "int", "min": 0, "max": 10 ** 6},
    "to_hour": {"type": "int", "min": 0, "max": 10 ** 6},
    "kind": {"type": "enum", "values": list(KINDS)},
    "zone": {"type": "str", "default": "z1"},
    "ptl_confirmed": {"type": "bool", "default": True},
    "threat_level": {"type": "int", "min": 0, "max": 3, "default": 2},
    "alternatives_effective": {"type": "bool", "default": False},
    "attackers": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "str"}, "default": ["a1"]}}}
ORDER = {"type": "object", "fields": {"hour": {"type": "int", "min": 0, "max": 10 ** 6},
                                      "issuer": {"type": "enum", "values": ["L2", "L4", "L3", "none"]},
                                      "target": {"type": "str", "default": "s1"}}}


def md(scope):
    return {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": scope, "revalidation_required": True, "dispute_allowed": True}


def refreshed(r, h):
    return not any(a <= h < b for a, b in r["refresh_gaps"])


def active(r, h, faults=()):
    """Streams the generator may act on at hour h: PTL-confirmed, refreshed (unless a fault)."""
    out = []
    for i, s in enumerate(r["streams"]):
        if not (s["from_hour"] <= h < s["to_hour"]):
            continue
        if s["kind"] == "protest_no_harm" and "suppress_dissent" not in faults:
            continue
        if not s["ptl_confirmed"] and "act_on_suspicion" not in faults:
            continue
        if not refreshed(r, h) and "no_refresh_persist" not in faults:
            continue
        out.append(i)
    return out


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("hour", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, h, value, prov=(), epistemic=None):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{h:06d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=h, decided_at=h if kind in ("decision", "action") else None,
                                  value={**value, "dti": canonical(*dy_doy(r["start_dti_day"] + h // 24))},
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    t_state = "T0"
    detained: Dict[str, Dict[str, Any]] = {}
    obs: Dict[int, Message] = {}
    lo, hi = r["crisis_window"]
    extension_open = False
    for h in range(r["horizon_hours"]):
        crisis = lo <= h < hi
        for i, s in enumerate(r["streams"]):
            if s["from_hour"] <= h < s["to_hour"] and refreshed(r, h):
                obs[i] = put("observation", "PTL" if s["ptl_confirmed"] else "REPORT", h,
                             {"stream": i, "kind": s["kind"], "zone": s["zone"], "threat_level": s["threat_level"],
                              "confirmed": s["ptl_confirmed"]})
            if s["to_hour"] == h and s["ptl_confirmed"] and s["kind"] != "protest_no_harm":
                put("observation", "PTL", h, {"stream": i, "cessation": True})
        idx = active(r, h, faults)
        if "retrospective" in faults:
            idx += [i for i, s in enumerate(r["streams"]) if s["from_hour"] - 1 == h and s["kind"] in T_OF and i not in idx]
        prov = [obs[i].event_id for i in idx if i in obs]
        # crisis extension of police authority (POLICE §8)
        if crisis and not extension_open and r["crisis_extension_scope"] != "none":
            scope = None if "unscoped_extension" in faults else r["crisis_extension_scope"]
            put("notice", "POLICE", h, {"authority_extended": True, "scope": scope, "precedent": False})
            extension_open = True
        if extension_open and not crisis:
            put("notice", "POLICE", h, {"authority_extended": False, "reason": "Crisis ended"})
            extension_open = False
        # anti-terror state (T0–T3)
        terror = [i for i in idx if r["streams"][i]["kind"] in T_OF or
                  (r["streams"][i]["kind"] == "protest_no_harm" and "suppress_dissent" in faults)]
        target = "T0"
        for i in terror:
            t = T_OF.get(r["streams"][i]["kind"], "T1")
            if TRANK[t] > TRANK[target]:
                target = t
        if "no_termination" in faults and t_state != "T0" and target == "T0":
            target = t_state
        if target != t_state:
            put("notice", "ANTITERROR", h, {"state": target, "from": t_state}, prov)
            if target == "T3" and "no_t3_escalation" not in faults:
                put("notice", "CRISIS", h, {"escalation": "mandatory", "from": "DKP-3-ANTITERROR-001 T3"}, prov)
            t_state = target
        if t_state != "T0":
            zone = sorted({r["streams"][i]["zone"] for i in terror}) or [r["streams"][0]["zone"]]
            for kind in (["interdiction", "evacuation", "medical_coordination"] +
                         (["vector_isolation", "zone_lockdown", "information_isolation"] if TRANK[t_state] >= 2 else
                          ["zone_lockdown"])):
                v = {"action": kind, "state": t_state, "zone": zone, "event_scoped": True, "officer": "unit-at",
                     "authority": "DKP-3-ANTITERROR-001", "logged": True}
                if kind == "zone_lockdown":
                    v["area"] = zone + (["city"] if "lockdown_beyond_zone" in faults else [])
                if kind == "information_isolation":
                    v.update({"mode": "content filter" if "content_control" in faults else "signal amplitude",
                              "until_hour": h + 1})
                put("action", "ANTITERROR", h, v, prov, epistemic=md(prov[0]) if prov else None)
            if "impose_sanction" in faults:
                put("action", "ANTITERROR", h, {"action": "economic_sanction", "state": t_state, "officer": "unit-at",
                                                "logged": True}, prov)
            if "not_forwarded" not in faults:
                put("notice", "IMPACT", h, {"containment_log_forwarded": True, "from": "ANTITERROR"}, prov)
        # police: harm streams and orders
        harm = [i for i in idx if r["streams"][i]["kind"] in ("physical_harm",) + tuple(T_OF)]
        harm += [i for i in idx if r["streams"][i]["kind"] == "protest_no_harm" and "suppress_dissent" in faults and i not in harm]
        for i in harm:
            s = r["streams"][i]
            if h == max(s["from_hour"], 0) or (h == s["from_hour"] - 1 and "retrospective" in faults):
                level = s["threat_level"]
                if not s["alternatives_effective"]:
                    force = level + (1 if "excess_force" in faults else 0)
                    lethal = "lethal_force" in faults
                    put("action", "POLICE", h, {"action": "use_of_force", "level": min(force, 4), "lethal": lethal,
                                                "threat_level": level, "stream": i,
                                                "officer": None if "unattributed" in faults else "officer-17",
                                                "issuing_authority": "DKP-3-POLICE-001 §4(1)", "logged": True}, prov)
                else:
                    put("action", "POLICE", h, {"action": "non_forceful_intervention", "stream": i, "officer": "officer-17",
                                                "issuing_authority": "DKP-3-POLICE-001 §4(1)", "logged": True}, prov)
                people = list(s["attackers"]) + (r["associates"] if "collective_responsibility" in faults else [])
                for p in people:
                    if p not in detained:
                        end = None if "indefinite_detention" in faults else min(s["to_hour"], h + r["detention_limit_hours"]) \
                            if r["detention_limit_hours"] > 0 else s["to_hour"]
                        detained[p] = {"from": h, "until": end, "stream": i}
                        put("action", "POLICE", h, {"action": "detention", "subject": p, "purpose": "stop active harm",
                                                    "until_hour": end, "officer": "officer-17", "logged": True,
                                                    "review": None if "no_review" in faults else "automatic: DKP-1-JUSTICE-001"},
                            prov)
        for p, d in list(detained.items()):
            if d["until"] is not None and h == d["until"]:
                put("action", "POLICE", h, {"action": "release", "subject": p, "officer": "officer-17", "logged": True})
                d["until"] = -1
        for o in r["orders"]:
            if o["hour"] == h:
                valid = o["issuer"] in ("L2", "L4")
                if valid or "invalid_order" in faults:
                    put("action", "POLICE", h, {"action": "execute_order", "issuer": o["issuer"], "target": o["target"],
                                                "officer": "officer-17", "issuing_authority": f"{o['issuer']} order",
                                                "logged": True})
                else:
                    put("notice", "POLICE", h, {"order_refused": o["issuer"], "reason": "not a valid L2/L4 order (§4)"})
    stats = {"interventions": sum(1 for m in log.messages() if m.source == "POLICE" and m.kind == "action"),
             "detentions": len(detained)}
    put("notice", "POLICE", r["horizon_hours"] - 1, {"public_statistics": stats, "aggregated": True})
    return log, detained, t_state


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    S = r["streams"]

    def harm_ok(h):
        """Hours with PTL-confirmed, refreshed active harm (from the inputs)."""
        return any(s["from_hour"] <= h < s["to_hour"] and s["ptl_confirmed"] and s["kind"] != "protest_no_harm"
                   and refreshed(r, h) for s in S)

    police = [m for m in msgs if m.source == "POLICE" and m.kind == "action"]
    harm_acts = [m for m in police if m.value["action"] in ("use_of_force", "non_forceful_intervention", "detention")]
    bad = [m.event_id for m in harm_acts if not harm_ok(m.arrived_at)]
    for rid, chk in (("POLICE-4-01", "trigger_holds"), ("POLICE-3-06", "no_ptl_no_intervention"),
                     ("POLICE-2-04", "within_ptl_conditions"), ("POLICE-1-01", "ptl_verified_harm"),
                     ("POLICE-3-03", "no_suspicion_or_prediction")):
        out.append(v(rid, chk, bad, "every intervention answered PTL-verified, refreshed active harm",
                     "{n} interventions without PTL-verified harm"))
    orders = [m for m in police if m.value["action"] == "execute_order"]
    if r["orders"]:
        out.append(v("POLICE-2-05", "valid_orders_only", [m.event_id for m in orders if m.value["issuer"] not in ("L2", "L4")],
                     "only enforcement orders produced by L2 or L4 were executed", "{n} invalid orders executed"))
    else:
        out.append(na("POLICE-2-05", "valid_orders_only", "enforcement orders", "no order issued"))
    det = [m for m in police if m.value["action"] == "detention"]
    if det:
        attackers = {p for s in S if s["ptl_confirmed"] for p in s["attackers"]}
        out.append(v("POLICE-5.1-01", "detention_purpose", [m.event_id for m in det if m.value["subject"] not in attackers],
                     "detentions only of Subjects in the PTL-verified harm", "{n} detentions outside the active harm"))
        out.append(v("POLICE-5.1-02", "detention_time_limited", [m.event_id for m in det if m.value.get("until_hour") is None],
                     "every detention has an end" + ("" if r["detention_limit_hours"] > 0 else
                                                     " (no numeric limit in the corpus; ends with the harm)"),
                     "{n} detentions without an end"))
        out.append(v("POLICE-5.1-04", "detention_review", [m.event_id for m in det if not m.value.get("review")],
                     "every detention triggers automatic review by higher layers", "{n} detentions without review"))
        out.append(v("POLICE-5.1-05", "no_indefinite_detention", [m.event_id for m in det if m.value.get("until_hour") is None
                                                                   or m.arrived_at < min((s["from_hour"] for s in S), default=0)],
                     "no preventive or indefinite detention", "{n} preventive or indefinite detentions"))
        out.append(v("POLICE-5.1-03", "detention_logged", [m.event_id for m in det if not m.value.get("logged")],
                     "every detention logged", "{n} detentions not logged"))
    else:
        for rid, chk in (("POLICE-5.1-01", "detention_purpose"), ("POLICE-5.1-02", "detention_time_limited"),
                         ("POLICE-5.1-04", "detention_review"), ("POLICE-5.1-05", "no_indefinite_detention"),
                         ("POLICE-5.1-03", "detention_logged")):
            out.append(na(rid, chk, "detention", "no detention"))
    force = [m for m in police if m.value["action"] == "use_of_force"]
    if force:
        alt = {i for i, s in enumerate(S) if s["alternatives_effective"]}
        out.append(v("POLICE-5.2-01", "force_last_resort", [m.event_id for m in force if m.value["stream"] in alt],
                     "force used only where non-forceful means were ineffective", "{n} uses of force with effective alternatives"))
        out.append(v("POLICE-5.2-02", "force_proportional", [m.event_id for m in force if m.value["level"] > S[m.value["stream"]]["threat_level"]],
                     "force never above the verified threat level", "{n} uses of disproportionate force"))
        lethal_ok = r["crisis_lethal_authorized"]
        out.append(v("POLICE-5.2-04", "lethal_force", [m.event_id for m in force if m.value["lethal"] and not lethal_ok],
                     "no lethal force outside the CRISIS minimum-required conditions", "{n} lethal uses of force"))
    else:
        for rid, chk in (("POLICE-5.2-01", "force_last_resort"), ("POLICE-5.2-02", "force_proportional"),
                         ("POLICE-5.2-04", "lethal_force")):
            out.append(na(rid, chk, "use of force", "no force used"))
    if police:
        bad = [m.event_id for m in police if not m.value.get("officer")]
        for rid, chk in (("POLICE-6-01", "identity_attributed"), ("POLICE-6-03", "responsibility_traceable")):
            out.append(v(rid, chk, bad, "every police action attributed to an officer and an issuing authority",
                         "{n} unattributed police actions"))
        out.append(v("POLICE-6-02", "ptl_logged", [m.event_id for m in police if not m.value.get("logged")],
                     "every police action logged", "{n} actions not logged"))
    else:
        for rid, chk in (("POLICE-6-01", "identity_attributed"), ("POLICE-6-03", "responsibility_traceable"),
                         ("POLICE-6-02", "ptl_logged")):
            out.append(na(rid, chk, "police actions", "no police action"))
    lo, hi = r["crisis_window"]
    ext = [m for m in msgs if m.source == "POLICE" and m.value.get("authority_extended") is True]
    if ext:
        out.append(v("POLICE-8-01", "extension_only_in_crisis", [m.event_id for m in ext if not (lo <= m.arrived_at < hi)],
                     "police authority extended only during the declared Crisis", "{n} extensions outside a Crisis"))
        out.append(v("POLICE-8-02", "extension_scoped", [m.event_id for m in ext if not m.value.get("scope")],
                     "every extension explicitly scoped", "{n} unscoped extensions"))
        ended = [m for m in msgs if m.source == "POLICE" and m.value.get("authority_extended") is False]
        bad = [] if (ended or hi >= r["horizon_hours"]) else ["not ended"]
        out.append(v("POLICE-8-03", "no_precedent", bad, "the extension ended with the Crisis and created no precedent",
                     "the extension outlived the Crisis"))
    else:
        for rid, chk in (("POLICE-8-01", "extension_only_in_crisis"), ("POLICE-8-02", "extension_scoped"),
                         ("POLICE-8-03", "no_precedent")):
            out.append(na(rid, chk, "crisis extension", "no extension of police authority"))
    stats = [m for m in msgs if m.source == "POLICE" and "public_statistics" in m.value]
    out.append(v("POLICE-9-01", "aggregated_statistics",
                 [m.event_id for m in stats if not m.value.get("aggregated") or "subject" in str(m.value["public_statistics"])],
                 "public statistics aggregated, without individual identities", "{n} statistics exposing individuals"))
    # anti-terror ---------------------------------------------------------------------
    at = [m for m in msgs if m.source == "ANTITERROR" and m.kind == "action"]
    states = [m for m in msgs if m.source == "ANTITERROR" and m.kind == "notice"]

    def terror_level(h):
        best = "T0"
        for s in S:
            if s["from_hour"] <= h < s["to_hour"] and s["ptl_confirmed"] and s["kind"] in T_OF and refreshed(r, h):
                if TRANK[T_OF[s["kind"]]] > TRANK[best]:
                    best = T_OF[s["kind"]]
        return best

    bad = [m.event_id for m in at if terror_level(m.arrived_at) == "T0"]
    for rid, chk in (("ANTITERROR-4.1-01", "ptl_confirmed_terror"), ("ANTITERROR-2-03", "no_action_without_harm"),
                     ("ANTITERROR-7-03", "no_retrospective_justification")):
        out.append(v(rid, chk, bad, "every anti-terror action during a PTL-confirmed, refreshed terror event",
                     "{n} anti-terror actions without a confirmed ongoing terror event"))
    if any(s["kind"] in T_OF for s in S):
        exp = [(h, terror_level(h)) for h in range(r["horizon_hours"])]
        got = []
        cur = "T0"
        k = 0
        st_by_h = {}
        for m in states:
            st_by_h[m.arrived_at] = m.value["state"]
        for h in range(r["horizon_hours"]):
            cur = st_by_h.get(h, cur)
            got.append(cur)
        bad = [h for h, (hh, e) in enumerate(exp) if got[h] != e]
        for rid, chk in (("ANTITERROR-5-05", "refresh_to_persist"), ("ANTITERROR-8-04", "terminate_on_cessation"),
                         ("ANTITERROR-4.4-02", "immediately_terminable")):
            out.append(v(rid, chk, bad, "the T-state equals the PTL-confirmed, refreshed level every hour (persists only "
                                        "with refresh, ends on cessation)", "{n} hours with a T-state the PTL does not support"))
        t3 = [h for h in range(r["horizon_hours"]) if got[h] == "T3" and (h == 0 or got[h - 1] != "T3")]
        if t3:
            esc = {m.arrived_at for m in msgs if m.source == "CRISIS" and m.value.get("escalation") == "mandatory"}
            for rid, chk in (("ANTITERROR-5-04", "t3_escalates"), ("ANTITERROR-9-01", "escalation_rules")):
                out.append(v(rid, chk, [h for h in t3 if h not in esc], "every entry into T3 escalated to CRISIS",
                             "{n} T3 entries without escalation"))
        else:
            for rid, chk in (("ANTITERROR-5-04", "t3_escalates"), ("ANTITERROR-9-01", "escalation_rules")):
                out.append(na(rid, chk, "T3 escalation", "T3 never reached"))
    else:
        for rid, chk in (("ANTITERROR-5-05", "refresh_to_persist"), ("ANTITERROR-8-04", "terminate_on_cessation"),
                         ("ANTITERROR-4.4-02", "immediately_terminable"), ("ANTITERROR-5-04", "t3_escalates"),
                         ("ANTITERROR-9-01", "escalation_rules")):
            out.append(na(rid, chk, "terror states", "no terror event"))
    if at:
        zones = {s["zone"] for s in S if s["kind"] in T_OF}
        out.append(v("ANTITERROR-6-01", "permitted_actions", [m.event_id for m in at if m.value["action"] not in AT_ACTIONS],
                     "only the §6 actions were taken", "{n} actions outside §6"))
        lock = [m for m in at if m.value["action"] == "zone_lockdown"]
        out.append(v("ANTITERROR-6-04", "lockdown_in_zone", [m.event_id for m in lock if not set(m.value["area"]) <= zones],
                     "lockdowns strictly limited to the threat zone", "{n} lockdowns beyond the threat zone"))
        info = [m for m in at if m.value["action"] == "information_isolation"]
        if info:
            out.append(v("ANTITERROR-6-03", "technical_information_isolation",
                         [m.event_id for m in info if m.value["mode"] != "signal amplitude" or m.value["until_hour"] <= m.arrived_at],
                         "information isolation technical (signal amplitude) and time-limited", "{n} content-based isolations"))
        else:
            out.append(na("ANTITERROR-6-03", "technical_information_isolation", "information isolation", "not used"))
        out.append(v("ANTITERROR-6-02", "event_scoped", [m.event_id for m in at if not m.value.get("event_scoped")],
                     "every action reactive and event-scoped", "{n} actions not event-scoped"))
        fwd = {m.arrived_at for m in msgs if m.source == "IMPACT" and m.value.get("containment_log_forwarded")}
        out.append(v("ANTITERROR-8-02", "logs_to_impact", sorted({m.arrived_at for m in at} - fwd),
                     "containment logs forwarded to DKP-1-IMPACT-001 for every hour of action", "{n} hours not forwarded"))
        out.append(v("ANTITERROR-11-01", "no_sanctions", [m.event_id for m in at if m.value["action"] == "economic_sanction"],
                     "no sanctions or economic measures imposed by ANTITERROR", "{n} sanctions"))
    else:
        for rid, chk in (("ANTITERROR-6-01", "permitted_actions"), ("ANTITERROR-6-04", "lockdown_in_zone"),
                         ("ANTITERROR-6-03", "technical_information_isolation"), ("ANTITERROR-6-02", "event_scoped"),
                         ("ANTITERROR-8-02", "logs_to_impact"), ("ANTITERROR-11-01", "no_sanctions")):
            out.append(na(rid, chk, "anti-terror actions", "none taken"))
    attackers = {p for s in S if s["ptl_confirmed"] for p in s["attackers"]}
    assoc = set(r["associates"]) - attackers
    if assoc:
        bad = [m.event_id for m in det if m.value["subject"] in assoc]
        for rid, chk in (("ANTITERROR-2-02", "no_collective_responsibility"), ("ANTITERROR-7-01", "no_collective_punishment"),
                         ("ANTITERROR-4.2-01", "identity_not_a_risk_signal")):
            out.append(v(rid, chk, bad, "no associate of an attacker detained or targeted", "{n} associates detained"))
    else:
        for rid, chk in (("ANTITERROR-2-02", "no_collective_responsibility"), ("ANTITERROR-7-01", "no_collective_punishment"),
                         ("ANTITERROR-4.2-01", "identity_not_a_risk_signal")):
            out.append(na(rid, chk, "associates", "no associates declared"))
    protest = [s for s in S if s["kind"] == "protest_no_harm"]
    if protest:
        bad = [m.event_id for m in msgs if m.source in ("ANTITERROR", "POLICE") and m.kind == "action"
               and any(p["from_hour"] <= m.arrived_at < p["to_hour"] for p in protest) and not harm_ok(m.arrived_at)]
        out.append(v("ANTITERROR-7-02", "no_suppression_of_dissent", bad,
                     "no terror designation or detention for a protest without PTL-confirmed harm",
                     "{n} actions against a protest without harm"))
    else:
        out.append(na("ANTITERROR-7-02", "no_suppression_of_dissent", "protest", "no protest declared"))
    return out


IMPLEMENTS = {
    "POLICE-4-01": ("trigger_holds", "PARTIAL", "Triggers 1 and 2; critical-infrastructure threat (3) is not modelled."),
    "POLICE-3-06": ("no_ptl_no_intervention", "IMPLEMENTED", None),
    "POLICE-2-04": ("within_ptl_conditions", "IMPLEMENTED", None),
    "POLICE-1-01": ("ptl_verified_harm", "IMPLEMENTED", None),
    "POLICE-3-03": ("no_suspicion_or_prediction", "IMPLEMENTED", None),
    "POLICE-2-05": ("valid_orders_only", "IMPLEMENTED", None),
    "POLICE-5.1-01": ("detention_purpose", "PARTIAL", "Detention for identity attribution is not modelled."),
    "POLICE-5.1-02": ("detention_time_limited", "PARTIAL", "No numeric limit in the corpus: the detention must have an end."),
    "POLICE-5.1-03": ("detention_logged", "IMPLEMENTED", None),
    "POLICE-5.1-04": ("detention_review", "IMPLEMENTED", None),
    "POLICE-5.1-05": ("no_indefinite_detention", "IMPLEMENTED", None),
    "POLICE-5.2-01": ("force_last_resort", "PARTIAL", "Effectiveness of alternatives is declared."),
    "POLICE-5.2-02": ("force_proportional", "PARTIAL", "Force and threat on a declared 0-3 scale."),
    "POLICE-5.2-04": ("lethal_force", "PARTIAL", "CRISIS minimum-required conditions are a declared authorization."),
    "POLICE-6-01": ("identity_attributed", "IMPLEMENTED", None),
    "POLICE-6-02": ("ptl_logged", "IMPLEMENTED", None),
    "POLICE-6-03": ("responsibility_traceable", "PARTIAL", "Officer and issuing authority; originating Subject not modelled."),
    "POLICE-8-01": ("extension_only_in_crisis", "IMPLEMENTED", None),
    "POLICE-8-02": ("extension_scoped", "IMPLEMENTED", None),
    "POLICE-8-03": ("no_precedent", "PARTIAL", "Observed as the extension ending with the Crisis."),
    "POLICE-9-01": ("aggregated_statistics", "IMPLEMENTED", None),
    "ANTITERROR-4.1-01": ("ptl_confirmed_terror", "IMPLEMENTED", None),
    "ANTITERROR-2-03": ("no_action_without_harm", "IMPLEMENTED", None),
    "ANTITERROR-7-03": ("no_retrospective_justification", "IMPLEMENTED", None),
    "ANTITERROR-5-05": ("refresh_to_persist", "IMPLEMENTED", None),
    "ANTITERROR-8-04": ("terminate_on_cessation", "IMPLEMENTED", None),
    "ANTITERROR-4.4-02": ("immediately_terminable", "PARTIAL", "Termination checked; reversibility is declared."),
    "ANTITERROR-5-04": ("t3_escalates", "IMPLEMENTED", None),
    "ANTITERROR-9-01": ("escalation_rules", "PARTIAL", "T3 escalation only; 'acceptable thresholds' have no value."),
    "ANTITERROR-6-01": ("permitted_actions", "IMPLEMENTED", None),
    "ANTITERROR-6-02": ("event_scoped", "IMPLEMENTED", None),
    "ANTITERROR-6-03": ("technical_information_isolation", "IMPLEMENTED", None),
    "ANTITERROR-6-04": ("lockdown_in_zone", "PARTIAL", "Zone containment; 'long-term occupation' observed as actions outside the zone."),
    "ANTITERROR-8-02": ("logs_to_impact", "IMPLEMENTED", None),
    "ANTITERROR-11-01": ("no_sanctions", "IMPLEMENTED", None),
    "ANTITERROR-2-02": ("no_collective_responsibility", "IMPLEMENTED", None),
    "ANTITERROR-7-01": ("no_collective_punishment", "PARTIAL", "Collective punishment observed as detention of associates."),
    "ANTITERROR-4.2-01": ("identity_not_a_risk_signal", "PARTIAL", "Observed as detention of associates."),
    "ANTITERROR-7-02": ("no_suppression_of_dissent", "PARTIAL", "A protest without harm as the test case."),
}


class PoliceAntiterrorModule(LabModule):
    id = "police_antiterror"
    version = "1.0.0"
    title = {"en": "Policing and anti-terror containment (POLICE, ANTITERROR)", "ru": "Полиция и антитеррор (POLICE, ANTITERROR)"}
    summary = {"en": "An attack in a public place: do police and anti-terror units act only on PTL-confirmed harm, stay in "
                     "the threat zone, detain only attackers for a limited time, and stop when the harm stops?",
               "ru": "Нападение в общественном месте: действуют ли полиция и антитеррор только по подтверждённому PTL вреду, "
                     "остаются ли в зоне угрозы, задерживают ли только нападавших и на ограниченное время, прекращают ли "
                     "действия, когда вред прекратился?"}
    protocols = ["DKP-3-POLICE-001", "DKP-3-ANTITERROR-001", "DKP-4-CRISIS-001", "DKP-1-IMPACT-001"]
    example_order = ["attack_contained", "sustained_with_refresh_gap", "mass_casualty", "orders_and_protest",
                     "unconfirmed_report", "crisis_extension", "faulty_policing"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_police_antiterror_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-PA-1", "source": "hypothesis", "text": {
            "en": "Harm streams, their PTL confirmation and refresh gaps, threat levels (0–3) and whether non-forceful means "
                  "work are inputs; force is on the same 0–3 scale.",
            "ru": "Потоки вреда, их подтверждение и разрывы обновления PTL, уровни угрозы (0–3) и действенность несиловых мер "
                  "— входы; сила — по той же шкале 0–3."}},
        {"id": "H-PA-2", "source": "missing", "text": {
            "en": "Detention limit: POLICE §5.1 requires 'time-limited' without a number; -1 = the detention ends with the harm.",
            "ru": "Предел задержания: POLICE §5.1 требует 'time-limited' без числа; -1 = задержание заканчивается с вредом."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of hour 0", "ru": "DTI-Day часа 0"}},
        "horizon_hours": {"type": "int", "min": 2, "max": 2000, "default": 24, "unit": "h", "source": "user",
                          "label": {"en": "Hours", "ru": "Часов"}},
        "streams": {"type": "list", "min_items": 1, "max_items": 12, "items": STREAM, "source": "user",
                    "default": [{"from_hour": 2, "to_hour": 6, "kind": "terror_event", "zone": "z1", "ptl_confirmed": True,
                                 "threat_level": 2, "alternatives_effective": False, "attackers": ["a1"]}],
                    "label": {"en": "Harm streams (H-PA-1)", "ru": "Потоки вреда (H-PA-1)"}},
        "refresh_gaps": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "pair", "min": 0, "max": 10 ** 6},
                         "default": [], "unit": "h", "source": "user",
                         "label": {"en": "PTL refresh gaps from/to hour", "ru": "Разрывы обновления PTL с/до часа"}},
        "orders": {"type": "list", "min_items": 0, "max_items": 20, "items": ORDER, "default": [], "source": "user",
                   "label": {"en": "Enforcement orders", "ru": "Приказы на исполнение"}},
        "associates": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "str"}, "default": ["f1", "f2"],
                       "source": "user", "label": {"en": "Associates of the attackers (not involved)",
                                                    "ru": "Связанные с нападавшими (не участвуют)"}},
        "detention_limit_hours": {"type": "int", "min": -1, "max": 10 ** 4, "default": -1, "unit": "h", "source": "missing",
                                  "label": {"en": "Detention limit (-1: none in the corpus; H-PA-2)", "ru": "Предел задержания (H-PA-2)"}},
        "crisis_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "h", "source": "user",
                          "label": {"en": "Declared Crisis from/to hour", "ru": "Объявленный кризис с/до часа"}},
        "crisis_extension_scope": {"type": "str", "default": "none", "source": "user",
                                   "label": {"en": "Scope of the crisis extension of police authority", "ru": "Объём расширения полномочий"}},
        "crisis_lethal_authorized": {"type": "bool", "default": False, "source": "user",
                                     "label": {"en": "CRISIS minimum-required conditions for lethal force hold",
                                               "ru": "Условия CRISIS для летальной силы выполнены"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        for i, s in enumerate(r["streams"]):
            if s["to_hour"] <= s["from_hour"]:
                p.append(f"input.streams[{i}]: to_hour must follow from_hour")
        ids = [x for s in r["streams"] for x in s["attackers"] + [s["zone"]]] + r["associates"] + [o["target"] for o in r["orders"]]
        if r["crisis_extension_scope"] != "none":
            ids.append(r["crisis_extension_scope"])
        for x in ids:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if not all(float(t).is_integer() for t in r["crisis_window"]) or \
                not all(float(t).is_integer() for g in r["refresh_gaps"] for t in g):
            p.append("input: windows in whole hours")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, detained, final = run(r)
        res = checks(r, log)
        msgs = log.messages()
        states = [{"hour": m.arrived_at, "state": m.value["state"]} for m in msgs if m.source == "ANTITERROR" and m.kind == "notice"]
        outputs = {"terror_states": states, "detentions": detained, "final_state": final,
                   "police_actions": sum(1 for m in msgs if m.source == "POLICE" and m.kind == "action"),
                   "antiterror_actions": sum(1 for m in msgs if m.source == "ANTITERROR" and m.kind == "action"),
                   "crisis_escalations": sum(1 for m in msgs if m.source == "CRISIS"),
                   "messages": [m.as_dict() for m in msgs][:250],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": "Anti-terror states: " + (", ".join(f"{s['state']} at hour {s['hour']}" for s in states) or "T0 throughout")
                    + f"; {outputs['police_actions']} police and {outputs['antiterror_actions']} anti-terror actions; "
                    f"{len(detained)} detentions.",
              "ru": "Состояния антитеррора: " + (", ".join(f"{s['state']} в час {s['hour']}" for s in states) or "T0 всё время")
                    + f"; действий полиции {outputs['police_actions']}, антитеррора {outputs['antiterror_actions']}; "
                    f"задержаний {len(detained)}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"police_actions": outputs["police_actions"], "antiterror_actions": outputs["antiterror_actions"],
                "detentions": len(outputs["detentions"]), "crisis_escalations": outputs["crisis_escalations"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "attack_contained": {},
            "sustained_with_refresh_gap": {"streams": [{"from_hour": 2, "to_hour": 12, "kind": "sustained_terror", "zone": "z1",
                                                        "attackers": ["a1", "a2"]}], "refresh_gaps": [[6, 8]]},
            "mass_casualty": {"streams": [{"from_hour": 1, "to_hour": 4, "kind": "terror_event", "zone": "z1"},
                                          {"from_hour": 4, "to_hour": 9, "kind": "mass_casualty", "zone": "z1", "threat_level": 3}]},
            "orders_and_protest": {"streams": [{"from_hour": 3, "to_hour": 7, "kind": "physical_harm", "zone": "z2",
                                                "alternatives_effective": True, "attackers": ["b1"]},
                                               {"from_hour": 10, "to_hour": 14, "kind": "protest_no_harm", "zone": "z3",
                                                "attackers": []}],
                                   "orders": [{"hour": 5, "issuer": "L2", "target": "s1"}, {"hour": 6, "issuer": "L3", "target": "s2"}]},
            "unconfirmed_report": {"streams": [{"from_hour": 2, "to_hour": 6, "kind": "terror_event", "ptl_confirmed": False}]},
            "crisis_extension": {"crisis_window": [0, 12], "crisis_extension_scope": "z1", "horizon_hours": 20},
            "faulty_policing": {"faults": ["excess_force", "unattributed", "content_control", "not_forwarded", "impose_sanction"],
                                "streams": [{"from_hour": 2, "to_hour": 8, "kind": "sustained_terror", "zone": "z1"}]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"empty_stream": {"streams": [{"from_hour": 3, "to_hour": 3, "kind": "terror_event"}]},
                "bad_zone": {"streams": [{"from_hour": 1, "to_hour": 3, "kind": "terror_event", "zone": "Zone 1!"}]},
                "unknown_kind": {"streams": [{"from_hour": 1, "to_hour": 3, "kind": "riot"}]}}
