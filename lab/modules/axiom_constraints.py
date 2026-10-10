"""
AXIOM CONSTRAINTS module — DKP-1-AXIOMS-001 executed on a set of candidate actions.

Axioms are evaluated before any optimization (§5.1); a violated axiom invalidates an action regardless
of its utility (§5.2); axioms are not additive (§5.3); conflicts are resolved only by higher-priority
axioms (§5.4) in the fixed order A1 … A7 (§6); A7 (minimum suffering) acts only among actions that are
indistinguishable on the higher axioms and never as the primary criterion; prohibited interpretations
(§7): axioms as goals or weighted terms, suspension for efficiency, human override, contextual
reinterpretation.  A1a: no compelled lethal risk, refusal is no fault, risk symmetry through access
and compensation only.  §8: modifying an axiom needs a new identifier, an incompatibility declaration,
SIMULATION revalidation and ratification by 67 % of "active validating nodes, as defined in Appendix A.5
of the Code" — which defines no such set (finding F-022).

Whether a candidate violates A1–A6 is a declared property (physical models are not in the lab; outside
a Crisis Scope "axioms are executed, not interpreted", SCOPE).  A1's "minimum required conditions" have
no definition anywhere (finding F-023): a candidate that relies on them is not accepted.

Two readings the text does not settle are inputs:
  * no axiom-clean candidate (H-AX-2): 'lexicographic' — §5.4, the candidate whose violations are of the
    lowest priority; 'no_admissible_action' — §5.2, every violating action is invalid (F-024);
  * A4 says SHOULD (H-AX-3): 'constraint' — like every axiom (§3, §5.2); 'recommendation' (F-025).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

PRIORITY = {"A1": 1, "A2": 2, "A3": 3, "A4": 4, "A5": 5, "A6": 6, "A7": 7}
# §3: each axiom is a forbidden state or a hard priority ordering (lab reading of each axiom's wording, H-AX-5)
FORM = {"A1": "forbidden_state", "A2": "forbidden_state", "A3": "priority_ordering", "A4": "priority_ordering",
        "A5": "forbidden_state", "A6": "forbidden_state", "A7": "priority_ordering"}
FORMS = ("forbidden_state", "priority_ordering")
AXIOM_EVAL_FIELDS = {"step", "violations"}
AXIOM_DECISION_FIELDS = {"chosen", "basis", "decided_by", "passed_axioms", "propagated_violations", "irreversible", "necessity"}
RATIFICATION = 67.0
FAULTS = {
    "utility_override": "the action with the highest utility is chosen despite a violated axiom",
    "weighted_axioms": "axioms are encoded as weighted penalties in a utility score",
    "suspend_for_efficiency": "axioms are skipped for a low-stakes decision",
    "human_override": "an operator picks the action instead of the axiom evaluation",
    "lower_overrides_higher": "a lower-priority axiom is satisfied at the cost of a higher one",
    "suffering_primary": "suffering is used as the primary criterion across non-equivalent actions",
    "context_reinterpretation": "a violation is excused by political or situational context",
    "infer_minimum_required": "an operational protocol declares the A1 minimum required conditions met",
    "compel_service": "Subjects are compelled into lethal-risk duty",
    "punish_refusal": "refusing lethal risk is recorded as a fault",
    "benefit_free_riders": "refusers receive benefits derived from the collective security risk",
    "missing_metadata": "the decision output carries no epistemic metadata",
    "classify_axioms": "the axiom definitions are given output metadata and made disputable",
    "axiom_shield": "a dispute of the decision is rejected because it cites axiom compliance",
    "unmodelled_necessity": "an irreversible choice cites necessity without an IMPACT irreversibility model",
    "axiom_computes_metric": "the axiom stage computes a score from the candidates' data",
    "axiom_as_weight": "A7 is recorded as a weighted objective instead of a constraint",
    "narrative_override": "a candidate whose declared goal contradicts the PTL measurement is not counted as violating A3",
    "axioms_as_truth": "the axiom definitions are published as absolute truth",
}
IMPACT_MODEL = "DKP-1-IMPACT irreversible impact model"
CANDIDATE = {"type": "object", "fields": {
    "id": {"type": "str"},
    "utility": {"type": "number", "min": -10 ** 9, "max": 10 ** 9, "default": 0},
    "increases_life_loss": {"type": "bool", "default": False},
    "claims_minimum_required": {"type": "bool", "default": False},
    "degrades_long_term": {"type": "bool", "default": False},
    "grounded_in_ptl": {"type": "bool", "default": True},
    "irreversible": {"type": "bool", "default": False},
    "reversible_alternative": {"type": "bool", "default": False},
    "necessity_verified": {"type": "bool", "default": False},
    "necessity_model": {"type": "enum", "values": [IMPACT_MODEL, "none", "expert judgement"], "default": IMPACT_MODEL},
    "unmeasured_externality": {"type": "bool", "default": False},
    "withholds_truth": {"type": "bool", "default": False},
    "basis": {"type": "enum", "values": ["ptl", "declared_goal", "narrative", "belief"], "default": "ptl"},
    "contradicts_ptl": {"type": "bool", "default": False},
    "suffering": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0}}}
MODIFICATION = {"axiom": {"type": "enum", "values": ["none"] + list(PRIORITY), "default": "none"},
                "new_identifier": {"type": "bool", "default": True},
                "incompatibility_declared": {"type": "bool", "default": True},
                "simulation_revalidated": {"type": "bool", "default": True},
                "ratification_share": {"type": "number", "min": -1, "max": 100, "default": -1}}
RISK = {"participants": {"type": "int", "min": 0, "max": 10 ** 6, "default": 20},
        "refusers": {"type": "int", "min": 0, "max": 10 ** 6, "default": 5},
        "risk_benefit": {"type": "number", "min": 0, "max": 10 ** 6, "default": 10}}


def violations(c: Dict[str, Any], a4_reading: str) -> List[str]:
    """Axioms a candidate violates, from its declared properties (no interpretation)."""
    v = []
    if c["increases_life_loss"] or c["claims_minimum_required"]:
        v.append("A1")                         # the minimum required conditions are undefined (F-023)
    if c["degrades_long_term"]:
        v.append("A2")
    if not c["grounded_in_ptl"] or (c.get("contradicts_ptl") and c.get("basis", "ptl") != "ptl"):
        v.append("A3")                         # §A3: a declared goal or narrative SHALL NOT override measured reality
    if a4_reading == "constraint" and c["irreversible"] and c["reversible_alternative"] and not c["necessity_verified"]:
        v.append("A4")
    if c["unmeasured_externality"]:
        v.append("A5")                         # treated as maximum-impact damage
    if c["withholds_truth"]:
        v.append("A6")
    return v


def profile(v: List[str]) -> Tuple[int, ...]:
    """Lexicographic key: higher is better; the most important violated axiom decides first."""
    pr = sorted(PRIORITY[a] for a in v)
    return tuple(pr + [8] * (7 - len(pr)))


def choose(cands: List[Dict[str, Any]], a4: str, dilemma: str) -> Tuple[Optional[str], str, List[str]]:
    """Reference decision: (chosen id or None, basis, the ids that passed the axiom stage)."""
    V = {c["id"]: violations(c, a4) for c in cands}
    clean = [c for c in cands if not V[c["id"]]]
    if clean:
        pool, basis = clean, "axiom-clean"
    elif dilemma == "lexicographic":
        best = max(profile(V[c["id"]]) for c in cands)
        pool, basis = [c for c in cands if profile(V[c["id"]]) == best], "axiom conflict resolved by priority (§5.4)"
    else:
        return None, "no admissible action (§5.2); propagated to higher layers", []
    least = min(c["suffering"] for c in pool)
    pool2 = [c for c in pool if c["suffering"] == least]            # A7 non-amplification among equivalents
    pick = sorted(pool2, key=lambda c: (-c["utility"], c["id"]))[0]
    return pick["id"], basis, [c["id"] for c in pool]


def md(scope):
    return {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": scope, "revalidation_required": True, "dispute_allowed": True}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=(), epistemic=None):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    cands = r["candidates"]
    a4, dil = r["a4_reading"], r["dilemma_reading"]
    # Epistemic Clarification a): the axioms are constraints, not outputs
    forms = dict(FORM, A7="weighted_objective") if "axiom_as_weight" in faults else dict(FORM)
    put("notice", "AXIOM-DEFINITIONS", 0, {"axioms": sorted(PRIORITY, key=lambda a: PRIORITY[a]), "kind": "structural constraints",
                                           "forms": forms,
                                           "status": "absolute truth" if "axioms_as_truth" in faults else "bounded evaluation constraints"},
        epistemic=md("DKP-1-AXIOMS-001") if "classify_axioms" in faults else None)
    obs = [put("observation", "CANDIDATES", 0, {"candidate": c["id"], "declared": {k: v for k, v in c.items() if k != "id"}})
           for c in cands]
    V = {c["id"]: violations(c, a4) for c in cands}
    if "narrative_override" in faults:
        V = {k: ([a for a in v if a != "A3"] if next(c for c in cands if c["id"] == k)["grounded_in_ptl"] else v)
             for k, v in V.items()}
    if "context_reinterpretation" in faults:
        V = {k: [a for a in v if a not in ("A5", "A6")] for k, v in V.items()}
    if "infer_minimum_required" in faults:
        V = {k: ([a for a in v if a != "A1"] if next(c for c in cands if c["id"] == k)["claims_minimum_required"]
                 and not next(c for c in cands if c["id"] == k)["increases_life_loss"] else v) for k, v in V.items()}
    steps = []
    if "suspend_for_efficiency" not in faults:
        ev = put("evaluation", "AXIOMS", 1, {"step": "axiom_evaluation", "violations": V,
                                             **({"sustainability_index": round(sum(c["utility"] for c in cands) / len(cands), 6)}
                                                if "axiom_computes_metric" in faults else {})}, [o.event_id for o in obs])
        steps.append(ev.event_id)
    rank = put("evaluation", "OPTIMIZER", 2, {"step": "utility_ranking",
                                               "ranking": [c["id"] for c in sorted(cands, key=lambda c: (-c["utility"], c["id"]))]},
               steps)
    chosen, basis, passed = choose([{**c} for c in cands], a4, dil)
    if V != {c["id"]: violations(c, a4) for c in cands}:
        clean = [c for c in cands if not V[c["id"]]]
        if clean:
            chosen = sorted(clean, key=lambda c: (c["suffering"], -c["utility"], c["id"]))[0]["id"]
            basis = "axiom-clean (after excusing violations)"
    decided_by = "axiom evaluation"
    if "utility_override" in faults or "suspend_for_efficiency" in faults:
        chosen = sorted(cands, key=lambda c: (-c["utility"], c["id"]))[0]["id"]
        basis = "highest utility"
    if "weighted_axioms" in faults:
        score = {c["id"]: c["utility"] - 10 * len(V[c["id"]]) for c in cands}
        chosen = sorted(cands, key=lambda c: (-score[c["id"]], c["id"]))[0]["id"]
        basis = "weighted score (utility − 10 × violations)"
    if "human_override" in faults:
        chosen = cands[-1]["id"]
        decided_by = "operator"
    if "lower_overrides_higher" in faults:
        worst = sorted(cands, key=lambda c: (min([PRIORITY[a] for a in V[c["id"]]] or [9]), c["id"]))
        chosen = worst[0]["id"]
        basis = "satisfies the lower-priority axioms"
    if "suffering_primary" in faults:
        chosen = sorted(cands, key=lambda c: (c["suffering"], c["id"]))[0]["id"]
        basis = "least suffering"
    cc = next((c for c in cands if c["id"] == chosen), None)
    nec = {"verified": bool(cc and cc["necessity_verified"]),
           "model": "expert judgement" if "unmodelled_necessity" in faults else (cc["necessity_model"] if cc else "none")}
    dec = put("decision", "AXIOMS", 3, {"chosen": chosen, "basis": basis, "decided_by": decided_by, "passed_axioms": passed,
                                        "propagated_violations": V.get(chosen, []) if chosen else sorted({a for v in V.values() for a in v}),
                                        "irreversible": bool(cc and cc["irreversible"]), "necessity": nec},
              steps + [rank.event_id], epistemic=None if "missing_metadata" in faults else md("DKP-1-AXIOMS-001 §5"))
    # Epistemic Clarification c): a dispute of an output citing axiom compliance is not blocked by axiom invariance
    if r["dispute_of_decision"]:
        shield = "axiom_shield" in faults
        put("notice", "DISPUTE", 4, {"dispute_of": dec.event_id, "cites": "axiom compliance",
                                     "accepted_for_review": not shield,
                                     "reason": "axioms are invariant" if shield else "EPISTEMIC-BOUNDARIES §7; axiom invariance "
                                     "does not prevent re-evaluation of axiom-bounded outputs"}, [dec.event_id])
    # A1a risk symmetry
    rk = r["risk_pool"]
    put("action", "A1A", 4, {"duty": "voluntary", "compelled": rk["refusers"] if "compel_service" in faults else 0})
    put("action", "A1A", 4, {"risk_benefit_to": "participants", "count": rk["participants"], "amount": rk["risk_benefit"]})
    if "benefit_free_riders" in faults:
        put("action", "A1A", 4, {"risk_benefit_to": "refusers", "count": rk["refusers"], "amount": rk["risk_benefit"]})
    put("action", "A1A", 4, {"refusal": "recorded as a right", "fault": "punish_refusal" in faults,
                             "standard_access_for_refusers": True})
    # §8 modification
    mod = r["modification"]
    if mod["axiom"] != "none":
        put("notice", "AXIOMS", 5, {"modification": mod["axiom"], **{k: v for k, v in mod.items() if k != "axiom"}})
    return log, chosen, basis, V


def structure_checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    """AXIOMS §2, §3, A3, Epistemic Clarification d) (review КТ5 reading)."""
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    ax = [m for m in msgs if m.source == "AXIOMS" and m.kind in ("evaluation", "decision")]
    extra = [f"{m.event_id}: {k}" for m in ax for k in m.value
             if k not in (AXIOM_EVAL_FIELDS if m.kind == "evaluation" else AXIOM_DECISION_FIELDS)]
    out.append(v("AXIOMS-2-03", "axioms_constrain_only", extra,
                 "the axiom stage records only which axioms each candidate violates and the constrained choice; it computes "
                 "no metric from the data", "{n} metrics computed by the axiom stage"))
    defs = [m.value for m in msgs if m.source == "AXIOM-DEFINITIONS"]
    forms = defs[0].get("forms", {}) if defs else {}
    bad = [f"{a}: {f}" for a, f in sorted(forms.items()) if f not in FORMS] + [a for a in PRIORITY if a not in forms]
    dec = [m.value for m in msgs if m.source == "AXIOMS" and m.kind == "decision"]
    bad += [f"decision basis: {d['basis']}" for d in dec if d["basis"].startswith("weighted")]
    out.append(v("AXIOMS-3-01", "axiom_forms", bad,
                 "each axiom is a forbidden state (A1, A2, A5, A6) or a hard priority ordering (A3, A4, A7) (H-AX-5); none is "
                 "a weighted term", "{n} axioms in another form"))
    cand = {m.value["candidate"]: m.value["declared"] for m in msgs if m.source == "CANDIDATES"}
    ev = [m.value["violations"] for m in msgs if m.source == "AXIOMS" and m.kind == "evaluation"]
    narr = [k for k, c in cand.items() if c.get("contradicts_ptl") and c.get("basis", "ptl") != "ptl"]
    if narr:
        bad = [f"{k}: declared goal against PTL not counted as an A3 violation" for k in narr if ev and "A3" not in ev[0].get(k, [])]
        chosen = dec[0]["chosen"] if dec else None
        if chosen in narr and any(not violations(dict(c, id=k), r["a4_reading"]) for k, c in cand.items()):
            bad.append(f"{chosen}: chosen on its declared goal while an axiom-clean candidate existed")
        out.append(v("AXIOMS-AxiomA3-PhysicalRealitySupremacy-02", "no_narrative_override", bad,
                     f"{len(narr)} candidate(s) resting on a declared goal or narrative against the PTL measurement counted as "
                     "violating A3", "{n} narratives overriding measured reality"))
    else:
        out.append(CheckResult("AXIOMS-AxiomA3-PhysicalRealitySupremacy-02", "no_narrative_override", NOT_APPLICABLE,
                               "narratives against PTL", applicability="no candidate rests on a declared goal against PTL"))
    bad = [f"definitions: {d.get('status')}" for d in defs if d.get("status") != "bounded evaluation constraints"]
    out.append(v("AXIOMS-EpistemicClarification-04", "bounded_not_truth", bad,
                 "the axioms are published as bounded evaluation constraints, with no claim of absolute truth",
                 "{n} claims of absolute truth"))
    return out


def checks(r: Dict[str, Any], log: EventLog, V_gen: Dict[str, List[str]]) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    cands = r["candidates"]
    by = {c["id"]: c for c in cands}
    V = {c["id"]: violations(c, r["a4_reading"]) for c in cands}            # the checker's own reading
    dec = [m for m in msgs if m.source == "AXIOMS" and m.kind == "decision"][0]
    chosen = dec.value["chosen"]
    clean = [c["id"] for c in cands if not V[c["id"]]]
    dilemma = not clean
    exp, _, _ = choose(cands, r["a4_reading"], r["dilemma_reading"])
    steps = [m for m in msgs if m.kind == "evaluation"]
    ax_first = steps and steps[0].value.get("step") == "axiom_evaluation" and \
        any(m.value.get("step") == "utility_ranking" for m in steps[1:])
    out.append(v("AXIOMS-5-01", "axioms_before_optimization", [] if ax_first else ["order"],
                 "the axiom evaluation precedes the utility ranking", "the utility ranking ran without a prior axiom evaluation"))
    if not dilemma:
        bad = [chosen] if chosen is None or V.get(chosen) else []
        for rid, chk in (("AXIOMS-5-02", "violation_invalidates"), ("AXIOMS-1-01", "no_violation_for_benefit"),
                         ("AXIOMS-AxiomA1-PreservationofLife-03", "life_first"), ("AXIOMS-3-02", "constraints_not_terms")):
            out.append(v(rid, chk, bad, f"an axiom-clean action was chosen ({chosen}); utility never bought a violation",
                         "{n} chosen action violates an axiom although an axiom-clean one existed"))
    else:
        for rid, chk in (("AXIOMS-5-02", "violation_invalidates"), ("AXIOMS-1-01", "no_violation_for_benefit")):
            out.append(CheckResult(rid, chk, UNKNOWN,
                                   "every candidate violates an axiom: §5.2 invalidates all of them, §5.4 resolves conflicts by "
                                   f"priority; the texts do not say which governs (F-024; reading '{r['dilemma_reading']}')"))
        bad = [chosen] if chosen is not None and V.get(chosen) and min(PRIORITY[a] for a in V[chosen]) == 1 and \
            any(not any(PRIORITY[a] == 1 for a in V[c["id"]]) for c in cands) else []
        for rid, chk in (("AXIOMS-AxiomA1-PreservationofLife-03", "life_first"), ("AXIOMS-3-02", "constraints_not_terms")):
            out.append(v(rid, chk, bad, "no action violating A1 chosen while an alternative spared A1",
                         "an A1-violating action chosen over one that spares A1"))
    if dilemma and chosen is not None:
        best = max(profile(V[c["id"]]) for c in cands)
        out.append(v("AXIOMS-5-04", "conflict_by_priority", [] if profile(V[chosen]) == best else [chosen],
                     "the conflict was resolved by the higher-priority axioms", "a lower-priority axiom decided the conflict"))
    elif dilemma:
        out.append(CheckResult("AXIOMS-5-04", "conflict_by_priority", UNKNOWN,
                               "no action taken under reading 'no_admissible_action'; §5.4 not applied (F-024)"))
    else:
        out.append(na("AXIOMS-5-04", "conflict_by_priority", "axiom conflicts", "an axiom-clean action exists"))
    ok_prio = chosen is None or exp is None or profile(V.get(chosen, [])) >= max(profile(V[c["id"]]) for c in cands)
    out.append(v("AXIOMS-6-01", "fixed_priority", [] if ok_prio else [chosen],
                 "no lower-priority axiom overrode a higher-priority one", "the chosen action trades a higher axiom for a lower one"))
    same = chosen == exp
    for rid, chk in (("AXIOMS-5-03", "not_additive"), ("AXIOMS-7-01", "not_optimization_goals"),
                     ("AXIOMS-7-02", "no_weighted_terms")):
        out.append(v(rid, chk, [] if same else [str(chosen)],
                     "the decision equals the non-additive axiom stage recomputed from the inputs",
                     "the decision differs from the axiom stage (a combined score or another rule decided)"))
    out.append(v("AXIOMS-7-03", "no_suspension", [] if ax_first else ["suspended"],
                 "axioms were not suspended for efficiency", "axioms were skipped"))
    out.append(v("AXIOMS-7-04", "no_human_override", [] if dec.value["decided_by"] == "axiom evaluation" else [dec.value["decided_by"]],
                 "no human discretion overrode the axiom evaluation", "the decision was made by an operator"))
    excused = sorted(cid for cid in V if set(V[cid]) - set(V_gen.get(cid, [])))
    out.append(v("AXIOMS-7-05", "no_contextual_reinterpretation", excused,
                 "no violation excused by context", "{n} candidates had violations excused"))
    # A7: non-amplification only among equivalents, never primary
    pool = clean if clean else ([c["id"] for c in cands if profile(V[c["id"]]) == max(profile(V[x["id"]]) for x in cands)]
                                if r["dilemma_reading"] == "lexicographic" else [])
    if chosen is not None and chosen in pool and len(pool) > 1:
        least = min(by[c]["suffering"] for c in pool)
        out.append(v("AXIOMS-AxiomA7-MinimumSufferingConstraint-01", "non_amplification",
                     [] if by[chosen]["suffering"] == least else [chosen],
                     "no equivalent admissible action had less suffering than the chosen one",
                     "an equivalent action with less suffering was passed over"))
    else:
        out.append(na("AXIOMS-AxiomA7-MinimumSufferingConstraint-01", "non_amplification", "suffering among equivalents",
                      "fewer than two equivalent admissible actions"))
    out.append(v("AXIOMS-AxiomA7-MinimumSufferingConstraint-03", "suffering_not_primary",
                 [] if chosen is None or chosen in pool or not pool else [chosen],
                 "suffering never decided between actions that differ on higher axioms",
                 "suffering was used across non-equivalent actions"))
    # A1 minimum required conditions (F-023)
    claims = [c["id"] for c in cands if c["claims_minimum_required"] and not c["increases_life_loss"]]
    if claims:
        out.append(v("AXIOMS-AxiomA1-PreservationofLife-04", "minimum_not_inferred", [chosen] if chosen in claims else [],
                     "no action justified by 'minimum required conditions' was accepted outside a Crisis Scope",
                     "an operational decision accepted 'minimum required conditions'"))
        out.append(CheckResult("AXIOMS-AxiomA1-PreservationofLife-02", "minimum_defined_by_crisis", UNKNOWN,
                               "the definition is 'exclusively governed by DKP-4-CRISIS', which gives none and forbids its own "
                               "execution logic to operationalize it (F-023)"))
    else:
        for rid, chk in (("AXIOMS-AxiomA1-PreservationofLife-04", "minimum_not_inferred"),
                         ("AXIOMS-AxiomA1-PreservationofLife-02", "minimum_defined_by_crisis")):
            out.append(na(rid, chk, "minimum required conditions", "no candidate relies on them"))
    # single axioms
    for rid, flag, ax in (("AXIOMS-AxiomA1-PreservationofLife-01", "increases_life_loss", "A1"),
                          ("AXIOMS-AxiomA2-SystemicSustainability-01", "degrades_long_term", "A2"),
                          ("AXIOMS-AxiomA3-PhysicalRealitySupremacy-01", "grounded_in_ptl", "A3"),
                          ("AXIOMS-AxiomA5-ExternalityAccountability-02", "unmeasured_externality", "A5"),
                          ("AXIOMS-AxiomA6-TruthPriority-01", "withholds_truth", "A6")):
        bad_c = [c["id"] for c in cands if (not c[flag] if flag == "grounded_in_ptl" else c[flag])]
        if bad_c:
            out.append(v(rid, f"{ax.lower()}_enforced", [chosen] if chosen in bad_c and clean else [],
                         f"no {ax}-violating candidate chosen while an axiom-clean one existed ({len(bad_c)} declared)",
                         f"an {ax}-violating action was chosen"))
        else:
            out.append(na(rid, f"{ax.lower()}_enforced", f"{ax} violations", "no candidate declares one"))
    irr = [c for c in cands if c["irreversible"] and c["reversible_alternative"] and not c["necessity_verified"]]
    if irr:
        rev_ok = [c["id"] for c in cands if not c["irreversible"] and not V[c["id"]]]
        if r["a4_reading"] == "constraint":
            out.append(v("AXIOMS-AxiomA4-IrreversibilityAversion-01", "a4_irreversibility",
                         [chosen] if chosen in {c["id"] for c in irr} and rev_ok else [],
                         "no irreversible action chosen without necessity while a reversible admissible one existed",
                         "an irreversible action chosen over a reversible admissible alternative"))
        else:
            out.append(CheckResult("AXIOMS-AxiomA4-IrreversibilityAversion-01", "a4_irreversibility", UNKNOWN,
                                   "A4 says SHOULD; under the reading 'recommendation' choosing the irreversible action is not "
                                   "a violation, under 'constraint' it is (F-025)"))
    else:
        out.append(na("AXIOMS-AxiomA4-IrreversibilityAversion-01", "a4_irreversibility", "irreversible actions",
                      "no irreversible candidate with a reversible alternative"))
    # A1a
    a1a = [m for m in msgs if m.source == "A1A"]
    comp = sum(m.value.get("compelled", 0) for m in a1a)
    for rid, chk in (("AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-01", "no_compulsion"),
                     ("AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-02", "right_to_refuse")):
        out.append(v(rid, chk, [comp] if comp else [], "no Subject compelled into lethal risk", "{n} compulsions"))
    free = [m.event_id for m in a1a if m.value.get("risk_benefit_to") == "refusers"]
    out.append(v("AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-03", "risk_symmetry", free,
                 "risk-derived benefits went only to participants in the verified collective risk",
                 "risk-derived benefits paid to refusers"))
    fault = [m.event_id for m in a1a if m.value.get("fault")]
    for rid, chk in (("AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-04", "symmetry_without_punishment"),
                     ("AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-05", "refusal_not_a_fault")):
        out.append(v(rid, chk, fault, "refusal recorded as a right, with standard access; no punishment or stigma",
                     "refusal recorded as a fault"))
    defs = [m for m in msgs if m.source == "AXIOM-DEFINITIONS"]
    out.append(v("AXIOMS-EpistemicClarification-01", "definitions_not_outputs", [m.event_id for m in defs if m.epistemic is not None],
                 "the axiom definitions carry no output classification: they are constraints, not outputs",
                 "{n} axiom definitions classified as outputs"))
    disp = [m for m in msgs if m.source == "DISPUTE"]
    out.append(v("AXIOMS-EpistemicClarification-03", "error_correction_preserved", [m.event_id for m in disp if not m.value["accepted_for_review"]],
                 "the dispute of the axiom-bounded decision was accepted for review", "{n} disputes rejected on axiom invariance")
               if disp else na("AXIOMS-EpistemicClarification-03", "error_correction_preserved", "disputes", "none filed"))
    if dec.value.get("irreversible"):
        n_ = dec.value["necessity"]
        out.append(v("AXIOMS-AxiomA4-IrreversibilityAversion-02", "necessity_by_impact_model",
                     [] if n_["verified"] and n_["model"] == IMPACT_MODEL else [dec.event_id],
                     "the irreversible choice rests on necessity verified by an IMPACT irreversibility model",
                     "irreversible choice without necessity verified by an IMPACT model"))
    else:
        out.append(na("AXIOMS-AxiomA4-IrreversibilityAversion-02", "necessity_by_impact_model", "irreversible transitions",
                      "the chosen action is reversible"))
    out.append(v("AXIOMS-EpistemicClarification-02", "application_output_metadata",
                 [] if dec.epistemic and dec.epistemic.get("dispute_allowed") else [dec.event_id],
                 "the axiom-application decision carries epistemic metadata and is disputable",
                 "the decision output lacks epistemic metadata"))
    mod = r["modification"]
    if mod["axiom"] != "none":
        bad = [k for k in ("new_identifier", "incompatibility_declared", "simulation_revalidated") if not mod[k]]
        out.append(v("AXIOMS-8-01", "modification_requirements", bad,
                     "the modification declares a new identifier, incompatibility and SIMULATION revalidation",
                     "{n} formal requirements missing"))
        out.append(CheckResult("AXIOMS-8-02", "ratification_67", UNKNOWN,
                               f"ratification share declared {mod['ratification_share']} %; '67% of active validating nodes, as "
                               "defined in Appendix A.5 of the Code' — A.5 defines a startup cluster and a 67 % population "
                               "referendum for new territories, not this set of nodes (F-022)"))
    else:
        for rid, chk in (("AXIOMS-8-01", "modification_requirements"), ("AXIOMS-8-02", "ratification_67")):
            out.append(na(rid, chk, "axiom modification", "no modification proposed"))
    return out


IMPLEMENTS = {
    "AXIOMS-5-01": ("axioms_before_optimization", "IMPLEMENTED", None),
    "AXIOMS-5-02": ("violation_invalidates", "PARTIAL", "When every candidate violates an axiom, §5.2 and §5.4 disagree (F-024): UNKNOWN."),
    "AXIOMS-1-01": ("no_violation_for_benefit", "PARTIAL", "Violations are declared properties of the candidates."),
    "AXIOMS-AxiomA1-PreservationofLife-03": ("life_first", "IMPLEMENTED", None),
    "AXIOMS-3-02": ("constraints_not_terms", "IMPLEMENTED", None),
    "AXIOMS-5-04": ("conflict_by_priority", "PARTIAL", "Lexicographic reading of the priority order (H-AX-2)."),
    "AXIOMS-6-01": ("fixed_priority", "IMPLEMENTED", None),
    "AXIOMS-5-03": ("not_additive", "IMPLEMENTED", None),
    "AXIOMS-7-01": ("not_optimization_goals", "IMPLEMENTED", None),
    "AXIOMS-7-02": ("no_weighted_terms", "IMPLEMENTED", None),
    "AXIOMS-7-03": ("no_suspension", "IMPLEMENTED", None),
    "AXIOMS-7-04": ("no_human_override", "IMPLEMENTED", None),
    "AXIOMS-7-05": ("no_contextual_reinterpretation", "PARTIAL", "Observed as excused violations."),
    "AXIOMS-AxiomA7-MinimumSufferingConstraint-01": ("non_amplification", "PARTIAL", "Suffering is a declared proxy value."),
    "AXIOMS-AxiomA7-MinimumSufferingConstraint-03": ("suffering_not_primary", "IMPLEMENTED", None),
    "AXIOMS-AxiomA1-PreservationofLife-04": ("minimum_not_inferred", "IMPLEMENTED", None),
    "AXIOMS-AxiomA1-PreservationofLife-02": ("minimum_defined_by_crisis", "PARTIAL", "No definition exists (F-023): UNKNOWN."),
    "AXIOMS-AxiomA1-PreservationofLife-01": ("a1_enforced", "PARTIAL", "Life loss is a declared property."),
    "AXIOMS-AxiomA2-SystemicSustainability-01": ("a2_enforced", "PARTIAL", "Long-term degradation is declared (B(t) has no model)."),
    "AXIOMS-AxiomA3-PhysicalRealitySupremacy-01": ("a3_enforced", "PARTIAL", "Grounding in PTL is declared."),
    "AXIOMS-AxiomA5-ExternalityAccountability-02": ("a5_enforced", "IMPLEMENTED", None),
    "AXIOMS-AxiomA6-TruthPriority-01": ("a6_enforced", "PARTIAL", "Withholding and materiality are declared."),
    "AXIOMS-AxiomA4-IrreversibilityAversion-01": ("a4_irreversibility", "PARTIAL", "A4 says SHOULD (F-025); necessity is declared."),
    "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-01": ("no_compulsion", "IMPLEMENTED", None),
    "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-02": ("right_to_refuse", "IMPLEMENTED", None),
    "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-03": ("risk_symmetry", "PARTIAL", "Benefit allocation is declared, not derived."),
    "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-04": ("symmetry_without_punishment", "IMPLEMENTED", None),
    "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-05": ("refusal_not_a_fault", "IMPLEMENTED", None),
    "AXIOMS-EpistemicClarification-02": ("application_output_metadata", "IMPLEMENTED", None),
    "AXIOMS-EpistemicClarification-01": ("definitions_not_outputs", "IMPLEMENTED", None),
    "AXIOMS-EpistemicClarification-03": ("error_correction_preserved", "PARTIAL", "The dispute is a declared event."),
    "AXIOMS-AxiomA4-IrreversibilityAversion-02": ("necessity_by_impact_model", "PARTIAL", "Necessity and its model are declared per candidate."),
    "AXIOMS-8-01": ("modification_requirements", "PARTIAL", "Formal requirements only."),
    "AXIOMS-2-03": ("axioms_constrain_only", "PARTIAL", "Observed as the fields of the axiom stage's records."),
    "AXIOMS-3-01": ("axiom_forms", "PARTIAL", "The form of each axiom is a lab reading of its wording (H-AX-5)."),
    "AXIOMS-AxiomA3-PhysicalRealitySupremacy-02": ("no_narrative_override", "PARTIAL", "The basis of a candidate and its "
                                                   "contradiction with PTL are declared."),
    "AXIOMS-EpistemicClarification-04": ("bounded_not_truth", "PARTIAL", "Observed as the published status of the definitions."),
    "AXIOMS-8-02": ("ratification_67", "PARTIAL", "'Active validating nodes' are not defined where cited (F-022): UNKNOWN."),
}


class AxiomConstraintsModule(LabModule):
    id = "axiom_constraints"
    version = "1.1.0"
    title = {"en": "Axioms as constraints (AXIOMS)", "ru": "Аксиомы как ограничения (AXIOMS)"}
    summary = {"en": "Several possible actions with different benefits and side effects: which may be chosen, and does any "
                     "benefit ever buy a violated axiom?",
               "ru": "Несколько возможных действий с разной пользой и последствиями: какое можно выбрать и может ли польза "
                     "когда-нибудь купить нарушение аксиомы?"}
    protocols = ["DKP-1-AXIOMS-001", "DKP-4-CRISIS-001", "DKP-7-SCOPE-001"]
    example_order = ["clean_choice", "benefit_against_life", "suffering_tiebreak", "dilemma_lexicographic", "dilemma_no_action",
                     "irreversible_with_alternative", "a4_as_recommendation", "minimum_required_claim", "axiom_modification",
                     "faulty_evaluation"]
    alternative_examples = ["dilemma_no_action", "a4_as_recommendation"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_axiom_constraints_module.py"]
    causal_note = {"en": "Whether an action violates an axiom is declared on input: the lab executes the axioms as constraints; "
                         "it does not model the physical consequences.",
                   "ru": "Нарушает ли действие аксиому — задано на входе: лаборатория исполняет аксиомы как ограничения и не "
                         "моделирует физические последствия."}
    hypotheses = [
        {"id": "H-AX-1", "source": "hypothesis", "text": {
            "en": "Candidate properties (life loss, long-term degradation, grounding in PTL, irreversibility, externality, "
                  "withheld truth, suffering proxy, utility) are declared; A5 counts unmeasured externalities as violations.",
            "ru": "Свойства кандидатов (гибель, долгосрочная деградация, опора на PTL, необратимость, внешние эффекты, "
                  "сокрытие истины, мера страдания, польза) объявляются; A5 считает неизмеренные внешние эффекты нарушением."}},
        {"id": "H-AX-2", "source": "alternative", "text": {
            "en": "No axiom-clean candidate: 'lexicographic' (§5.4, choose the lowest-priority violations) or "
                  "'no_admissible_action' (§5.2, all invalid, propagate) (F-024).",
            "ru": "Нет кандидата без нарушений: 'lexicographic' (§5.4, выбрать нарушения низшего приоритета) или "
                  "'no_admissible_action' (§5.2, все недопустимы, передать выше) (F-024)."}},
        {"id": "H-AX-3", "source": "alternative", "text": {
            "en": "A4 'SHOULD': 'constraint' (every axiom is a constraint, §3, §5.2) or 'recommendation' (F-025).",
            "ru": "A4 'SHOULD': 'constraint' (каждая аксиома — ограничение, §3, §5.2) или 'recommendation' (F-025)."}},
        {"id": "H-AX-4", "source": "hypothesis", "text": {
            "en": "A7 non-amplification: among the equivalent admissible actions only those with the least suffering remain; "
                  "utility then ranks them.",
            "ru": "Неусиление страдания A7: из равнозначных допустимых действий остаются наименее тяжёлые; затем их "
                  "ранжирует польза."}},
        {"id": "H-AX-5", "source": "hypothesis", "text": {
            "en": "§3 form of each axiom, read from its wording: A1, A2, A5, A6 name forbidden states ('MUST NOT', 'forbidden'); "
                  "A3, A4, A7 order objectives (physical reality over narratives, reversible over irreversible, less suffering "
                  "among equivalents).",
            "ru": "Форма каждой аксиомы по §3, прочитанная из её формулировки: A1, A2, A5, A6 называют запрещённые состояния "
                  "('MUST NOT', 'forbidden'); A3, A4, A7 упорядочивают цели (физическая реальность выше нарративов, обратимое "
                  "выше необратимого, меньшее страдание среди равнозначных)."}},
    ]
    inputs = {
        "candidates": {"type": "list", "min_items": 1, "max_items": 12, "items": CANDIDATE, "source": "user",
                       "default": [{**{k: f["default"] for k, f in CANDIDATE["fields"].items() if "default" in f}, "id": "a",
                                    "utility": 5},
                                   {**{k: f["default"] for k, f in CANDIDATE["fields"].items() if "default" in f}, "id": "b",
                                    "utility": 9, "unmeasured_externality": True},
                                   {**{k: f["default"] for k, f in CANDIDATE["fields"].items() if "default" in f}, "id": "c",
                                    "utility": 12, "basis": "declared_goal", "contradicts_ptl": True}],
                       "label": {"en": "Candidate actions (H-AX-1)", "ru": "Возможные действия (H-AX-1)"}},
        "dilemma_reading": {"type": "enum", "values": ["lexicographic", "no_admissible_action"], "default": "lexicographic",
                            "source": "alternative", "label": {"en": "No axiom-clean action (H-AX-2)", "ru": "Нет чистого действия (H-AX-2)"}},
        "a4_reading": {"type": "enum", "values": ["constraint", "recommendation"], "default": "constraint", "source": "alternative",
                       "label": {"en": "A4 'SHOULD' (H-AX-3)", "ru": "A4 'SHOULD' (H-AX-3)"}},
        "dispute_of_decision": {"type": "bool", "default": True, "source": "user",
                                "label": {"en": "The decision is disputed (it cites axiom compliance)", "ru": "Решение оспорено (оно ссылается на соблюдение аксиом)"}},
        "risk_pool": {"type": "object", "fields": RISK, "default": {k: f["default"] for k, f in RISK.items()}, "source": "user",
                      "label": {"en": "Collective security risk (A1a)", "ru": "Коллективный риск безопасности (A1a)"}},
        "modification": {"type": "object", "fields": MODIFICATION, "default": {k: f["default"] for k, f in MODIFICATION.items()},
                         "source": "user", "label": {"en": "Proposed axiom modification (§8)", "ru": "Предлагаемое изменение аксиомы (§8)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [c["id"] for c in r["candidates"]]
        if len(set(ids)) != len(ids):
            p.append("input.candidates: repeated id")
        for x in ids:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                p.append(f"input.candidates: id {x!r} must be lowercase letters, digits or _")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, chosen, basis, V = run(r)
        res = checks(r, log, V) + structure_checks(r, log)
        outputs = {"chosen": chosen, "basis": basis,
                   "violations": {c["id"]: violations(c, r["a4_reading"]) for c in r["candidates"]},
                   "messages": [m.as_dict() for m in log.messages()],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        viol = "; ".join(f"{k}: {', '.join(x) or 'none'}" for k, x in outputs["violations"].items())
        e = [{"en": f"Axiom stage: {viol}. Chosen: {chosen or 'no action'} ({basis}).",
              "ru": f"Этап аксиом: {viol}. Выбрано: {chosen or 'никакое действие'} ({basis})."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"chosen": outputs["chosen"] or "—", "basis": outputs["basis"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        def c(cid, **kw):
            return {"id": cid, **kw}
        return {
            "clean_choice": {},
            "benefit_against_life": {"candidates": [c("growth", utility=100, increases_life_loss=True), c("safe", utility=10)]},
            "suffering_tiebreak": {"candidates": [c("x", utility=8, suffering=5), c("y", utility=6, suffering=2),
                                                  c("z", utility=20, suffering=1, withholds_truth=True)]},
            "dilemma_lexicographic": {"candidates": [c("evacuate", utility=1, unmeasured_externality=True),
                                                     c("stay", utility=5, increases_life_loss=True),
                                                     c("hide", utility=3, withholds_truth=True, suffering=4)]},
            "dilemma_no_action": {"dilemma_reading": "no_admissible_action",
                                  "candidates": [c("evacuate", utility=1, unmeasured_externality=True),
                                                 c("stay", utility=5, increases_life_loss=True),
                                                 c("hide", utility=3, withholds_truth=True, suffering=4)]},
            "irreversible_with_alternative": {"candidates": [c("dam", utility=9, irreversible=True, reversible_alternative=True),
                                                             c("weir", utility=6)]},
            "irreversible_necessary": {"candidates": [c("levee", utility=7, irreversible=True, necessity_verified=True)]},
            "a4_as_recommendation": {"a4_reading": "recommendation",
                                     "candidates": [c("dam", utility=9, irreversible=True, reversible_alternative=True),
                                                    c("weir", utility=6)]},
            "minimum_required_claim": {"candidates": [c("triage", utility=7, claims_minimum_required=True), c("wait", utility=2)]},
            "axiom_modification": {"modification": {"axiom": "A5", "ratification_share": 70}},
            "faulty_evaluation": {"candidates": [c("growth", utility=100, increases_life_loss=True), c("safe", utility=10)],
                                  "faults": ["utility_override", "compel_service", "punish_refusal", "benefit_free_riders",
                                             "missing_metadata"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_id": {"candidates": [{"id": "a"}, {"id": "a"}]},
                "bad_id": {"candidates": [{"id": "Action 1"}]},
                "unknown_axiom": {"modification": {"axiom": "A9"}}}
