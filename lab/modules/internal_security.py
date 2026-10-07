"""
INTERNAL SECURITY module — DKP-3-INTERNAL-SEC-001: the S0–S4 state machine and its limits.

PTL-confirmed integrity evidence (identity, impact, justice-execution and audit triggers, §6) drives a
finite-state system (§5): S1 Suspicion (max 7 DTI-Days), S2 Confirmed Integrity Violation (max 14
unless escalated), S3 Active Compromise (max 3), S4 Systemic Compromise (mandatory escalation to
DKP-4-CRISIS-001); automatic reversion to S0 when a maximum expires.  Each state allows its own
actions (§7); restrictive effects on Subjects go only as formal triggers to JUSTICE or IDENTITY (§2);
every action names its rule, evidence, scope and reversal path (§4.4, §9); during a PTL halt or an
arbitration flag all L3 execution stops (§6); hard bans (§8): no surveillance without a trigger, no
collective punishment, no permanent exclusion, no secret rules, no ideological justification, no
Subject or linked group above 4 % of the nodes.

Open in the text (H-IS-2): after an automatic reversion to S0, may evidence that still persists drive
the state up again at once?  'evidence_driven' (default): yes, containment comes in capped pulses;
'episode_once': no, the episode stays in S0 until the evidence changes.  Time unit: DTI-Day.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

LEVELS = ("suspicion", "violation", "active_compromise", "systemic")
STATE_OF = {"suspicion": "S1", "violation": "S2", "active_compromise": "S3", "systemic": "S4"}
RANK = {"S0": 0, "S1": 1, "S2": 2, "S3": 3, "S4": 4}
MAX_DAYS = {"S1": 7, "S2": 14, "S3": 3}                       # §5
NODE_CAP = 4.0                                               # §8, percent
TRIGGERS = ("identity", "impact", "justice_execution", "audit")
ALLOWED = {                                                  # §7
    "S1": {"evidence_preservation", "verification_frequency", "multisig_required", "challenge_response"},
    "S2": {"privilege_revocation_request", "subsystem_isolation", "freeze_request", "justice_workflow"},
    "S3": {"partial_execution_halt", "safe_mode", "multiparty_authorization"},
    "S4": {"crisis_escalation", "ptl_halt_request", "non_essential_suspension"},
}
SUBJECT_EFFECTS = {"privilege_revocation_request", "freeze_request", "justice_workflow"}
FAULTS = {
    "predictive_trigger": "unconfirmed (predicted) evidence drives the state machine",
    "throttle_in_s1": "baseline access is throttled during Suspicion",
    "overstay": "a state is kept beyond its maximum duration",
    "direct_execution": "a privilege is revoked directly at L3 instead of through IDENTITY",
    "act_during_halt": "L3 actions continue during a PTL halt",
    "no_crisis_escalation": "Systemic Compromise is not escalated to CRISIS",
    "collective_punishment": "identity-linked Subjects not involved are targeted too",
    "mass_surveillance": "evidence is collected on Subjects outside the triggering episode",
    "secret_rule": "an action is taken without naming its rule",
    "missing_due_process": "a restrictive trigger lacks reversal and appeal conditions",
    "permanent_exclusion": "a permanent exclusion is imposed without a Justice outcome",
    "ideological_justification": "an action is justified by a narrative",
}
EPISODE = {"type": "object", "fields": {
    "from_day": {"type": "int", "min": 0, "max": 10 ** 6},
    "to_day": {"type": "int", "min": 0, "max": 10 ** 6},
    "level": {"type": "enum", "values": list(LEVELS)},
    "trigger": {"type": "enum", "values": list(TRIGGERS), "default": "identity"},
    "ptl_confirmed": {"type": "bool", "default": True},
    "subjects": {"type": "list", "min_items": 1, "max_items": 20, "items": {"type": "str"}, "default": ["s1"]}}}
NODE = {"type": "object", "fields": {"holder": {"type": "str"}, "group": {"type": "str", "default": "none"},
                                     "share": {"type": "number", "min": 0, "max": 100}}}


def md(scope):
    return {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": scope, "revalidation_required": True, "dispute_allowed": True}


def level_on(r, k, faults=()) -> Tuple[Optional[str], List[int]]:
    best, idx = None, []
    for i, e in enumerate(r["evidence"]):
        if e["from_day"] <= k < e["to_day"] and (e["ptl_confirmed"] or "predictive_trigger" in faults):
            if best is None or LEVELS.index(e["level"]) > LEVELS.index(best):
                best = e["level"]
            idx.append(i)
    return best, [i for i in idx if r["evidence"][i]["level"] == best] if best else []


def halted(r, k):
    lo, hi = r["ptl_halt_window"]
    return lo <= k < hi


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=(), epistemic=None):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:05d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=k, decided_at=k if kind in ("decision", "action") else None,
                                  value={**value, "day": k, "dti": canonical(*dy_doy(r["start_dti_day"] + k))},
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    state, since = "S0", 0
    deferred: Optional[Tuple[str, List[str], List[str], List[int]]] = None      # actions held during a PTL halt
    blocked_level: Optional[str] = None
    stays: List[Dict[str, Any]] = []
    ev_msgs: Dict[int, Message] = {}
    for k in range(r["horizon_days"]):
        for i, e in enumerate(r["evidence"]):
            if e["from_day"] == k:
                ev_msgs[i] = put("observation", "PTL" if e["ptl_confirmed"] else "PREDICTION", k,
                                 {"episode": i, "level": e["level"], "trigger": e["trigger"], "subjects": e["subjects"],
                                  "ptl_confirmed": e["ptl_confirmed"]})
        lvl, idx = level_on(r, k, faults)
        if blocked_level and lvl != blocked_level:
            blocked_level = None
        target = STATE_OF[lvl] if lvl else "S0"
        prov = [ev_msgs[i].event_id for i in idx if i in ev_msgs]
        if state in MAX_DAYS and k - since >= MAX_DAYS[state] and "overstay" not in faults and \
                not (RANK[target] > RANK[state]):
            put("notice", "INTSEC", k, {"state": "S0", "from": state, "reason": f"maximum {MAX_DAYS[state]} DTI-Days expired (§5)"})
            stays[-1]["end"] = k
            stays[-1]["ended_by"] = "expiry"
            state, since = "S0", k
            if r["reentry_reading"] == "episode_once":
                blocked_level = lvl
            continue
        if blocked_level:
            target = "S0"
        if target != state:
            if stays and stays[-1].get("end") is None:
                stays[-1]["end"] = k
                stays[-1]["ended_by"] = "escalation" if RANK[target] > RANK[state] else "evidence"
            put("notice", "INTSEC", k, {"state": target, "from": state, "evidence": idx}, prov)
            state, since = target, k
            if state != "S0":
                stays.append({"state": state, "start": k, "end": None, "ended_by": None})
                subjects = sorted({s for i in idx for s in r["evidence"][i]["subjects"]})
                if halted(r, k) and "act_during_halt" not in faults:
                    put("notice", "INTSEC", k, {"l3_execution": "suspended", "reason": "PTL halt or arbitration flag (§6)"})
                    deferred = (state, subjects, prov, idx)
                else:
                    deferred = None
                    emit(put, r, faults, state, k, subjects, prov, idx)
            else:
                deferred = None
        elif deferred and not halted(r, k) and deferred[0] == state:
            put("notice", "INTSEC", k, {"l3_execution": "resumed", "reason": "PTL halt resolved (§6)"})
            emit(put, r, faults, state, k, deferred[1], deferred[2], deferred[3])
            deferred = None
        elif state != "S0" and halted(r, k) and k == r["ptl_halt_window"][0]:
            put("notice", "INTSEC", k, {"l3_execution": "suspended", "reason": "PTL halt or arbitration flag (§6)"})
    if stays and stays[-1].get("end") is None:
        stays[-1]["end"] = r["horizon_days"]
        stays[-1]["ended_by"] = "horizon"
    return log, stays


def emit(put, r, faults, state, k, subjects, prov, idx):
    def act(kind, scope, target=None, restrictive=False, executed_by="L3", source="INTSEC", **extra):
        v = {"action": kind, "state": state, "scope": scope, "evidence": idx, "logged": True, "reversible": True,
             "rule": f"INTERNAL-SEC §7 ({state})", "executed_by": executed_by, **extra}
        if target:
            v["target"] = target
        if restrictive:
            v.update({"violated_rule": f"integrity trigger {', '.join(r['evidence'][i]['trigger'] for i in idx)}",
                      "reversal": f"automatic on expiry of {state} or on Justice appeal",
                      "appeal": "DKP-1-JUSTICE-001 / DKP-4-ERROR-001"})
            if "missing_due_process" in faults:
                v.pop("reversal")
                v.pop("appeal")
        if "secret_rule" in faults and kind in ("evidence_preservation", "subsystem_isolation"):
            v.pop("rule")
        if "ideological_justification" in faults and kind in ("evidence_preservation", "subsystem_isolation"):
            v["justification"] = "narrative: hostile movement"
        put("action", source, k, v, prov, epistemic=md(prov[0]) if prov else None)

    linked = r["linked_subjects"] if "collective_punishment" in faults else []
    if state == "S1":
        watched = subjects + (r["linked_subjects"] if "mass_surveillance" in faults else [])
        for s in watched:
            act("evidence_preservation", "subject records", target=s)
        act("verification_frequency", "affected pipelines")
        act("multisig_required", "sensitive or high-impact operations")
        act("challenge_response", "via DKP-1-IDENTITY-001")
        if "throttle_in_s1" in faults:
            for s in subjects:
                act("baseline_throttle", "baseline access", target=s, restrictive=True)
    elif state == "S2":
        for s in subjects + linked:
            if "direct_execution" in faults:
                act("privilege_revocation", "credentials", target=s, restrictive=True, executed_by="L3")
            else:
                act("privilege_revocation_request", "scoped credentials", target=s, restrictive=True,
                    executed_by="trigger to DKP-1-IDENTITY-001", source="IDENTITY")
            act("freeze_request", "disputed transactions and assets", target=s, restrictive=True,
                executed_by="trigger to DKP-2-FINANCE-001 / DKP-2-ASSETS-001", source="ASSETS")
            act("justice_workflow", "Justice-domain workflow", target=s, restrictive=True,
                executed_by="trigger to DKP-1-JUSTICE-001", source="JUSTICE")
        if "permanent_exclusion" in faults and subjects:
            act("permanent_exclusion", "all access", target=subjects[0], restrictive=True, reversible=False)
        act("subsystem_isolation", "affected subsystem: " + ", ".join(sorted({r["evidence"][i]["trigger"] for i in idx})))
    elif state == "S3":
        act("partial_execution_halt", "compromised modules")
        act("safe_mode", "affected execution paths")
        act("multiparty_authorization", "sensitive operations")
    elif state == "S4":
        if "no_crisis_escalation" not in faults:
            put("notice", "CRISIS", k, {"escalation": "mandatory", "from": "DKP-3-INTERNAL-SEC-001 S4"}, prov)
            act("crisis_escalation", "system", executed_by="trigger to DKP-4-CRISIS-001")
        act("ptl_halt_request", "PTL", executed_by="request to DKP-0-ORACLE-001")
        act("non_essential_suspension", "non-essential execution paths")


def checks(r: Dict[str, Any], log: EventLog, stays: List[Dict[str, Any]]) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    acts = [m for m in msgs if m.kind == "action"]
    # state durations, from the state notices (independent of the generator's own bookkeeping)
    trans = [(m.arrived_at, m.value["state"], m.value.get("reason", "")) for m in msgs
             if m.source == "INTSEC" and m.kind == "notice" and "state" in m.value]
    periods = []
    for i, (d, s, why) in enumerate(trans):
        end = trans[i + 1][0] if i + 1 < len(trans) else r["horizon_days"]
        nxt = trans[i + 1][1] if i + 1 < len(trans) else None
        periods.append((s, d, end, nxt, trans[i + 1][2] if i + 1 < len(trans) else ""))
    bad = [m.event_id for m in msgs if m.source == "INTSEC" and m.kind == "notice" and "state" in m.value
           and (m.value["state"] not in RANK or not m.value.get("dti"))]
    out.append(v("INTSEC-5-01", "finite_state_machine", bad,
                 f"{len(trans)} transitions, all between the states S0–S4 and indexed by DTI-Day",
                 "{n} transitions outside S0–S4 or without a DTI-Day"))
    for st, rid in (("S1", "INTSEC-5-02"), ("S2", "INTSEC-5-03"), ("S3", "INTSEC-5-04")):
        ps = [p for p in periods if p[0] == st]
        if not ps:
            out.append(na(rid, f"max_duration_{st}", f"{st} duration", f"{st} never entered"))
            continue
        bad = [f"day {p[1]}: {p[2] - p[1]} days" for p in ps if p[2] - p[1] > MAX_DAYS[st] and
               not (p[3] and RANK[p[3]] > RANK[st] and p[2] - p[1] <= MAX_DAYS[st])]
        out.append(v(rid, f"max_duration_{st}", bad, f"every {st} stay lasted at most {MAX_DAYS[st]} DTI-Days",
                     "{n} " + st + " stays beyond the maximum"))
    capped = [p for p in periods if p[0] in MAX_DAYS and p[2] - p[1] >= MAX_DAYS[p[0]] and p[2] < r["horizon_days"]]
    if capped:
        bad = [f"{p[0]} from day {p[1]}" for p in capped if not (p[3] == "S0" and "expired" in p[4]) and
               not (p[3] and RANK[p[3]] > RANK[p[0]])]
        out.append(v("INTSEC-5-06", "auto_revert", bad, "every state that reached its maximum reverted to S0 automatically",
                     "{n} states not reverted at expiry"))
    else:
        out.append(na("INTSEC-5-06", "auto_revert", "automatic reversion", "no state reached its maximum"))
    s4 = [p for p in periods if p[0] == "S4"]
    if s4:
        esc = {m.arrived_at for m in msgs if m.source == "CRISIS" and m.value.get("escalation") == "mandatory"}
        bad = [p[1] for p in s4 if p[1] not in esc and not halted(r, p[1])]
        for rid in ("INTSEC-5-05", "INTSEC-7.4-01"):
            out.append(v(rid, "s4_escalates", bad, "Systemic Compromise escalated to DKP-4-CRISIS-001 on entry",
                         "{n} S4 entries without escalation"))
    else:
        for rid in ("INTSEC-5-05", "INTSEC-7.4-01"):
            out.append(na(rid, "s4_escalates", "S4 escalation", "S4 never entered"))
    # evidence: every action traces to PTL-confirmed evidence covering its day
    confirmed = {m.event_id: m for m in msgs if m.source == "PTL"}
    bad = [m.event_id for m in acts if not m.provenance or not set(m.provenance) <= set(confirmed)]
    for rid, chk in (("INTSEC-4.2-01", "non_preemptive"), ("INTSEC-11-01", "no_evidence_no_action"),
                     ("INTSEC-4.1-01", "responds_to_ptl")):
        out.append(v(rid, chk, bad, "every action traces to PTL-confirmed evidence of an occurring violation",
                     "{n} actions without PTL-confirmed evidence"))
    allowed = [m.event_id for m in acts if m.value["action"] not in ALLOWED.get(m.value["state"], set())]
    for rid, st in (("INTSEC-7.1-01", "S1"), ("INTSEC-7.2-01", "S2"), ("INTSEC-7.3-01", "S3")):
        mine = [m for m in acts if m.value["state"] == st]
        if mine:
            out.append(v(rid, f"allowed_actions_{st}", [m.event_id for m in mine if m.event_id in allowed],
                         f"only §7 actions taken in {st}", "{n} actions outside the permitted list"))
        else:
            out.append(na(rid, f"allowed_actions_{st}", f"{st} actions", f"{st} never entered"))
    s1 = [m for m in acts if m.value["state"] == "S1"]
    if s1:
        out.append(v("INTSEC-7.1-02", "no_throttle_s1", [m.event_id for m in s1 if "throttle" in m.value["action"]],
                     "no throttling or slowdown of baseline access during Suspicion", "{n} throttling actions in S1"))
    else:
        out.append(na("INTSEC-7.1-02", "no_throttle_s1", "throttling in S1", "S1 never entered"))
    # restrictive or corrective effects on Subjects (evidence preservation in S1 is non-coercive, §5)
    subj = [m for m in acts if m.value.get("target") and m.value["action"] != "evidence_preservation"]
    bad = [m.event_id for m in subj if m.value["executed_by"] == "L3"]
    for rid, chk in (("INTSEC-2-03", "effects_via_triggers"), ("INTSEC-2-02", "no_autonomous_revocation"),
                     ("INTSEC-11-05", "no_overreach")):
        if subj:
            out.append(v(rid, chk, bad, "every effect on a Subject went as a formal trigger to JUSTICE, IDENTITY or L2",
                         "{n} effects on Subjects executed directly at L3"))
        else:
            out.append(na(rid, chk, "effects on Subjects", "no Subject-directed action"))
    if r["ptl_halt_window"][1] > r["ptl_halt_window"][0]:
        out.append(v("INTSEC-6-03", "halt_suspends_l3", [m.event_id for m in acts if halted(r, m.arrived_at)],
                     "no L3 action during the PTL halt", "{n} L3 actions during the halt"))
    else:
        out.append(na("INTSEC-6-03", "halt_suspends_l3", "PTL halt", "no PTL halt declared"))
    involved = {s for e in r["evidence"] if e["ptl_confirmed"] for s in e["subjects"]}
    watch = [m for m in acts if m.value["action"] == "evidence_preservation"]
    out.append(v("INTSEC-8-01", "no_mass_surveillance", [m.event_id for m in watch if m.value["target"] not in involved],
                 "evidence collected only on Subjects in PTL-triggered episodes", "{n} Subjects watched without a trigger"))
    linked = set(r["linked_subjects"]) - involved
    if linked:
        out.append(v("INTSEC-8-02", "no_collective_punishment", [m.event_id for m in subj if m.value["target"] in linked],
                     f"no action against the {len(linked)} identity-linked Subjects not involved",
                     "{n} actions against Subjects only linked by association"))
    else:
        out.append(na("INTSEC-8-02", "no_collective_punishment", "guilt by association", "no linked, uninvolved Subjects declared"))
    out.append(v("INTSEC-8-03", "no_permanent_exclusion", [m.event_id for m in acts if m.value["action"] == "permanent_exclusion"
                                                            or not m.value.get("reversible", True)],
                 "no permanent or irreversible exclusion at L3", "{n} permanent exclusions without a Justice outcome"))
    out.append(v("INTSEC-8-04", "no_secret_rules", [m.event_id for m in acts if not m.value.get("rule")],
                 "every action names the rule it applies", "{n} actions without a stated rule"))
    out.append(v("INTSEC-8-05", "no_ideology", [m.event_id for m in acts if "justification" in m.value],
                 "no action justified by ideology or narrative", "{n} actions justified by a narrative"))
    restrictive = [m for m in acts if m.value.get("target") and m.value["action"] != "evidence_preservation"]
    if restrictive:
        bad = [m.event_id for m in restrictive if not all(m.value.get(f) for f in ("evidence", "violated_rule", "scope",
                                                                                  "reversal", "appeal"))
               and m.value.get("evidence") is not None]
        bad += [m.event_id for m in restrictive if m.value.get("evidence") == []]
        out.append(v("INTSEC-9-01", "due_process", bad,
                     "every restrictive action states its evidence, rule, scope, reversal and appeal", "{n} without due process"))
    else:
        out.append(na("INTSEC-9-01", "due_process", "restrictive actions", "none taken"))
    out.append(v("INTSEC-4.4-01", "logged_traceable", [m.event_id for m in acts if not m.value.get("logged") or not m.provenance],
                 "every action logged and traceable to its evidence", "{n} actions not logged or not traceable"))
    shares: Dict[str, float] = {}
    for x in r["node_shares"]:
        key = x["group"] if x["group"] != "none" else "holder:" + x["holder"]
        shares[key] = shares.get(key, 0.0) + x["share"]
    if r["node_shares"]:
        out.append(v("INTSEC-8-06", "node_cap", sorted(k for k, s in shares.items() if s > NODE_CAP + 1e-9),
                     f"no Subject or identity-linked group above {NODE_CAP:g} % of INTERNAL-SEC nodes "
                     f"(largest {max(shares.values()):.2f} %)", "{n} holders or groups above the cap"))
    else:
        out.append(na("INTSEC-8-06", "node_cap", "node concentration", "no node distribution declared"))
    again, _ = run(r)
    out.append(v("INTSEC-11-03", "complete_audit_trail", [] if again.digest() == log.digest() else ["digest"],
                 "complete, reproducible audit trail (re-execution gives a byte-identical log)", "re-execution differs"))
    return out


IMPLEMENTS = {
    "INTSEC-5-01": ("finite_state_machine", "PARTIAL", "The state machine is modelled on declared evidence episodes."),
    "INTSEC-5-02": ("max_duration_S1", "IMPLEMENTED", None),
    "INTSEC-5-03": ("max_duration_S2", "IMPLEMENTED", None),
    "INTSEC-5-04": ("max_duration_S3", "IMPLEMENTED", None),
    "INTSEC-5-05": ("s4_escalates", "IMPLEMENTED", None),
    "INTSEC-5-06": ("auto_revert", "PARTIAL", "Whether persisting evidence re-enters at once after reversion is not defined (H-IS-2, F-021)."),
    "INTSEC-7.4-01": ("s4_escalates", "PARTIAL", "Escalation and halt request are recorded; CRISIS itself is in crisis_recovery."),
    "INTSEC-4.1-01": ("responds_to_ptl", "IMPLEMENTED", None),
    "INTSEC-4.2-01": ("non_preemptive", "IMPLEMENTED", None),
    "INTSEC-11-01": ("no_evidence_no_action", "IMPLEMENTED", None),
    "INTSEC-7.1-01": ("allowed_actions_S1", "IMPLEMENTED", None),
    "INTSEC-7.2-01": ("allowed_actions_S2", "IMPLEMENTED", None),
    "INTSEC-7.3-01": ("allowed_actions_S3", "IMPLEMENTED", None),
    "INTSEC-7.1-02": ("no_throttle_s1", "IMPLEMENTED", None),
    "INTSEC-2-02": ("no_autonomous_revocation", "IMPLEMENTED", None),
    "INTSEC-2-03": ("effects_via_triggers", "IMPLEMENTED", None),
    "INTSEC-11-05": ("no_overreach", "PARTIAL", "Observed as effects on Subjects executed at L3."),
    "INTSEC-6-03": ("halt_suspends_l3", "IMPLEMENTED", None),
    "INTSEC-8-01": ("no_mass_surveillance", "IMPLEMENTED", None),
    "INTSEC-8-02": ("no_collective_punishment", "IMPLEMENTED", None),
    "INTSEC-8-03": ("no_permanent_exclusion", "IMPLEMENTED", None),
    "INTSEC-8-04": ("no_secret_rules", "IMPLEMENTED", None),
    "INTSEC-8-05": ("no_ideology", "IMPLEMENTED", None),
    "INTSEC-8-06": ("node_cap", "PARTIAL", "Node shares are declared inputs."),
    "INTSEC-9-01": ("due_process", "IMPLEMENTED", None),
    "INTSEC-4.4-01": ("logged_traceable", "PARTIAL", "Logging and traceability; physical reversibility is declared."),
    "INTSEC-11-03": ("complete_audit_trail", "IMPLEMENTED", None),
}


class InternalSecurityModule(LabModule):
    id = "internal_security"
    version = "1.0.0"
    title = {"en": "Internal security states (INTERNAL-SEC)", "ru": "Состояния внутренней безопасности (INTERNAL-SEC)"}
    summary = {"en": "Integrity evidence arrives: does the system step through S1–S4 within the time limits, act only on "
                     "PTL evidence, route every effect on a person through Justice or Identity, and never punish by association?",
               "ru": "Поступают свидетельства нарушения целостности: проходит ли система S1–S4 в пределах сроков, действует ли "
                     "только по данным PTL, направляет ли любые меры против людей через Justice или Identity и не наказывает ли "
                     "за связи?"}
    protocols = ["DKP-3-INTERNAL-SEC-001", "DKP-4-CRISIS-001", "DKP-1-IDENTITY-001", "DKP-1-JUSTICE-001"]
    example_order = ["suspicion_then_violation", "persisting_compromise", "persisting_compromise_once", "systemic",
                     "unconfirmed_prediction", "halt_during_violation", "concentrated_nodes", "faulty_security"]
    alternative_examples = ["persisting_compromise_once"]
    noncompliant_examples = ["concentrated_nodes"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_internal_security_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-IS-1", "source": "hypothesis", "text": {
            "en": "Evidence episodes are inputs with a level (suspicion, violation, active compromise, systemic) and PTL "
                  "confirmation; the state follows the highest confirmed level of the day.",
            "ru": "Эпизоды свидетельств — входы с уровнем (подозрение, нарушение, активная компрометация, системная) и "
                  "подтверждением PTL; состояние следует наивысшему подтверждённому уровню дня."}},
        {"id": "H-IS-2", "source": "alternative", "text": {
            "en": "After automatic reversion to S0 (§5): 'evidence_driven' (default) — evidence that still persists drives the "
                  "state up again the next day; 'episode_once' — the episode stays in S0 until its evidence changes (F-021).",
            "ru": "После автоматического возврата в S0 (§5): 'evidence_driven' (по умолчанию) — сохраняющиеся свидетельства "
                  "снова поднимают состояние на следующий день; 'episode_once' — эпизод остаётся в S0, пока свидетельства не "
                  "изменятся (F-021)."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of day 0", "ru": "DTI-Day дня 0"}},
        "horizon_days": {"type": "int", "min": 2, "max": 2000, "default": 40, "unit": "day", "source": "user",
                         "label": {"en": "Days", "ru": "Дней"}},
        "evidence": {"type": "list", "min_items": 0, "max_items": 20, "items": EPISODE, "source": "user",
                     "default": [{"from_day": 2, "to_day": 6, "level": "suspicion", "trigger": "identity", "ptl_confirmed": True,
                                  "subjects": ["s1"]},
                                 {"from_day": 6, "to_day": 15, "level": "violation", "trigger": "identity", "ptl_confirmed": True,
                                  "subjects": ["s1"]}],
                     "label": {"en": "Evidence episodes (H-IS-1)", "ru": "Эпизоды свидетельств (H-IS-1)"}},
        "linked_subjects": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "str"}, "default": ["s2", "s3"],
                            "source": "user", "label": {"en": "Identity-linked Subjects not involved",
                                                         "ru": "Связанные субъекты, не участвующие"}},
        "node_shares": {"type": "list", "min_items": 0, "max_items": 50, "items": NODE, "source": "user",
                        "default": [{"holder": "n1", "group": "none", "share": 3.5}, {"holder": "n2", "group": "g1", "share": 2},
                                    {"holder": "n3", "group": "g1", "share": 1.5}],
                        "label": {"en": "Shares of INTERNAL-SEC nodes (%)", "ru": "Доли узлов INTERNAL-SEC (%)"}},
        "ptl_halt_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "day", "source": "user",
                            "label": {"en": "PTL halt or arbitration flag from/to day", "ru": "Остановка PTL / арбитраж с/до дня"}},
        "reentry_reading": {"type": "enum", "values": ["evidence_driven", "episode_once"], "default": "evidence_driven",
                            "source": "alternative", "label": {"en": "Re-entry after expiry (H-IS-2)", "ru": "Повторный вход (H-IS-2)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        for i, e in enumerate(r["evidence"]):
            if e["to_day"] <= e["from_day"]:
                p.append(f"input.evidence[{i}]: to_day must follow from_day")
            for s in e["subjects"]:
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", s):
                    p.append(f"input.evidence[{i}]: subject {s!r}")
        for s in r["linked_subjects"] + [x["holder"] for x in r["node_shares"]] + [x["group"] for x in r["node_shares"]]:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", s):
                p.append(f"input: identifier {s!r} must be lowercase letters, digits or _")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if not all(float(t).is_integer() for t in r["ptl_halt_window"]):
            p.append("input.ptl_halt_window: whole days")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, stays = run(r)
        res = checks(r, log, stays)
        msgs = log.messages()
        timeline = [{"day": m.arrived_at, "state": m.value["state"], "reason": m.value.get("reason")}
                    for m in msgs if m.source == "INTSEC" and m.kind == "notice" and "state" in m.value]
        outputs = {"states": timeline, "stays": stays,
                   "actions": [m.as_dict() for m in msgs if m.kind == "action"][:200],
                   "contained_days": sum(s["end"] - s["start"] for s in stays if s["state"] in ("S2", "S3", "S4")),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": "States: " + (", ".join(f"{t['state']} on day {t['day']}" + (" (expired)" if t["reason"] else "")
                                             for t in timeline) or "S0 throughout") + ".",
              "ru": "Состояния: " + (", ".join(f"{t['state']} в день {t['day']}" + (" (истёк срок)" if t["reason"] else "")
                                               for t in timeline) or "S0 всё время") + "."}]
        if any(t["reason"] for t in timeline):
            e.append({"en": f"Re-entry reading '{r['reentry_reading']}' (H-IS-2): containment in force on "
                            f"{outputs['contained_days']} days.",
                      "ru": f"Прочтение повторного входа '{r['reentry_reading']}' (H-IS-2): меры действовали "
                            f"{outputs['contained_days']} дней."})
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"contained_days": outputs["contained_days"], "state_changes": len(outputs["states"]),
                "actions": len(outputs["actions"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        compromise = [{"from_day": 3, "to_day": 13, "level": "active_compromise", "trigger": "audit", "subjects": ["s1"]}]
        return {
            "suspicion_then_violation": {},
            "persisting_compromise": {"evidence": compromise},
            "persisting_compromise_once": {"evidence": compromise, "reentry_reading": "episode_once"},
            "systemic": {"evidence": [{"from_day": 2, "to_day": 5, "level": "active_compromise", "trigger": "impact",
                                       "subjects": ["s1"]},
                                      {"from_day": 5, "to_day": 9, "level": "systemic", "trigger": "impact", "subjects": ["s1"]}]},
            "unconfirmed_prediction": {"evidence": [{"from_day": 2, "to_day": 8, "level": "violation", "ptl_confirmed": False,
                                                     "subjects": ["s9"]}]},
            "halt_during_violation": {"ptl_halt_window": [5, 9]},
            "concentrated_nodes": {"node_shares": [{"holder": "n1", "group": "g1", "share": 3},
                                                   {"holder": "n2", "group": "g1", "share": 2}]},
            "faulty_security": {"faults": ["collective_punishment", "mass_surveillance", "secret_rule", "missing_due_process",
                                           "ideological_justification"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"empty_episode": {"evidence": [{"from_day": 4, "to_day": 4, "level": "suspicion"}]},
                "bad_subject": {"linked_subjects": ["Robert'); DROP"]},
                "unknown_level": {"evidence": [{"from_day": 1, "to_day": 3, "level": "treason"}]}}
