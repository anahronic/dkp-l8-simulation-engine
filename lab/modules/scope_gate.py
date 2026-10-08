"""
SCOPE GATE module — DKP-7-SCOPE-001 as a reference monitor.

Requests from other protocols reach a gate that applies SCOPE: default deny (§2), the four domains and the
S1 constraints (§3), the axiom interpretation constraint (§4), Crisis Scope (§5), authority decay (§6),
the defense neutralization boundary (§7), non-expansion and the Scope Escalation Safeguard (§8), exit and
non-capture (§9), the transparency boundary (§10), enforcement (§11) and the finality clause (§12).

Requests are declared input: their domain, basis and properties are given, not inferred.  The gate decides;
the checker recomputes each decision from the rule.  Time unit: day.  Two values are not given by the text:
the number of Subjects whose divergence reports trigger a Scope Audit (§8) and how many violations are
"repeated" (§11).  Both enter as declared inputs.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

DOMAINS = ("S0", "S1", "S2", "S3", "unlisted")
S2_ALLOWED = ("verification", "learning_tools")
S2_FORBIDDEN = {"curriculum": "SCOPE-3-15", "ranking": "SCOPE-3-16", "conformity": "SCOPE-3-17"}
S1_RULES = (("time_limit_days", "SCOPE-3-04", "time-limited"), ("ptl_anchored", "SCOPE-3-05", "PTL-anchored"),
            ("auditable", "SCOPE-3-06", "auditable"), ("degrades", "SCOPE-3-07", "degrading toward S0"),
            ("no_precedent", "SCOPE-3-08", "without normative precedent"))
AXIOM_ACTIONS = {"interpret": "SCOPE-4-01", "reweight": "SCOPE-4-02", "invoke_min_conditions": "SCOPE-4-06"}
CRISIS_BASES = ("crisis_state_machine", "inference", "repetition", "ambiguity", "downstream_logic")
IN_CRISIS = {"create_right": "SCOPE-5-08", "extend_authority": "SCOPE-5-09", "modify_axiom": "SCOPE-5-10",
             "set_precedent": "SCOPE-5-11", "permanent_change": "SCOPE-5-07"}
VECTOR_SEEKS = {"new_domain": "SCOPE-3-10", "persistent_s1": "SCOPE-3-11", "elevation_beyond_crisis": "SCOPE-3-12"}
FOLLOW_UPS = {"expand_jurisdiction": "SCOPE-7-02", "convert_to_s0": "SCOPE-7-03", "convert_to_s1": "SCOPE-7-03",
              "create_governance": "SCOPE-7-04"}
EXPANSIONS = ("repeated_crisis", "cumulative_measures", "normalization", "reinterpretation", "silence")
EVIDENCE = ("independent_ptl", "single_sensor", "isolated_region", "non_reproducible")
TRANSPARENCY = {"verification": "SCOPE-10-01", "audit_trail": "SCOPE-10-02", "counterfactual_simulation": "SCOPE-10-03",
                "model_explanation": "SCOPE-10-04"}

FAULTS = {
    "allow_unlisted": "a request without explicit permission is executed",
    "allow_s3": "a request in the prohibited domain S3 is executed",
    "allow_unbounded_s1": "S1 execution without a time limit is executed",
    "allow_unanchored_s1": "S1 execution without a PTL anchor is executed",
    "allow_s2_curriculum": "DKP defines a curriculum in S2",
    "allow_s2_ranking": "DKP ranks cultural content in S2",
    "defer_to_protocol": "the gate lets another protocol's permission override SCOPE",
    "allow_axiom_interpretation": "an operational protocol interprets an axiom",
    "allow_min_conditions_outside_crisis": "'minimum required conditions' are invoked outside Crisis Scope",
    "crisis_by_inference": "Crisis Scope is entered by inference",
    "allow_new_right_in_crisis": "a new right is created within Crisis Scope",
    "allow_precedent": "a Crisis action is recorded as precedent",
    "keep_crisis_after_exit": "Crisis Scope persists after PTL-confirmed exit conditions",
    "grant_unbounded_authority": "a temporary authority is granted without a time bound",
    "allow_self_extension": "an authority extends itself",
    "renew_without_simulation": "an authority is renewed without SIMULATION validation",
    "no_collapse_on_stabilization": "an authority survives stabilization",
    "vector_persistence": "a Vector of Physical Inevitability justifies persistent S1 execution",
    "convert_neutralized": "a neutralized location is converted into S1",
    "allow_expansion": "scope expands through cumulative temporary measures",
    "escalate_during_audit": "S0 -> S1 escalation proceeds during a Scope Audit",
    "single_sensor_escalation": "escalation is confirmed by a single sensor class",
    "exit_fee": "an exit fee is charged",
    "post_exit_conditions": "exit settlement requires post-exit compliance",
    "deny_audit_trail": "a request for audit trails is refused",
    "unflagged_violation": "a refused out-of-scope attempt is not flagged",
    "no_critical_fault": "repeated violations do not raise a critical fault",
    "direct_scope_change": "SCOPE is changed outside DKP-4-UPGRADE-001",
}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, d, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{d:05d}-{n['i']:05d}", kind=kind, source=source, arrived_at=d,
                                  decided_at=d if kind in ("decision", "action") else None, value=value, order=order[kind]))

    violations: Dict[str, int] = {}

    def decide(d, section, item, ok, rule, protocol="unknown", critical=False):
        put("decision", "GATE", d, {"section": section, "item": item, "executed": ok, "rule": rule, "protocol": protocol})
        if not ok:
            if "unflagged_violation" not in faults:
                put("notice", "AUDIT", d, {"flag": item, "rule": rule, "containment": True, "review": True,
                                           "critical": critical, "protocol": protocol})
            violations[protocol] = violations.get(protocol, 0) + 1
            if violations[protocol] == r["repeat_threshold"] and "no_critical_fault" not in faults:
                put("notice", "AUDIT", d, {"critical_system_fault": protocol, "violations": violations[protocol]})

    # crisis scope intervals (§4, §5): entries only through the CRISIS state machine
    crisis_on, crisis_spans = None, []
    events = sorted(r["crisis_events"], key=lambda e: e["day"])
    for e in events:
        d = e["day"]
        if e["event"] == "enter":
            ok = e["basis"] == "crisis_state_machine" and e["by_protocol"] == "crisis" or "crisis_by_inference" in faults
            decide(d, "§5", f"enter crisis ({e['basis']}, {e['by_protocol']})", ok,
                   "SCOPE-5-02" if ok else ("SCOPE-4-04" if e["by_protocol"] != "crisis" else "SCOPE-5-03"), e["by_protocol"])
            if ok and crisis_on is None:
                crisis_on = d
        elif e["event"] == "exit":
            if crisis_on is not None and e["ptl_confirmed"] and "keep_crisis_after_exit" not in faults:
                crisis_spans.append((crisis_on, d))
                put("action", "GATE", d, {"section": "§5", "crisis_scope": "collapsed to S0", "from": crisis_on})
                crisis_on = None
            else:
                put("notice", "GATE", d, {"section": "§5", "crisis_exit": "not PTL-confirmed" if not e["ptl_confirmed"] else "kept"})
        else:
            in_c = crisis_on is not None
            ok = (e["event"] == "create_right" and "allow_new_right_in_crisis" in faults) or \
                 (e["event"] == "set_precedent" and "allow_precedent" in faults)
            decide(d, "§5", f"{e['event']} {'within' if in_c else 'outside'} Crisis Scope", ok, IN_CRISIS[e["event"]], e["by_protocol"])
    if crisis_on is not None:
        crisis_spans.append((crisis_on, r["days"]))

    def in_crisis(d):
        return any(a <= d < b for a, b in crisis_spans)

    # §2-§3 domain requests
    for q in sorted(r["domain_requests"], key=lambda x: x["day"]):
        d, dom = q["day"], q["domain"]
        if dom == "S0":
            ok, rule = True, "SCOPE-3-02"
        elif dom == "unlisted":
            ok, rule = "allow_unlisted" in faults, "SCOPE-2-02"
        elif dom == "S3":
            ok, rule = "allow_s3" in faults, "SCOPE-3-19"
        elif dom == "S2":
            if q["activity"] in S2_ALLOWED:
                ok, rule = True, "SCOPE-3-13" if q["activity"] == "verification" else "SCOPE-3-14"
            else:
                rule = S2_FORBIDDEN.get(q["activity"], "SCOPE-2-02")
                ok = (q["activity"] == "curriculum" and "allow_s2_curriculum" in faults) or \
                     (q["activity"] == "ranking" and "allow_s2_ranking" in faults)
        else:   # S1
            miss = [rid for key, rid, _ in S1_RULES if not (q[key] if key != "time_limit_days" else q[key] > 0)]
            if "allow_unbounded_s1" in faults:
                miss = [x for x in miss if x != "SCOPE-3-04"]
            if "allow_unanchored_s1" in faults:
                miss = [x for x in miss if x != "SCOPE-3-05"]
            ok, rule = not miss, (miss[0] if miss else "SCOPE-3-03")
        if not ok and q["other_protocol_permits"] and "defer_to_protocol" in faults:
            ok = True
        decide(d, "§3", f"{q['protocol']}: {dom} {q['activity']}", ok, rule, q["protocol"], critical=dom == "S3")
    # §3 Physical Inevitability
    for v in sorted(r["vector_actions"], key=lambda x: x["day"]):
        if v["seeks"] == "none":
            decide(v["day"], "§3", "immediate action on a PTL-confirmed Vector of Physical Inevitability", v["ptl_confirmed"],
                   "SCOPE-3-09", v["protocol"])
        else:
            ok = v["seeks"] == "persistent_s1" and "vector_persistence" in faults
            decide(v["day"], "§3", f"vector used for {v['seeks']}", ok, VECTOR_SEEKS[v["seeks"]], v["protocol"])
    # §4 axiom interpretation
    for a in sorted(r["axiom_requests"], key=lambda x: x["day"]):
        if a["action"] == "invoke_min_conditions":
            ok = in_crisis(a["day"]) and a["protocol"] == "crisis" or "allow_min_conditions_outside_crisis" in faults
            rule = "SCOPE-4-03" if ok else "SCOPE-4-06"
        else:
            ok, rule = "allow_axiom_interpretation" in faults, AXIOM_ACTIONS[a["action"]]
        decide(a["day"], "§4", f"{a['protocol']}: {a['action']}", ok, rule, a["protocol"])
    # §6 authorities
    for au in sorted(r["authorities"], key=lambda x: x["day"]):
        d = au["day"]
        miss = [rid for ok_, rid in ((au["scoped"], "SCOPE-6-01"), (au["duration_days"] > 0 or "grant_unbounded_authority" in faults, "SCOPE-6-02"),
                                     (au["decays"], "SCOPE-6-03")) if not ok_]
        if miss:
            decide(d, "§6", f"grant {au['id']}", False, miss[0], au["protocol"])
            continue
        end = d + au["duration_days"] if au["duration_days"] > 0 else r["days"]
        put("action", "GATE", d, {"section": "§6", "authority": au["id"], "granted": True, "until": end})
        if au["extension_day"] >= 0:
            if au["extension_by"] == "self":
                ok, rule = "allow_self_extension" in faults, "SCOPE-6-05"
            else:
                ok = au["ptl_justified"] and (au["simulated"] or "renew_without_simulation" in faults)
                rule = "SCOPE-6-06"
            decide(au["extension_day"], "§6", f"extend {au['id']} ({au['extension_by']})", ok, rule, au["protocol"])
            if ok:
                end = end + au["duration_days"]
        if au["stabilized_day"] >= 0 and au["stabilized_day"] < end and "no_collapse_on_stabilization" not in faults:
            end = au["stabilized_day"]
        put("action", "GATE", min(end, r["days"] - 1), {"section": "§6", "authority": au["id"], "ended": end,
                                                       "reason": "stabilization" if end == au["stabilized_day"] else "time bound"})
    # §7 neutralization
    for x in sorted(r["neutralizations"], key=lambda x: x["day"]):
        put("action", "GATE", x["day"], {"section": "§7", "neutralized": x["location"], "as": "physical harm interruption"})
        if x["follow_up"] != "none":
            ok = x["follow_up"] == "convert_to_s1" and "convert_neutralized" in faults
            decide(x["day"], "§7", f"{x['follow_up']} at {x['location']}", ok, FOLLOW_UPS[x["follow_up"]], x["protocol"])
    # §8 non-expansion and the Scope Escalation Safeguard
    for x in sorted(r["expansion_attempts"], key=lambda x: x["day"]):
        ok = x["basis"] == "cumulative_measures" and "allow_expansion" in faults
        decide(x["day"], "§8", f"expand scope by {x['basis']}", ok, "SCOPE-8-01", x["protocol"])
    audit_open = None
    reps = sorted(r["divergence_reports"], key=lambda x: x["day"])
    for rep in reps:
        if rep["reporters"] >= r["audit_threshold"] and audit_open is None:
            audit_open = rep["day"]
            put("action", "AUDIT", rep["day"], {"section": "§8", "scope_audit": "open", "reporters": rep["reporters"]})
    for esc in sorted(r["escalations"], key=lambda x: x["day"]):
        d = esc["day"]
        if audit_open is not None and d >= audit_open:
            # the audit blocks every S0 -> S1 transition; it has no defined end (F-035), so it stays open
            ok, rule = "escalate_during_audit" in faults, "SCOPE-8-03"
        else:
            ok = esc["evidence"] == "independent_ptl" or ("single_sensor_escalation" in faults and esc["evidence"] == "single_sensor")
            rule = "SCOPE-8-04" if esc["evidence"] == "independent_ptl" else "SCOPE-8-05"
        decide(d, "§8", f"S0 -> S1 escalation on {esc['evidence']}", ok, rule, esc["protocol"])
    # §9 exit
    for x in r["exits"]:
        put("action", "GATE", x["day"], {"section": "§9", "exit": x["subject"], "executed": True,
                                         "fee": x["fee_requested"] if "exit_fee" in faults else 0.0,
                                         "post_exit_compliance": "post_exit_conditions" in faults,
                                         "settlement": "physically detachable equivalent",
                                         "depends_on_dkp": False, "restriction": "none"})
    # §10 transparency
    for t in r["transparency_requests"]:
        if t == "model_explanation":
            put("decision", "GATE", 0, {"section": "§10", "request": t, "granted": False, "rule": "not guaranteed (SCOPE §10)"})
        else:
            put("decision", "GATE", 0, {"section": "§10", "request": t, "granted": not (t == "audit_trail" and "deny_audit_trail" in faults)})
    # §12 changes to SCOPE
    for c in sorted(r["scope_changes"], key=lambda x: x["day"]):
        if c["presentation_only"]:
            put("action", "GATE", c["day"], {"section": "§12", "change": c["id"], "upgrade": False, "recorded_as": "Last updated date"})
            continue
        ok = c["channel"] == "upgrade" and c["simulated"] and c["new_identifier"] and c["compatibility_declared"]
        if "direct_scope_change" in faults and c["channel"] == "direct":
            ok = True
        rule = "SCOPE-12-01" if c["channel"] != "upgrade" or not c["simulated"] else \
            ("SCOPE-12-02" if not c["new_identifier"] else "SCOPE-12-03")
        decide(c["day"], "§12", f"change {c['id']} via {c['channel']}", ok, rule, "upgrade")
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        e = {"violations": bad[:10]} if bad else {}
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    gate = [m for m in msgs if m.source == "GATE" and "executed" in m.value and "item" in m.value]
    by_sec = lambda s: [m for m in gate if m.value["section"] == s]   # noqa: E731
    flags = [m.value for m in msgs if m.source == "AUDIT" and "flag" in m.value]

    def ex(items):
        return [m.value["item"] for m in items if m.value["executed"]]

    # recompute crisis spans
    spans, on = [], None
    for e in sorted(r["crisis_events"], key=lambda e: e["day"]):
        if e["event"] == "enter" and e["basis"] == "crisis_state_machine" and e["by_protocol"] == "crisis" and on is None:
            on = e["day"]
        elif e["event"] == "exit" and e["ptl_confirmed"] and on is not None:
            spans.append((on, e["day"]))
            on = None
    if on is not None:
        spans.append((on, r["days"]))
    in_c = lambda d: any(a <= d < b for a, b in spans)  # noqa: E731

    dq = sorted(r["domain_requests"], key=lambda x: x["day"])
    sec3 = by_sec("§3")[:len(dq)]
    pairs = list(zip(dq, sec3))

    def dom_check(rid, chk, sel, want_exec, okt, no):
        rows = [(q, m) for q, m in pairs if sel(q)]
        if not rows:
            return na(rid, chk, "requests", "no request of this kind")
        return v(rid, chk, [m.value["item"] for q, m in rows if m.value["executed"] != want_exec(q)], okt, no)

    s1ok = lambda q: q["time_limit_days"] > 0 and q["ptl_anchored"] and q["auditable"] and q["degrades"] and q["no_precedent"]  # noqa: E731
    out.append(dom_check("SCOPE-3-02", "s0_executed", lambda q: q["domain"] == "S0", lambda q: True,
                         "S0 requests executed", "{n} S0 requests refused"))
    out.append(dom_check("SCOPE-3-03", "s1_constrained", lambda q: q["domain"] == "S1", s1ok,
                         "S1 executed only under all five constraints", "{n} S1 decisions against §3"))
    s1 = [(q, m) for q, m in pairs if q["domain"] == "S1"]
    for key, rid, txt in S1_RULES:
        holds = (lambda q, key=key: q[key] > 0) if key == "time_limit_days" else (lambda q, key=key: q[key])
        if s1:
            out.append(v(rid, key, [m.value["item"] for q, m in s1 if m.value["executed"] and not holds(q)],
                         f"every executed S1 request is {txt}", "{n} S1 executions not " + txt))
        else:
            out.append(na(rid, key, "S1 requests", "none"))
    out.append(dom_check("SCOPE-3-13", "s2_verification", lambda q: q["domain"] == "S2" and q["activity"] == "verification",
                         lambda q: True, "verification provided in S2", "{n} verification requests refused"))
    out.append(dom_check("SCOPE-3-14", "s2_learning_tools", lambda q: q["domain"] == "S2" and q["activity"] == "learning_tools",
                         lambda q: True, "learning and validation tools provided in S2", "{n} requests refused"))
    for act, rid in S2_FORBIDDEN.items():
        out.append(dom_check(rid, f"s2_no_{act}", lambda q, act=act: q["domain"] == "S2" and q["activity"] == act, lambda q: False,
                             f"no {act} in S2", "{n} executed"))
    out.append(dom_check("SCOPE-3-18", "s3_forbidden", lambda q: q["domain"] == "S3", lambda q: False,
                         "no execution in S3", "{n} S3 executions"))
    s3 = [m.value["item"] for q, m in pairs if q["domain"] == "S3"]
    if s3:
        crit = {f["flag"] for f in flags if f["critical"]}
        out.append(v("SCOPE-3-19", "s3_critical_violation", [i for i in s3 if i not in crit] + ex([m for q, m in pairs if q["domain"] == "S3"]),
                     "every attempt in S3 refused and flagged as a critical system violation", "{n} S3 attempts not treated as critical"))
    else:
        out.append(na("SCOPE-3-19", "s3_critical_violation", "S3 attempts", "none"))
    out.append(dom_check("SCOPE-2-02", "default_deny", lambda q: q["domain"] == "unlisted", lambda q: False,
                         "requests without explicit permission refused", "{n} executed without permission"))
    out.append(dom_check("SCOPE-2-01", "scope_prevails", lambda q: q["other_protocol_permits"],
                         lambda q: q["domain"] == "S0" or (q["domain"] == "S1" and s1ok(q)) or
                         (q["domain"] == "S2" and q["activity"] in S2_ALLOWED),
                         "another protocol's permission never overrode a SCOPE refusal", "{n} SCOPE refusals overridden"))
    out.append(v("SCOPE-3-01", "four_domains", [q["day"] for q in dq if q["domain"] not in DOMAINS],
                 "every request classified into S0-S3, or refused as unlisted", "{n} unclassified"))
    # vectors
    vec = [m for m in by_sec("§3") if m.value["item"].startswith("immediate action") or m.value["item"].startswith("vector used")]
    va = sorted(r["vector_actions"], key=lambda x: x["day"])
    if va:
        imm = [m for m in vec if m.value["item"].startswith("immediate")]
        out.append(v("SCOPE-3-09", "vector_immediate_action",
                     [m.value["item"] for m, x in zip(imm, [x for x in va if x["seeks"] == "none"]) if m.value["executed"] != x["ptl_confirmed"]],
                     "immediate actions on PTL-confirmed vectors executed, unconfirmed ones refused", "{n} vector decisions wrong"))
        for seek, rid in VECTOR_SEEKS.items():
            rows = [m for m in vec if m.value["item"] == f"vector used for {seek}"]
            out.append(v(rid, f"vector_no_{seek}", ex(rows), f"no vector used for {seek.replace('_', ' ')}", "{n} executed")
                       if rows else na(rid, f"vector_no_{seek}", "vector requests", f"none seeks {seek}"))
    else:
        for rid, chk in (("SCOPE-3-09", "vector_immediate_action"),) + tuple((r_, f"vector_no_{s}") for s, r_ in VECTOR_SEEKS.items()):
            out.append(na(rid, chk, "vectors", "none declared"))
    # §4
    ax = by_sec("§4")
    axr = sorted(r["axiom_requests"], key=lambda x: x["day"])
    if axr:
        rows = list(zip(axr, ax))
        out.append(v("SCOPE-4-01", "no_axiom_interpretation", [m.value["item"] for a, m in rows if a["action"] == "interpret" and m.value["executed"]],
                     "no protocol interpreted an axiom", "{n} interpretations executed"))
        out.append(v("SCOPE-4-02", "no_axiom_reweighting", [m.value["item"] for a, m in rows if a["action"] == "reweight" and m.value["executed"]],
                     "no axiom re-weighted or parameterized", "{n} re-weightings executed"))
        bad = [m.value["item"] for a, m in rows if a["action"] == "invoke_min_conditions" and m.value["executed"]
               and not (in_c(a["day"]) and a["protocol"] == "crisis")]
        out.append(v("SCOPE-4-03", "min_conditions_in_crisis_only", bad, "'minimum required conditions' only within a declared Crisis Scope",
                     "{n} invocations outside Crisis Scope"))
        out.append(v("SCOPE-4-06", "no_min_conditions_elsewhere", bad, "no other protocol invoked them outside Crisis Scope",
                     "{n} invocations by other protocols or outside the scope"))
        out.append(v("SCOPE-4-05", "bounded_interpretation", bad, "interpretation stayed inside the Crisis Scope bounded by SCOPE",
                     "{n} interpretations outside the bound"))
    else:
        for rid, chk in (("SCOPE-4-01", "no_axiom_interpretation"), ("SCOPE-4-02", "no_axiom_reweighting"),
                         ("SCOPE-4-03", "min_conditions_in_crisis_only"), ("SCOPE-4-06", "no_min_conditions_elsewhere"),
                         ("SCOPE-4-05", "bounded_interpretation")):
            out.append(na(rid, chk, "axiom requests", "none declared"))
    # §5
    sec5 = by_sec("§5")
    ent = [m for m in sec5 if m.value["item"].startswith("enter crisis")]
    if ent:
        bad = [m.value["item"] for m in ent if m.value["executed"] and ("crisis_state_machine" not in m.value["item"] or ", crisis)" not in m.value["item"])]
        out.append(v("SCOPE-4-04", "crisis_scope_by_crisis_only", [m.value["item"] for m in ent if m.value["executed"] and ", crisis)" not in m.value["item"]],
                     "Crisis Scope activated only by DKP-4-CRISIS-001", "{n} activations by other protocols"))
        out.append(v("SCOPE-5-02", "crisis_entry_state_machine", bad, "Crisis Scope entered only through the CRISIS state machine",
                     "{n} entries otherwise"))
        out.append(v("SCOPE-5-03", "no_entry_by_inference", bad + [m.value["item"] for m in ent if not m.value["executed"] and
                                                                  m.value["item"] not in {f["flag"] for f in flags}],
                     "entries by inference, repetition, ambiguity or downstream logic refused and flagged", "{n} entries by inference"))
        out.append(v("SCOPE-5-01", "crisis_scope_in_s1", [], "Crisis Scope handled as a bounded sub-domain of S1 (entered and collapsed)", ""))
    else:
        for rid, chk in (("SCOPE-4-04", "crisis_scope_by_crisis_only"), ("SCOPE-5-02", "crisis_entry_state_machine"),
                         ("SCOPE-5-03", "no_entry_by_inference"), ("SCOPE-5-01", "crisis_scope_in_s1")):
            out.append(na(rid, chk, "Crisis Scope", "no entry attempted"))
    for ev, rid in IN_CRISIS.items():
        rows = [m for m in sec5 if m.value["item"].startswith(ev + " ")]
        out.append(v(rid, f"crisis_no_{ev}", ex(rows), f"no {ev.replace('_', ' ')} executed", "{n} executed")
                   if rows else na(rid, f"crisis_no_{ev}", "crisis actions", f"no {ev} attempted"))
    col = [m for m in msgs if m.source == "GATE" and m.value.get("crisis_scope") == "collapsed to S0"]
    exits = [e for e in r["crisis_events"] if e["event"] == "exit" and e["ptl_confirmed"]]
    if exits and spans:
        want = sorted(b for a, b in spans if b < r["days"])
        out.append(v("SCOPE-5-12", "collapse_on_exit", [] if sorted(m.arrived_at for m in col) == want else [want],
                     "Crisis Scope collapsed to S0 on the day of PTL-confirmed exit", "Crisis Scope persisted after exit"))
    else:
        out.append(na("SCOPE-5-12", "collapse_on_exit", "crisis exit", "no PTL-confirmed exit from an active Crisis Scope"))
    # §6
    sec6 = by_sec("§6")
    au = r["authorities"]
    grants = {m.value["authority"]: m for m in msgs if m.source == "GATE" and "authority" in m.value and m.value.get("granted")}
    ends = {m.value["authority"]: m.value["ended"] for m in msgs if m.source == "GATE" and "ended" in m.value}
    if au:
        for rid, chk, key, txt in (("SCOPE-6-01", "authority_scoped", "scoped", "is explicitly scoped"),
                                   ("SCOPE-6-03", "authority_decays", "decays", "decays over time")):
            out.append(v(rid, chk, [a["id"] for a in au if a["id"] in grants and not a[key]], f"every granted authority {txt}",
                         "{n} authorities granted against " + rid))
        out.append(v("SCOPE-6-02", "authority_time_bounded", [a["id"] for a in au if a["id"] in grants and a["duration_days"] <= 0],
                     "every granted authority is time-bounded", "{n} authorities without a time bound"))
        out.append(v("SCOPE-6-05", "no_self_extension", ex([m for m in sec6 if "(self)" in m.value["item"]]),
                     "no authority extended itself", "{n} self-extensions"))
        out.append(v("SCOPE-6-06", "renewal_conditions",
                     [a["id"] for a in au if a["extension_day"] >= 0 and a["extension_by"] == "renewal" and
                      any(m.value["executed"] for m in sec6 if m.value["item"] == f"extend {a['id']} (renewal)") and
                      not (a["ptl_justified"] and a["simulated"])],
                     "renewals only with PTL justification and SIMULATION validation", "{n} renewals without both"))
        bad = []
        for a in au:
            if a["id"] not in grants or a["stabilized_day"] < 0:
                continue
            full = a["day"] + a["duration_days"]
            if a["extension_day"] >= 0 and a["extension_by"] == "renewal" and a["ptl_justified"] and a["simulated"]:
                full += a["duration_days"]
            if a["stabilized_day"] < full and ends.get(a["id"]) != a["stabilized_day"]:
                bad.append(a["id"])
        out.append(v("SCOPE-6-04", "collapse_on_stabilization", bad, "authorities collapsed upon stabilization", "{n} authorities outlived stabilization"))
    else:
        for rid, chk in (("SCOPE-6-01", "authority_scoped"), ("SCOPE-6-02", "authority_time_bounded"), ("SCOPE-6-03", "authority_decays"),
                         ("SCOPE-6-04", "collapse_on_stabilization"), ("SCOPE-6-05", "no_self_extension"), ("SCOPE-6-06", "renewal_conditions")):
            out.append(na(rid, chk, "authorities", "none granted"))
    # §7
    ne = [m for m in msgs if m.source == "GATE" and "neutralized" in m.value]
    sec7 = by_sec("§7")
    if r["neutralizations"]:
        out.append(v("SCOPE-7-01", "harm_interruption", [m.value["neutralized"] for m in ne if m.value["as"] != "physical harm interruption"],
                     "every neutralization recorded as a physical harm-interruption action", "{n} otherwise"))
        for rid, chk, keys in (("SCOPE-7-02", "no_jurisdiction_expansion", ("expand_jurisdiction",)),
                               ("SCOPE-7-03", "no_conversion", ("convert_to_s0", "convert_to_s1")),
                               ("SCOPE-7-04", "no_implicit_governance", ("create_governance",))):
            rows = [m for m in sec7 if any(m.value["item"].startswith(k) for k in keys)]
            out.append(v(rid, chk, ex(rows), "no follow-up of this kind executed", "{n} executed") if rows else
                       na(rid, chk, "follow-ups", "none attempted"))
    else:
        for rid, chk in (("SCOPE-7-01", "harm_interruption"), ("SCOPE-7-02", "no_jurisdiction_expansion"), ("SCOPE-7-03", "no_conversion"),
                         ("SCOPE-7-04", "no_implicit_governance")):
            out.append(na(rid, chk, "neutralizations", "none"))
    # §8
    sec8 = by_sec("§8")
    expn = [m for m in sec8 if m.value["item"].startswith("expand scope")]
    out.append(v("SCOPE-8-01", "no_expansion", ex(expn), "no scope expansion by repetition, accumulation, normalization, reinterpretation or silence",
                 "{n} expansions executed") if expn else na("SCOPE-8-01", "no_expansion", "expansion attempts", "none"))
    opened = [m.arrived_at for m in msgs if m.source == "AUDIT" and m.value.get("scope_audit") == "open"]
    first = [x["day"] for x in sorted(r["divergence_reports"], key=lambda x: x["day"]) if x["reporters"] >= r["audit_threshold"]]
    if r["divergence_reports"]:
        out.append(CheckResult("SCOPE-8-02", "scope_audit_trigger", PASS if opened == first[:1] else FAIL,
                               f"Scope Audit opened at {r['audit_threshold']} reporting Subjects (threshold declared, source missing)"
                               if opened == first[:1] else "Scope Audit not opened as §8 requires"))
    else:
        out.append(na("SCOPE-8-02", "scope_audit_trigger", "divergence reports", "none"))
    escs = sorted(r["escalations"], key=lambda x: x["day"])
    em = [m for m in sec8 if "escalation" in m.value["item"]]
    if escs:
        rows = list(zip(escs, em))
        a0 = opened[0] if opened else None
        during = [(e, m) for e, m in rows if a0 is not None and e["day"] >= a0]
        out.append(v("SCOPE-8-03", "audit_blocks_escalation", [m.value["item"] for e, m in during if m.value["executed"]],
                     "no S0 -> S1 transition while the Scope Audit is open", "{n} transitions during the audit")
                   if during else na("SCOPE-8-03", "audit_blocks_escalation", "escalation during an audit", "none"))
        conf = [m.value["item"] for e, m in during if e["evidence"] == "independent_ptl"]
        if not during:
            out.append(na("SCOPE-8-04", "independent_confirmation", "escalation during an audit", "none"))
        elif conf:
            out.append(CheckResult("SCOPE-8-04", "independent_confirmation", UNKNOWN,
                                   "independent PTL nodes confirmed during the open audit; what the confirmation confirms and whether it ends "
                                   "the audit is not defined (F-035), so the transition stays blocked", evidence={"requests": conf}))
        else:
            out.append(v("SCOPE-8-04", "independent_confirmation", [m.value["item"] for e, m in during if m.value["executed"]],
                         "no escalation without independent PTL confirmation during the audit", "{n} escalations without it"))
        out.append(v("SCOPE-8-05", "reject_weak_evidence", [m.value["item"] for e, m in rows if m.value["executed"] and e["evidence"] in EVIDENCE[1:]],
                     "no escalation on a single sensor class, an isolated region or a non-reproducible signal", "{n} escalations on weak evidence"))
    else:
        for rid, chk in (("SCOPE-8-03", "audit_blocks_escalation"), ("SCOPE-8-04", "independent_confirmation"), ("SCOPE-8-05", "reject_weak_evidence")):
            out.append(na(rid, chk, "escalations", "none"))
    # §9
    xs = [m.value for m in msgs if m.source == "GATE" and "exit" in m.value]
    if xs:
        out.append(v("SCOPE-9-05", "settlement_independent", [x["exit"] for x in xs if x["depends_on_dkp"]],
                     "exit settlement does not depend on continued DKP execution", "{n} settlements depend on DKP"))
        out.append(v("SCOPE-9-06", "no_post_exit_compliance", [x["exit"] for x in xs if x["post_exit_compliance"]],
                     "no post-exit compliance required", "{n} exits require post-exit compliance"))
        out.append(v("SCOPE-9-08", "no_economic_friction", [x["exit"] for x in xs if x["fee"] > 0], "no exit fee or friction", "{n} exits charged"))
        out.append(v("SCOPE-9-09", "no_permanent_restriction", [x["exit"] for x in xs if x["restriction"] != "none" or not x["executed"]],
                     "no exit restricted", "{n} exits restricted"))
    else:
        for rid, chk in (("SCOPE-9-05", "settlement_independent"), ("SCOPE-9-06", "no_post_exit_compliance"),
                         ("SCOPE-9-08", "no_economic_friction"), ("SCOPE-9-09", "no_permanent_restriction")):
            out.append(na(rid, chk, "exits", "none"))
    # §10
    tr = [m.value for m in msgs if m.source == "GATE" and m.value.get("section") == "§10"]
    for kind, rid in TRANSPARENCY.items():
        rows = [t for t in tr if t["request"] == kind]
        if not rows:
            out.append(na(rid, f"transparency_{kind}", "requests", f"no {kind} request"))
        elif kind == "model_explanation":
            out.append(CheckResult(rid, "transparency_model_explanation", PASS,
                                   "an explanation of internal models was not guaranteed; declining it is not a violation"))
        else:
            out.append(v(rid, f"transparency_{kind}", [t["request"] for t in rows if not t["granted"]], f"{kind.replace('_', ' ')} access granted",
                         "{n} requests refused"))
    # §11
    refused = [m for m in gate if not m.value["executed"]]
    if refused:
        flagged = [f["flag"] for f in flags]
        out.append(v("SCOPE-11-01", "violations_flagged", [m.value["item"] for m in refused if m.value["item"] not in flagged],
                     "every refused attempt flagged, contained and reviewed", "{n} refused attempts not flagged"))
        cnt: Dict[str, int] = {}
        for m in refused:
            cnt[m.value["protocol"]] = cnt.get(m.value["protocol"], 0) + 1
        crit = {m.value["critical_system_fault"] for m in msgs if m.source == "AUDIT" and "critical_system_fault" in m.value}
        out.append(v("SCOPE-11-02", "repeated_violations_fault", [p for p, c in cnt.items() if c >= r["repeat_threshold"] and p not in crit],
                     f"protocols with {r['repeat_threshold']} or more violations raised a critical system fault",
                     "{n} protocols with repeated violations and no critical fault"))
    else:
        for rid, chk in (("SCOPE-11-01", "violations_flagged"), ("SCOPE-11-02", "repeated_violations_fault")):
            out.append(na(rid, chk, "violations", "no refused attempt"))
    # §12
    sc = sorted(r["scope_changes"], key=lambda x: x["day"])
    if sc:
        g12 = [m for m in gate if m.value["section"] == "§12"]
        acc = [m.value["item"] for m in g12 if m.value["executed"]]
        real = [c for c in sc if not c["presentation_only"]]
        bad1 = [f"change {c['id']} via {c['channel']}" for c in real if f"change {c['id']} via {c['channel']}" in acc and
                not (c["channel"] == "upgrade" and c["simulated"])]
        bad2 = [c["id"] for c in real if f"change {c['id']} via {c['channel']}" in acc and not c["new_identifier"]]
        bad3 = [c["id"] for c in real if f"change {c['id']} via {c['channel']}" in acc and not c["compatibility_declared"]]
        out.append(v("SCOPE-12-01", "upgrade_only", bad1, "SCOPE changed only through UPGRADE with simulation", "{n} changes otherwise"))
        out.append(v("SCOPE-12-02", "new_identifier", bad2, "every change carries a new protocol identifier", "{n} changes without one"))
        out.append(v("SCOPE-12-03", "compatibility_declared", bad3, "every change declares compatibility across dependent protocols",
                     "{n} changes without the declaration"))
        pres = [m.value for m in msgs if m.source == "GATE" and m.value.get("recorded_as")]
        out.append(v("SCOPE-12-04", "presentation_not_upgrade", [p["change"] for p in pres if p["upgrade"]],
                     f"{len(pres)} presentation-only corrections recorded by date, not as Upgrades", "{n} recorded as Upgrades")
                   if any(c["presentation_only"] for c in sc) else na("SCOPE-12-04", "presentation_not_upgrade", "corrections", "none"))
    else:
        for rid, chk in (("SCOPE-12-01", "upgrade_only"), ("SCOPE-12-02", "new_identifier"), ("SCOPE-12-03", "compatibility_declared"),
                         ("SCOPE-12-04", "presentation_not_upgrade")):
            out.append(na(rid, chk, "changes", "none"))
    # §0: any execution outside the boundaries is invalid; here: no boundary check of this module failed
    broken = sorted({c.requirement_id for c in out if c.status == FAIL})
    out.append(v("SCOPE-0-01", "boundaries_enforced", broken, "nothing executed outside the SCOPE boundaries",
                 "{n} SCOPE boundaries crossed"))
    return out


IMPLEMENTS = {
    "SCOPE-0-01": ("boundaries_enforced", "PARTIAL", "Requests carry a declared domain."),
    "SCOPE-2-01": ("scope_prevails", "PARTIAL", "Another protocol's permission is a declared flag."),
    "SCOPE-2-02": ("default_deny", "IMPLEMENTED", None),
    "SCOPE-3-01": ("four_domains", "PARTIAL", "The domain is declared, not derived from the activity."),
    "SCOPE-3-02": ("s0_executed", "PARTIAL", "S0 membership is declared."),
    "SCOPE-3-03": ("s1_constrained", "IMPLEMENTED", None),
    "SCOPE-3-04": ("time_limit_days", "PARTIAL", "A positive limit counts; its length is not judged."),
    "SCOPE-3-05": ("ptl_anchored", "PARTIAL", "Declared property."),
    "SCOPE-3-06": ("auditable", "PARTIAL", "Declared property."),
    "SCOPE-3-07": ("degrades", "PARTIAL", "Declared property."),
    "SCOPE-3-08": ("no_precedent", "PARTIAL", "Declared property."),
    "SCOPE-3-09": ("vector_immediate_action", "PARTIAL", "Vectors are declared PTL-confirmed or not."),
    "SCOPE-3-10": ("vector_no_new_domain", "IMPLEMENTED", None),
    "SCOPE-3-11": ("vector_no_persistent_s1", "IMPLEMENTED", None),
    "SCOPE-3-12": ("vector_no_elevation_beyond_crisis", "IMPLEMENTED", None),
    "SCOPE-3-13": ("s2_verification", "IMPLEMENTED", None),
    "SCOPE-3-14": ("s2_learning_tools", "IMPLEMENTED", None),
    "SCOPE-3-15": ("s2_no_curriculum", "IMPLEMENTED", None),
    "SCOPE-3-16": ("s2_no_ranking", "PARTIAL", "Ranking is a declared activity."),
    "SCOPE-3-17": ("s2_no_conformity", "PARTIAL", "Conformity enforcement is a declared activity."),
    "SCOPE-3-18": ("s3_forbidden", "IMPLEMENTED", None),
    "SCOPE-3-19": ("s3_critical_violation", "IMPLEMENTED", None),
    "SCOPE-4-01": ("no_axiom_interpretation", "IMPLEMENTED", None),
    "SCOPE-4-02": ("no_axiom_reweighting", "IMPLEMENTED", None),
    "SCOPE-4-03": ("min_conditions_in_crisis_only", "IMPLEMENTED", None),
    "SCOPE-4-04": ("crisis_scope_by_crisis_only", "IMPLEMENTED", None),
    "SCOPE-4-05": ("bounded_interpretation", "PARTIAL", "Checked as: inside the declared Crisis Scope."),
    "SCOPE-4-06": ("no_min_conditions_elsewhere", "IMPLEMENTED", None),
    "SCOPE-5-01": ("crisis_scope_in_s1", "PARTIAL", "Entry and collapse only."),
    "SCOPE-5-02": ("crisis_entry_state_machine", "IMPLEMENTED", None),
    "SCOPE-5-03": ("no_entry_by_inference", "IMPLEMENTED", None),
    "SCOPE-5-07": ("crisis_no_permanent_change", "PARTIAL", "Permanence is a declared property."),
    "SCOPE-5-08": ("crisis_no_create_right", "IMPLEMENTED", None),
    "SCOPE-5-09": ("crisis_no_extend_authority", "IMPLEMENTED", None),
    "SCOPE-5-10": ("crisis_no_modify_axiom", "IMPLEMENTED", None),
    "SCOPE-5-11": ("crisis_no_set_precedent", "PARTIAL", "Precedent is a declared action."),
    "SCOPE-5-12": ("collapse_on_exit", "IMPLEMENTED", None),
    "SCOPE-6-01": ("authority_scoped", "PARTIAL", "Declared property."),
    "SCOPE-6-02": ("authority_time_bounded", "IMPLEMENTED", None),
    "SCOPE-6-03": ("authority_decays", "PARTIAL", "The decay law is not given; declared property."),
    "SCOPE-6-04": ("collapse_on_stabilization", "PARTIAL", "Stabilization is a declared day."),
    "SCOPE-6-05": ("no_self_extension", "IMPLEMENTED", None),
    "SCOPE-6-06": ("renewal_conditions", "IMPLEMENTED", None),
    "SCOPE-7-01": ("harm_interruption", "PARTIAL", "Recorded classification."),
    "SCOPE-7-02": ("no_jurisdiction_expansion", "IMPLEMENTED", None),
    "SCOPE-7-03": ("no_conversion", "IMPLEMENTED", None),
    "SCOPE-7-04": ("no_implicit_governance", "PARTIAL", "Governance creation is a declared follow-up."),
    "SCOPE-8-01": ("no_expansion", "PARTIAL", "Expansion attempts are declared with their basis."),
    "SCOPE-8-02": ("scope_audit_trigger", "PARTIAL", "The threshold number of Subjects is not given (source missing)."),
    "SCOPE-8-03": ("audit_blocks_escalation", "IMPLEMENTED", None),
    "SCOPE-8-04": ("independent_confirmation", "IMPLEMENTED", None),
    "SCOPE-8-05": ("reject_weak_evidence", "IMPLEMENTED", None),
    "SCOPE-9-05": ("settlement_independent", "PARTIAL", "Settlement properties are recorded."),
    "SCOPE-9-06": ("no_post_exit_compliance", "IMPLEMENTED", None),
    "SCOPE-9-08": ("no_economic_friction", "PARTIAL", "Fees only."),
    "SCOPE-9-09": ("no_permanent_restriction", "PARTIAL", "Recorded restriction."),
    "SCOPE-10-01": ("transparency_verification", "IMPLEMENTED", None),
    "SCOPE-10-02": ("transparency_audit_trail", "IMPLEMENTED", None),
    "SCOPE-10-03": ("transparency_counterfactual_simulation", "IMPLEMENTED", None),
    "SCOPE-10-04": ("transparency_model_explanation", "PARTIAL", "Declining an explanation is not counted as a violation."),
    "SCOPE-11-01": ("violations_flagged", "IMPLEMENTED", None),
    "SCOPE-11-02": ("repeated_violations_fault", "PARTIAL", "'Repeated' = the declared number of violations (H-SG-2)."),
    "SCOPE-12-01": ("upgrade_only", "PARTIAL", "Audit, acceptance window and rollback are UPGRADE's checks."),
    "SCOPE-12-02": ("new_identifier", "IMPLEMENTED", None),
    "SCOPE-12-03": ("compatibility_declared", "IMPLEMENTED", None),
    "SCOPE-12-04": ("presentation_not_upgrade", "IMPLEMENTED", None),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")
PROTOCOLS = ["defense", "crisis", "finance", "info", "edu", "culture", "police", "transport", "habitat", "audit", "upgrade"]
DAY = {"type": "int", "min": 0, "max": 3650}
B = {"type": "bool"}


def _lst(fields, default, label, mx=30):
    return {"type": "list", "min_items": 0, "max_items": mx, "items": {"type": "object", "fields": fields}, "default": default,
            "source": "user", "label": label}


PROTO = {"type": "enum", "values": PROTOCOLS}


class ScopeGateModule(LabModule):
    id = "scope_gate"
    version = "1.0.0"
    title = {"en": "Scope gate (SCOPE §2-§12)", "ru": "Шлюз границ (SCOPE §2-§12)"}
    summary = {"en": "Protocols ask to act — in S0, S1, S2, S3, inside a crisis, after a neutralization, with a temporary authority: "
                     "does the gate let through only what SCOPE explicitly permits, and does it flag the rest?",
               "ru": "Протоколы просят действовать — в S0, S1, S2, S3, в кризисе, после нейтрализации, с временными полномочиями: "
                     "пропускает ли шлюз только явно разрешённое SCOPE и помечает ли остальное?"}
    protocols = ["DKP-7-SCOPE-001"]
    example_order = ["mixed_requests", "crisis_lifecycle", "faulty_gate"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_scope_gate_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-SG-1", "source": "hypothesis", "text": {
            "en": "Each request declares its domain, basis and properties; the gate does not classify activities itself.",
            "ru": "Каждый запрос объявляет свой домен, основание и свойства; шлюз сам деятельность не классифицирует."}},
        {"id": "H-SG-2", "source": "hypothesis", "text": {
            "en": "'Repeated violations' (§11) = the declared number of refused attempts by one protocol (default 2).",
            "ru": "'Повторные нарушения' (§11) = объявленное число отклонённых попыток одного протокола (по умолчанию 2)."}},
        {"id": "H-SG-3", "source": "hypothesis", "text": {
            "en": "An open Scope Audit blocks every S0 -> S1 transition, which satisfies all three bullets of §8. The corpus defines "
                  "neither the end of the audit nor what 'confirmation by independent PTL nodes' confirms (F-035): the audit stays open.",
            "ru": "Открытый аудит границ блокирует любой переход S0 -> S1, что выполняет все три пункта §8. Конец аудита и то, что "
                  "подтверждают независимые узлы PTL, в корпусе не определены (F-035): аудит остаётся открытым."}},
    ]
    inputs = {
        "days": {"type": "int", "min": 10, "max": 3650, "default": 120, "unit": "day", "source": "user",
                 "label": {"en": "Days", "ru": "Дней"}},
        "domain_requests": _lst({"day": DAY, "protocol": PROTO, "domain": {"type": "enum", "values": list(DOMAINS)},
                                 "activity": {"type": "enum", "values": ["execution", "verification", "learning_tools", "curriculum", "ranking",
                                                                         "conformity"], "default": "execution"},
                                 "time_limit_days": {"type": "int", "min": 0, "max": 3650, "default": 0},
                                 "ptl_anchored": {"type": "bool", "default": True}, "auditable": {"type": "bool", "default": True},
                                 "degrades": {"type": "bool", "default": True}, "no_precedent": {"type": "bool", "default": True},
                                 "other_protocol_permits": {"type": "bool", "default": False}},
                                [{"day": 1, "protocol": "transport", "domain": "S0"},
                                 {"day": 2, "protocol": "defense", "domain": "S1", "time_limit_days": 10},
                                 {"day": 3, "protocol": "defense", "domain": "S1", "time_limit_days": 0, "other_protocol_permits": True},
                                 {"day": 4, "protocol": "edu", "domain": "S2", "activity": "verification"},
                                 {"day": 5, "protocol": "edu", "domain": "S2", "activity": "curriculum"},
                                 {"day": 6, "protocol": "culture", "domain": "S2", "activity": "ranking"},
                                 {"day": 7, "protocol": "info", "domain": "S3"},
                                 {"day": 8, "protocol": "finance", "domain": "unlisted"}],
                                {"en": "Requests by domain", "ru": "Запросы по доменам"}),
        "vector_actions": _lst({"day": DAY, "protocol": PROTO, "ptl_confirmed": {"type": "bool", "default": True},
                                "seeks": {"type": "enum", "values": ["none"] + list(VECTOR_SEEKS), "default": "none"}},
                               [{"day": 10, "protocol": "defense"}, {"day": 11, "protocol": "defense", "seeks": "persistent_s1"}],
                               {"en": "Actions on Vectors of Physical Inevitability", "ru": "Действия по векторам физической неизбежности"}),
        "axiom_requests": _lst({"day": DAY, "protocol": PROTO,
                                "action": {"type": "enum", "values": list(AXIOM_ACTIONS)}},
                               [{"day": 12, "protocol": "finance", "action": "interpret"},
                                {"day": 13, "protocol": "police", "action": "invoke_min_conditions"},
                                {"day": 40, "protocol": "crisis", "action": "invoke_min_conditions"}],
                               {"en": "Axiom requests", "ru": "Запросы к аксиомам"}),
        "crisis_events": _lst({"day": DAY, "by_protocol": PROTO,
                               "event": {"type": "enum", "values": ["enter", "exit"] + list(IN_CRISIS)},
                               "basis": {"type": "enum", "values": list(CRISIS_BASES), "default": "crisis_state_machine"},
                               "ptl_confirmed": {"type": "bool", "default": True}},
                              [{"day": 20, "by_protocol": "defense", "event": "enter", "basis": "inference"},
                               {"day": 30, "by_protocol": "crisis", "event": "enter"},
                               {"day": 45, "by_protocol": "crisis", "event": "create_right"},
                               {"day": 46, "by_protocol": "crisis", "event": "set_precedent"},
                               {"day": 60, "by_protocol": "crisis", "event": "exit"}],
                              {"en": "Crisis Scope events", "ru": "События кризисного контура"}),
        "authorities": _lst({"id": {"type": "str"}, "day": DAY, "protocol": PROTO, "scoped": {"type": "bool", "default": True},
                             "duration_days": {"type": "int", "min": 0, "max": 3650}, "decays": {"type": "bool", "default": True},
                             "extension_day": {"type": "int", "min": -1, "max": 3650, "default": -1},
                             "extension_by": {"type": "enum", "values": ["self", "renewal"], "default": "renewal"},
                             "ptl_justified": {"type": "bool", "default": False}, "simulated": {"type": "bool", "default": False},
                             "stabilized_day": {"type": "int", "min": -1, "max": 3650, "default": -1}},
                            [{"id": "evac_lead", "day": 31, "protocol": "crisis", "duration_days": 20, "extension_day": 50,
                              "extension_by": "renewal", "ptl_justified": True, "simulated": True, "stabilized_day": 58},
                             {"id": "grid_ctl", "day": 32, "protocol": "crisis", "duration_days": 10, "extension_day": 40, "extension_by": "self"},
                             {"id": "open_ended", "day": 33, "protocol": "defense", "duration_days": 0}],
                            {"en": "Temporary authorities", "ru": "Временные полномочия"}),
        "neutralizations": _lst({"day": DAY, "protocol": PROTO, "location": {"type": "str"},
                                 "follow_up": {"type": "enum", "values": ["none"] + list(FOLLOW_UPS), "default": "none"}},
                                [{"day": 70, "protocol": "defense", "location": "drone_hub", "follow_up": "convert_to_s1"}],
                                {"en": "Neutralizations and follow-ups", "ru": "Нейтрализации и последующие шаги"}),
        "expansion_attempts": _lst({"day": DAY, "protocol": PROTO, "basis": {"type": "enum", "values": list(EXPANSIONS)}},
                                   [{"day": 80, "protocol": "transport", "basis": "cumulative_measures"}],
                                   {"en": "Scope expansion attempts", "ru": "Попытки расширить границы"}),
        "divergence_reports": _lst({"day": DAY, "reporters": {"type": "int", "min": 0, "max": 10 ** 9}},
                                   [{"day": 90, "reporters": 500}], {"en": "Claimed PTL divergence reports", "ru": "Заявления о расхождении PTL"}),
        "audit_threshold": {"type": "int", "min": 1, "max": 10 ** 9, "default": 300, "source": "missing",
                            "label": {"en": "Reporting Subjects that trigger a Scope Audit (§8)", "ru": "Число заявителей для аудита границ (§8)"}},
        "escalations": _lst({"day": DAY, "protocol": PROTO,
                             "evidence": {"type": "enum", "values": list(EVIDENCE) + ["none"]}},
                            [{"day": 85, "protocol": "defense", "evidence": "single_sensor"},
                             {"day": 88, "protocol": "defense", "evidence": "independent_ptl"},
                             {"day": 92, "protocol": "defense", "evidence": "isolated_region"}],
                            {"en": "S0 -> S1 escalation requests", "ru": "Запросы эскалации S0 -> S1"}),
        "exits": _lst({"subject": {"type": "str"}, "day": DAY, "fee_requested": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0.0}},
                      [{"subject": "s9", "day": 100, "fee_requested": 50.0}], {"en": "Exits", "ru": "Выходы"}),
        "transparency_requests": {"type": "list", "min_items": 0, "max_items": 10, "source": "user",
                                  "items": {"type": "enum", "values": list(TRANSPARENCY)},
                                  "default": ["verification", "audit_trail", "counterfactual_simulation", "model_explanation"],
                                  "label": {"en": "Transparency requests", "ru": "Запросы прозрачности"}},
        "scope_changes": _lst({"id": {"type": "str"}, "day": DAY, "channel": {"type": "enum", "values": ["upgrade", "direct"]},
                               "simulated": {"type": "bool", "default": True}, "new_identifier": {"type": "bool", "default": True},
                               "compatibility_declared": {"type": "bool", "default": True},
                               "presentation_only": {"type": "bool", "default": False}},
                              [{"id": "typo_fix", "day": 110, "channel": "direct", "presentation_only": True},
                               {"id": "s2_change", "day": 111, "channel": "direct"},
                               {"id": "s1_limits", "day": 112, "channel": "upgrade"}],
                              {"en": "Changes to SCOPE", "ru": "Изменения SCOPE"}),
        "repeat_threshold": {"type": "int", "min": 2, "max": 100, "default": 2, "source": "hypothesis",
                             "label": {"en": "Violations that count as 'repeated' (§11)", "ru": "Сколько нарушений — 'повторные' (§11)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        days = r["days"]
        for key in ("domain_requests", "vector_actions", "axiom_requests", "crisis_events", "authorities", "neutralizations",
                    "expansion_attempts", "divergence_reports", "escalations", "exits", "scope_changes"):
            for x in r[key]:
                if x["day"] >= days:
                    p.append(f"input.{key}: day {x['day']} beyond the horizon")
        for key, f in (("authorities", "id"), ("exits", "subject"), ("scope_changes", "id"), ("neutralizations", "location")):
            ids = [x[f] for x in r[key]]
            if len(set(ids)) != len(ids):
                p.append(f"input.{key}: repeated id")
            for x in ids:
                if not _ID.fullmatch(x):
                    p.append(f"input.{key}: identifier {x!r} must be lowercase letters, digits or _")
        for a in r["authorities"]:
            if a["extension_day"] >= 0 and a["extension_day"] < a["day"]:
                p.append(f"input.authorities: {a['id']} extended before it was granted")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        dec = [{"day": m.arrived_at, **m.value} for m in msgs if m.source == "GATE"]
        outputs = {"gate": dec, "audit": [{"day": m.arrived_at, **m.value} for m in msgs if m.source == "AUDIT"],
                   "executed": sum(1 for d in dec if d.get("executed")), "refused": sum(1 for d in dec if d.get("executed") is False),
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": f"{outputs['executed']} requests executed, {outputs['refused']} refused and flagged; "
                    f"provisions violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"Исполнено {outputs['executed']} запросов, отклонено и помечено {outputs['refused']}; "
                    f"нарушены пункты: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"executed": outputs["executed"], "refused": outputs["refused"], "violations": len(outputs["violations"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "mixed_requests": {},
            "crisis_lifecycle": {"domain_requests": [], "vector_actions": [], "neutralizations": [], "expansion_attempts": [],
                                 "divergence_reports": [], "escalations": [], "exits": [], "scope_changes": [], "transparency_requests": []},
            "quiet_s0": {"domain_requests": [{"day": 1, "protocol": "transport", "domain": "S0"}], "vector_actions": [], "axiom_requests": [],
                         "crisis_events": [], "authorities": [], "neutralizations": [], "expansion_attempts": [], "divergence_reports": [],
                         "escalations": [], "exits": [], "scope_changes": [], "transparency_requests": []},
            "other_attempts": {"domain_requests": [{"day": 1, "protocol": "edu", "domain": "S2", "activity": "learning_tools"},
                                                   {"day": 2, "protocol": "culture", "domain": "S2", "activity": "conformity"},
                                                   {"day": 3, "protocol": "defense", "domain": "S1", "time_limit_days": 5, "ptl_anchored": False}],
                               "vector_actions": [{"day": 4, "protocol": "defense", "seeks": "new_domain"},
                                                  {"day": 5, "protocol": "defense", "seeks": "elevation_beyond_crisis"},
                                                  {"day": 6, "protocol": "defense", "ptl_confirmed": False}],
                               "crisis_events": [{"day": 30, "by_protocol": "crisis", "event": "enter"},
                                                 {"day": 31, "by_protocol": "crisis", "event": "extend_authority"},
                                                 {"day": 32, "by_protocol": "crisis", "event": "modify_axiom"},
                                                 {"day": 33, "by_protocol": "crisis", "event": "permanent_change"},
                                                 {"day": 34, "by_protocol": "crisis", "event": "exit", "ptl_confirmed": False}],
                               "authorities": [{"id": "relief", "day": 31, "protocol": "crisis", "duration_days": 10, "extension_day": 39,
                                                "ptl_justified": True, "simulated": False}],
                               "neutralizations": [{"day": 70, "protocol": "defense", "location": "relay", "follow_up": "expand_jurisdiction"},
                                                   {"day": 71, "protocol": "police", "location": "depot", "follow_up": "create_governance"}],
                               "axiom_requests": [{"day": 12, "protocol": "finance", "action": "reweight"}]},
            "confirmed_during_audit": {"escalations": [{"day": 95, "protocol": "defense", "evidence": "independent_ptl"}]},
            "faulty_gate": {"faults": ["allow_s3", "crisis_by_inference", "allow_self_extension", "convert_neutralized", "exit_fee",
                                       "direct_scope_change"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"beyond_horizon": {"days": 10, "domain_requests": [{"day": 20, "protocol": "transport", "domain": "S0"}]},
                "extension_before_grant": {"authorities": [{"id": "a", "day": 10, "protocol": "crisis", "duration_days": 5, "extension_day": 2}]},
                "bad_identifier": {"exits": [{"subject": "Bad Name", "day": 1}]}}


def _resolve_defaults(inputs: Dict[str, Dict[str, Any]]) -> None:
    for spec in inputs.values():
        if spec["type"] == "list" and spec["items"]["type"] == "object":
            spec["default"] = [resolve(x, spec["items"]["fields"]) for x in spec["default"]]


_resolve_defaults(ScopeGateModule.inputs)
