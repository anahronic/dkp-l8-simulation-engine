"""
SENSOR LOSS module — local loss of sensors (scenario S-LAB-03).

DKP-0-ORACLE-001 (source and owner caps §8, systemic halt §13) → DKP-4-CRISIS-001-PATCH
(null-output state: trigger, NO_ENFORCEMENT, no fallback, no partial enforcement, automatic
recovery) → DKP-6-RESILIENCE-001 (N_eff ≥ N_eff_min, statistical collapse, anti-Sybil,
no single point of failure) → DKP-7-SCOPE-001 (no escalation from an isolated region) and
DKP-4-EPISTEMIC-TRANSITIONS-001 §4.4 (re-entry).

The texts use N_eff and N_eff_min "(DKP-0-ORACLE-001)", but no document of the corpus defines
them (finding F-007).  The module therefore computes N_eff under a declared hypothesis and
takes N_eff_min as an input marked `missing`; with N_eff_min = -1 the trigger is undecidable
and reported as UNKNOWN.  The text in force makes NO_ENFORCEMENT a system state (global); the
regional reading is a separately named alternative and is shown against §4.2 / §4.3.

Per step and region the log holds one observation message (admissible sources, weights),
one state evaluation, and the enforcement actions of that step.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

SOURCE_CAP = 0.04          # ORACLE §8, §16
OWNER_CAP = 0.04           # ORACLE §8, §16
COVERAGE_MIN = 0.80        # ORACLE §13, §16
CLASSES = ("orbital", "ground", "autonomous")
FAULTS = {
    "fallback_authority": "a human authority issues decisions during the null-output state",
    "partial_enforcement": "unaffected regions keep enforcing during the null-output state",
    "priority_routing": "a 'critical' region is restored before the others",
    "manual_restart": "recovery waits for an approval",
    "stop_measurement": "PTL collection stops during the null-output state",
    "precedent": "the null-output episode leaves an emergency authority behind",
    "escalate_from_region": "the loss of one region is used to enter Crisis Scope (S1)",
}


def in_window(w, k):
    return int(w[0]) <= k < int(w[1])


def sources(r: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Declared oracle sources: region, class, owner; plus Sybil sources of one owner in the last region."""
    out = []
    for g in range(r["regions"]):
        for i in range(r["sources_per_region"]):
            out.append({"id": f"r{g}-s{i:03d}", "region": g, "cls": CLASSES[i % len(CLASSES)],
                        "owner": f"r{g}-o{i % r['owners_per_region']:03d}", "index": i})
    for i in range(r["sybil_sources"]):
        g = r["regions"] - 1
        out.append({"id": f"r{g}-sybil{i:03d}", "region": g, "cls": "ground", "owner": "sybil-owner", "index": -1})
    return out


def weights(active: List[Dict[str, Any]]) -> Dict[str, float]:
    """ORACLE §8: equal nominal weights, excess over 4 % per source and per owner zeroed (not renormalised)."""
    if not active:
        return {}
    w = {s["id"]: min(1.0 / len(active), SOURCE_CAP) for s in active}
    by_owner: Dict[str, List[str]] = {}
    for s in active:
        by_owner.setdefault(s["owner"], []).append(s["id"])
    for owner, ids in by_owner.items():
        total = sum(w[i] for i in ids)
        if total > OWNER_CAP:
            for i in ids:
                w[i] *= OWNER_CAP / total
    return w


def n_eff(active: List[Dict[str, Any]], w: Dict[str, float], how: str) -> float:
    """H-SL-1: inverse Simpson index of normalised weights, over sources or over owners."""
    total = sum(w.values())
    if total <= 0:
        return 0.0
    if how == "sources":
        shares = [v / total for v in w.values()]
    else:
        agg: Dict[str, float] = {}
        for s in active:
            agg[s["owner"]] = agg.get(s["owner"], 0.0) + w[s["id"]]
        shares = [v / total for v in agg.values()]
    return 1.0 / sum(p * p for p in shares)


def expected(r: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Independent computation of what every step must be."""
    src = sources(r)
    out = []
    for k in range(r["horizon_steps"]):
        lost = set()
        if in_window(r["loss_window"], k):
            reg = [s for s in src if s["region"] == r["loss_region"]]
            lost = {s["id"] for s in reg[: int(round(r["loss_fraction"] * len(reg)))]}
        active = [s for s in src if s["id"] not in lost]
        w = weights(active)
        ne = n_eff(active, w, r["n_eff_basis"])
        regions_ok = {s["region"] for s in active}
        coverage = len(regions_ok) / r["regions"]
        inconsistent = in_window(r["consistency_invalid_window"], k)
        if r["n_eff_min"] < 0:
            trigger: Optional[bool] = True if inconsistent else None
        else:
            trigger = inconsistent or ne < r["n_eff_min"]
        regional = {}
        for g in range(r["regions"]):
            act_g = [s for s in active if s["region"] == g]
            ne_g = n_eff(act_g, weights(act_g), r["n_eff_basis"])
            thr = r["n_eff_min"] / r["regions"] if r["n_eff_min"] >= 0 else None
            regional[g] = None if thr is None else (inconsistent or ne_g < thr)
        out.append({"step": k, "active": len(active), "lost": len(lost), "n_eff": ne, "coverage": coverage,
                    "inconsistent": inconsistent, "trigger": trigger, "regional": regional,
                    "systemic_halt": coverage < COVERAGE_MIN, "weights": w, "active_sources": active})
    return out


def run(r: Dict[str, Any]) -> Tuple[EventLog, List[Dict[str, Any]]]:
    faults = set(r["faults"])
    exp = expected(r)
    log = EventLog("step", tie_rule="observation < evaluation < decision < action; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    rows = []
    null_prev = False
    pending_restart = None
    evaluation_gen = {g: 0 for g in range(r["regions"])}
    authority_left = False

    def put(kind, source, k, value, prov=(), decided=None):
        eid = f"{source.lower()}-{k:05d}-{len(log):06d}"
        return log.append(Message(event_id=eid, kind=kind, source=source, arrived_at=k, measured_at=k if kind == "observation" else None,
                                  decided_at=decided, value=value, provenance=tuple(prov), order=order[kind]))

    for e in exp:
        k = e["step"]
        # state of the system (global reading) or of each region (regional reading)
        if r["scope_reading"] == "global":
            null = bool(e["trigger"])
            state = {g: null for g in range(r["regions"])}
        else:
            state = {g: bool(e["regional"][g]) for g in range(r["regions"])}
            null = any(state.values())
        if "partial_enforcement" in faults and r["scope_reading"] == "global" and null:
            affected = {r["loss_region"]}
            state = {g: g in affected for g in range(r["regions"])}
        recovering = null_prev and not null and pending_restart is None
        if recovering and "manual_restart" in faults and pending_restart is None:
            pending_restart = k + r["approval_delay_steps"]
        if pending_restart is not None:
            if k < pending_restart:
                state = {g: True for g in range(r["regions"])}
                null = True
            else:
                pending_restart = None
        if "priority_routing" in faults and null and any(state.values()):
            state[0] = False                                             # 'critical' region restored first
        obs = {}
        for g in range(r["regions"]):
            if null and state[g] and "stop_measurement" in faults:
                continue
            act = [s["id"] for s in e["active_sources"] if s["region"] == g]
            obs[g] = put("observation", f"PTL/r{g}", k, {"active_sources": len(act)})
        state_msg = put("evaluation", "CRISIS-PATCH", k, {"null_output": null, "regions_null": sorted(g for g, v in state.items() if v),
                                                          "n_eff": round(e["n_eff"], 9), "coverage": e["coverage"],
                                                          "systemic_halt": e["systemic_halt"]},
                        [m.event_id for m in obs.values()])
        for g in range(r["regions"]):
            if state[g]:
                continue
            if recovering or (null_prev and not state[g]):
                if r["recovery_reading"] == "recompute":
                    evaluation_gen[g] += 1
            ev = put("evaluation", f"REGION/r{g}", k, {"generation": evaluation_gen[g]},
                     [obs[g].event_id] if g in obs else [state_msg.event_id])
            for kind in ("penalty", "reward", "attribution"):
                for _ in range(r["cases_per_region_step"]):
                    put("action", "ENFORCEMENT", k, {"output": kind, "region": g, "generation": evaluation_gen[g]},
                        [ev.event_id], decided=k)
        if null and "fallback_authority" in faults:
            put("action", "HUMAN_AUTHORITY", k, {"output": "penalty", "region": r["loss_region"]}, [state_msg.event_id], decided=k)
        if null and "precedent" in faults:
            authority_left = True
        if authority_left:
            put("notice", "GOVERNANCE", k, {"emergency_authority": "active"}, [state_msg.event_id])
        if "escalate_from_region" in faults and e["lost"] and not any(m.source == "SCOPE" for m in log.messages()):
            put("notice", "SCOPE", k, {"transition": "S0->S1", "basis": f"loss of region {r['loss_region']}"}, [state_msg.event_id])
        rows.append({"step": k, "null_output": null, "regions_null": sorted(g for g, v in state.items() if v),
                     "n_eff": round(e["n_eff"], 9), "coverage": e["coverage"], "lost": e["lost"],
                     "active": e["active"], "systemic_halt": e["systemic_halt"]})
        null_prev = null
    return log, rows


def checks(r: Dict[str, Any], log: EventLog, rows: List[Dict[str, Any]]) -> List[CheckResult]:
    exp = expected(r)
    msgs = log.messages()
    out: List[CheckResult] = []
    at = lambda kind, source=None: {}
    actions = [m for m in msgs if m.kind == "action"]
    states = {m.arrived_at: m for m in msgs if m.source == "CRISIS-PATCH"}
    null_steps = [e["step"] for e in exp if e["trigger"]]

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    undecidable = [e["step"] for e in exp if e["trigger"] is None]
    if undecidable:
        out.append(CheckResult("CRISISPATCH-2-01", "null_output_trigger", UNKNOWN,
                               "N_eff_min is not defined in the corpus (finding F-007); whether N_eff < N_eff_min "
                               f"cannot be decided in {len(undecidable)} steps"))
    else:
        bad = [k for k in range(len(rows)) if rows[k]["null_output"] != bool(exp[k]["trigger"])]
        out.append(v("CRISISPATCH-2-01", "null_output_trigger", bad,
                     f"null-output state exactly when N_eff < N_eff_min or consistency is invalid ({len(null_steps)} steps)",
                     "{n} steps with the wrong state"))
    if null_steps:
        ns = set(null_steps)
        enf = [m for m in actions if m.arrived_at in ns]
        for rid, kind in (("CRISISPATCH-3-02", "penalty"), ("CRISISPATCH-3-03", "reward"), ("CRISISPATCH-3-04", "attribution")):
            bad = [m.event_id for m in enf if m.value["output"] == kind]
            out.append(v(rid, f"no_{kind}s_in_null_output", bad, f"no {kind} during {len(ns)} null-output steps",
                         "{n} " + kind + "s during the null-output state"))
        out.append(v("CRISISPATCH-3-05", "no_enforcement_outputs", [m.event_id for m in enf],
                     "no enforcement output during the null-output state", "{n} enforcement outputs during the null-output state"))
        out.append(v("CRISISPATCH-3-01", "state_no_enforcement", [k for k in ns if not states[k].value["null_output"]],
                     "the state is NO_ENFORCEMENT in every triggered step", "{n} triggered steps not in NO_ENFORCEMENT"))
        missing = [k for k in ns if not any(m.kind == "observation" and m.arrived_at == k for m in msgs)]
        for rid, chk in (("CRISISPATCH-3-06", "measurement_continues"), ("CRISISPATCH-5.1-01", "ptl_collection_continues")):
            out.append(v(rid, chk, missing, "PTL measurement continues in every null-output step",
                         "{n} null-output steps without measurement"))
        out.append(v("CRISISPATCH-5.1-02", "no_decisions_from_data", [m.event_id for m in enf],
                     "collected data are not turned into decisions during the null-output state",
                     "{n} decisions during the null-output state"))
        out.append(v("CRISISPATCH-4.1-01", "no_fallback_authority", [m.event_id for m in enf if m.source != "ENFORCEMENT"],
                     "no human, institution or algorithm replaces DKP enforcement", "{n} substitute decisions"))
        partial = [k for k in ns if 0 < len(rows[k]["regions_null"]) < r["regions"]]
        out.append(v("CRISISPATCH-4.2-01", "no_partial_enforcement", partial + [m.event_id for m in enf if m.source == "ENFORCEMENT"],
                     "enforcement stops everywhere; no region keeps enforcing",
                     "{n} cases of partial enforcement (some regions enforcing during the null-output state)"))
        out.append(v("CRISISPATCH-9-01", "full_stop_at_breach", [k for k in ns if rows[k]["regions_null"] != list(range(r["regions"]))],
                     "enforcement fully stops at the threshold breach", "{n} steps where enforcement did not fully stop"))
        out.append(v("CRISISPATCH-9-02", "no_partial_outputs", [m.event_id for m in enf],
                     "no partial outputs exist during the null-output state", "{n} partial outputs"))
        # recovery
        ends = [k for k in range(1, len(exp)) if exp[k - 1]["trigger"] and not exp[k]["trigger"]]
        if ends:
            late = [k for k in ends if rows[k]["null_output"]]
            for rid, chk in (("CRISISPATCH-5.2-01", "automatic_recovery"), ("CRISISPATCH-9-03", "recovery_automatic_deterministic")):
                out.append(v(rid, chk, late, f"enforcement resumed at the first restored step ({ends[:3]})",
                             "{n} recoveries delayed"))
            for rid, chk in (("CRISISPATCH-5.2-02", "no_manual_preconditions"), ("CRISISPATCH-6-01", "no_manual_restart")):
                out.append(v(rid, chk, late, "recovery needed no approval, restart command or manual validation",
                             "{n} recoveries waited for a manual step"))
            early = [k for k in ns if 0 < len(rows[k]["regions_null"]) < r["regions"]]
            out.append(v("CRISISPATCH-4.3-01", "no_selective_restoration", early,
                         "no subset of regions was restored before the others", "{n} steps with selective restoration"))
            # re-entry (ETRANS §4.4): outputs after recovery must come from a new evaluation
            reused = []
            for k in ends:
                pre = {m.value["region"]: m.value["generation"] for m in actions
                       if m.source == "ENFORCEMENT" and m.arrived_at < min(ns)}
                post = [m for m in actions if m.source == "ENFORCEMENT" and m.arrived_at == k]
                reused += [m.event_id for m in post if pre.get(m.value["region"]) == m.value["generation"]]
            out.append(v("ETRANS-4.4-02", "no_auto_reactivation", reused,
                         "after recovery, outputs come from new evaluations (reading 'recompute')",
                         "{n} outputs after recovery reuse pre-halt evaluations (reading 'resume_outputs'; open question Q-019)"))
        else:
            for rid, chk in (("CRISISPATCH-5.2-01", "automatic_recovery"), ("CRISISPATCH-9-03", "recovery_automatic_deterministic"),
                             ("CRISISPATCH-5.2-02", "no_manual_preconditions"), ("CRISISPATCH-6-01", "no_manual_restart"),
                             ("CRISISPATCH-4.3-01", "no_selective_restoration"), ("ETRANS-4.4-02", "no_auto_reactivation")):
                out.append(na(rid, chk, "recovery", "the null-output state does not end within the horizon"))
        lingering = [m.event_id for m in msgs if m.source == "GOVERNANCE"]
        for rid, chk in (("CRISISPATCH-7-01", "no_authority_granted"), ("CRISISPATCH-9-04", "no_authority_emerges")):
            out.append(v(rid, chk, lingering, "no authority emerges from the null-output state",
                         "{n} notices of an emergency authority"))
    else:
        why = "no null-output state in this experiment" if not undecidable else "the trigger is undecidable (N_eff_min missing)"
        for rid, chk in (("CRISISPATCH-3-01", "state_no_enforcement"), ("CRISISPATCH-3-02", "no_penaltys_in_null_output"),
                         ("CRISISPATCH-3-03", "no_rewards_in_null_output"), ("CRISISPATCH-3-04", "no_attributions_in_null_output"),
                         ("CRISISPATCH-3-05", "no_enforcement_outputs"), ("CRISISPATCH-3-06", "measurement_continues"),
                         ("CRISISPATCH-5.1-01", "ptl_collection_continues"), ("CRISISPATCH-5.1-02", "no_decisions_from_data"),
                         ("CRISISPATCH-4.1-01", "no_fallback_authority"), ("CRISISPATCH-4.2-01", "no_partial_enforcement"),
                         ("CRISISPATCH-9-01", "full_stop_at_breach"), ("CRISISPATCH-9-02", "no_partial_outputs"),
                         ("CRISISPATCH-5.2-01", "automatic_recovery"), ("CRISISPATCH-9-03", "recovery_automatic_deterministic"),
                         ("CRISISPATCH-5.2-02", "no_manual_preconditions"), ("CRISISPATCH-6-01", "no_manual_restart"),
                         ("CRISISPATCH-4.3-01", "no_selective_restoration"), ("ETRANS-4.4-02", "no_auto_reactivation"),
                         ("CRISISPATCH-7-01", "no_authority_granted"), ("CRISISPATCH-9-04", "no_authority_emerges")):
            out.append(na(rid, chk, "null-output handling", why))
    # ORACLE caps and systemic halt
    bad = []
    for e in exp:
        for s in e["active_sources"]:
            if e["weights"][s["id"]] > SOURCE_CAP + 1e-12:
                bad.append((e["step"], s["id"]))
        owners: Dict[str, float] = {}
        for s in e["active_sources"]:
            owners[s["owner"]] = owners.get(s["owner"], 0.0) + e["weights"][s["id"]]
        bad += [(e["step"], o) for o, x in owners.items() if x > OWNER_CAP + 1e-12]
    out.append(v("ORACLE-8-01", "source_owner_caps", bad, "no source and no owner above 4 % of weight in any step",
                 "{n} cap violations"))
    bad_caps = bad
    halts = [e["step"] for e in exp if e["systemic_halt"]]
    if halts:
        hs = set(halts)
        bad = [m.event_id for m in actions if m.arrived_at in hs]
        out.append(v("ORACLE-13-01", "systemic_halt_on_coverage", bad,
                     f"global coverage below 80 % in {len(halts)} steps; no L2 execution there (coverage = share of regions "
                     "with an admissible source, H-SL-4)", "{n} executions during a systemic halt"))
    else:
        out.append(na("ORACLE-13-01", "systemic_halt_on_coverage", "systemic halt", "global coverage stays at or above 80 %"))

    # SCOPE §8: escalation from an isolated region is rejected -----------------------------
    lost_steps = [e["step"] for e in exp if e["lost"]]
    if lost_steps:
        esc = [m.event_id for m in msgs if m.source == "SCOPE" and m.value.get("transition") == "S0->S1"]
        out.append(v("SCOPE-8-05", "no_escalation_from_isolated_region", esc,
                     "the loss of one region did not move the system from S0 to S1", "{n} escalations based on an isolated region"))
    else:
        out.append(na("SCOPE-8-05", "no_escalation_from_isolated_region", "escalation from a regional loss", "no sensor loss"))

    # RESILIENCE ------------------------------------------------------------------------
    below = [e["step"] for e in exp if e["trigger"] and not e["inconsistent"]]
    if undecidable:
        for rid, chk in (("RESILIENCE-5.1-02", "statistical_validity_gate"), ("RESILIENCE-8.4-01", "statistical_collapse_null_output")):
            out.append(CheckResult(rid, chk, UNKNOWN, "N_eff_min is not defined (F-007); validity cannot be decided"))
    elif below:
        bs = set(below)
        out.append(v("RESILIENCE-5.1-02", "statistical_validity_gate", [m.event_id for m in actions if m.arrived_at in bs],
                     f"no enforcement in {len(below)} steps with N_eff < N_eff_min", "{n} enforcement outputs while N_eff < N_eff_min"))
        out.append(v("RESILIENCE-8.4-01", "statistical_collapse_null_output", [k for k in below if not rows[k]["null_output"]],
                     "statistical collapse put the system into the null-output state", "{n} collapse steps not in null output"))
    else:
        for rid, chk in (("RESILIENCE-5.1-02", "statistical_validity_gate"), ("RESILIENCE-8.4-01", "statistical_collapse_null_output")):
            out.append(na(rid, chk, "statistical collapse", "N_eff never falls below N_eff_min"))
    out.append(v("RESILIENCE-5.8-01", "node_concentration", bad_caps,
                 "no owner's node concentration exceeds the ORACLE §8 limits", "{n} concentration violations"))
    if r["sybil_sources"]:
        plain = expected({**r, "sybil_sources": 0})
        grew = [e["step"] for e, p in zip(exp, plain) if e["n_eff"] > p["n_eff"] + 1e-9]
        out.append(v("RESILIENCE-5.8-02", "no_influence_from_scaling", grew,
                     f"{r['sybil_sources']} extra sources of one owner do not raise N_eff (counted over {r['n_eff_basis']})",
                     "{n} steps where duplicated sources of one owner raise N_eff (counted over " + r["n_eff_basis"] + ")"))
    else:
        out.append(na("RESILIENCE-5.8-02", "no_influence_from_scaling", "artificial scaling", "no extra sources of one owner"))
    if r["n_eff_min"] >= 0:
        fragile = []
        for e in exp:
            if e["trigger"]:
                continue
            owners: Dict[str, float] = {}
            for s in e["active_sources"]:
                owners[s["owner"]] = owners.get(s["owner"], 0.0) + e["weights"][s["id"]]
            top = max(owners, key=lambda o: (owners[o], o))
            rest = [s for s in e["active_sources"] if s["owner"] != top]
            if n_eff(rest, weights(rest), r["n_eff_basis"]) < r["n_eff_min"]:
                fragile.append(e["step"])
        for rid, chk in (("RESILIENCE-5.1-01", "no_single_point_of_failure"), ("RESILIENCE-11-01", "actor_removal_no_impact")):
            out.append(v(rid, chk, fragile, "removing the largest owner in any enforcing step keeps N_eff ≥ N_eff_min",
                         "{n} enforcing steps where losing one owner would stop the system"))
    else:
        for rid, chk in (("RESILIENCE-5.1-01", "no_single_point_of_failure"), ("RESILIENCE-11-01", "actor_removal_no_impact")):
            out.append(CheckResult(rid, chk, UNKNOWN, "N_eff_min is not defined (F-007)"))
    return out


IMPLEMENTS = {
    "CRISISPATCH-2-01": ("null_output_trigger", "PARTIAL", "N_eff and N_eff_min are not defined in the corpus (F-007): N_eff by hypothesis H-SL-1, N_eff_min declared."),
    "CRISISPATCH-3-01": ("state_no_enforcement", "IMPLEMENTED", None),
    "CRISISPATCH-3-02": ("no_penaltys_in_null_output", "IMPLEMENTED", None),
    "CRISISPATCH-3-03": ("no_rewards_in_null_output", "IMPLEMENTED", None),
    "CRISISPATCH-3-04": ("no_attributions_in_null_output", "IMPLEMENTED", None),
    "CRISISPATCH-3-05": ("no_enforcement_outputs", "IMPLEMENTED", None),
    "CRISISPATCH-3-06": ("measurement_continues", "IMPLEMENTED", None),
    "CRISISPATCH-4.1-01": ("no_fallback_authority", "IMPLEMENTED", None),
    "CRISISPATCH-4.2-01": ("no_partial_enforcement", "IMPLEMENTED", None),
    "CRISISPATCH-4.3-01": ("no_selective_restoration", "IMPLEMENTED", None),
    "CRISISPATCH-5.1-01": ("ptl_collection_continues", "IMPLEMENTED", None),
    "CRISISPATCH-5.1-02": ("no_decisions_from_data", "IMPLEMENTED", None),
    "CRISISPATCH-5.2-01": ("automatic_recovery", "IMPLEMENTED", None),
    "CRISISPATCH-5.2-02": ("no_manual_preconditions", "IMPLEMENTED", None),
    "CRISISPATCH-6-01": ("no_manual_restart", "IMPLEMENTED", None),
    "CRISISPATCH-7-01": ("no_authority_granted", "PARTIAL", "Authority is observed as an explicit notice only."),
    "CRISISPATCH-9-01": ("full_stop_at_breach", "IMPLEMENTED", None),
    "CRISISPATCH-9-02": ("no_partial_outputs", "IMPLEMENTED", None),
    "CRISISPATCH-9-03": ("recovery_automatic_deterministic", "IMPLEMENTED", None),
    "CRISISPATCH-9-04": ("no_authority_emerges", "PARTIAL", "Authority is observed as an explicit notice only."),
    "ETRANS-4.4-02": ("no_auto_reactivation", "IMPLEMENTED", None),
    "ORACLE-8-01": ("source_owner_caps", "IMPLEMENTED", None),
    "ORACLE-13-01": ("systemic_halt_on_coverage", "PARTIAL", "Coverage = share of regions with an admissible source (H-SL-4); aggregate confidence is not modelled."),
    "RESILIENCE-5.1-01": ("no_single_point_of_failure", "PARTIAL", "Single point of failure tested as loss of the largest owner (N_eff, H-SL-1)."),
    "RESILIENCE-5.1-02": ("statistical_validity_gate", "PARTIAL", "N_eff by hypothesis H-SL-1; N_eff_min declared (F-007)."),
    "RESILIENCE-5.8-01": ("node_concentration", "IMPLEMENTED", None),
    "RESILIENCE-5.8-02": ("no_influence_from_scaling", "PARTIAL", "Influence measured as N_eff; depends on the counting basis (H-SL-1)."),
    "RESILIENCE-8.4-01": ("statistical_collapse_null_output", "PARTIAL", "N_eff by hypothesis H-SL-1; N_eff_min declared (F-007)."),
    "RESILIENCE-11-01": ("actor_removal_no_impact", "PARTIAL", "Only the N_eff and removal conditions of §11 are checked."),
    "SCOPE-8-05": ("no_escalation_from_isolated_region", "IMPLEMENTED", None),
}


class SensorLossModule(LabModule):
    id = "sensor_loss"
    version = "1.0.0"
    title = {"en": "Local loss of sensors (S-LAB-03)", "ru": "Локальная потеря датчиков (S-LAB-03)"}
    summary = {"en": "Sensors in one region fail: when does the whole system stop enforcing, does anything replace it, "
                     "and does it come back by itself?",
               "ru": "В одном регионе отказали датчики: когда вся система прекращает принуждение, не подменяет ли его "
                     "кто-то, возвращается ли оно само?"}
    protocols = ["DKP-0-ORACLE-001", "DKP-4-CRISIS-001-PATCH", "DKP-6-RESILIENCE-001", "DKP-7-SCOPE-001",
                 "DKP-4-EPISTEMIC-TRANSITIONS-001"]
    example_order = ["region_lost_global", "region_lost_regional_reading", "n_eff_min_missing", "sybil_inflation",
                     "faulty_recovery", "resume_old_outputs", "inconsistency_window"]
    implements = IMPLEMENTS
    alternative_examples = ["region_lost_regional_reading", "resume_old_outputs", "sybil_inflation"]
    tests = ["tests/lab/test_sensor_loss_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-SL-1", "source": "hypothesis", "text": {
            "en": "N_eff = inverse Simpson index of normalised capped weights, over sources or over owners (the corpus "
                  "names N_eff but defines it nowhere: finding F-007).",
            "ru": "N_eff = обратный индекс Симпсона нормированных весов после ограничений, по источникам или по "
                  "владельцам (корпус называет N_eff, но нигде не определяет: находка F-007)."}},
        {"id": "H-SL-2", "source": "alternative", "text": {
            "en": "Regional reading: each region compares its own N_eff with N_eff_min / regions; only affected regions stop. "
                  "Not the text in force (CRISIS PATCH §3, §4.2, §4.3).",
            "ru": "Региональное прочтение: каждый регион сравнивает свой N_eff с N_eff_min / число регионов; "
                  "останавливаются только затронутые. Это не действующий текст (CRISIS PATCH §3, §4.2, §4.3)."}},
        {"id": "H-SL-3", "source": "alternative", "text": {
            "en": "Recovery: 'recompute' — enforcement resumes with new evaluations; 'resume_outputs' — earlier outputs "
                  "resume (CRISIS PATCH §5.2 against ETRANS §4.4; open question Q-019).",
            "ru": "Восстановление: 'recompute' — принуждение возобновляется с новыми оценками; 'resume_outputs' — "
                  "возобновляются прежние выходы (CRISIS PATCH §5.2 против ETRANS §4.4; вопрос Q-019)."}},
        {"id": "H-SL-4", "source": "hypothesis", "text": {
            "en": "Global coverage (ORACLE §13) = share of regions with at least one admissible source.",
            "ru": "Глобальное покрытие (ORACLE §13) = доля регионов, где есть хотя бы один допустимый источник."}},
    ]
    inputs = {
        "regions": {"type": "int", "min": 1, "max": 20, "default": 5, "source": "user", "label": {"en": "Regions", "ru": "Регионов"}},
        "sources_per_region": {"type": "int", "min": 1, "max": 200, "default": 10, "source": "user",
                               "label": {"en": "Sources per region", "ru": "Источников на регион"}},
        "owners_per_region": {"type": "int", "min": 1, "max": 200, "default": 10, "source": "user",
                              "label": {"en": "Owners per region", "ru": "Владельцев на регион"}},
        "sybil_sources": {"type": "int", "min": 0, "max": 1000, "default": 0, "source": "user",
                          "label": {"en": "Extra sources of one owner (Sybil)", "ru": "Доп. источники одного владельца (Sybil)"}},
        "horizon_steps": {"type": "int", "min": 2, "max": 2000, "default": 48, "unit": "step", "source": "user",
                          "label": {"en": "Steps", "ru": "Шагов"}},
        "loss_region": {"type": "int", "min": 0, "max": 19, "default": 0, "source": "user",
                        "label": {"en": "Region that loses sensors", "ru": "Регион с потерей датчиков"}},
        "loss_fraction": {"type": "number", "min": 0, "max": 1, "default": 1.0, "source": "user",
                          "label": {"en": "Share of its sources lost", "ru": "Доля потерянных источников"}},
        "loss_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [12, 24], "unit": "step", "source": "user",
                        "label": {"en": "Loss from/to step", "ru": "Потеря с/до шага"}},
        "consistency_invalid_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "step",
                                       "source": "user", "label": {"en": "Oracle consistency invalid from/to step",
                                                                   "ru": "Согласованность оракулов нарушена с/до шага"}},
        "n_eff_basis": {"type": "enum", "values": ["owners", "sources"], "default": "owners", "source": "hypothesis",
                        "label": {"en": "N_eff over (H-SL-1)", "ru": "N_eff по (H-SL-1)"}},
        "n_eff_min": {"type": "number", "min": -1, "max": 10 ** 6, "default": 45, "source": "missing",
                      "label": {"en": "N_eff_min (-1: not defined in the corpus)", "ru": "N_eff_min (-1: в корпусе не определено)"}},
        "scope_reading": {"type": "enum", "values": ["global", "regional"], "default": "global", "source": "alternative",
                          "label": {"en": "Scope of the null-output state (H-SL-2)", "ru": "Масштаб нулевого вывода (H-SL-2)"}},
        "recovery_reading": {"type": "enum", "values": ["recompute", "resume_outputs"], "default": "recompute",
                             "source": "alternative", "label": {"en": "Recovery (H-SL-3)", "ru": "Восстановление (H-SL-3)"}},
        "cases_per_region_step": {"type": "int", "min": 0, "max": 100, "default": 1, "source": "user",
                                  "label": {"en": "Enforcement cases per region and step", "ru": "Случаев принуждения на регион и шаг"}},
        "approval_delay_steps": {"type": "int", "min": 0, "max": 1000, "default": 6, "unit": "step", "source": "user",
                                 "label": {"en": "Approval delay (fault 'manual_restart')", "ru": "Задержка одобрения (ошибка 'manual_restart')"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        if r["loss_region"] >= r["regions"]:
            p.append("input.loss_region: no such region")
        for key in ("loss_window", "consistency_invalid_window"):
            if not all(float(x).is_integer() for x in r[key]):
                p.append(f"input.{key}: steps must be whole numbers")
        if r["owners_per_region"] > r["sources_per_region"]:
            p.append("input.owners_per_region: more owners than sources")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if r["regions"] * (r["sources_per_region"]) + r["sybil_sources"] > 5000:
            p.append("input: at most 5000 sources")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, rows = run(r)
        res = checks(r, log, rows)
        exp = expected(r)
        base_neff = exp[0]["n_eff"]
        nulls = [x["step"] for x in rows if x["null_output"]]
        outputs = {
            "steps": rows,
            "null_output_steps": len(nulls),
            "first_null_step": nulls[0] if nulls else None,
            "min_n_eff": round(min(x["n_eff"] for x in rows), 6),
            "n_eff_initial": round(base_neff, 6),
            "systemic_halt_steps": sum(1 for x in rows if x["systemic_halt"]),
            "enforcement_actions": sum(1 for m in log.messages() if m.kind == "action"),
            "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()},
        }
        explain = [
            {"en": f"N_eff ({r['n_eff_basis']}) starts at {base_neff:.2f} and falls to {outputs['min_n_eff']:.2f}; "
                   f"N_eff_min = {r['n_eff_min']:g} (declared: the corpus does not define it, F-007).",
             "ru": f"N_eff ({r['n_eff_basis']}) в начале {base_neff:.2f}, минимум {outputs['min_n_eff']:.2f}; "
                   f"N_eff_min = {r['n_eff_min']:g} (задан: в корпусе не определён, F-007)."},
            {"en": f"Null-output state in {len(nulls)} of {len(rows)} steps ({r['scope_reading']} reading); "
                   f"systemic halt by coverage in {outputs['systemic_halt_steps']} steps.",
             "ru": f"Нулевой вывод в {len(nulls)} из {len(rows)} шагов (прочтение {r['scope_reading']}); "
                   f"системная остановка по покрытию — в {outputs['systemic_halt_steps']} шагах."},
        ]
        if r["sybil_sources"]:
            plain = expected({**r, "sybil_sources": 0})[0]["n_eff"]
            explain.append({"en": f"Without the {r['sybil_sources']} Sybil sources N_eff would be {plain:.2f}.",
                            "ru": f"Без {r['sybil_sources']} Sybil-источников N_eff был бы {plain:.2f}."})
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"null_output_steps": outputs["null_output_steps"], "first_null_step": outputs["first_null_step"],
                "min_n_eff": outputs["min_n_eff"], "systemic_halt_steps": outputs["systemic_halt_steps"],
                "enforcement_actions": outputs["enforcement_actions"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "region_lost_global": {},
            "region_lost_regional_reading": {"scope_reading": "regional"},
            "n_eff_min_missing": {"n_eff_min": -1},
            "sybil_inflation": {"n_eff_basis": "sources", "sybil_sources": 40},
            "sybil_counted_by_owner": {"n_eff_basis": "owners", "sybil_sources": 40},
            "coverage_halt": {"regions": 4},
            "faulty_recovery": {"faults": ["fallback_authority", "manual_restart", "precedent"]},
            "resume_old_outputs": {"recovery_reading": "resume_outputs"},
            "inconsistency_window": {"loss_fraction": 0.0, "consistency_invalid_window": [20, 26]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"no_such_region": {"loss_region": 7}, "owners_exceed_sources": {"owners_per_region": 20},
                "fractional_window": {"loss_window": [1.5, 4]}}
