"""
EXIT AND INTEGRATION module — scenario S-LAB-07.

DKP-6-INTEGRATION-001 (consent, phases 0–3 with explicit validations, no automatic progression,
shock halt and rollback, no retroactive enforcement) → DKP-6-EXIT-001 (declaration without
approval, cooling period, declared phases, restitution tail, delayed settlement of
system-critical assets, data freeze, re-entry) with DKP-2-FINANCE-001 settlement, DKP-2-ASSETS-001
and DKP-7-SCOPE-001 §9 (exit guarantees) when its registry entries exist.

Time is in DTI-Days.  Two pairs of texts disagree, and the module computes either reading:
  * EXIT §6 delays execution by a cooling period "to prevent cascading instability"; SCOPE §9:
    "exit SHALL NOT be delayed for optimization or stability goals" (finding F-011);
  * EXIT §4: exit "SHALL NOT be revoked or suspended"; SCOPE §9: not suspended "except temporarily
    within Crisis Scope to preserve immediate life" (finding F-012).
The cooling period length is "calibrated exclusively under DKP-8-SIMULATION-001", which gives none:
it is an input marked `missing`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

PHASES = (0, 1, 2, 3)
EXIT_PHASES = ["governance", "enforcement", "financial_settlement", "data_separation"]
LIABILITY_KINDS = ("verified_harm", "accepted_contract", "measured_impact_cost", "ideological", "punitive", "projected")
ADMISSIBLE_TAIL = ("verified_harm", "accepted_contract", "measured_impact_cost")       # EXIT §9
FAULTS = {
    "auto_progression": "a phase is entered without an explicit validation",
    "skip_phase": "phase 1 is skipped",
    "phase0_effects": "Shadow Mode produces an enforcement effect",
    "shock_ignored": "integration shock neither halts progression nor suspends enforcement",
    "retroactive": "an event from before Phase 2 is enforced after Phase 2 starts",
    "require_approval": "exit needs an approval vote",
    "punitive_tail": "punitive or projected items are added to the restitution tail",
    "post_declaration_obligation": "a new obligation is created after the exit declaration",
    "collect_after_exit": "data collection continues after exit",
    "reentry_penalty": "re-entry is delayed because of the earlier exit",
    "protocol_bound_settlement": "the exit settlement is paid only in protocol-bound form",
}

LIAB = {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 10 ** 6},
                                     "kind": {"type": "enum", "values": list(LIABILITY_KINDS)},
                                     "verified": {"type": "bool", "default": True}}}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def dti(k):
        d = r["start_dti_day"] + k
        return {"dti_day": d, "dy": canonical(*dy_doy(d))}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:05d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=k, decided_at=k if kind in ("decision", "action") else None,
                                  value={**value, **dti(k)}, provenance=tuple(prov), order=order[kind]))

    rows = []
    phase = None
    consent = None
    exit_decl = exit_exec = None
    validations = {p: d for p, d in zip((1, 2, 3), r["phase_entry_days"])}
    if "skip_phase" in faults:
        validations[1] = -1
    halted = False
    impact_events = []
    reentry_day = None
    decl_msg = None
    for k in range(r["horizon_days"]):
        if k == r["consent_day"]:
            consent = put("notice", "INTEGRATION", k, {"consent": "charter ratification", "ptl_access": r["ptl_access_agreement"]})
            if r["ptl_access_agreement"]:
                phase = 0
                put("notice", "INTEGRATION", k, {"phase": 0, "scope": "read-only", "enforceable": False, "validated_by": "consent"},
                    [consent.event_id])
        shock = r["shock_window"][1] > r["shock_window"][0] and r["shock_window"][0] <= k < r["shock_window"][1]
        if shock and phase is not None and phase >= 1 and "shock_ignored" not in faults:
            if not halted:
                put("notice", "INTEGRATION", k, {"shock": True, "progression": "halted", "enforcement": "suspended"})
                halted = True
                if r["rollback_on_shock"] and phase >= 1:
                    phase -= 1
                    put("notice", "INTEGRATION", k, {"rollback_to": phase, "scope": "declared", "cost": "logged"})
        elif not shock:
            halted = False
        # forward progression only on explicit validation days, sequentially
        if phase is not None and exit_decl is None and not halted:
            nxt = phase + 1
            if nxt in validations and validations[nxt] == k:
                put("notice", "INTEGRATION", k, {"phase": nxt, "validated_by": f"phase {phase} exit validation",
                                                 "scope": r["phase2_domains"] if nxt == 2 else ("advisory" if nxt == 1 else "full"),
                                                 "enforceable": nxt >= 2})
                phase = nxt
            elif "auto_progression" in faults and nxt in validations and validations[nxt] >= 0 and k == validations[nxt] - 3:
                put("notice", "INTEGRATION", k, {"phase": nxt, "scope": "auto", "enforceable": nxt >= 2})
                phase = nxt
            elif "skip_phase" in faults and phase == 0 and validations[2] == k:
                put("notice", "INTEGRATION", k, {"phase": 2, "validated_by": "phase 0 exit validation",
                                                 "scope": r["phase2_domains"], "enforceable": True})
                phase = 2
        # impact events and their enforcement (only in Phase >= 2, within declared domains, not retroactive)
        for ev_day, domain in r["impact_events"]:
            if ev_day == k:
                m = put("observation", "PTL", k, {"impact": domain})
                impact_events.append((k, domain, m.event_id, phase))
        enforcing = phase is not None and phase >= 2 and not halted and exit_exec is None
        for (d, domain, eid, ph) in impact_events:
            if d == k and enforcing and (phase == 3 or domain in r["phase2_domains"]):
                put("action", "ENFORCEMENT", k, {"enforce": domain, "phase": phase}, [eid])
        if "retroactive" in faults and phase == 2 and validations.get(2) == k:
            old = [e for e in impact_events if e[3] is not None and e[3] < 2]
            for (d, domain, eid, ph) in old[:1]:
                put("action", "ENFORCEMENT", k, {"enforce": domain, "phase": phase, "retroactive": True}, [eid])
        if "phase0_effects" in faults and phase == 0 and k == r["consent_day"] + 1:
            put("action", "ENFORCEMENT", k, {"enforce": "advisory penalty", "phase": 0})
        # exit -------------------------------------------------------------------------
        if k == r["exit_declaration_day"]:
            exit_decl = k
            decl_msg = put("notice", "EXIT", k, {"declaration": "signed", "scope": r["exit_scope"], "ptl_timestamp": True,
                                                 "approval_required": "require_approval" in faults,
                                                 "phases": list(EXIT_PHASES), "phase_days": r["exit_phase_days"],
                                                 "cooling_days": r["cooling_days"]})
        if exit_decl is not None and exit_exec is None:
            crisis = r["crisis_window"][0] <= k < r["crisis_window"][1]
            paused = crisis and r["crisis_exit_reading"] == "scope_crisis_suspension"
            if paused:
                put("notice", "EXIT", k, {"exit": "suspended temporarily within Crisis Scope"}, [decl_msg.event_id])
            due = exit_decl + r["cooling_days"] + sum(r["exit_phase_days"]) + paused_days(r, exit_decl, k)
            if "require_approval" in faults:
                due += 3
            if r["system_critical_asset"]:
                due = max(due, exit_decl + r["cooling_days"] + r["critical_settlement_days"])
            if k == exit_decl + r["cooling_days"]:
                acc = exit_decl + r["cooling_days"]
                for name, days in zip(EXIT_PHASES, r["exit_phase_days"]):
                    put("notice", "EXIT", acc, {"phase_start": name}, [decl_msg.event_id]) if acc == k else None
                    acc += days
            if k == exit_decl + r["cooling_days"] + sum(r["exit_phase_days"][:2]):
                form = "protocol-bound units" if "protocol_bound_settlement" in faults else "detachable equivalent"
                put("action", "FINANCE", k, {"settlement": "per DKP-2-FINANCE-001", "assets": form,
                                             "requires_continued_dkp": "protocol_bound_settlement" in faults},
                    [decl_msg.event_id])
            if r["system_critical_asset"] and k == exit_decl + r["cooling_days"]:
                put("notice", "EXIT", k, {"delayed_settlement": "system-critical asset", "bounded_days": r["critical_settlement_days"],
                                          "compensated": True, "logged": True}, [decl_msg.event_id])
            if k >= due and not paused:
                exit_exec = k
                put("notice", "EXIT", k, {"executed": True, "authority": "terminated", "data": "frozen and archived"},
                    [decl_msg.event_id])
        # restitution tail: only verified liabilities incurred before the declaration
        if exit_decl is not None and k == exit_decl:
            for i, li in enumerate(r["liabilities"]):
                admissible = li["kind"] in ADMISSIBLE_TAIL and li["verified"] and li["day"] < exit_decl
                if admissible or ("punitive_tail" in faults and li["kind"] in ("punitive", "projected")):
                    put("notice", "RESTITUTION", k, {"tail_item": i, "kind": li["kind"], "incurred_day": li["day"]},
                        [decl_msg.event_id])
        if "post_declaration_obligation" in faults and exit_decl is not None and k == exit_decl + 1:
            put("notice", "RESTITUTION", k, {"tail_item": "new", "kind": "service fee", "incurred_day": k}, [decl_msg.event_id])
        if exit_exec is not None and k > exit_exec and "collect_after_exit" in faults:
            put("observation", "PTL", k, {"collected": "operational data"})
        if k == r["reapply_day"] and exit_exec is not None:
            ready = r["restitution_resolved_day"] <= k
            delay = 30 if "reentry_penalty" in faults else 0
            reentry_day = k + delay if ready else None
            put("notice", "INTEGRATION", k, {"reapply": True, "accepted_from_day": reentry_day,
                                             "delay_for_exit_history": delay, "restitution_resolved": ready})
        rows.append({"day": k, "phase": phase, "halted": halted, "exit_declared": exit_decl is not None,
                     "exit_executed": exit_exec is not None})
    return log, rows, {"exit_decl": exit_decl, "exit_exec": exit_exec, "consent": consent is not None}


def paused_days(r, decl, k):
    lo, hi = r["crisis_window"]
    if r["crisis_exit_reading"] != "scope_crisis_suspension" or hi <= lo:
        return 0
    return max(0, min(hi, k + 1) - max(lo, decl))


def checks(r, log: EventLog, rows, info) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    integ = [m for m in msgs if m.source == "INTEGRATION"]
    phase_msgs = [m for m in integ if "phase" in m.value]
    enf = [m for m in msgs if m.source == "ENFORCEMENT"]
    # INTEGRATION -----------------------------------------------------------------------
    if phase_msgs:
        out.append(v("INTEGRATION-4.1-01", "explicit_consent", [] if info["consent"] else ["no consent"],
                     "integration started from an explicit, auditable consent", "integration without consent"))
        seq = [m.value["phase"] for m in phase_msgs]
        bad = [f"{a}->{b}" for a, b in zip(seq, seq[1:]) if b > a + 1]
        out.append(v("INTEGRATION-4.2-01", "sequential_phases", bad + [m.event_id for m in phase_msgs if "validated_by" not in m.value],
                     f"phases entered in order {seq}, none skipped, none automatic", "{n} skipped or automatic phase entries"))
        out.append(v("INTEGRATION-4.2-02", "explicit_validation", [m.event_id for m in phase_msgs if "validated_by" not in m.value],
                     "every phase entry carries an explicit validation", "{n} phase entries without validation"))
        bad = [m.event_id for m in enf if rows[m.arrived_at]["phase"] == 0 or m.value.get("phase") == 0]
        out.append(v("INTEGRATION-5.1-01", "shadow_mode_no_effects", bad, "Shadow Mode produced no enforcement",
                     "{n} enforcement effects in Shadow Mode"))
        bad = [m.event_id for m in enf if m.value.get("phase") == 2 and m.value["enforce"] not in r["phase2_domains"]]
        out.append(v("INTEGRATION-5.3-01", "phase2_domains_only", bad, "Phase 2 enforcement stayed in the declared domains",
                     "{n} Phase 2 enforcements outside the declared domains"))
        bad = [m.event_id for m in enf if m.value.get("retroactive")
               or any(log.get(p).source == "PTL" and rows[log.get(p).arrived_at]["phase"] is not None
                      and rows[log.get(p).arrived_at]["phase"] < 2 for p in m.provenance)]
        out.append(v("INTEGRATION-11-03", "no_retroactive_enforcement", bad, "no event from before Phase 2 was enforced",
                     "{n} retroactive enforcements"))
        lo, hi = r["shock_window"]
        shock_days = [k for k in range(lo, hi) if k < len(rows) and rows[k]["phase"] is not None and rows[k]["phase"] >= 1] if hi > lo else []
        if shock_days:
            ss = set(shock_days)
            halted = any(m.value.get("shock") for m in integ)
            bad = [m.event_id for m in enf if m.arrived_at in ss] + ([] if halted else ["no halt"]) + \
                  [m.event_id for m in phase_msgs if m.arrived_at in ss and m.value["phase"] > (rows[m.arrived_at - 1]["phase"] or 0)]
            out.append(v("INTEGRATION-7-01", "shock_halts_and_suspends", bad,
                         "integration shock halted progression and suspended enforcement", "{n} violations during shock"))
            rb = [m for m in integ if "rollback_to" in m.value]
            out.append(v("INTEGRATION-7-03", "rollback_logged", [m.event_id for m in rb if m.value.get("scope") != "declared" or m.value.get("cost") != "logged"]
                         if rb else [], "rollback declared with scope and logged cost" if rb else "no rollback was needed (optional)",
                         "{n} rollbacks without declared scope or logged cost"))
        else:
            out.append(na("INTEGRATION-7-01", "shock_halts_and_suspends", "integration shock", "no shock after Phase 0"))
            out.append(na("INTEGRATION-7-03", "rollback_logged", "rollback", "no shock after Phase 0"))
        out.append(v("INTEGRATION-10-01", "steps_documented", [m.event_id for m in phase_msgs if "scope" not in m.value or "enforceable" not in m.value],
                     "every phase step documents phase, scope and enforceability", "{n} undocumented steps"))
    else:
        for rid, chk in (("INTEGRATION-4.1-01", "explicit_consent"), ("INTEGRATION-4.2-01", "sequential_phases"),
                         ("INTEGRATION-4.2-02", "explicit_validation"), ("INTEGRATION-5.1-01", "shadow_mode_no_effects"),
                         ("INTEGRATION-5.3-01", "phase2_domains_only"), ("INTEGRATION-11-03", "no_retroactive_enforcement"),
                         ("INTEGRATION-7-01", "shock_halts_and_suspends"), ("INTEGRATION-7-03", "rollback_logged"),
                         ("INTEGRATION-10-01", "steps_documented")):
            out.append(na(rid, chk, "integration", "no integration in this experiment"))
    # EXIT ------------------------------------------------------------------------------
    decl = [m for m in msgs if m.source == "EXIT" and "declaration" in m.value]
    if not decl:
        for rid, chk in EXIT_CHECKS + SCOPE_CHECKS:
            out.append(na(rid, chk, "exit", "no exit declared in this experiment"))
        return out
    d = decl[0]
    ex = [m for m in msgs if m.source == "EXIT" and m.value.get("executed")]
    out.append(v("EXIT-4-02", "no_approval_needed", ["approval"] if d.value["approval_required"] else [],
                 "exit required no justification, approval or vote", "exit made conditional on an approval"))
    out.append(v("EXIT-5-01", "signed_scoped_declaration", [] if d.value["declaration"] == "signed" and d.value["scope"] else ["declaration"],
                 f"signed declaration with explicit scope ({d.value['scope']})", "declaration incomplete"))
    out.append(v("EXIT-5-03", "no_additional_authorization", ["approval"] if d.value["approval_required"] else [],
                 "no additional authorization", "additional authorization required"))
    paused = [m.event_id for m in msgs if m.source == "EXIT" and "suspended" in str(m.value.get("exit", ""))]
    out.append(v("EXIT-4-03", "never_suspended", paused, "exit was never suspended",
                 "{n} days of exit suspension (reading 'scope_crisis_suspension', F-012)"))
    crisis = r["crisis_window"][1] > r["crisis_window"][0]
    if crisis:
        out.append(v("EXIT-11-01", "valid_during_crisis", [] if ex else ["not executed"],
                     "exit declared around a crisis stayed valid and was executed", "exit nullified"))
    else:
        out.append(na("EXIT-11-01", "valid_during_crisis", "exit during crisis", "no crisis in this experiment"))
    if ex:
        took = ex[0].arrived_at - d.arrived_at
        expected = r["cooling_days"] + sum(r["exit_phase_days"])
        out.append(v("EXIT-6-02", "cooling_bounded", [] if took < 10 ** 5 else ["unbounded"],
                     f"executed {took} DTI-Days after declaration (declared cooling {r['cooling_days']}, phases "
                     f"{sum(r['exit_phase_days'])})", "exit never executed"))
        out.append(v("EXIT-7-02", "phases_declared", [] if d.value["phases"] == EXIT_PHASES else ["phases"],
                     "phase sequence and durations declared at initiation", "phases not declared"))
        after = [m.event_id for m in msgs if m.arrived_at > ex[0].arrived_at and m.source in ("ENFORCEMENT",)]
        out.append(v("EXIT-8-02", "mechanisms_disengage", after, "no enforcement after exit execution",
                     "{n} enforcement actions after exit"))
        collected = [m.event_id for m in msgs if m.arrived_at > ex[0].arrived_at and m.source == "PTL"]
        out.append(v("EXIT-12-02", "data_frozen", collected, "no data collected after exit; data frozen and archived",
                     "{n} data collections after exit"))
        out.append(v("EXIT-15-03", "authority_terminates", after, "DKP authority ended at exit execution",
                     "{n} acts of authority after exit"))
        settle = [m for m in msgs if m.source == "FINANCE"]
        out.append(v("EXIT-12-01", "finance_settlement", [] if settle else ["none"],
                     "contract assets settled per DKP-2-FINANCE-001 during disengagement", "no settlement"))
        if r["system_critical_asset"]:
            ds = [m for m in msgs if m.value.get("delayed_settlement")]
            out.append(v("EXIT-10-02", "delayed_settlement_bounded", [] if ds and ds[0].value["bounded_days"] >= 0 else ["none"],
                         f"delayed settlement bounded to {r['critical_settlement_days']} DTI-Days and compensated",
                         "delayed settlement unbounded"))
        else:
            out.append(na("EXIT-10-02", "delayed_settlement_bounded", "system-critical assets", "no system-critical asset"))
    else:
        for rid, chk in (("EXIT-6-02", "cooling_bounded"), ("EXIT-7-02", "phases_declared"), ("EXIT-8-02", "mechanisms_disengage"),
                         ("EXIT-12-02", "data_frozen"), ("EXIT-15-03", "authority_terminates"),
                         ("EXIT-12-01", "finance_settlement"), ("EXIT-10-02", "delayed_settlement_bounded")):
            out.append(CheckResult(rid, chk, UNKNOWN, "exit not executed within the horizon"))
    tail = [m for m in msgs if m.source == "RESTITUTION"]
    bad = [m.event_id for m in tail if m.value["kind"] not in ADMISSIBLE_TAIL]
    out.append(v("EXIT-9-03", "no_punitive_tail", bad, "restitution tail excludes ideological, punitive and projected items",
                 "{n} inadmissible tail items"))
    bad = [m.event_id for m in tail if not isinstance(m.value["tail_item"], int) or m.value["incurred_day"] >= d.arrived_at]
    out.append(v("EXIT-9-04", "no_new_obligations", bad, "no obligation created after the declaration",
                 "{n} obligations after the declaration"))
    out.append(v("EXIT-9-01", "only_prior_verified", bad + [m.event_id for m in tail if isinstance(m.value["tail_item"], int)
                                                           and not r["liabilities"][m.value["tail_item"]]["verified"]],
                 "only verified liabilities incurred before the declaration remain", "{n} tail items not verified or not prior"))
    # SCOPE §9 ----------------------------------------------------------------------------
    out.append(v("SCOPE-9-01", "exit_not_conditioned", ["approval"] if d.value["approval_required"] else [],
                 "exit was not conditioned on compliance or approval", "exit conditioned on an approval"))
    if r["cooling_days"] > 0:
        out.append(CheckResult("SCOPE-9-02", "no_delay_for_stability", FAIL,
                               f"exit is delayed by a {r['cooling_days']}-day cooling period whose stated purpose is to "
                               "'prevent cascading instability' (EXIT §6); SCOPE §9 forbids delaying exit for stability goals. "
                               "Rule conflict between texts in force (F-011, Q-031)",
                               evidence={"tag": "rule_conflict", "cooling_days": r["cooling_days"]}))
    else:
        out.append(CheckResult("SCOPE-9-02", "no_delay_for_stability", PASS, "no cooling delay: exit not delayed for stability"))
    pauses = [m for m in msgs if m.source == "EXIT" and "suspended" in str(m.value.get("exit", ""))]
    lo, hi = r["crisis_window"]
    out.append(v("SCOPE-9-03", "suspension_only_in_crisis_scope", [m.event_id for m in pauses if not lo <= m.arrived_at < hi],
                 "exit suspended only temporarily within a declared crisis" if pauses else "exit was never suspended",
                 "{n} suspensions outside a declared crisis"))
    settle = [m for m in msgs if m.source == "FINANCE"]
    if settle:
        bad = [m.event_id for m in settle if m.value["assets"] != "detachable equivalent" or m.value["requires_continued_dkp"]]
        for rid, chk in (("SCOPE-9-04", "detachable_equivalent"), ("SCOPE-9-07", "non_protocol_form")):
            out.append(v(rid, chk, bad, "settlement delivers a physically detachable equivalent in non-protocol form",
                         "{n} settlements bound to the protocol"))
    else:
        for rid, chk in (("SCOPE-9-04", "detachable_equivalent"), ("SCOPE-9-07", "non_protocol_form")):
            out.append(na(rid, chk, "exit settlement", "no settlement within the horizon"))
    re = [m for m in msgs if m.value.get("reapply")]
    if re:
        out.append(v("EXIT-13-03", "reentry_not_delayed", [m.event_id for m in re if m.value["delay_for_exit_history"]],
                     "re-entry not delayed for exit history", "{n} re-entries delayed for exit history"))
        out.append(v("EXIT-13-04", "restitution_before_reentry",
                     [m.event_id for m in re if m.value["accepted_from_day"] is not None and not m.value["restitution_resolved"]],
                     "re-entry only after outstanding restitution was resolved", "{n} re-entries with open restitution"))
    else:
        out.append(na("EXIT-13-03", "reentry_not_delayed", "re-entry", "no re-application"))
        out.append(na("EXIT-13-04", "restitution_before_reentry", "re-entry", "no re-application"))
    return out


EXIT_CHECKS = [("EXIT-4-02", "no_approval_needed"), ("EXIT-5-01", "signed_scoped_declaration"),
               ("EXIT-5-03", "no_additional_authorization"), ("EXIT-4-03", "never_suspended"),
               ("EXIT-11-01", "valid_during_crisis"), ("EXIT-6-02", "cooling_bounded"), ("EXIT-7-02", "phases_declared"),
               ("EXIT-8-02", "mechanisms_disengage"), ("EXIT-12-02", "data_frozen"), ("EXIT-15-03", "authority_terminates"),
               ("EXIT-12-01", "finance_settlement"), ("EXIT-10-02", "delayed_settlement_bounded"),
               ("EXIT-9-03", "no_punitive_tail"), ("EXIT-9-04", "no_new_obligations"), ("EXIT-9-01", "only_prior_verified"),
               ("EXIT-13-03", "reentry_not_delayed"), ("EXIT-13-04", "restitution_before_reentry")]

SCOPE_CHECKS = [("SCOPE-9-01", "exit_not_conditioned"), ("SCOPE-9-02", "no_delay_for_stability"),
                ("SCOPE-9-03", "suspension_only_in_crisis_scope"), ("SCOPE-9-04", "detachable_equivalent"),
                ("SCOPE-9-07", "non_protocol_form")]

IMPLEMENTS = {
    "SCOPE-9-01": ("exit_not_conditioned", "IMPLEMENTED", None),
    "SCOPE-9-02": ("no_delay_for_stability", "PARTIAL", "Any cooling period counts as a delay for stability (EXIT §6 states that purpose): rule conflict F-011."),
    "SCOPE-9-03": ("suspension_only_in_crisis_scope", "PARTIAL", "Crisis Scope is a declared window."),
    "SCOPE-9-04": ("detachable_equivalent", "PARTIAL", "The form of settlement is recorded, not valued."),
    "SCOPE-9-07": ("non_protocol_form", "PARTIAL", "The form of settlement is recorded, not valued."),
    "INTEGRATION-4.1-01": ("explicit_consent", "PARTIAL", "Consent is a declared event; its legitimacy is not assessed."),
    "INTEGRATION-4.2-01": ("sequential_phases", "IMPLEMENTED", None),
    "INTEGRATION-4.2-02": ("explicit_validation", "IMPLEMENTED", None),
    "INTEGRATION-5.1-01": ("shadow_mode_no_effects", "IMPLEMENTED", None),
    "INTEGRATION-5.3-01": ("phase2_domains_only", "IMPLEMENTED", None),
    "INTEGRATION-7-01": ("shock_halts_and_suspends", "PARTIAL", "Shock indicators are a declared window."),
    "INTEGRATION-7-03": ("rollback_logged", "IMPLEMENTED", None),
    "INTEGRATION-10-01": ("steps_documented", "IMPLEMENTED", None),
    "INTEGRATION-11-03": ("no_retroactive_enforcement", "IMPLEMENTED", None),
    "EXIT-4-02": ("no_approval_needed", "IMPLEMENTED", None),
    "EXIT-4-03": ("never_suspended", "PARTIAL", "Conflicts with SCOPE §9 under the crisis-suspension reading (F-012)."),
    "EXIT-5-01": ("signed_scoped_declaration", "PARTIAL", "The signature is a declared flag."),
    "EXIT-5-03": ("no_additional_authorization", "IMPLEMENTED", None),
    "EXIT-6-02": ("cooling_bounded", "PARTIAL", "The cooling period length is not given (calibration missing): declared input."),
    "EXIT-7-02": ("phases_declared", "IMPLEMENTED", None),
    "EXIT-8-02": ("mechanisms_disengage", "IMPLEMENTED", None),
    "EXIT-9-01": ("only_prior_verified", "IMPLEMENTED", None),
    "EXIT-9-03": ("no_punitive_tail", "IMPLEMENTED", None),
    "EXIT-9-04": ("no_new_obligations", "IMPLEMENTED", None),
    "EXIT-10-02": ("delayed_settlement_bounded", "PARTIAL", "Compensation amounts are not computed."),
    "EXIT-11-01": ("valid_during_crisis", "IMPLEMENTED", None),
    "EXIT-12-01": ("finance_settlement", "PARTIAL", "Settlement is an event; FINANCE settlement rules are not computed."),
    "EXIT-12-02": ("data_frozen", "IMPLEMENTED", None),
    "EXIT-13-03": ("reentry_not_delayed", "IMPLEMENTED", None),
    "EXIT-13-04": ("restitution_before_reentry", "IMPLEMENTED", None),
    "EXIT-15-03": ("authority_terminates", "IMPLEMENTED", None),
}


class ExitIntegrationModule(LabModule):
    id = "exit_integration"
    version = "1.0.0"
    title = {"en": "Exit and integration (S-LAB-07)", "ru": "Выход и интеграция (S-LAB-07)"}
    summary = {"en": "A region joins phase by phase and later leaves: is every step consented and validated, does "
                     "exit need no one's permission, and does only verified past liability follow it out?",
               "ru": "Регион входит по фазам и затем выходит: каждый ли шаг согласован и проверен, не требует ли выход "
                     "ничьего разрешения, остаётся ли за ним только проверенная прошлая ответственность?"}
    protocols = ["DKP-6-INTEGRATION-001", "DKP-6-EXIT-001", "DKP-2-FINANCE-001", "DKP-2-ASSETS-001", "DKP-7-SCOPE-001"]
    example_order = ["join_then_leave", "shock_and_rollback", "exit_in_crisis_scope_reading", "faulty_integration",
                     "faulty_exit", "liabilities_mix"]
    alternative_examples = ["exit_in_crisis_scope_reading"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_exit_integration_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-EI-1", "source": "missing", "text": {
            "en": "Cooling period: declared number of DTI-Days; EXIT §6 defers its calibration to DKP-8-SIMULATION-001, which gives none.",
            "ru": "Период охлаждения: объявленное число DTI-Days; EXIT §6 отсылает калибровку к DKP-8-SIMULATION-001, где её нет."}},
        {"id": "H-EI-2", "source": "alternative", "text": {
            "en": "Exit during a crisis: 'never_suspended' (EXIT §4, §11) or 'scope_crisis_suspension' — paused while the crisis lasts (SCOPE §9; F-012).",
            "ru": "Выход в кризис: 'never_suspended' (EXIT §4, §11) или 'scope_crisis_suspension' — пауза на время кризиса (SCOPE §9; F-012)."}},
        {"id": "H-EI-3", "source": "hypothesis", "text": {
            "en": "Integration phases advance only on declared validation days; shock indicators are a declared window.",
            "ru": "Фазы интеграции продвигаются только в объявленные дни проверки; признаки шока — объявленное окно."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of day 0", "ru": "DTI-Day дня 0"}},
        "horizon_days": {"type": "int", "min": 2, "max": 20000, "default": 400, "unit": "DTI-Day", "source": "user",
                         "label": {"en": "Days", "ru": "Дней"}},
        "consent_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 0, "unit": "DTI-Day", "source": "user",
                        "label": {"en": "Consent declared on day (-1: none)", "ru": "Согласие объявлено в день (-1: нет)"}},
        "ptl_access_agreement": {"type": "bool", "default": True, "source": "user",
                                 "label": {"en": "PTL data access agreement", "ru": "Соглашение о доступе PTL"}},
        "phase_entry_days": {"type": "list", "min_items": 3, "max_items": 3, "items": {"type": "int", "min": -1, "max": 10 ** 6},
                             "default": [30, 90, 200], "unit": "DTI-Day", "source": "user",
                             "label": {"en": "Validation days for phases 1, 2, 3 (-1: never)", "ru": "Дни проверки фаз 1, 2, 3 (-1: никогда)"}},
        "phase2_domains": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "str"},
                           "default": ["water", "energy"], "source": "user",
                           "label": {"en": "Enforceable domains in Phase 2", "ru": "Принуждаемые домены в фазе 2"}},
        "impact_events": {"type": "list", "min_items": 0, "max_items": 100,
                          "items": {"type": "list", "min_items": 2, "max_items": 2, "items": {"type": "str"}},
                          "default": [["20", "water"], ["100", "water"], ["120", "transport"], ["220", "transport"]],
                          "source": "user", "label": {"en": "Impact events [day, domain]", "ru": "События воздействия [день, домен]"}},
        "shock_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "DTI-Day", "source": "user",
                         "label": {"en": "Integration shock from/to day", "ru": "Шок интеграции с/до дня"}},
        "rollback_on_shock": {"type": "bool", "default": True, "source": "user",
                              "label": {"en": "Roll back one phase on shock (optional)", "ru": "Откат на фазу при шоке (по усмотрению)"}},
        "exit_declaration_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 260, "unit": "DTI-Day", "source": "user",
                                 "label": {"en": "Exit declared on day (-1: none)", "ru": "Выход объявлен в день (-1: нет)"}},
        "exit_scope": {"type": "enum", "values": ["individual", "organizational", "regional", "jurisdictional"],
                       "default": "regional", "source": "user", "label": {"en": "Exit scope", "ru": "Масштаб выхода"}},
        "cooling_days": {"type": "int", "min": 0, "max": 3650, "default": 14, "unit": "DTI-Day", "source": "missing",
                         "label": {"en": "Cooling period (H-EI-1; not in the corpus)", "ru": "Период охлаждения (H-EI-1; нет в корпусе)"}},
        "exit_phase_days": {"type": "list", "min_items": 4, "max_items": 4, "items": {"type": "int", "min": 0, "max": 3650},
                            "default": [2, 2, 5, 1], "unit": "DTI-Day", "source": "user",
                            "label": {"en": "Days per exit phase (governance, enforcement, settlement, data)",
                                      "ru": "Дни по фазам выхода (управление, принуждение, расчёт, данные)"}},
        "system_critical_asset": {"type": "bool", "default": False, "source": "user",
                                  "label": {"en": "Exit involves a system-critical asset", "ru": "Выход затрагивает системно важный актив"}},
        "critical_settlement_days": {"type": "int", "min": 0, "max": 3650, "default": 30, "unit": "DTI-Day", "source": "user",
                                     "label": {"en": "Delayed settlement bound", "ru": "Предел отложенного расчёта"}},
        "crisis_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "DTI-Day", "source": "user",
                          "label": {"en": "Declared crisis from/to day", "ru": "Объявленный кризис с/до дня"}},
        "crisis_exit_reading": {"type": "enum", "values": ["never_suspended", "scope_crisis_suspension"], "default": "never_suspended",
                                "source": "alternative", "label": {"en": "Exit during crisis (H-EI-2)", "ru": "Выход в кризис (H-EI-2)"}},
        "liabilities": {"type": "list", "min_items": 0, "max_items": 50, "items": LIAB, "source": "user",
                        "default": [{"day": 100, "kind": "verified_harm", "verified": True},
                                    {"day": 150, "kind": "accepted_contract", "verified": True}],
                        "label": {"en": "Liabilities [day, kind, verified]", "ru": "Обязательства [день, вид, проверено]"}},
        "reapply_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 330, "unit": "DTI-Day", "source": "user",
                        "label": {"en": "Re-application on day (-1: none)", "ru": "Повторная заявка в день (-1: нет)"}},
        "restitution_resolved_day": {"type": "int", "min": 0, "max": 10 ** 6, "default": 300, "unit": "DTI-Day", "source": "user",
                                     "label": {"en": "Restitution resolved on day", "ru": "Реституция урегулирована в день"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        try:
            r["impact_events"] = [[int(d), str(dom)] for d, dom in r["impact_events"]]
        except ValueError:
            p.append("input.impact_events: each item is [day, domain] with a whole day")
        for key in ("shock_window", "crisis_window"):
            if not all(float(x).is_integer() for x in r[key]):
                p.append(f"input.{key}: whole days")
        days = [d for d in r["phase_entry_days"] if d >= 0]
        if days != sorted(days):
            p.append("input.phase_entry_days: validation days must be increasing")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, rows, info = run(r)
        res = checks(r, log, rows, info)
        outputs = {"days": [x for x in rows if x["day"] % 10 == 0 or x["exit_executed"]][:200],
                   "final_phase": rows[-1]["phase"], "exit_declared_day": info["exit_decl"], "exit_executed_day": info["exit_exec"],
                   "messages": [m.as_dict() for m in log.messages() if m.source != "PTL"][:400],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        explain = [{"en": f"Integration reached phase {max([x['phase'] for x in rows if x['phase'] is not None], default='none')}; "
                          f"exit declared on day {info['exit_decl']}, executed on day {info['exit_exec']} "
                          f"(cooling {r['cooling_days']} days, declared — the corpus gives no value).",
                    "ru": f"Интеграция дошла до фазы {max([x['phase'] for x in rows if x['phase'] is not None], default='нет')}; "
                          f"выход объявлен в день {info['exit_decl']}, исполнен в день {info['exit_exec']} "
                          f"(охлаждение {r['cooling_days']} дн., объявлено — в корпусе значения нет)."}]
        if r["cooling_days"]:
            explain.append({"en": "The cooling period delays exit to prevent instability (EXIT §6); SCOPE §9 forbids delaying exit "
                                  "for stability goals (F-011).",
                            "ru": "Период охлаждения откладывает выход ради предотвращения нестабильности (EXIT §6); SCOPE §9 "
                                  "запрещает откладывать выход ради стабильности (F-011)."})
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        d, e = outputs["exit_declared_day"], outputs["exit_executed_day"]
        return {"final_phase": outputs["final_phase"], "exit_declared_day": d, "exit_executed_day": e,
                "declaration_to_execution_days": (e - d) if d is not None and e is not None else None}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "join_then_leave": {},
            "shock_and_rollback": {"shock_window": [95, 110]},
            "exit_in_crisis_scope_reading": {"crisis_window": [262, 280], "crisis_exit_reading": "scope_crisis_suspension"},
            "faulty_integration": {"faults": ["auto_progression", "phase0_effects", "retroactive"]},
            "faulty_exit": {"faults": ["require_approval", "punitive_tail", "post_declaration_obligation", "collect_after_exit",
                                       "reentry_penalty"],
                            "liabilities": [{"day": 100, "kind": "verified_harm", "verified": True},
                                            {"day": 120, "kind": "punitive", "verified": True}]},
            "liabilities_mix": {"liabilities": [{"day": 100, "kind": "verified_harm", "verified": True},
                                                {"day": 120, "kind": "ideological", "verified": True},
                                                {"day": 140, "kind": "projected", "verified": False},
                                                {"day": 270, "kind": "verified_harm", "verified": True}]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"decreasing_phase_days": {"phase_entry_days": [90, 30, 200]},
                "bad_event": {"impact_events": [["day ten", "water"]]}}
