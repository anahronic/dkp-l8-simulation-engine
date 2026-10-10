"""
HABITAT DIGNITY module — DKP-5-HABITAT-001 beyond the calibration gate.

Sites report habitat measurements.  SPDI is built only from PTL-verified physical components, never from
preference, market value, status or aesthetics (§4); thresholds come only from an L8 bundle and cannot be
lowered by other protocols (§5); without a valid bundle every output is informational (§6).  Density and
enclosure are judged through SPDI components, not architectural prescriptions (§7).  Prohibited conditions
trigger remediation, never forced displacement by default; persistent violations escalate to review (§8,
§10).  Sensor tampering is a critical integrity violation handled by ORACLE and AUDIT, not by HABITAT (§9).
HABITAT does not define styles, rank habitats, impose uniform standards or housing forms (§2, §11).  SPDI
values and flags stay auditable, aggregated and reviewable; individual exposure data are "protected under
DKP-7-SCOPE-001", which contains no data-protection rules (F-040).

No Calibration Bundle exists (F-014).  The bundle here is a declared model condition, not a calibration;
its numbers are not proposals.  Time unit: month.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

COMPONENTS = ("living_space", "noise", "light", "air", "thermal", "water", "green_access")     # §4
FORBIDDEN_INPUTS = {"preference": "HABITAT-4-03", "market_value": "HABITAT-4-04", "status": "HABITAT-4-05", "aesthetics": "HABITAT-4-06"}
CONDITIONS = {"containment_zone": "HABITAT-8-02", "resource_denial": "HABITAT-8-03", "degradation_lever": "HABITAT-8-04",
              "autonomy_suppression": "HABITAT-8-05"}                                                         # §8
DESIGN = {"density_stress": "HABITAT-7-01", "permanent_enclosure": "HABITAT-7-02", "vertical_compression": "HABITAT-7-03",
          "biosphere_isolation": "HABITAT-7-04"}                                                              # §7
OUT_OF_SCOPE = {"architectural_style": "HABITAT-2-01", "aesthetic_norm": "HABITAT-2-02", "override_climate_adaptation": "HABITAT-2-03",
                "rank_beyond_compliance": "HABITAT-11-01", "uniform_global_standard": "HABITAT-11-02", "mandate_housing_form": "HABITAT-11-03",
                "override_cultural_adaptation": "HABITAT-11-04"}
BUNDLE_STATES = ("none", "valid", "expired", "invalid_signature", "other_model")

FAULTS = {
    "market_in_spdi": "market value enters SPDI",
    "self_report_only": "a self-reported measurement enters SPDI",
    "remediate_without_bundle": "remediation is triggered without a valid bundle",
    "manual_interpretation": "a violation is read from raw values by hand",
    "threshold_lowered": "a finance protocol lowers SPDI_min",
    "forced_displacement": "forced displacement is the default remedy",
    "no_remediation": "a confirmed violation gets no remediation plan",
    "no_escalation": "a persistent violation is not escalated",
    "habitat_investigates": "HABITAT runs its own investigation and penalty for sensor tampering",
    "out_of_scope_executed": "HABITAT mandates a housing form",
    "design_by_prescription": "density is judged by a fixed floor-area prescription instead of SPDI components",
    "expose_individual": "individual exposure data are published",
    "unauditable_flags": "violation flags are not available for audit",
    "direct_change": "HABITAT is changed outside UPGRADE",
    "count_non_living_space": "a storage container is counted as living space",
}


LIVING_KINDS = ("dwelling", "shelter")       # §3 Living Space: enclosed or semi-enclosed, for rest, shelter and daily life
SPACE_KINDS = LIVING_KINDS + ("storage", "open_lot")


def spdi(site, bundle):
    w = bundle["weights"]
    tot = sum(w[c] for c in COMPONENTS) or 1.0
    return round(sum(w[c] * site["components"][c] for c in COMPONENTS) / tot, 9)


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("month", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    b = r["bundle"]
    valid = b["state"] == "valid"
    spdi_min = b["spdi_min"]
    for q in r["threshold_requests"]:
        ok = q["by"] == "simulation" or ("threshold_lowered" in faults and q["by"] != "simulation")
        put("decision", "HABITAT", 0, {"threshold_request": q["by"], "new_spdi_min": q["value"], "accepted": ok})
        if ok:
            spdi_min = q["value"]
    persist: Dict[str, int] = {}
    for k in range(r["months"]):
        for s in r["sites"]:
            comp = dict(s["components"])
            living = s["space_kind"] in LIVING_KINDS
            if not living and "count_non_living_space" not in faults:
                comp["living_space"] = 0.0                  # §3: not an area for rest, shelter and daily life
            admitted = s["ptl_verified"] or "self_report_only" in faults
            used_inputs = list(COMPONENTS) + (["market_value"] if "market_in_spdi" in faults else [])
            val = spdi({"components": comp}, b)
            if "market_in_spdi" in faults:
                val = round((val + s["extra"]["market_value"]) / 2, 9)
            low = [c for c in COMPONENTS if comp[c] < b["component_min"][c]]
            rec = {"site": s["id"], "spdi": val if admitted else None, "inputs": used_inputs if admitted else [], "ptl_verified": s["ptl_verified"],
                   "model": "declared bundle (not a calibration)", "informational_only": not valid,
                   "exposure_level": "aggregated" if "expose_individual" not in faults else "individual",
                   "auditable": "unauditable_flags" not in faults, "reviewable_post_facto": True,
                   "space_kind": s["space_kind"], "living_space_used": comp["living_space"]}
            violation = admitted and (val < spdi_min or bool(low) or s["chronic_exposure_unsafe"] or bool(s["conditions"]))
            rec["violation_flag"] = violation if valid or "manual_interpretation" in faults else None
            put("evaluation", "HABITAT", k, rec)
            if s["tampered"] and k == 0:
                put("notice", "HABITAT", k, {"integrity_violation": s["id"], "critical": True,
                                             "routed_to": ["DKP-0-ORACLE-001", "DKP-8-AUDIT-001"],
                                             **({"habitat_investigation": True, "penalty": "fine"} if "habitat_investigates" in faults else {})})
            if violation and (valid or "remediate_without_bundle" in faults or "manual_interpretation" in faults):
                persist[s["id"]] = persist.get(s["id"], 0) + 1
                if persist[s["id"]] == 1 and "no_remediation" not in faults:
                    put("action", "HABITAT", k, {"remediation_plan": s["id"],
                                                 "remedy": "forced displacement" if "forced_displacement" in faults else "on-site improvement",
                                                 "relocation_assistance": "offered" if s["relocation_wanted"] else "not requested",
                                                 "incentives": "via DKP-2-FINANCE-001", "causes": low + s["conditions"] +
                                                 (["SPDI below minimum"] if val < spdi_min else [])})
                if persist[s["id"]] == r["persistence_months"] and "no_escalation" not in faults:
                    put("notice", "HABITAT", k, {"escalation": s["id"], "to": "system-level review under DKP-7-SCOPE-001"})
            elif not violation:
                persist[s["id"]] = 0
    for d in r["designs"]:
        crit = "fixed floor-area prescription" if "design_by_prescription" in faults else "SPDI components"
        comp_fail = d["affects"] in ("density_stress", "permanent_enclosure", "biosphere_isolation") and d["component_effect"] == "below_threshold"
        put("decision", "HABITAT", 0, {"design": d["id"], "feature": d["affects"], "judged_by": crit,
                                       "admitted": not comp_fail if crit == "SPDI components" else d["floor_area_ok"]})
    for q in r["out_of_scope_requests"]:
        ok = q == "mandate_housing_form" and "out_of_scope_executed" in faults
        put("decision", "HABITAT", 0, {"out_of_scope": q, "executed": ok})
    for c in r["changes"]:
        ok = (c["channel"] == "upgrade" and c["simulated"] and c["new_identifier"] and c["compatibility_declared"]) or \
            ("direct_change" in faults and c["channel"] == "direct")
        put("decision", "HABITAT", 0, {"change": c["id"], "accepted": ok, "presentation_only": c["presentation_only"]})
    return log


def living_space_check(r: Dict[str, Any], msgs) -> CheckResult:
    """HABITAT §3 Living Space (review КТ5 reading)."""
    recs = [m.value for m in msgs if m.source == "HABITAT" and "space_kind" in m.value]
    site = {s["id"]: s for s in r["sites"]}
    bad = [f"{x['site']}: {x['space_kind']} counted as living space" for x in recs
           if x["space_kind"] not in LIVING_KINDS and x["living_space_used"] > 0]
    bad += [f"{x['site']}: living space altered" for x in recs if x["space_kind"] in LIVING_KINDS
            and x["living_space_used"] != site[x["site"]]["components"]["living_space"]]
    return CheckResult("HABITAT-3-02", "living_space_definition", FAIL if bad else PASS,
                       f"{len(set(b.split(':')[0] for b in bad))} sites with a non-living area counted as living space" if bad else
                       "only enclosed or semi-enclosed areas for rest, shelter and daily life count as living space "
                       f"({len({x['site'] for x in recs})} sites)", evidence={"violations": bad[:10]} if bad else {})


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    H = lambda key: [m for m in msgs if m.source == "HABITAT" and key in m.value]   # noqa: E731
    b = r["bundle"]
    valid = b["state"] == "valid"
    sites = {s["id"]: s for s in r["sites"]}
    ev = [m.value for m in H("spdi")]
    out.append(v("HABITAT-4-02", "ptl_components_only", [e["site"] for e in ev if e["spdi"] is not None and
                                                         (not sites[e["site"]]["ptl_verified"] or set(e["inputs"]) - set(COMPONENTS))],
                 "SPDI built only from PTL-verified physical components", "{n} SPDI values from other inputs"))
    out.append(v("HABITAT-9-01", "ptl_anchored", [e["site"] for e in ev if e["spdi"] is not None and not sites[e["site"]]["ptl_verified"]],
                 "every SPDI measurement PTL-anchored; self-reports alone never used", "{n} SPDI values from self-reports"))
    for key, rid in FORBIDDEN_INPUTS.items():
        out.append(v(rid, f"no_{key}", [e["site"] for e in ev if key in e["inputs"]], f"no {key.replace('_', ' ')} in SPDI", "{n} SPDI values use it"))
    exp_min = b["spdi_min"]
    acc_thr = [m.value for m in H("threshold_request") if m.value["accepted"]]
    tr = [m.value for m in H("threshold_request")]
    if tr:
        out.append(v("HABITAT-5-07", "no_external_lowering", [x["threshold_request"] for x in acc_thr if x["threshold_request"] != "simulation"],
                     "no economic, operational or governance protocol changed a threshold", "{n} thresholds changed outside L8"))
        out.append(v("HABITAT-5-05", "thresholds_from_l8", [x["threshold_request"] for x in acc_thr if x["threshold_request"] != "simulation"],
                     "thresholds only from DKP-8-SIMULATION-001", "{n} thresholds from elsewhere"))
    else:
        for rid, chk in (("HABITAT-5-07", "no_external_lowering"), ("HABITAT-5-05", "thresholds_from_l8")):
            out.append(na(rid, chk, "threshold requests", "none"))
    out.append(CheckResult("HABITAT-5-04", "no_numbers_in_protocol", PASS, "the protocol text gives no number for SPDI_min or component thresholds; "
                           "the lab takes them only from the declared bundle"))
    out.append(v("HABITAT-2-04", "no_enforcement_without_l8", [m.value["remediation_plan"] for m in H("remediation_plan") if not valid],
                 "no enforcement without a valid L8 bundle", "{n} remediations without a valid bundle"))
    flags = [e for e in ev if e["violation_flag"] is not None and not valid]
    out.append(v("HABITAT-6-03", "no_manual_interpretation", [e["site"] for e in flags],
                 "without a valid bundle no violation is read from raw values", "{n} manual readings"))
    # admissibility recomputed (only with a valid bundle)
    if valid:
        thr = exp_min if not [x for x in acc_thr if x["threshold_request"] == "simulation"] else acc_thr[-1]["new_spdi_min"]
        viol = {s["id"] for s in r["sites"] if s["ptl_verified"] and (spdi(s, b) < thr or any(s["components"][c] < b["component_min"][c] for c in COMPONENTS)
                                                                         or s["chronic_exposure_unsafe"] or s["conditions"])}
        plans = {m.value["remediation_plan"]: m.value for m in H("remediation_plan")}
        out.append(v("HABITAT-5-03", "chronic_exposure", [s["id"] for s in r["sites"] if s["ptl_verified"] and s["chronic_exposure_unsafe"] and s["id"] not in plans],
                     "unsafe chronic exposure treated as inadmissible", "{n} unsafe exposures ignored")
                   if any(s["chronic_exposure_unsafe"] for s in r["sites"]) else na("HABITAT-5-03", "chronic_exposure", "unsafe exposure", "none"))
        out.append(v("HABITAT-8-01", "persistent_low_spdi", [i for i in viol if i not in plans], "every inadmissible habitat flagged and remediated",
                     "{n} violations without a plan") if viol else na("HABITAT-8-01", "persistent_low_spdi", "violations", "none"))
        for key, rid in CONDITIONS.items():
            ids = [s["id"] for s in r["sites"] if key in s["conditions"]]
            out.append(v(rid, f"condition_{key}", [i for i in ids if i not in plans], f"{key.replace('_', ' ')} flagged as a habitat violation",
                         "{n} not flagged") if ids else na(rid, f"condition_{key}", key, "none declared"))
        out.append(v("HABITAT-8-06", "mandatory_remediation", [i for i in viol if i not in plans], "every violation started a remediation pathway",
                     "{n} without") if viol else na("HABITAT-8-06", "mandatory_remediation", "violations", "none"))
        out.append(v("HABITAT-10-01", "remediation_initiated", [i for i in viol if i not in plans], "a remediation plan initiated for every confirmed violation",
                     "{n} violations without a plan") if viol else na("HABITAT-10-01", "remediation_initiated", "violations", "none"))
        out.append(v("HABITAT-10-04", "no_forced_displacement", [p for p, x in plans.items() if x["remedy"] == "forced displacement"],
                     "no plan uses forced displacement as its remedy", "{n} plans displace by force") if plans else
                   na("HABITAT-10-04", "no_forced_displacement", "plans", "none"))
        out.append(v("HABITAT-10-02", "relocation_assistance_optional", [p for p, x in plans.items() if x["relocation_assistance"] == "imposed"],
                     "relocation assistance offered only on request, never imposed", "{n} imposed") if plans else
                   na("HABITAT-10-02", "relocation_assistance_optional", "plans", "none"))
        out.append(v("HABITAT-10-03", "incentives_via_l2", [p for p, x in plans.items() if x["incentives"] != "via DKP-2-FINANCE-001"],
                     "economic incentives routed through L2", "{n} otherwise") if plans else na("HABITAT-10-03", "incentives_via_l2", "plans", "none"))
        pers = [s["id"] for s in r["sites"] if s["id"] in viol and r["months"] >= r["persistence_months"]]
        esc = {m.value["escalation"] for m in H("escalation")}
        out.append(v("HABITAT-10-05", "persistent_escalation", [i for i in pers if i not in esc],
                     f"violations lasting {r['persistence_months']} months (declared, source missing) escalated to review",
                     "{n} persistent violations not escalated") if pers else na("HABITAT-10-05", "persistent_escalation", "persistent violations", "none"))
    else:
        for rid, chk in (("HABITAT-5-03", "chronic_exposure"), ("HABITAT-8-01", "persistent_low_spdi"), ("HABITAT-8-06", "mandatory_remediation"),
                         ("HABITAT-10-02", "relocation_assistance_optional"), ("HABITAT-10-03", "incentives_via_l2"),
                         ("HABITAT-10-05", "persistent_escalation"), ("HABITAT-10-01", "remediation_initiated"),
                         ("HABITAT-10-04", "no_forced_displacement")) + tuple((rid, f"condition_{key}") for key, rid in CONDITIONS.items()):
            out.append(na(rid, chk, "enforcement", f"no valid L8 bundle (state: {b['state']}): outputs are informational (§6, F-014)"))
    # §7 design through SPDI components
    ds = [m.value for m in H("design")]
    if ds:
        out.append(v("HABITAT-7-05", "judged_by_components", [d["design"] for d in ds if d["judged_by"] != "SPDI components"],
                     "density and enclosure judged through SPDI components", "{n} judged by fixed prescriptions"))
        for key, rid in DESIGN.items():
            rows = [d for d in ds if d["feature"] == key]
            want = {x["id"]: not (x["affects"] in ("density_stress", "permanent_enclosure", "biosphere_isolation") and x["component_effect"] == "below_threshold")
                    for x in r["designs"]}
            out.append(v(rid, f"design_{key}", [d["design"] for d in rows if d["admitted"] != want[d["design"]] or d["judged_by"] != "SPDI components"],
                         f"designs with {key.replace('_', ' ')} admitted only when SPDI components stay above threshold", "{n} decided otherwise")
                       if rows else na(rid, f"design_{key}", key, "no such design"))
    else:
        for key, rid in list(DESIGN.items()) + [("judged", "HABITAT-7-05")]:
            out.append(na(rid, f"design_{key}" if key != "judged" else "judged_by_components", "designs", "none"))
    # §9 integrity
    tp = [m.value for m in H("integrity_violation")]
    if tp:
        out.append(v("HABITAT-9-02", "tampering_critical", [x["integrity_violation"] for x in tp if not x["critical"]], "tampering recorded as a critical integrity violation", "{n} not"))
        out.append(v("HABITAT-9-03", "routed_to_oracle_audit", [x["integrity_violation"] for x in tp if sorted(x["routed_to"]) != ["DKP-0-ORACLE-001", "DKP-8-AUDIT-001"]],
                     "tampering handled by ORACLE and AUDIT", "{n} routed elsewhere"))
        out.append(v("HABITAT-9-04", "no_own_investigation", [x["integrity_violation"] for x in tp if x.get("habitat_investigation") or x.get("penalty")],
                     "HABITAT ran no investigation and imposed no penalty", "{n} HABITAT investigations"))
    else:
        for rid, chk in (("HABITAT-9-02", "tampering_critical"), ("HABITAT-9-03", "routed_to_oracle_audit"), ("HABITAT-9-04", "no_own_investigation")):
            out.append(na(rid, chk, "tampering", "none"))
    # §2, §11 scope
    oq = [m.value for m in H("out_of_scope")]
    for key, rid in OUT_OF_SCOPE.items():
        rows = [x for x in oq if x["out_of_scope"] == key]
        out.append(v(rid, f"scope_{key}", [x["out_of_scope"] for x in rows if x["executed"]], f"no {key.replace('_', ' ')}", "{n} executed")
                   if rows else na(rid, f"scope_{key}", key, "not requested"))
    # §12
    out.append(v("HABITAT-12-01", "auditable", [e["site"] for e in ev if not e["auditable"]], "SPDI values and flags available for audit", "{n} not auditable"))
    out.append(v("HABITAT-12-02", "aggregated", [e["site"] for e in ev if e["exposure_level"] != "aggregated"], "values aggregated to protect privacy", "{n} individual"))
    out.append(v("HABITAT-12-03", "post_facto_review", [e["site"] for e in ev if not e["reviewable_post_facto"]], "values reviewable post-facto", "{n} not"))
    if any(e["exposure_level"] == "individual" for e in ev):
        out.append(CheckResult("HABITAT-12-04", "individual_data_protected", FAIL, "individual exposure data were published"))
    else:
        out.append(CheckResult("HABITAT-12-04", "individual_data_protected", UNKNOWN,
                               "individual exposure data kept aggregated (PRIVACY-style protection); HABITAT says they are protected "
                               "'under DKP-7-SCOPE-001', which contains no data-protection rules (F-040)"))
    ch = [m.value for m in H("change")]
    cs = {c["id"]: c for c in r["changes"]}
    if ch:
        acc = [x["change"] for x in ch if x["accepted"] and not x["presentation_only"]]
        out.append(v("HABITAT-13-01", "upgrade_only", [i for i in acc if cs[i]["channel"] != "upgrade" or not cs[i]["simulated"]],
                     "HABITAT changed only through UPGRADE with simulation", "{n} otherwise"))
        out.append(v("HABITAT-13-02", "new_identifier", [i for i in acc if not cs[i]["new_identifier"]], "accepted changes carry a new identifier", "{n} without"))
        out.append(v("HABITAT-13-03", "compatibility", [i for i in acc if not cs[i]["compatibility_declared"]],
                     "accepted changes declare compatibility with TRANSPORT and SCOPE", "{n} without"))
        pres = [x for x in ch if x["presentation_only"]]
        out.append(v("HABITAT-13-04", "presentation_not_upgrade", [], f"{len(pres)} presentation-only corrections recorded by date", "")
                   if pres else na("HABITAT-13-04", "presentation_not_upgrade", "corrections", "none"))
    else:
        for rid, chk in (("HABITAT-13-01", "upgrade_only"), ("HABITAT-13-02", "new_identifier"), ("HABITAT-13-03", "compatibility"),
                         ("HABITAT-13-04", "presentation_not_upgrade")):
            out.append(na(rid, chk, "changes", "none"))
    return out + [living_space_check(r, msgs)]


IMPLEMENTS = {
    "HABITAT-2-01": ("scope_architectural_style", "PARTIAL", "Requests are declared."),
    "HABITAT-3-02": ("living_space_definition", "PARTIAL", "The kind of each space is declared (dwelling, shelter, storage, open lot)."),
    "HABITAT-2-02": ("scope_aesthetic_norm", "PARTIAL", "Requests are declared."),
    "HABITAT-2-03": ("scope_override_climate_adaptation", "PARTIAL", "Requests are declared."),
    "HABITAT-2-04": ("no_enforcement_without_l8", "IMPLEMENTED", None),
    "HABITAT-4-02": ("ptl_components_only", "PARTIAL", "SPDI model from the declared bundle (not a calibration)."),
    "HABITAT-4-03": ("no_preference", "IMPLEMENTED", None),
    "HABITAT-4-04": ("no_market_value", "IMPLEMENTED", None),
    "HABITAT-4-05": ("no_status", "IMPLEMENTED", None),
    "HABITAT-4-06": ("no_aesthetics", "IMPLEMENTED", None),
    "HABITAT-5-03": ("chronic_exposure", "PARTIAL", "Safe limits are a declared flag."),
    "HABITAT-5-04": ("no_numbers_in_protocol", "IMPLEMENTED", None),
    "HABITAT-5-05": ("thresholds_from_l8", "PARTIAL", "Threshold requests are declared with their origin."),
    "HABITAT-5-07": ("no_external_lowering", "IMPLEMENTED", None),
    "HABITAT-7-01": ("design_density_stress", "PARTIAL", "Component effects of designs are declared."),
    "HABITAT-7-02": ("design_permanent_enclosure", "PARTIAL", "Component effects of designs are declared."),
    "HABITAT-7-03": ("design_vertical_compression", "PARTIAL", "Judged through declared component effects."),
    "HABITAT-7-04": ("design_biosphere_isolation", "PARTIAL", "Component effects of designs are declared."),
    "HABITAT-7-05": ("judged_by_components", "IMPLEMENTED", None),
    "HABITAT-8-01": ("persistent_low_spdi", "PARTIAL", "Only with a declared valid bundle."),
    "HABITAT-8-02": ("condition_containment_zone", "PARTIAL", "Conditions are declared."),
    "HABITAT-8-03": ("condition_resource_denial", "PARTIAL", "Conditions are declared."),
    "HABITAT-8-04": ("condition_degradation_lever", "PARTIAL", "Conditions are declared."),
    "HABITAT-8-05": ("condition_autonomy_suppression", "PARTIAL", "Conditions are declared."),
    "HABITAT-8-06": ("mandatory_remediation", "PARTIAL", "Only with a declared valid bundle (§6)."),
    "HABITAT-9-01": ("ptl_anchored", "IMPLEMENTED", None),
    "HABITAT-9-02": ("tampering_critical", "IMPLEMENTED", None),
    "HABITAT-9-03": ("routed_to_oracle_audit", "IMPLEMENTED", None),
    "HABITAT-9-04": ("no_own_investigation", "IMPLEMENTED", None),
    "HABITAT-10-01": ("remediation_initiated", "PARTIAL", "Plans are events; their content is not modelled."),
    "HABITAT-10-02": ("relocation_assistance_optional", "IMPLEMENTED", None),
    "HABITAT-10-04": ("no_forced_displacement", "IMPLEMENTED", None),
    "HABITAT-10-03": ("incentives_via_l2", "PARTIAL", "Recorded routing."),
    "HABITAT-10-05": ("persistent_escalation", "PARTIAL", "'Persistent' = declared number of months (source missing)."),
    "HABITAT-11-01": ("scope_rank_beyond_compliance", "PARTIAL", "Requests are declared."),
    "HABITAT-11-02": ("scope_uniform_global_standard", "PARTIAL", "Requests are declared."),
    "HABITAT-11-03": ("scope_mandate_housing_form", "PARTIAL", "Requests are declared."),
    "HABITAT-11-04": ("scope_override_cultural_adaptation", "PARTIAL", "Requests are declared."),
    "HABITAT-12-01": ("auditable", "IMPLEMENTED", None),
    "HABITAT-12-02": ("aggregated", "IMPLEMENTED", None),
    "HABITAT-12-03": ("post_facto_review", "PARTIAL", "Recorded property."),
    "HABITAT-12-04": ("individual_data_protected", "PARTIAL", "Referenced rules are absent from SCOPE (F-040)."),
    "HABITAT-13-01": ("upgrade_only", "PARTIAL", "Declared properties of the change."),
    "HABITAT-13-02": ("new_identifier", "IMPLEMENTED", None),
    "HABITAT-13-03": ("compatibility", "IMPLEMENTED", None),
    "HABITAT-13-04": ("presentation_not_upgrade", "IMPLEMENTED", None),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")
GOOD = {"living_space": 0.8, "noise": 0.7, "light": 0.8, "air": 0.9, "thermal": 0.8, "water": 1.0, "green_access": 0.7}


def _site(i, **kw):
    s = {"id": i, "components": dict(GOOD), "ptl_verified": True, "chronic_exposure_unsafe": False, "conditions": [], "tampered": False,
         "relocation_wanted": False, "extra": {"market_value": 0.2, "status": 0.5}}
    s.update(kw)
    return s


SITES = [_site("north_block"), _site("dense_estate", components=dict(GOOD, living_space=0.2, green_access=0.1), relocation_wanted=True),
         _site("fenced_zone", conditions=["containment_zone"]), _site("self_report", ptl_verified=False),
         _site("tampered_sensor", tampered=True)]
BUNDLE = {"state": "valid", "spdi_min": 0.5, "component_min": {c: 0.25 for c in COMPONENTS}, "weights": {c: 1.0 for c in COMPONENTS}}


class HabitatDignityModule(LabModule):
    id = "habitat_dignity"
    version = "1.1.0"
    title = {"en": "Habitat dignity (HABITAT)", "ru": "Достоинство жилой среды (HABITAT)"}
    summary = {"en": "Five sites — a decent block, a dense estate, a fenced zone, a self-reported site and a tampered sensor: does SPDI "
                     "stay physical, are violations remediated without displacement, and does HABITAT keep out of style and ranking?",
               "ru": "Пять участков — нормальный квартал, перенаселённый район, огороженная зона, самоотчёт и подделанный датчик: остаётся ли "
                     "SPDI физическим, исправляются ли нарушения без выселения, не лезет ли HABITAT в стиль и рейтинги?"}
    protocols = ["DKP-5-HABITAT-001"]
    example_order = ["five_sites", "no_bundle", "faulty_habitat"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_habitat_dignity_module.py"]
    causal_note = {"en": "The bundle is a declared model condition, not a calibration (no Calibration Bundle exists, F-014).",
                   "ru": "Пакет — объявленное условие модели, а не калибровка (пакета калибровки нет, F-014)."}
    hypotheses = [
        {"id": "H-HA-1", "source": "hypothesis", "text": {
            "en": "SPDI = weighted mean of the seven normalized components with the declared bundle's weights; components are given in [0,1].",
            "ru": "SPDI = взвешенное среднее семи нормированных компонент с весами объявленного пакета; компоненты заданы в [0,1]."}},
        {"id": "H-HA-2", "source": "hypothesis", "text": {
            "en": "A design is admitted when its declared effect leaves the SPDI components above their thresholds (§7: 'evaluated "
                  "indirectly via SPDI components').",
            "ru": "Проект допускается, если его объявленное влияние оставляет компоненты SPDI выше порогов (§7: 'оцениваются косвенно "
                  "через компоненты SPDI')."}},
    ]
    inputs = {
        "months": {"type": "int", "min": 1, "max": 120, "default": 6, "unit": "month", "source": "user", "label": {"en": "Months", "ru": "Месяцев"}},
        "persistence_months": {"type": "int", "min": 1, "max": 120, "default": 3, "source": "missing",
                               "label": {"en": "Months after which a violation is 'persistent' (§10)", "ru": "Через сколько месяцев нарушение 'устойчиво' (§10)"}},
        "bundle": {"type": "object", "source": "missing", "label": {"en": "Declared L8 bundle (model condition)", "ru": "Объявленный пакет L8 (условие модели)"},
                   "fields": {"state": {"type": "enum", "values": list(BUNDLE_STATES), "default": "valid"},
                              "spdi_min": {"type": "number", "min": 0, "max": 1, "default": 0.5},
                              "component_min": {"type": "object", "fields": {c: {"type": "number", "min": 0, "max": 1, "default": 0.25} for c in COMPONENTS},
                                                "default": {c: 0.25 for c in COMPONENTS}},
                              "weights": {"type": "object", "fields": {c: {"type": "number", "min": 0, "max": 10, "default": 1.0} for c in COMPONENTS},
                                          "default": {c: 1.0 for c in COMPONENTS}}},
                   "default": BUNDLE},
        "sites": {"type": "list", "min_items": 1, "max_items": 30, "source": "user", "label": {"en": "Sites", "ru": "Участки"},
                  "items": {"type": "object", "fields": {
                      "id": {"type": "str"},
                      "components": {"type": "object", "fields": {c: {"type": "number", "min": 0, "max": 1} for c in COMPONENTS}},
                      "ptl_verified": {"type": "bool", "default": True}, "chronic_exposure_unsafe": {"type": "bool", "default": False},
                      "conditions": {"type": "list", "min_items": 0, "max_items": 4, "items": {"type": "enum", "values": list(CONDITIONS)}, "default": []},
                      "tampered": {"type": "bool", "default": False}, "relocation_wanted": {"type": "bool", "default": False},
                      "space_kind": {"type": "enum", "values": list(SPACE_KINDS), "default": "dwelling"},
                      "extra": {"type": "object", "fields": {"market_value": {"type": "number", "min": 0, "max": 1, "default": 0.0},
                                                             "status": {"type": "number", "min": 0, "max": 1, "default": 0.0}},
                                "default": {"market_value": 0.0, "status": 0.0}}}},
                  "default": SITES},
        "threshold_requests": {"type": "list", "min_items": 0, "max_items": 5, "source": "user", "label": {"en": "Threshold change requests", "ru": "Запросы изменить порог"},
                               "items": {"type": "object", "fields": {"by": {"type": "enum", "values": ["simulation", "finance", "operations", "governance"]},
                                                                      "value": {"type": "number", "min": 0, "max": 1}}},
                               "default": [{"by": "finance", "value": 0.3}]},
        "designs": {"type": "list", "min_items": 0, "max_items": 10, "source": "user", "label": {"en": "Habitat designs", "ru": "Проекты жилой среды"},
                    "items": {"type": "object", "fields": {"id": {"type": "str"}, "affects": {"type": "enum", "values": list(DESIGN)},
                                                           "component_effect": {"type": "enum", "values": ["above_threshold", "below_threshold"]},
                                                           "floor_area_ok": {"type": "bool", "default": True}}},
                    "default": [{"id": "tower_a", "affects": "vertical_compression", "component_effect": "above_threshold", "floor_area_ok": False},
                                {"id": "pod_city", "affects": "density_stress", "component_effect": "below_threshold", "floor_area_ok": True},
                                {"id": "atrium", "affects": "permanent_enclosure", "component_effect": "above_threshold"},
                                {"id": "sealed_dome", "affects": "biosphere_isolation", "component_effect": "below_threshold"}]},
        "out_of_scope_requests": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "enum", "values": list(OUT_OF_SCOPE)},
                                  "default": list(OUT_OF_SCOPE), "source": "user", "label": {"en": "Requests outside HABITAT", "ru": "Запросы вне HABITAT"}},
        "changes": {"type": "list", "min_items": 0, "max_items": 5, "source": "user", "label": {"en": "Changes to HABITAT", "ru": "Изменения HABITAT"},
                    "items": {"type": "object", "fields": {"id": {"type": "str"}, "channel": {"type": "enum", "values": ["upgrade", "direct"]},
                                                           "simulated": {"type": "bool", "default": True}, "new_identifier": {"type": "bool", "default": True},
                                                           "compatibility_declared": {"type": "bool", "default": True},
                                                           "presentation_only": {"type": "bool", "default": False}}},
                    "default": [{"id": "spdi_v2", "channel": "upgrade"}, {"id": "typo", "channel": "direct", "presentation_only": True},
                                {"id": "quiet_edit", "channel": "direct"}]},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        for key, ids in (("sites", [s["id"] for s in r["sites"]]), ("designs", [d["id"] for d in r["designs"]]), ("changes", [c["id"] for c in r["changes"]])):
            if len(set(ids)) != len(ids):
                p.append(f"input.{key}: repeated id")
            for x in ids:
                if not _ID.fullmatch(x):
                    p.append(f"input.{key}: identifier {x!r} must be lowercase letters, digits or _")
        if sum(r["bundle"]["weights"].values()) <= 0:
            p.append("input.bundle.weights: at least one positive weight")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        outputs = {"evaluations": [dict(m.value, month=m.arrived_at) for m in msgs if "spdi" in m.value],
                   "decisions": [m.value for m in msgs if m.kind in ("decision", "action", "notice")],
                   "operational_use": False,
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        plans = [d["remediation_plan"] for d in outputs["decisions"] if "remediation_plan" in d]
        e = [{"en": f"Bundle {r['bundle']['state']}; remediation plans: {', '.join(plans) or 'none'}; violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"Пакет {r['bundle']['state']}; планы исправления: {', '.join(plans) or 'нет'}; нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]), "plans": sum(1 for d in outputs["decisions"] if "remediation_plan" in d)}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"five_sites": {},
                "no_bundle": {"bundle": dict(BUNDLE, state="none")},
                "expired_bundle": {"bundle": dict(BUNDLE, state="expired")},
                "chronic_noise": {"sites": [_site("airport_edge", chronic_exposure_unsafe=True)], "designs": [], "out_of_scope_requests": [],
                                  "changes": [], "threshold_requests": [{"by": "simulation", "value": 0.55}]},
                "container_home": {"sites": [_site("north_block"), _site("yard_containers", space_kind="storage")],
                                   "designs": [], "out_of_scope_requests": [], "changes": []},
                "faulty_habitat": {"faults": ["market_in_spdi", "forced_displacement", "threshold_lowered", "habitat_investigates", "expose_individual"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_site": {"sites": [_site("a"), _site("a")]},
                "zero_weights": {"bundle": dict(BUNDLE, weights={c: 0.0 for c in COMPONENTS})},
                "component_above_one": {"sites": [_site("a", components=dict(GOOD, air=1.5))]}}


for _spec in HabitatDignityModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
    elif _spec["type"] == "object":
        _spec["default"] = resolve(_spec["default"], _spec["fields"])
