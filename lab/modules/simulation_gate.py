"""
SIMULATION GATE module — DKP-8-SIMULATION-001 as the pre-activation gate for proposed changes.

Each proposed change (protocol, parameter, composite index, activation condition, onboarding, interop) must
pass simulation before activation (§2, §4).  Scenarios use only declared, versioned, reproducible,
physical, unsmoothed inputs (§5).  Invariant violations invalidate the change (§6); outcomes are classified
F1-F4 and F1-F3 block activation, F4 requires redesign (§7).  Eligibility (§8) needs no violation, no
F1-F3, risk inside the envelope, stability under adversarial scenarios and reproduction by independent
nodes; it permits, never mandates, deployment.  A pass yields a signed Calibration Bundle with the §9
contents; composite indices are fully specified and never modified outside L8.  Triggers demand
recalibration (§10).  Runs are deterministic and transparent (§11); no override or appeal (§12); audit
compares deployed with simulated behaviour (§13); changes to SIMULATION follow §14.

The scenario outcomes are declared input: the lab checks the gate, not the physics of the scenarios.
Every run of this lab is itself research (operational_use: false); no bundle produced here is a real
calibration.  Time unit: step.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

KINDS = ("protocol_modification", "parameter", "composite_index", "activation_condition", "onboarding", "interop")
SCENARIOS = ("historical", "synthetic", "adversarial", "boundary")
VIOLATIONS = ("none", "axiom", "scope", "life", "biosphere", "authority_expansion", "reversibility")
OVERRIDES = ("political", "economic", "emergency", "human_authority")
TRIGGERS = ("environmental_drift", "regime_change", "sensor_change", "audit_divergence", "dependency_update")
BUNDLE_FIELDS = ("thresholds", "model", "aggregation", "confidence_bounds", "validity_window", "assumptions")

FAULTS = {
    "skip_simulation": "a parameter change is activated without simulation",
    "accept_unphysical": "a scenario with unphysical data is accepted",
    "accept_smoothed": "a smoothed or cherry-picked scenario is accepted",
    "accept_undeclared": "an undeclared, unversioned input is accepted",
    "ignore_invariant": "an invariant violation does not invalidate the change",
    "activate_after_f2": "a change with systemic instability is activated",
    "f4_activated": "a change with an externality leak is activated without redesign",
    "no_adversarial_required": "a change is eligible without any adversarial scenario",
    "single_node": "one node's reproduction is enough",
    "unsigned_bundle": "the calibration bundle is unsigned",
    "incomplete_bundle": "the bundle lacks a validity window",
    "unspecified_index": "a composite index is accepted without declared weights",
    "modify_index_outside_l8": "a composite index is changed outside L8",
    "deploy_mandated": "passing simulation forces deployment",
    "emergency_override": "an emergency overrides a failed simulation",
    "appeal_accepted": "a failed simulation is appealed successfully",
    "opaque_artifacts": "simulation configuration is hidden",
    "ignore_trigger": "a recalibration trigger is ignored",
    "no_rollback_on_divergence": "audit divergence beyond tolerance triggers nothing",
    "live_effect": "a simulation writes to the live system",
    "self_change_without_identifier": "SIMULATION is changed without a new identifier",
}


def _admissible(s):
    return s["declared"] and s["versioned"] and s["reproducible"] and not (s["unphysical"] or s["bypass_ptl"] or s["smoothed"] or s["cherry_picked"])


def evaluate_change(c, r, faults=frozenset()):
    """Gate decision for one change (§4-§9)."""
    rej, kept = [], []
    for s in c["scenarios"]:
        ok = _admissible(s)
        if not ok and "accept_unphysical" in faults and (s["unphysical"] or s["bypass_ptl"]) and s["declared"] and s["versioned"]:
            ok = True
        if not ok and "accept_smoothed" in faults and (s["smoothed"] or s["cherry_picked"]) and not (s["unphysical"] or s["bypass_ptl"]):
            ok = True
        if not ok and "accept_undeclared" in faults and not (s["declared"] and s["versioned"] and s["reproducible"]) and not \
                (s["unphysical"] or s["bypass_ptl"] or s["smoothed"] or s["cherry_picked"]):
            ok = True
        (kept if ok else rej).append(s["name"])
    classes, inv = [], []
    for s in c["scenarios"]:
        if s["name"] not in kept:
            continue
        if s["violation"] in ("axiom", "scope"):
            classes.append("F1")
        if s["violation"] != "none" and "ignore_invariant" not in faults:
            inv.append(f"{s['name']}:{s['violation']}")
        if s["instability"]:
            classes.append("F2")
        if s["irreversible"] or s["violation"] == "reversibility":
            classes.append("F3")
        if s["externality_leak"]:
            classes.append("F4")
    classes = sorted(set(classes))
    blocking = [x for x in classes if x in ("F1", "F2", "F3")]
    if "activate_after_f2" in faults:
        blocking = [x for x in blocking if x != "F2"]
    if "ignore_invariant" in faults:
        blocking = [x for x in blocking if x != "F1"]
    adversarial = any(s["kind"] == "adversarial" and s["name"] in kept for s in c["scenarios"])
    stable_adv = all(not s["instability"] for s in c["scenarios"] if s["kind"] == "adversarial" and s["name"] in kept)
    nodes = min([s["reproduced_by_nodes"] for s in c["scenarios"] if s["name"] in kept] or [0])
    envelope = all(s["risk_within_envelope"] for s in c["scenarios"] if s["name"] in kept)
    reasons = []
    if not kept:
        reasons.append("no admissible scenario")
    if inv:
        reasons.append("invariant violated")
    if blocking:
        reasons.append("blocking failure " + ",".join(blocking))
    if "F4" in classes and "f4_activated" not in faults:
        reasons.append("F4: redesign and re-simulation required")
    if not envelope:
        reasons.append("risk outside the declared envelope")
    if not adversarial and "no_adversarial_required" not in faults:
        reasons.append("no adversarial scenario")
    if not stable_adv:
        reasons.append("unstable under adversarial scenarios")
    if nodes < r["min_independent_nodes"] and "single_node" not in faults:
        reasons.append(f"reproduced by {nodes} nodes")
    if c["kind"] == "composite_index" and not (c["index_model"] and c["index_weights"] and c["index_uncertainty"]) and "unspecified_index" not in faults:
        reasons.append("composite index not fully specified")
    return {"admissible": kept, "rejected": rej, "classes": classes, "invariant_violations": inv, "eligible": not reasons, "reasons": reasons}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    for c in r["changes"]:
        if c["skip_requested"] and "skip_simulation" in faults:
            put("decision", "GATE", 1, {"change": c["id"], "activated": True, "simulated": False})
            continue
        res = evaluate_change(c, r, faults)
        put("evaluation", "SIM", 0, {"change": c["id"], "kind": c["kind"], **res, "live_effects": "written" if "live_effect" in faults else "none",
                                     "configuration_exposed": "opaque_artifacts" not in faults, "summary_published": True,
                                     "re_executable": True})
        if res["eligible"]:
            b = {"change": c["id"], "signed": "unsigned_bundle" not in faults}
            for f in BUNDLE_FIELDS:
                b[f] = not (f == "validity_window" and "incomplete_bundle" in faults)
            if c["kind"] == "composite_index":
                b["index"] = {"model": c["index_model"], "weights": c["index_weights"], "uncertainty": c["index_uncertainty"]}
            put("action", "SIM", 0, {"bundle": b})
        deploy = res["eligible"] and (c["deploy_decision"] or "deploy_mandated" in faults)
        if not res["eligible"] and c["override"] != "none" and "emergency_override" in faults and c["override"] == "emergency":
            deploy = True
        put("decision", "GATE", 1, {"change": c["id"], "activated": deploy, "simulated": True, "eligible": res["eligible"],
                                    "override": c["override"], "override_granted": (not res["eligible"]) and deploy})
        if not res["eligible"] and c["appeal"]:
            put("decision", "GATE", 1, {"change": c["id"], "appeal": "granted" if "appeal_accepted" in faults else "refused",
                                        "path": "redesign and re-simulation"})
    for q in r["index_modifications"]:
        put("decision", "GATE", 2, {"index_modification": q["index"], "by_layer": q["layer"],
                                    "accepted": q["layer"] == "L8" or "modify_index_outside_l8" in faults})
    for t in r["triggers"]:
        put("decision", "SIM", 3, {"trigger": t, "recalibration_required": "ignore_trigger" not in faults})
    for d in r["deployed_divergence"]:
        over = d["divergence"] > r["divergence_tolerance"]
        act = "rollback or halt" if over and "no_rollback_on_divergence" not in faults else "none"
        put("action", "AUDIT", 4, {"compare": d["change"], "divergence": d["divergence"], "beyond_tolerance": over, "response": act})
    for c in r["self_changes"]:
        ok = c["new_identifier"] and c["incompatibility_declared"] and c["dependents_resimulated"] or \
            ("self_change_without_identifier" in faults and not c["new_identifier"])
        put("decision", "GATE", 5, {"simulation_change": c["id"], "accepted": ok, "presentation_only": c["presentation_only"]}
            if not c["presentation_only"] else {"simulation_change": c["id"], "accepted": True, "presentation_only": True, "upgrade": False})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    sims = {m.value["change"]: m.value for m in msgs if m.source == "SIM" and "admissible" in m.value}
    gates = {m.value["change"]: m.value for m in msgs if m.source == "GATE" and "activated" in m.value}
    bundles = {m.value["bundle"]["change"]: m.value["bundle"] for m in msgs if m.source == "SIM" and "bundle" in m.value}
    ch = {c["id"]: c for c in r["changes"]}
    want = {i: evaluate_change(c, r) for i, c in ch.items()}
    act = [i for i, g in gates.items() if g["activated"]]
    unsim = [i for i in act if not gates[i]["simulated"]]
    out.append(v("SIMULATION-2-01", "simulation_before_activation", unsim + [i for i in act if not want[i]["eligible"]],
                 "no change activated without passing simulation", "{n} changes activated without it"))
    out.append(v("SIMULATION-4-01", "mandatory_scope", unsim, "every change kind of §4 was simulated", "{n} skipped"))
    out.append(v("SIMULATION-1-01", "hard_gate", [i for i in act if not want[i]["eligible"]] + unsim, "simulation acted as a hard gate", "{n} passed around it"))
    out.append(v("SIMULATION-0-01", "exclusive_mechanism", unsim, "every change went through this protocol", "{n} did not"))
    sc = [s for c in r["changes"] for s in c["scenarios"]]
    bad_in = [(i, s["name"]) for i, c in ch.items() for s in c["scenarios"] if i in sims and s["name"] in sims[i]["admissible"] and not _admissible(s)]
    phys = [x for x in bad_in if any(s["name"] == x[1] and (s["unphysical"] or s["bypass_ptl"]) for s in ch[x[0]]["scenarios"])]
    smooth = [x for x in bad_in if any(s["name"] == x[1] and (s["smoothed"] or s["cherry_picked"]) for s in ch[x[0]]["scenarios"])]
    undecl = [x for x in bad_in if x not in phys and x not in smooth]
    out.append(v("SIMULATION-5-02", "physical_inputs", phys, "no unphysical or PTL-bypassing scenario admitted", "{n} admitted"))
    out.append(v("SIMULATION-5-03", "no_smoothing", smooth, "no smoothed, normalized or cherry-picked scenario admitted", "{n} admitted"))
    out.append(v("SIMULATION-5-04", "declared_inputs", undecl, "inputs declared, versioned and reproducible", "{n} undeclared inputs admitted"))
    out.append(v("SIMULATION-5-01", "admissible_sources", [s["name"] for s in sc if s["kind"] not in SCENARIOS],
                 "scenarios drawn from historical, synthetic, adversarial or boundary data", "{n} other scenarios"))
    out.append(v("SIMULATION-3-02", "bounded_scenarios", [s["name"] for s in sc if not s["declared"] and any(s["name"] in sims[i]["admissible"] for i in sims)],
                 "scenarios are bounded, declared sets of conditions", "{n} unbounded scenarios used"))
    inv_bad = [i for i in gates if gates[i]["activated"] and want[i]["invariant_violations"]]
    out.append(v("SIMULATION-6-02", "invariant_invalidates", inv_bad, "every invariant violation invalidated its change", "{n} activated despite a violation"))
    out.append(v("SIMULATION-6-01", "invariants_enforced", [i for i in sims if sims[i]["invariant_violations"] != want[i]["invariant_violations"]],
                 "axiom, scope, life, biosphere, authority and reversibility invariants checked", "{n} changes checked otherwise"))
    out.append(v("SIMULATION-3-03", "invariant_definition", [], "invariants derived from AXIOMS and SCOPE", ""))
    for fx, rid in (("F1", "SIMULATION-7-01"), ("F2", "SIMULATION-7-02"), ("F3", "SIMULATION-7-03"), ("F4", "SIMULATION-7-04")):
        ids = [i for i in want if fx in want[i]["classes"]]
        out.append(v(rid, f"class_{fx.lower()}", [i for i in ids if fx not in sims.get(i, {}).get("classes", [])], f"{fx} outcomes classified",
                     "{n} misclassified") if ids else na(rid, f"class_{fx.lower()}", fx, "no scenario of this class"))
    blk = [i for i in want if set(want[i]["classes"]) & {"F1", "F2", "F3"}]
    out.append(v("SIMULATION-7-05", "f1_f3_block", [i for i in blk if gates.get(i, {}).get("activated")], "F1-F3 blocked activation", "{n} activated")
               if blk else na("SIMULATION-7-05", "f1_f3_block", "F1-F3 failures", "none"))
    f4 = [i for i in want if "F4" in want[i]["classes"]]
    out.append(v("SIMULATION-7-06", "f4_redesign", [i for i in f4 if gates.get(i, {}).get("activated")], "F4 sent back to redesign and re-simulation",
                 "{n} activated without redesign") if f4 else na("SIMULATION-7-06", "f4_redesign", "F4 failures", "none"))
    out.append(v("SIMULATION-3-04", "failure_state", [i for i in want if not want[i]["eligible"] and gates.get(i, {}).get("activated")],
                 "failure states (violation, envelope, irreversibility) never activated", "{n} activated"))
    elig = [i for i in sims if sims[i]["eligible"]]
    out.append(v("SIMULATION-8-01", "acceptance_criteria", [i for i in elig if not want[i]["eligible"]], "eligibility only when every §8 condition holds",
                 "{n} declared eligible wrongly"))
    out.append(v("SIMULATION-3-05", "formal_acceptance", [i for i in elig if not want[i]["eligible"]], "acceptance decided by formal conditions", "{n} otherwise"))
    passed_not_deployed = [i for i in elig if not ch[i]["deploy_decision"]]
    out.append(v("SIMULATION-8-02", "eligibility_not_mandate", [i for i in passed_not_deployed if gates[i]["activated"]],
                 "passing changes deployed only by a separate decision", "{n} deployed because they passed")
               if passed_not_deployed else na("SIMULATION-8-02", "eligibility_not_mandate", "eligible changes left undeployed", "none"))
    if elig:
        out.append(v("SIMULATION-9-01", "bundle_contents", [i for i in elig if i not in bundles or not bundles[i]["signed"] or
                                                             not all(bundles[i][f] for f in BUNDLE_FIELDS)],
                     "every pass produced a signed bundle with thresholds, model, aggregation, bounds, validity window and assumptions",
                     "{n} bundles missing, unsigned or incomplete"))
        out.append(v("SIMULATION-3-06", "bundle_definition", [i for i in elig if i not in bundles or not bundles[i]["signed"]], "bundles are signed L8 artifacts",
                     "{n} unsigned"))
    else:
        for rid, chk in (("SIMULATION-9-01", "bundle_contents"), ("SIMULATION-3-06", "bundle_definition")):
            out.append(na(rid, chk, "eligible changes", "none"))
    ci = [i for i, c in ch.items() if c["kind"] == "composite_index"]
    out.append(v("SIMULATION-CompositeIndices-01", "index_specified", [i for i in ci if sims.get(i, {}).get("eligible") and
                                                                       not (ch[i]["index_model"] and ch[i]["index_weights"] and ch[i]["index_uncertainty"])],
                 "composite indices eligible only with model, inputs, weights and uncertainty propagation", "{n} under-specified indices passed")
               if ci else na("SIMULATION-CompositeIndices-01", "index_specified", "composite indices", "none proposed"))
    im = [m.value for m in msgs if m.source == "GATE" and "index_modification" in m.value]
    out.append(v("SIMULATION-CompositeIndices-02", "index_only_in_l8", [x["index_modification"] for x in im if x["accepted"] and x["by_layer"] != "L8"],
                 "composite indices changed only in L8", "{n} changed elsewhere") if im else
               na("SIMULATION-CompositeIndices-02", "index_only_in_l8", "index modifications", "none"))
    out.append(v("SIMULATION-CompositeIndices-03", "ptl_raw_only", [x["index_modification"] for x in im if x["accepted"] and x["by_layer"] == "L0"],
                 "PTL emits raw outputs; calibration stays in L8", "{n} PTL calibrations") if im else
               na("SIMULATION-CompositeIndices-03", "ptl_raw_only", "index modifications", "none"))
    tr = [m.value for m in msgs if m.source == "SIM" and "trigger" in m.value]
    out.append(v("SIMULATION-10-01", "recalibration_triggers", [x["trigger"] for x in tr if not x["recalibration_required"]],
                 "every trigger demanded a new simulation and calibration", "{n} triggers ignored") if tr else
               na("SIMULATION-10-01", "recalibration_triggers", "triggers", "none"))
    again = run(r)
    out.append(v("SIMULATION-11-01", "deterministic", [] if again.digest() == log.digest() else ["digest"], "identical inputs, identical simulation log", "runs differ"))
    out.append(v("SIMULATION-11-02", "exposed_and_reexecutable", [i for i, s in sims.items() if not (s["configuration_exposed"] and s["summary_published"] and s["re_executable"])],
                 "configuration exposed, summaries published, re-execution possible", "{n} opaque simulations"))
    out.append(v("SIMULATION-11-03", "not_opaque", [i for i, s in sims.items() if not s["configuration_exposed"]], "no opaque artifact", "{n} opaque"))
    out.append(v("SIMULATION-3-01", "isolated_environment", [i for i, s in sims.items() if s["live_effects"] != "none"], "simulations produced no live effects",
                 "{n} simulations wrote to the live system"))
    ov = [i for i, c in ch.items() if c["override"] != "none" and not want[i]["eligible"]]
    out.append(v("SIMULATION-12-01", "no_override", [i for i in ov if gates.get(i, {}).get("override_granted")], "no political, economic, emergency or human override",
                 "{n} overrides granted") if ov else na("SIMULATION-12-01", "no_override", "override requests on failed changes", "none"))
    ap = [m.value for m in msgs if m.source == "GATE" and "appeal" in m.value]
    out.append(v("SIMULATION-12-02", "no_appeal", [x["change"] for x in ap if x["appeal"] != "refused"], "appeals refused; redesign and re-simulation only",
                 "{n} appeals granted") if ap else na("SIMULATION-12-02", "no_appeal", "appeals", "none"))
    au = [m.value for m in msgs if m.source == "AUDIT" and "compare" in m.value]
    if au:
        out.append(v("SIMULATION-13-01", "audit_compares", [], f"{len(au)} deployed changes compared with their simulation", ""))
        out.append(v("SIMULATION-13-02", "divergence_flagged", [x["compare"] for x in au if (x["divergence"] > r["divergence_tolerance"]) != x["beyond_tolerance"]],
                     f"divergence beyond tolerance {r['divergence_tolerance']} (declared, source missing) flagged", "{n} misflagged"))
        out.append(v("SIMULATION-13-03", "rollback_or_halt", [x["compare"] for x in au if x["beyond_tolerance"] and x["response"] == "none"],
                     "divergence beyond tolerance triggered rollback or halt", "{n} without a response"))
    else:
        for rid, chk in (("SIMULATION-13-01", "audit_compares"), ("SIMULATION-13-02", "divergence_flagged"), ("SIMULATION-13-03", "rollback_or_halt")):
            out.append(na(rid, chk, "deployed changes", "none"))
    scg = [m.value for m in msgs if m.source == "GATE" and "simulation_change" in m.value]
    scd = {c["id"]: c for c in r["self_changes"]}
    if scg:
        acc = [x["simulation_change"] for x in scg if x["accepted"] and not x["presentation_only"]]
        out.append(v("SIMULATION-14-01", "upgrade_procedure", [i for i in acc if not (scd[i]["new_identifier"] and scd[i]["incompatibility_declared"] and scd[i]["dependents_resimulated"])],
                     "SIMULATION changed only with the full procedure", "{n} changes otherwise"))
        out.append(v("SIMULATION-14-02", "new_identifier", [i for i in acc if not scd[i]["new_identifier"]], "accepted changes carry a new identifier", "{n} without"))
        out.append(v("SIMULATION-14-03", "incompatibility_declared", [i for i in acc if not scd[i]["incompatibility_declared"]], "incompatibility declared", "{n} without"))
        out.append(v("SIMULATION-14-04", "dependents_resimulated", [i for i in acc if not scd[i]["dependents_resimulated"]], "dependents re-simulated", "{n} without"))
        pres = [x for x in scg if x["presentation_only"]]
        out.append(v("SIMULATION-14-05", "presentation_not_upgrade", [x["simulation_change"] for x in pres if x.get("upgrade")],
                     "presentation-only corrections not treated as Upgrades", "{n} treated as Upgrades") if pres else
                   na("SIMULATION-14-05", "presentation_not_upgrade", "presentation corrections", "none"))
    else:
        for rid, chk in (("SIMULATION-14-01", "upgrade_procedure"), ("SIMULATION-14-02", "new_identifier"), ("SIMULATION-14-03", "incompatibility_declared"),
                         ("SIMULATION-14-04", "dependents_resimulated"), ("SIMULATION-14-05", "presentation_not_upgrade")):
            out.append(na(rid, chk, "changes to SIMULATION", "none"))
    return out


IMPLEMENTS = {
    "SIMULATION-0-01": ("exclusive_mechanism", "PARTIAL", "Changes are declared."),
    "SIMULATION-1-01": ("hard_gate", "IMPLEMENTED", None),
    "SIMULATION-2-01": ("simulation_before_activation", "IMPLEMENTED", None),
    "SIMULATION-3-01": ("isolated_environment", "PARTIAL", "Recorded property."),
    "SIMULATION-3-02": ("bounded_scenarios", "PARTIAL", "Scenarios are declared."),
    "SIMULATION-3-03": ("invariant_definition", "PARTIAL", "Invariant kinds are declared per scenario."),
    "SIMULATION-3-04": ("failure_state", "PARTIAL", "Risk envelopes are declared."),
    "SIMULATION-3-05": ("formal_acceptance", "IMPLEMENTED", None),
    "SIMULATION-3-06": ("bundle_definition", "PARTIAL", "Lab bundles are research artifacts, never calibration (operational_use: false)."),
    "SIMULATION-4-01": ("mandatory_scope", "IMPLEMENTED", None),
    "SIMULATION-5-01": ("admissible_sources", "IMPLEMENTED", None),
    "SIMULATION-5-02": ("physical_inputs", "PARTIAL", "Unphysical data is a declared flag."),
    "SIMULATION-5-03": ("no_smoothing", "PARTIAL", "Declared flags."),
    "SIMULATION-5-04": ("declared_inputs", "IMPLEMENTED", None),
    "SIMULATION-6-01": ("invariants_enforced", "PARTIAL", "Violations are declared scenario outcomes."),
    "SIMULATION-6-02": ("invariant_invalidates", "IMPLEMENTED", None),
    "SIMULATION-7-01": ("class_f1", "IMPLEMENTED", None),
    "SIMULATION-7-02": ("class_f2", "PARTIAL", "Instability is a declared outcome."),
    "SIMULATION-7-03": ("class_f3", "PARTIAL", "Irreversibility is a declared outcome."),
    "SIMULATION-7-04": ("class_f4", "PARTIAL", "Leaks are a declared outcome."),
    "SIMULATION-7-05": ("f1_f3_block", "IMPLEMENTED", None),
    "SIMULATION-7-06": ("f4_redesign", "IMPLEMENTED", None),
    "SIMULATION-8-01": ("acceptance_criteria", "PARTIAL", "Independent nodes: declared minimum (source missing); adversarial stability: at least one adversarial scenario (H-SM-1)."),
    "SIMULATION-8-02": ("eligibility_not_mandate", "IMPLEMENTED", None),
    "SIMULATION-9-01": ("bundle_contents", "IMPLEMENTED", None),
    "SIMULATION-CompositeIndices-01": ("index_specified", "IMPLEMENTED", None),
    "SIMULATION-CompositeIndices-02": ("index_only_in_l8", "IMPLEMENTED", None),
    "SIMULATION-CompositeIndices-03": ("ptl_raw_only", "PARTIAL", "Requests carry their layer."),
    "SIMULATION-10-01": ("recalibration_triggers", "IMPLEMENTED", None),
    "SIMULATION-11-01": ("deterministic", "IMPLEMENTED", None),
    "SIMULATION-11-02": ("exposed_and_reexecutable", "PARTIAL", "Recorded properties."),
    "SIMULATION-11-03": ("not_opaque", "PARTIAL", "Recorded properties."),
    "SIMULATION-12-01": ("no_override", "IMPLEMENTED", None),
    "SIMULATION-12-02": ("no_appeal", "IMPLEMENTED", None),
    "SIMULATION-13-01": ("audit_compares", "PARTIAL", "Divergence values are declared."),
    "SIMULATION-13-02": ("divergence_flagged", "PARTIAL", "Tolerance not given (source missing)."),
    "SIMULATION-13-03": ("rollback_or_halt", "IMPLEMENTED", None),
    "SIMULATION-14-01": ("upgrade_procedure", "PARTIAL", "Declared properties of the change."),
    "SIMULATION-14-02": ("new_identifier", "IMPLEMENTED", None),
    "SIMULATION-14-03": ("incompatibility_declared", "IMPLEMENTED", None),
    "SIMULATION-14-04": ("dependents_resimulated", "IMPLEMENTED", None),
    "SIMULATION-14-05": ("presentation_not_upgrade", "IMPLEMENTED", None),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")


def _sc(name, kind="historical", **kw):
    s = {"name": name, "kind": kind, "declared": True, "versioned": True, "reproducible": True, "unphysical": False, "bypass_ptl": False,
         "smoothed": False, "cherry_picked": False, "violation": "none", "instability": False, "irreversible": False, "externality_leak": False,
         "risk_within_envelope": True, "reproduced_by_nodes": 3}
    s.update(kw)
    return s


def _ch(i, kind, scen, **kw):
    c = {"id": i, "kind": kind, "scenarios": scen, "deploy_decision": True, "override": "none", "appeal": False, "skip_requested": False,
         "index_model": True, "index_weights": True, "index_uncertainty": True}
    c.update(kw)
    return c


GOOD = [_sc("hist", "historical"), _sc("stress", "adversarial")]
CHANGES = [
    _ch("ttl_rule", "parameter", GOOD),
    _ch("spdi_v2", "composite_index", GOOD + [_sc("boundary", "boundary")], deploy_decision=False),
    _ch("crisis_fast", "activation_condition", [_sc("hist"), _sc("stress", "adversarial", instability=True)], override="emergency", appeal=True),
    _ch("habitat_rule", "protocol_modification", [_sc("hist", violation="scope"), _sc("stress", "adversarial")]),
    _ch("interop_x", "interop", [_sc("hist", externality_leak=True), _sc("stress", "adversarial")]),
    _ch("onboard_y", "onboarding", [_sc("hist", smoothed=True), _sc("fake", unphysical=True), _sc("anon", declared=False),
                                    _sc("stress", "adversarial")]),
    _ch("bundle_z", "parameter", [_sc("hist", reproduced_by_nodes=1), _sc("stress", "adversarial", reproduced_by_nodes=1)], skip_requested=True),
    _ch("deadlock_rule", "protocol_modification", [_sc("hist", instability=True), _sc("stress", "adversarial")]),
    _ch("plain_rule", "parameter", [_sc("hist")]),
    _ch("index_w", "composite_index", GOOD, index_weights=False),
    _ch("dam_rule", "activation_condition", [_sc("hist", irreversible=True), _sc("stress", "adversarial")]),
]


class SimulationGateModule(LabModule):
    id = "simulation_gate"
    version = "1.0.0"
    title = {"en": "Simulation gate (SIMULATION)", "ru": "Шлюз симуляции (SIMULATION)"}
    summary = {"en": "Seven proposed changes — a parameter, a new index, a faster crisis trigger, a rule that breaks scope, a leaky interop, "
                     "a cherry-picked onboarding, a single-node result: which may become eligible, and is anything activated around the gate?",
               "ru": "Семь предложенных изменений — параметр, новый индекс, быстрый кризисный триггер, правило вне границ, протекающая "
                     "интероперабельность, подобранный онбординг, результат одного узла: что может стать допустимым и проходит ли что-то мимо шлюза?"}
    protocols = ["DKP-8-SIMULATION-001"]
    example_order = ["proposed_changes", "faulty_gate"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_simulation_gate_module.py"]
    causal_note = {"en": "Scenario outcomes are declared; the lab checks the gate's decisions, not the physics of the scenarios. No lab "
                         "bundle is a calibration (operational_use: false).",
                   "ru": "Исходы сценариев объявлены; лаборатория проверяет решения шлюза, а не физику сценариев. Ни один пакет "
                         "лаборатории не является калибровкой (operational_use: false)."}
    hypotheses = [
        {"id": "H-SM-1", "source": "hypothesis", "text": {
            "en": "'Stable under adversarial scenarios' requires at least one admissible adversarial scenario, none of them unstable; "
                  "'reproducible by independent nodes' = every admissible scenario reproduced by at least the declared number of nodes.",
            "ru": "'Устойчивость в состязательных сценариях' требует хотя бы одного допустимого состязательного сценария без "
                  "неустойчивости; 'воспроизводимость независимыми узлами' = каждый допустимый сценарий воспроизведён не менее чем "
                  "объявленным числом узлов."}},
        {"id": "H-SM-2", "source": "hypothesis", "text": {
            "en": "Life-preservation, biosphere, authority and reversibility violations invalidate the change (§6) even when §7 gives "
                  "them no class; reversibility violations are F3.",
            "ru": "Нарушения сохранения жизни, биосферы, полномочий и обратимости делают изменение недействительным (§6), даже если "
                  "§7 не даёт им класса; нарушения обратимости — F3."}},
    ]
    inputs = {
        "min_independent_nodes": {"type": "int", "min": 1, "max": 100, "default": 2, "source": "missing",
                                  "label": {"en": "Independent nodes needed to reproduce", "ru": "Сколько независимых узлов должны воспроизвести"}},
        "divergence_tolerance": {"type": "number", "min": 0, "max": 1, "default": 0.05, "source": "missing",
                                 "label": {"en": "Deployed/simulated divergence tolerance", "ru": "Допуск расхождения развёрнутого и симулированного"}},
        "changes": {"type": "list", "min_items": 0, "max_items": 20, "source": "user", "label": {"en": "Proposed changes", "ru": "Предложенные изменения"},
                    "items": {"type": "object", "fields": {
                        "id": {"type": "str"}, "kind": {"type": "enum", "values": list(KINDS)},
                        "scenarios": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "object", "fields": {
                            "name": {"type": "str"}, "kind": {"type": "enum", "values": list(SCENARIOS)},
                            "declared": {"type": "bool", "default": True}, "versioned": {"type": "bool", "default": True},
                            "reproducible": {"type": "bool", "default": True}, "unphysical": {"type": "bool", "default": False},
                            "bypass_ptl": {"type": "bool", "default": False}, "smoothed": {"type": "bool", "default": False},
                            "cherry_picked": {"type": "bool", "default": False},
                            "violation": {"type": "enum", "values": list(VIOLATIONS), "default": "none"},
                            "instability": {"type": "bool", "default": False}, "irreversible": {"type": "bool", "default": False},
                            "externality_leak": {"type": "bool", "default": False}, "risk_within_envelope": {"type": "bool", "default": True},
                            "reproduced_by_nodes": {"type": "int", "min": 0, "max": 100, "default": 3}}}},
                        "deploy_decision": {"type": "bool", "default": True},
                        "override": {"type": "enum", "values": ["none"] + list(OVERRIDES), "default": "none"},
                        "appeal": {"type": "bool", "default": False}, "skip_requested": {"type": "bool", "default": False},
                        "index_model": {"type": "bool", "default": True}, "index_weights": {"type": "bool", "default": True},
                        "index_uncertainty": {"type": "bool", "default": True}}},
                    "default": CHANGES},
        "index_modifications": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Index modification requests", "ru": "Запросы на изменение индексов"},
                                "items": {"type": "object", "fields": {"index": {"type": "str"}, "layer": {"type": "enum", "values": ["L0", "L2", "L5", "L8"]}}},
                                "default": [{"index": "b_t", "layer": "L0"}, {"index": "spdi", "layer": "L5"}, {"index": "spdi", "layer": "L8"}]},
        "triggers": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "enum", "values": list(TRIGGERS)},
                     "default": ["environmental_drift", "sensor_change"], "source": "user", "label": {"en": "Recalibration triggers", "ru": "Поводы для перекалибровки"}},
        "deployed_divergence": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Deployed vs simulated", "ru": "Развёрнутое против симулированного"},
                                "items": {"type": "object", "fields": {"change": {"type": "str"}, "divergence": {"type": "number", "min": 0, "max": 10}}},
                                "default": [{"change": "ttl_rule", "divergence": 0.02}, {"change": "ttl_rule_b", "divergence": 0.2}]},
        "self_changes": {"type": "list", "min_items": 0, "max_items": 5, "source": "user", "label": {"en": "Changes to SIMULATION", "ru": "Изменения SIMULATION"},
                         "items": {"type": "object", "fields": {"id": {"type": "str"}, "new_identifier": {"type": "bool", "default": True},
                                                                "incompatibility_declared": {"type": "bool", "default": True},
                                                                "dependents_resimulated": {"type": "bool", "default": True},
                                                                "presentation_only": {"type": "bool", "default": False}}},
                         "default": [{"id": "sim_002"}, {"id": "typo", "presentation_only": True}, {"id": "quiet_edit", "new_identifier": False}]},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [c["id"] for c in r["changes"]]
        if len(set(ids)) != len(ids):
            p.append("input.changes: repeated id")
        for c in r["changes"]:
            names = [s["name"] for s in c["scenarios"]]
            if len(set(names)) != len(names):
                p.append(f"input.changes: {c['id']} repeats a scenario name")
            for x in [c["id"]] + names:
                if not _ID.fullmatch(x):
                    p.append(f"input.changes: identifier {x!r} must be lowercase letters, digits or _")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        sims = [m.value for m in msgs if m.source == "SIM" and "admissible" in m.value]
        outputs = {"simulations": sims, "gate": [m.value for m in msgs if m.source == "GATE"],
                   "bundles": [m.value["bundle"] for m in msgs if m.source == "SIM" and "bundle" in m.value],
                   "audit": [m.value for m in msgs if m.source == "AUDIT"],
                   "operational_use": False,
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        el = [s["change"] for s in sims if s["eligible"]]
        e = [{"en": f"{len(sims)} changes simulated, eligible: {', '.join(el) or 'none'}; violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"Симулировано изменений: {len(sims)}, допустимы: {', '.join(el) or 'нет'}; нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]), "eligible": sum(1 for s in outputs["simulations"] if s["eligible"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"proposed_changes": {},
                "one_clean_change": {"changes": [_ch("ttl_rule", "parameter", GOOD)], "index_modifications": [], "triggers": [], "deployed_divergence": [],
                                     "self_changes": []},
                "faulty_gate": {"faults": ["skip_simulation", "accept_smoothed", "activate_after_f2", "deploy_mandated", "emergency_override"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_change": {"changes": [_ch("a", "parameter", GOOD), _ch("a", "parameter", GOOD)]},
                "repeated_scenario": {"changes": [_ch("a", "parameter", [_sc("x"), _sc("x")])]}}


for _spec in SimulationGateModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
