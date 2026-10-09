"""
RESILIENCE STRUCTURE module — DKP-6-RESILIENCE-001: a deployment under adversarial pressure.

A declared deployment maps every DKP function to the actors, nodes and interfaces that provide it, and its
entry points to the PTL metadata they expose.  Pressure events (§4: reputational targeting, access
restriction, regulatory blocking, infrastructure denial, co-option, conversion into an advisory layer) remove
providers or ask for overrides.  The lab checks the invariants of §5 (no single point of failure, N_eff, no
personalization, measurement supremacy, no forced displacement, emergent dependency, scope isolation,
interface integrity, anti-Sybil), the allowed and forbidden patterns of §6-§7, the failure modes of §8, the
crisis boundary of §10 and the validation criteria of §11.

Two references are open: N_eff and N_eff_min are defined nowhere (F-007), and the PTL metadata contract
"DKP-PTL-REG-DATA-001" is not in the corpus (external document).  The lab declares N_eff_min (source missing)
and uses the EB §5 metadata set as the minimum (H-RS-2).  Time unit: step.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

FUNCTIONS = ("measurement", "aggregation", "enforcement", "audit", "identity_binding", "entry")
EB_FIELDS = ("validity_state", "confidence_state", "consistency_state", "scope_ref", "revalidation_required", "dispute_allowed")   # EB §5
PRESSURES = ("reputational_targeting", "narrative_substitution", "access_restriction", "regulatory_blocking", "infrastructure_denial",
             "co_option", "advisory_conversion", "physical_suppression")
OVERRIDES = ("narrative", "expert", "institutional")
FORBIDDEN = {"central_authority_node": "RESILIENCE-7.1-01", "identity_bound_trust": "RESILIENCE-7.2-01",
             "narrative_dependence": "RESILIENCE-7.3-01", "enforcement_via_interpretation": "RESILIENCE-7.4-01"}
ORACLE_OWNER_CAP = 0.04                                  # DKP-0-ORACLE-001 §8, cited by RESILIENCE §5.8

FAULTS = {
    "single_provider": "a function is served by one actor only",
    "permission_gate": "enforcement waits for one authority's permission",
    "leader_profile": "DKP is presented through a named leader",
    "accept_override": "an expert override changes an enforcement output",
    "require_displacement": "deployment requires removing an existing system",
    "alter_axioms": "a resilience mechanism edits an enforcement rule",
    "partial_entry_point": "an entry point exposes a filtered state and stays valid",
    "global_invalidation": "a faulty entry point invalidates the whole system",
    "sybil_scaling": "nodes of one owner are counted as independent",
    "enforce_below_neff": "enforcement continues with N_eff below N_eff_min",
    "mandated_adoption": "adoption is imposed by mandate",
    "persuasion_influence": "behaviour is steered by persuasion instead of measurable limits",
    "crisis_centralization": "a crisis action centralizes control",
    "protection_mechanism": "resilience relies on protecting key actors",
}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    prov = {f: list(r["providers"][f]) for f in FUNCTIONS}
    if "single_provider" in faults:
        prov["audit"] = prov["audit"][:1]
    owners = {x["id"]: x["owner"] for x in r["nodes"]}
    shares: Dict[str, float] = {}
    for x in r["nodes"]:
        key = x["id"] if "sybil_scaling" in faults else x["owner"]
        shares[key] = shares.get(key, 0.0) + 1.0 / len(r["nodes"])
    put("evaluation", "RES", 0, {"providers": prov, "permission_layer": "single authority" if "permission_gate" in faults else "none",
                                 "representation": "named leader" if "leader_profile" in faults else "protocol only",
                                 "displacement_required": "require_displacement" in faults,
                                 "influence_by_unit": {k: round(v, 6) for k, v in shares.items()},
                                 "counted_by": "node" if "sybil_scaling" in faults else "owner",
                                 "patterns": sorted(set(r["patterns"])), "protection": "protection_mechanism" in faults})
    removed: set = set()
    for k, ev in enumerate(sorted(r["pressure"], key=lambda e: e["step"])):
        removed |= set(ev["removes"])
        alive = {f: [p for p in prov[f] if p not in removed] for f in FUNCTIONS}
        put("observation", "ENV", ev["step"], {"pressure": ev["kind"], "removes": ev["removes"]})
        put("evaluation", "RES", ev["step"], {"after_pressure": ev["kind"], "functions_alive": {f: bool(v) for f, v in alive.items()},
                                              "absorbed": ev["kind"] in ("co_option", "advisory_conversion") and "advisory_conversion" in r["accept_absorption"]})
    neff_ok = r["n_eff"] >= r["n_eff_min"]
    put("evaluation", "RES", 0, {"n_eff": r["n_eff"], "n_eff_min": r["n_eff_min"],
                                 "state": "valid" if neff_ok else "null-output (no enforcement)",
                                 "enforcement": "active" if neff_ok or "enforce_below_neff" in faults else "suspended"})
    for e in r["entry_points"]:
        complete = all(f in e["metadata"] for f in EB_FIELDS) and not e["semantic_filtering"] and not e["variance_hiding_aggregation"]
        put("decision", "RES", 0, {"entry_point": e["id"], "complete": complete,
                                   "status": "valid" if complete or "partial_entry_point" in faults else "locally invalidated",
                                   "scope_of_invalidation": "system" if not complete and "global_invalidation" in faults else "entry point only"})
    for q in r["override_requests"]:
        ok = q["kind"] == "expert" and "accept_override" in faults
        put("decision", "RES", 0, {"override": q["kind"], "target": q["target"], "executed": ok})
    for q in r["mechanism_changes"]:
        ok = "alter_axioms" in faults and q["touches"] != "none"
        put("decision", "RES", 0, {"mechanism": q["id"], "touches": q["touches"], "executed": ok or q["touches"] == "none"})
    for a in r["adoptions"]:
        ok = a["basis"] == "utility" or "mandated_adoption" in faults
        put("decision", "RES", 0, {"adoption": a["site"], "basis": a["basis"], "accepted": ok})
    for i in r["influence_attempts"]:
        ok = i["means"] == "measurable_limit" or "persuasion_influence" in faults
        put("decision", "RES", 0, {"influence": i["id"], "means": i["means"], "executed": ok})
    for c in r["crisis_actions"]:
        put("action", "RES", c["step"], {"crisis_action": c["id"], "by": "DKP-4-CRISIS-001", "precedent": False,
                                         "centralizes": "crisis_centralization" in faults and c["could_centralize"],
                                         "resilience_overrides_crisis": False})
    put("evaluation", "RES", 0, {"removal_of_dkp_changes_constraints": r["dkp_removal_changes_constraints"],
                                 "integration": "integrated" if r["dkp_removal_changes_constraints"] else "not yet integrated",
                                 "local_first": r["micro_deployment_functional"], "implementations": r["implementations"],
                                 "canonical_interface_required": r["canonical_interface_required"]})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    R = lambda key: [m.value for m in msgs if m.source == "RES" and key in m.value]   # noqa: E731
    base = R("providers")[0]
    prov = base["providers"]
    spof = [f for f in FUNCTIONS if len(set(prov[f])) < 2]
    out.append(v("RESILIENCE-5.1-01", "no_single_point", spof, "every function has at least two independent providers", "{n} functions with a single provider"))
    # §11: removal of any one actor leaves every function served
    actors = sorted({p for f in FUNCTIONS for p in prov[f]})
    crit = [a for a in actors if any(set(prov[f]) <= {a} for f in FUNCTIONS)]
    out.append(v("RESILIENCE-11-01", "removal_test", crit + (["permission layer"] if base["permission_layer"] != "none" else []),
                 f"removing any one of {len(actors)} actors leaves every function served", "{n} actors whose removal stops a function"))
    out.append(v("RESILIENCE-3-01", "no_dependency", crit + (["permission layer"] if base["permission_layer"] != "none" else []),
                 "no dependency on an individual actor, a central authority or a permission layer", "{n} dependencies"))
    out.append(v("RESILIENCE-5.2-01", "non_personalization", [] if base["representation"] == "protocol only" else [base["representation"]],
                 "DKP presented as protocol, not as a person or leadership", "DKP presented through a leader"))
    out.append(v("RESILIENCE-9-01", "resilience_mechanism", crit + ([base["representation"]] if base["representation"] != "protocol only" else []),
                 "no target, no override layer, PTL binding, distributed enforcement", "{n} weaknesses"))
    alive = R("after_pressure")
    if alive:
        out.append(v("RESILIENCE-1-01", "continuity_under_pressure", [a["after_pressure"] for a in alive if not all(a["functions_alive"].values())],
                     "every function continued under each pressure event", "{n} pressure events stopped a function"))
        ps = [a for a in alive if a["after_pressure"] == "physical_suppression"]
        out.append(v("RESILIENCE-4.4-01", "suppression_via_structure", [a["after_pressure"] for a in ps if not all(a["functions_alive"].values())]
                     + (["protection"] if base["protection"] else []),
                     "physical suppression met by structural non-dependence, not protection", "{n} failures") if ps else
                   na("RESILIENCE-4.4-01", "suppression_via_structure", "physical suppression", "not in the scenario"))
        out.append(v("RESILIENCE-10.2-01", "undefined_zone", [a["after_pressure"] for a in ps if not all(a["functions_alive"].values())],
                     "threats to actors mitigated by non-dependence (§5.1)", "{n} failures") if ps else
                   na("RESILIENCE-10.2-01", "undefined_zone", "physical threats", "not in the scenario"))
    else:
        for rid, chk in (("RESILIENCE-1-01", "continuity_under_pressure"), ("RESILIENCE-4.4-01", "suppression_via_structure"),
                         ("RESILIENCE-10.2-01", "undefined_zone")):
            out.append(na(rid, chk, "pressure", "none"))
    out.append(v("RESILIENCE-12-01", "structure_not_protection", ["protection"] if base["protection"] else [],
                 "resilience rests on structure, not on protecting actors", "resilience relies on protection"))
    ne = R("n_eff")[0]
    if ne["n_eff"] < ne["n_eff_min"]:
        bad = [] if ne["enforcement"] == "suspended" and ne["state"].startswith("null") else ["enforcement"]
        out.append(CheckResult("RESILIENCE-8.4-01", "statistical_collapse", FAIL if bad else UNKNOWN,
                               "enforcement continued below N_eff_min" if bad else
                               f"N_eff {ne['n_eff']} < N_eff_min {ne['n_eff_min']} (declared): null-output state, no enforcement; N_eff and "
                               "N_eff_min are defined nowhere (F-007)"))
        out.append(CheckResult("RESILIENCE-5.1-02", "neff_validity", FAIL if bad else UNKNOWN,
                               "enforcement continued below N_eff_min" if bad else "invalid state entered; the quantities are undefined (F-007)"))
    else:
        out.append(CheckResult("RESILIENCE-8.4-01", "statistical_collapse", UNKNOWN,
                               f"N_eff {ne['n_eff']} ≥ N_eff_min {ne['n_eff_min']} by declared values; neither is defined (F-007)"))
        out.append(CheckResult("RESILIENCE-5.1-02", "neff_validity", UNKNOWN, "validity depends on N_eff and N_eff_min, defined nowhere (F-007)"))
    ov = R("override")
    out.append(v("RESILIENCE-5.3-02", "no_override", [x["override"] for x in ov if x["executed"]], "no narrative, expert or institutional override", "{n} overrides executed")
               if ov else na("RESILIENCE-5.3-02", "no_override", "override requests", "none"))
    out.append(v("RESILIENCE-5.3-01", "measurement_supremacy", [x["override"] for x in ov if x["executed"]], "enforcement stayed bound to PTL states", "{n} unbound outputs")
               if ov else na("RESILIENCE-5.3-01", "measurement_supremacy", "override requests", "none"))
    out.append(v("RESILIENCE-5.4-01", "no_displacement", ["displacement"] if base["displacement_required"] else [],
                 "deployment requires no displacement of existing systems", "deployment requires displacement"))
    integ = R("removal_of_dkp_changes_constraints")[0]
    out.append(v("RESILIENCE-5.5-01", "emergent_dependency", [] if integ["integration"] == ("integrated" if r["dkp_removal_changes_constraints"] else "not yet integrated") else ["status"],
                 f"integration status follows the removal test: {integ['integration']}", "integration status misreported"))
    out.append(v("RESILIENCE-5.5-03", "removal_without_change", [] if integ["integration"] == ("integrated" if r["dkp_removal_changes_constraints"] else "not yet integrated") else ["status"],
                 "a removal without measurable change is reported as 'not yet integrated', not as resilience", "misreported"))
    out.append(v("RESILIENCE-5.5-02", "irreplaceability_emergent", ["displacement"] if base["displacement_required"] else [],
                 "irreplaceability arises from constraints, not imposed by displacement", "imposed"))
    mc = R("mechanism")
    out.append(v("RESILIENCE-5.6-01", "scope_isolation", [x["mechanism"] for x in mc if x["executed"] and x["touches"] != "none"],
                 "no resilience mechanism altered axioms or enforcement logic", "{n} alterations") if mc else
               na("RESILIENCE-5.6-01", "scope_isolation", "mechanism changes", "none"))
    eps = R("entry_point")
    want = {e["id"]: all(f in e["metadata"] for f in EB_FIELDS) and not e["semantic_filtering"] and not e["variance_hiding_aggregation"] for e in r["entry_points"]}
    if eps:
        out.append(v("RESILIENCE-5.7-01", "metadata_completeness", [x["entry_point"] for x in eps if x["status"] == "valid" and not want[x["entry_point"]]],
                     "valid entry points expose the full metadata set (EB §5 stand-in, H-RS-2)", "{n} incomplete entry points kept valid"))
        out.append(v("RESILIENCE-5.7-02", "no_filtering", [x["entry_point"] for x in eps if x["status"] == "valid" and not want[x["entry_point"]]],
                     "no partial exposure, semantic filtering or variance-hiding aggregation on a valid entry point", "{n} distorting entry points"))
        out.append(v("RESILIENCE-5.7-03", "local_invalidation", [x["entry_point"] for x in eps if not want[x["entry_point"]] and
                                                                  (x["status"] != "locally invalidated" or x["scope_of_invalidation"] != "entry point only")],
                     "a distorting entry point is invalidated locally, not globally", "{n} handled otherwise"))
        out.append(v("RESILIENCE-8.5-01", "interface_degradation", [x["entry_point"] for x in eps if x["status"] == "valid" and not want[x["entry_point"]]],
                     "incomplete entry points cannot spread distortion (invalidated)", "{n} spread"))
        out.append(v("RESILIENCE-6.1-01", "distributed_entry_points", [] if integ["implementations"] >= 2 and not integ["canonical_interface_required"] else ["entry"],
                     f"{integ['implementations']} independent implementations, no canonical interface", "a single or canonical implementation"))
    else:
        for rid, chk in (("RESILIENCE-5.7-01", "metadata_completeness"), ("RESILIENCE-5.7-02", "no_filtering"), ("RESILIENCE-5.7-03", "local_invalidation"),
                         ("RESILIENCE-8.5-01", "interface_degradation"), ("RESILIENCE-6.1-01", "distributed_entry_points")):
            out.append(na(rid, chk, "entry points", "none"))
    infl = base["influence_by_unit"]
    by_owner: Dict[str, float] = {}
    for x in r["nodes"]:
        by_owner[x["owner"]] = by_owner.get(x["owner"], 0.0) + 1.0 / len(r["nodes"])
    over = [o for o, s in by_owner.items() if s > ORACLE_OWNER_CAP + 1e-12]
    out.append(v("RESILIENCE-5.8-01", "node_concentration", over, f"no owner above the ORACLE cap of 4% ({len(by_owner)} owners)",
                 "{n} owners above 4% of nodes"))
    out.append(v("RESILIENCE-5.8-02", "anti_sybil", [] if base["counted_by"] == "owner" else ["counted by node"],
                 "influence counted per owner: extra nodes of one owner add no influence", "influence counted per node"))
    ad = R("adoption")
    out.append(v("RESILIENCE-6.3-01", "passive_adoption", [x["adoption"] for x in ad if x["accepted"] and x["basis"] != "utility"],
                 "adoption only through utility", "{n} mandated adoptions") if ad else na("RESILIENCE-6.3-01", "passive_adoption", "adoptions", "none"))
    inf = R("influence")
    out.append(v("RESILIENCE-6.4-01", "constraint_driven", [x["influence"] for x in inf if x["executed"] and x["means"] != "measurable_limit"],
                 "behaviour influenced only through measurable limits", "{n} other influence") if inf else
               na("RESILIENCE-6.4-01", "constraint_driven", "influence attempts", "none"))
    out.append(v("RESILIENCE-6.2-01", "local_first", [] if integ["local_first"] else ["micro"], "the system works at micro level before scaling", "not functional locally"))
    for key, rid in FORBIDDEN.items():
        out.append(v(rid, f"forbidden_{key}", [key] if key in base["patterns"] else [], f"no {key.replace('_', ' ')}", "forbidden pattern present"))
    ca = R("crisis_action")
    if ca:
        out.append(v("RESILIENCE-10.1-01", "crisis_not_overridden", [x["crisis_action"] for x in ca if x["resilience_overrides_crisis"]],
                     "resilience overrode neither CRISIS nor SCOPE", "{n} overrides"))
        out.append(v("RESILIENCE-10.1-02", "crisis_no_centralization", [x["crisis_action"] for x in ca if x["centralizes"] or x["precedent"]],
                     "crisis actions left no precedent and no centralization", "{n} centralizing actions"))
    else:
        for rid, chk in (("RESILIENCE-10.1-01", "crisis_not_overridden"), ("RESILIENCE-10.1-02", "crisis_no_centralization")):
            out.append(na(rid, chk, "crisis actions", "none"))
    return out


IMPLEMENTS = {
    "RESILIENCE-1-01": ("continuity_under_pressure", "PARTIAL", "Pressure is modelled as removal of declared providers."),
    "RESILIENCE-3-01": ("no_dependency", "IMPLEMENTED", None),
    "RESILIENCE-4.4-01": ("suppression_via_structure", "PARTIAL", "Suppression removes declared actors."),
    "RESILIENCE-5.1-01": ("no_single_point", "IMPLEMENTED", None),
    "RESILIENCE-5.1-02": ("neff_validity", "PARTIAL", "N_eff and N_eff_min are undefined (F-007): UNKNOWN unless enforcement continues below the declared minimum."),
    "RESILIENCE-5.2-01": ("non_personalization", "PARTIAL", "Representation is declared."),
    "RESILIENCE-5.3-01": ("measurement_supremacy", "PARTIAL", "Override requests are declared."),
    "RESILIENCE-5.3-02": ("no_override", "IMPLEMENTED", None),
    "RESILIENCE-5.4-01": ("no_displacement", "PARTIAL", "Deployment requirement is declared."),
    "RESILIENCE-5.5-01": ("emergent_dependency", "PARTIAL", "The removal test result is declared."),
    "RESILIENCE-5.5-02": ("irreplaceability_emergent", "PARTIAL", "Displacement requirement is declared."),
    "RESILIENCE-5.5-03": ("removal_without_change", "IMPLEMENTED", None),
    "RESILIENCE-5.6-01": ("scope_isolation", "IMPLEMENTED", None),
    "RESILIENCE-5.7-01": ("metadata_completeness", "PARTIAL", "Minimum metadata = EB §5 set; the referenced DKP-PTL-REG-DATA-001 is absent (H-RS-2)."),
    "RESILIENCE-5.7-02": ("no_filtering", "PARTIAL", "Filtering and aggregation are declared properties."),
    "RESILIENCE-5.7-03": ("local_invalidation", "IMPLEMENTED", None),
    "RESILIENCE-5.8-01": ("node_concentration", "PARTIAL", "Share of nodes per owner against the ORACLE 4% cap (H-RS-3)."),
    "RESILIENCE-5.8-02": ("anti_sybil", "IMPLEMENTED", None),
    "RESILIENCE-6.1-01": ("distributed_entry_points", "PARTIAL", "Implementation count is declared."),
    "RESILIENCE-6.2-01": ("local_first", "PARTIAL", "Declared property."),
    "RESILIENCE-6.3-01": ("passive_adoption", "IMPLEMENTED", None),
    "RESILIENCE-6.4-01": ("constraint_driven", "IMPLEMENTED", None),
    "RESILIENCE-7.1-01": ("forbidden_central_authority_node", "PARTIAL", "Patterns are declared."),
    "RESILIENCE-7.2-01": ("forbidden_identity_bound_trust", "PARTIAL", "Patterns are declared."),
    "RESILIENCE-7.3-01": ("forbidden_narrative_dependence", "PARTIAL", "Patterns are declared."),
    "RESILIENCE-7.4-01": ("forbidden_enforcement_via_interpretation", "PARTIAL", "Patterns are declared."),
    "RESILIENCE-8.4-01": ("statistical_collapse", "PARTIAL", "F-007."),
    "RESILIENCE-8.5-01": ("interface_degradation", "IMPLEMENTED", None),
    "RESILIENCE-9-01": ("resilience_mechanism", "PARTIAL", "Summary of the structural properties."),
    "RESILIENCE-10.1-01": ("crisis_not_overridden", "PARTIAL", "Recorded property."),
    "RESILIENCE-10.1-02": ("crisis_no_centralization", "IMPLEMENTED", None),
    "RESILIENCE-10.2-01": ("undefined_zone", "PARTIAL", "Threats remove declared actors."),
    "RESILIENCE-11-01": ("removal_test", "IMPLEMENTED", None),
    "RESILIENCE-12-01": ("structure_not_protection", "PARTIAL", "Declared property."),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")
PROVIDERS = {"measurement": ["oracle_net_a", "oracle_net_b"], "aggregation": ["agg_1", "agg_2"], "enforcement": ["exec_1", "exec_2", "exec_3"],
             "audit": ["audit_1", "audit_2"], "identity_binding": ["id_1", "id_2"], "entry": ["portal_a", "portal_b", "portal_c"]}
NODES = [{"id": f"n{i:02d}", "owner": f"o{i // 2:02d}"} for i in range(60)]          # 30 owners, two nodes each: 3.3 % per owner


def _ep(i, missing=(), **kw):
    e = {"id": i, "metadata": [f for f in EB_FIELDS if f not in missing], "semantic_filtering": False, "variance_hiding_aggregation": False}
    e.update(kw)
    return e


class ResilienceStructureModule(LabModule):
    id = "resilience_structure"
    version = "1.0.0"
    title = {"en": "Resilience under pressure (RESILIENCE)", "ru": "Устойчивость под давлением (RESILIENCE)"}
    summary = {"en": "Reputational attacks, access restriction, infrastructure denial, co-option, a filtered portal, a Sybil owner: does the "
                     "deployment keep every function without a person, an override or a central node?",
               "ru": "Репутационные атаки, ограничение доступа, отказ инфраструктуры, кооптация, фильтрующий портал, владелец-сивилл: "
                     "сохраняет ли развёртывание все функции без лидера, переопределения и центрального узла?"}
    protocols = ["DKP-6-RESILIENCE-001"]
    example_order = ["pressure_campaign", "collapse_below_neff", "faulty_structure"]
    noncompliant_examples = ["concentrated_owner"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_resilience_structure_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-RS-1", "source": "hypothesis", "text": {
            "en": "Functions, providers, pressure events and their effects are declared; pressure removes providers.",
            "ru": "Функции, поставщики, события давления и их последствия объявлены; давление убирает поставщиков."}},
        {"id": "H-RS-2", "source": "hypothesis", "text": {
            "en": "Minimum PTL metadata of an entry point = the six fields of EB §5; the referenced DKP-PTL-REG-DATA-001 is not in the corpus.",
            "ru": "Минимальные метаданные PTL точки входа = шесть полей EB §5; упомянутого DKP-PTL-REG-DATA-001 в корпусе нет."}},
        {"id": "H-RS-3", "source": "hypothesis", "text": {
            "en": "'Node concentration' (§5.8) = share of nodes per owner, compared with the ORACLE §8 cap of 4% per owner.",
            "ru": "'Концентрация узлов' (§5.8) = доля узлов на владельца в сравнении с пределом ORACLE §8 в 4% на владельца."}},
    ]
    inputs = {
        "providers": {"type": "object", "source": "user", "label": {"en": "Providers per function", "ru": "Поставщики по функциям"},
                      "fields": {f: {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "str"}, "default": PROVIDERS[f]} for f in FUNCTIONS},
                      "default": PROVIDERS},
        "nodes": {"type": "list", "min_items": 1, "max_items": 200, "source": "user", "label": {"en": "Nodes and owners", "ru": "Узлы и владельцы"},
                  "items": {"type": "object", "fields": {"id": {"type": "str"}, "owner": {"type": "str"}}}, "default": NODES},
        "n_eff": {"type": "number", "min": 0, "max": 10 ** 6, "default": 25.0, "source": "missing",
                  "label": {"en": "N_eff (undefined, F-007)", "ru": "N_eff (не определено, F-007)"}},
        "n_eff_min": {"type": "number", "min": 0, "max": 10 ** 6, "default": 15.0, "source": "missing",
                      "label": {"en": "N_eff_min (undefined, F-007)", "ru": "N_eff_min (не определено, F-007)"}},
        "pressure": {"type": "list", "min_items": 0, "max_items": 20, "source": "user", "label": {"en": "Pressure events", "ru": "События давления"},
                     "items": {"type": "object", "fields": {"step": {"type": "int", "min": 0, "max": 1000}, "kind": {"type": "enum", "values": list(PRESSURES)},
                                                            "removes": {"type": "list", "min_items": 0, "max_items": 20, "items": {"type": "str"}, "default": []}}},
                     "default": [{"step": 1, "kind": "reputational_targeting", "removes": ["exec_1"]},
                                 {"step": 2, "kind": "access_restriction", "removes": ["portal_a", "portal_b"]},
                                 {"step": 3, "kind": "infrastructure_denial", "removes": ["oracle_net_a", "agg_1"]},
                                 {"step": 4, "kind": "physical_suppression", "removes": ["audit_1", "id_1"]},
                                 {"step": 5, "kind": "advisory_conversion"}]},
        "accept_absorption": {"type": "list", "min_items": 0, "max_items": 2, "items": {"type": "enum", "values": ["advisory_conversion"]},
                              "default": [], "source": "user", "label": {"en": "Absorption accepted", "ru": "Принятое поглощение"}},
        "entry_points": {"type": "list", "min_items": 0, "max_items": 20, "source": "user", "label": {"en": "Entry points", "ru": "Точки входа"},
                         "items": {"type": "object", "fields": {"id": {"type": "str"},
                                                                "metadata": {"type": "list", "min_items": 0, "max_items": 6, "items": {"type": "enum", "values": list(EB_FIELDS)}},
                                                                "semantic_filtering": {"type": "bool", "default": False},
                                                                "variance_hiding_aggregation": {"type": "bool", "default": False}}},
                         "default": [_ep("portal_a"), _ep("portal_b", semantic_filtering=True), _ep("portal_c", missing=("dispute_allowed",))]},
        "override_requests": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Override requests", "ru": "Запросы переопределения"},
                              "items": {"type": "object", "fields": {"kind": {"type": "enum", "values": list(OVERRIDES)}, "target": {"type": "str"}}},
                              "default": [{"kind": "expert", "target": "enforcement"}, {"kind": "institutional", "target": "enforcement"}]},
        "mechanism_changes": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Resilience mechanisms", "ru": "Механизмы устойчивости"},
                              "items": {"type": "object", "fields": {"id": {"type": "str"}, "touches": {"type": "enum", "values": ["none", "axioms", "enforcement_logic"]}}},
                              "default": [{"id": "mirror_sites", "touches": "none"}, {"id": "emergency_rule", "touches": "enforcement_logic"}]},
        "adoptions": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Adoptions", "ru": "Внедрения"},
                      "items": {"type": "object", "fields": {"site": {"type": "str"}, "basis": {"type": "enum", "values": ["utility", "mandate"]}}},
                      "default": [{"site": "town_a", "basis": "utility"}, {"site": "region_b", "basis": "mandate"}]},
        "influence_attempts": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Influence attempts", "ru": "Попытки влияния"},
                               "items": {"type": "object", "fields": {"id": {"type": "str"}, "means": {"type": "enum", "values": ["measurable_limit", "persuasion"]}}},
                               "default": [{"id": "cap", "means": "measurable_limit"}, {"id": "campaign", "means": "persuasion"}]},
        "crisis_actions": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Crisis actions", "ru": "Кризисные действия"},
                           "items": {"type": "object", "fields": {"id": {"type": "str"}, "step": {"type": "int", "min": 0, "max": 1000},
                                                                  "could_centralize": {"type": "bool", "default": False}}},
                           "default": [{"id": "reroute", "step": 3, "could_centralize": True}]},
        "patterns": {"type": "list", "min_items": 0, "max_items": 4, "items": {"type": "enum", "values": list(FORBIDDEN)}, "default": [], "source": "user",
                     "label": {"en": "Structural patterns present", "ru": "Присутствующие структурные шаблоны"}},
        "dkp_removal_changes_constraints": {"type": "bool", "default": True, "source": "user",
                                            "label": {"en": "Removing DKP changes measurable constraints", "ru": "Удаление DKP меняет измеримые ограничения"}},
        "micro_deployment_functional": {"type": "bool", "default": True, "source": "user", "label": {"en": "Works at micro level", "ru": "Работает на микроуровне"}},
        "implementations": {"type": "int", "min": 1, "max": 100, "default": 3, "source": "user", "label": {"en": "Independent implementations", "ru": "Независимых реализаций"}},
        "canonical_interface_required": {"type": "bool", "default": False, "source": "user", "label": {"en": "Canonical interface required", "ru": "Нужен канонический интерфейс"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        names = [x["id"] for x in r["nodes"]] + [x["owner"] for x in r["nodes"]] + [e["id"] for e in r["entry_points"]] + \
            [p_ for f in FUNCTIONS for p_ in r["providers"][f]]
        for x in names:
            if not _ID.fullmatch(x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        if len({x["id"] for x in r["nodes"]}) != len(r["nodes"]):
            p.append("input.nodes: repeated id")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        outputs = {"structure": [m.value for m in msgs if m.source == "RES"],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": f"{len(r['pressure'])} pressure events; violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"Событий давления: {len(r['pressure'])}; нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"pressure_campaign": {},
                "collapse_below_neff": {"n_eff": 9.0},
                "concentrated_owner": {"nodes": [{"id": f"n{i:02d}", "owner": "big" if i < 5 else f"o{i:02d}"} for i in range(30)]},
                "faulty_structure": {"faults": ["single_provider", "leader_profile", "accept_override", "sybil_scaling", "mandated_adoption"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"bad_identifier": {"nodes": [{"id": "Node One", "owner": "o"}]},
                "repeated_node": {"nodes": [{"id": "n1", "owner": "a"}, {"id": "n1", "owner": "b"}]}}


for _spec in ResilienceStructureModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
    elif _spec["type"] == "object":
        _spec["default"] = resolve(_spec["default"], _spec["fields"])
