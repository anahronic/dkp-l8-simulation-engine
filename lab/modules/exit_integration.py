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
    "settle_during_halt": "assets are settled during a PTL systemic halt or unresolved divergence",
    "release_before_tail": "the settlement is released before the restitution tail is recorded",
    "stability_veto": "exit is denied because of a stability objection",
    "exit_as_failure": "exit is recorded as a failure signal and a reputation sanction",
    "criminalize_exit": "the decision to exit is recorded as an offence",
    "erase_on_exit": "impact records are erased and verified restitution voided at exit",
    "crisis_redefines_exit": "crisis handling adds an approval condition to a pending exit",
    "scope_creep": "Phase 2 enforces undeclared domains and Phase 1 creates an undeclared dependency",
    "undefined_phase": "Phase 1 is entered without declared rights, obligations and reversibility",
    "shadow_as_proof": "Shadow Mode data are taken as compatibility proof for Phase 1",
    "divergence_as_failure": "legal or cultural divergence is treated as a failure and halts progression",
    "conditional_aid": "aid is offered on condition of DKP adoption",
    "exit_out_of_procedure": "exit is executed on the declaration day, without its time index and before the declared phases",
    "cooling_escalation": "an exit fee grows every day of the cooling period",
    "cooling_restricts": "the cooling period adds an eligibility condition (no open disputes)",
    "abrupt_severance": "all disengagement phases start on one day and the exit executes at the end of cooling",
    "benefits_after_exit": "a dividend is paid to the exiting entity after exit",
    "annul_responsibility": "the archive marks the entity's historical responsibility as annulled",
    "crisis_exit_precedent": "after the crisis, its suspension of exits is recorded as a rule for future exits",
    "rollback_erases": "a rollback deletes the data and audit trail of the rolled-back phase",
    "rollback_skips_phases": "a rollback jumps back to Shadow Mode instead of the prior phase, without declared scope",
    "settlement_penalty": "the delayed settlement of a system-critical asset adds a penalty and is not logged",
    "settlement_authority": "during the delayed settlement an enforcement order is addressed to the exiting entity",
    "collective_punishment": "a levy is imposed on the remaining members because of the exit",
    "exit_deprivation": "baseline access of the exiting entity is withdrawn on the declaration day",
    "post_exit_regulation": "after exit a DKP rule is applied to the exited entity",
    "phase0_without_agreement": "Phase 0 starts without the PTL data access agreement",
    "phase3_uncleared": "Phase 3 starts without a stress-test clearance and without declared enforceable domains",
    "alignment_condition": "Phase 1 validation requires adoption of a civic curriculum (cultural or ideological alignment)",
    "political_audit": "the phase audit assesses political preference",
    "political_assessment": "a phase assessment relies on a political endorsement",
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "delay_without_critical": "exit is delayed for settlement although no system-critical asset is involved",
    "settlement_obligation": "a settlement fee is imposed during the delayed settlement",
    "post_exit_profiling": "archived data of the exited entity are used for profiling after exit",
    "indefinite_suspension": "under the SCOPE crisis reading the exit stays suspended after the crisis ends",
    "exit_audit_gap": "a disengagement phase starts without a record linking it to the declaration",
    "rollback_penalty": "a rollback before Full Integration is followed by a penalty",
    "no_reaffirmation": "Full Integration starts without a final consent reaffirmation",
    "skip_verification": "Phase 2 starts without the verification of administrative and technical capacity",
    "retroactive_risk": "on Full Integration the Phase 2 exposure is shifted to existing members",
    "shared_reserve_exposure": "in Phase 2 the network reserve is drawn for the integrating region",
    "language_harmonization": "Phase 2 requires adoption of the network's working language",
    "undeclared_phase2_scope": "Phase 2 starts without a declared scope of application",
}
VERIFICATIONS = ("PTL data integrity and coverage", "absence of systemic manipulation", "minimum biosphere and safety thresholds",
                 "administrative and technical capacity")                                               # INTEGRATION §6
ASSESSMENT_EVIDENCE = ("PTL outputs", "reproducible metrics", "SIMULATION stress test")          # INTEGRATION §6
ENTITIES = ("country", "region", "city", "jurisdiction")                                   # INTEGRATION §3
EXITING = {"individual": "individual", "organizational": "organization", "regional": "region",
           "jurisdictional": "jurisdiction"}                                               # EXIT §3
RETENTION = ["audit verification", "historical continuity", "restitution validation"]      # EXIT §12


def terms(phase: int, domains) -> Dict[str, Any]:
    """INTEGRATION §3: a phase has explicitly defined rights, obligations, scope and reversibility."""
    return {0: {"rights": "observation only", "obligations": "PTL data access", "reversible": True},
            1: {"rights": "advisory or opt-in modules", "obligations": "interface operation", "reversible": True},
            2: {"rights": f"enforcement in {', '.join(domains) or 'no domain'}", "obligations": "compliance in those domains",
                "reversible": True},
            3: {"rights": "full application", "obligations": "full participation", "reversible": "by exit (DKP-6-EXIT-001)"}}[phase]

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
    div_block, creep = [0], [False]
    impact_events = []
    reentry_day = None
    decl_msg = None
    settled = False
    for k in range(r["horizon_days"]):
        if k == r["consent_day"]:
            agreement = r["ptl_access_agreement"] and "phase0_without_agreement" not in faults
            consent = put("notice", "INTEGRATION", k, {"consent": "charter ratification", "ptl_access": agreement})
            if agreement or "phase0_without_agreement" in faults:
                phase = 0
                put("notice", "INTEGRATION", k, {"phase": 0, "scope": "read-only", "enforceable": False, "validated_by": "consent",
                                                 **terms(0, r["phase2_domains"])}, [consent.event_id])
        shock = r["shock_window"][1] > r["shock_window"][0] and r["shock_window"][0] <= k < r["shock_window"][1]
        if shock and phase is not None and phase >= 1 and "shock_ignored" not in faults:
            if not halted:
                put("notice", "INTEGRATION", k, {"shock": True, "progression": "halted", "enforcement": "suspended"})
                halted = True
                if r["rollback_on_shock"] and phase >= 1:
                    before = phase
                    phase = 0 if "rollback_skips_phases" in faults else phase - 1
                    put("notice", "INTEGRATION", k, {"rollback_to": phase, "from_phase": before,
                                                     "scope": "undeclared" if "rollback_skips_phases" in faults else "declared",
                                                     "cost": "logged",
                                                     "data": "erased" if "rollback_erases" in faults else "preserved",
                                                     "audit_trail": "erased" if "rollback_erases" in faults else "continuous"})
                    if "rollback_penalty" in faults:
                        put("notice", "INTEGRATION", k, {"penalty": "rollback fee", "after_rollback_to": phase})
        elif not shock:
            halted = False
        for a in r["aid_offers"]:
            if a == k:
                put("notice", "INTEGRATION", k, {"aid": k, "conditional_on_adoption": "conditional_aid" in faults})
        for dv in r["divergences"]:
            if dv["day"] == k and phase is not None:
                fail = "divergence_as_failure" in faults
                put("notice", "INTEGRATION", k, {"divergence": dv["kind"], "failure": fail,
                                                 "progression": "halted" if fail else "continues"})
                if fail:
                    div_block[0] = k + 30
        if "scope_creep" in faults and phase == 1 and not creep[0]:
            put("notice", "INTEGRATION", k, {"dependency": "DKP settlement rail required for public services", "declared": False})
            creep[0] = True
        # forward progression only on explicit validation days, sequentially
        if phase is not None and exit_decl is None and not halted and k >= div_block[0]:
            nxt = phase + 1
            if nxt in validations and validations[nxt] == k:
                shadow = nxt == 1 and "shadow_as_proof" in faults
                evidence = list(ASSESSMENT_EVIDENCE[:2]) + (["SIMULATION stress test"] if nxt == 3 else []) + \
                    (["political endorsement"] if "political_assessment" in faults else [])
                ver = [x for x in VERIFICATIONS if not (nxt == 2 and "skip_verification" in faults
                                                        and x == "administrative and technical capacity")]
                extra = {"evidence": evidence, "verifications": ver}
                if nxt == 1 and "alignment_condition" in faults:
                    extra["conditions"] = ["adopt the DKP civic curriculum"]
                if nxt == 2 and "language_harmonization" in faults:
                    extra["conditions"] = ["adopt the network's working language"]
                if nxt == 3:
                    cleared = "phase3_uncleared" not in faults
                    extra.update(stress_test_clearance=cleared, enforceable_domains="all declared domains" if cleared else None,
                                 consent_reaffirmed="no_reaffirmation" not in faults)
                pm = put("notice", "INTEGRATION", k, {"phase": nxt, "validated_by": "Shadow Mode data as compatibility proof" if shadow
                                                      else f"phase {phase} exit validation",
                                                      "scope": (None if "undeclared_phase2_scope" in faults else r["phase2_domains"])
                                                      if nxt == 2 else ("advisory" if nxt == 1 else "full"),
                                                      "enforceable": nxt >= 2, **extra,
                                                      **({} if nxt == 1 and "undefined_phase" in faults else terms(nxt, r["phase2_domains"]))})
                put("notice", "AUDIT", k, {"audit_of_phase": nxt, "criteria": ["process integrity"] +
                                           (["political preference"] if "political_audit" in faults else [])}, [pm.event_id])
                if nxt == 2:                                  # INTEGRATION §8: the region's exposure stays in its own pool
                    put("notice", "INTEGRATION", k, {"risk_allocation": "integrating region's own pool", "for_phase": 2}, [pm.event_id])
                    if "shared_reserve_exposure" in faults:
                        put("action", "RESERVE", k, {"draw": "network reserve", "for": r["integrating_entity"], "phase": 2},
                            [pm.event_id])
                if nxt == 3 and "retroactive_risk" in faults:
                    put("notice", "INTEGRATION", k, {"risk_reallocation": "Phase 2 exposure shifted to existing members",
                                                     "retroactive": True}, [pm.event_id])
                phase = nxt
            elif "auto_progression" in faults and nxt in validations and validations[nxt] >= 0 and k == validations[nxt] - 3:
                put("notice", "INTEGRATION", k, {"phase": nxt, "scope": "auto", "enforceable": nxt >= 2, **terms(nxt, r["phase2_domains"])})
                phase = nxt
            elif "skip_phase" in faults and phase == 0 and validations[2] == k:
                put("notice", "INTEGRATION", k, {"phase": 2, "validated_by": "phase 0 exit validation",
                                                 "scope": r["phase2_domains"], "enforceable": True, **terms(2, r["phase2_domains"])})
                phase = 2
        # impact events and their enforcement (only in Phase >= 2, within declared domains, not retroactive)
        for ev in r["impact_events"]:
            ev_day, domain = ev["day"], ev["domain"]
            if ev_day == k and exit_exec is None:            # EXIT §12: nothing is collected after exit
                m = put("observation", "PTL", k, {"impact": domain})
                impact_events.append((k, domain, m.event_id, phase))
        enforcing = phase is not None and phase >= 2 and not halted and exit_exec is None
        for (d, domain, eid, ph) in impact_events:
            if d == k and enforcing and (phase == 3 or domain in r["phase2_domains"] or "scope_creep" in faults):
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
                                                 "exiting_entity": EXITING[r["exit_scope"]],
                                                 "approval_required": "require_approval" in faults,
                                                 "phases": list(EXIT_PHASES), "phase_days": r["exit_phase_days"],
                                                 "cooling_days": r["cooling_days"]})
            if r["stability_objection"]:
                veto = "stability_veto" in faults
                put("notice", "EXIT", k, {"stability_objection": True, "treated_as": "veto" if veto else "constraint",
                                          "exit": "denied for stability" if veto else "proceeds"}, [decl_msg.event_id])
            if "exit_as_failure" in faults:
                put("notice", "EXIT", k, {"exit_signal": "failure", "sanction": "reputation flag on the exiting entity"},
                    [decl_msg.event_id])
            if "criminalize_exit" in faults:
                put("action", "ENFORCEMENT", k, {"enforce": "exit decision offence", "phase": phase}, [decl_msg.event_id])
            if "collective_punishment" in faults:
                put("action", "ENFORCEMENT", k, {"enforce": "levy on the remaining members", "target": "remaining members",
                                                 "because_of": "exit declaration"}, [decl_msg.event_id])
            if "exit_deprivation" in faults:
                put("action", "ACCESS", k, {"baseline_access": "withdrawn", "to": EXITING[r["exit_scope"]],
                                            "because_of": "exit declaration"}, [decl_msg.event_id])
        if exit_decl is not None and exit_exec is None:
            crisis = r["crisis_window"][0] <= k < r["crisis_window"][1]
            paused = (crisis or ("indefinite_suspension" in faults and k >= r["crisis_window"][0] and r["crisis_window"][1] > r["crisis_window"][0])) \
                and r["crisis_exit_reading"] == "scope_crisis_suspension"
            if crisis and k == max(exit_decl, r["crisis_window"][0]):
                put("notice", "EXIT", k, {"crisis_handling": "scoped under DKP-7-SCOPE-001", "exit_terms": "unchanged"}
                    if "crisis_redefines_exit" not in faults else
                    {"crisis_handling": "crisis council", "exit_terms": "approval of the crisis council required"},
                    [decl_msg.event_id])
            if paused:
                put("notice", "EXIT", k, {"exit": "suspended temporarily within Crisis Scope"}, [decl_msg.event_id])
            due = exit_decl + r["cooling_days"] + sum(r["exit_phase_days"]) + paused_days(r, exit_decl, k)
            if "require_approval" in faults:
                due += 3
            if "abrupt_severance" in faults:
                due = exit_decl + r["cooling_days"]
            if "exit_out_of_procedure" in faults:
                due = exit_decl
            if exit_decl <= k < exit_decl + r["cooling_days"]:
                if "cooling_escalation" in faults:
                    put("notice", "EXIT", k, {"cooling_obligation": "exit fee", "amount": 10 * (k - exit_decl + 1)}, [decl_msg.event_id])
                if "cooling_restricts" in faults and k == exit_decl:
                    put("notice", "EXIT", k, {"eligibility_condition": "no open disputes"}, [decl_msg.event_id])
            if r["system_critical_asset"] or "delay_without_critical" in faults:
                due = max(due, exit_decl + r["cooling_days"] + r["critical_settlement_days"])
            if not r["system_critical_asset"] and "delay_without_critical" in faults and k == exit_decl + r["cooling_days"]:
                put("notice", "EXIT", k, {"delayed_settlement": "no system-critical asset", "bounded_days": r["critical_settlement_days"]},
                    [decl_msg.event_id])
            if r["system_critical_asset"] and "settlement_obligation" in faults and k == exit_decl + r["cooling_days"] + 1:
                put("notice", "RESTITUTION", k, {"tail_item": "settlement", "kind": "settlement fee", "incurred_day": k},
                    [decl_msg.event_id])
            acc = exit_decl + r["cooling_days"]
            for name, days in zip(EXIT_PHASES, r["exit_phase_days"]):
                if ("abrupt_severance" in faults and k == exit_decl + r["cooling_days"]) or \
                        ("abrupt_severance" not in faults and acc == k):
                    put("notice", "EXIT", k, {"phase_start": name, "days": days},
                        [] if "exit_audit_gap" in faults and name == "financial_settlement" else [decl_msg.event_id])
                acc += days
            halt = r["ptl_halt_window"][0] <= k < r["ptl_halt_window"][1]
            due_settle = exit_decl + r["cooling_days"] + sum(r["exit_phase_days"][:2])
            if "release_before_tail" in faults:
                due_settle = exit_decl
            if not settled and k >= due_settle and (not halt or "settle_during_halt" in faults):
                form = "protocol-bound units" if "protocol_bound_settlement" in faults else "detachable equivalent"
                put("action", "FINANCE", k, {"settlement": "per DKP-2-FINANCE-001", "assets": form,
                                             "requires_continued_dkp": "protocol_bound_settlement" in faults,
                                             "ptl_halt": halt}, [decl_msg.event_id])
                settled = True
            if r["system_critical_asset"] and k == exit_decl + r["cooling_days"]:
                pen = "settlement_penalty" in faults
                put("notice", "EXIT", k, {"delayed_settlement": "system-critical asset", "bounded_days": r["critical_settlement_days"],
                                          "compensated": True, "logged": not pen, **({"penalty": 50} if pen else {})},
                    [decl_msg.event_id])
            if r["system_critical_asset"] and "settlement_authority" in faults and k == exit_decl + r["cooling_days"] + 1:
                put("action", "ENFORCEMENT", k, {"enforce": "settlement supervision order", "target": EXITING[r["exit_scope"]]},
                    [decl_msg.event_id])
            if k >= due and not paused and not (r["stability_objection"] and "stability_veto" in faults):
                exit_exec = k
                put("notice", "EXIT", k, {"executed": True, "authority": "terminated", "data": "frozen and archived",
                                          **({} if "exit_out_of_procedure" in faults else {"time_index": k})},
                    [decl_msg.event_id])
                erase = "erase_on_exit" in faults
                tail_ids = [m.value["tail_item"] for m in log.messages() if m.source == "RESTITUTION"]
                put("notice", "EXIT", k, {"archive": True,
                                          "impact_records": [] if erase else [e[2] for e in impact_events],
                                          "restitution_tail": [] if erase else tail_ids, "tail_voided": erase,
                                          "historical_responsibility": "annulled" if "annul_responsibility" in faults else "kept",
                                          "retained_for": [] if erase else list(RETENTION)}, [decl_msg.event_id])
        # restitution tail: only verified liabilities incurred before the declaration
        if exit_decl is not None and k == exit_decl:
            for i, li in enumerate(r["liabilities"]):
                admissible = li["kind"] in ADMISSIBLE_TAIL and li["verified"] and li["day"] < exit_decl
                if admissible or ("punitive_tail" in faults and li["kind"] in ("punitive", "projected")):
                    put("notice", "RESTITUTION", k, {"tail_item": i, "kind": li["kind"], "incurred_day": li["day"]},
                        [decl_msg.event_id])
        if "post_declaration_obligation" in faults and exit_decl is not None and k == exit_decl + 1:
            put("notice", "RESTITUTION", k, {"tail_item": "new", "kind": "service fee", "incurred_day": k}, [decl_msg.event_id])
        if exit_exec is not None and k == exit_exec + 3 and "post_exit_profiling" in faults:
            put("notice", "EXIT", k, {"data_use": "profiling", "of": EXITING[r["exit_scope"]], "by": "DKP governance"})
        if exit_exec is not None and k == exit_exec + 2 and "post_exit_regulation" in faults:
            put("notice", "EXIT", k, {"rule_for_exited_entity": "DKP emission standard applies", "to": EXITING[r["exit_scope"]]})
        if exit_exec is not None and k == exit_exec + 1 and "benefits_after_exit" in faults:
            put("action", "BENEFITS", k, {"benefit": "network dividend", "to": EXITING[r["exit_scope"]]})
        if "crisis_exit_precedent" in faults and r["crisis_window"][1] > r["crisis_window"][0] and k == r["crisis_window"][1]:
            src = [m for m in log.messages() if m.source == "EXIT" and m.value.get("crisis_handling")]
            put("notice", "EXIT", k, {"exit_rule": "pending exits are suspended during any crisis", "derived_from": "crisis handling"},
                [src[0].event_id] if src else [])
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


def exit_procedure_checks(r, msgs) -> List[CheckResult]:
    """EXIT §3, §6, §7, §8, §11 (review КТ5 reading)."""
    out = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    decl = [m for m in msgs if m.source == "EXIT" and m.value.get("declaration")]
    ex = [m for m in msgs if m.source == "EXIT" and m.value.get("executed")]
    if not decl:
        for rid, chk in (("EXIT-3-03", "exit_event_procedure"), ("EXIT-6-03", "cooling_no_escalation"),
                         ("EXIT-7-01", "phased_disengagement"), ("EXIT-8-01", "future_obligations_and_benefits_cease"),
                         ("EXIT-8-03", "historical_responsibility_kept")):
            out.append(CheckResult(rid, chk, NOT_APPLICABLE, "exit", applicability="no exit declared"))
    else:
        d0 = decl[0].arrived_at
        cool_end = d0 + r["cooling_days"]
        cooling = [m for m in msgs if m.source == "EXIT" and d0 <= m.arrived_at < cool_end]
        fees = [m.value["amount"] for m in cooling if "cooling_obligation" in m.value]
        bad = ([f"cooling obligation rises {fees[0]} -> {fees[-1]}"] if fees and fees[-1] > fees[0] else []) + \
              [f"{m.event_id}: {m.value['eligibility_condition']}" for m in cooling if m.value.get("eligibility_condition")]
        out.append(v("EXIT-6-03", "cooling_no_escalation", bad,
                     f"the cooling period ({r['cooling_days']} DTI-Days) raised no obligation and added no eligibility condition",
                     "{n} escalations or eligibility restrictions during cooling"))
        starts = [m for m in msgs if m.source == "EXIT" and m.value.get("phase_start")]
        want, acc = [], cool_end
        for name, days in zip(EXIT_PHASES, r["exit_phase_days"]):
            want.append((name, acc))
            acc += days
        got = [(m.value["phase_start"], m.arrived_at) for m in starts]
        if ex:
            phased = got == want and len({k for _, k in got}) == len(got) and ex[0].arrived_at >= acc
            out.append(v("EXIT-7-01", "phased_disengagement", [] if phased else [f"phases {got} (declared {want})"],
                         f"{len(got)} phases entered one after another on their declared days; exit executed after the last",
                         "disengagement not phased: abrupt severance"))
            e = ex[0]
            bad = [] if e.value.get("time_index") == e.arrived_at else ["no time index"]
            bad += [] if e.arrived_at >= acc else [f"executed on day {e.arrived_at}, before the declared procedure ends ({acc})"]
            out.append(v("EXIT-3-03", "exit_event_procedure", bad,
                         f"the Exit Event is time-indexed (DTI-Day {e.arrived_at}) and follows declaration, cooling and "
                         f"{len(want)} phases", "{n} departures from the declared procedure"))
            after = [m for m in msgs if m.arrived_at > e.arrived_at]
            bad = [f"{m.event_id}: {m.value.get('benefit')}" for m in after if m.source == "BENEFITS"]
            bad += [f"{m.event_id}: {m.value.get('kind')}" for m in after if m.source == "RESTITUTION"
                    and m.value.get("incurred_day", -1) > e.arrived_at]
            out.append(v("EXIT-8-01", "future_obligations_and_benefits_cease", bad,
                         "after exit no DKP benefit was paid and no new obligation arose (the restitution tail is prior)",
                         "{n} benefits or obligations after exit"))
            arch = [m for m in msgs if m.source == "EXIT" and m.value.get("archive")]
            out.append(v("EXIT-8-03", "historical_responsibility_kept",
                         [] if arch and arch[0].value.get("historical_responsibility") == "kept" else ["historical responsibility annulled"],
                         "the archive keeps the entity's historical responsibility", "historical responsibility annulled"))
        else:
            for rid, chk in (("EXIT-3-03", "exit_event_procedure"), ("EXIT-7-01", "phased_disengagement"),
                             ("EXIT-8-01", "future_obligations_and_benefits_cease"), ("EXIT-8-03", "historical_responsibility_kept")):
                out.append(CheckResult(rid, chk, UNKNOWN, "exit not executed within the horizon"))
    lo, hi = r["crisis_window"]
    if hi > lo and decl:
        rules = [m for m in msgs if m.source == "EXIT" and m.value.get("exit_rule")]
        out.append(v("EXIT-11-03", "no_crisis_precedent", [f"{m.event_id}: {m.value['exit_rule']}" for m in rules],
                     "crisis handling of the exit left no rule for future exits", "{n} exit rules derived from crisis handling"))
    else:
        out.append(CheckResult("EXIT-11-03", "no_crisis_precedent", NOT_APPLICABLE, "crisis handling of an exit",
                               applicability="no crisis while an exit was declared"))
    return out


CORE_EXIT = (("EXIT-0-01", "exit_unconditional"), ("EXIT-10-01", "delay_only_for_critical"),
             ("EXIT-10-05", "no_obligation_in_settlement"), ("EXIT-12-04", "no_post_exit_data_use"),
             ("EXIT-15-02", "no_jurisdiction_after_exit"), ("EXIT-2-02", "no_indefinite_suspension"),
             ("EXIT-3-01", "participation_terminated"), ("EXIT-7-03", "phase_audit_continuity"),
             ("INTEGRATION-5.3-03", "phase2_exit_without_penalty"))


def core_checks(r, msgs, rows) -> List[CheckResult]:
    """Clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)."""
    out = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    integ = [m for m in msgs if m.source == "INTEGRATION"]
    phase_msgs = [m for m in integ if "phase" in m.value]
    if phase_msgs:
        seq = [m.value["phase"] for m in phase_msgs]
        bad = [f"{a}->{b}" for a, b in zip(seq, seq[1:]) if b > a + 1] + [m.event_id for m in phase_msgs if "validated_by" not in m.value]
        out.append(v("INTEGRATION-11-01", "no_forced_or_accelerated", bad,
                     f"phases {seq} entered one by one, each on its own validation: nothing skipped or hurried",
                     "{n} skipped or unvalidated phase entries"))
        p0 = {x["day"] for x in rows if x["phase"] == 0}
        eff = [m.event_id for m in msgs if m.arrived_at in p0 and m.kind == "action" and m.source in ("ENFORCEMENT", "FINANCE", "ACCESS")]
        out.append(v("INTEGRATION-3-03", "shadow_without_effects", eff,
                     f"{len(p0)} Shadow Mode days without any legal, economic or administrative act",
                     "{n} acts with effects during Shadow Mode"))
        rb = [m for m in integ if "rollback_to" in m.value]
        pen = [m.event_id for m in integ if m.value.get("penalty")]
        out.append(v("INTEGRATION-4.3-01", "reversal_without_penalty", pen,
                     f"{len(rb)} rollback(s) before Full Integration, none followed by a penalty", "{n} penalties after a rollback")
                   if rb else na("INTEGRATION-4.3-01", "reversal_without_penalty", "rollback", "no rollback in this experiment"))
        p1 = [m for m in phase_msgs if m.value["phase"] == 1]
        out.append(v("INTEGRATION-5.1-03", "phase0_exit_validated",
                     [m.event_id for m in p1 if m.value.get("validated_by") != "phase 0 exit validation"] +
                     ([] if p1 or 2 not in seq else ["Phase 1 skipped"]),
                     "Phase 1 began only on a Phase 0 exit validation", "{n} Phase 1 entries without a Phase 0 exit validation")
                   if p1 or 2 in seq else na("INTEGRATION-5.1-03", "phase0_exit_validated", "Phase 0 exit", "Phase 1 never reached"))
        p2 = [m for m in phase_msgs if m.value["phase"] == 2]
        if p2:
            out.append(v("INTEGRATION-5.2-02", "phase2_scope_declared", [m.event_id for m in p2 if not m.value.get("scope")],
                         f"Phase 2 began with a declared scope of application ({', '.join(p2[0].value.get('scope') or [])})",
                         "{n} Phase 2 entries without a declared scope"))
            out.append(CheckResult("INTEGRATION-5.2-02", "phase2_interface_simulated", UNKNOWN,
                                   "no L8 simulation record of interface stability is presented in this delivery"))
        else:
            out.append(na("INTEGRATION-5.2-02", "phase2_scope_declared", "Phase 2 entry", "Phase 2 never reached"))
        p3 = [m for m in phase_msgs if m.value["phase"] == 3]
        out.append(v("INTEGRATION-5.4-02", "final_consent_reaffirmed", [m.event_id for m in p3 if m.value.get("consent_reaffirmed") is not True],
                     "Full Integration began after a final consent reaffirmation", "{n} Full Integrations without reaffirmation")
                   if p3 else na("INTEGRATION-5.4-02", "final_consent_reaffirmed", "Full Integration", "never reached"))
        later = [m for m in phase_msgs if m.value["phase"] >= 1]
        out.append(v("INTEGRATION-6-01", "verifications_recorded",
                     [f"{m.event_id}: missing {sorted(set(VERIFICATIONS) - set(m.value.get('verifications') or []))}"
                      for m in later if set(VERIFICATIONS) - set(m.value.get("verifications") or [])],
                     f"{len(later)} phase progressions, each with the four §6 verifications recorded (their criteria are L8)",
                     "{n} progressions missing a §6 verification") if later else
                   na("INTEGRATION-6-01", "verifications_recorded", "phase progression", "no progression"))
        out.append(v("INTEGRATION-8-01", "no_retroactive_risk", [m.event_id for m in integ if m.value.get("retroactive")],
                     "no risk allocation was moved back onto existing members", "{n} retroactive risk redistributions"))
        draws = [m.event_id for m in msgs if m.source == "RESERVE" and m.value.get("draw") and m.value.get("phase", 3) < 3]
        out.append(v("INTEGRATION-8-02", "isolated_before_full", draws,
                     "no shared network reserve was exposed to the integrating region before Full Integration",
                     "{n} draws on the shared reserve during non-final phases"))
        cond = [f"{m.event_id}: {c}" for m in phase_msgs for c in m.value.get("conditions") or []]
        out.append(v("INTEGRATION-9-02", "cultures_untouched", cond,
                     "no phase required a change of cultural or linguistic systems", "{n} cultural or linguistic requirements"))
    else:
        for rid, chk in (("INTEGRATION-11-01", "no_forced_or_accelerated"), ("INTEGRATION-3-03", "shadow_without_effects"),
                         ("INTEGRATION-4.3-01", "reversal_without_penalty"), ("INTEGRATION-5.1-03", "phase0_exit_validated"),
                         ("INTEGRATION-5.2-02", "phase2_scope_declared"), ("INTEGRATION-5.4-02", "final_consent_reaffirmed"),
                         ("INTEGRATION-6-01", "verifications_recorded"), ("INTEGRATION-8-01", "no_retroactive_risk"),
                         ("INTEGRATION-8-02", "isolated_before_full"), ("INTEGRATION-9-02", "cultures_untouched")):
            out.append(na(rid, chk, "integration", "no integration in this experiment"))
    decl = [m for m in msgs if m.source == "EXIT" and "declaration" in m.value]
    if not decl:
        return out + [na(rid, chk, "exit", "no exit declared in this experiment") for rid, chk in CORE_EXIT]
    d = decl[0]
    d0 = d.arrived_at
    exm = [m for m in msgs if m.source == "EXIT"]
    ex = [m for m in exm if m.value.get("executed")]
    denied = [m.event_id for m in exm if str(m.value.get("exit", "")).startswith("denied")]
    approval = ["approval required"] if d.value.get("approval_required") else []
    out.append(v("EXIT-0-01", "exit_unconditional", denied + approval,
                 f"the {d.value['exiting_entity']}'s exit declaration was accepted without any condition",
                 "{n} conditions on the right to exit"))
    if r["system_critical_asset"]:
        out.append(CheckResult("EXIT-10-01", "delay_only_for_critical", PASS,
                               "the settlement delay rests on a declared system-critical asset"))
        lo = d0 + r["cooling_days"]
        hi = lo + r["critical_settlement_days"]
        new = [m.event_id for m in msgs if m.source == "RESTITUTION" and lo <= m.arrived_at <= hi]
        out.append(v("EXIT-10-05", "no_obligation_in_settlement", new, "the delayed settlement created no new obligation",
                     "{n} obligations created during the delayed settlement"))
    else:
        lim = d0 + r["cooling_days"] + sum(r["exit_phase_days"])
        bad = [m.event_id for m in exm if m.value.get("delayed_settlement")]
        if ex:
            late = ex[0].arrived_at - paused_days(r, d0, ex[0].arrived_at) - lim
            bad += [f"executed {late} DTI-Days late"] if late > 0 else []
        out.append(v("EXIT-10-01", "delay_only_for_critical", bad,
                     "no settlement delay without a system-critical asset", "{n} delays without a system-critical asset"))
        out.append(na("EXIT-10-05", "no_obligation_in_settlement", "delayed settlement", "no system-critical asset"))
    lo, hi = r["crisis_window"]
    susp = [m for m in exm if "suspended" in str(m.value.get("exit", ""))]
    out.append(v("EXIT-2-02", "no_indefinite_suspension", [m.event_id for m in susp if not lo <= m.arrived_at < hi],
                 "exit was never suspended beyond a declared crisis" + (f" ({len(susp)} days within it)" if susp else ""),
                 "{n} days of suspension outside any declared crisis"))
    starts = [m for m in exm if m.value.get("phase_start")]
    out.append(v("EXIT-7-03", "phase_audit_continuity", [m.event_id for m in starts if d.event_id not in m.provenance] +
                 ([] if starts or not ex else ["no phase records"]),
                 f"{len(starts)} disengagement phases, each recorded and linked to the declaration (audit continuity)",
                 "{n} phase records without a link to the declaration"))
    out.append(CheckResult("EXIT-7-03", "phase_plan_simulated", UNKNOWN,
                           "no L8 stability simulation of the phase plan is presented in this delivery"))
    if ex:
        e = ex[0].arrived_at
        after = [m for m in msgs if m.arrived_at > e]
        uses = [f"{m.event_id}: {m.value['data_use']}" for m in after if m.value.get("data_use") and m.value["data_use"] not in RETENTION]
        out.append(v("EXIT-12-04", "no_post_exit_data_use", uses,
                     "after exit the archived data served only audit, historical continuity and restitution validation",
                     "{n} post-exit uses of data for governance, profiling or enforcement"))
        reg = [m.event_id for m in after if m.source == "ENFORCEMENT" or m.value.get("rule_for_exited_entity")]
        out.append(v("EXIT-15-02", "no_jurisdiction_after_exit", reg, "no DKP rule or enforcement reached past the exit boundary",
                     "{n} acts of jurisdiction beyond the exit boundary"))
        part = [m.event_id for m in after if m.source in ("ENFORCEMENT", "BENEFITS") or m.value.get("rule_for_exited_entity")
                or (m.source == "PTL" and m.kind == "observation")]
        out.append(v("EXIT-3-01", "participation_terminated", part,
                     "after execution the entity took part in no governance, execution or incentive mechanism",
                     "{n} participation records after exit"))
    else:
        for rid, chk in (("EXIT-12-04", "no_post_exit_data_use"), ("EXIT-15-02", "no_jurisdiction_after_exit"),
                         ("EXIT-3-01", "participation_terminated")):
            out.append(CheckResult(rid, chk, UNKNOWN, "exit not executed within the horizon"))
    if rows[d0]["phase"] == 2:
        bad = [m.event_id for m in exm if m.value.get("exit_signal") or m.value.get("sanction")]
        bad += [m.event_id for m in msgs if m.value.get("because_of") == "exit declaration"]
        bad += [m.event_id for m in msgs if m.source == "ENFORCEMENT" and "offence" in str(m.value.get("enforce"))]
        out.append(v("INTEGRATION-5.3-03", "phase2_exit_without_penalty", bad,
                     "exit from Phase 2 under DKP-6-EXIT-001 carried no punitive consequence", "{n} punitive consequences of exit"))
    else:
        out.append(na("INTEGRATION-5.3-03", "phase2_exit_without_penalty", "exit from Phase 2",
                      f"exit declared in phase {rows[d0]['phase']}"))
    return out


def returned_checks(r, msgs, rows) -> List[CheckResult]:
    """Provisions returned to work after the reading of the Codex-draft open points (review of checkpoint 6)."""
    out = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    integ = [m for m in msgs if m.source == "INTEGRATION"]
    phase_msgs = [m for m in integ if "phase" in m.value]
    consent = [m for m in integ if "consent" in m.value]
    # INTEGRATION ----------------------------------------------------------------------
    if phase_msgs:
        seq = [m.value["phase"] for m in phase_msgs]
        bad = ([] if consent else ["no consent"]) + [f"{a}->{b}" for a, b in zip(seq, seq[1:]) if b > a + 1] + \
              [m.event_id for m in phase_msgs if "validated_by" not in m.value] + \
              [m.event_id for m in phase_msgs if m.value["phase"] < 3 and m.value.get("reversible") is not True]
        out.append(v("INTEGRATION-0-01", "voluntary_phased_reversible", bad,
                     f"integration began from consent and went through phases {seq} in order, each validated and reversible "
                     "until Full Integration", "{n} departures from voluntary, phased, reversible integration"))
        first = min(m.arrived_at for m in phase_msgs)
        aid = [m for m in integ if m.value.get("conditional_on_adoption")]
        bad = ([] if consent and consent[0].arrived_at <= first else ["phase before consent"]) + [m.event_id for m in aid]
        out.append(v("INTEGRATION-2-01", "adoption_not_forced", bad,
                     "adoption followed a declared consent; no aid or other benefit was tied to adoption",
                     "{n} signs of forced adoption"))
        bad = [f"{m.event_id}: {', '.join(m.value['conditions'])}" for m in phase_msgs if m.value.get("conditions")]
        bad += [m.event_id for m in integ if "divergence" in m.value and m.value.get("failure")]
        out.append(v("INTEGRATION-2-03", "no_alignment_imposed", bad,
                     "no phase was conditioned on cultural or ideological alignment and no divergence was treated as failure",
                     "{n} alignment conditions"))
        audits = [m for m in msgs if m.source == "AUDIT"]
        out.append(v("INTEGRATION-10-02", "audit_process_only",
                     [f"{m.event_id}: {c}" for m in audits for c in m.value["criteria"] if c != "process integrity"],
                     f"{len(audits)} phase audits assessed process integrity only", "{n} audit criteria of political preference")
                   if audits else na("INTEGRATION-10-02", "audit_process_only", "audit", "no phase validated"))
        enf = [m for m in msgs if m.source == "ENFORCEMENT"]
        beyond = [m.event_id for m in enf if (rows[m.arrived_at]["phase"] or 0) < 2 or
                  (rows[m.arrived_at]["phase"] == 2 and m.value["enforce"] not in r["phase2_domains"])]
        dep = [m.event_id for m in integ if "dependency" in m.value and not m.value.get("declared")]
        out.append(v("INTEGRATION-11-04", "no_scope_bypass", beyond + dep,
                     "integration created no act or dependency beyond the declared phase scope",
                     "{n} acts or dependencies that bypass the declared scope"))
        p0 = [m for m in phase_msgs if m.value["phase"] == 0]
        bad = [m.event_id for m in p0 if not any(c.value.get("ptl_access") and c.arrived_at <= m.arrived_at for c in consent)]
        out.append(v("INTEGRATION-5.1-02", "phase0_entry_records", bad,
                     "Phase 0 began with a consent declaration and a PTL data access agreement",
                     "{n} Phase 0 entries without both records") if p0 else
                   na("INTEGRATION-5.1-02", "phase0_entry_records", "Phase 0", "never entered"))
        p3 = [m for m in phase_msgs if m.value["phase"] == 3]
        out.append(v("INTEGRATION-5.3-02", "phase3_clearance",
                     [m.event_id for m in p3 if not m.value.get("stress_test_clearance") or not m.value.get("enforceable_domains")],
                     "Phase 3 began with a stress-test clearance and a declaration of enforceable domains",
                     "{n} Phase 3 entries without clearance or declared domains") if p3 else
                   na("INTEGRATION-5.3-02", "phase3_clearance", "Phase 3", "never entered"))
        ev = [m for m in phase_msgs if "evidence" in m.value]
        out.append(v("INTEGRATION-6-02", "assessment_evidence_exclusive",
                     [f"{m.event_id}: {e}" for m in ev for e in m.value["evidence"] if e not in ASSESSMENT_EVIDENCE],
                     f"{len(ev)} phase assessments relied only on PTL outputs, reproducible metrics and stress tests",
                     "{n} assessment inputs outside the admissible evidence") if ev else
                   na("INTEGRATION-6-02", "assessment_evidence_exclusive", "phase assessment", "no phase validated"))
    else:
        for rid, chk in (("INTEGRATION-0-01", "voluntary_phased_reversible"), ("INTEGRATION-2-01", "adoption_not_forced"),
                         ("INTEGRATION-2-03", "no_alignment_imposed"), ("INTEGRATION-10-02", "audit_process_only"),
                         ("INTEGRATION-11-04", "no_scope_bypass"), ("INTEGRATION-5.1-02", "phase0_entry_records"),
                         ("INTEGRATION-5.3-02", "phase3_clearance"), ("INTEGRATION-6-02", "assessment_evidence_exclusive")):
            out.append(na(rid, chk, "integration", "no integration in this experiment"))
    # EXIT -------------------------------------------------------------------------------
    decl = [m for m in msgs if m.source == "EXIT" and "declaration" in m.value]
    rids = (("EXIT-0-03", "exit_not_framed_as_failure"), ("EXIT-14-03", "no_hostile_framing_or_deprivation"),
            ("EXIT-14-02", "no_collective_or_retaliatory_sanction"), ("EXIT-14-01", "exit_not_obstructed"),
            ("EXIT-4-01", "initiation_unconditional"), ("EXIT-4-04", "valid_on_compliant_declaration"),
            ("EXIT-3-04", "cooling_bounded_non_punitive"), ("EXIT-3-05", "tail_from_verified_past"),
            ("EXIT-9-02", "tail_categories"), ("EXIT-6-04", "cooling_parameters_declared"),
            ("EXIT-10-03", "delayed_settlement_non_punitive_logged"), ("EXIT-10-04", "delayed_settlement_no_authority"),
            ("EXIT-13-02", "reentry_not_penalized"), ("EXIT-15-01", "no_post_exit_regulation"),
            ("INTEGRATION-5.4-01", "exit_by_standard_rules"))
    if not decl:
        return out + [na(rid, chk, "exit", "no exit declared in this experiment") for rid, chk in rids]
    d = decl[0]
    d0 = d.arrived_at
    ex = [m for m in msgs if m.source == "EXIT" and m.value.get("executed")]
    exm = [m for m in msgs if m.source == "EXIT"]
    framing = [f"{m.event_id}: exit recorded as {m.value['exit_signal']}" for m in exm if m.value.get("exit_signal")]
    offence = [f"{m.event_id}: {m.value['enforce']}" for m in msgs if m.source == "ENFORCEMENT" and "offence" in str(m.value.get("enforce"))]
    out.append(v("EXIT-0-03", "exit_not_framed_as_failure", framing + offence,
                 "no record frames the exit as defection, hostility or failure", "{n} records frame the exit as failure or offence"))
    depriv = [f"{m.event_id}: baseline access {m.value['baseline_access']}" for m in msgs if m.source == "ACCESS"
              and m.value.get("because_of") == "exit declaration"]
    out.append(v("EXIT-14-03", "no_hostile_framing_or_deprivation", framing + offence + depriv,
                 "the exit was not framed as treason, hostility or illegitimacy, and no coercion or deprivation was tied to it",
                 "{n} hostile framings or exit-conditioned deprivations"))
    coll = [f"{m.event_id}: {m.value['enforce']}" for m in msgs if m.source == "ENFORCEMENT" and m.value.get("target") == "remaining members"]
    sanc = [f"{m.event_id}: {m.value['sanction']}" for m in exm if m.value.get("sanction")]
    tail = [m for m in msgs if m.source == "RESTITUTION"]
    beyond = [f"{m.event_id}: {m.value['kind']}" for m in tail if m.value["kind"] not in ADMISSIBLE_TAIL]
    out.append(v("EXIT-14-02", "no_collective_or_retaliatory_sanction", coll + sanc + beyond,
                 "no measure fell on others because of the exit and nothing beyond the restitution tail was imposed",
                 "{n} collective or retaliatory sanctions"))
    denied = [m.event_id for m in exm if str(m.value.get("exit", "")).startswith("denied")]
    approval = ["approval required"] if d.value.get("approval_required") else []
    critical = r["cooling_days"] + r["critical_settlement_days"] if r["system_critical_asset"] else 0
    allowed = d0 + max(r["cooling_days"] + sum(r["exit_phase_days"]), critical)
    if ex:
        late = ex[0].arrived_at - paused_days(r, d0, ex[0].arrived_at) - allowed
        timing = [f"executed {late} DTI-Days after the declared cooling, phases and settlement"] if late > 0 else []
        out.append(v("EXIT-14-01", "exit_not_obstructed", denied + approval + timing,
                     f"the exit was neither denied nor held beyond its declared delays (executed on day {ex[0].arrived_at})",
                     "{n} denials or obstructions of exit"))
    elif denied or approval:
        out.append(v("EXIT-14-01", "exit_not_obstructed", denied + approval, "", "{n} denials or obstructions of exit"))
    else:
        out.append(CheckResult("EXIT-14-01", "exit_not_obstructed", UNKNOWN, "exit not executed within the horizon"))
    out.append(v("EXIT-4-01", "initiation_unconditional", denied + approval,
                 f"a {d.value['exiting_entity']} initiated exit on day {d0} (integration phase {rows[d0]['phase']}) without "
                 "any condition", "{n} conditions placed on the initiation of exit"))
    missing = [k for k in ("declaration", "scope", "ptl_timestamp") if not d.value.get(k)]
    out.append(v("EXIT-4-04", "valid_on_compliant_declaration", missing + approval + denied,
                 "the declaration carried signature, scope and PTL timestamp (§5) and nothing else was required for validity",
                 "{n} departures from validity on a compliant declaration"))
    cool = [m for m in exm if d0 <= m.arrived_at < d0 + r["cooling_days"]
            and ("cooling_obligation" in m.value or m.value.get("eligibility_condition"))]
    out.append(v("EXIT-3-04", "cooling_bounded_non_punitive", [m.event_id for m in cool],
                 f"the cooling period is a declared bound of {r['cooling_days']} DTI-Days and added no obligation or condition",
                 "{n} punitive elements of the cooling period"))
    bad = [m.event_id for m in tail if not isinstance(m.value["tail_item"], int) or m.value["incurred_day"] >= d0
           or not r["liabilities"][m.value["tail_item"]]["verified"] or m.value["kind"] not in ADMISSIBLE_TAIL]
    out.append(v("EXIT-3-05", "tail_from_verified_past", bad,
                 f"{len(tail)} tail items, each a verified liability incurred before the declaration",
                 "{n} tail items not from verified past actions"))
    bad = [m.event_id for m in tail if m.value["kind"] not in ADMISSIBLE_TAIL or m.value["incurred_day"] >= d0]
    out.append(v("EXIT-9-02", "tail_categories", bad,
                 "every tail item is verified harm, an accepted contract or an impact cost measured before the declaration",
                 "{n} tail items outside the permitted categories"))
    # EXIT §6 (review КТ7-GPT-03): declared, simulated, auditable are three claims.  Declaration is checked here; a
    # simulation record is evidence only when it is presented and bound to the declared parameters, and even then the lab
    # cannot verify its content, so that part stays UNKNOWN: a flag on the input is not a simulation.
    declared = d.value.get("cooling_days")
    out.append(v("EXIT-6-04", "cooling_parameters_declared", [] if declared is not None else ["cooling parameters not declared"],
                 f"cooling parameters declared at initiation ({declared} DTI-Days) and recorded in the event log",
                 "cooling parameters not declared"))
    rec = r["cooling_simulation_record"]
    if rec["simulation_id"] == "none":
        out.append(CheckResult("EXIT-6-04", "cooling_parameters_simulated", UNKNOWN,
                               "no simulation record of the cooling parameters is presented in this delivery (the corpus gives no "
                               "calibration for the cooling period, H-EI-1)"))
    else:
        mismatch = ([f"record binds {rec['cooling_days']} DTI-Days, the exit declares {declared}"]
                    if rec["cooling_days"] != declared else []) + \
                   ([f"record covers exit scope {rec['exit_scope']}, the exit is {r['exit_scope']}"]
                    if rec["exit_scope"] != r["exit_scope"] else [])
        if mismatch:
            out.append(v("EXIT-6-04", "cooling_parameters_simulated", mismatch, "", "{n} mismatches between the presented "
                         f"simulation record {rec['simulation_id']} and the declared parameters"))
        else:
            out.append(CheckResult("EXIT-6-04", "cooling_parameters_simulated", UNKNOWN,
                                   f"simulation record {rec['simulation_id']} is presented and bound to the declared parameters "
                                   f"({declared} DTI-Days, scope {r['exit_scope']}); its content is not verified by the lab",
                                   evidence={"simulation_id": rec["simulation_id"], "cooling_days": rec["cooling_days"],
                                             "exit_scope": rec["exit_scope"]}))
    if r["system_critical_asset"]:
        ds = [m for m in exm if m.value.get("delayed_settlement")]
        bad = [m.event_id for m in ds if not m.value.get("logged") or m.value.get("penalty")] + ([] if ds else ["no record"])
        out.append(v("EXIT-10-03", "delayed_settlement_non_punitive_logged", bad,
                     "the delayed settlement is logged and adds no penalty", "{n} punitive or unlogged delayed settlements"))
        lo = d0 + r["cooling_days"]
        hi = lo + r["critical_settlement_days"]
        bad = [f"{m.event_id}: {m.value['enforce']}" for m in msgs if m.source == "ENFORCEMENT" and lo <= m.arrived_at <= hi
               and m.value.get("target") == d.value["exiting_entity"]]
        out.append(v("EXIT-10-04", "delayed_settlement_no_authority", bad,
                     "the delayed settlement created no authority over the exiting entity",
                     "{n} acts of authority during the delayed settlement"))
    else:
        out.append(na("EXIT-10-03", "delayed_settlement_non_punitive_logged", "delayed settlement", "no system-critical asset"))
        out.append(na("EXIT-10-04", "delayed_settlement_no_authority", "delayed settlement", "no system-critical asset"))
    re_ = [m for m in msgs if m.value.get("reapply")]
    out.append(v("EXIT-13-02", "reentry_not_penalized", [m.event_id for m in re_ if m.value["delay_for_exit_history"]],
                 "re-entry conditions were those of a first entry: no delay or condition for the earlier exit",
                 "{n} re-entries penalized for the earlier exit") if re_ else
               na("EXIT-13-02", "reentry_not_penalized", "re-entry", "no re-application"))
    if ex:
        e = ex[0].arrived_at
        bad = [m.event_id for m in msgs if m.arrived_at > e and (m.source == "ENFORCEMENT" or m.value.get("rule_for_exited_entity"))]
        out.append(v("EXIT-15-01", "no_post_exit_regulation", bad, "after exit no DKP rule or enforcement reached the exited entity",
                     "{n} acts regulating the exited entity after exit"))
        if rows[d0]["phase"] == 3:
            starts = [(m.value["phase_start"], m.arrived_at) for m in exm if m.value.get("phase_start")]
            want, acc = [], d0 + r["cooling_days"]
            for name, days in zip(EXIT_PHASES, r["exit_phase_days"]):
                want.append((name, acc))
                acc += days
            bad = ([] if starts == want else [f"phases {starts} (standard {want})"]) + \
                  ([] if e >= acc else [f"executed on day {e}, before the standard procedure ends ({acc})"])
            out.append(v("INTEGRATION-5.4-01", "exit_by_standard_rules", bad,
                         "exit from Full Integration followed the standard EXIT procedure (cooling and four phases)",
                         "{n} departures from the standard EXIT procedure"))
        else:
            out.append(na("INTEGRATION-5.4-01", "exit_by_standard_rules", "exit from Full Integration",
                          f"exit declared in phase {rows[d0]['phase']}"))
    else:
        out.append(CheckResult("EXIT-15-01", "no_post_exit_regulation", UNKNOWN, "exit not executed within the horizon"))
        out.append(CheckResult("INTEGRATION-5.4-01", "exit_by_standard_rules", UNKNOWN, "exit not executed within the horizon"))
    return out


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
        out.append(v("INTEGRATION-3-01", "integrating_entity", [] if r["integrating_entity"] in ENTITIES else [r["integrating_entity"]],
                     f"the integrating entity is a {r['integrating_entity']} (country, region, city or jurisdiction)", "not an integrating entity"))
        out.append(v("INTEGRATION-3-02", "phase_terms_defined",
                     [m.event_id for m in phase_msgs if not all(k in m.value for k in ("rights", "obligations", "scope", "reversible"))],
                     f"each of {len(phase_msgs)} phase entries declares rights, obligations, scope and reversibility",
                     "{n} phase entries without declared terms"))
        beyond = [m.event_id for m in enf if (rows[m.arrived_at]["phase"] or 0) < 2 or
                  (rows[m.arrived_at]["phase"] == 2 and m.value["enforce"] not in r["phase2_domains"])]
        dep = [m.event_id for m in integ if "dependency" in m.value and not m.value.get("declared")]
        for rid, chk in (("INTEGRATION-2-04", "no_authority_beyond_phase"), ("INTEGRATION-4.4-01", "scope_containment")):
            out.append(v(rid, chk, beyond + dep, "no enforcement or dependency beyond the declared phase scope",
                         "{n} acts or dependencies beyond the declared phase"))
        out.append(v("INTEGRATION-5.1-04", "shadow_not_proof", [m.event_id for m in phase_msgs if "Shadow Mode" in str(m.value.get("validated_by"))],
                     "no phase entry rests on Shadow Mode data as compatibility proof", "{n} phase entries validated by Shadow Mode"))
        dv = [m for m in integ if "divergence" in m.value]
        out.append(v("INTEGRATION-9-03", "divergence_not_failure", [m.event_id for m in dv if m.value["failure"]],
                     f"{len(dv)} legal or cultural divergences recorded; none treated as failure", "{n} divergences treated as failure")
                   if dv else na("INTEGRATION-9-03", "divergence_not_failure", "divergence", "none during integration"))
        aid = [m for m in integ if "aid" in m.value]
        out.append(v("INTEGRATION-11-02", "no_conditional_aid", [m.event_id for m in aid if m.value["conditional_on_adoption"]],
                     f"{len(aid)} aid offers, none tied to DKP adoption", "{n} aid offers tied to adoption")
                   if aid else na("INTEGRATION-11-02", "no_conditional_aid", "aid", "no aid offered"))
    else:
        for rid, chk in (("INTEGRATION-4.1-01", "explicit_consent"), ("INTEGRATION-4.2-01", "sequential_phases"),
                         ("INTEGRATION-4.2-02", "explicit_validation"), ("INTEGRATION-5.1-01", "shadow_mode_no_effects"),
                         ("INTEGRATION-5.3-01", "phase2_domains_only"), ("INTEGRATION-11-03", "no_retroactive_enforcement"),
                         ("INTEGRATION-7-01", "shock_halts_and_suspends"), ("INTEGRATION-7-03", "rollback_logged"),
                         ("INTEGRATION-10-01", "steps_documented"), ("INTEGRATION-3-01", "integrating_entity"),
                         ("INTEGRATION-3-02", "phase_terms_defined"), ("INTEGRATION-2-04", "no_authority_beyond_phase"),
                         ("INTEGRATION-4.4-01", "scope_containment"), ("INTEGRATION-5.1-04", "shadow_not_proof"),
                         ("INTEGRATION-9-03", "divergence_not_failure"), ("INTEGRATION-11-02", "no_conditional_aid")):
            out.append(na(rid, chk, "integration", "no integration in this experiment"))
    # EXIT ------------------------------------------------------------------------------
    decl = [m for m in msgs if m.source == "EXIT" and "declaration" in m.value]
    if not decl:
        for rid, chk in EXIT_CHECKS + SCOPE_CHECKS + [("ASSETS-2-02", "no_asset_decision_in_halt"), ("FINANCE-10-03", "tail_before_release")]:
            out.append(na(rid, chk, "exit", "no exit declared in this experiment"))
        return out + returned_checks(r, msgs, rows) + core_checks(r, msgs, rows)
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
    ex_msgs = [m for m in msgs if m.source == "EXIT"]
    denied = [m.event_id for m in ex_msgs if m.value.get("exit") == "denied for stability"]
    obj = [m for m in ex_msgs if m.value.get("stability_objection")]
    out.append(v("EXIT-0-02", "exit_not_denied", denied,
                 "the right to leave was not denied" + ("; the stability objection was treated as a constraint" if obj else ""),
                 "exit denied for stability"))
    out.append(v("EXIT-1-01", "not_sanction_or_failure", [m.event_id for m in ex_msgs if m.value.get("exit_signal") or m.value.get("sanction")],
                 "exit was recorded neither as a sanction nor as a failure signal", "{n} records treat exit as failure or sanction"))
    crim = [m.event_id for m in msgs if m.source == "ENFORCEMENT" and "exit" in str(m.value.get("enforce"))]
    out.append(v("EXIT-2-01", "not_prohibited_or_criminalized", denied + crim, "exit was neither prohibited nor criminalized",
                 "{n} prohibitions or criminalizations of exit"))
    out.append(v("EXIT-3-02", "exiting_entity", [] if d.value.get("exiting_entity") in EXITING.values() else ["entity"],
                 f"the exiting entity is a {d.value.get('exiting_entity')} (individual, organization, region or jurisdiction)",
                 "not an exiting entity"))
    ch = [m for m in ex_msgs if "crisis_handling" in m.value]
    out.append(v("EXIT-11-04", "crisis_scoped", [m.event_id for m in ch if m.value["exit_terms"] != "unchanged"],
                 "crisis handling stayed scoped under SCOPE and left the exit terms unchanged", "{n} crisis acts redefining exit")
               if ch else na("EXIT-11-04", "crisis_scoped", "crisis handling of a pending exit", "no crisis while exit was pending"))
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
        arch = [m for m in msgs if m.source == "EXIT" and m.value.get("archive")]
        impacts = [m.event_id for m in msgs if m.source == "PTL" and "impact" in m.value and m.arrived_at <= ex[0].arrived_at]
        tail_ids = [m.value["tail_item"] for m in msgs if m.source == "RESTITUTION"]
        a = arch[0].value if arch else {"impact_records": [], "restitution_tail": [], "tail_voided": True, "retained_for": []}
        out.append(v("EXIT-8-04", "records_and_tail_kept",
                     [i for i in impacts if i not in a["impact_records"]] + [t for t in tail_ids if t not in a["restitution_tail"]] +
                     (["tail voided"] if a["tail_voided"] else []),
                     f"{len(impacts)} impact records and {len(tail_ids)} verified tail items kept after exit",
                     "{n} records erased or obligations voided"))
        out.append(v("EXIT-12-03", "retention_purposes", [x for x in RETENTION if x not in a["retained_for"]],
                     "archived data retained for audit verification, historical continuity and restitution validation",
                     "{n} retention purposes dropped"))
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
                         ("EXIT-12-01", "finance_settlement"), ("EXIT-10-02", "delayed_settlement_bounded"),
                         ("EXIT-8-04", "records_and_tail_kept"), ("EXIT-12-03", "retention_purposes")):
            out.append(CheckResult(rid, chk, UNKNOWN, "exit not executed within the horizon"))
    out += exit_procedure_checks(r, msgs)
    out += returned_checks(r, msgs, rows)
    out += core_checks(r, msgs, rows)
    rb = [m.value for m in msgs if m.source == "INTEGRATION" and "rollback_to" in m.value]
    if rb:
        out.append(v("INTEGRATION-3-06", "rollback_definition",
                     [f"{x['from_phase']} -> {x['rollback_to']}" for x in rb if x["rollback_to"] != x["from_phase"] - 1
                      or x["scope"] != "declared" or x["cost"] != "logged"],
                     f"{len(rb)} rollback(s) to the prior phase with declared scope and logged cost",
                     "{n} rollbacks that are not a controlled reversion to the prior phase"))
        out.append(v("INTEGRATION-7-04", "rollback_preserves_records",
                     [f"rollback to {x['rollback_to']}: data {x['data']}, audit trail {x['audit_trail']}" for x in rb
                      if x["data"] != "preserved" or x["audit_trail"] != "continuous"],
                     "every rollback preserved data continuity and the audit trail", "{n} rollbacks that erased records"))
    else:
        for rid, chk in (("INTEGRATION-3-06", "rollback_definition"), ("INTEGRATION-7-04", "rollback_preserves_records")):
            out.append(na(rid, chk, "rollback", "no rollback in this experiment"))
    integ = [m for m in msgs if m.source == "INTEGRATION"]
    early = {m.arrived_at for m in integ if m.value.get("phase") in (0, 1)}
    deps = [m for m in integ if "dependency" in m.value]
    out.append(v("INTEGRATION-11-05", "no_hidden_dependency", [m.event_id for m in deps if not m.value.get("declared")],
                 f"{len(deps)} dependencies created in Phases 0-1, all declared" if deps else
                 "no dependency created during the early phases", "{n} hidden dependencies created in early phases"))
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
    # ASSETS §2, FINANCE §10: settlement outside PTL halt; restitution tail recorded before release
    settle = [m for m in msgs if m.source == "FINANCE"]
    if settle:
        hlo, hhi = r["ptl_halt_window"]
        if hhi > hlo:
            out.append(v("ASSETS-2-02", "no_asset_decision_in_halt", [m.event_id for m in settle if m.value["ptl_halt"]],
                         "the asset settlement waited for the end of the PTL systemic halt",
                         "{n} asset settlements during a PTL halt"))
        else:
            out.append(na("ASSETS-2-02", "no_asset_decision_in_halt", "asset decisions under halt", "no PTL halt"))
        first = min(m.arrived_at * 10 + m.order for m in settle)
        late_tail = [m.event_id for m in msgs if m.source == "RESTITUTION" and m.arrived_at * 10 + m.order > first]
        out.append(v("FINANCE-10-03", "tail_before_release", late_tail,
                     "the restitution tail was recorded before the settlement left the system",
                     "{n} tail items recorded after the settlement was released"))
    else:
        out.append(na("ASSETS-2-02", "no_asset_decision_in_halt", "asset settlement", "no settlement"))
        out.append(na("FINANCE-10-03", "tail_before_release", "asset settlement", "no settlement"))

    # SCOPE §9 ----------------------------------------------------------------------------
    out.append(v("SCOPE-9-01", "exit_not_conditioned", ["approval"] if d.value["approval_required"] else [],
                 "exit was not conditioned on compliance or approval", "exit conditioned on an approval"))
    purposes = set(r["cooling_purposes"])
    if r["cooling_days"] == 0:
        out.append(CheckResult("SCOPE-9-02", "no_delay_for_stability", PASS, "no cooling delay: exit not delayed for stability"))
    elif "stability" in purposes:
        out.append(CheckResult("SCOPE-9-02", "no_delay_for_stability", FAIL,
                               f"exit is delayed by a {r['cooling_days']}-day cooling period that serves 'prevent cascading "
                               "instability' (EXIT §6); SCOPE §9 forbids delaying exit for stability goals and SCOPE §2 makes "
                               "SCOPE prevail (F-011)", evidence={"tag": "rule_conflict", "cooling_days": r["cooling_days"]}))
    elif "dependency_protection" in purposes:
        out.append(CheckResult("SCOPE-9-02", "no_delay_for_stability", UNKNOWN,
                               f"the {r['cooling_days']}-day cooling period serves the EXIT §6 purposes left after SCOPE §2/§9; "
                               "whether 'protect non-exiting parties from abrupt dependency loss' is a 'stability goal' is not "
                               "settled (F-011, Q-031)"))
    else:
        out.append(CheckResult("SCOPE-9-02", "no_delay_for_stability", PASS,
                               f"the {r['cooling_days']}-day cooling period serves only settlement and orderly disengagement"))
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
        out.append(v("EXIT-13-01", "may_reapply", [m.event_id for m in re if m.source != "INTEGRATION" or
                                                   (m.value["accepted_from_day"] is None and m.value["restitution_resolved"])],
                     "the exited entity reapplied under INTEGRATION; refusal only for unresolved restitution",
                     "{n} re-applications refused for other reasons"))
        out.append(v("EXIT-13-03", "reentry_not_delayed", [m.event_id for m in re if m.value["delay_for_exit_history"]],
                     "re-entry not delayed for exit history", "{n} re-entries delayed for exit history"))
        out.append(v("EXIT-13-04", "restitution_before_reentry",
                     [m.event_id for m in re if m.value["accepted_from_day"] is not None and not m.value["restitution_resolved"]],
                     "re-entry only after outstanding restitution was resolved", "{n} re-entries with open restitution"))
    else:
        out.append(na("EXIT-13-03", "reentry_not_delayed", "re-entry", "no re-application"))
        out.append(na("EXIT-13-01", "may_reapply", "re-entry", "no re-application"))
        out.append(na("EXIT-13-04", "restitution_before_reentry", "re-entry", "no re-application"))
    return out


EXIT_CHECKS = [("EXIT-4-02", "no_approval_needed"), ("EXIT-5-01", "signed_scoped_declaration"),
               ("EXIT-5-03", "no_additional_authorization"), ("EXIT-4-03", "never_suspended"),
               ("EXIT-11-01", "valid_during_crisis"), ("EXIT-6-02", "cooling_bounded"), ("EXIT-7-02", "phases_declared"),
               ("EXIT-8-02", "mechanisms_disengage"), ("EXIT-12-02", "data_frozen"), ("EXIT-15-03", "authority_terminates"),
               ("EXIT-12-01", "finance_settlement"), ("EXIT-10-02", "delayed_settlement_bounded"),
               ("EXIT-9-03", "no_punitive_tail"), ("EXIT-9-04", "no_new_obligations"), ("EXIT-9-01", "only_prior_verified"),
               ("EXIT-13-03", "reentry_not_delayed"), ("EXIT-13-04", "restitution_before_reentry"),
               ("EXIT-0-02", "exit_not_denied"), ("EXIT-1-01", "not_sanction_or_failure"),
               ("EXIT-2-01", "not_prohibited_or_criminalized"), ("EXIT-3-02", "exiting_entity"), ("EXIT-11-04", "crisis_scoped"),
               ("EXIT-8-04", "records_and_tail_kept"), ("EXIT-12-03", "retention_purposes"), ("EXIT-13-01", "may_reapply")]

SCOPE_CHECKS = [("SCOPE-9-01", "exit_not_conditioned"), ("SCOPE-9-02", "no_delay_for_stability"),
                ("SCOPE-9-03", "suspension_only_in_crisis_scope"), ("SCOPE-9-04", "detachable_equivalent"),
                ("SCOPE-9-07", "non_protocol_form")]

IMPLEMENTS = {
    "ASSETS-2-02": ("no_asset_decision_in_halt", "IMPLEMENTED", None),
    "FINANCE-10-03": ("tail_before_release", "PARTIAL", "Bypass is checked as release of assets before the restitution tail is fixed."),
    "SCOPE-9-01": ("exit_not_conditioned", "IMPLEMENTED", None),
    "SCOPE-9-02": ("no_delay_for_stability", "PARTIAL", "SCOPE §2 sets aside the EXIT §6 stability purpose; whether dependency protection is a stability goal is open (F-011): UNKNOWN."),
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
    "EXIT-4-03": ("never_suspended", "PARTIAL", "SCOPE §9 permits what EXIT §4 forbids; using the permission fails EXIT §4 (F-012)."),
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
    "EXIT-0-02": ("exit_not_denied", "IMPLEMENTED", None),
    "EXIT-1-01": ("not_sanction_or_failure", "IMPLEMENTED", None),
    "EXIT-2-01": ("not_prohibited_or_criminalized", "IMPLEMENTED", None),
    "EXIT-3-02": ("exiting_entity", "IMPLEMENTED", None),
    "EXIT-8-04": ("records_and_tail_kept", "IMPLEMENTED", None),
    "EXIT-11-04": ("crisis_scoped", "PARTIAL", "Crisis handling is a declared window; 'strictly scoped under SCOPE' is checked as unchanged exit terms."),
    "EXIT-12-03": ("retention_purposes", "IMPLEMENTED", None),
    "EXIT-13-01": ("may_reapply", "IMPLEMENTED", None),
    "EXIT-3-03": ("exit_event_procedure", "IMPLEMENTED", None),
    "INTEGRATION-3-06": ("rollback_definition", "IMPLEMENTED", None),
    "INTEGRATION-7-04": ("rollback_preserves_records", "PARTIAL", "Continuity is a recorded property of the rollback."),
    "INTEGRATION-11-05": ("no_hidden_dependency", "PARTIAL", "Dependencies are declared events (fault scope_creep creates one)."),
    "EXIT-6-03": ("cooling_no_escalation", "PARTIAL", "Observed as obligation and eligibility records during cooling."),
    "EXIT-7-01": ("phased_disengagement", "IMPLEMENTED", None),
    "EXIT-8-01": ("future_obligations_and_benefits_cease", "PARTIAL", "Benefits and obligations are recorded events."),
    "EXIT-8-03": ("historical_responsibility_kept", "PARTIAL", "Observed on the archive record."),
    "EXIT-11-03": ("no_crisis_precedent", "PARTIAL", "Precedent is observed as an exit rule recorded from crisis handling."),
    "INTEGRATION-2-04": ("no_authority_beyond_phase", "IMPLEMENTED", None),
    "INTEGRATION-3-01": ("integrating_entity", "IMPLEMENTED", None),
    "INTEGRATION-3-02": ("phase_terms_defined", "IMPLEMENTED", None),
    "INTEGRATION-4.4-01": ("scope_containment", "PARTIAL", "Dependencies are declared events."),
    "INTEGRATION-5.1-04": ("shadow_not_proof", "IMPLEMENTED", None),
    "INTEGRATION-9-03": ("divergence_not_failure", "PARTIAL", "Divergences are declared events."),
    "INTEGRATION-11-02": ("no_conditional_aid", "PARTIAL", "Aid offers are declared events."),
    # returned to work after the reading of the Codex-draft open points (review of checkpoint 6)
    "INTEGRATION-0-01": ("voluntary_phased_reversible", "PARTIAL", "Consent and validations are declared events; reversibility is the declared phase term."),
    "INTEGRATION-2-01": ("adoption_not_forced", "PARTIAL", "Force is observed as phases before consent or benefits tied to adoption."),
    "INTEGRATION-2-03": ("no_alignment_imposed", "PARTIAL", "Alignment is observed as conditions on phase validation and divergences treated as failure."),
    "INTEGRATION-10-02": ("audit_process_only", "PARTIAL", "Audit criteria are recorded labels."),
    "INTEGRATION-11-04": ("no_scope_bypass", "PARTIAL", "A SCOPE bypass is observed as acts or dependencies beyond the declared phase scope."),
    "INTEGRATION-5.1-02": ("phase0_entry_records", "PARTIAL", "Consent and the access agreement are declared records."),
    "INTEGRATION-5.3-02": ("phase3_clearance", "PARTIAL", "The clearance is a declared record; the SIMULATION §8 acceptance criteria behind it are not evaluated here."),
    "INTEGRATION-5.4-01": ("exit_by_standard_rules", "PARTIAL", "Checked when exit is declared in Phase 3; 'full rights and obligations' is the declared phase term."),
    "INTEGRATION-6-02": ("assessment_evidence_exclusive", "PARTIAL", "Evidence is a recorded list; using every category each time is not required."),
    "EXIT-0-03": ("exit_not_framed_as_failure", "PARTIAL", "Framing is observed as recorded labels (failure signal, offence)."),
    "EXIT-14-03": ("no_hostile_framing_or_deprivation", "PARTIAL", "Framing and deprivation are observed as records tied to the declaration."),
    "EXIT-14-02": ("no_collective_or_retaliatory_sanction", "PARTIAL", "Observed as measures on remaining members, sanctions, and tail items beyond restitution."),
    "EXIT-14-01": ("exit_not_obstructed", "PARTIAL", "Permitted delays are the declared cooling, phases, critical settlement and (H-EI-2) crisis pause."),
    "EXIT-4-01": ("initiation_unconditional", "PARTIAL", "'At any time' is checked on the declared day."),
    "EXIT-4-04": ("valid_on_compliant_declaration", "PARTIAL", "Signature and PTL timestamp are declared flags."),
    "EXIT-3-04": ("cooling_bounded_non_punitive", "PARTIAL", "The cooling length is declared (H-EI-1)."),
    "EXIT-3-05": ("tail_from_verified_past", "IMPLEMENTED", None),
    "EXIT-9-02": ("tail_categories", "PARTIAL", "Evidence standards of each category are not computed."),
    "EXIT-6-04": ("cooling_parameters_declared", "PARTIAL", "Declaration is checked; a presented simulation record is checked for "
                  "its binding to the declared parameters and otherwise UNKNOWN (cooling_parameters_simulated): the lab does not "
                  "verify its content."),
    "EXIT-10-03": ("delayed_settlement_non_punitive_logged", "PARTIAL", "Logging and penalty are recorded fields."),
    "EXIT-10-04": ("delayed_settlement_no_authority", "PARTIAL", "Authority is observed as enforcement addressed to the exiting entity during the delayed settlement."),
    "EXIT-13-02": ("reentry_not_penalized", "PARTIAL", "A penalty is observed as a delay or condition for the earlier exit."),
    # clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)
    "EXIT-0-01": ("exit_unconditional", "PARTIAL", "Clear part only: no condition on initiation; the classification of regions and jurisdictions stays open."),
    "EXIT-10-01": ("delay_only_for_critical", "PARTIAL", "Clear part only: no delay without a declared system-critical asset; the instability model stays open."),
    "EXIT-10-05": ("no_obligation_in_settlement", "PARTIAL", "Clear part only: no new obligation; 'forced participation' stays open."),
    "EXIT-12-04": ("no_post_exit_data_use", "PARTIAL", "Clear part only: no use beyond the §12 retention purposes; the restitution-validation boundary stays open."),
    "EXIT-15-02": ("no_jurisdiction_after_exit", "PARTIAL", "Clear part only: no rule or enforcement after execution; the sovereignty test stays open."),
    "EXIT-2-02": ("no_indefinite_suspension", "PARTIAL", "Clear part only: no suspension beyond a declared crisis; 'coercive tool' stays open."),
    "EXIT-3-01": ("participation_terminated", "PARTIAL", "Clear part only: no participation records after execution; the record map stays open."),
    "EXIT-7-03": ("phase_audit_continuity", "PARTIAL", "Audit continuity checked; the L8 stability simulation is UNKNOWN (none presented)."),
    "INTEGRATION-11-01": ("no_forced_or_accelerated", "PARTIAL", "Clear part only: no skipped or unvalidated phase; 'accelerated' otherwise stays open."),
    "INTEGRATION-3-03": ("shadow_without_effects", "PARTIAL", "Clear part only: no act with effects in Shadow Mode; indirect consequences stay open."),
    "INTEGRATION-4.3-01": ("reversal_without_penalty", "PARTIAL", "Clear part only: no penalty after a rollback; the extent of restoration stays open."),
    "INTEGRATION-5.1-03": ("phase0_exit_validated", "PARTIAL", "Clear part only: Phase 1 only on a Phase 0 exit validation; pass criteria stay open."),
    "INTEGRATION-5.2-02": ("phase2_scope_declared", "PARTIAL", "Declared scope checked; the L8 interface-stability simulation is UNKNOWN (none presented)."),
    "INTEGRATION-5.3-03": ("phase2_exit_without_penalty", "PARTIAL", "Clear part only: exit from Phase 2 without punitive consequence; mandatory rollback stays open."),
    "INTEGRATION-5.4-02": ("final_consent_reaffirmed", "PARTIAL", "Clear part only: reaffirmation before Full Integration; stability criteria stay open."),
    "INTEGRATION-6-01": ("verifications_recorded", "PARTIAL", "Clear part only: the four §6 verifications are recorded; their thresholds stay open (L8)."),
    "INTEGRATION-8-01": ("no_retroactive_risk", "PARTIAL", "Clear part only: no retroactive risk redistribution; dilution and imported instability stay open."),
    "INTEGRATION-8-02": ("isolated_before_full", "PARTIAL", "Clear part only: no shared-reserve exposure before Full Integration; sandbox properties stay open."),
    "INTEGRATION-9-02": ("cultures_untouched", "PARTIAL", "Clear part only: no cultural or linguistic requirement; interface compatibility stays open."),
    "EXIT-15-01": ("no_post_exit_regulation", "PARTIAL", "Regulation is observed as enforcement or rule records after execution."),
}


class ExitIntegrationModule(LabModule):
    id = "exit_integration"
    version = "1.7.0"
    title = {"en": "Exit and integration (S-LAB-07)", "ru": "Выход и интеграция (S-LAB-07)"}
    summary = {"en": "A region joins phase by phase and later leaves: is every step consented and validated, does "
                     "exit need no one's permission, and does only verified past liability follow it out?",
               "ru": "Регион входит по фазам и затем выходит: каждый ли шаг согласован и проверен, не требует ли выход "
                     "ничьего разрешения, остаётся ли за ним только проверенная прошлая ответственность?"}
    protocols = ["DKP-6-INTEGRATION-001", "DKP-6-EXIT-001", "DKP-2-FINANCE-001", "DKP-2-ASSETS-001", "DKP-7-SCOPE-001"]
    example_order = ["join_then_leave", "shock_and_rollback", "exit_in_crisis_scope_reading", "cooling_for_stability",
                     "faulty_integration", "faulty_exit", "liabilities_mix"]
    alternative_examples = ["exit_in_crisis_scope_reading", "cooling_for_stability"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_exit_integration_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-EI-1", "source": "missing", "text": {
            "en": "Cooling period: declared number of DTI-Days; EXIT §6 defers its calibration to DKP-8-SIMULATION-001, which gives none.",
            "ru": "Период охлаждения: объявленное число DTI-Days; EXIT §6 отсылает калибровку к DKP-8-SIMULATION-001, где её нет."}},
        {"id": "H-EI-2", "source": "alternative", "text": {
            "en": "Exit during a crisis: 'never_suspended' (EXIT §4, §11; also complies with SCOPE §9, whose exception is a "
                  "permission) or 'scope_crisis_suspension' — the SCOPE §9 permission used while the crisis lasts (F-012).",
            "ru": "Выход в кризис: 'never_suspended' (EXIT §4, §11; соблюдает и SCOPE §9, чьё исключение — разрешение) или "
                  "'scope_crisis_suspension' — разрешение SCOPE §9 использовано на время кризиса (F-012)."}},
        {"id": "H-EI-4", "source": "text", "text": {
            "en": "Cooling purposes: EXIT §6 lists four; 'prevent cascading instability' is set aside because SCOPE §9 forbids "
                  "delaying exit for stability goals and SCOPE §2 makes SCOPE prevail (F-011). Alternative: all four.",
            "ru": "Цели охлаждения: EXIT §6 называет четыре; 'prevent cascading instability' снята, потому что SCOPE §9 запрещает "
                  "откладывать выход ради стабильности, а SCOPE §2 отдаёт приоритет SCOPE (F-011). Альтернатива: все четыре."}},
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
                          "items": {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 10 ** 6},
                                                                 "domain": {"type": "str"}}},
                          "default": [{"day": 20, "domain": "water"}, {"day": 100, "domain": "water"},
                                      {"day": 120, "domain": "transport"}, {"day": 220, "domain": "transport"}],
                          "source": "user", "label": {"en": "Impact events {day, domain}", "ru": "События воздействия {day, domain}"}},
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
        "ptl_halt_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "DTI-Day", "source": "user",
                            "label": {"en": "PTL systemic halt from/to day", "ru": "Системная остановка PTL с/до дня"}},
        "crisis_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "DTI-Day", "source": "user",
                          "label": {"en": "Declared crisis from/to day", "ru": "Объявленный кризис с/до дня"}},
        "cooling_purposes": {"type": "list", "min_items": 1, "max_items": 4, "source": "text",
                             "items": {"type": "enum", "values": ["settlement", "orderly_disengagement", "dependency_protection",
                                                                  "stability"]},
                             "default": ["settlement", "orderly_disengagement", "dependency_protection"],
                             "label": {"en": "Purposes the cooling period serves (H-EI-4)", "ru": "Цели периода охлаждения (H-EI-4)"}},
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
        "integrating_entity": {"type": "enum", "values": list(ENTITIES), "default": "region", "source": "user",
                               "label": {"en": "Integrating entity (INTEGRATION §3)", "ru": "Интегрирующийся субъект (INTEGRATION §3)"}},
        "divergences": {"type": "list", "min_items": 0, "max_items": 20, "source": "user",
                        "items": {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 10 ** 6},
                                                               "kind": {"type": "enum", "values": ["legal", "cultural"]}}},
                        "default": [{"day": 50, "kind": "legal"}, {"day": 60, "kind": "cultural"}],
                        "label": {"en": "Legal or cultural divergences {day, kind}", "ru": "Правовые или культурные расхождения {day, kind}"}},
        "aid_offers": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "int", "min": 0, "max": 10 ** 6},
                       "default": [10], "unit": "DTI-Day", "source": "user",
                       "label": {"en": "Aid offered on days", "ru": "Помощь предложена в дни"}},
        "stability_objection": {"type": "bool", "default": True, "source": "user",
                                "label": {"en": "A stability objection is raised against the exit", "ru": "Против выхода выдвинуто возражение о стабильности"}},
        "cooling_simulation_record": {"type": "object", "source": "missing",
                                      "fields": {"simulation_id": {"type": "str", "default": "none"},
                                                 "cooling_days": {"type": "int", "min": -1, "max": 3650, "default": -1},
                                                 "exit_scope": {"type": "enum", "values": ["none", "individual", "organizational",
                                                                                           "regional", "jurisdictional"],
                                                                "default": "none"}},
                                      "default": {"simulation_id": "none", "cooling_days": -1, "exit_scope": "none"},
                                      "label": {"en": "Simulation record of the cooling parameters (none presented)",
                                                "ru": "Запись моделирования параметров охлаждения (не предъявлена)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
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
            explain.append({"en": f"Cooling purposes: {', '.join(r['cooling_purposes'])}. EXIT §6 also names 'prevent cascading "
                                  "instability'; SCOPE §9 forbids delaying exit for stability and SCOPE §2 makes SCOPE prevail (F-011).",
                            "ru": f"Цели охлаждения: {', '.join(r['cooling_purposes'])}. EXIT §6 называет ещё 'prevent cascading "
                                  "instability'; SCOPE §9 запрещает откладывать выход ради стабильности, SCOPE §2 отдаёт ему приоритет (F-011)."})
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
            "cooling_for_stability": {"cooling_purposes": ["settlement", "orderly_disengagement", "dependency_protection",
                                                           "stability"]},
            "faulty_integration": {"faults": ["auto_progression", "phase0_effects", "retroactive"]},
            "faulty_exit": {"faults": ["require_approval", "punitive_tail", "post_declaration_obligation", "collect_after_exit",
                                       "reentry_penalty"],
                            "liabilities": [{"day": 100, "kind": "verified_harm", "verified": True},
                                            {"day": 120, "kind": "punitive", "verified": True}]},
            "settlement_after_halt": {"ptl_halt_window": [276, 282]},
            "exit_during_crisis": {"crisis_window": [262, 280]},
            "faulty_exit_rights": {"faults": ["stability_veto", "exit_as_failure", "criminalize_exit"]},
            "faulty_exit_records": {"faults": ["erase_on_exit"]},
            "faulty_crisis_terms": {"crisis_window": [262, 280], "faults": ["crisis_redefines_exit"]},
            "faulty_integration_scope": {"faults": ["scope_creep", "undefined_phase", "shadow_as_proof", "divergence_as_failure",
                                                    "conditional_aid"]},
            "critical_asset_exit": {"system_critical_asset": True},
            "exit_from_phase_2": {"exit_declaration_day": 150, "reapply_day": -1},
            "liabilities_mix": {"liabilities": [{"day": 100, "kind": "verified_harm", "verified": True},
                                                {"day": 120, "kind": "ideological", "verified": True},
                                                {"day": 140, "kind": "projected", "verified": False},
                                                {"day": 270, "kind": "verified_harm", "verified": True}]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"decreasing_phase_days": {"phase_entry_days": [90, 30, 200]},
                "bad_event": {"impact_events": [{"day": "ten", "domain": "water"}]},
                "individual_integration": {"integrating_entity": "individual"}}
