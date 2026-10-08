"""
AUDIT TRACE module — DKP-8-AUDIT-001: continuous audit of a stream of execution events.

Every in-scope event (§4: executions, parameter accesses and updates, oracle inputs, cross-layer calls,
upgrade, crisis and Mercy invocations) becomes an Audit Event in an immutable, hash-chained Audit Trace
(§3, §6); private beliefs, non-system cultural expression and off-chain activity are not recorded (§4).
Audit nodes replay each event (§6) and check the invariants of §5 and the epistemic metadata of §4.
Deviations are classified D1-D4 (§7) and answered by §8: logging, remediation, halt, halt with upgrade
review — never punishment.  Audit observes and reports only (§10), stays open to independent verification
(§9), keeps running during Mercy (§11) and is changed only through UPGRADE (§12).

The mapping of each invariant to a D-level is not given except for missing metadata (D2, §4); the lab
declares it (H-AT-1).  §4 calls D2 "Consistency or Integrity Anomaly", §7 calls it "Constraint
Violation" (F-038).  Time unit: step.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

IN_SCOPE = ("execution", "parameter_access", "parameter_update", "oracle_input", "cross_layer_call", "upgrade", "crisis", "mercy")
EXCLUDED = ("private_belief", "cultural_expression", "offchain_no_effect")
FLAGS = ("axiom_violation", "scope_expansion", "runtime_tuning", "nondeterministic", "attribution_lost", "metadata_missing",
         "epistemic_upgrade", "stale_unflagged", "concealed_coordinated", "benign_anomaly")
LEVEL = {"axiom_violation": "D3", "scope_expansion": "D3", "runtime_tuning": "D3", "attribution_lost": "D3",
         "nondeterministic": "D2", "metadata_missing": "D2", "epistemic_upgrade": "D2", "stale_unflagged": "D2",
         "concealed_coordinated": "D4", "benign_anomaly": "D1"}                 # H-AT-1 (only metadata_missing is written: §4)
RESPONSE = {"D1": "log and monitor", "D2": "remediation protocol", "D3": "systemic halt", "D4": "immediate halt and mandatory upgrade review"}
RANK = {"D1": 1, "D2": 2, "D3": 3, "D4": 4}

FAULTS = {
    "record_private": "private beliefs are recorded",
    "skip_out_of_scope_kind": "parameter accesses are not audited",
    "mutable_trace": "an audit event is rewritten after recording",
    "no_replay": "audit nodes do not recompute",
    "ignore_nondeterminism": "replicas that disagree are not flagged",
    "metadata_as_d1": "missing metadata is classified D1",
    "no_axiom_escalation": "an axiom violation is not escalated",
    "allow_runtime_tuning": "a runtime parameter change is not flagged",
    "scope_expansion_unflagged": "scope expansion without upgrade is not a breach",
    "attribution_loss_ignored": "loss of attribution is not a systemic fault",
    "no_halt_on_d3": "a D3 deviation does not halt",
    "d4_without_review": "a D4 deviation halts without upgrade review",
    "punish": "audit applies a sanction",
    "inject_correction": "audit corrects live execution",
    "mask_failure": "audit hides a deviation",
    "delay_halt": "audit delays a halt signal",
    "suspend_in_mercy": "audit pauses during Mercy",
    "closed_method": "the audit methodology is not exposed",
    "direct_change": "AUDIT is changed outside UPGRADE",
}


def _h(prev, ev):
    return hashlib.sha256((prev + json.dumps(ev, sort_keys=True)).encode()).hexdigest()[:16]


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:04d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    prev = "genesis"
    mercy = [(m["from"], m["until"]) for m in r["mercy_periods"]]
    halted_until = -1
    for e in sorted(r["events"], key=lambda x: x["t"]):
        t = e["t"]
        put("observation", e["protocol"].upper(), t, {"event": e["id"], "kind": e["kind"]})
        in_m = any(a <= t < b for a, b in mercy)
        if in_m and "suspend_in_mercy" in faults:
            continue
        if e["kind"] in EXCLUDED and "record_private" not in faults:
            continue
        if e["kind"] == "parameter_access" and "skip_out_of_scope_kind" in faults:
            continue
        rec = {"event": e["id"], "protocol": e["protocol"], "kind": e["kind"], "t": t, "signed": True}
        h = _h(prev, rec)
        rec["hash"], rec["prev"] = h, prev
        prev = h
        put("action", "AUDIT", t, {"audit_event": rec})
        if "mutable_trace" in faults and e["flags"]:
            put("action", "AUDIT", t, {"rewrite": e["id"]})
        if "no_replay" not in faults:
            put("evaluation", "AUDIT", t, {"replay": e["id"], "replicas_agree": not e["replicas_differ"],
                                           "recomputed_by": r["audit_nodes"]})
        flags = list(e["flags"])
        if e["replicas_differ"] and "nondeterministic" not in flags:
            flags.append("nondeterministic")
        if e["kind"] == "parameter_update" and not e["via_upgrade"] and "runtime_tuning" not in flags:
            flags.append("runtime_tuning")
        drop = {"ignore_nondeterminism": "nondeterministic", "allow_runtime_tuning": "runtime_tuning",
                "scope_expansion_unflagged": "scope_expansion", "attribution_loss_ignored": "attribution_lost"}
        for f, fl in drop.items():
            if f in faults and fl in flags:
                flags.remove(fl)
        if "mask_failure" in faults and flags:
            flags = flags[1:]
        if not flags:
            continue
        lv = {fl: ("D1" if fl == "metadata_missing" and "metadata_as_d1" in faults else LEVEL[fl]) for fl in flags}
        top = max(lv.values(), key=lambda x: RANK[x])
        dev = {"event": e["id"], "protocol": e["protocol"], "deviations": lv, "level": top, "silent": e["silent"],
               "during_mercy": in_m}
        put("evaluation", "AUDIT", t, {"deviation": dev})
        if "axiom_violation" in flags and "no_axiom_escalation" not in faults:
            put("notice", "AUDIT", t, {"escalation": e["id"], "reason": "axiom violation (§5.1)", "immediate": True})
        resp = {"event": e["id"], "level": top, "response": RESPONSE[top], "procedural": True}
        if top == "D3" and "no_halt_on_d3" in faults:
            resp["response"] = "log and monitor"
        if top == "D4" and "d4_without_review" in faults:
            resp["response"] = "immediate halt"
        if "punish" in faults:
            resp["sanction"] = "fine"
            resp["procedural"] = False
        kt = t + (2 if "delay_halt" in faults and "halt" in resp["response"] else 0)
        put("action", "AUDIT", kt, {"response": resp})
        if "inject_correction" in faults:
            put("action", "AUDIT", t, {"modify_live_execution": e["id"]})
        if "halt" in resp["response"]:
            halted_until = max(halted_until, t)
    put("notice", "AUDIT", 0, {"transparency": {"methodology_exposed": "closed_method" not in faults, "invariants_listed": "closed_method" not in faults,
                                                "independent_verification": True, "aggregated_for_privacy": True, "proprietary": False}})
    for c in r["changes"]:
        ok = (c["channel"] == "upgrade" and c["simulated"] and c["new_identifier"] and c["scope_compatibility"]) or \
            ("direct_change" in faults and c["channel"] == "direct")
        put("decision", "AUDIT", 0, {"change": c["id"], "channel": c["channel"], "accepted": ok})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    A = lambda key: [m for m in msgs if m.source == "AUDIT" and key in m.value]   # noqa: E731
    recs = [m.value["audit_event"] for m in A("audit_event")]
    rec_ids = {x["event"] for x in recs}
    ev = {e["id"]: e for e in r["events"]}
    should = [e["id"] for e in r["events"] if e["kind"] in IN_SCOPE]
    out.append(v("AUDIT-4-01", "scope_recorded", [i for i in should if i not in rec_ids], "every in-scope event recorded", "{n} in-scope events missing"))
    out.append(v("AUDIT-1-01", "continuous", [i for i in should if i not in rec_ids], "audit ran on every event (a permanent condition)", "{n} gaps"))
    exc = [e["id"] for e in r["events"] if e["kind"] in EXCLUDED]
    out.append(v("AUDIT-4-02", "exclusions", [i for i in exc if i in rec_ids], "private beliefs, cultural expression and off-chain activity not recorded",
                 "{n} excluded activities recorded") if exc else na("AUDIT-4-02", "exclusions", "excluded activity", "none declared"))
    # hash chain
    prev, broken = "genesis", []
    for x in recs:
        body = {k: x[k] for k in ("event", "protocol", "kind", "t", "signed")}
        if x["prev"] != prev or _h(prev, body) != x["hash"]:
            broken.append(x["event"])
        prev = x["hash"]
    rew = [m.value["rewrite"] for m in A("rewrite")]
    out.append(v("AUDIT-3-02", "immutable_trace", broken + rew, f"{len(recs)} audit events in an unbroken hash chain, none rewritten",
                 "{n} events rewritten or out of chain"))
    out.append(v("AUDIT-3-01", "verifiable_events", [x["event"] for x in recs if not x["signed"]] + broken, "every audit event signed and hashed", "{n} not verifiable"))
    out.append(v("AUDIT-6-02", "audit_data_properties", broken + rew + [x["event"] for x in recs if "t" not in x],
                 "audit data immutable and time-indexed", "{n} records violate it"))
    rp = {m.value["replay"]: m.value for m in A("replay")}
    out.append(v("AUDIT-6-01", "replay_recompute", [i for i in rec_ids if i not in rp], "every audit event replayed by independent audit nodes",
                 "{n} events not recomputed"))
    # deviations recomputed
    devs = {m.value["deviation"]["event"]: m.value["deviation"] for m in A("deviation")}
    want = {}
    for e in r["events"]:
        if e["kind"] not in IN_SCOPE:
            continue
        fl = set(e["flags"])
        if e["replicas_differ"]:
            fl.add("nondeterministic")
        if e["kind"] == "parameter_update" and not e["via_upgrade"]:
            fl.add("runtime_tuning")
        if fl:
            want[e["id"]] = fl
    miss = [i for i, fl in want.items() if i not in devs or set(devs[i]["deviations"]) != fl]
    out.append(v("AUDIT-3-04", "deviations_detected", miss, f"{len(want)} deviations detected with all their causes", "{n} deviations missed or incomplete"))
    out.append(v("AUDIT-5-01", "invariants_verified", miss, "invariants of §5 verified on every event", "{n} events not fully verified"))
    sil = [i for i in want if ev[i]["silent"]]
    out.append(v("AUDIT-3-05", "silent_failures", [i for i in sil if i not in devs], "silent failures (no error signal) still detected", "{n} silent failures missed")
               if sil else na("AUDIT-3-05", "silent_failures", "silent failures", "none declared"))
    for rid, chk, fl, txt in (("AUDIT-5.1-01", "axiom_compliance", "axiom_violation", "axiom violations"),
                              ("AUDIT-5.2-01", "scope_compliance", "scope_expansion", "scope violations"),
                              ("AUDIT-5.3-01", "parameter_integrity", "runtime_tuning", "parameter changes outside UPGRADE"),
                              ("AUDIT-5.5-01", "attribution_integrity", "attribution_lost", "losses of attribution")):
        ids = [i for i, f in want.items() if fl in f]
        out.append(v(rid, chk, [i for i in ids if i not in devs or fl not in devs[i]["deviations"]], f"{txt} detected", "{n} " + txt + " missed")
                   if ids else na(rid, chk, txt, "none in the stream"))
    ax = [i for i, f in want.items() if "axiom_violation" in f]
    esc = {m.value["escalation"] for m in A("escalation")}
    out.append(v("AUDIT-5.1-02", "axiom_escalation", [i for i in ax if i not in esc], "every axiom violation escalated at once", "{n} not escalated")
               if ax else na("AUDIT-5.1-02", "axiom_escalation", "axiom violations", "none"))
    sc = [i for i, f in want.items() if "scope_expansion" in f]
    out.append(v("AUDIT-5.2-02", "scope_breach_critical", [i for i in sc if devs.get(i, {}).get("level") not in ("D3", "D4")],
                 "scope expansion without upgrade treated as a critical breach (D3)", "{n} treated as minor") if sc else
               na("AUDIT-5.2-02", "scope_breach_critical", "scope expansion", "none"))
    rt = [i for i, f in want.items() if "runtime_tuning" in f]
    out.append(v("AUDIT-5.3-02", "no_runtime_tuning", [i for i in rt if i not in devs or "runtime_tuning" not in devs[i]["deviations"]],
                 "runtime tuning flagged as forbidden", "{n} runtime changes accepted") if rt else
               na("AUDIT-5.3-02", "no_runtime_tuning", "runtime tuning", "none"))
    nd = [i for i, f in want.items() if "nondeterministic" in f]
    out.append(v("AUDIT-5.4-01", "determinism", [i for i in nd if i not in devs or "nondeterministic" not in devs[i]["deviations"]],
                 "replica disagreement flagged as an audit failure", "{n} nondeterministic executions missed") if nd else
               na("AUDIT-5.4-01", "determinism", "nondeterminism", "none"))
    md = [i for i, f in want.items() if "metadata_missing" in f]
    out.append(v("AUDIT-EpistemicMetadataVerification-04", "metadata_d2", [i for i in md if devs.get(i, {}).get("deviations", {}).get("metadata_missing") != "D2"],
                 "missing metadata reported as D2", "{n} classified otherwise") if md else
               na("AUDIT-EpistemicMetadataVerification-04", "metadata_d2", "missing metadata", "none"))
    out.append(v("AUDIT-EpistemicMetadataVerification-01", "metadata_presence", [i for i in md if i not in devs], "missing metadata detected", "{n} missed")
               if md else na("AUDIT-EpistemicMetadataVerification-01", "metadata_presence", "missing metadata", "none"))
    eu = [i for i, f in want.items() if f & {"epistemic_upgrade", "stale_unflagged"}]
    out.append(v("AUDIT-EpistemicMetadataVerification-02", "metadata_validity", [i for i in eu if i not in devs],
                 "unauthorized epistemic upgrades and unreflected staleness detected", "{n} missed") if eu else
               na("AUDIT-EpistemicMetadataVerification-02", "metadata_validity", "invalid metadata", "none"))
    out.append(v("AUDIT-EpistemicMetadataVerification-03", "eb_classification", [i for i in md + eu if devs.get(i, {}).get("level") not in ("D2", "D3", "D4")],
                 "metadata deviations classified against EB §5", "{n} unclassified") if md + eu else
               na("AUDIT-EpistemicMetadataVerification-03", "eb_classification", "metadata deviations", "none"))
    out.append(v("AUDIT-7-01", "classification", [i for i, d in devs.items() if d["level"] not in RANK], "every deviation classified D1-D4", "{n} unclassified"))
    resp = {m.value["response"]["event"]: (m.arrived_at, m.value["response"]) for m in A("response")}
    for lvl, rid, chk in (("D1", "AUDIT-8-01", "d1_log"), ("D2", "AUDIT-8-02", "d2_remediation"), ("D3", "AUDIT-8-03", "d3_halt"), ("D4", "AUDIT-8-04", "d4_halt_review")):
        ids = [i for i, d in devs.items() if d["level"] == lvl]
        out.append(v(rid, chk, [i for i in ids if i not in resp or resp[i][1]["response"] != RESPONSE[lvl]], f"{lvl}: {RESPONSE[lvl]}",
                     "{n} " + lvl + " responses wrong") if ids else na(rid, chk, lvl, "no deviation of this level"))
    out.append(v("AUDIT-8-05", "procedural_not_punitive", [i for i, (t, x) in resp.items() if not x["procedural"] or "sanction" in x],
                 "responses procedural, without punishment", "{n} punitive responses"))
    late = [i for i, (t, x) in resp.items() if "halt" in x["response"] and t != ev[i]["t"]]
    mod = [m.value["modify_live_execution"] for m in A("modify_live_execution")]
    masked = [i for i, f in want.items() if i in devs and set(devs[i]["deviations"]) != f]
    out.append(v("AUDIT-10-01", "observe_and_report", mod + late + masked, "audit modified nothing, masked nothing and delayed no halt",
                 "{n} interferences"))
    out.append(v("AUDIT-2-02", "outputs_do_not_override", mod, "audit outputs changed no logic, rule or parameter", "{n} live changes"))
    out.append(v("AUDIT-1-02", "verifies_not_judges", [i for i, (t, x) in resp.items() if "sanction" in x], "audit verified execution and judged no outcome",
                 "{n} judgments"))
    tr = A("transparency")[0].value["transparency"]
    out.append(v("AUDIT-9-01", "accessible", [k for k in ("methodology_exposed", "invariants_listed", "independent_verification") if not tr[k]],
                 "outputs open to independent verification; methodology and invariants exposed", "{n} transparency duties unmet"))
    out.append(v("AUDIT-9-02", "not_closed", [k for k in ("methodology_exposed",) if not tr[k]] + (["proprietary"] if tr["proprietary"] else []),
                 "no proprietary, closed or authority-gated audit", "audit closed"))
    mer = [e for e in r["events"] if e["kind"] in IN_SCOPE and any(m["from"] <= e["t"] < m["until"] for m in r["mercy_periods"])]
    if mer:
        out.append(v("AUDIT-11-01", "audit_in_mercy", [e["id"] for e in mer if e["id"] not in rec_ids], "audit uninterrupted during Mercy", "{n} events unaudited"))
        out.append(v("AUDIT-11-02", "mercy_not_visibility", [e["id"] for e in mer if e["id"] in want and e["id"] not in devs],
                     "deviations during Mercy still recorded", "{n} deviations hidden during Mercy"))
    else:
        for rid, chk in (("AUDIT-11-01", "audit_in_mercy"), ("AUDIT-11-02", "mercy_not_visibility")):
            out.append(na(rid, chk, "Mercy", "no Mercy period"))
    ch = [m.value for m in A("change")]
    if ch:
        good = {c["id"] for c in r["changes"] if c["channel"] == "upgrade" and c["simulated"] and c["new_identifier"] and c["scope_compatibility"]}
        acc = [x["change"] for x in ch if x["accepted"]]
        out.append(v("AUDIT-12-01", "upgrade_only", [i for i in acc if i not in good], "AUDIT changed only through UPGRADE with simulation", "{n} other changes"))
        cs = {c["id"]: c for c in r["changes"]}
        out.append(v("AUDIT-12-02", "new_identifier", [i for i in acc if not cs[i]["new_identifier"]], "accepted changes carry a new identifier", "{n} without"))
        out.append(v("AUDIT-12-03", "simulated", [i for i in acc if not cs[i]["simulated"]], "accepted changes simulated", "{n} not simulated"))
        out.append(v("AUDIT-12-04", "scope_compatibility", [i for i in acc if not cs[i]["scope_compatibility"]], "accepted changes declare SCOPE compatibility",
                     "{n} without"))
    else:
        for rid, chk in (("AUDIT-12-01", "upgrade_only"), ("AUDIT-12-02", "new_identifier"), ("AUDIT-12-03", "simulated"), ("AUDIT-12-04", "scope_compatibility")):
            out.append(na(rid, chk, "changes", "none"))
    out.append(CheckResult("AUDIT-3-03", "invariants_always", PASS if not miss else FAIL, "invariants checked on every recorded event" if not miss
                           else "some events not checked against the invariants"))
    return out


IMPLEMENTS = {
    "AUDIT-1-01": ("continuous", "PARTIAL", "Continuity over the declared stream."),
    "AUDIT-1-02": ("verifies_not_judges", "PARTIAL", "No sanction in responses."),
    "AUDIT-2-02": ("outputs_do_not_override", "PARTIAL", "Live modifications only."),
    "AUDIT-3-01": ("verifiable_events", "IMPLEMENTED", None),
    "AUDIT-3-02": ("immutable_trace", "IMPLEMENTED", None),
    "AUDIT-3-03": ("invariants_always", "PARTIAL", "Per recorded event."),
    "AUDIT-3-04": ("deviations_detected", "IMPLEMENTED", None),
    "AUDIT-3-05": ("silent_failures", "PARTIAL", "Silence is a declared property."),
    "AUDIT-4-01": ("scope_recorded", "IMPLEMENTED", None),
    "AUDIT-4-02": ("exclusions", "IMPLEMENTED", None),
    "AUDIT-EpistemicMetadataVerification-01": ("metadata_presence", "IMPLEMENTED", None),
    "AUDIT-EpistemicMetadataVerification-02": ("metadata_validity", "PARTIAL", "Declared flags."),
    "AUDIT-EpistemicMetadataVerification-03": ("eb_classification", "PARTIAL", "Level check only."),
    "AUDIT-EpistemicMetadataVerification-04": ("metadata_d2", "IMPLEMENTED", None),
    "AUDIT-5-01": ("invariants_verified", "IMPLEMENTED", None),
    "AUDIT-5.1-01": ("axiom_compliance", "PARTIAL", "Axiom violations are declared flags."),
    "AUDIT-5.1-02": ("axiom_escalation", "PARTIAL", "Escalation target not defined; recorded as an immediate notice."),
    "AUDIT-5.2-01": ("scope_compliance", "PARTIAL", "Declared flags."),
    "AUDIT-5.2-02": ("scope_breach_critical", "PARTIAL", "Critical = D3 (H-AT-1)."),
    "AUDIT-5.3-01": ("parameter_integrity", "IMPLEMENTED", None),
    "AUDIT-5.3-02": ("no_runtime_tuning", "IMPLEMENTED", None),
    "AUDIT-5.4-01": ("determinism", "PARTIAL", "Replica agreement is declared."),
    "AUDIT-5.5-01": ("attribution_integrity", "PARTIAL", "Declared flags."),
    "AUDIT-6-01": ("replay_recompute", "PARTIAL", "Replay recorded; recomputation is the declared replica result."),
    "AUDIT-6-02": ("audit_data_properties", "PARTIAL", "Immutability and time index."),
    "AUDIT-7-01": ("classification", "PARTIAL", "D-levels per H-AT-1; §4 and §7 name D2 differently (F-038)."),
    "AUDIT-8-01": ("d1_log", "IMPLEMENTED", None),
    "AUDIT-8-02": ("d2_remediation", "IMPLEMENTED", None),
    "AUDIT-8-03": ("d3_halt", "PARTIAL", "Partial or full halt is not specified; recorded as a halt."),
    "AUDIT-8-04": ("d4_halt_review", "IMPLEMENTED", None),
    "AUDIT-8-05": ("procedural_not_punitive", "IMPLEMENTED", None),
    "AUDIT-9-01": ("accessible", "PARTIAL", "Recorded properties."),
    "AUDIT-9-02": ("not_closed", "PARTIAL", "Recorded properties."),
    "AUDIT-10-01": ("observe_and_report", "IMPLEMENTED", None),
    "AUDIT-11-01": ("audit_in_mercy", "IMPLEMENTED", None),
    "AUDIT-11-02": ("mercy_not_visibility", "IMPLEMENTED", None),
    "AUDIT-12-01": ("upgrade_only", "PARTIAL", "Declared properties of the change."),
    "AUDIT-12-02": ("new_identifier", "IMPLEMENTED", None),
    "AUDIT-12-03": ("simulated", "IMPLEMENTED", None),
    "AUDIT-12-04": ("scope_compatibility", "IMPLEMENTED", None),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")


def _e(i, t, protocol, kind, flags=(), **kw):
    x = {"id": i, "t": t, "protocol": protocol, "kind": kind, "flags": list(flags), "replicas_differ": False, "via_upgrade": False, "silent": False}
    x.update(kw)
    return x


EVENTS = [_e("e1", 1, "habitat", "execution"), _e("e2", 2, "finance", "parameter_access"),
          _e("e3", 3, "finance", "parameter_update"), _e("e4", 4, "assets", "execution", ["metadata_missing"], silent=True),
          _e("e5", 5, "transport", "execution", replicas_differ=True), _e("e6", 6, "crisis", "crisis"),
          _e("e7", 7, "defense", "cross_layer_call", ["scope_expansion"]), _e("e8", 8, "police", "execution", ["axiom_violation"]),
          _e("e9", 9, "labor", "execution", ["attribution_lost"]), _e("e10", 10, "info", "oracle_input", ["concealed_coordinated"]),
          _e("e11", 11, "habitat", "execution", ["benign_anomaly"]), _e("e12", 12, "upgrade", "parameter_update", via_upgrade=True),
          _e("e13", 13, "culture", "cultural_expression"), _e("e14", 14, "edu", "private_belief"),
          _e("e15", 15, "habitat", "mercy"), _e("e16", 16, "habitat", "execution", ["epistemic_upgrade"])]


class AuditTraceModule(LabModule):
    id = "audit_trace"
    version = "1.0.0"
    title = {"en": "Continuous audit (AUDIT)", "ru": "Непрерывный аудит (AUDIT)"}
    summary = {"en": "Sixteen events, from a quiet execution to a concealed capture attempt: are they traced immutably, replayed, "
                     "classified D1-D4 and answered procedurally — without the audit touching anything?",
               "ru": "Шестнадцать событий — от тихого исполнения до скрытой попытки захвата: неизменно ли они записаны, переиграны, "
                     "классифицированы D1-D4 и обработаны процедурно — без вмешательства аудита?"}
    protocols = ["DKP-8-AUDIT-001"]
    example_order = ["event_stream", "faulty_audit"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_audit_trace_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-AT-1", "source": "hypothesis", "text": {
            "en": "D-level per cause: missing metadata D2 (written, §4); nondeterminism, unauthorized epistemic upgrade, unreflected "
                  "staleness D2; axiom, scope, parameter and attribution integrity D3 ('Structural Breach (scope, axiom, or parameter "
                  "integrity)'); concealed or coordinated D4; benign anomaly D1. The highest level of an event decides the response.",
            "ru": "Уровень по причине: нет метаданных — D2 (написано, §4); недетерминизм, несанкционированное повышение эпистемического "
                  "состояния, неотражённое устаревание — D2; целостность аксиом, границ, параметров и атрибуции — D3; скрытое или "
                  "согласованное — D4; безвредная аномалия — D1. Ответ определяет высший уровень события."}},
    ]
    inputs = {
        "audit_nodes": {"type": "int", "min": 1, "max": 1000, "default": 3, "source": "user", "label": {"en": "Audit nodes", "ru": "Узлов аудита"}},
        "events": {"type": "list", "min_items": 1, "max_items": 200, "source": "user", "label": {"en": "Execution events", "ru": "События исполнения"},
                   "items": {"type": "object", "fields": {
                       "id": {"type": "str"}, "t": {"type": "int", "min": 0, "max": 10 ** 6}, "protocol": {"type": "str"},
                       "kind": {"type": "enum", "values": list(IN_SCOPE) + list(EXCLUDED)},
                       "flags": {"type": "list", "min_items": 0, "max_items": len(FLAGS), "items": {"type": "enum", "values": list(FLAGS)}, "default": []},
                       "replicas_differ": {"type": "bool", "default": False}, "via_upgrade": {"type": "bool", "default": False},
                       "silent": {"type": "bool", "default": False}}},
                   "default": EVENTS},
        "mercy_periods": {"type": "list", "min_items": 0, "max_items": 5, "source": "user", "label": {"en": "Mercy periods", "ru": "Периоды милосердия"},
                          "items": {"type": "object", "fields": {"from": {"type": "int", "min": 0, "max": 10 ** 6}, "until": {"type": "int", "min": 0, "max": 10 ** 6}}},
                          "default": [{"from": 15, "until": 20}]},
        "changes": {"type": "list", "min_items": 0, "max_items": 5, "source": "user", "label": {"en": "Changes to AUDIT", "ru": "Изменения AUDIT"},
                    "items": {"type": "object", "fields": {"id": {"type": "str"}, "channel": {"type": "enum", "values": ["upgrade", "direct"]},
                                                           "simulated": {"type": "bool", "default": True}, "new_identifier": {"type": "bool", "default": True},
                                                           "scope_compatibility": {"type": "bool", "default": True}}},
                    "default": [{"id": "d_levels_v2", "channel": "upgrade"}, {"id": "hotfix", "channel": "direct"}]},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [e["id"] for e in r["events"]]
        if len(set(ids)) != len(ids):
            p.append("input.events: repeated id")
        for x in ids + [e["protocol"] for e in r["events"]]:
            if not _ID.fullmatch(x):
                p.append(f"input.events: identifier {x!r} must be lowercase letters, digits or _")
        for m in r["mercy_periods"]:
            if m["until"] <= m["from"]:
                p.append("input.mercy_periods: until must follow from")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        devs = [m.value["deviation"] for m in msgs if m.source == "AUDIT" and "deviation" in m.value]
        outputs = {"trace": [m.value["audit_event"] for m in msgs if m.source == "AUDIT" and "audit_event" in m.value],
                   "deviations": devs, "responses": [m.value["response"] for m in msgs if m.source == "AUDIT" and "response" in m.value],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        lv = {k: sum(1 for d in devs if d["level"] == k) for k in RANK}
        e = [{"en": f"{len(outputs['trace'])} audit events; deviations {lv}; violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"{len(outputs['trace'])} событий аудита; отклонения {lv}; нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]), "deviations": len(outputs["deviations"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"event_stream": {},
                "quiet_stream": {"events": [_e("e1", 1, "habitat", "execution"), _e("e2", 2, "finance", "parameter_access")], "mercy_periods": [],
                                 "changes": []},
                "faulty_audit": {"faults": ["record_private", "mutable_trace", "metadata_as_d1", "punish", "suspend_in_mercy"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_event": {"events": [_e("e1", 1, "habitat", "execution"), _e("e1", 2, "habitat", "execution")]},
                "mercy_backwards": {"mercy_periods": [{"from": 10, "until": 5}]}}


for _spec in AuditTraceModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
