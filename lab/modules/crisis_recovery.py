"""
CRISIS AND RECOVERY module — scenario S-LAB-06.

DKP-3-DEFENSE-001 (D0–D3, escalation, Resource Recovery Claim, wind-down) and DKP-4-ERROR-001
(systemic error escalation) → DKP-4-CRISIS-001 (PTL-anchored triggers, C0–C4, allowed and
prohibited actions, algorithmic governance, automatic exit, sequential recovery, transparency,
§12 epistemic classification, non-precedent) → exit to DKP-4-UPGRADE-001 or partition.
DKP-7-SCOPE-001 constraints are added when its registry entries exist.

What the texts leave open is declared, not assumed silently:
  * "sustained" D3 has no duration: CRISIS §6 forbids numbers in the protocol and defers them to
    DKP-8-SIMULATION-001, which gives none (open question Q-029); the duration is an input
    marked `missing`, and DEFENSE §5 ("mandatory escalation" at D3) is shown against it (F-010);
  * transitions among C1–C4 are not specified: hypothesis H-CR-1 maps the number and kind of
    active triggers to a state.
"""

from __future__ import annotations

from typing import Any, Dict, List

from lab.core.bus import EventLog, Message, epistemic_problems
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.run import canonical_json, sha256_text
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

HOURS_PER_DAY = 24
TRIGGERS = ("d3", "error_cascade", "ptl_divergence", "multi_domain")
FAULTS = {
    "forecast_entry": "crisis entered on a forecast before any PTL-confirmed trigger",
    "emergency_authority": "a discretionary emergency authority is granted to a group",
    "suspend_ptl_logging": "PTL logging is suspended during the crisis",
    "unlogged_human": "a human intervention is not logged as an external perturbation",
    "status_priority": "rationing gives priority by social status",
    "delayed_collapse": "crisis authority persists after the exit conditions hold",
    "finance_early": "financial execution resumes before Justice closes crisis claims",
    "valid_crisis_output": "crisis outputs are labelled VALID / SUFFICIENT_DATA",
    "cite_precedent": "a post-crisis decision cites a crisis action as justification",
    "no_broadcast": "no Final State Vector Broadcast in C3",
    "stale_confirmation": "crisis actions continue without refreshed PTL confirmation",
    "upgrade_during_crisis": "a protocol upgrade is activated while the crisis lasts",
}


def in_window(w, k):
    return int(w[0]) <= k < int(w[1])


def crisis_state(active: List[str]) -> str:
    """H-CR-1: no trigger -> C0; PTL divergence or three or more triggers -> C3; two -> C2; one -> C1."""
    if not active:
        return "C0"
    if "ptl_divergence" in active or len(active) >= 3:
        return "C3"
    return "C2" if len(active) == 2 else "C1"


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("hour", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}
    commits: Dict[str, str] = {}

    def dti(k):
        d = r["start_dti_day"] + k // HOURS_PER_DAY
        return {"dti_day": d, "dy": canonical(*dy_doy(d))}

    def put(kind, source, k, value, prov=(), epistemic=None):
        n["i"] += 1
        eid = f"{source.lower().replace('/', '-')}-{k:04d}-{n['i']:05d}"
        m = log.append(Message(event_id=eid, kind=kind, source=source, arrived_at=k,
                               measured_at=k if kind == "observation" else None,
                               decided_at=k if kind in ("decision", "action") else None,
                               value=value, epistemic=epistemic, provenance=tuple(prov), order=order[kind]))
        if kind == "action":
            commits[eid] = sha256_text(canonical_json(m.as_dict()))
        return m

    d3_run = 0
    in_crisis = False
    state = "C0"
    exit_step = None
    crisis_actions: List[str] = []
    claims_open = False
    authority_until = None
    broadcast_done = False
    layers_active = {"L0": True, "L1": True, "L2": True}
    rows = []
    for k in range(r["horizon_steps"]):
        confirmed = not in_window(r["confirmation_gap_window"], k)
        flags = {"d3": in_window(r["d3_window"], k), "error_cascade": in_window(r["error_cascade_window"], k),
                 "ptl_divergence": in_window(r["ptl_divergence_window"], k),
                 "multi_domain": in_window(r["multi_domain_window"], k)}
        ptl = None
        if not (in_crisis and "suspend_ptl_logging" in faults):
            ptl = put("observation", "PTL", k, {"confirmed": confirmed, **flags, **dti(k)})
        # DEFENSE: D3 only with refreshed confirmation; escalation request at D3
        level = "D3" if flags["d3"] and confirmed else ("D0" if not flags["d3"] else "D0")
        dmsg = put("evaluation", "DEFENSE", k, {"level": level, **dti(k)}, [ptl.event_id] if ptl else [])
        if level == "D3":
            d3_run += 1
            if d3_run == 1:
                put("notice", "DEFENSE", k, {"escalate_to": "DKP-4-CRISIS-001"}, [dmsg.event_id])
                if r["identifiable_harm_source"]:
                    put("notice", "DEFENSE", k, {"resource_recovery_claim": "routed to DKP-1-JUSTICE-001"}, [dmsg.event_id])
                    claims_open = True
        else:
            d3_run = 0
        if flags["error_cascade"] and confirmed:
            put("notice", "ERROR", k, {"escalate_to": "DKP-4-CRISIS-001", "reason": "systemic cascading error"},
                [ptl.event_id] if ptl else [])
        need = r["sustained_d3_steps"] if r["d3_reading"] == "sustained" else 1
        active = [t for t in TRIGGERS if (t == "d3" and d3_run >= need) or (t != "d3" and flags[t] and confirmed)]
        if "forecast_entry" in faults and not in_crisis and any(in_window(r[f"{t}_window"], k + 3) for t in TRIGGERS) \
                and not active:
            active = ["forecast"]
        exit_ok = not active and (not r["error_cascade_window"][1] > r["error_cascade_window"][0]
                                  or 0 <= r["error_correction_complete_step"] <= k)
        prev_state = state
        if active:
            in_crisis = True
            state = crisis_state([a for a in active if a != "forecast"]) if active != ["forecast"] else "C1"
        elif in_crisis and exit_ok and confirmed:
            in_crisis, state, exit_step = False, "C0", k
            if "delayed_collapse" in faults:
                authority_until = k + 6
        md = {"validity_state": "CONDITIONAL", "confidence_state": "SUFFICIENT_DATA" if confirmed else "DEGRADED_SIGNAL",
              "consistency_state": "ORACLE_CONFLICT" if flags["ptl_divergence"] else "CONSISTENT",
              "scope_ref": f"DKP-4-CRISIS-001:{state}", "revalidation_required": True, "dispute_allowed": True}
        if "valid_crisis_output" in faults:
            md = {**md, "validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA"}
        cmsg = put("evaluation", "CRISIS", k, {"state": state, "active_triggers": active, **dti(k)},
                   [ptl.event_id] if ptl else [], epistemic=md if state != "C0" else None)
        if in_crisis:
            if confirmed or "stale_confirmation" in faults:
                a = put("action", "CRISIS", k, {"action": "suspend_non_essential", "state": state, "time_limited": True,
                                                "reversible": True, "ends_at_exit": True, **dti(k)},
                        [cmsg.event_id], epistemic=md)
                crisis_actions.append(a.event_id)
                rule = "status" if "status_priority" in faults else r["allocation_rule"]
                put("action", "CRISIS", k, {"action": "ration", "rule": rule, "purpose": "life and core execution", **dti(k)},
                    [cmsg.event_id], epistemic=md)
            if state in ("C3", "C4") and not broadcast_done and "no_broadcast" not in faults:
                put("notice", "CRISIS", k, {"final_state_vector_broadcast": "external isolated archives"}, [cmsg.event_id])
                broadcast_done = True
            if "emergency_authority" in faults:
                put("notice", "GOVERNANCE", k, {"authority": "emergency council", "discretionary": True}, [cmsg.event_id])
            layers_active.update(L1=False, L2=False)
        if in_crisis and "upgrade_during_crisis" in faults and k == r["d3_window"][0] + 8:
            put("notice", "UPGRADE", k, {"activation": "emergency patch", "crisis_state": state}, [cmsg.event_id])
        if k == r["human_intervention_step"]:
            if "unlogged_human" in faults:
                put("action", "HUMAN", k, {"intervention": "manual rerouting"}, [cmsg.event_id])
            else:
                put("notice", "CRISIS", k, {"external_perturbation": "human intervention", "post_crisis_audit": True},
                    [cmsg.event_id])
        if authority_until is not None and k < authority_until:
            put("notice", "GOVERNANCE", k, {"authority": "crisis authority", "after_exit": True}, [cmsg.event_id])
        # sequential recovery after exit: L0 -> L1 -> L2; finance waits for Justice closure of crisis claims
        if exit_step is not None and not in_crisis:
            if k == exit_step:
                put("notice", "RECOVERY", k, {"reactivate": "L0", "pathway": r["exit_pathway"]}, [cmsg.event_id])
            if k == exit_step + 1:
                put("notice", "RECOVERY", k, {"reactivate": "L1"}, [cmsg.event_id])
                layers_active["L1"] = True
            if k >= exit_step + 2 and not layers_active["L2"]:
                closed = not claims_open or (0 <= r["justice_closure_step"] <= k)
                if closed or "finance_early" in faults:
                    put("notice", "RECOVERY", k, {"reactivate": "L2", "finance": "resumes",
                                                  "claims_closed": closed}, [cmsg.event_id])
                    layers_active["L2"] = True
            if k == r["upgrade_activation_step"] and r["exit_pathway"] == "upgrade":
                put("notice", "UPGRADE", k, {"activation": "DKP-4-UPGRADE-001 pathway", "crisis_state": state}, [cmsg.event_id])
            if k == r["post_crisis_decision_step"]:
                prov = [cmsg.event_id] + (crisis_actions[:1] if "cite_precedent" in faults else [])
                put("decision", "GOVERNANCE", k, {"decision": "routine allocation", "justification": "protocol rules"}, prov)
        rows.append({"step": k, "state": state, "defense": level, "active_triggers": active, "confirmed": confirmed,
                     "layers": dict(layers_active)})
    return log, rows, commits, {"exit_step": exit_step, "claims_open": claims_open}


def checks(r, log: EventLog, rows, commits, info) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []
    crisis_steps = [x["step"] for x in rows if x["state"] != "C0"]

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    ptl = {m.arrived_at: m for m in msgs if m.source == "PTL"}
    trig_ok = lambda k: k in ptl and ptl[k].value["confirmed"] and any(ptl[k].value[t] for t in TRIGGERS)
    # entry ---------------------------------------------------------------------------
    entries = [x["step"] for i, x in enumerate(rows) if x["state"] != "C0" and (i == 0 or rows[i - 1]["state"] == "C0")]
    if entries:
        bad = [k for k in entries if not trig_ok(k)]
        out.append(v("CRISIS-4-02", "no_discretionary_entry", bad, "every crisis entry follows a PTL-confirmed trigger",
                     "{n} crisis entries without a PTL-confirmed trigger (forecast or discretion)"))
        d3_entry = [k for k in entries if "d3" in rows[k]["active_triggers"]]
        if d3_entry:
            first_d3 = min(x["step"] for x in rows if x["defense"] == "D3")
            out.append(CheckResult("CRISIS-4-01", "ptl_confirmed_triggers", UNKNOWN,
                                   f"entry on 'sustained D3' needs a duration the corpus does not give (Q-029); computed "
                                   f"with {r['sustained_d3_steps'] if r['d3_reading'] == 'sustained' else 1} step(s): "
                                   f"DEFENSE escalated at step {first_d3}, crisis entered at step {d3_entry[0]} (F-010)",
                                   evidence={"defense_escalation": first_d3, "crisis_entry": d3_entry[0]}))
        else:
            out.append(v("CRISIS-4-01", "ptl_confirmed_triggers", bad,
                         "crisis entered on PTL-confirmed triggers listed in §4", "{n} entries on unlisted triggers"))
    else:
        out.append(na("CRISIS-4-02", "no_discretionary_entry", "crisis entry", "no crisis in this experiment"))
        out.append(na("CRISIS-4-01", "ptl_confirmed_triggers", "crisis entry", "no crisis in this experiment"))
    bad = [x["step"] for x in rows if x["state"] not in ("C0", "C1", "C2", "C3", "C4")] + \
          [m.event_id for m in msgs if m.source == "CRISIS" and m.kind == "evaluation" and "dti_day" not in m.value]
    out.append(v("CRISIS-5-01", "finite_dti_states", bad, "crisis states are C0–C4, each indexed by DTI-Day",
                 "{n} states outside C0–C4 or without DTI index"))
    if not crisis_steps:
        for rid, chk in (("CRISIS-5-07", "persistence_needs_confirmation"), ("CRISIS-7-01", "logging_no_authority"),
                         ("CRISIS-7-03", "no_status_priority"), ("CRISIS-7-04", "allocation_basis"),
                         ("CRISIS-6-04", "action_qualities"), ("CRISIS-10-01", "actions_anchored_committed"),
                         ("CRISIS-12.1-01", "conditional_outputs"), ("CRISIS-12.1-02", "scope_ref_flags"),
                         ("CRISIS-10-02", "final_state_broadcast"), ("CRISIS-9-01", "automatic_exit"),
                         ("CRISIS-9-05", "immediate_collapse"), ("CRISIS-9-02", "sequential_recovery"),
                         ("CRISIS-Non-PrecedentRule_-01", "no_precedent"), ("CRISIS-8-02", "human_logged")):
            out.append(na(rid, chk, "crisis execution", "no crisis in this experiment"))
        return out + defense_checks(r, log, rows, msgs, v, na)
    cs = set(crisis_steps)
    actions = [m for m in msgs if m.kind == "action" and m.source == "CRISIS"]
    unconfirmed = [m.event_id for m in actions if not rows[m.arrived_at]["confirmed"]]
    out.append(v("CRISIS-5-07", "persistence_needs_confirmation", unconfirmed,
                 "crisis actions only in steps with refreshed PTL confirmation", "{n} crisis actions without refreshed confirmation"))
    gaps = [k for k in cs if k not in ptl]
    authority = [m.event_id for m in msgs if m.source == "GOVERNANCE" and m.kind == "notice" and m.arrived_at in cs]
    out.append(v("CRISIS-7-01", "logging_no_authority", gaps + authority,
                 "PTL logging continued in every crisis step; no discretionary authority granted",
                 "{n} crisis steps without PTL logging or with a discretionary authority"))
    rations = [m for m in actions if m.value.get("action") == "ration"]
    out.append(v("CRISIS-7-03", "no_status_priority", [m.event_id for m in rations if m.value["rule"] == "status"],
                 "no allocation by social status, historical impact or perceived utility", "{n} allocations by status"))
    out.append(v("CRISIS-7-04", "allocation_basis", [m.event_id for m in rations if m.value["rule"] not in ("egalitarian", "proximity")],
                 f"allocation is {r['allocation_rule']} (egalitarian minimum or physical proximity)",
                 "{n} allocations on another basis"))
    bad = [m.event_id for m in actions if m.value.get("action") == "suspend_non_essential"
           and not (m.value["time_limited"] and m.value["reversible"] and m.value["ends_at_exit"])]
    out.append(v("CRISIS-6-04", "action_qualities", bad, "crisis actions are time-limited, reversible and audited",
                 "{n} crisis actions not time-limited or not reversible"))
    bad = [m.event_id for m in actions if not m.provenance or "dti_day" not in m.value
           or commits.get(m.event_id) != sha256_text(canonical_json(m.as_dict()))]
    out.append(v("CRISIS-10-01", "actions_anchored_committed", bad,
                 "every crisis action is PTL-anchored (provenance), DTI-indexed and committed (digest)",
                 "{n} crisis actions not anchored, indexed or committed"))
    outs = [m for m in msgs if m.source == "CRISIS" and m.epistemic is not None]
    out.append(v("CRISIS-12.1-01", "conditional_outputs", [m.event_id for m in outs if m.epistemic["validity_state"] != "CONDITIONAL"],
                 "every crisis output is CONDITIONAL", "{n} crisis outputs not CONDITIONAL"))
    out.append(v("CRISIS-12.1-02", "scope_ref_flags", [m.event_id for m in outs if epistemic_problems(m.epistemic)
                 or not m.epistemic["scope_ref"].startswith("DKP-4-CRISIS-001:C") or m.epistemic["revalidation_required"] is not True
                 or m.epistemic["dispute_allowed"] is not True],
                 "crisis outputs carry scope_ref DKP-4-CRISIS-001:C[n], revalidation_required and dispute_allowed TRUE",
                 "{n} crisis outputs with wrong metadata"))
    c3 = [x["step"] for x in rows if x["state"] in ("C3", "C4")]
    if c3:
        sent = any(m.value.get("final_state_vector_broadcast") for m in msgs if m.source == "CRISIS")
        out.append(v("CRISIS-10-02", "final_state_broadcast", [] if sent else c3[:1],
                     "Final State Vector Broadcast initiated in C3", "no Final State Vector Broadcast in C3/C4"))
    else:
        out.append(na("CRISIS-10-02", "final_state_broadcast", "Final State Vector Broadcast", "no C3 or C4 state"))
    human = [m for m in msgs if m.source == "HUMAN"]
    if r["human_intervention_step"] >= 0:
        logged = [m for m in msgs if m.value and m.value.get("external_perturbation")]
        out.append(v("CRISIS-8-02", "human_logged", [m.event_id for m in human] if not logged else [],
                     "the human intervention is logged as an external perturbation for post-crisis audit",
                     "{n} human interventions executed without being logged as perturbations"))
    else:
        out.append(na("CRISIS-8-02", "human_logged", "human intervention", "no human intervention declared"))
    ex = info["exit_step"]
    if ex is not None:
        # independent: first step after the last crisis step where no trigger is active and ERROR correction is complete
        out.append(v("CRISIS-9-01", "automatic_exit", [] if rows[ex - 1]["state"] != "C0" else [ex],
                     f"crisis terminated automatically at step {ex}, when the exit conditions were confirmed",
                     "exit not at the confirmed restoration"))
        lingering = [m.event_id for m in msgs if m.source == "GOVERNANCE" and m.kind == "notice" and m.arrived_at >= ex]
        out.append(v("CRISIS-9-05", "immediate_collapse", lingering, "all crisis authority ended at the exit step",
                     "{n} notices of crisis authority after exit"))
        rec = {m.value["reactivate"]: m.arrived_at for m in msgs if m.source == "RECOVERY"}
        order_ok = rec.get("L0", -1) <= rec.get("L1", 10 ** 9) <= rec.get("L2", 10 ** 9)
        fin = [m for m in msgs if m.source == "RECOVERY" and m.value.get("reactivate") == "L2"]
        early = [m.event_id for m in fin if info["claims_open"] and not m.value["claims_closed"]]
        out.append(v("CRISIS-9-02", "sequential_recovery", ([] if order_ok else ["order"]) + early,
                     "recovery L0 → L1 → L2; finance resumed only after Justice closed crisis claims",
                     "{n} violations of sequential recovery or early finance"))
        cited = [m.event_id for m in msgs if m.kind == "decision" and m.source == "GOVERNANCE"
                 and any(log.get(p).kind == "action" and log.get(p).source == "CRISIS" for p in m.provenance)]
        out.append(v("CRISIS-Non-PrecedentRule_-01", "no_precedent", cited,
                     "no post-crisis decision cites a crisis action", "{n} post-crisis decisions cite crisis actions"))
    else:
        for rid, chk in (("CRISIS-9-01", "automatic_exit"), ("CRISIS-9-05", "immediate_collapse"),
                         ("CRISIS-9-02", "sequential_recovery"), ("CRISIS-Non-PrecedentRule_-01", "no_precedent")):
            out.append(na(rid, chk, "crisis exit", "the crisis does not end within the horizon"))
    return out + defense_checks(r, log, rows, msgs, v, na)


SCOPE_MIRRORS = [("CRISIS-4-02", "SCOPE-5-02", "crisis_entry_by_state_machine"),
                 ("CRISIS-9-05", "SCOPE-5-12", "exit_collapses_to_s0"),
                 ("CRISIS-9-05", "SCOPE-6-04", "stabilization_restores_baseline"),
                 ("CRISIS-Non-PrecedentRule_-01", "SCOPE-3-08", "s1_no_precedent"),
                 ("CRISIS-6-04", "SCOPE-3-04", "s1_time_limited")]


def scope_mirrors(results: List[CheckResult]) -> List[CheckResult]:
    """SCOPE §3, §5, §6 constrain the same crisis execution; each mirrors one CRISIS check."""
    by = {c.requirement_id: c for c in results}
    out = []
    for src, rid, chk in SCOPE_MIRRORS:
        c = by[src]
        out.append(CheckResult(rid, chk, c.status, f"{c.explanation} (as checked for {src})", evidence=c.evidence,
                               applicability=c.applicability))
    return out


def defense_checks(r, log, rows, msgs, v, na) -> List[CheckResult]:
    out = []
    # ERROR §9: a systemic or cascading error escalates to CRISIS automatically
    lo, hi = r["error_cascade_window"]
    if hi > lo:
        esc = [m.arrived_at for m in msgs if m.source == "ERROR" and m.value.get("escalate_to")]
        first = next((x["step"] for x in rows if lo <= x["step"] < hi and x["confirmed"]), None)
        out.append(v("ERROR-9-05", "systemic_error_escalates", [] if first is None or (esc and esc[0] == first) else [first],
                     "the cascading error escalated to CRISIS at its first confirmed hour", "no automatic escalation"))
    else:
        out.append(na("ERROR-9-05", "systemic_error_escalates", "systemic error escalation", "no cascading error"))
    # UPGRADE §2, §11: no upgrade operation while a crisis state C1-C4 holds
    ups = [m for m in msgs if m.source == "UPGRADE"]
    bad = [m.event_id for m in ups if rows[m.arrived_at]["state"] != "C0"]
    for rid, chk in (("UPGRADE-2-05", "no_upgrade_in_crisis"), ("UPGRADE-11-01", "no_emergency_upgrade")):
        out.append(v(rid, chk, bad, f"{len(ups)} upgrade activation(s), none during a crisis state" if ups else
                     "no upgrade operation during the crisis", "{n} upgrade operations during a crisis state"))
    d3 = [x["step"] for x in rows if x["defense"] == "D3"]
    if d3:
        esc = [m.arrived_at for m in msgs if m.source == "DEFENSE" and m.kind == "notice" and m.value.get("escalate_to")]
        out.append(v("DEFENSE-9-01", "escalation_to_crisis", [] if esc and esc[0] == d3[0] else [d3[0]],
                     f"Defense requested escalation to CRISIS at the first D3 step ({d3[0]})", "no escalation at D3"))
        unconf = [k for k in d3 if not rows[k]["confirmed"]]
        out.append(v("DEFENSE-5-02", "d3_needs_confirmation", unconf, "D3 held only with refreshed PTL confirmation",
                     "{n} D3 steps without confirmation"))
        if r["identifiable_harm_source"]:
            claim = [m for m in msgs if m.source == "DEFENSE" and m.value.get("resource_recovery_claim")]
            out.append(v("DEFENSE-8-02", "resource_recovery_claim", [] if claim else [d3[0]],
                         "an identifiable harm source produced a Resource Recovery Claim routed to JUSTICE",
                         "no Resource Recovery Claim"))
        else:
            out.append(na("DEFENSE-8-02", "resource_recovery_claim", "Resource Recovery Claim", "no identifiable harm source"))
        after = [x["step"] for x in rows if x["step"] > d3[-1] and x["defense"] != "D0"]
        out.append(v("DEFENSE-8-04", "wind_down", after, "Defense wound down when the harm stream ceased",
                     "{n} steps of defense after the harm ceased"))
    else:
        for rid, chk in (("DEFENSE-9-01", "escalation_to_crisis"), ("DEFENSE-5-02", "d3_needs_confirmation"),
                         ("DEFENSE-8-02", "resource_recovery_claim"), ("DEFENSE-8-04", "wind_down")):
            out.append(na(rid, chk, "defense escalation", "no D3 state in this experiment"))
    return out


IMPLEMENTS = {
    "CRISIS-4-01": ("ptl_confirmed_triggers", "PARTIAL", "'Sustained' has no duration (Q-029); D3 entry gives UNKNOWN (F-010)."),
    "CRISIS-4-02": ("no_discretionary_entry", "IMPLEMENTED", None),
    "CRISIS-5-01": ("finite_dti_states", "PARTIAL", "Transitions among C1–C4 are a hypothesis (H-CR-1)."),
    "CRISIS-5-07": ("persistence_needs_confirmation", "PARTIAL", "Revalidation cadence is not defined (Q-029)."),
    "CRISIS-6-04": ("action_qualities", "PARTIAL", "Proportionality to the threat is not measurable here."),
    "CRISIS-7-01": ("logging_no_authority", "IMPLEMENTED", None),
    "CRISIS-7-03": ("no_status_priority", "IMPLEMENTED", None),
    "CRISIS-7-04": ("allocation_basis", "IMPLEMENTED", None),
    "CRISIS-8-02": ("human_logged", "IMPLEMENTED", None),
    "CRISIS-9-01": ("automatic_exit", "PARTIAL", "Exit conditions are scenario inputs confirmed by PTL messages."),
    "CRISIS-9-02": ("sequential_recovery", "IMPLEMENTED", None),
    "CRISIS-9-05": ("immediate_collapse", "IMPLEMENTED", None),
    "CRISIS-10-01": ("actions_anchored_committed", "IMPLEMENTED", None),
    "CRISIS-10-02": ("final_state_broadcast", "PARTIAL", "The broadcast is a logged notice; the external archive is not modelled."),
    "CRISIS-12.1-01": ("conditional_outputs", "PARTIAL", "Confidence and consistency are propagated from the scenario's PTL flags."),
    "CRISIS-12.1-02": ("scope_ref_flags", "IMPLEMENTED", None),
    "CRISIS-Non-PrecedentRule_-01": ("no_precedent", "PARTIAL", "Precedent is detected as citation (provenance) of a crisis action."),
    "DEFENSE-5-02": ("d3_needs_confirmation", "IMPLEMENTED", None),
    "DEFENSE-8-02": ("resource_recovery_claim", "IMPLEMENTED", None),
    "DEFENSE-8-04": ("wind_down", "PARTIAL", "Admissible-state restoration is the end of the harm window."),
    "DEFENSE-9-01": ("escalation_to_crisis", "IMPLEMENTED", None),
    "ERROR-9-05": ("systemic_error_escalates", "PARTIAL", "'Protocol-defined threshold' of affected Subjects is not modelled; the cascade is a declared window."),
    "UPGRADE-2-05": ("no_upgrade_in_crisis", "IMPLEMENTED", None),
    "UPGRADE-11-01": ("no_emergency_upgrade", "IMPLEMENTED", None),
    "SCOPE-5-02": ("crisis_entry_by_state_machine", "IMPLEMENTED", None),
    "SCOPE-5-12": ("exit_collapses_to_s0", "IMPLEMENTED", None),
    "SCOPE-6-04": ("stabilization_restores_baseline", "PARTIAL", "Baseline = absence of crisis authority notices after exit."),
    "SCOPE-3-08": ("s1_no_precedent", "PARTIAL", "Precedent detected as citation of a crisis action."),
    "SCOPE-3-04": ("s1_time_limited", "PARTIAL", "Crisis actions end at exit; no numeric time limit exists (Q-029)."),
}


class CrisisRecoveryModule(LabModule):
    id = "crisis_recovery"
    version = "1.0.0"
    title = {"en": "Crisis and recovery (S-LAB-06)", "ru": "Кризис и восстановление (S-LAB-06)"}
    summary = {"en": "An existential threat or a cascading failure: does the system enter crisis only on PTL evidence, "
                     "keep logging, grant no one power, leave by itself and recover layer by layer?",
               "ru": "Угроза существованию или каскадный отказ: входит ли система в кризис только по данным PTL, "
                     "продолжает ли журнал, не даёт ли кому-то власти, выходит ли сама и восстанавливается по слоям?"}
    protocols = ["DKP-4-CRISIS-001", "DKP-3-DEFENSE-001", "DKP-4-ERROR-001", "DKP-4-UPGRADE-001", "DKP-7-SCOPE-001"]
    example_order = ["d3_sustained", "d3_immediate", "cascade_and_divergence", "faulty_crisis", "no_crisis"]
    alternative_examples = ["d3_immediate"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_crisis_recovery_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-CR-1", "source": "hypothesis", "text": {
            "en": "Crisis state from active triggers: none C0; one C1; two C2; PTL divergence or three or more C3. "
                  "C4 is not entered automatically. The text names the states but not their transitions.",
            "ru": "Состояние кризиса по активным триггерам: нет — C0; один — C1; два — C2; расхождение PTL или три и "
                  "более — C3. C4 автоматически не наступает. Текст называет состояния, но не переходы."}},
        {"id": "H-CR-2", "source": "missing", "text": {
            "en": "'Sustained' D3 = D3 for the declared number of steps; the corpus gives no duration (CRISIS §6 forbids "
                  "numbers and defers them to DKP-8-SIMULATION-001).",
            "ru": "'Устойчивое' D3 = D3 в течение объявленного числа шагов; корпус длительности не даёт (CRISIS §6 "
                  "запрещает числа и отсылает к DKP-8-SIMULATION-001)."}},
        {"id": "H-CR-3", "source": "alternative", "text": {
            "en": "'immediate' reading: crisis is entered at the first D3 step, as DEFENSE §5 ('mandatory escalation') "
                  "would require; 'sustained' is the CRISIS §4 wording.",
            "ru": "Прочтение 'immediate': кризис наступает на первом шаге D3, как требовал бы DEFENSE §5 "
                  "('обязательная эскалация'); 'sustained' — формулировка CRISIS §4."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of step 0", "ru": "DTI-Day шага 0"}},
        "horizon_steps": {"type": "int", "min": 2, "max": 5000, "default": 96, "unit": "h", "source": "user",
                          "label": {"en": "Hours", "ru": "Часов"}},
        "d3_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [10, 40], "unit": "h", "source": "user",
                      "label": {"en": "Existential threat (D3) from/to hour", "ru": "Угроза существованию (D3) с/до часа"}},
        "error_cascade_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "h", "source": "user",
                                 "label": {"en": "Cascading systemic error from/to hour", "ru": "Каскадная ошибка с/до часа"}},
        "ptl_divergence_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "h", "source": "user",
                                  "label": {"en": "PTL divergence from/to hour", "ru": "Расхождение PTL с/до часа"}},
        "multi_domain_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "h", "source": "user",
                                "label": {"en": "Multi-domain harm from/to hour", "ru": "Многодоменный вред с/до часа"}},
        "confirmation_gap_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "h", "source": "user",
                                    "label": {"en": "No refreshed PTL confirmation from/to hour", "ru": "Нет подтверждения PTL с/до часа"}},
        "d3_reading": {"type": "enum", "values": ["sustained", "immediate"], "default": "sustained", "source": "alternative",
                       "label": {"en": "Crisis entry on D3 (H-CR-3)", "ru": "Вход в кризис при D3 (H-CR-3)"}},
        "sustained_d3_steps": {"type": "int", "min": 1, "max": 10 ** 4, "default": 6, "unit": "h", "source": "missing",
                               "label": {"en": "'Sustained' D3 lasts (H-CR-2; not in the corpus)", "ru": "'Устойчивое' D3 длится (H-CR-2; нет в корпусе)"}},
        "error_correction_complete_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "h", "source": "user",
                                           "label": {"en": "ERROR confirms correction at hour (-1: never)",
                                                     "ru": "ERROR подтверждает исправление в час (-1: никогда)"}},
        "identifiable_harm_source": {"type": "bool", "default": True, "source": "user",
                                     "label": {"en": "Identifiable external harm source", "ru": "Источник вреда установлен"}},
        "justice_closure_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 60, "unit": "h", "source": "user",
                                 "label": {"en": "Justice closes crisis claims at hour (-1: never)",
                                           "ru": "Justice закрывает претензии кризиса в час (-1: никогда)"}},
        "allocation_rule": {"type": "enum", "values": ["egalitarian", "proximity"], "default": "egalitarian", "source": "text",
                            "label": {"en": "Rationing basis (CRISIS §7)", "ru": "Основа распределения (CRISIS §7)"}},
        "human_intervention_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 20, "unit": "h", "source": "user",
                                    "label": {"en": "Human intervention at hour (-1: none)", "ru": "Вмешательство человека в час (-1: нет)"}},
        "post_crisis_decision_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 80, "unit": "h", "source": "user",
                                      "label": {"en": "Routine decision after the crisis at hour", "ru": "Обычное решение после кризиса в час"}},
        "upgrade_activation_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 70, "unit": "h", "source": "user",
                                    "label": {"en": "Upgrade activation at hour (pathway 'upgrade')", "ru": "Активация обновления в час (путь 'upgrade')"}},
        "exit_pathway": {"type": "enum", "values": ["soft_reset", "upgrade", "partition"], "default": "soft_reset", "source": "user",
                         "label": {"en": "Exit pathway (CRISIS §9)", "ru": "Путь выхода (CRISIS §9)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = [f"input.{k}: whole hours" for k in ("d3_window", "error_cascade_window", "ptl_divergence_window",
                                                  "multi_domain_window", "confirmation_gap_window")
             if not all(float(x).is_integer() for x in r[k])]
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, rows, commits, info = run(r)
        res = checks(r, log, rows, commits, info)
        res += scope_mirrors(res)
        states = [x["state"] for x in rows]
        d3 = [x["step"] for x in rows if x["defense"] == "D3"]
        entry = next((x["step"] for x in rows if x["state"] != "C0"), None)
        outputs = {"states": rows, "crisis_hours": sum(1 for s in states if s != "C0"), "max_state": max(states),
                   "defense_escalation_hour": d3[0] if d3 else None, "crisis_entry_hour": entry,
                   "exit_hour": info["exit_step"],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        explain = [{"en": f"Crisis in {outputs['crisis_hours']} of {len(rows)} hours; highest state {outputs['max_state']} "
                          f"(H-CR-1); exit at hour {info['exit_step']}.",
                    "ru": f"Кризис {outputs['crisis_hours']} из {len(rows)} часов; наивысшее состояние {outputs['max_state']} "
                          f"(H-CR-1); выход в час {info['exit_step']}."}]
        if d3 and entry is not None and entry > d3[0]:
            explain.append({"en": f"DEFENSE escalated at hour {d3[0]} (D3: 'mandatory escalation'); CRISIS entered at hour "
                                  f"{entry} after 'sustained' D3 of a declared {r['sustained_d3_steps']} h (F-010).",
                            "ru": f"DEFENSE эскалировал в час {d3[0]} (D3: 'обязательная эскалация'); CRISIS наступил в час "
                                  f"{entry} после 'устойчивого' D3 объявленной длительности {r['sustained_d3_steps']} ч (F-010)."})
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"crisis_hours": outputs["crisis_hours"], "max_state": outputs["max_state"],
                "escalation_to_entry_hours": (outputs["crisis_entry_hour"] - outputs["defense_escalation_hour"])
                if outputs["crisis_entry_hour"] is not None and outputs["defense_escalation_hour"] is not None else None,
                "exit_hour": outputs["exit_hour"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "d3_sustained": {},
            "d3_immediate": {"d3_reading": "immediate"},
            "cascade_and_divergence": {"d3_window": [0, 0], "error_cascade_window": [10, 30], "ptl_divergence_window": [20, 26],
                                       "error_correction_complete_step": 32, "identifiable_harm_source": False},
            "faulty_crisis": {"faults": ["forecast_entry", "emergency_authority", "status_priority", "delayed_collapse",
                                         "finance_early", "cite_precedent", "unlogged_human"]},
            "no_crisis": {"d3_window": [0, 0], "human_intervention_step": -1},
            "exit_to_upgrade": {"exit_pathway": "upgrade"},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"fractional_window": {"d3_window": [1.5, 3]}, "unknown_fault": {"faults": ["martial_law"]}}
