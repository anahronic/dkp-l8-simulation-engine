"""
UPGRADE LIFECYCLE module — DKP-4-UPGRADE-001: from proposal to activation and rollback.

Every proposal passes: definition (§3: presentation-only changes are not upgrades) → hard
constraints (§2: no axiom redefinition, no PTL rule change, nothing during an active Crisis; §4.1,
§4.5, §4.6 invariants) → completeness (§5, procedural rejection) → simulation and proof (§6: no
simulation, no upgrade) → anti-capture (§7: correlated proposals by IDENTITY linkage, lineage) →
approval and activation (§8: all simulations pass, no unresolved ERROR or Justice appeal, window
announced in advance, at least 30 DTI-Days between publication of final results and activation,
deterministic DTI-Day, a defined reversibility window, automatic log) → post-activation (§9:
automatic rollback, no stacking of fixes on a faulty version).

What the module does not decide:
  * who approves (UPGRADE §8 gives necessary conditions only; S1, open question Q-001): an
    activation is a declared request, checked against the conditions;
  * the "full post-crisis audit and stabilization period ... as defined by DKP-8-AUDIT-001" for
    upgrades touching Defense, Crisis, Identity or Justice: AUDIT defines none (finding F-020);
    such an upgrade after a crisis is held, and the check says UNKNOWN unless a period is declared;
  * simulation results, capture convergence and invariant effects are declared inputs (the lab
    cannot simulate an arbitrary protocol change); influence caps have no number (UNKNOWN).
Time unit: DTI-Day.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError
from lab.modules.time import canonical, dy_doy

COOLING_DAYS = 30                                               # UPGRADE §8 Post-Crisis Cooldown Rule
KINDS = ("formula", "threshold", "logic", "cross_layer", "presentation_only")
TARGETS = ("axioms", "ptl_rules", "defense", "crisis", "identity", "justice", "finance", "social", "upgrade_protocol")
COOLDOWN_LAYERS = ("defense", "crisis", "identity", "justice")
PROPOSAL_ITEMS = ("specification", "before_after", "impact_deltas", "failure_modes_rollback", "simulation_parameters")
THRESHOLDS = ("standard", "elevated", "highest")              # declared lab levels; the corpus defines no hierarchy (§2)
ANALYSES = ("stress_testing", "capture_resistance")           # §6
FAULTS = {
    "upgrade_in_crisis": "a proposal is accepted while a Crisis is active",
    "direct_patch_accepted": "a change submitted outside UPGRADE (direct patch) enters the system",
    "discretionary_tuning": "an operator's parameter tuning without specification or comparison is accepted",
    "skip_completeness": "an incomplete proposal is processed",
    "weaken_axiom_accepted": "a proposal weakening an axiom is accepted",
    "degrade_defense_accepted": "a proposal degrading Defense or Crisis effectiveness is accepted",
    "no_simulation": "an upgrade is approved without a passed simulation",
    "short_cooling": "activation comes less than 30 DTI-Days after publication of the final results",
    "activate_with_open_appeal": "activation while an ERROR or Justice appeal is unresolved",
    "unannounced": "activation without an announced window",
    "no_rollback": "post-activation deviation does not trigger rollback",
    "stack_fix": "a fix is activated on top of a faulty version instead of rolling it back",
    "ignore_correlation": "correlated proposals from linked initiators are not flagged",
    "presentation_as_upgrade": "a presentation-only change is run through the upgrade procedure",
    "threshold_as_cosmetic": "a threshold change is treated as a presentation change and skips the procedure",
    "results_only": "the simulation methodology is withheld (results only) and the upgrade is activated anyway",
    "erase_artifact": "the simulation record of a rolled-back upgrade is removed from the archive",
    "refuse_error_in_cooldown": "an ERROR procedure initiated during the post-crisis cooldown is refused",
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "accept_named_privilege": "a rule that names specific Subjects or groups is accepted",
    "self_upgrade_standard": "a modification of UPGRADE itself is evaluated at the standard threshold",
    "unverified_input_accepted": "an evaluation input without PTL verification is used",
    "vpi_removal_accepted": "a proposal removing the response path to Vectors of Physical Inevitability is accepted",
    "package_without_capture": "a simulation package without the capture-resistance analysis counts as passed",
}
PROPOSAL = {"type": "object", "fields": {
    "id": {"type": "str"},
    "submitted_day": {"type": "int", "min": 0, "max": 10 ** 6, "default": 0},
    "channel": {"type": "enum", "values": ["upgrade", "direct_patch", "operator_tuning"], "default": "upgrade"},
    "kind": {"type": "enum", "values": list(KINDS), "default": "threshold"},
    "targets": {"type": "list", "min_items": 1, "max_items": len(TARGETS), "items": {"type": "enum", "values": list(TARGETS)},
                "default": ["social"]},
    "missing_items": {"type": "list", "min_items": 0, "max_items": len(PROPOSAL_ITEMS),
                      "items": {"type": "enum", "values": list(PROPOSAL_ITEMS)}, "default": []},
    "weakens_axioms": {"type": "bool", "default": False},
    "degrades_defense_crisis": {"type": "bool", "default": False},
    "simulation_passed": {"type": "bool", "default": True},
    "stress_and_capture_tested": {"type": "bool", "default": True},
    "results_published_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 5},
    "methodology_published": {"type": "bool", "default": True},
    "initiator_link": {"type": "str", "default": "independent"},
    "capture_convergence": {"type": "bool", "default": False},
    "announced_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 20},
    "activation_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 40},
    "reversible_window_days": {"type": "int", "min": 0, "max": 3650, "default": 30},
    "deviation_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1},
    "fixes": {"type": "str", "default": "none"},
    "names_subjects": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "str"}, "default": []},
    "data_sources": {"type": "list", "min_items": 1, "max_items": 3, "items": {"type": "enum", "values": ["ptl_verified", "unverified", "forecast"]},
                     "default": ["ptl_verified"]},
    "removes_vpi_response": {"type": "bool", "default": False},
    "analyses": {"type": "list", "min_items": 0, "max_items": 2, "items": {"type": "enum", "values": list(ANALYSES)},
                 "default": list(ANALYSES)}}}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:05d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=k, decided_at=k if kind in ("decision", "action") else None,
                                  value={**value, "day": k, "dti": canonical(*dy_doy(r["start_dti_day"] + k))},
                                  provenance=tuple(prov), order=order[kind]))

    lo, hi = r["crisis_window"]
    crisis = lambda k: lo <= k < hi
    crisis_seen = hi > lo
    stab = r["stabilization_days"]
    appeals = [(a[0], a[1]) for a in r["open_appeals"]]
    state: Dict[str, Dict[str, Any]] = {}
    links: Dict[str, List[str]] = {}
    version = {"current": "v0", "stable": "v0"}
    for k in range(r["horizon_days"]):
        for p in r["proposals"]:
            pid = p["id"]
            if p["submitted_day"] == k:
                s = state.setdefault(pid, {"status": None})
                sub = put("observation", "UPGRADE", k, {"proposal": pid, "kind": p["kind"], "targets": p["targets"],
                                                        "initiator_link": p["initiator_link"], "fixes": p["fixes"]})
                s["msg"] = sub.event_id
                if (p["kind"] == "presentation_only" and "presentation_as_upgrade" not in faults) or                         (p["kind"] == "threshold" and "threshold_as_cosmetic" in faults):
                    s["status"] = "not_an_upgrade"
                    put("notice", "UPGRADE", k, {"proposal": pid, "status": "not an upgrade (§3): recorded by 'Last updated'"},
                        [sub.event_id])
                    continue
                reason = None
                if p["channel"] == "direct_patch" and "direct_patch_accepted" not in faults:
                    reason = "submitted outside UPGRADE: the only lawful mechanism of change (§0)"
                elif p["channel"] == "operator_tuning" and "discretionary_tuning" not in faults:
                    reason = "opaque or discretionary parameter tuning (§11)"
                elif crisis(k) and "upgrade_in_crisis" not in faults:
                    reason = "active Crisis (§2, §4.3, §11)"
                elif p["missing_items"] and "skip_completeness" not in faults:
                    reason = f"incomplete proposal (§5): missing {', '.join(p['missing_items'])}"
                elif ("axioms" in p["targets"] or p["weakens_axioms"]) and "weaken_axiom_accepted" not in faults:
                    reason = "touches Axiom A1/A2 (§2, §4.1)"
                elif "ptl_rules" in p["targets"]:
                    reason = "modifies Physical Truth Layer rules (§2)"
                elif p["degrades_defense_crisis"] and "degrade_defense_accepted" not in faults:
                    reason = "degrades Defense or Crisis (§4.5, §4.6)"
                elif p["removes_vpi_response"] and "vpi_removal_accepted" not in faults:
                    reason = "removes the response to PTL-confirmed Vectors of Physical Inevitability (§4.6)"
                elif p["names_subjects"] and "accept_named_privilege" not in faults:
                    reason = f"privileges specific Subjects or groups: {', '.join(p['names_subjects'])} (§11)"
                elif set(p["targets"]) & set(COOLDOWN_LAYERS) and crisis_seen and k >= hi and \
                        (stab < 0 or k < hi + stab):
                    reason = ("post-crisis audit and stabilization period not defined by AUDIT (F-020): held"
                              if stab < 0 else "within the declared post-crisis stabilization period")
                if reason:
                    s["status"] = "held" if "F-020" in reason else "rejected"
                    put("decision", "UPGRADE", k, {"proposal": pid, "status": s["status"], "reason": reason}, [sub.event_id])
                    continue
                s["status"] = "proposed"
                links.setdefault(p["initiator_link"], []).append(pid)
                if p["initiator_link"] != "independent" and len(links[p["initiator_link"]]) > 1 and \
                        "ignore_correlation" not in faults:
                    put("notice", "UPGRADE", k, {"proposal": pid, "correlated_with": links[p["initiator_link"]][:-1],
                                                 "via": "DKP-1-IDENTITY-001 linkage"}, [sub.event_id])
                if "upgrade_protocol" in p["targets"] or p["kind"] != "presentation_only":
                    lvl = "highest" if "upgrade_protocol" in p["targets"] and "self_upgrade_standard" not in faults else "standard"
                    put("notice", "UPGRADE", k, {"proposal": pid, "security_threshold": lvl}, [sub.event_id])
                put("notice", "UPGRADE", k, {"proposal": pid, "lineage": {"fixes": p["fixes"], "parent": version["current"]},
                                             "channel": p["channel"],
                                             "contents": [i for i in PROPOSAL_ITEMS if i not in p["missing_items"]]},
                    [sub.event_id])
            s = state.get(pid)
            if not s or s["status"] not in ("proposed", "active"):
                continue
            if s["status"] == "proposed" and p["results_published_day"] == k:
                inputs = [d for d in p["data_sources"] if d == "ptl_verified" or "unverified_input_accepted" in faults]
                done = [a for a in p["analyses"] if a != "capture_resistance" or "package_without_capture" not in faults]
                ok = (p["simulation_passed"] and p["stress_and_capture_tested"]
                      and (set(ANALYSES) <= set(done) or "package_without_capture" in faults)
                      and bool(inputs) and (all(d == "ptl_verified" for d in inputs) or "unverified_input_accepted" in faults))                     or "no_simulation" in faults
                put("notice", "SIMULATION", k, {"proposal": pid, "published": True,
                                                "methodology": p["methodology_published"] and "results_only" not in faults,
                                                "passed": p["simulation_passed"],
                                                "stress_and_capture": p["stress_and_capture_tested"],
                                                "analyses": done, "inputs": inputs or ["none admissible"],
                                                "inputs_refused": [d for d in p["data_sources"] if d not in inputs]}, [s["msg"]])
                if p["capture_convergence"]:
                    ok = False
                s["sim_ok"] = ok
                if not ok:
                    s["status"] = "rejected"
                    put("decision", "UPGRADE", k, {"proposal": pid, "status": "rejected",
                                                   "reason": "simulation or capture analysis failed (§6, §7)"}, [s["msg"]])
                    continue
            if s["status"] == "proposed" and p["announced_day"] == k:
                put("notice", "UPGRADE", k, {"proposal": pid, "activation_window_announced": p["activation_day"]}, [s["msg"]])
            if s["status"] == "proposed" and p["activation_day"] == k:
                why = []
                if not s.get("sim_ok"):
                    why.append("no passed and published simulation (§6)")
                if not p["methodology_published"] and "results_only" not in faults:
                    why.append("simulation methodology not published (§6)")
                if p["results_published_day"] < 0 or (k - p["results_published_day"] < COOLING_DAYS and "short_cooling" not in faults):
                    why.append(f"cooling-off: fewer than {COOLING_DAYS} DTI-Days since publication (§8)")
                if any(a <= k < b for a, b in appeals) and "activate_with_open_appeal" not in faults:
                    why.append("unresolved ERROR or Justice appeal (§8)")
                if not (0 <= p["announced_day"] < k) and "unannounced" not in faults:
                    why.append("activation window not announced in advance (§8)")
                if crisis(k):
                    why.append("active Crisis (§2)")
                if p["reversible_window_days"] <= 0:
                    why.append("no reversibility window defined (§8)")
                faulty = version["current"] != version["stable"]
                if p["fixes"] != "none" and faulty and "stack_fix" not in faults:
                    why.append("the version it fixes is faulty and must be rolled back first (§9)")
                if why:
                    s["status"] = "refused"
                    put("decision", "UPGRADE", k, {"proposal": pid, "status": "activation refused", "reasons": why}, [s["msg"]])
                    continue
                s["status"] = "active"
                parent = version["current"]
                version["current"] = pid
                version["stable_before"] = version["stable"]
                put("action", "UPGRADE", k, {"proposal": pid, "activated": True, "on_dti_day": r["start_dti_day"] + k,
                                             "reversible_until": k + p["reversible_window_days"], "parent": parent,
                                             "logged": True}, [s["msg"]])
                if p["deviation_day"] < 0:
                    version["stable"] = pid
            if s["status"] == "active" and p["deviation_day"] == k:
                put("observation", "MONITOR", k, {"proposal": pid, "deviation": "unexpected impact deviation"}, [s["msg"]])
                if "no_rollback" not in faults and "stack_fix" not in faults:
                    back = version.get("stable_before", "v0")
                    put("action", "UPGRADE", k, {"proposal": pid, "rollback_to": back, "automatic": True}, [s["msg"]])
                    s["status"] = "rolled_back"
                    version["current"] = back
                    version["stable"] = back
        for d in r["cooldown_error_initiations"]:
            if d == k:
                within = crisis_seen and k >= hi and (stab < 0 or k < hi + stab)
                put("notice", "ERROR", k, {"error_initiated_by": "Subject", "trigger": "suspected regression",
                                           "during_cooldown": within,
                                           "accepted": "refuse_error_in_cooldown" not in faults or not within})
    # UPGRADE §10: every upgrade artifact archived permanently, with an anchor reference, auditable under AUDIT
    arts = [m for m in log.messages() if m.source in ("UPGRADE", "SIMULATION")]
    gone = []
    if "erase_artifact" in faults:
        rolled = {m.value["proposal"] for m in arts if m.value.get("rollback_to")}
        gone = [m.event_id for m in arts if m.source == "SIMULATION" and m.value["proposal"] in rolled][:1] or \
            [m.event_id for m in arts if m.source == "SIMULATION"][:1]
    put("notice", "ARCHIVE", r["horizon_days"] - 1, {"artifacts": [m.event_id for m in arts if m.event_id not in gone],
                                                       "removed": gone, "permanent": True,
                                                       "ptl_anchor": "lab digest of the PTL time index (declared)",
                                                       "audit": "DKP-8-AUDIT-001 §6 (traces and recomputation)"})
    return log, {pid: s["status"] for pid, s in state.items()}, dict(version)


def core_checks(r: Dict[str, Any], msgs) -> List[CheckResult]:
    """Clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)
    prop = {p["id"]: p for p in r["proposals"]}
    lineage = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and "lineage" in m.value}   # went on to evaluation
    named = [pid for pid, p in prop.items() if p["names_subjects"] and p["kind"] != "presentation_only"]
    out.append(v("UPGRADE-11-04", "no_named_privilege", [f"{x}: names {prop[x]['names_subjects']}" for x in named if x in lineage],
                 f"{len(named)} proposal(s) naming specific Subjects or groups, none admitted", "{n} rules naming Subjects or groups admitted")
               if named else na("UPGRADE-11-04", "no_named_privilege", "rules naming Subjects", "no proposal names Subjects or groups"))
    selfp = [m for m in msgs if m.source == "UPGRADE" and "security_threshold" in m.value
             and "upgrade_protocol" in prop[m.value["proposal"]]["targets"]]
    out.append(v("UPGRADE-2-06", "self_upgrade_highest_threshold", [f"{m.value['proposal']}: {m.value['security_threshold']}" for m in selfp
                                                                    if m.value["security_threshold"] != THRESHOLDS[-1]],
                 f"{len(selfp)} modification(s) of UPGRADE itself, each at the highest declared threshold ({THRESHOLDS[-1]})",
                 "{n} self-modifications below the highest threshold") if selfp else
               na("UPGRADE-2-06", "self_upgrade_highest_threshold", "modifications of UPGRADE", "none proposed"))
    sims = [m for m in msgs if m.source == "SIMULATION" and "inputs" in m.value]
    out.append(v("UPGRADE-4.2-01", "ptl_verified_inputs", [f"{m.value['proposal']}: {m.value['inputs']}" for m in sims
                                                           if set(m.value["inputs"]) - {"ptl_verified", "none admissible"}],
                 f"{len(sims)} evaluation(s), each on PTL-verified data only (refused inputs recorded)",
                 "{n} evaluations using data without PTL verification") if sims else
               na("UPGRADE-4.2-01", "ptl_verified_inputs", "evaluations", "no simulation published"))
    vpi = [pid for pid, p in prop.items() if p["removes_vpi_response"]]
    out.append(v("UPGRADE-4.6-01", "vpi_response_kept", [x for x in vpi if x in lineage],
                 f"{len(vpi)} proposal(s) removing the declared VPI response path, none admitted", "{n} such proposals admitted")
               if vpi else na("UPGRADE-4.6-01", "vpi_response_kept", "VPI response path", "no proposal removes it"))
    act = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and m.value.get("activated")}
    pk = {m.value["proposal"]: m.value.get("analyses", []) for m in sims}
    out.append(v("UPGRADE-6-02", "package_has_both_analyses", [f"{x}: {pk.get(x)}" for x in sorted(act) if not set(ANALYSES) <= set(pk.get(x, []))],
                 f"{len(act)} activated upgrade(s), each with a simulation package containing stress-testing and capture-resistance "
                 "analysis", "{n} activations on a package missing an analysis") if act else
               na("UPGRADE-6-02", "package_has_both_analyses", "activated upgrades", "none activated"))
    return out


def returned_checks(r: Dict[str, Any], msgs) -> List[CheckResult]:
    """Provisions returned to work after the reading of the Codex-draft open points (review of checkpoint 6)."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})
    arch = [m for m in msgs if m.source == "ARCHIVE"]
    arts = [m for m in msgs if m.source in ("UPGRADE", "SIMULATION")]
    kept = set(arch[0].value["artifacts"]) if arch else set()
    bad = [f"{m.event_id}: not archived" for m in arts if m.event_id not in kept]
    bad += [] if arch and arch[0].value["permanent"] and arch[0].value["ptl_anchor"] else ["archive not permanent or not anchored"]
    out.append(v("UPGRADE-10-01", "artifacts_archived", bad,
                 f"all {len(arts)} upgrade artifacts archived permanently with an anchor reference and an audit route",
                 "{n} upgrade artifacts missing from the permanent archive"))
    P = {p["id"]: p for p in r["proposals"]}
    act = [m.value["proposal"] for m in msgs if m.source == "UPGRADE" and m.value.get("activated")]
    lin = {m.value["proposal"]: m.value for m in msgs if m.source == "UPGRADE" and "lineage" in m.value}
    lin_id = {m.value["proposal"]: m.event_id for m in msgs if m.source == "UPGRADE" and "lineage" in m.value}
    sim = {m.value["proposal"]: m.value for m in msgs if m.source == "SIMULATION"}
    ann = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and "activation_window_announced" in m.value}
    bad = []
    for pid in act:
        if set(PROPOSAL_ITEMS) - set(lin.get(pid, {}).get("contents", [])):
            bad.append(f"{pid}: specification incomplete")
        if not sim.get(pid, {}).get("methodology"):
            bad.append(f"{pid}: simulation methodology not public")
        if pid not in ann:
            bad.append(f"{pid}: not announced")
        if lin_id.get(pid) not in kept:
            bad.append(f"{pid}: not archived for audit")
    out.append(v("UPGRADE-4.4-01", "visible_specified_auditable", bad,
                 f"{len(act)} activated upgrade(s), each publicly announced with published methodology, a complete §5 "
                 "specification and an archived trace", "{n} upgrades not visible, not specified or not auditable") if act else
               CheckResult("UPGRADE-4.4-01", "visible_specified_auditable", NOT_APPLICABLE, "activated upgrades",
                           applicability="no upgrade activated"))
    inits = [m for m in msgs if m.source == "ERROR" and m.value.get("error_initiated_by") and m.value.get("during_cooldown")]
    out.append(v("UPGRADE-Post-CrisisCooldownRule-03", "error_open_in_cooldown", [m.event_id for m in inits if not m.value["accepted"]],
                 f"{len(inits)} ERROR initiation(s) by Subjects during the cooldown accepted",
                 "{n} ERROR initiations refused during the cooldown") if inits else
               CheckResult("UPGRADE-Post-CrisisCooldownRule-03", "error_open_in_cooldown", NOT_APPLICABLE, "ERROR initiations",
                           applicability="none during a post-crisis cooldown"))
    return out


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

    P = {p["id"]: p for p in r["proposals"]}
    lo, hi = r["crisis_window"]
    acts = {m.value["proposal"]: m for m in msgs if m.source == "UPGRADE" and m.value.get("activated")}
    accepted = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and "lineage" in m.value}
    rejected = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and m.value.get("status") == "rejected"}
    upgrades = [p for p in r["proposals"] if p["kind"] != "presentation_only"]
    # §0 only lawful mechanism; §5 contents of an admitted proposal; §11 no opaque or discretionary tuning
    adm = [m.value for m in msgs if m.source == "UPGRADE" and "lineage" in m.value]
    out.append(v("UPGRADE-0-01", "only_lawful_mechanism", [f"{x['proposal']}: via {x['channel']}" for x in adm if x["channel"] != "upgrade"],
                 f"{len(adm)} change(s) admitted, all through the UPGRADE procedure; changes by other routes refused",
                 "{n} changes admitted outside UPGRADE"))
    out.append(v("UPGRADE-5-01", "proposal_contents", [f"{x['proposal']}: missing {sorted(set(PROPOSAL_ITEMS) - set(x['contents']))}"
                                                       for x in adm if set(x["contents"]) != set(PROPOSAL_ITEMS)],
                 f"{len(adm)} admitted proposal(s) include specification, before/after comparison, impact deltas, failure modes "
                 "with rollback and simulation parameters", "{n} admitted proposals without the §5 contents") if adm else
               na("UPGRADE-5-01", "proposal_contents", "admitted proposals", "no proposal admitted"))
    out.append(v("UPGRADE-11-02", "no_opaque_tuning",
                 [f"{x['proposal']}: {x['channel']}" for x in adm if x["channel"] == "operator_tuning"] +
                 [f"{x['proposal']}: without {', '.join(sorted({'specification', 'before_after'} - set(x['contents'])))}" for x in adm
                  if {"specification", "before_after"} - set(x["contents"])],
                 "no parameter changed by an operator's discretion or without specification and before/after comparison",
                 "{n} opaque or discretionary tunings"))
    # §3 presentation-only changes
    pres = [p["id"] for p in r["proposals"] if p["kind"] == "presentation_only"]
    if pres:
        bad = [pid for pid in pres if pid in accepted or pid in acts]
        for rid in ("UPGRADE-3-02", "UPGRADE-12-03"):
            out.append(v(rid, "presentation_not_upgrade", bad, "presentation-only changes were recorded without the upgrade procedure",
                         "{n} presentation-only changes run as upgrades"))
    else:
        for rid in ("UPGRADE-3-02", "UPGRADE-12-03"):
            out.append(na(rid, "presentation_not_upgrade", "presentation-only changes", "none proposed"))
    # §3 definition: a change of formulas, thresholds, logic or cross-layer rules is an Upgrade
    cosmetic = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and "not an upgrade" in str(m.value.get("status", ""))}
    out.append(v("UPGRADE-3-01", "upgrade_definition", [p["id"] for p in upgrades if p["id"] in cosmetic],
                 f"{len(upgrades)} changes of formulas, thresholds, logic or cross-layer rules entered the upgrade procedure",
                 "{n} such changes treated as presentation-only") if upgrades else
               na("UPGRADE-3-01", "upgrade_definition", "upgrades", "only presentation-only changes"))
    # §2 / §4.3 / §11: nothing during an active Crisis
    if hi > lo:
        bad = [p["id"] for p in upgrades if lo <= p["submitted_day"] < hi and p["id"] in accepted]
        bad += [pid for pid, m in acts.items() if lo <= m.arrived_at < hi]
        for rid in ("UPGRADE-4.3-01", "UPGRADE-11-01"):
            out.append(v(rid, "no_crisis_upgrade", bad, "no upgrade proposed or activated during the active Crisis",
                         "{n} upgrades during the Crisis"))
    else:
        for rid in ("UPGRADE-4.3-01", "UPGRADE-11-01"):
            out.append(na(rid, "no_crisis_upgrade", "upgrades during a Crisis", "no Crisis declared"))
    incomplete = [p["id"] for p in upgrades if p["missing_items"]]
    if incomplete:
        out.append(v("UPGRADE-5-02", "incomplete_rejected", [pid for pid in incomplete if pid in accepted],
                     "incomplete proposals rejected procedurally", "{n} incomplete proposals processed"))
    else:
        out.append(na("UPGRADE-5-02", "incomplete_rejected", "incomplete proposals", "every proposal is complete"))
    ax = [p["id"] for p in upgrades if p["weakens_axioms"] or "axioms" in p["targets"]]
    if ax:
        for rid in ("UPGRADE-4.1-01", "UPGRADE-2-03"):
            out.append(v(rid, "axioms_untouched", [pid for pid in ax if pid in accepted],
                         "proposals touching Axiom A1/A2 rejected", "{n} axiom-touching proposals accepted"))
    else:
        for rid in ("UPGRADE-4.1-01", "UPGRADE-2-03"):
            out.append(na(rid, "axioms_untouched", "axiom changes", "no proposal touches the axioms"))
    ptl = [p["id"] for p in upgrades if "ptl_rules" in p["targets"]]
    if ptl:
        out.append(v("UPGRADE-2-04", "ptl_rules_untouched", [pid for pid in ptl if pid in accepted],
                     "proposals modifying PTL rules rejected", "{n} PTL-rule changes accepted"))
    else:
        out.append(na("UPGRADE-2-04", "ptl_rules_untouched", "PTL rule changes", "no proposal targets PTL rules"))
    deg = [p["id"] for p in upgrades if p["degrades_defense_crisis"]]
    if deg:
        for rid in ("UPGRADE-4.5-01", "UPGRADE-4.6-02"):
            out.append(v(rid, "no_degradation", [pid for pid in deg if pid in accepted],
                         "proposals degrading Defense or Crisis (declared effect) rejected",
                         "{n} degrading proposals accepted"))
    else:
        for rid in ("UPGRADE-4.5-01", "UPGRADE-4.6-02"):
            out.append(na(rid, "no_degradation", "Defense/Crisis degradation", "no proposal declares a degradation"))
    # §6: no simulation, no upgrade
    if acts:
        bad = [pid for pid in acts if not (P[pid]["simulation_passed"] and P[pid]["stress_and_capture_tested"]
                                           and P[pid]["results_published_day"] >= 0)]
        for rid, chk in (("UPGRADE-6-01", "simulation_before_approval"), ("UPGRADE-11-03", "no_bypass")):
            out.append(v(rid, chk, bad, "every activated upgrade passed a published simulation, stress test and capture analysis",
                         "{n} upgrades activated without a passed simulation"))
        pub = {m.value["proposal"]: m.value for m in msgs if m.source == "SIMULATION" and m.value.get("published")}
        out.append(v("UPGRADE-6-03", "public_results_methodology",
                     [pid for pid in acts if pid not in pub or not pub[pid]["methodology"]],
                     "every activated upgrade published its simulation results and methodology",
                     "{n} upgrades activated without published results and methodology"))
        bad = [pid for pid in acts if acts[pid].arrived_at - P[pid]["results_published_day"] < COOLING_DAYS]
        out.append(v("UPGRADE-Post-CrisisCooldownRule-02", "cooling_off_30", bad,
                     f"at least {COOLING_DAYS} DTI-Days between publication of final results and every activation",
                     "{n} activations inside the cooling-off period"))
        bad = [pid for pid in acts if any(a <= acts[pid].arrived_at < b for a, b in r["open_appeals"])
               or not (0 <= P[pid]["announced_day"] < acts[pid].arrived_at) or not P[pid]["simulation_passed"]]
        out.append(v("UPGRADE-8-01", "activation_conditions", bad,
                     "activations only with passed simulations, no unresolved appeal and a window announced in advance "
                     "(necessary conditions; who decides is open, Q-001)", "{n} activations without the §8 conditions"))
        bad = [pid for pid, m in acts.items() if m.value.get("on_dti_day") != r["start_dti_day"] + m.arrived_at
               or not m.value.get("logged")]
        for rid, chk in (("UPGRADE-Post-CrisisCooldownRule-04", "deterministic_day"),
                         ("UPGRADE-Post-CrisisCooldownRule-06", "logged")):
            out.append(v(rid, chk, bad, "activation on a deterministic DTI-Day, logged automatically", "{n} activations not logged"))
        bad = [pid for pid, m in acts.items() if m.value.get("reversible_until", -1) <= m.arrived_at]
        out.append(v("UPGRADE-Post-CrisisCooldownRule-05", "reversible_window", bad,
                     "every activation declares a reversibility window (its length is not defined by the corpus)",
                     "{n} activations without a reversibility window"))
    else:
        for rid, chk in (("UPGRADE-6-01", "simulation_before_approval"), ("UPGRADE-11-03", "no_bypass"),
                         ("UPGRADE-Post-CrisisCooldownRule-02", "cooling_off_30"), ("UPGRADE-8-01", "activation_conditions"),
                         ("UPGRADE-Post-CrisisCooldownRule-04", "deterministic_day"),
                         ("UPGRADE-Post-CrisisCooldownRule-06", "logged"),
                         ("UPGRADE-Post-CrisisCooldownRule-05", "reversible_window"), ("UPGRADE-6-03", "public_results_methodology")):
            out.append(na(rid, chk, "activation", "no upgrade activated"))
    # post-crisis stabilization (F-020)
    layered = [p for p in upgrades if set(p["targets"]) & set(COOLDOWN_LAYERS) and hi > lo and p["submitted_day"] >= hi]
    if layered and r["stabilization_days"] < 0:
        out.append(CheckResult("UPGRADE-Post-CrisisCooldownRule-01", "post_crisis_stabilization", UNKNOWN,
                               f"{len(layered)} proposals touch Defense, Crisis, Identity or Justice after a Crisis; the "
                               "'full post-crisis audit and stabilization period' is 'as defined by DKP-8-AUDIT-001', which "
                               "defines none (F-020); the lab holds them"))
    elif layered:
        bad = [p["id"] for p in layered if (p["id"] in accepted and p["submitted_day"] < hi + r["stabilization_days"])
               or (p["id"] in acts and acts[p["id"]].arrived_at < hi + r["stabilization_days"])]
        out.append(v("UPGRADE-Post-CrisisCooldownRule-01", "post_crisis_stabilization", bad,
                     f"no Defense/Crisis/Identity/Justice upgrade within the declared {r['stabilization_days']}-day stabilization",
                     "{n} layered upgrades inside the stabilization period"))
    else:
        out.append(na("UPGRADE-Post-CrisisCooldownRule-01", "post_crisis_stabilization", "post-crisis stabilization",
                      "no layered proposal after a Crisis"))
    # §7 anti-capture
    groups: Dict[str, List[str]] = {}
    for p in upgrades:
        if p["id"] in accepted and p["initiator_link"] != "independent":
            groups.setdefault(p["initiator_link"], []).append(p["id"])
    corr = [ids for ids in groups.values() if len(ids) > 1]
    if corr:
        flagged = {m.value["proposal"] for m in msgs if m.source == "UPGRADE" and "correlated_with" in m.value}
        bad = [pid for ids in corr for pid in ids[1:] if pid not in flagged]
        out.append(v("UPGRADE-7-02", "correlation_detected", bad,
                     "proposals from IDENTITY-linked initiators flagged as correlated", "{n} correlated proposals not flagged"))
    else:
        out.append(na("UPGRADE-7-02", "correlation_detected", "correlated proposals", "no linked initiators"))
    lin = [pid for pid in accepted if not any(m.source == "UPGRADE" and m.value.get("proposal") == pid and "lineage" in m.value
                                              for m in msgs)]
    out.append(v("UPGRADE-7-04", "lineage", lin, "every accepted proposal records its lineage (parent version, fixes)",
                 "{n} proposals without lineage"))
    conv = [p["id"] for p in upgrades if p["capture_convergence"]]
    if conv:
        out.append(v("UPGRADE-7-03", "micro_upgrade_capture", [pid for pid in conv if pid in acts],
                     "proposals declared as converging toward capture were not activated (convergence is a declared input)",
                     "{n} converging proposals activated"))
    else:
        out.append(CheckResult("UPGRADE-7-03", "micro_upgrade_capture", UNKNOWN,
                               "no measure of 'cumulative micro-upgrades converging toward capture' is defined; "
                               "convergence can only be declared"))
    out.append(CheckResult("UPGRADE-7-01", "influence_caps", UNKNOWN,
                           "'caps on influence over upgrade initiation' have no value in the corpus"))
    # §9 rollback
    dev = [p for p in upgrades if p["deviation_day"] >= 0 and p["id"] in acts and p["deviation_day"] < r["horizon_days"]]
    if dev:
        rb = {m.value["proposal"]: m for m in msgs if m.source == "UPGRADE" and "rollback_to" in m.value}
        bad = [p["id"] for p in dev if p["id"] not in rb or rb[p["id"]].arrived_at != p["deviation_day"]]
        for rid, chk in (("UPGRADE-9-01", "automatic_rollback"), ("UPGRADE-9-03", "rollback_priority")):
            out.append(v(rid, chk, bad, "post-activation deviation rolled back automatically on the day it was detected",
                         "{n} deviations without rollback"))
        faulty = {p["id"]: (p["deviation_day"], rb.get(p["id"])) for p in dev}
        bad = []
        for pid, m in acts.items():
            f = P[pid]["fixes"]
            if f in faulty and faulty[f][0] <= m.arrived_at and (faulty[f][1] is None or faulty[f][1].arrived_at > m.arrived_at):
                bad.append(pid)
        out.append(v("UPGRADE-9-02", "no_stacking", bad, "no fix activated on top of a faulty, not rolled-back version",
                     "{n} fixes stacked on a faulty version"))
    else:
        for rid, chk in (("UPGRADE-9-01", "automatic_rollback"), ("UPGRADE-9-03", "rollback_priority"),
                         ("UPGRADE-9-02", "no_stacking")):
            out.append(na(rid, chk, "rollback", "no post-activation deviation"))
    # §12 edition dating of the pinned corpus
    from lab.core.registry import catalog
    docs = [d for d in catalog()["documents"] if d["kind"] in ("protocol", "addendum", "appendix", "codex")]
    bad = [d["id"] for d in docs if not d.get("last_updated") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["last_updated"])]
    out.append(v("UPGRADE-12-04", "edition_dated", bad,
                 f"all {len(docs)} registered documents of the pinned corpus carry a 'Last updated' date (the glossary is "
                 "not counted: whether it is a 'DKP document' is not said)", "{n} documents without an edition date"))
    return out


IMPLEMENTS = {
    # clear parts of provisions whose open point remains (reading record, partial_check; review КТ7-GPT-01)
    "UPGRADE-11-04": ("no_named_privilege", "PARTIAL", "Clear part only: no rule naming specific Subjects or groups; unequal effects stay open."),
    "UPGRADE-2-06": ("self_upgrade_highest_threshold", "PARTIAL", "Clear part only: the highest of the declared levels; the corpus defines no hierarchy."),
    "UPGRADE-4.2-01": ("ptl_verified_inputs", "PARTIAL", "Clear part only: evaluation data verified by PTL; whether simulations qualify stays open."),
    "UPGRADE-4.6-01": ("vpi_response_kept", "PARTIAL", "Clear part only: a declared removal of the VPI response path is refused; a model of response capability stays open."),
    "UPGRADE-6-02": ("package_has_both_analyses", "PARTIAL", "Clear part only: both analyses in the package; coverage and adequacy standards stay open."),
    "UPGRADE-3-02": ("presentation_not_upgrade", "IMPLEMENTED", None),
    "UPGRADE-3-01": ("upgrade_definition", "PARTIAL", "The kind of change is declared."),
    "UPGRADE-6-03": ("public_results_methodology", "PARTIAL", "Publication is a declared event."),
    "UPGRADE-12-03": ("presentation_not_upgrade", "IMPLEMENTED", None),
    "UPGRADE-4.3-01": ("no_crisis_upgrade", "PARTIAL", "Crisis only; 'urgency' and 'fear' are not measurable."),
    "UPGRADE-11-01": ("no_crisis_upgrade", "IMPLEMENTED", None),
    "UPGRADE-5-02": ("incomplete_rejected", "IMPLEMENTED", None),
    "UPGRADE-0-01": ("only_lawful_mechanism", "PARTIAL", "Other routes are declared channels of a proposal."),
    "UPGRADE-5-01": ("proposal_contents", "PARTIAL", "The contents are declared per proposal (missing_items)."),
    "UPGRADE-11-02": ("no_opaque_tuning", "PARTIAL", "Discretionary tuning is a declared channel."),
    # returned to work after the reading of the Codex-draft open points (review of checkpoint 6)
    "UPGRADE-10-01": ("artifacts_archived", "PARTIAL", "Archive and audit route are recorded; the PTL anchor is a declared reference (no evidence contract, cf. EXIT-5-02)."),
    "UPGRADE-4.4-01": ("visible_specified_auditable", "PARTIAL", "Visibility = announcement and published methodology; specification = §5 contents; audit = archived trace."),
    "UPGRADE-Post-CrisisCooldownRule-03": ("error_open_in_cooldown", "PARTIAL", "ERROR initiations are declared events; the cooldown end is declared (F-020)."),
    "UPGRADE-4.1-01": ("axioms_untouched", "PARTIAL", "The effect on the axioms is a declared property of the proposal."),
    "UPGRADE-2-03": ("axioms_untouched", "PARTIAL", "The effect on the axioms is a declared property of the proposal."),
    "UPGRADE-2-04": ("ptl_rules_untouched", "PARTIAL", "Targets are declared."),
    "UPGRADE-4.5-01": ("no_degradation", "PARTIAL", "Degradation is declared; the lab cannot measure trigger sensitivity of an arbitrary change."),
    "UPGRADE-4.6-02": ("no_degradation", "PARTIAL", "Degradation is declared."),
    "UPGRADE-6-01": ("simulation_before_approval", "PARTIAL", "Simulation results are declared inputs."),
    "UPGRADE-11-03": ("no_bypass", "PARTIAL", "Simulation and cooling-off; audit is not modelled."),
    "UPGRADE-Post-CrisisCooldownRule-01": ("post_crisis_stabilization", "PARTIAL", "AUDIT defines no stabilization period (F-020): UNKNOWN unless declared."),
    "UPGRADE-Post-CrisisCooldownRule-02": ("cooling_off_30", "IMPLEMENTED", None),
    "UPGRADE-Post-CrisisCooldownRule-04": ("deterministic_day", "IMPLEMENTED", None),
    "UPGRADE-Post-CrisisCooldownRule-05": ("reversible_window", "PARTIAL", "The length of the window is not defined; only its existence is checked."),
    "UPGRADE-Post-CrisisCooldownRule-06": ("logged", "IMPLEMENTED", None),
    "UPGRADE-8-01": ("activation_conditions", "PARTIAL", "Necessary conditions only; who approves is open (Q-001)."),
    "UPGRADE-7-01": ("influence_caps", "PARTIAL", "No cap value in the corpus: UNKNOWN."),
    "UPGRADE-7-02": ("correlation_detected", "IMPLEMENTED", None),
    "UPGRADE-7-03": ("micro_upgrade_capture", "PARTIAL", "No convergence measure: declared input or UNKNOWN."),
    "UPGRADE-7-04": ("lineage", "IMPLEMENTED", None),
    "UPGRADE-9-01": ("automatic_rollback", "IMPLEMENTED", None),
    "UPGRADE-9-02": ("no_stacking", "IMPLEMENTED", None),
    "UPGRADE-9-03": ("rollback_priority", "PARTIAL", "Observed as rollback on the day of detection."),
    "UPGRADE-12-04": ("edition_dated", "PARTIAL", "Checked on the pinned corpus files, not on the published site."),
}


class UpgradeLifecycleModule(LabModule):
    id = "upgrade_lifecycle"
    version = "1.3.0"
    title = {"en": "Upgrade lifecycle (UPGRADE)", "ru": "Жизненный цикл изменения (UPGRADE)"}
    summary = {"en": "Proposals to change the protocols: which are rejected and why, when may one be activated, and is a "
                     "faulty one rolled back rather than patched?",
               "ru": "Предложения изменить протоколы: какие отклоняются и почему, когда можно активировать, откатывается "
                     "ли неудачное изменение вместо латания?"}
    protocols = ["DKP-4-UPGRADE-001", "DKP-8-SIMULATION-001", "DKP-4-CRISIS-001", "DKP-8-AUDIT-001"]
    example_order = ["ordinary_upgrade", "rejections", "deviation_and_rollback", "after_crisis_layered",
                     "after_crisis_declared_stabilization", "correlated_initiators", "presentation_only",
                     "activation_refused_cooling", "faulty_upgrades"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_upgrade_lifecycle_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-UP-1", "source": "hypothesis", "text": {
            "en": "Simulation results, stress and capture analysis, effects on axioms and on Defense/Crisis are declared per "
                  "proposal; the lab does not simulate an arbitrary protocol change.",
            "ru": "Результаты симуляции, стресс-тест и анализ захвата, влияние на аксиомы и на Defense/Crisis объявляются для "
                  "каждого предложения; лаборатория не симулирует произвольное изменение протокола."}},
        {"id": "H-UP-2", "source": "hypothesis", "text": {
            "en": "Activation is a declared request on a DTI-Day; the module checks the necessary conditions of §8 and never "
                  "decides who approves (Q-001).",
            "ru": "Активация — объявленный запрос на DTI-Day; модуль проверяет необходимые условия §8 и не решает, кто "
                  "одобряет (Q-001)."}},
        {"id": "H-UP-3", "source": "missing", "text": {
            "en": "Post-crisis audit and stabilization period: 'as defined by DKP-8-AUDIT-001', which defines none (F-020). "
                  "-1 = undefined: proposals touching Defense, Crisis, Identity or Justice after a Crisis are held.",
            "ru": "Пост-кризисный аудит и период стабилизации: 'as defined by DKP-8-AUDIT-001', где его нет (F-020). "
                  "-1 = не определён: предложения о Defense, Crisis, Identity, Justice после кризиса удерживаются."}},
    ]
    inputs = {
        "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                          "label": {"en": "DTI-Day of day 0", "ru": "DTI-Day дня 0"}},
        "horizon_days": {"type": "int", "min": 2, "max": 2000, "default": 120, "unit": "day", "source": "user",
                         "label": {"en": "Days", "ru": "Дней"}},
        "proposals": {"type": "list", "min_items": 1, "max_items": 12, "items": PROPOSAL, "source": "user",
                      "default": [{**{k: f["default"] for k, f in PROPOSAL["fields"].items() if "default" in f}, "id": "u1"},
                                  {**{k: f["default"] for k, f in PROPOSAL["fields"].items() if "default" in f}, "id": "u2",
                                   "channel": "direct_patch", "submitted_day": 1},
                                  {**{k: f["default"] for k, f in PROPOSAL["fields"].items() if "default" in f}, "id": "u3",
                                   "channel": "operator_tuning", "submitted_day": 2}],
                      "label": {"en": "Proposals (H-UP-1)", "ru": "Предложения (H-UP-1)"}},
        "crisis_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [0, 0], "unit": "day", "source": "user",
                          "label": {"en": "Active Crisis from/to day", "ru": "Активный кризис с/до дня"}},
        "stabilization_days": {"type": "int", "min": -1, "max": 3650, "default": -1, "unit": "day", "source": "missing",
                               "label": {"en": "Post-crisis stabilization (-1: undefined, F-020; H-UP-3)",
                                         "ru": "Стабилизация после кризиса (-1: не определена, F-020)"}},
        "open_appeals": {"type": "list", "min_items": 0, "max_items": 20,
                         "items": {"type": "pair", "min": 0, "max": 10 ** 6}, "default": [], "source": "user",
                         "label": {"en": "Unresolved ERROR/Justice appeals from/to day", "ru": "Незакрытые апелляции с/до дня"}},
        "cooldown_error_initiations": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "int", "min": 0, "max": 10 ** 6},
                                       "default": [], "unit": "day", "source": "user",
                                       "label": {"en": "ERROR procedures initiated by Subjects on days",
                                                 "ru": "Процедуры ERROR, начатые Субъектами, в дни"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [x["id"] for x in r["proposals"]]
        if len(set(ids)) != len(ids):
            p.append("input.proposals: repeated id")
        for x in ids:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                p.append(f"input.proposals: id {x!r} must be lowercase letters, digits or _ (at most 24)")
        for x in r["proposals"]:
            if x["fixes"] != "none" and x["fixes"] not in ids:
                p.append(f"input.proposals: {x['id']} fixes unknown proposal {x['fixes']}")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x["initiator_link"]):
                p.append(f"input.proposals: initiator_link {x['initiator_link']!r}")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if not all(float(t).is_integer() for t in r["crisis_window"]) or \
                not all(float(t).is_integer() for a in r["open_appeals"] for t in a):
            p.append("input: windows in whole days")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, status, version = run(r)
        res = checks(r, log) + returned_checks(r, log.messages()) + core_checks(r, log.messages())
        msgs = log.messages()
        decisions = [m.value for m in msgs if m.source == "UPGRADE" and m.kind in ("decision", "action")]
        outputs = {"status": status, "version": version, "decisions": decisions,
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = []
        for d in decisions:
            what = d.get("status") or ("activated" if d.get("activated") else f"rolled back to {d.get('rollback_to')}")
            why = d.get("reason") or "; ".join(d.get("reasons", []))
            e.append({"en": f"Day {d['day']}: {d['proposal']} — {what}" + (f" ({why})" if why else "") + ".",
                      "ru": f"День {d['day']}: {d['proposal']} — {what}" + (f" ({why})" if why else "") + "."})
        return ModuleResult(outputs=outputs, checks=res, explain=e[:40])

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        st = list(outputs["status"].values())
        return {"activated": sum(1 for s in st if s == "active"), "rolled_back": sum(1 for s in st if s == "rolled_back"),
                "rejected_or_refused": sum(1 for s in st if s in ("rejected", "refused")),
                "current_version": outputs["version"]["current"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "ordinary_upgrade": {},
            "rejections": {"proposals": [
                {"id": "incomplete", "missing_items": ["before_after"]},
                {"id": "axiom", "targets": ["axioms"]},
                {"id": "ptl", "targets": ["ptl_rules"]},
                {"id": "weaker_defense", "targets": ["defense"], "degrades_defense_crisis": True},
                {"id": "failed_sim", "simulation_passed": False},
                {"id": "ok", "submitted_day": 3}]},
            "deviation_and_rollback": {"proposals": [
                {"id": "u1", "deviation_day": 50},
                {"id": "fix", "submitted_day": 52, "results_published_day": 55, "announced_day": 60, "activation_day": 90,
                 "fixes": "u1"}]},
            "after_crisis_layered": {"crisis_window": [0, 10], "proposals": [
                {"id": "justice_change", "submitted_day": 12, "targets": ["justice"], "results_published_day": 15,
                 "announced_day": 20, "activation_day": 50},
                {"id": "social_change", "submitted_day": 12, "results_published_day": 15, "announced_day": 20,
                 "activation_day": 50}]},
            "after_crisis_declared_stabilization": {"crisis_window": [0, 10], "stabilization_days": 20, "proposals": [
                {"id": "early", "submitted_day": 12, "targets": ["justice"], "results_published_day": 15,
                 "announced_day": 20, "activation_day": 50},
                {"id": "later", "submitted_day": 31, "targets": ["justice"], "results_published_day": 35,
                 "announced_day": 40, "activation_day": 70}]},
            "correlated_initiators": {"proposals": [
                {"id": "a", "initiator_link": "group_x"},
                {"id": "b", "submitted_day": 2, "initiator_link": "group_x", "results_published_day": 6, "activation_day": 45}]},
            "presentation_only": {"proposals": [{"id": "typo", "kind": "presentation_only"}]},
            "capture_and_scope": {"proposals": [
                {"id": "carveout", "names_subjects": ["coop_alpha"]},
                {"id": "vpi_cut", "targets": ["defense"], "removes_vpi_response": True},
                {"id": "self_change", "targets": ["upgrade_protocol"], "data_sources": ["ptl_verified", "forecast"]}]},
            "error_in_cooldown": {"crisis_window": [0, 10], "stabilization_days": 20, "cooldown_error_initiations": [15],
                                  "proposals": [{"id": "later", "submitted_day": 31, "results_published_day": 35,
                                                 "announced_day": 40, "activation_day": 70}]},
            "activation_refused_cooling": {"proposals": [{"id": "u1", "activation_day": 25}]},
            "faulty_upgrades": {"crisis_window": [60, 70], "open_appeals": [[38, 45]], "proposals": [
                {"id": "u1", "deviation_day": 50},
                {"id": "fix", "submitted_day": 51, "results_published_day": 52, "announced_day": 53, "activation_day": 54,
                 "fixes": "u1"},
                {"id": "in_crisis", "submitted_day": 62}],
                "faults": ["upgrade_in_crisis", "short_cooling", "activate_with_open_appeal", "no_rollback", "stack_fix"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_id": {"proposals": [{"id": "a"}, {"id": "a"}]},
                "unknown_fix": {"proposals": [{"id": "a", "fixes": "zz"}]},
                "unknown_target": {"proposals": [{"id": "a", "targets": ["moon"]}]}}
