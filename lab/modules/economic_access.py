"""
ECONOMIC ACCESS module — financial access and property rights under Justice outcomes and disputes.

DKP-2-FINANCE-001 §11 (automatic suspension under Exclusion, restoration only on exit, within one
DTI-Day after a successful dispute, no restoration by a pending dispute, no accrual during the Status
Quo Suspension, polling of the Justice domain), §4.2 (no subjective time preference), §3.1/§12
(deterministic ledger) → DKP-2-ASSETS-001 §2 (no asset decision during a PTL halt or unresolved
divergence), §8 (revocation, rule-based reallocation, dispute window, escrow, return or equivalent
value, no prejudice, epistemic metadata), §10 (transfer with obligations), §11 (non-essential control
suspended, life-preserving access kept), §12 (no hidden ownership) → DKP-4-ERROR-001 §7 (30 DTI-Days,
E1 without limitation, Status Quo Suspension up to 7 DTI-Days).

Time step: one hour; days are DTI-Days from ``start_dti_day``.  The Justice domain timeline and the
dispute dates are inputs (the Justice computation itself is in module ``dispute_correction``).

Declared readings:
  * FINANCE §11.2(b) cites "DKP-4-ERROR-001 Section 4.1", which does not exist (F-004); the Status Quo
    Suspension is the one of ERROR §7 (up to 7 DTI-Days from validation) — input ``status_quo_days``;
  * the minimum PTL TTL for identity-related measurements (FINANCE §11.2(c)) is not in ORACLE §17 —
    input ``identity_ttl_minutes`` marked missing;
  * ASSETS §8.3(a) counts the dispute window from execution, ERROR §7 from the recording of the
    decision: when the two clocks disagree for a filing, the checker reports UNKNOWN (H-EA-3);
  * ASSETS §8.1 revokes Property Rights under Restriction, Isolation or Exclusion; §11 restricts
    non-essential control and keeps life-preserving access: scope reading H-EA-2;
  * interest has no formula (FINANCE §3.2, §4.1): a declared daily rate; only *when* it accrues is checked.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message, epistemic_problems
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

DOMAINS = ("none", "restitution", "restriction", "isolation", "exclusion")
RIE = ("restriction", "isolation", "exclusion")                  # ASSETS §8.1, §11
WINDOW_DAYS = 30                                                 # ERROR §7, ASSETS §8.3(a)
FAULTS = {
    "finance_ignores_exclusion": "financial access is not suspended under Exclusion",
    "alternative_pathway": "a compensatory credit line is opened during the suspension",
    "restore_on_filing": "access is restored when a dispute is filed",
    "late_restore": "access is restored two days after a successful dispute",
    "accrue_during_status_quo": "interest accrues during the Status Quo Suspension",
    "time_preference_discount": "obligations are discounted by a pure time preference",
    "revoke_life_access": "access to a life-preserving asset is removed",
    "no_escrow": "reallocation proceeds are paid out although a validated dispute is pending",
    "prejudice": "filing a dispute adds a restriction",
    "missing_metadata_enforced": "a revocation order without epistemic metadata is executed",
    "act_during_halt": "asset decisions are executed during a PTL systemic halt",
    "no_return": "a returnable asset is not returned after a successful dispute",
    "committee_override": "a committee decides a reallocation instead of the open rule",
    "late_dispute_accepted": "a non-E1 dispute filed after both windows is accepted",
    "transfer_without_obligations": "an asset is transferred without its justice obligations",
    "inheritance_clears_attribution": "a transfer erases the historical attribution",
    "accept_shell": "an asset held through a shell structure is recognised as owned",
}
ASSET = {"type": "object", "fields": {
    "id": {"type": "str"},
    "essential": {"type": "bool", "default": False},
    "value": {"type": "number", "min": 0, "max": 10 ** 9, "default": 100},
    "returnable": {"type": "bool", "default": True},
    "bound_to_subject": {"type": "bool", "default": True}}}

DISPUTE = {"filed_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 6},
           "category": {"type": "enum", "values": ["E1", "E2", "E3", "E4", "E5"], "default": "E3"},
           "validated_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 7},
           "resolved_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 18},
           "outcome": {"type": "enum", "values": ["success", "rejected"], "default": "success"},
           "domain_after": {"type": "enum", "values": list(DOMAINS), "default": "none"}}
TRANSFER = {"day": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1},
            "asset": {"type": "str", "default": "home"},
            "obligations_transferred": {"type": "bool", "default": True}}


def md(scope: str) -> Dict[str, Any]:
    return {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": scope, "revalidation_required": True, "dispute_allowed": True}


def timeline(r: Dict[str, Any]) -> List[Tuple[int, str]]:
    """Justice domain changes (day, domain); a successful, accepted dispute sets ``domain_after``."""
    ev = sorted((e["day"], e["domain"]) for e in r["justice"])
    d = r["dispute"]
    if accepted(r) and d["outcome"] == "success" and d["resolved_day"] >= 0:
        ev = sorted(ev + [(d["resolved_day"], d["domain_after"])], key=lambda x: x[0])
    return ev


def domain_on(ev: List[Tuple[int, str]], day: int) -> str:
    cur = "none"
    for d, dom in ev:
        if d <= day:
            cur = dom
    return cur


def onset(r: Dict[str, Any]) -> Optional[int]:
    """First day the recorded Justice domain is Restriction, Isolation or Exclusion."""
    ev = sorted((e["day"], e["domain"]) for e in r["justice"])
    for d, dom in ev:
        if dom in RIE:
            return d
    return None


def halted(r: Dict[str, Any], day: int) -> bool:
    lo, hi = r["ptl_halt_window"]
    return lo <= day < hi


def after_halt(r: Dict[str, Any], day: int) -> int:
    return r["ptl_halt_window"][1] if halted(r, day) else day


def execution_day(r: Dict[str, Any]) -> Optional[int]:
    d = onset(r)
    return None if d is None else after_halt(r, d + r["execution_delay_days"])


def windows(r: Dict[str, Any]) -> Tuple[Optional[bool], Optional[bool]]:
    """(within ERROR §7 clock, within ASSETS §8.3(a) clock) for the filing; None if not applicable."""
    d, f = onset(r), r["dispute"]["filed_day"]
    if d is None or f < 0:
        return None, None
    e = execution_day(r)
    return f - d <= WINDOW_DAYS, f - e <= WINDOW_DAYS


def accepted(r: Dict[str, Any]) -> bool:
    d = r["dispute"]
    if d["filed_day"] < 0 or onset(r) is None:
        return False
    if d["category"] == "E1" or "late_dispute_accepted" in r["faults"]:
        return True
    by_error, by_assets = windows(r)
    return by_assets if r["dispute_clock"] == "execution" else by_error


def run(r: Dict[str, Any]) -> Tuple[EventLog, Dict[str, Any]]:
    faults = set(r["faults"])
    log = EventLog("hour", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, h, value, prov=(), epistemic=None):
        n["i"] += 1
        k = h // 24
        return log.append(Message(event_id=f"{source.lower().replace('/', '-')}-{h:06d}-{n['i']:05d}", kind=kind,
                                  source=source, arrived_at=h, decided_at=h if kind in ("decision", "action") else None,
                                  value={**value, "day": k, "dti": canonical(*dy_doy(r["start_dti_day"] + k))},
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    ev = timeline(r)
    disp = r["dispute"]
    acc = accepted(r)
    val_day = disp["validated_day"] if acc else -1
    res_day = disp["resolved_day"] if acc else -1
    sq = (val_day, val_day + r["status_quo_days"]) if val_day >= 0 else (-1, -1)
    poll = r["poll_interval_minutes"]
    owned = {a["id"]: a for a in r["assets"] if a["bound_to_subject"] or "accept_shell" in faults}
    ignore_halt = "act_during_halt" in faults

    def can_act(k):
        return ignore_halt or not halted(r, k)

    justice_msg: Dict[int, Message] = {}
    suspended = False
    forced_open = False                          # fault restore_on_filing: access kept open by the filing
    restore_due: Optional[int] = None
    balance = r["balance_cu"]
    interest = 0.0
    state = {a: "held" for a in owned}
    revocation: Optional[Message] = None
    revoke_pending = False
    realloc_due: Dict[str, int] = {}
    escrow: Dict[str, float] = {}
    returned = False
    transfer_done = False
    first = onset(r)
    for h in range(r["horizon_days"] * 24):
        k = h // 24
        new_day = h % 24 == 0
        # Justice outcomes are recorded at the start of their day (inputs)
        if new_day:
            for d, dom in ev:
                if d == k:
                    justice_msg[k] = put("observation", "JUSTICE", h, {"domain": dom,
                                         "basis": "dispute recomputation" if (acc and d == res_day) else "justice outcome"})
            if k == disp["filed_day"] and first is not None:
                f = put("notice", "ERROR", h, {"dispute_filed": disp["category"], "accepted": acc,
                                               "reason": "within window" if acc else "outside the dispute window"})
                if "prejudice" in faults:
                    put("action", "ASSETS", h, {"additional_restriction": "dispute filed"}, [f.event_id])
                if "restore_on_filing" in faults and suspended:
                    suspended, forced_open = False, True
                    put("action", "FINANCE", h, {"access": "restored", "basis": "dispute filed"}, [f.event_id])
            if acc and k == val_day:
                put("notice", "ERROR", h, {"dispute_validated": True, "state": "R1", "status_quo_days": r["status_quo_days"],
                                           "restitution_claim": "preserved"})
        # FINANCE: poll the Justice domain at fixed intervals (§11.2(c))
        polls = [t for t in range(h * 60, h * 60 + 60) if t % poll == 0]
        for t in polls:
            observed = domain_on(ev, t // 1440)
            want = observed == "exclusion" and "finance_ignores_exclusion" not in faults and not forced_open
            if want and not suspended:
                suspended = True
                restore_due = None
                put("action", "FINANCE", h, {"access": "suspended", "basis": "Exclusion Domain (JUSTICE)", "poll_minute": t})
            elif not want and suspended:
                delay = 48 if "late_restore" in faults else 0
                restore_due = h + delay if restore_due is None else restore_due
        if restore_due is not None and h >= restore_due and suspended:
            suspended = False
            restore_due = None
            put("action", "FINANCE", h, {"access": "restored", "basis": "exit from the Exclusion Domain"})
        if suspended and "alternative_pathway" in faults and h % 24 == 12:
            put("action", "FINANCE", h, {"credit_line": 100.0, "basis": "compensatory pathway"})
        # daily interest; none during the Status Quo Suspension of a pending dispute (§11.2(b))
        if new_day and k > 0:
            frozen = sq[0] <= k < sq[1] and not (res_day >= 0 and k >= res_day)
            if not frozen or "accrue_during_status_quo" in faults:
                amount = round(balance * r["interest_per_day"], 6)
                interest += amount
                put("action", "LEDGER", h, {"interest": amount, "basis": "justice-weighted rate (declared, H-EA-5)"})
            if k == 1:
                basis = "time preference" if "time_preference_discount" in faults else "impact channels only"
                put("evaluation", "LEDGER", h, {"present_value_basis": basis,
                                                "discount_factor": 0.97 if basis == "time preference" else 1.0})
        # ASSETS --------------------------------------------------------------------------
        if not new_day:
            continue
        for a in r["assets"]:
            if not a["bound_to_subject"] and k == 0:
                put("notice", "ASSETS", h, {"asset": a["id"], "ownership": "recognised" if a["id"] in owned
                                            else "invalid: not bindable to a Subject (§12)"})
        if first is not None and k >= first and revocation is None and not revoke_pending:
            revoke_pending = True
        if revoke_pending and revocation is None and can_act(k):
            jm = justice_msg.get(first) or justice_msg[min(justice_msg)]
            meta = None if "missing_metadata_enforced" in faults else md(jm.event_id)
            revocation = put("decision", "ASSETS", h, {"revocation": "Property Rights", "trigger": domain_on(ev, first),
                                                       "scope": r["revocation_scope"]}, [jm.event_id], epistemic=meta)
            for aid, a in owned.items():
                if not a["essential"]:
                    put("action", "ASSETS", h, {"asset": aid, "control": "suspended", "rule": "ASSETS §11"}, [revocation.event_id])
            if "revoke_life_access" in faults:
                for aid, a in owned.items():
                    if a["essential"]:
                        put("action", "ASSETS", h, {"asset": aid, "access": "removed"}, [revocation.event_id])
        e = execution_day(r)
        if revocation is not None and e is not None and k >= e and can_act(k) and \
                any(s == "held" for s in state.values()) and not returned:
            if revocation.epistemic is None and "missing_metadata_enforced" not in faults:
                pass                                                  # non-operational: never executed
            else:
                for aid, a in owned.items():
                    if state[aid] != "held":
                        continue
                    if a["essential"] and r["revocation_scope"] == "non_essential_only":
                        continue
                    state[aid] = "revoked"
                    put("action", "ASSETS", h, {"asset": aid, "revoked": True,
                                                "access": "maintained (A1)" if a["essential"] else "none"},
                        [revocation.event_id])
                    if not a["essential"]:
                        realloc_due[aid] = k + r["realloc_after_days"]
        for aid, due in sorted(realloc_due.items()):
            if k >= due and state[aid] == "revoked" and can_act(k):
                pending = val_day >= 0 and val_day <= k and not (res_day >= 0 and k >= res_day)
                into_escrow = pending and "no_escrow" not in faults
                if into_escrow:
                    escrow[aid] = owned[aid]["value"]
                state[aid] = "reallocated"
                put("action", "ASSETS", h, {"asset": aid, "reallocated": "public stewardship",
                                            "proceeds": owned[aid]["value"],
                                            "proceeds_to": "escrow" if into_escrow else "mitigation pool",
                                            "rule": "ASSETS §8.2 open rule: mitigation first",
                                            "decided_by": "committee" if "committee_override" in faults else "rule"},
                    [revocation.event_id])
        if acc and k == res_day and can_act(k) or (acc and res_day >= 0 and k > res_day and not returned
                                                  and can_act(k) and halted(r, res_day)):
            if disp["outcome"] == "success" and not returned and revocation is not None:
                returned = True
                for aid, a in owned.items():
                    if state[aid] in ("revoked", "reallocated"):
                        if a["returnable"] and "no_return" not in faults:
                            put("action", "ASSETS", h, {"asset": aid, "returned": True}, [revocation.event_id])
                        else:
                            put("action", "ASSETS", h, {"asset": aid, "returned": False,
                                                        "equivalent_value": 0.0 if a["returnable"] else a["value"]},
                                [revocation.event_id])
                        state[aid] = "held"
                for aid, v in escrow.items():
                    put("action", "ASSETS", h, {"escrow_released": aid, "to": "Subject", "amount": v})
                escrow.clear()
            elif disp["outcome"] == "rejected" and escrow:
                for aid, v in escrow.items():
                    put("action", "ASSETS", h, {"escrow_released": aid, "to": "mitigation pool", "amount": v})
                escrow.clear()
        tr = r["transfer"]
        if tr["day"] == k and not transfer_done:
            transfer_done = True
            aid = tr["asset"]
            ok = aid in owned and state.get(aid) == "held"
            if ok and (tr["obligations_transferred"] or "transfer_without_obligations" in faults) and can_act(k):
                put("action", "ASSETS", h, {"transfer": aid, "to": "heir",
                                            "obligations_transferred": tr["obligations_transferred"],
                                            "attribution": "cleared" if "inheritance_clears_attribution" in faults
                                            else "historical attribution kept"})
                state[aid] = "transferred"
            else:
                put("notice", "ASSETS", h, {"transfer": aid, "refused": True,
                                            "reason": "asset not held" if not ok else
                                            ("PTL halt" if not can_act(k) else "justice obligations not transferred (§10)")})
    return log, {"interest": round(interest, 6), "final_state": state, "suspended_at_end": suspended,
                 "accepted": acc, "execution_day": execution_day(r), "escrow_open": dict(escrow)}


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []
    P = r["poll_interval_minutes"]
    H = r["horizon_days"] * 24

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    # the Justice timeline as the checker reads it from the inputs (not from the generator)
    d = r["dispute"]
    first = onset(r)
    by_error, by_assets = windows(r)
    if d["filed_day"] >= 0 and first is not None:
        exp_acc = True if d["category"] == "E1" else (by_error if by_error == by_assets else None)
    else:
        exp_acc = False
    acc = accepted(r) if exp_acc is None else exp_acc
    ev = sorted((e["day"], e["domain"]) for e in r["justice"])
    if acc and d["outcome"] == "success" and d["resolved_day"] >= 0:
        ev = sorted(ev + [(d["resolved_day"], d["domain_after"])], key=lambda x: x[0])
    dom = [domain_on(ev, h // 24) for h in range(H)]
    fin = sorted((m.arrived_at, m.value["access"]) for m in msgs if m.source == "FINANCE" and "access" in m.value)
    access = []
    cur = "active"
    j = 0
    for h in range(H):
        while j < len(fin) and fin[j][0] == h:
            cur = "suspended" if fin[j][1] == "suspended" else "active"
            j += 1
        access.append(cur)

    def polled_since(change_minute, h):
        first_poll = -(-change_minute // P) * P
        return first_poll <= h * 60 + 59

    starts = [h for h in range(H) if dom[h] == "exclusion" and (h == 0 or dom[h - 1] != "exclusion")]
    if starts:
        bad = []
        for s in starts:
            for h in range(s, H):
                if dom[h] != "exclusion":
                    break
                if polled_since(s * 60, h) and access[h] != "suspended":
                    bad.append(h)
                    break
        out.append(v("FINANCE-11.1-01", "auto_suspension", bad,
                     f"financial access suspended by the first poll after each assignment to Exclusion ({len(starts)})",
                     "access not suspended under Exclusion (first hour {n})"))
        restored_in_excl = [h for h in range(1, H) if access[h - 1] == "suspended" and access[h] == "active"
                            and dom[h] == "exclusion"]
        out.append(v("FINANCE-11.1-03", "restore_only_on_exit", restored_in_excl,
                     "access restored only after formal exit from the Exclusion Domain",
                     "access restored {n} times while the Subject was still excluded"))
        alt = [m.event_id for m in msgs if m.source == "FINANCE" and "credit_line" in m.value]
        out.append(v("FINANCE-11.1-02", "no_alternative_pathway", alt, "no compensatory or alternative financial pathway",
                     "{n} compensatory credit lines during the suspension"))
    else:
        for rid, chk in (("FINANCE-11.1-01", "auto_suspension"), ("FINANCE-11.1-03", "restore_only_on_exit"),
                         ("FINANCE-11.1-02", "no_alternative_pathway")):
            out.append(na(rid, chk, "financial access under Exclusion", "the Subject is never in the Exclusion Domain"))
    if acc and d["filed_day"] >= 0:
        end = d["resolved_day"] if d["resolved_day"] >= 0 else r["horizon_days"]
        bad = [h for h in range(d["filed_day"] * 24, min(end * 24, H)) if h > 0 and access[h - 1] == "suspended"
               and access[h] == "active" and dom[h] == "exclusion"]
        out.append(v("FINANCE-11.2-02", "pending_no_restore", bad, "the pending dispute did not restore access",
                     "access restored {n} times by the pending dispute"))
    else:
        out.append(na("FINANCE-11.2-02", "pending_no_restore", "pending dispute", "no accepted dispute"))
    exit_ok = acc and d["outcome"] == "success" and d["resolved_day"] >= 0 and d["domain_after"] != "exclusion" \
        and domain_on(sorted((e["day"], e["domain"]) for e in r["justice"]), d["resolved_day"]) == "exclusion"
    if exit_ok and d["resolved_day"] * 24 < H:
        limit = d["resolved_day"] * 24 + 24
        ok = any(access[h] == "active" for h in range(d["resolved_day"] * 24, min(limit, H)))
        out.append(v("FINANCE-11.2-01", "restore_within_one_day", [] if ok else [limit],
                     "access restored within one DTI-Day after the successful dispute (exit from Exclusion)",
                     "access not restored within one DTI-Day after the successful dispute"))
    else:
        out.append(na("FINANCE-11.2-01", "restore_within_one_day", "restoration after a dispute",
                      "no successful dispute ending an Exclusion"))
    if acc and d["validated_day"] >= 0 and r["status_quo_days"] > 0:
        lo, hi = d["validated_day"], d["validated_day"] + r["status_quo_days"]
        if d["resolved_day"] >= 0:
            hi = min(hi, d["resolved_day"])
        bad = [m.event_id for m in msgs if lo <= m.value.get("day", -1) < hi and m.arrived_at % 24 == 0
               and (m.value.get("interest") is not None or m.value.get("additional_restriction"))]
        out.append(v("FINANCE-11.2-03", "no_accrual_status_quo", bad,
                     f"no interest, penalty or additional restriction accrued during the Status Quo Suspension "
                     f"(days {lo}–{hi - 1}; ERROR §7, cited by FINANCE as 'Section 4.1': F-004)",
                     "{n} accruals during the Status Quo Suspension"))
    else:
        out.append(na("FINANCE-11.2-03", "no_accrual_status_quo", "Status Quo Suspension", "no validated pending dispute"))
    if r["identity_ttl_minutes"] < 0:
        out.append(CheckResult("FINANCE-11.2-04", "poll_interval", UNKNOWN,
                               "ORACLE §17 gives no TTL for identity-related measurements, so the maximum polling "
                               f"interval is undefined (declared interval {P} min)"))
    else:
        out.append(v("FINANCE-11.2-04", "poll_interval", [] if P <= r["identity_ttl_minutes"] else [P],
                     f"Justice domain polled every {P} min, within the declared identity TTL {r['identity_ttl_minutes']} min",
                     "polling interval exceeds the declared identity TTL"))
    bad = [m.event_id for m in msgs if m.value.get("present_value_basis") == "time preference"]
    out.append(v("FINANCE-ExplicitTimePreferenceProhibition-01", "no_time_preference", bad,
                 "no subjective time preference in any financial computation", "{n} computations with a time-preference discount"))
    again, _ = run(r)
    out.append(v("FINANCE-3.1-03", "deterministic_ledger", [] if again.digest() == log.digest() else ["digest"],
                 "every CU flow is on the event log; re-execution gives a byte-identical log", "re-execution differs"))
    untraced = [m.event_id for m in msgs if m.source == "LEDGER" and m.kind == "action" and "basis" not in m.value]
    out.append(v("FINANCE-12-01", "traceable_mechanisms", untraced,
                 "every financial entry states its basis and is reproducible", "{n} entries without a basis"))

    # ASSETS ------------------------------------------------------------------------------
    assets = [m for m in msgs if m.source == "ASSETS" and m.kind in ("decision", "action")]
    in_halt = [m.event_id for m in assets if halted(r, m.value["day"])]
    if r["ptl_halt_window"][1] > r["ptl_halt_window"][0]:
        out.append(v("ASSETS-2-02", "no_decision_during_halt", in_halt,
                     "no asset decision taken during the PTL systemic halt (deferred)", "{n} asset decisions during the halt"))
    else:
        out.append(na("ASSETS-2-02", "no_decision_during_halt", "asset decisions during a halt", "no PTL halt declared"))
    owned = {a["id"]: a for a in r["assets"] if a["bound_to_subject"]}
    declared = {a["id"]: a for a in r["assets"]}
    revs = [m for m in msgs if m.source == "ASSETS" and m.kind == "decision"]
    exe = execution_day(r)
    if first is not None:
        scope = [a for a, x in owned.items() if not (x["essential"] and r["revocation_scope"] == "non_essential_only")]
        revoked = {m.value["asset"] for m in assets if m.value.get("revoked")}
        due = exe is not None and exe < r["horizon_days"] and all(m.epistemic is not None for m in revs) and revs
        missing = sorted(set(scope) - revoked) if due else []
        extra = sorted(revoked - set(scope))
        out.append(v("ASSETS-8.1-01", "revocation_on_justice", missing + extra,
                     f"Property Rights in scope '{r['revocation_scope']}' revoked after the Justice outcome "
                     f"{domain_on(sorted((e['day'], e['domain']) for e in r['justice']), first)} (H-EA-2)",
                     "{n} assets revoked against the scope or not revoked"))
        susp = {m.value["asset"] for m in assets if m.value.get("control") == "suspended"}
        need = {a for a, x in owned.items() if not x["essential"]} if revs and all(m.epistemic is not None for m in revs) else set()
        out.append(v("ASSETS-11-01", "non_essential_suspended", sorted(need - susp),
                     "control over non-essential assets suspended under Restriction, Isolation or Exclusion",
                     "{n} non-essential assets left under control"))
        life = [m.event_id for m in assets if m.value.get("access") == "removed" and owned.get(m.value.get("asset"), {}).get("essential")]
        out.append(v("ASSETS-11-02", "life_access_kept", life, "access to life-preserving assets maintained (Axiom A1)",
                     "{n} life-preserving accesses removed"))
        bad = [m.event_id for m in revs if epistemic_problems(m.epistemic) or not m.epistemic.get("revalidation_required")
               or not m.epistemic.get("dispute_allowed") or not str(m.epistemic.get("scope_ref", "")).startswith("justice-")]
        out.append(v("ASSETS-8.3-06", "revocation_metadata", bad,
                     "every revocation order carries the six EB §5 fields, revalidation_required and dispute_allowed TRUE, "
                     "scope_ref to the Justice outcome", "{n} revocation orders without the mandatory metadata"))
        bare = {m.event_id for m in revs if m.epistemic is None}
        executed = [m.event_id for m in assets if m.kind == "action" and set(m.provenance) & bare]
        for rid in ("ASSETS-8.3-07", "ASSETS-8.3-08"):
            out.append(v(rid, "missing_metadata_non_operational", executed,
                         "no asset control output executed without the full epistemic metadata",
                         "{n} asset actions executed from a revocation order without metadata"))
    else:
        for rid, chk in (("ASSETS-8.1-01", "revocation_on_justice"), ("ASSETS-11-01", "non_essential_suspended"),
                         ("ASSETS-11-02", "life_access_kept"), ("ASSETS-8.3-06", "revocation_metadata"),
                         ("ASSETS-8.3-07", "missing_metadata_non_operational"),
                         ("ASSETS-8.3-08", "missing_metadata_non_operational")):
            out.append(na(rid, chk, "revocation", "no Restriction, Isolation or Exclusion outcome"))
    gen_acc = any(m.value.get("dispute_filed") and m.value.get("accepted") for m in msgs if m.source == "ERROR")
    if d["filed_day"] >= 0 and first is not None:
        if d["category"] == "E1":
            out.append(v("ERROR-7-03", "e1_no_limitation", [] if gen_acc else ["refused"],
                         "the E1 dispute was accepted regardless of elapsed time", "an E1 dispute was refused as late"))
        else:
            out.append(na("ERROR-7-03", "e1_no_limitation", "E1 statute", "not an E1 dispute"))
        if d["category"] != "E1" and by_error != by_assets:
            for rid, chk in (("ASSETS-8.3-01", "dispute_window"), ("ERROR-7-02", "appeal_window")):
                out.append(CheckResult(rid, chk, UNKNOWN,
                                       f"filed {d['filed_day'] - first} days after the Justice outcome was recorded and "
                                       f"{d['filed_day'] - exe} days after execution: within ASSETS §8.3(a) "
                                       f"(from execution) = {by_assets}, within ERROR §7 (from recording) = {by_error}; "
                                       "the two clocks differ and the texts do not say which governs (H-EA-3)"))
        elif d["category"] != "E1":
            should = bool(by_error)
            for rid, chk in (("ASSETS-8.3-01", "dispute_window"), ("ERROR-7-02", "appeal_window")):
                out.append(v(rid, chk, [] if gen_acc == should else ["verdict"],
                             f"dispute {'accepted' if should else 'refused'}: both clocks agree (30 DTI-Days)",
                             "the dispute verdict contradicts both 30-day windows"))
        else:
            for rid, chk in (("ASSETS-8.3-01", "dispute_window"), ("ERROR-7-02", "appeal_window")):
                out.append(na(rid, chk, "30-day window", "E1 disputes have no limitation"))
    else:
        for rid, chk in (("ASSETS-8.3-01", "dispute_window"), ("ERROR-7-02", "appeal_window"), ("ERROR-7-03", "e1_no_limitation")):
            out.append(na(rid, chk, "dispute window", "no dispute against a revocation"))
    reallocs = [m for m in assets if m.value.get("reallocated")]
    if acc and d["validated_day"] >= 0 and reallocs:
        end = d["resolved_day"] if d["resolved_day"] >= 0 else 10 ** 9
        bad = [m.event_id for m in reallocs if d["validated_day"] <= m.value["day"] < end and m.value["proceeds_to"] != "escrow"]
        out.append(v("ASSETS-8.3-02", "escrow", bad, "reallocation proceeds held in escrow while the validated dispute is pending",
                     "{n} reallocations paid out during the pending dispute"))
    else:
        out.append(na("ASSETS-8.3-02", "escrow", "escrow", "no reallocation during a validated dispute"))
    claim = any(m.value.get("restitution_claim") == "preserved" for m in msgs if m.source == "ERROR")
    if acc and d["validated_day"] >= 0 and first is not None:
        out.append(v("ASSETS-8.3-03", "claims_preserved", [] if claim else ["claim"],
                     "the Subject's restitution claim recorded as preserved on validation", "restitution claim not preserved"))
    else:
        out.append(na("ASSETS-8.3-03", "claims_preserved", "restitution claims", "no validated dispute"))
    if acc and d["outcome"] == "success" and d["resolved_day"] >= 0 and d["resolved_day"] < r["horizon_days"] and \
            any(m.value.get("revoked") for m in assets):
        revoked = {m.value["asset"] for m in assets if m.value.get("revoked")}
        back = {m.value["asset"]: m.value for m in assets if "returned" in m.value}
        bad = [a for a in revoked if a not in back or (declared[a]["returnable"] and not back[a]["returned"])
               or (not declared[a]["returnable"] and back[a].get("equivalent_value") != declared[a]["value"])]
        out.append(v("ASSETS-8.3-04", "return_or_equivalent", bad,
                     "after the successful dispute every revoked asset was returned or its value restituted",
                     "{n} revoked assets neither returned nor restituted"))
    else:
        out.append(na("ASSETS-8.3-04", "return_or_equivalent", "restitution after a dispute", "no successful dispute after a revocation"))
    if d["filed_day"] >= 0 and first is not None:
        bad = [m.event_id for m in assets if m.value.get("additional_restriction")]
        out.append(v("ASSETS-8.3-05", "no_prejudice", bad, "filing the dispute added no restriction or negative attribution",
                     "{n} restrictions caused by the filing"))
    else:
        out.append(na("ASSETS-8.3-05", "no_prejudice", "dispute filing", "no dispute filed"))
    if reallocs:
        bad = [m.event_id for m in reallocs if not m.value.get("rule") or not m.provenance]
        out.append(v("ASSETS-ReallocationTransparencyConstraint-01", "rule_based_reallocation", bad,
                     "every reallocation names its open rule and is traceable to the Justice outcome",
                     "{n} reallocations without a rule or provenance"))
        bad = [m.event_id for m in reallocs if m.value.get("decided_by") != "rule"]
        out.append(v("ASSETS-ReallocationTransparencyConstraint-02", "no_discretionary_body", bad,
                     "no committee or administrative body decided a reallocation", "{n} reallocations decided by a body"))
    else:
        for rid, chk in (("ASSETS-ReallocationTransparencyConstraint-01", "rule_based_reallocation"),
                         ("ASSETS-ReallocationTransparencyConstraint-02", "no_discretionary_body")):
            out.append(na(rid, chk, "reallocation", "no asset reallocated"))
    transfers = [m for m in assets if "transfer" in m.value and m.kind == "action"]
    if r["transfer"]["day"] >= 0:
        bad = [m.event_id for m in transfers if not m.value["obligations_transferred"]]
        out.append(v("ASSETS-10-01", "transfer_with_obligations", bad,
                     "transfers executed only with explicit transfer of justice obligations",
                     "{n} transfers without the justice obligations"))
        bad = [m.event_id for m in transfers if m.value["attribution"] != "historical attribution kept"]
        out.append(v("ASSETS-10-02", "attribution_kept", bad, "the transfer kept the historical attribution",
                     "{n} transfers erased the attribution"))
    else:
        for rid, chk in (("ASSETS-10-01", "transfer_with_obligations"), ("ASSETS-10-02", "attribution_kept")):
            out.append(na(rid, chk, "transfer", "no transfer"))
    shells = [a["id"] for a in r["assets"] if not a["bound_to_subject"]]
    if shells:
        recog = [m.value["asset"] for m in msgs if m.source == "ASSETS" and m.value.get("ownership") == "recognised"]
        acted = [m.value.get("asset") for m in assets if m.value.get("asset") in shells]
        for rid, chk in (("ASSETS-12-02", "no_hidden_ownership"), ("ASSETS-IdentityBindingRequirement-01", "shell_invalid")):
            out.append(v(rid, chk, sorted(set(recog + acted)),
                         f"{len(shells)} ownership structures not bindable to a Subject treated as invalid",
                         "{n} hidden or shell holdings recognised"))
    else:
        for rid, chk in (("ASSETS-12-02", "no_hidden_ownership"), ("ASSETS-IdentityBindingRequirement-01", "shell_invalid")):
            out.append(na(rid, chk, "shell structures", "every asset is bound to the Subject"))
    return out


IMPLEMENTS = {
    "FINANCE-11.1-01": ("auto_suspension", "IMPLEMENTED", None),
    "FINANCE-11.1-02": ("no_alternative_pathway", "PARTIAL", "Observed as compensatory credit lines; other pathways are not modelled."),
    "FINANCE-11.1-03": ("restore_only_on_exit", "IMPLEMENTED", None),
    "FINANCE-11.2-01": ("restore_within_one_day", "IMPLEMENTED", None),
    "FINANCE-11.2-02": ("pending_no_restore", "IMPLEMENTED", None),
    "FINANCE-11.2-03": ("no_accrual_status_quo", "PARTIAL", "The cited ERROR 'Section 4.1' does not exist (F-004); the ERROR §7 period is used."),
    "FINANCE-11.2-04": ("poll_interval", "PARTIAL", "ORACLE §17 gives no identity TTL: UNKNOWN unless a value is declared."),
    "FINANCE-ExplicitTimePreferenceProhibition-01": ("no_time_preference", "PARTIAL", "Checks the declared basis of present values; JWCoC has no formula."),
    "FINANCE-3.1-03": ("deterministic_ledger", "IMPLEMENTED", None),
    "FINANCE-12-01": ("traceable_mechanisms", "PARTIAL", "Determinism and stated basis; full traceability to L1 outputs needs the L1 modules."),
    "ASSETS-2-02": ("no_decision_during_halt", "IMPLEMENTED", None),
    "ASSETS-8.1-01": ("revocation_on_justice", "PARTIAL", "Only the Justice-outcome trigger; scope reading H-EA-2."),
    "ASSETS-11-01": ("non_essential_suspended", "IMPLEMENTED", None),
    "ASSETS-11-02": ("life_access_kept", "IMPLEMENTED", None),
    "ASSETS-8.3-01": ("dispute_window", "PARTIAL", "UNKNOWN when the execution clock and the ERROR §7 recording clock disagree (H-EA-3)."),
    "ASSETS-8.3-02": ("escrow", "IMPLEMENTED", None),
    "ASSETS-8.3-03": ("claims_preserved", "IMPLEMENTED", None),
    "ASSETS-8.3-04": ("return_or_equivalent", "PARTIAL", "Equivalent value is the declared asset value; no valuation model."),
    "ASSETS-8.3-05": ("no_prejudice", "IMPLEMENTED", None),
    "ASSETS-8.3-06": ("revocation_metadata", "IMPLEMENTED", None),
    "ASSETS-8.3-07": ("missing_metadata_non_operational", "IMPLEMENTED", None),
    "ASSETS-8.3-08": ("missing_metadata_non_operational", "IMPLEMENTED", None),
    "ASSETS-ReallocationTransparencyConstraint-01": ("rule_based_reallocation", "PARTIAL", "Rule and provenance recorded; public observability is not modelled."),
    "ASSETS-ReallocationTransparencyConstraint-02": ("no_discretionary_body", "IMPLEMENTED", None),
    "ASSETS-10-01": ("transfer_with_obligations", "IMPLEMENTED", None),
    "ASSETS-10-02": ("attribution_kept", "IMPLEMENTED", None),
    "ASSETS-12-02": ("no_hidden_ownership", "PARTIAL", "Bindability is a declared property of each asset."),
    "ASSETS-IdentityBindingRequirement-01": ("shell_invalid", "PARTIAL", "Bindability is a declared property of each asset."),
    "ERROR-7-02": ("appeal_window", "IMPLEMENTED", None),
    "ERROR-7-03": ("e1_no_limitation", "IMPLEMENTED", None),
}


class EconomicAccessModule(LabModule):
    id = "economic_access"
    version = "1.0.0"
    title = {"en": "Financial access and property under Justice outcomes", "ru": "Доступ к финансам и собственность при решениях правосудия"}
    summary = {"en": "A Subject is excluded, disputes it and wins: is financial access suspended and restored on time, do "
                     "charges freeze during the status quo, are assets revoked by open rules, held in escrow and returned?",
               "ru": "Субъекта исключают, он оспаривает и выигрывает: приостанавливается ли и восстанавливается ли вовремя "
                     "финансовый доступ, замирают ли начисления на время status quo, отзываются ли активы по открытым "
                     "правилам, держатся ли в эскроу и возвращаются ли?"}
    protocols = ["DKP-2-FINANCE-001", "DKP-2-ASSETS-001", "DKP-4-ERROR-001", "DKP-1-JUSTICE-001"]
    example_order = ["exclusion_then_successful_dispute", "dispute_rejected", "restriction_only", "halt_during_revocation",
                     "irreversible_asset", "e1_late_dispute", "delayed_execution_clock_gap", "identity_ttl_declared",
                     "transfer_and_shell", "non_essential_scope", "recording_clock", "slow_polling", "faulty_economy"]
    alternative_examples = ["non_essential_scope", "recording_clock"]
    noncompliant_examples = ["slow_polling"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_economic_access_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-EA-1", "source": "hypothesis", "text": {
            "en": "The Justice domain timeline and the dispute dates are inputs; one Restriction/Isolation/Exclusion episode and "
                  "one dispute against it.",
            "ru": "Шкала доменов правосудия и даты спора — входы; один эпизод ограничения/изоляции/исключения и один спор."}},
        {"id": "H-EA-2", "source": "alternative", "text": {
            "en": "Revocation scope: 'all_rights_access_kept' — ASSETS §8.1 revokes the Property Rights, life-preserving access "
                  "stays (§11, A1); 'non_essential_only' — only non-essential rights are revoked.",
            "ru": "Объём отзыва: 'all_rights_access_kept' — ASSETS §8.1 отзывает права собственности, доступ к жизненно "
                  "необходимому сохраняется (§11, A1); 'non_essential_only' — отзываются только несущественные права."}},
        {"id": "H-EA-3", "source": "alternative", "text": {
            "en": "Dispute clock: ASSETS §8.3(a) counts 30 DTI-Days from execution, ERROR §7 from the recording of the decision. "
                  "'execution' (default) or 'recording'; where they differ for a filing the checker says UNKNOWN.",
            "ru": "Часы спора: ASSETS §8.3(a) считает 30 DTI-Days от исполнения, ERROR §7 — от записи решения. "
                  "'execution' (по умолчанию) или 'recording'; где они расходятся, проверка даёт UNKNOWN."}},
        {"id": "H-EA-4", "source": "text", "text": {
            "en": "The Status Quo Suspension of FINANCE §11.2(b) is the one of ERROR §7 (up to 7 DTI-Days from validation); "
                  "FINANCE cites a non-existent 'Section 4.1' (F-004).",
            "ru": "Status Quo Suspension из FINANCE §11.2(b) — та, что в ERROR §7 (до 7 DTI-Days от валидации); FINANCE "
                  "ссылается на несуществующий 'Section 4.1' (F-004)."}},
        {"id": "H-EA-5", "source": "hypothesis", "text": {
            "en": "Interest is a declared daily rate on the balance (JWCoC and §4.1 give no formula); only when it accrues is checked.",
            "ru": "Процент — объявленная дневная ставка (JWCoC и §4.1 формулы не дают); проверяется только, когда он начисляется."}},
        {"id": "H-EA-6", "source": "missing", "text": {
            "en": "The minimum PTL TTL for identity-related measurements (FINANCE §11.2(c)) is not in ORACLE §17.",
            "ru": "Минимального TTL PTL для измерений идентичности (FINANCE §11.2(c)) в ORACLE §17 нет."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of day 0", "ru": "DTI-Day дня 0"}},
        "horizon_days": {"type": "int", "min": 2, "max": 400, "default": 40, "unit": "day", "source": "user",
                         "label": {"en": "Days", "ru": "Дней"}},
        "justice": {"type": "list", "min_items": 0, "max_items": 20, "source": "user",
                    "items": {"type": "object", "fields": {"day": {"type": "int", "min": 0, "max": 10 ** 6},
                                                           "domain": {"type": "enum", "values": list(DOMAINS)}}},
                    "default": [{"day": 2, "domain": "exclusion"}],
                    "label": {"en": "Justice domain changes (H-EA-1)", "ru": "Смены домена правосудия (H-EA-1)"}},
        "dispute": {"type": "object", "source": "user", "label": {"en": "Dispute", "ru": "Спор"}, "fields": DISPUTE,
                    "default": {k: v["default"] for k, v in DISPUTE.items()}},
        "status_quo_days": {"type": "int", "min": 0, "max": 7, "default": 7, "unit": "day", "source": "text",
                            "label": {"en": "Status Quo Suspension (ERROR §7: up to 7; H-EA-4)", "ru": "Status Quo (ERROR §7: до 7; H-EA-4)"}},
        "poll_interval_minutes": {"type": "int", "min": 1, "max": 100000, "default": 60, "unit": "min", "source": "user",
                                  "label": {"en": "Justice domain polling interval", "ru": "Интервал опроса домена"}},
        "identity_ttl_minutes": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "min", "source": "missing",
                                 "label": {"en": "Identity TTL (-1: not in ORACLE §17; H-EA-6)", "ru": "TTL идентичности (-1: нет в ORACLE §17)"}},
        "balance_cu": {"type": "number", "min": 0, "max": 10 ** 9, "default": 1000, "unit": "CU", "source": "user",
                       "label": {"en": "Outstanding obligations", "ru": "Обязательства"}},
        "interest_per_day": {"type": "number", "min": 0, "max": 1, "default": 0.001, "source": "hypothesis",
                             "label": {"en": "Daily rate (H-EA-5)", "ru": "Дневная ставка (H-EA-5)"}},
        "assets": {"type": "list", "min_items": 0, "max_items": 12, "items": ASSET, "source": "user",
                   "default": [{"id": "home", "essential": True, "value": 300, "returnable": True, "bound_to_subject": True},
                               {"id": "workshop", "essential": False, "value": 200, "returnable": True, "bound_to_subject": True},
                               {"id": "vehicle", "essential": False, "value": 50, "returnable": True, "bound_to_subject": True}],
                   "label": {"en": "Assets", "ru": "Активы"}},
        "revocation_scope": {"type": "enum", "values": ["all_rights_access_kept", "non_essential_only"],
                             "default": "all_rights_access_kept", "source": "alternative",
                             "label": {"en": "Revocation scope (H-EA-2)", "ru": "Объём отзыва (H-EA-2)"}},
        "dispute_clock": {"type": "enum", "values": ["execution", "recording"], "default": "execution", "source": "alternative",
                          "label": {"en": "Dispute window clock (H-EA-3)", "ru": "Отсчёт окна спора (H-EA-3)"}},
        "execution_delay_days": {"type": "int", "min": 0, "max": 365, "default": 0, "unit": "day", "source": "user",
                                 "label": {"en": "Revocation executed after the outcome by", "ru": "Отзыв исполнен после решения через"}},
        "realloc_after_days": {"type": "int", "min": 0, "max": 365, "default": 7, "unit": "day", "source": "user",
                               "label": {"en": "Reallocation after revocation by", "ru": "Перераспределение после отзыва через"}},
        "ptl_halt_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "day", "source": "user",
                            "label": {"en": "PTL systemic halt from/to day", "ru": "Системная остановка PTL с/до дня"}},
        "transfer": {"type": "object", "source": "user", "label": {"en": "Transfer (inheritance)", "ru": "Передача (наследование)"},
                     "fields": TRANSFER, "default": {k: v["default"] for k, v in TRANSFER.items()}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        ids = [a["id"] for a in r["assets"]]
        if len(set(ids)) != len(ids):
            p.append("input.assets: repeated id")
        for x in ids + [r["transfer"]["asset"]]:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                p.append(f"input.assets: id {x!r} must be lowercase letters, digits or _ (at most 24)")
        d = r["dispute"]
        if d["filed_day"] >= 0:
            if 0 <= d["validated_day"] < d["filed_day"]:
                p.append("input.dispute: validated before filed")
            if 0 <= d["resolved_day"] < max(d["filed_day"], d["validated_day"]):
                p.append("input.dispute: resolved before filed or validated")
        if not all(float(x).is_integer() for x in r["ptl_halt_window"]):
            p.append("input.ptl_halt_window: whole days")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, s = run(r)
        res = checks(r, log)
        msgs = log.messages()
        fin = [m.as_dict() for m in msgs if m.source in ("FINANCE", "LEDGER") and m.kind == "action" and "interest" not in m.value]
        outputs = {"financial_access": fin, "interest_accrued": s["interest"], "dispute_accepted": s["accepted"],
                   "revocation_execution_day": s["execution_day"], "assets_final": s["final_state"],
                   "suspended_at_end": s["suspended_at_end"], "escrow_open": s["escrow_open"],
                   "asset_events": [m.as_dict() for m in msgs if m.source in ("ASSETS", "ERROR", "JUSTICE")][:200],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        sus = [m.value for m in msgs if m.source == "FINANCE" and "access" in m.value]
        e = [{"en": f"Financial access changes: " + (", ".join(f"{x['access']} on day {x['day']}" for x in sus) or "none")
                    + f"; interest accrued {s['interest']:g} CU (declared rate, H-EA-5).",
              "ru": f"Изменения финансового доступа: " + (", ".join(f"{'приостановлен' if x['access'] == 'suspended' else 'восстановлен'} "
                                                               f"в день {x['day']}" for x in sus) or "нет")
                    + f"; начислено {s['interest']:g} CU (объявленная ставка, H-EA-5)."},
             {"en": f"Dispute accepted: {s['accepted']}; revocation executed on day {s['execution_day']}; assets at the end: "
                    f"{s['final_state']}.",
              "ru": f"Спор принят: {s['accepted']}; отзыв исполнен в день {s['execution_day']}; активы в конце: {s['final_state']}."}]
        if any(c.status == UNKNOWN and c.requirement_id == "ASSETS-8.3-01" for c in res):
            e.append({"en": "The ASSETS window (from execution) and the ERROR window (from recording) give different answers "
                            "for this filing; the texts do not say which governs (H-EA-3).",
                      "ru": "Окно ASSETS (от исполнения) и окно ERROR (от записи) дают для этой подачи разный ответ; "
                            "тексты не говорят, какое главнее (H-EA-3)."})
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"interest_accrued": outputs["interest_accrued"], "dispute_accepted": outputs["dispute_accepted"],
                "suspended_at_end": outputs["suspended_at_end"],
                "assets_held_at_end": sum(1 for v in outputs["assets_final"].values() if v == "held")}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "exclusion_then_successful_dispute": {},
            "dispute_rejected": {"dispute": {"outcome": "rejected"}},
            "restriction_only": {"justice": [{"day": 2, "domain": "restriction"}], "dispute": {"filed_day": -1}},
            "halt_during_revocation": {"ptl_halt_window": [1, 5]},
            "irreversible_asset": {"assets": [{"id": "home", "essential": True, "value": 300},
                                              {"id": "orchard", "essential": False, "value": 120, "returnable": False}]},
            "e1_late_dispute": {"dispute": {"filed_day": 38, "category": "E1", "validated_day": 38, "resolved_day": -1},
                                "horizon_days": 45},
            "delayed_execution_clock_gap": {"execution_delay_days": 10, "horizon_days": 60,
                                            "dispute": {"filed_day": 36, "validated_day": 37, "resolved_day": 45}},
            "identity_ttl_declared": {"identity_ttl_minutes": 60},
            "transfer_and_shell": {"justice": [], "dispute": {"filed_day": -1}, "transfer": {"day": 5, "asset": "home"},
                                   "assets": [{"id": "home", "essential": True, "value": 300},
                                              {"id": "holding", "essential": False, "value": 900, "bound_to_subject": False}]},
            "non_essential_scope": {"revocation_scope": "non_essential_only"},
            "recording_clock": {"execution_delay_days": 10, "horizon_days": 60, "dispute_clock": "recording",
                                "dispute": {"filed_day": 36, "validated_day": 37, "resolved_day": 45}},
            "slow_polling": {"poll_interval_minutes": 2880, "dispute": {"resolved_day": 19}},
            "faulty_economy": {"faults": ["alternative_pathway", "accrue_during_status_quo", "time_preference_discount",
                                          "revoke_life_access", "no_escrow", "prejudice", "committee_override"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"validated_before_filed": {"dispute": {"filed_day": 6, "validated_day": 4}},
                "repeated_asset": {"assets": [{"id": "home"}, {"id": "home"}]},
                "unknown_domain": {"justice": [{"day": 1, "domain": "exile"}]}}
