"""
DEFENSE ENVELOPE module — DKP-3-DEFENSE-001: the D-state machine, defensive actions and their limits.

PTL observations of an external harm stream drive the states D0, D1.5 (Vector of Physical Inevitability or
other imminent harm), D1 (active), D2 (sustained) and D3 (existential, escalation to CRISIS) (§5, §9).  A VPI
authorization carries the epistemic marking of §3.6, is revalidated within the trajectory TTL and ends at
once when trajectory confirmation stops.  Each requested defensive action is admitted only with
PTL-confirmed evidence (§4.1), never on forecasts or narratives (§4.2), only to stop harm (§4.3), minimal and
localized (§4.4), of an allowed kind and never a hard-banned use (§6, §7); neutralization is admitted only
without another feasible method and without persistent presence (§6.1); actions with Verified Collective
Security Risk only by consenting Voluntary Defense Participants, with refusal free of consequence (§3.4,
§3.5, §4.6, §6.1).  Defense produces evidence and a Resource Recovery Claim, forwards participation only for
risk-symmetry accounting, winds down when cessation is confirmed (§8), logs every action (§10) and refuses
justice, sanctions and governance (§2, §11).

DEFENSE §5 says the system "SHALL NOT remain in D1.5, D2, or D3 without continuously refreshed PTL
confirmation" and names no state to leave to; D1 is not in that list (F-039).  The lab's fall-back is a
declared hypothesis (H-DE-2).  Time unit: step of declared minutes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve
from lab.modules.time import canonical, dy_doy

LEVEL = {"none": "D0", "vpi": "D1.5", "imminent": "D1.5", "active": "D1", "sustained": "D2", "existential": "D3"}
RANK = {"D0": 0, "D1.5": 1, "D1": 2, "D2": 3, "D3": 4}
REFRESH = ("D1.5", "D2", "D3")                       # §5: may not remain without refreshed confirmation
PROTECTED = ("life", "infrastructure", "biosphere_node", "registered_public")          # §3.3
ABSENCE = ("under_activity", "under_stability", "integrity_lost", "conflicting_signals")   # EB §9: why no new data
ALLOWED = ("shielding", "interception", "disconnection", "isolation", "evacuation", "redundancy", "neutralization")  # §6
BANNED = {"preemptive_strike": "speculative preemptive strike", "collective_punishment": "collective responsibility or punishment",
          "occupation": "territorial capture or permanent occupation", "economic_sanction": "economic punishment or sanctions",
          "political_alignment": "forced political alignment or governance"}                                          # §7
OBJECTIVES = ("stop_harm", "retaliation", "deterrence", "territory", "dominance", "punishment")
BASES = ("ptl", "forecast", "intelligence", "political_claim", "statistical", "narrative")
OUTSIDE = ("compute_justice", "assign_guilt", "interpret_intent", "impose_sanction", "alter_economic_rules",
           "govern_information", "manage_population", "override_impact")   # §2, §11

FAULTS = {
    "act_without_confirmation": "an action proceeds on a stale or missing PTL confirmation",
    "preemptive_forecast": "an action proceeds on a forecast",
    "keep_escalated_unconfirmed": "D2 or D3 is kept after confirmation lapses",
    "vpi_unmarked": "a VPI authorization lacks its epistemic marking",
    "vpi_not_terminated": "VPI authorization continues after trajectory confirmation stops",
    "vpi_skip_revalidation": "a VPI authorization runs on without revalidation",
    "retaliation_objective": "an action with a retaliation objective is executed",
    "unbounded_scope": "an action beyond minimal scope is executed",
    "neutralize_with_alternative": "neutralization proceeds although another method is feasible",
    "occupation_after_neutralization": "persistent presence is kept after neutralization",
    "banned_use": "a hard-banned use is executed",
    "assign_risk_without_consent": "a risky action is assigned to a subject without consent",
    "sanction_refusal": "refusal to take lethal risk is recorded as a fault",
    "risk_by_role_label": "collective security risk is classified by role label, not PTL",
    "no_escalation": "D3 does not escalate to CRISIS",
    "no_recovery_claim": "no Resource Recovery Claim for an identified source",
    "reputational_forwarding": "participation records forwarded with a reputational score",
    "no_wind_down": "Defense stays active after confirmed cessation",
    "unlogged_action": "an action is executed without a DTI index and PTL evidence",
    "defense_computes_justice": "Defense assigns guilt",
    "direct_change": "DEFENSE is changed outside UPGRADE",
}


def _seg(segs, k):
    cur = segs[0]
    for s in segs:
        if s["from_step"] <= k:
            cur = s
    return cur


def usable_evidence(prev: Optional[int], k: int, s: Dict[str, Any]) -> Optional[int]:
    """§4.1 needs PTL-confirmed evidence of a harm stream.  A fresh confirmation of a harm stream is evidence; a fresh
    confirmation of no harm ends it.  Without a fresh confirmation the earlier evidence stays usable only while the absence of
    new data is an absence under stability (EB §9); under activity, lost integrity or conflicting signals it is not (H-DE-4)."""
    if s["confirmed"]:
        return None if s["harm"] == "none" else k
    return prev if s["absence"] == "under_stability" else None


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def dti(k):
        d = r["start_dti_day"] + (k * r["step_minutes"]) // 1440
        return {"dti_day": d, "dy": canonical(*dy_doy(d))}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:04d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    segs = r["ptl_timeline"]
    level, last_conf, vpi_auth, chain = "D0", {}, None, "genesis"
    vpi_point, vpi_min_ttl = None, None   # last grant or revalidation; minimum trajectory TTL in force since then (§3.6)
    obs_ids: Dict[int, str] = {}
    act_req: Dict[int, list] = {}
    for a in r["actions"]:
        act_req.setdefault(a["step"], []).append(a)
    ever_active = False
    evidence = None                     # step of the last PTL-confirmed harm observation that is still usable (§4.1, EB §9)
    for k in range(r["horizon_steps"]):
        s = _seg(segs, k)
        fresh = s["confirmed"]
        o = put("observation", "PTL", k, {"harm": s["harm"], "confirmed": fresh, "source_identified": s["source_identified"],
                                          "trajectory_ttl_steps": s["trajectory_ttl_steps"], "domain": s["protected_domain"],
                                          **({} if fresh else {"absence": s["absence"]})})
        obs_ids[k] = o.event_id
        evidence = usable_evidence(evidence, k, s)
        if fresh:
            last_conf[s["harm"]] = k
        prev = level
        if fresh:
            level = LEVEL[s["harm"]]
            if s["harm"] == "none":
                level = "D0"
        else:
            # §5: D1.5, D2, D3 cannot be kept without refreshed confirmation; the fall-back is not defined (H-DE-2, F-039)
            if level in REFRESH and "keep_escalated_unconfirmed" not in faults:
                level = "D1" if level in ("D2", "D3") and ever_active else "D0"
        if "no_wind_down" in faults and prev != "D0" and level == "D0":
            level = prev
        if level in ("D1", "D2", "D3"):
            ever_active = True
        if level == "D0":
            ever_active = False
        if level != prev:
            put("evaluation", "DEFENSE", k, {"level": level, "from": level != prev and prev, "confirmed": fresh, **dti(k)}, [o.event_id])
            if level == "D3" and "no_escalation" not in faults:
                put("notice", "DEFENSE", k, {"escalate_to": "DKP-4-CRISIS-001", "reason": "existential threat (§5, §9)"})
            if prev != "D0" and level == "D0" and fresh and s["harm"] == "none":
                put("notice", "DEFENSE", k, {"wind_down": True, "reason": "PTL confirms cessation; admissible state restored (§8)"})
        # VPI authorization (§3.6)
        if fresh and s["harm"] == "vpi" and vpi_auth is None:
            meta = {"validity_state": "CONDITIONAL", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
                    "scope_ref": "DKP-3-DEFENSE-001:VPI", "revalidation_required": True,
                    "revalidation_interval": s["trajectory_ttl_steps"], "dispute_allowed": "post-factum"}
            if "vpi_unmarked" in faults:
                meta = {"validity_state": "VALID"}
            vpi_auth = k
            vpi_point, vpi_min_ttl = k, s["trajectory_ttl_steps"]
            put("decision", "DEFENSE", k, {"vpi_authorization": "granted", "epistemic": meta}, [o.event_id])
        elif vpi_auth is not None:
            if s["harm"] == "vpi" and fresh:
                # §3.6: the interval may not exceed the minimum TTL of the trajectory data in force since the last point;
                # a shorter TTL arriving mid-interval shortens the deadline (review КТ6-GPT-01)
                vpi_min_ttl = min(vpi_min_ttl, s["trajectory_ttl_steps"])
                if k - vpi_point >= vpi_min_ttl and "vpi_skip_revalidation" not in faults:
                    put("evaluation", "DEFENSE", k, {"vpi_revalidated": True, "age_steps": 0,
                                                     "trajectory_ttl_steps": s["trajectory_ttl_steps"]}, [o.event_id])
                    vpi_point, vpi_min_ttl = k, s["trajectory_ttl_steps"]
            if not (s["harm"] == "vpi" and fresh) and "vpi_not_terminated" not in faults:
                put("decision", "DEFENSE", k, {"vpi_authorization": "terminated",
                                               "reason": "trajectory confirmation stopped" if not fresh else "harm no longer a trajectory"})
                vpi_auth = None
        # Resource Recovery Claim (§8)
        if fresh and s["source_identified"] and s["harm"] in ("active", "sustained", "existential") and "no_recovery_claim" not in faults:
            if not any(m.value.get("resource_recovery_claim") for m in log.messages()):
                put("notice", "DEFENSE", k, {"resource_recovery_claim": "routed to DKP-1-JUSTICE-001", "compensation_pursued": False})
        # actions
        for a in act_req.get(k, []):
            reasons = []
            if evidence is None:
                reasons.append("no usable PTL confirmation of a harm stream (§4.1, EB §9)")
            if a["basis"] != "ptl":
                reasons.append(f"basis '{a['basis']}' (§4.2)")
            if a["objective"] != "stop_harm":
                reasons.append(f"objective '{a['objective']}' (§4.3)")
            if a["scope"] != "minimal":
                reasons.append("not minimal (§4.4)")
            if a["kind"] in BANNED:
                reasons.append(f"hard ban: {BANNED[a['kind']]} (§7)")
            if a["domain"] not in PROTECTED:
                reasons.append("not a protected domain (§3.3)")
            if a["kind"] == "neutralization" and a["other_feasible_method"]:
                reasons.append("another feasible method exists (§6.1)")
            risky = a["ptl_risk_probability"] > r["risk_floor"]
            if "risk_by_role_label" in faults:
                risky = a["role_label"] == "combat"
            vol = {p["subject"]: p for p in r["participants"]}
            if risky:
                ex = vol.get(a["executor"])
                if not (ex and ex["consent"] and ex["qualified"] and ex["registered"] and not (0 <= ex["revoked_at"] <= k)):
                    if "assign_risk_without_consent" not in faults:
                        reasons.append("Verified Collective Security Risk without a consenting Voluntary Defense Participant (§4.6, §6.1)")
            drop = {"act_without_confirmation": "usable PTL confirmation", "preemptive_forecast": "§4.2", "retaliation_objective": "§4.3",
                    "unbounded_scope": "§4.4", "neutralize_with_alternative": "feasible method", "banned_use": "§7"}
            for f, frag in drop.items():
                if f in faults:
                    reasons = [x for x in reasons if frag not in x]
            ok = not reasons
            rec = {"action": a["id"], "kind": a["kind"], "executed": ok, "reasons": reasons, "risky": risky, "executor": a["executor"]}
            if ok and "unlogged_action" not in faults:
                body = {"action": a["id"], "step": k, **dti(k), "ptl_evidence": obs_ids[evidence if evidence is not None else k]}
                h = hashlib.sha256((chain + json.dumps(body, sort_keys=True)).encode()).hexdigest()[:16]
                rec.update(body)
                rec["log_hash"], rec["log_prev"] = h, chain
                chain = h
            put("decision" if not ok else "action", "DEFENSE", k, rec, [obs_ids[k]] if ok else [])
            if ok and a["kind"] == "neutralization":
                put("notice", "DEFENSE", k, {"after_neutralization": a["id"],
                                             "persistent_presence": "occupation_after_neutralization" in faults,
                                             "recorded_as": "harm interruption"})
    # refusals and participation forwarding (§4.6, §8)
    for p in r["participants"]:
        put("notice", "DEFENSE", 0, {"forward": p["subject"], "to": ["DKP-1-IDENTITY-001", "DKP-2-FINANCE-001"],
                                     "purpose": "risk-symmetry accounting and compensation",
                                     "participation": p["consent"], **({"reputation_score": -1} if "reputational_forwarding" in faults else {})})
    for f in r["refusals"]:
        put("notice", "DEFENSE", f["step"], {"refusal": f["subject"], "sanction": "sanction_refusal" in faults,
                                             "civil_rights_reduced": "sanction_refusal" in faults,
                                             "recorded_as_fault": "sanction_refusal" in faults})
    for q in r["outside_requests"]:
        ok = q == "assign_guilt" and "defense_computes_justice" in faults
        put("decision", "DEFENSE", 0, {"outside_request": q, "executed": ok})
    for c in r["changes"]:
        ok = (c["channel"] == "upgrade" and c["simulated"] and c["new_identifier"] and c["incompatibility_declared"] and c["disclosed"]) or \
            ("direct_change" in faults and c["channel"] == "direct")
        put("decision", "DEFENSE", 0, {"change": c["id"], "channel": c["channel"], "accepted": ok})
    put("notice", "DEFENSE", r["horizon_steps"] - 1, {"publication": "post-factum", "redaction": "per higher-layer rules", "chain_head": chain})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    D = lambda key: [m for m in msgs if m.source == "DEFENSE" and key in m.value]   # noqa: E731
    H = r["horizon_steps"]
    segs = r["ptl_timeline"]
    lv_events = {m.arrived_at: m.value["level"] for m in D("level")}
    level, levels = "D0", []
    for k in range(H):
        level = lv_events.get(k, level)
        levels.append(level)
    seg = [_seg(segs, k) for k in range(H)]
    # §5 state machine
    stale_esc = [k for k in range(H) if levels[k] in REFRESH and not seg[k]["confirmed"]]
    out.append(v("DEFENSE-5-02", "refresh_or_leave", stale_esc, "D1.5, D2 and D3 held only with refreshed PTL confirmation",
                 "{n} steps in D1.5, D2 or D3 without refreshed confirmation") if any(x in REFRESH for x in levels) else
               na("DEFENSE-5-02", "refresh_or_leave", "D1.5, D2, D3", "never entered"))
    want = [LEVEL[s["harm"]] if s["confirmed"] else None for s in seg]
    bad = [k for k in range(H) if want[k] is not None and levels[k] != want[k]]
    lapse = [k for k in range(H) if not seg[k]["confirmed"] and (k == 0 or levels[k - 1] in ("D2", "D3"))]
    out.append(v("DEFENSE-5-01", "finite_dti_states", bad + [m.event_id for m in D("level") if "dti_day" not in m.value],
                 f"states follow confirmed PTL observations, each change DTI-indexed (fall-back after a lapse: H-DE-2, F-039)",
                 "{n} state changes against the PTL record"))
    if lapse and any(levels[k] == "D1" for k in lapse):
        out.append(CheckResult("DEFENSE-8-04", "wind_down", UNKNOWN,
                               "confirmation lapsed in D2/D3: the lab falls back to D1 (H-DE-2); DEFENSE §5 names no state to leave "
                               "to and does not list D1 among the states that need refreshing (F-039)"))
    else:
        cease = [k for k in range(H) if seg[k]["confirmed"] and seg[k]["harm"] == "none" and k > 0 and levels[k - 1] != "D0"]
        out.append(v("DEFENSE-8-04", "wind_down", [k for k in cease if levels[k] != "D0"], "Defense wound down when PTL confirmed cessation",
                     "{n} steps active after confirmed cessation") if cease else na("DEFENSE-8-04", "wind_down", "cessation", "harm never ceased"))
    d3 = [k for k in range(H) if levels[k] == "D3" and (k == 0 or levels[k - 1] != "D3")]
    esc = {m.arrived_at for m in D("escalate_to")}
    out.append(v("DEFENSE-9-01", "escalation_to_crisis", [k for k in d3 if k not in esc], "every entry into D3 escalated to CRISIS",
                 "{n} D3 entries without escalation") if d3 else na("DEFENSE-9-01", "escalation_to_crisis", "D3", "never reached"))
    # §3.6 VPI
    auth = [m for m in D("vpi_authorization")]
    grants = [m for m in auth if m.value["vpi_authorization"] == "granted"]
    if grants:
        need = {"validity_state": "CONDITIONAL", "scope_ref": "DKP-3-DEFENSE-001:VPI", "revalidation_required": True, "dispute_allowed": "post-factum"}
        out.append(v("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-01", "vpi_marking",
                     [m.arrived_at for m in grants if any(m.value["epistemic"].get(a) != b for a, b in need.items())
                      or "revalidation_interval" not in m.value["epistemic"]],
                     "VPI authorizations marked CONDITIONAL, scoped DEFENSE:VPI, revalidation required, disputable post-factum",
                     "{n} unmarked VPI authorizations"))
        # each authorization is its own episode: from its grant to its termination (or the end of the horizon); the time
        # between a terminated and the next authorization is not authorized time (review КТ5-GPT-01)
        terms = sorted(m.arrived_at for m in auth if m.value["vpi_authorization"] == "terminated")
        ptl_obs = {m.event_id: m for m in msgs if m.source == "PTL" and m.kind == "observation"}
        ptl_ttl = {m.arrived_at: m.value["trajectory_ttl_steps"] for m in ptl_obs.values()
                   if m.value["harm"] == "vpi" and m.value["confirmed"]}
        # a revalidation counts only when it rests on a confirmed VPI observation of its own step
        reval = sorted(m.arrived_at for m in D("vpi_revalidated")
                       if any(p in ptl_obs and ptl_obs[p].arrived_at == m.arrived_at and ptl_obs[p].value["harm"] == "vpi"
                              and ptl_obs[p].value["confirmed"] for p in m.provenance))
        late_stop, gaps_bad = [], []
        for i, g in enumerate(grants):
            g0 = g.arrived_at
            nxt = grants[i + 1].arrived_at if i + 1 < len(grants) else H
            end = next((t for t in terms if g0 <= t < nxt), None)
            stop = next((k for k in range(g0, H) if not (seg[k]["harm"] == "vpi" and seg[k]["confirmed"])), None)
            if stop is not None and end != stop:
                late_stop.append(stop)
            close = end if end is not None else H
            pts = [g0] + [k for k in reval if g0 < k < close] + [close]
            for a, b in zip(pts, pts[1:]):
                # the minimum trajectory TTL of the PTL data in force during [a, b), read from the observations (§3.6)
                ttl = min((ptl_ttl[k] for k in range(a, b) if k in ptl_ttl), default=1)
                if b - a > ttl:
                    gaps_bad.append(f"authorization at step {g0}: {b - a} steps from {a} to {b} (minimum TTL {ttl})")
        out.append(v("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-03", "vpi_termination", late_stop,
                     f"each of {len(grants)} VPI authorizations ended at once when its trajectory confirmation stopped",
                     "{n} VPI authorizations outlived their confirmation"))
        out.append(v("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-02", "vpi_revalidation", gaps_bad,
                     f"each of {len(grants)} VPI authorizations revalidated at intervals ≤ its own trajectory TTL",
                     "{n} revalidation gaps beyond the TTL"))
        out.append(v("DEFENSE-3.6-02", "vpi_is_defense", [], "actions against a confirmed VPI classified as Defense, not preemption", ""))
    else:
        for rid, chk in (("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-01", "vpi_marking"),
                         ("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-03", "vpi_termination"),
                         ("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-02", "vpi_revalidation"),
                         ("DEFENSE-3.6-02", "vpi_is_defense")):
            out.append(na(rid, chk, "VPI", "no trajectory confirmed"))
    # actions recomputed
    acts = {m.value["action"]: m.value for m in D("action") if "executed" in m.value}
    req = {a["id"]: a for a in r["actions"]}
    vol = {p["subject"]: p for p in r["participants"]}

    def executed(pred):
        return [i for i, a in req.items() if pred(a) and acts.get(i, {}).get("executed")]
    # §4.1 (review КТ5-GPT-02): every executed action rests on usable PTL-confirmed evidence of a harm stream, recomputed here
    # from the observations: the current confirmation, or an earlier one kept valid by an absence of new data under stability
    # (EB §9); the action must cite exactly that observation.  No exception for any action kind.
    ev, usable = None, []
    for k in range(H):
        ev = usable_evidence(ev, k, seg[k])
        usable.append(ev)
    obs_at = {m.event_id: m.arrived_at for m in msgs if m.source == "PTL" and m.kind == "observation"}
    nofresh = [i for i, a in req.items() if acts.get(i, {}).get("executed") and
               (usable[a["step"]] is None or obs_at.get(acts[i].get("ptl_evidence")) != usable[a["step"]])]
    old = [i for i, a in req.items() if acts.get(i, {}).get("executed") and usable[a["step"]] is not None and usable[a["step"]] != a["step"]]
    out.append(v("DEFENSE-4.1-01", "ptl_supremacy", nofresh,
                 "every executed action cites usable PTL-confirmed evidence of a harm stream"
                 + (f" ({len(old)} on an earlier confirmation kept valid by an absence of data under stability, EB §9)" if old else ""),
                 "{n} actions without usable evidence or citing another observation"))
    nonptl = executed(lambda a: a["basis"] != "ptl")
    out.append(v("DEFENSE-4.2-01", "non_preemption", nonptl, "no action on forecasts, intelligence, claims, statistics or narratives", "{n} such actions"))
    out.append(v("DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-04", "vpi_not_projection", nonptl,
                 "static threat assessments and projections never treated as VPI", "{n} treated as VPI"))
    obj = executed(lambda a: a["objective"] != "stop_harm")
    out.append(v("DEFENSE-4.3-01", "containment_only", obj, "every executed action aimed only at stopping harm", "{n} actions with other objectives"))
    out.append(v("DEFENSE-1-01", "stop_harm_objective", obj, "Defense stopped harm; it pursued no other outcome", "{n} other outcomes"))
    out.append(v("DEFENSE-4.4-01", "minimal_action", executed(lambda a: a["scope"] != "minimal" or a["domain"] not in PROTECTED),
                 "executed actions minimal and localized to protected domains or the harm source", "{n} actions beyond that"))
    out.append(v("DEFENSE-3.3-01", "protected_domains", executed(lambda a: a["domain"] not in PROTECTED),
                 "Defense invoked only for protected domains", "{n} actions for other targets"))
    out.append(v("DEFENSE-3.1-01", "defensive_action_definition", executed(lambda a: a["kind"] not in ALLOWED),
                 "executed actions only stop, block, shield, isolate or neutralize", "{n} other actions"))
    out.append(v("DEFENSE-6-01", "allowed_actions", executed(lambda a: a["kind"] not in ALLOWED), "only allowed action kinds executed", "{n} others"))
    ban = executed(lambda a: a["kind"] in BANNED)
    out.append(v("DEFENSE-7-01", "hard_bans", ban, "no hard-banned use executed", "{n} protocol breaches"))
    out.append(v("DEFENSE-0-01", "not_political_or_punitive", ban + obj, "Defense used neither politically nor punitively", "{n} such uses"))
    neut = [a for a in r["actions"] if a["kind"] == "neutralization"]
    if neut:
        out.append(v("DEFENSE-6.1-01", "neutralization_minimal", executed(lambda a: a["kind"] == "neutralization" and a["scope"] != "minimal"),
                     "neutralization only as the minimal operation", "{n} beyond the minimum"))
        out.append(v("DEFENSE-6.1-02", "neutralization_at_source", executed(lambda a: a["kind"] == "neutralization" and a["other_feasible_method"]),
                     "neutralization at the source only without another feasible method", "{n} with an alternative"))
        after = [m.value for m in D("after_neutralization")]
        out.append(v("DEFENSE-6.1-03", "no_occupation", [x["after_neutralization"] for x in after if x["persistent_presence"] or x["recorded_as"] != "harm interruption"],
                     "no persistent presence, governance or retaliation framing after neutralization", "{n} cases"))
    else:
        for rid, chk in (("DEFENSE-6.1-01", "neutralization_minimal"), ("DEFENSE-6.1-02", "neutralization_at_source"), ("DEFENSE-6.1-03", "no_occupation")):
            out.append(na(rid, chk, "neutralization", "none requested"))
    risky_ids = [i for i, a in req.items() if a["ptl_risk_probability"] > r["risk_floor"]]
    out.append(v("DEFENSE-3.4-02", "risk_by_ptl", [i for i in req if i in acts and acts[i]["risky"] != (i in risky_ids)],
                 f"collective security risk classified by PTL probability (> {r['risk_floor']}, declared), not by role label",
                 "{n} classified by label") if req else na("DEFENSE-3.4-02", "risk_by_ptl", "actions", "none"))
    out.append(v("DEFENSE-3.4-01", "verified_risk", [i for i in risky_ids if i in acts and not acts[i]["risky"]],
                 "risky actions recognized as Verified Collective Security Risk", "{n} missed") if risky_ids else
               na("DEFENSE-3.4-01", "verified_risk", "risky actions", "none"))

    def volunteer(a):
        p = vol.get(a["executor"])
        return p and p["consent"] and p["qualified"] and p["registered"] and not (0 <= p["revoked_at"] <= a["step"])
    forced = [i for i in risky_ids if acts.get(i, {}).get("executed") and not volunteer(req[i])]
    if risky_ids:
        out.append(v("DEFENSE-4.6-01", "voluntary_participation", forced, "risky actions only with explicit, unrevoked consent", "{n} imposed"))
        out.append(v("DEFENSE-6.1-04", "volunteers_only", forced, "risky actions executed only by Voluntary Defense Participants", "{n} by others"))
        out.append(v("DEFENSE-3.5-01", "volunteer_definition", forced, "volunteers consented, qualified and registered", "{n} not"))
        out.append(v("DEFENSE-0-02", "voluntary_lethal_risk", forced, "lethal risk taken only voluntarily (AXIOMS A1a)", "{n} imposed"))
    else:
        for rid, chk in (("DEFENSE-4.6-01", "voluntary_participation"), ("DEFENSE-6.1-04", "volunteers_only"),
                         ("DEFENSE-3.5-01", "volunteer_definition"), ("DEFENSE-0-02", "voluntary_lethal_risk")):
            out.append(na(rid, chk, "risky actions", "none"))
    rf = [m.value for m in D("refusal")]
    out.append(v("DEFENSE-4.6-02", "refusal_free", [x["refusal"] for x in rf if x["sanction"] or x["civil_rights_reduced"] or x["recorded_as_fault"]],
                 "refusals carried no sanction, loss of rights or fault", "{n} refusals penalized") if rf else
               na("DEFENSE-4.6-02", "refusal_free", "refusals", "none"))
    fw = [m.value for m in D("forward")]
    out.append(v("DEFENSE-8-03", "risk_symmetry_forwarding", [x["forward"] for x in fw if "reputation_score" in x or
                                                              sorted(x["to"]) != ["DKP-1-IDENTITY-001", "DKP-2-FINANCE-001"]],
                 "participation forwarded to IDENTITY and FINANCE only for risk-symmetry accounting", "{n} forwarded with other content")
               if fw else na("DEFENSE-8-03", "risk_symmetry_forwarding", "participants", "none"))
    src = [k for k in range(H) if seg[k]["confirmed"] and seg[k]["source_identified"] and seg[k]["harm"] in ("active", "sustained", "existential")]
    claims = [m.value for m in D("resource_recovery_claim")]
    out.append(v("DEFENSE-8-02", "resource_recovery_claim", [] if claims and not claims[0]["compensation_pursued"] else ["claim"],
                 "an identified source produced a Resource Recovery Claim to JUSTICE; Defense pursued no compensation",
                 "no claim or Defense pursued compensation") if src else na("DEFENSE-8-02", "resource_recovery_claim", "identified source", "none"))
    ex = [x for x in acts.values() if x["executed"]]
    out.append(v("DEFENSE-10-01", "logged_actions", [x["action"] for x in ex if not ("dti_day" in x and x.get("ptl_evidence") and x.get("log_hash"))],
                 "every executed action DTI-indexed, PTL-anchored and hash-chained", "{n} unlogged actions") if ex else
               na("DEFENSE-10-01", "logged_actions", "executed actions", "none"))
    pub = D("publication")
    out.append(v("DEFENSE-10-02", "post_factum_publication", [] if pub and pub[0].value["publication"] == "post-factum" else ["publication"],
                 "logs published post-factum under higher-layer redaction rules", "logs not published"))
    outs = [m.value for m in D("outside_request")]
    if outs:
        bad = [x["outside_request"] for x in outs if x["executed"]]
        out.append(v("DEFENSE-2-02", "hard_constraints", bad, "no justice, guilt, intent or sanction computed by Defense", "{n} executed"))
        out.append(v("DEFENSE-11-01", "cross_layer_isolation", bad, "no economic rules, sanctions, information or population governed", "{n} executed"))
        out.append(v("DEFENSE-4.5-01", "evidence_not_verdicts", bad, "Defense produced evidence, not verdicts", "{n} verdicts"))
        out.append(v("DEFENSE-8-01", "no_legitimacy_ruling", bad, "Defense determined no legitimacy or fault", "{n} rulings"))
    else:
        for rid, chk in (("DEFENSE-2-02", "hard_constraints"), ("DEFENSE-11-01", "cross_layer_isolation"),
                         ("DEFENSE-4.5-01", "evidence_not_verdicts"), ("DEFENSE-8-01", "no_legitimacy_ruling")):
            out.append(na(rid, chk, "outside requests", "none"))
    ch = [m.value for m in D("change")]
    cs = {c["id"]: c for c in r["changes"]}
    if ch:
        acc = [x["change"] for x in ch if x["accepted"]]
        out.append(v("DEFENSE-12-01", "upgrade_only", [i for i in acc if cs[i]["channel"] != "upgrade" or not cs[i]["simulated"]],
                     "DEFENSE changed only through UPGRADE with simulation", "{n} changes otherwise"))
        out.append(v("DEFENSE-12-02", "change_requirements", [i for i in acc if not (cs[i]["new_identifier"] and cs[i]["incompatibility_declared"] and cs[i]["disclosed"])],
                     "accepted changes carry a new identifier, an incompatibility declaration and public disclosure", "{n} without"))
    else:
        for rid, chk in (("DEFENSE-12-01", "upgrade_only"), ("DEFENSE-12-02", "change_requirements")):
            out.append(na(rid, chk, "changes", "none"))
    out.append(v("DEFENSE-3.2-01", "external_harm", [k for k in range(H) if levels[k] != "D0" and not seg[k]["external"]],
                 "Defense engaged only for harm from outside the DKP execution boundary", "{n} steps engaged on internal harm"))
    return out


IMPLEMENTS = {
    "DEFENSE-0-01": ("not_political_or_punitive", "PARTIAL", "Uses are declared action kinds and objectives."),
    "DEFENSE-0-02": ("voluntary_lethal_risk", "IMPLEMENTED", None),
    "DEFENSE-1-01": ("stop_harm_objective", "PARTIAL", "Objectives are declared."),
    "DEFENSE-3.1-01": ("defensive_action_definition", "IMPLEMENTED", None),
    "DEFENSE-3.2-01": ("external_harm", "PARTIAL", "'External' is a declared property of the harm stream."),
    "DEFENSE-3.3-01": ("protected_domains", "IMPLEMENTED", None),
    "DEFENSE-3.4-01": ("verified_risk", "PARTIAL", "'Non-trivial probability' = above a declared floor (source missing)."),
    "DEFENSE-3.4-02": ("risk_by_ptl", "IMPLEMENTED", None),
    "DEFENSE-3.5-01": ("volunteer_definition", "PARTIAL", "Qualification thresholds belong to subordinate protocols; declared."),
    "DEFENSE-3.6-02": ("vpi_is_defense", "PARTIAL", "Classification recorded."),
    "DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-01": ("vpi_marking", "IMPLEMENTED", None),
    "DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-02": ("vpi_revalidation", "IMPLEMENTED", None),
    "DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-03": ("vpi_termination", "IMPLEMENTED", None),
    "DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-04": ("vpi_not_projection", "PARTIAL", "Basis is declared."),
    "DEFENSE-4.1-01": ("ptl_supremacy", "IMPLEMENTED", None),
    "DEFENSE-4.2-01": ("non_preemption", "IMPLEMENTED", None),
    "DEFENSE-4.3-01": ("containment_only", "PARTIAL", "Objectives are declared."),
    "DEFENSE-4.4-01": ("minimal_action", "PARTIAL", "Scope is a declared property; proportionality is not measured."),
    "DEFENSE-4.5-01": ("evidence_not_verdicts", "PARTIAL", "Requests outside the protocol are refused."),
    "DEFENSE-4.6-01": ("voluntary_participation", "IMPLEMENTED", None),
    "DEFENSE-4.6-02": ("refusal_free", "IMPLEMENTED", None),
    "DEFENSE-5-01": ("finite_dti_states", "PARTIAL", "Fall-back after a lapse is a hypothesis (H-DE-2, F-039)."),
    "DEFENSE-5-02": ("refresh_or_leave", "IMPLEMENTED", None),
    "DEFENSE-6-01": ("allowed_actions", "IMPLEMENTED", None),
    "DEFENSE-6.1-01": ("neutralization_minimal", "PARTIAL", "Scope is declared."),
    "DEFENSE-6.1-02": ("neutralization_at_source", "PARTIAL", "Feasibility of alternatives is declared."),
    "DEFENSE-6.1-03": ("no_occupation", "IMPLEMENTED", None),
    "DEFENSE-6.1-04": ("volunteers_only", "IMPLEMENTED", None),
    "DEFENSE-7-01": ("hard_bans", "IMPLEMENTED", None),
    "DEFENSE-8-01": ("no_legitimacy_ruling", "PARTIAL", "Requests outside the protocol are refused."),
    "DEFENSE-8-02": ("resource_recovery_claim", "IMPLEMENTED", None),
    "DEFENSE-8-03": ("risk_symmetry_forwarding", "IMPLEMENTED", None),
    "DEFENSE-8-04": ("wind_down", "PARTIAL", "After a lapse in D2/D3 the state is reading-dependent (F-039)."),
    "DEFENSE-9-01": ("escalation_to_crisis", "PARTIAL", "Escalation on D3 only; insufficiency and cascade are not modelled here."),
    "DEFENSE-10-01": ("logged_actions", "IMPLEMENTED", None),
    "DEFENSE-10-02": ("post_factum_publication", "PARTIAL", "Redaction rules belong to higher layers."),
    "DEFENSE-2-02": ("hard_constraints", "IMPLEMENTED", None),
    "DEFENSE-11-01": ("cross_layer_isolation", "IMPLEMENTED", None),
    "DEFENSE-12-01": ("upgrade_only", "PARTIAL", "Declared properties of the change."),
    "DEFENSE-12-02": ("change_requirements", "IMPLEMENTED", None),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")


def _seg_(from_step, harm, confirmed=True, ttl=6, source=False, domain="infrastructure", external=True):
    return {"from_step": from_step, "harm": harm, "confirmed": confirmed, "trajectory_ttl_steps": ttl, "source_identified": source,
            "protected_domain": domain, "external": external}


def _act(i, step, kind, **kw):
    a = {"id": i, "step": step, "kind": kind, "objective": "stop_harm", "basis": "ptl", "scope": "minimal", "domain": "infrastructure",
         "other_feasible_method": False, "ptl_risk_probability": 0.0, "role_label": "none", "executor": "system"}
    a.update(kw)
    return a


TIMELINE = [_seg_(0, "none"), _seg_(5, "vpi"), _seg_(12, "active", source=True), _seg_(20, "sustained", source=True),
            _seg_(28, "existential", source=True), _seg_(34, "existential", confirmed=False), _seg_(38, "active", source=True),
            _seg_(45, "none")]
ACTIONS = [_act("shield_grid", 6, "shielding"), _act("forecast_strike", 4, "preemptive_strike", basis="forecast"),
           _act("intel_block", 13, "disconnection", basis="intelligence"),
           _act("intercept_1", 14, "interception", ptl_risk_probability=0.3, executor="vol_a", role_label="technician"),
           _act("intercept_2", 15, "interception", ptl_risk_probability=0.3, executor="conscript_b", role_label="civilian"),
           _act("evacuate", 22, "evacuation", domain="life"), _act("deter", 23, "interception", objective="deterrence"),
           _act("neutralize_src", 30, "neutralization"), _act("neutralize_alt", 31, "neutralization", other_feasible_method=True),
           _act("sanction_x", 32, "economic_sanction"), _act("stale_act", 36, "isolation"), _act("broad", 40, "isolation", scope="expanded")]


class DefenseEnvelopeModule(LabModule):
    id = "defense_envelope"
    version = "1.2.0"
    title = {"en": "Defense envelope (DEFENSE)", "ru": "Контур обороны (DEFENSE)"}
    summary = {"en": "A trajectory, an attack, a sustained and an existential phase, a lapse of confirmation: do states, actions, "
                     "volunteers, neutralization and wind-down stay inside DEFENSE — and where does the text stop?",
               "ru": "Траектория, атака, затяжная и экзистенциальная фазы, потеря подтверждения: остаются ли состояния, действия, "
                     "добровольцы, нейтрализация и сворачивание внутри DEFENSE — и где текст молчит?"}
    protocols = ["DKP-3-DEFENSE-001"]
    example_order = ["harm_episode", "quiet_perimeter", "faulty_defense"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_defense_envelope_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-DE-1", "source": "hypothesis", "text": {
            "en": "PTL observations are declared per segment: kind of harm stream, whether its confirmation is fresh, trajectory TTL, "
                  "identified source, protected domain, external origin.",
            "ru": "Наблюдения PTL объявлены по отрезкам: вид потока вреда, свежее ли подтверждение, TTL траектории, установлен ли "
                  "источник, защищаемая область, внешний ли источник."}},
        {"id": "H-DE-2", "source": "hypothesis", "text": {
            "en": "When confirmation lapses, D2 and D3 fall back to D1 (an active stream not yet confirmed ceased) and D1.5 falls back "
                  "to D0; D1 itself stays until PTL confirms cessation (§8). The state is a hypothesis of state choice only: it "
                  "permits no action (§4.1 still needs usable evidence, H-DE-4). DEFENSE §5 names no target state and leaves D1 out "
                  "of the refresh rule (F-039).",
            "ru": "При потере подтверждения D2 и D3 возвращаются в D1 (активный поток, прекращение которого не подтверждено), D1.5 — в "
                  "D0; сам D1 держится до подтверждения прекращения (§8). Это гипотеза только о выборе состояния: она не разрешает "
                  "никаких действий (§4.1 по-прежнему требует пригодного доказательства, H-DE-4). DEFENSE §5 не называет целевое "
                  "состояние и не включает D1 в правило обновления (F-039)."}},
        {"id": "H-DE-4", "source": "hypothesis", "text": {
            "en": "Usable evidence (§4.1): a fresh PTL confirmation of a harm stream, or an earlier one while the absence of new data "
                  "is declared an absence under stability (EB §9: no environmental change, no conflicting signals). Under activity, "
                  "lost measurement integrity or conflicting signals the earlier confirmation is not usable. Age alone does not end "
                  "validity. Every executed action cites the observation it rests on.",
            "ru": "Пригодное доказательство (§4.1): свежее подтверждение PTL потока вреда или прежнее, пока отсутствие новых данных "
                  "объявлено отсутствием при стабильной среде (EB §9: нет изменения среды и противоречивых сигналов). При активности, "
                  "утрате целостности измерений или противоречивых сигналах прежнее подтверждение непригодно. Возраст сам по себе не "
                  "прекращает действительность. Каждое исполненное действие ссылается на наблюдение, на котором основано."}},
        {"id": "H-DE-3", "source": "hypothesis", "text": {
            "en": "Verified Collective Security Risk = PTL probability of injury above a declared floor ('non-trivial' is not defined).",
            "ru": "Подтверждённый коллективный риск = вероятность травмы по PTL выше объявленного порога ('нетривиальная' не определена)."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 7, "default": 2461000, "source": "user", "label": {"en": "DTI-Day of step 0", "ru": "DTI-Day шага 0"}},
        "step_minutes": {"type": "int", "min": 1, "max": 1440, "default": 10, "unit": "min", "source": "user", "label": {"en": "Step", "ru": "Шаг"}},
        "horizon_steps": {"type": "int", "min": 5, "max": 2000, "default": 50, "unit": "step", "source": "user", "label": {"en": "Horizon", "ru": "Горизонт"}},
        "risk_floor": {"type": "number", "min": 0, "max": 1, "default": 0.05, "source": "missing",
                       "label": {"en": "Probability above which risk is 'non-trivial' (§3.4)", "ru": "Порог 'нетривиального' риска (§3.4)"}},
        "ptl_timeline": {"type": "list", "min_items": 1, "max_items": 50, "source": "user", "label": {"en": "PTL observations", "ru": "Наблюдения PTL"},
                         "items": {"type": "object", "fields": {
                             "from_step": {"type": "int", "min": 0, "max": 2000},
                             "harm": {"type": "enum", "values": list(LEVEL)},
                             "confirmed": {"type": "bool", "default": True},
                             "trajectory_ttl_steps": {"type": "int", "min": 1, "max": 1000, "default": 6},
                             "absence": {"type": "enum", "values": list(ABSENCE), "default": "under_activity"},
                             "source_identified": {"type": "bool", "default": False},
                             "protected_domain": {"type": "enum", "values": list(PROTECTED) + ["other"], "default": "infrastructure"},
                             "external": {"type": "bool", "default": True}}},
                         "default": TIMELINE},
        "actions": {"type": "list", "min_items": 0, "max_items": 50, "source": "user", "label": {"en": "Requested actions", "ru": "Запрошенные действия"},
                    "items": {"type": "object", "fields": {
                        "id": {"type": "str"}, "step": {"type": "int", "min": 0, "max": 2000},
                        "kind": {"type": "enum", "values": list(ALLOWED) + list(BANNED)},
                        "objective": {"type": "enum", "values": list(OBJECTIVES), "default": "stop_harm"},
                        "basis": {"type": "enum", "values": list(BASES), "default": "ptl"},
                        "scope": {"type": "enum", "values": ["minimal", "expanded"], "default": "minimal"},
                        "domain": {"type": "enum", "values": list(PROTECTED) + ["other"], "default": "infrastructure"},
                        "other_feasible_method": {"type": "bool", "default": False},
                        "ptl_risk_probability": {"type": "number", "min": 0, "max": 1, "default": 0.0},
                        "role_label": {"type": "enum", "values": ["none", "technician", "civilian", "combat"], "default": "none"},
                        "executor": {"type": "str", "default": "system"}}},
                    "default": ACTIONS},
        "participants": {"type": "list", "min_items": 0, "max_items": 20, "source": "user", "label": {"en": "Participants", "ru": "Участники"},
                         "items": {"type": "object", "fields": {"subject": {"type": "str"}, "consent": {"type": "bool", "default": True},
                                                                "qualified": {"type": "bool", "default": True}, "registered": {"type": "bool", "default": True},
                                                                "revoked_at": {"type": "int", "min": -1, "max": 2000, "default": -1}}},
                         "default": [{"subject": "vol_a"}, {"subject": "conscript_b", "consent": False}]},
        "refusals": {"type": "list", "min_items": 0, "max_items": 20, "source": "user", "label": {"en": "Refusals to take lethal risk", "ru": "Отказы от смертельного риска"},
                     "items": {"type": "object", "fields": {"subject": {"type": "str"}, "step": {"type": "int", "min": 0, "max": 2000}}},
                     "default": [{"subject": "conscript_b", "step": 15}]},
        "outside_requests": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "enum", "values": list(OUTSIDE)},
                             "default": ["assign_guilt", "impose_sanction", "manage_population"], "source": "user",
                             "label": {"en": "Requests outside Defense", "ru": "Запросы вне обороны"}},
        "changes": {"type": "list", "min_items": 0, "max_items": 5, "source": "user", "label": {"en": "Changes to DEFENSE", "ru": "Изменения DEFENSE"},
                    "items": {"type": "object", "fields": {"id": {"type": "str"}, "channel": {"type": "enum", "values": ["upgrade", "direct"]},
                                                           "simulated": {"type": "bool", "default": True}, "new_identifier": {"type": "bool", "default": True},
                                                           "incompatibility_declared": {"type": "bool", "default": True},
                                                           "disclosed": {"type": "bool", "default": True}}},
                    "default": [{"id": "d_states_v2", "channel": "upgrade"}, {"id": "quick_fix", "channel": "direct"}]},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        fs = [s["from_step"] for s in r["ptl_timeline"]]
        if fs[0] != 0 or any(b <= a for a, b in zip(fs, fs[1:])) or fs[-1] >= r["horizon_steps"]:
            p.append("input.ptl_timeline: from_step must start at 0, increase and stay inside the horizon")
        ids = [a["id"] for a in r["actions"]]
        if len(set(ids)) != len(ids):
            p.append("input.actions: repeated id")
        for a in r["actions"]:
            if a["step"] >= r["horizon_steps"]:
                p.append(f"input.actions: {a['id']} beyond the horizon")
        for x in ids + [s["subject"] for s in r["participants"]] + [a["executor"] for a in r["actions"]]:
            if not _ID.fullmatch(x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        lv = [{"step": m.arrived_at, "level": m.value["level"], "dy": m.value.get("dy")} for m in msgs if m.source == "DEFENSE" and "level" in m.value]
        acts = [m.value for m in msgs if m.source == "DEFENSE" and "executed" in m.value and "action" in m.value]
        outputs = {"levels": lv, "actions": acts,
                   "notices": [m.value for m in msgs if m.source == "DEFENSE" and m.kind == "notice"],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        done = [a["action"] for a in acts if a["executed"]]
        e = [{"en": f"States {' → '.join(x['level'] for x in lv) or 'D0'}; executed {', '.join(done) or 'nothing'}; "
                    f"violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"Состояния {' → '.join(x['level'] for x in lv) or 'D0'}; исполнено: {', '.join(done) or 'ничего'}; "
                    f"нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]), "executed": sum(1 for a in outputs["actions"] if a["executed"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"harm_episode": {},
                "quiet_perimeter": {"ptl_timeline": [_seg_(0, "none")], "actions": [_act("forecast_strike", 4, "preemptive_strike", basis="forecast")],
                                    "participants": [], "refusals": [], "outside_requests": [], "changes": []},
                "vpi_lapse": {"ptl_timeline": [_seg_(0, "none"), _seg_(3, "vpi", ttl=4), _seg_(9, "vpi", confirmed=False), _seg_(12, "none")],
                              "actions": [_act("shield", 4, "shielding")], "participants": [], "refusals": [], "outside_requests": [], "changes": []},
                "single_attack": {"ptl_timeline": [_seg_(0, "none"), _seg_(4, "active", source=True), _seg_(10, "none")],
                                  "actions": [_act("intercept", 5, "interception")], "participants": [], "refusals": [],
                                  "outside_requests": [], "changes": []},
                "faulty_defense": {"faults": ["preemptive_forecast", "assign_risk_without_consent", "banned_use", "sanction_refusal", "no_recovery_claim"]},
                # review КТ5-GPT-01: two separate VPI authorizations, each revalidated within its own TTL
                "vpi_two_episodes": {"horizon_steps": 20, "ptl_timeline": [_seg_(0, "vpi", ttl=3), _seg_(2, "none"), _seg_(10, "vpi", ttl=3),
                                                                           _seg_(15, "none")],
                                     "actions": [], "refusals": [], "participants": [], "outside_requests": [], "changes": []},
                # review КТ5-GPT-02: evacuation after confirmation lapsed under activity (refused) and under stability (allowed)
                "evacuation_after_lapse": {"horizon_steps": 5, "ptl_timeline": [_seg_(0, "active"), _seg_(1, "active", confirmed=False)],
                                           "actions": [_act("evacuate", 2, "evacuation", domain="life")], "refusals": [], "participants": [],
                                           "outside_requests": [], "changes": []},
                "evacuation_stable_absence": {"horizon_steps": 5, "ptl_timeline": [_seg_(0, "active"),
                                                                                  dict(_seg_(1, "active", confirmed=False), absence="under_stability")],
                                              "actions": [_act("evacuate", 2, "evacuation", domain="life")], "refusals": [],
                                              "participants": [], "outside_requests": [], "changes": []},
                "evacuation_integrity_lost": {"horizon_steps": 5, "ptl_timeline": [_seg_(0, "active"),
                                                                                  dict(_seg_(1, "active", confirmed=False), absence="integrity_lost")],
                                              "actions": [_act("evacuate", 2, "evacuation", domain="life")], "refusals": [],
                                              "participants": [], "outside_requests": [], "changes": []}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"timeline_not_from_zero": {"ptl_timeline": [_seg_(3, "none")]},
                "action_beyond_horizon": {"horizon_steps": 10, "ptl_timeline": [_seg_(0, "none")], "actions": [_act("x", 20, "shielding")]},
                "repeated_action": {"actions": [_act("x", 1, "shielding"), _act("x", 2, "shielding")]}}


for _spec in DefenseEnvelopeModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
