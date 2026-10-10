"""
INTEROP FAILURE module — failure of an external interface (scenario S-LAB-10).

DKP-8-INTEROP-001 (translation only; external rulings, values, information and black-box inputs
never authoritative; graceful degradation without effect on internal execution, no rollback, no
Crisis or Mercy) → DKP-6-RESILIENCE-001 (mirrored outputs not altered §5.3; entry points keep PTL
metadata, otherwise local invalidation §5.7) → DKP-8-AUDIT-001 (epistemic metadata verification,
D2 reporting, observation only, determinism).

The internal execution is computed twice — with and without the external failure — and compared
message by message.  The sources of an outside provider have one of two roles, never both: an
External System (INTEROP §3, "not governed by DKP protocols"), whose readings enter only as untrusted
I1 inputs and cannot substitute PTL verification (§8), so their outage is an interop failure
(§9: no Crisis); or registered PTL sources governed by ORACLE, whose outage is a loss of PTL outputs
(CRISIS §4).  The lab once counted an external mirror among PTL sources and reported a conflict
between INTEROP §9 and CRISIS §4 (F-013, reclassified as an implementation error); that premise is now
the counterexample `mirror_feeds_ptl`.  The CRISIS §4 "correction tolerance" is not defined (input
marked `missing`).
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from lab.core.bus import EventLog, Message, epistemic_problems
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.run import canonical_json, sha256_text
from lab.core.schema import LabInputError

FAULTS = {
    "binding_external_ruling": "an external court ruling is executed internally",
    "unflagged_external_value": "an external value enters without the externally-sourced flag",
    "blackbox_authoritative": "a proprietary black-box input drives an internal decision",
    "info_substitutes_ptl": "external consensus replaces PTL verification in a decision",
    "external_dependency": "internal decisions depend on an external API (governance-by-API)",
    "alter_mirror": "an output mirrored for external human validation is altered",
    "keep_bad_entry_point": "an entry point that strips metadata stays valid",
    "rollback_on_failure": "DKP state is rolled back when the external system fails",
    "audit_masks": "audit does not report missing epistemic metadata",
    "govern_external": "DKP issues a directive to an external legal system",
    "export_as_ruling": "a DKP output is exported to an external court as a binding ruling",
    "system_complies": "DKP itself acts to comply with an external ruling on a Subject's behalf",
    "direct_ledger_write": "an external economic system writes into DKP outside the three named channels",
    "interop_overreach": "INTEROP carries out a function its scope excludes (harmonization, adjudication, enforcement bridge...)",
    "undeclared_interface": "an external value arrives through an interface that is not formally defined",
    "nondeterministic_translation": "the translation of an external value differs between runs",
    "compatibility_as_consent": "a compatible interface is recorded as the external party's consent",
    "audit_modifies": "audit injects a corrective action into live execution",
    "mirror_feeds_ptl": "readings of an external oracle mirror are counted as PTL sources (the lab's former premise, F-013)",
    "crisis_from_interop": "the outage of an external oracle mirror enters Crisis",
    "no_crisis_on_ptl_loss": "a loss of registered PTL sources beyond the tolerance does not enter Crisis",
}


def crisis_condition(r: Dict[str, Any], k: int, failure: bool) -> bool:
    """Generator: when this hour calls for Crisis.  Registered sources: PTL loss beyond the declared
    tolerance (CRISIS §4).  External mirror: never (INTEROP §9), unless a fault says otherwise."""
    lo, hi = r["external_failure_window"]
    faults = set(r["faults"])
    if r["mirror_role"] == "registered_ptl_source":
        registered = r["internal_sources"] + r["mirror_sources"]
        lost = r["mirror_sources"] if lo <= k < hi else 0
        return (r["ptl_loss_tolerance"] >= 0 and lost / registered > r["ptl_loss_tolerance"]
                and "no_crisis_on_ptl_loss" not in faults)
    return "crisis_from_interop" in faults and failure and lo <= k < hi


REQUESTS = {                                                  # functions INTEROP excludes, and where
    "harmonize_legal_systems": "INTEROP-1-01", "enforce_dkp_externally": "INTEROP-1-01", "accept_external_norm": "INTEROP-1-01",
    "adjudicate_regime_conflict": "INTEROP-5-04", "automatic_harmonization": "INTEROP-10-01", "resolve_geopolitical_conflict": "INTEROP-12-01",
    "unify_legal_systems": "INTEROP-12-02", "guarantee_external_compliance": "INTEROP-12-03", "enforcement_bridge": "INTEROP-12-04"}
INTERFACES = {"legal": "IB-LEGAL-1", "finance": "IB-FIN-1", "info": "IB-INFO-1", "oracle_mirror": "IB-ORACLE-1"}   # §3 formally defined


def translate(value: float) -> Dict[str, Any]:
    """§3 Translation Layer for an external value: a fixed mapping, flagged as external (§6); no CU value is invented."""
    return {"external_value": value, "internal": {"externally_sourced": True, "justice_weighted": "not computed: no translation function"},
            "mapping": "IB-FIN-1/v1"}


def md(scope="interop"):
    return {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
            "scope_ref": scope, "revalidation_required": False, "dispute_allowed": True}


def run(r: Dict[str, Any], failure: bool = True):
    faults = set(r["faults"])
    log = EventLog("hour", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=(), epistemic=None):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower().replace('/', '-')}-{k:04d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=k, measured_at=k if kind == "observation" else None,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    lo, hi = r["external_failure_window"]
    registered = r["mirror_role"] == "registered_ptl_source"
    feeds_ptl = registered or "mirror_feeds_ptl" in faults
    entry_valid = True
    crisis = False
    total = r["internal_sources"] + (r["mirror_sources"] if feeds_ptl else 0)
    for k in range(r["horizon_steps"]):
        in_window = lo <= k < hi
        # the provider's outage: for an external mirror an interop failure (absent from the baseline run);
        # for registered PTL sources a loss of PTL sources, present in both runs (not an interop event)
        down = in_window and (failure or registered)
        mirror_ok = 0 if down else r["mirror_sources"]
        ext: Dict[str, Message] = {}
        if not registered and mirror_ok:
            ext["mirror"] = put("observation", "EXTERNAL/ORACLE", k, {"mirrored_sources": mirror_ok, "class": "I1"})
        used = r["internal_sources"] + (mirror_ok if feeds_ptl else 0)
        ptl = put("observation", "PTL", k, {"internal_sources": r["internal_sources"],
                                            "provider_sources": mirror_ok if feeds_ptl else 0, "share": used / total},
                  [ext["mirror"].event_id] if feeds_ptl and "mirror" in ext else [])
        if failure and in_window:
            channels = ["legal", "finance", "info"] + ([] if registered else ["oracle_mirror"])
            put("notice", "INTEROP", k, {"boundary": "degraded", "channels": channels}, [ptl.event_id])
            if "rollback_on_failure" in faults and k == lo:
                put("action", "INTEROP", k, {"rollback": "DKP state to hour 0"}, [ptl.event_id])
        want = crisis_condition(r, k, failure)
        if want and not crisis:
            put("notice", "CRISIS", k, {"enter": "C3", "trigger": "loss of PTL outputs beyond tolerance" if registered
                                        else "external oracle mirror outage",
                                        "cause": "registered PTL sources" if registered else "interop"}, [ptl.event_id])
            crisis = True
        if crisis and not want:
            put("notice", "CRISIS", k, {"exit": True}, [ptl.event_id])
            crisis = False
        # requests for functions INTEROP excludes (§1, §5, §10, §12): refused at the boundary
        if k == r["request_step"]:
            for kind in r["out_of_scope_requests"]:
                q = put("observation", "EXTERNAL/REQUEST", k, {"request": kind})
                if "interop_overreach" in faults:
                    put("action", "INTEROP", k, {"perform": kind}, [q.event_id])
                else:
                    put("notice", "INTEROP", k, {"boundary_event": "out-of-scope request", "request": kind, "response": "refused",
                                                 "basis": REQUESTS[kind], "interface": INTERFACES["legal"]}, [q.event_id])
        # external events at the boundary
        if failure and k == r["external_ruling_step"]:
            ext["ruling"] = put("observation", "EXTERNAL/LEGAL", k, {"ruling": "suspend subject X", "binding_claimed": True})
            put("notice", "INTEROP", k, {"boundary_event": "external ruling received", "internal_status": "not binding", "interface": INTERFACES["legal"],
                                         "compliance_responsibility": "Subject (INTEROP §5)"}, [ext["ruling"].event_id])
            if "system_complies" in faults:
                put("action", "INTEROP", k, {"comply_with": "external ruling", "on_behalf_of": "subject X"}, [ext["ruling"].event_id])
            if "govern_external" in faults:
                put("action", "DKP", k, {"directive": "adopt DKP allocation rules", "addressed_to": "EXTERNAL/LEGAL"},
                    [ext["ruling"].event_id])
        if k == r["external_value_step"]:
            flag = "unflagged_external_value" not in faults
            ext["value"] = put("observation", "EXTERNAL/FINANCE", k, {"asset_bridge": 1000.0, "channel": "asset_bridge",
                                                                       "externally_sourced": flag,
                                                                       "justice_weighted": "not computed: no translation function"})
            tr = translate(ext["value"].value["asset_bridge"])
            if "nondeterministic_translation" in faults and failure:
                tr["internal"] = dict(tr["internal"], rounding_salt=k)
            put("notice", "INTEROP", k, {"translation": tr, "interface": INTERFACES["finance"]}, [ext["value"].event_id])
            put("notice", "INTEROP", k, {"boundary_event": "external value", "translation_rule": "flag + FINANCE constraints",
                                         "interface": "IB-ADHOC" if "undeclared_interface" in faults else INTERFACES["finance"]},
                [ext["value"].event_id])
            if "compatibility_as_consent" in faults:
                put("notice", "INTEROP", k, {"inference": "external party consented: interface compatible"}, [ext["value"].event_id])
            for ch in ("reporting_gateway", "settlement_mirror") + (("direct_ledger_write",) if "direct_ledger_write" in faults else ()):
                e = put("observation", "EXTERNAL/FINANCE", k, {"channel": ch, "externally_sourced": flag,
                                                                "justice_weighted": "not computed: no translation function"})
                put("notice", "INTEROP", k, {"boundary_event": f"external economic interaction via {ch}", "interface": INTERFACES["finance"]},
                    [e.event_id])
        if failure and k == r["blackbox_step"]:
            ext["blackbox"] = put("observation", "EXTERNAL/BLACKBOX", k, {"control": "proprietary recommendation"})
            put("notice", "INTEROP", k, {"boundary_event": "black-box input", "authoritative": False, "interface": INTERFACES["info"]},
                [ext["blackbox"].event_id])
        if failure and k == r["external_info_step"]:
            ext["info"] = put("observation", "EXTERNAL/INFO", k, {"claim": "institutional consensus", "class": "I1"})
            put("notice", "INTEROP", k, {"boundary_event": "external information", "class": "I1 (untrusted)", "interface": INTERFACES["info"]},
                [ext["info"].event_id])
        # internal decision: from internal PTL only (unless a fault adds external provenance)
        prov = [ptl.event_id]
        value = {"decision": "allocate", "basis": "internal PTL", "internal_sources": r["internal_sources"]}
        if "binding_external_ruling" in faults and "ruling" in ext:
            prov.append(ext["ruling"].event_id)
            value = {**value, "suspend": "subject X"}
        if "blackbox_authoritative" in faults and "blackbox" in ext:
            prov.append(ext["blackbox"].event_id)
        if "info_substitutes_ptl" in faults and "info" in ext:
            prov = [ext["info"].event_id]
            value = {**value, "basis": "external consensus"}
        if "external_dependency" in faults:
            api = put("observation", "EXTERNAL/API", k, {"api_ok": not down})
            prov.append(api.event_id)
            value = {**value, "api_ok": not down}
        dec = None
        if not crisis:
            dec = put("decision", "DKP", k, value, prov, epistemic=md())
        # export to an external legal system (INTEROP §5)
        if dec is not None and k == r["export_step"]:
            put("notice", "INTEROP", k, {"export": dec.event_id, "as": "binding ruling" if "export_as_ruling" in faults else "evidence",
                                         "to": "external court", "digest": sha256_text(canonical_json(dec.value)),
                                         "epistemic": dict(dec.epistemic)}, [dec.event_id])
        # mirroring for external human validation
        if dec is not None and k == r["human_validation_step"]:
            mirrored = dict(dec.value)
            if "alter_mirror" in faults:
                mirrored["decision"] = "allocate (adjusted by reviewer)"
            put("notice", "MIRROR", k, {"mirror_of": dec.event_id, "content": mirrored,
                                        "digest": sha256_text(canonical_json(mirrored))}, [dec.event_id])
        # entry point exposing DKP state
        if k >= r["stripping_entry_step"] >= 0 and dec is not None:
            stripped = None if entry_valid else None
            ep = put("evaluation", "ENTRYPOINT/third-party", k, {"state": dec.value, "valid": entry_valid}, [dec.event_id],
                     epistemic=None)                                      # metadata stripped
            if entry_valid and "keep_bad_entry_point" not in faults:
                put("notice", "RESILIENCE", k, {"entry_point": "third-party", "invalidated": "locally",
                                                "reason": "incomplete PTL metadata"}, [ep.event_id])
                entry_valid = False
            if "audit_masks" not in faults:
                put("notice", "AUDIT", k, {"deviation": "D2", "finding": "missing epistemic metadata", "output": ep.event_id},
                    [ep.event_id])
        if dec is not None:
            put("notice", "AUDIT", k, {"audit_event": dec.event_id, "metadata_ok": not epistemic_problems(dec.epistemic)},
                [dec.event_id])
        if "audit_modifies" in faults and k == 5:
            put("action", "AUDIT", k, {"inject": "corrective rerouting"}, [ptl.event_id])
    return log


def internal(log: EventLog) -> List[Tuple[int, str]]:
    return [(m.arrived_at, sha256_text(canonical_json(m.value))) for m in log.messages() if m.source == "DKP"]


def checks(r, log: EventLog, baseline: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    decisions = [m for m in msgs if m.source == "DKP"]
    ext_ids = lambda src: {m.event_id for m in msgs if m.source == src}
    lo, hi = r["external_failure_window"]
    failed = hi > lo
    if failed:
        diff = sorted(set(internal(baseline)) ^ set(internal(log)))
        out.append(v("INTEROP-9-02", "internal_execution_unaffected", diff,
                     "internal decisions are identical with and without the external failure",
                     "{n} internal decisions differ because of the external failure"))
        rb = [m.event_id for m in msgs if m.value and m.value.get("rollback")]
        out.append(v("INTEROP-9-03", "no_rollback", rb, "no DKP state rolled back", "{n} rollbacks on external failure"))
        # a crisis the run without the interop failure does not have was caused by the interop failure
        base_entries = {m.arrived_at for m in baseline.messages() if m.source == "CRISIS" and m.value.get("enter")}
        crisis = [m.event_id for m in msgs if m.source == "CRISIS" and m.value.get("enter") and m.arrived_at not in base_entries]
        out.append(v("INTEROP-9-04", "no_crisis_from_interop", crisis, "no Crisis or Mercy triggered by the interop failure",
                     "{n} crisis entries caused by the interop failure"))
        # CRISIS §4 from the declared inputs: only registered PTL sources count (an external mirror is I1, INTEROP §8)
        if r["mirror_role"] != "registered_ptl_source":
            out.append(na("CRISIS-4-01", "ptl_loss_triggers_crisis", "PTL loss",
                          "the failing sources are an External System (INTEROP §3), ingested only as untrusted I1 "
                          "(§8): no PTL output is lost"))
        elif r["ptl_loss_tolerance"] < 0:
            out.append(CheckResult("CRISIS-4-01", "ptl_loss_triggers_crisis", UNKNOWN,
                                   "registered PTL sources were lost, but the 'correction tolerance' of CRISIS §4 is not "
                                   "defined; whether this is a crisis trigger cannot be decided"))
        else:
            share = r["mirror_sources"] / (r["internal_sources"] + r["mirror_sources"])
            lossy = [k for k in range(r["horizon_steps"]) if lo <= k < hi] if share > r["ptl_loss_tolerance"] else []
            if not lossy:
                out.append(na("CRISIS-4-01", "ptl_loss_triggers_crisis", "PTL loss",
                              f"PTL loss {share:.3g} stays within the declared tolerance {r['ptl_loss_tolerance']}"))
            else:
                hours, on = set(), False
                notices = [m for m in msgs if m.source == "CRISIS"]
                for k in range(r["horizon_steps"]):
                    for m in notices:
                        if m.arrived_at == k:
                            on = True if m.value.get("enter") else False if m.value.get("exit") else on
                    if on:
                        hours.add(k)
                missed = [k for k in lossy if k not in hours]
                out.append(v("CRISIS-4-01", "ptl_loss_triggers_crisis", missed,
                             f"registered PTL sources lost ({share:.3g} > {r['ptl_loss_tolerance']}) in {len(lossy)} hours; "
                             "crisis in force for all of them (CRISIS §4)",
                             "{n} hours of PTL loss beyond the declared tolerance without crisis"))
    else:
        for rid, chk in (("INTEROP-9-02", "internal_execution_unaffected"), ("INTEROP-9-03", "no_rollback"),
                         ("INTEROP-9-04", "no_crisis_from_interop"), ("CRISIS-4-01", "ptl_loss_triggers_crisis")):
            out.append(na(rid, chk, "external failure", "no external failure in this experiment"))

    def ancestors(m):
        seen, todo = set(), list(m.provenance)
        while todo:
            e = todo.pop()
            if e not in seen:
                seen.add(e)
                todo.extend(log.get(e).provenance)
        return seen

    def uses(src):
        ids = ext_ids(src)
        return [m.event_id for m in decisions if ids & ancestors(m)]
    if ext_ids("EXTERNAL/LEGAL"):
        bad = uses("EXTERNAL/LEGAL")
        for rid, chk in (("INTEROP-5-02", "external_rulings_not_binding"), ("INTEROP-10-04", "no_silent_norm_import")):
            out.append(v(rid, chk, bad, "the external ruling was logged at the boundary and not executed internally",
                         "{n} internal decisions executed an external ruling"))
    else:
        for rid, chk in (("INTEROP-5-02", "external_rulings_not_binding"), ("INTEROP-10-04", "no_silent_norm_import")):
            out.append(na(rid, chk, "external rulings", "no external ruling in this experiment"))
    vals = [m for m in msgs if m.source == "EXTERNAL/FINANCE"]
    if vals:
        out.append(v("INTEROP-6-04", "external_values_flagged", [m.event_id for m in vals if not m.value["externally_sourced"]],
                     "every external value carries the externally-sourced flag", "{n} external values without the flag"))
        out.append(CheckResult("INTEROP-6-02", "justice_weighted_translation", UNKNOWN,
                               "external values must be translated into justice-weighted internal equivalents; no translation "
                               "function is given (FINANCE §3.2 JWCoC has no formula for external values)"))
    else:
        out.append(na("INTEROP-6-04", "external_values_flagged", "external values", "no external value"))
        out.append(na("INTEROP-6-02", "justice_weighted_translation", "external values", "no external value"))
    if ext_ids("EXTERNAL/BLACKBOX"):
        out.append(v("INTEROP-7-04", "blackbox_not_authoritative", uses("EXTERNAL/BLACKBOX"),
                     "the black-box input was not used as an authoritative input", "{n} decisions driven by a black-box input"))
    else:
        out.append(na("INTEROP-7-04", "blackbox_not_authoritative", "black-box inputs", "no black-box input"))
    if ext_ids("EXTERNAL/INFO") | ext_ids("EXTERNAL/ORACLE"):
        bad = uses("EXTERNAL/INFO") + uses("EXTERNAL/ORACLE")
        out.append(v("INTEROP-8-02", "no_external_validation_for_ptl", bad,
                     "external information (consensus claims, mirrored oracle readings) did not replace PTL verification",
                     "{n} decisions based on external information in place of PTL"))
        ext_in = ext_ids("EXTERNAL/INFO") | ext_ids("EXTERNAL/ORACLE")
        trusted = [m.event_id for m in msgs if m.source in ("EXTERNAL/INFO", "EXTERNAL/ORACLE") and m.value.get("class") != "I1"]
        trusted += [m.event_id for m in msgs if m.source == "PTL" and ext_in & set(m.provenance)]
        out.append(v("INTEROP-8-01", "external_info_as_i1", trusted,
                     "external information ingested only as untrusted I1 (never as a PTL source)",
                     "{n} external inputs ingested above I1 or counted as PTL"))
    else:
        out.append(na("INTEROP-8-02", "no_external_validation_for_ptl", "external information", "no external information"))
        out.append(na("INTEROP-8-01", "external_info_as_i1", "external information", "no external information"))
    api = uses("EXTERNAL/API")
    for rid, chk in (("INTEROP-10-02", "no_external_decision_dependency"), ("INTEROP-10-03", "no_governance_by_api")):
        out.append(v(rid, chk, api, "no internal decision depends on an external decision system or API",
                     "{n} internal decisions depend on an external API"))
    # §3 External System: not governed by DKP; §5 exports and compliance; §6 economic channels
    directives = [m.event_id for m in msgs if m.kind in ("action", "decision") and str(m.value.get("addressed_to", "")).startswith("EXTERNAL")]
    roles = [m.event_id for m in msgs if m.source == "EXTERNAL/ORACLE" and r["mirror_role"] == "registered_ptl_source"]
    out.append(v("INTEROP-3-01", "external_not_governed", directives + roles,
                 "external systems only send inputs across the boundary; DKP addresses no directive to them, and registered PTL "
                 "sources are not treated as external", "{n} directives to external systems or misclassified sources"))
    exports = [m for m in msgs if m.source == "INTEROP" and m.value.get("export")]
    if exports:
        bad = [m.event_id for m in exports if m.value["as"] not in ("evidence", "signal", "reference_data")
               or m.value["digest"] != sha256_text(canonical_json(log.get(m.value["export"]).value))
               or m.value["epistemic"] != log.get(m.value["export"]).epistemic]
        out.append(v("INTEROP-5-01", "exports_as_evidence", bad, f"{len(exports)} DKP outputs exported as evidence, unaltered and with "
                     "their epistemic metadata", "{n} exports as something other than evidence, signals or reference data"))
    else:
        out.append(na("INTEROP-5-01", "exports_as_evidence", "exports", "no DKP output exported"))
    if ext_ids("EXTERNAL/LEGAL"):
        comply = [m.event_id for m in msgs if m.source == "INTEROP" and m.kind == "action" and m.value.get("comply_with")]
        recv = [m for m in msgs if m.source == "INTEROP" and m.value.get("boundary_event") == "external ruling received"]
        out.append(v("INTEROP-5-03", "compliance_by_subjects", comply + [m.event_id for m in recv if "Subject" not in m.value.get("compliance_responsibility", "")],
                     "compliance with the external ruling was left to the Subject; DKP took no compliance action",
                     "{n} compliance acts by the system"))
    else:
        out.append(na("INTEROP-5-03", "compliance_by_subjects", "external legal obligations", "no external ruling"))
    econ = [m for m in msgs if m.source == "EXTERNAL/FINANCE"]
    out.append(v("INTEROP-6-01", "economic_channels", [m.event_id for m in econ if m.value.get("channel") not in
                                                       ("asset_bridge", "reporting_gateway", "settlement_mirror")],
                 f"{len(econ)} external economic interactions, each through an asset bridge, reporting gateway or settlement mirror",
                 "{n} interactions outside the named channels") if econ else
               na("INTEROP-6-01", "economic_channels", "external economic interactions", "none"))
    boundary = [m for m in msgs if m.source == "INTEROP" and m.value.get("boundary_event")]
    out.append(v("INTEROP-11-03", "boundary_events_recorded",
                 [] if boundary or not (ext_ids("EXTERNAL/LEGAL") | ext_ids("EXTERNAL/FINANCE") | ext_ids("EXTERNAL/INFO")) else ["none"],
                 f"{len(boundary)} boundary events recorded for review", "external events without boundary records"))
    # §1, §5, §10, §12: functions INTEROP excludes are refused when requested
    reqs = [m for m in msgs if m.source == "EXTERNAL/REQUEST"]
    answered = {m.provenance[0]: m for m in msgs if m.source == "INTEROP" and m.value.get("request") and m.provenance}
    performed = {log.get(m.provenance[0]).value["request"] for m in msgs
                 if m.source == "INTEROP" and m.kind == "action" and m.value.get("perform") and m.provenance}
    for rid, chk, what in (("INTEROP-1-01", "excluded_functions_refused", "harmonization, external enforcement, binding external norms"),
                           ("INTEROP-5-04", "no_regime_adjudication", "adjudication between external legal regimes"),
                           ("INTEROP-10-01", "no_automatic_harmonization", "automatic legal harmonization"),
                           ("INTEROP-12-01", "no_geopolitical_resolution", "resolution of geopolitical conflicts"),
                           ("INTEROP-12-02", "no_legal_unification", "unification of legal systems"),
                           ("INTEROP-12-03", "no_compliance_guarantee", "a guarantee of compliance by external actors"),
                           ("INTEROP-12-04", "no_enforcement_bridge", "acting as an enforcement bridge")):
        mine = [m for m in reqs if REQUESTS[m.value["request"]] == rid]
        if not mine:
            out.append(na(rid, chk, what, "no such request in this experiment"))
            continue
        bad = [f"{m.value['request']} performed" if m.value["request"] in performed else f"{m.value['request']} not answered"
               for m in mine if m.value["request"] in performed or answered.get(m.event_id, None) is None
               or answered[m.event_id].value.get("response") != "refused"]
        out.append(v(rid, chk, bad, f"{len(mine)} request(s) for {what} refused at the boundary ({rid})",
                     "{n} excluded functions performed or not refused"))
    acts = [m.event_id for m in msgs if m.source == "INTEROP" and m.kind in ("action", "decision")]
    out.append(v("INTEROP-2-01", "purely_translational", acts,
                 "INTEROP produced only boundary records, translations, exports as evidence and refusals; no action",
                 "{n} INTEROP actions (compliance, rollback, excluded functions)"))
    recs = [m for m in msgs if m.source == "INTEROP" and (m.value.get("boundary_event") or m.value.get("translation"))]
    out.append(v("INTEROP-3-02", "defined_interfaces", [m.event_id for m in recs if m.value.get("interface") not in INTERFACES.values()],
                 f"{len(recs)} boundary records, each at a formally defined interface ({', '.join(sorted(INTERFACES.values()))})",
                 "{n} boundary records at an undeclared interface") if recs else
               na("INTEROP-3-02", "defined_interfaces", "boundary records", "no interaction with an external system"))
    trs = [m for m in msgs if m.source == "INTEROP" and m.value.get("translation")]
    base_trs = [m.value["translation"] for m in baseline.messages() if m.source == "INTEROP" and m.value.get("translation")]
    out.append(v("INTEROP-3-03", "deterministic_translation",
                 [m.event_id for m in trs if m.value["translation"] != translate(m.value["translation"]["external_value"])
                  or m.value["translation"] not in base_trs],
                 f"{len(trs)} translation(s) equal to the declared mapping and identical across runs",
                 "{n} translations differ from the declared mapping or between runs") if trs else
               na("INTEROP-3-03", "deterministic_translation", "translations", "no external value translated"))
    consent = [m.event_id for m in msgs if m.value and m.value.get("inference")]
    out.append(v("INTEROP-4.3-01", "compatibility_not_consent", consent,
                 "no compatibility at an interface was recorded as legitimacy, obligation or consent",
                 "{n} inferences of consent, legitimacy or obligation from compatibility"))
    norm = uses("EXTERNAL/LEGAL") if ext_ids("EXTERNAL/LEGAL") else []
    comply = [m.event_id for m in msgs if m.source == "INTEROP" and m.kind == "action" and m.value.get("comply_with")]
    leak = norm + comply + consent + sorted(x for x in performed if x == "accept_external_norm")
    out.append(v("INTEROP-3-04", "no_normative_leakage", leak,
                 "no external authority, norm or obligation entered DKP (no internal decision from an external ruling, no "
                 "compliance act, no consent inferred, no external norm accepted)",
                 "{n} imports of external authority, norms or obligations"))
    converge = norm + sorted(x for x in performed if x in ("harmonize_legal_systems", "unify_legal_systems",
                                                          "automatic_harmonization", "accept_external_norm"))
    converge += [m.event_id for m in recs if m.value.get("interface") not in INTERFACES.values()]
    out.append(v("INTEROP-12-05", "compatibility_not_convergence", converge,
                 "external systems interacted through defined interfaces and translations, while internal rules took nothing "
                 "from them (no harmonization, unification or adopted norm)",
                 "{n} cases of convergence or of interaction without a defined interface"))
    mirrors = [m for m in msgs if m.source == "MIRROR"]
    if mirrors:
        bad = [m.event_id for m in mirrors if sha256_text(canonical_json(log.get(m.value["mirror_of"]).value)) != m.value["digest"]]
        out.append(v("RESILIENCE-5.3-03", "mirror_unaltered", bad, "outputs mirrored for external human validation are unaltered",
                     "{n} mirrored outputs altered"))
    else:
        out.append(na("RESILIENCE-5.3-03", "mirror_unaltered", "mirroring", "no mirroring for human validation"))
    eps = [m for m in msgs if m.source.startswith("ENTRYPOINT")]
    if eps:
        inv = [m for m in msgs if m.source == "RESILIENCE" and m.value.get("invalidated")]
        still = [m.event_id for m in eps if m.value["valid"] and m.arrived_at > eps[0].arrived_at]
        out.append(v("RESILIENCE-5.7-03", "entry_point_invalidated", still + ([] if inv else ["not invalidated"]),
                     "the entry point that stripped PTL metadata was invalidated locally", "{n} outputs from an invalid entry point"))
        reported = {m.value["output"] for m in msgs if m.source == "AUDIT" and m.value.get("deviation") == "D2"}
        bad = [m.event_id for m in eps if m.event_id not in reported]
        out.append(v("AUDIT-EpistemicMetadataVerification-04", "metadata_deviation_reported", bad,
                     f"all {len(eps)} outputs without epistemic metadata reported as D2 deviations",
                     "{n} outputs without metadata not reported"))
    else:
        out.append(na("RESILIENCE-5.7-03", "entry_point_invalidated", "entry point integrity", "no metadata-stripping entry point"))
        out.append(na("AUDIT-EpistemicMetadataVerification-04", "metadata_deviation_reported", "metadata deviations",
                      "no output without metadata"))
    bad = [m.event_id for m in decisions if epistemic_problems(m.epistemic)]
    out.append(v("AUDIT-EpistemicMetadataVerification-01", "operational_outputs_have_metadata", bad,
                 f"all {len(decisions)} internal operational outputs carry the six EB §5 fields", "{n} outputs without metadata"))
    inj = [m.event_id for m in msgs if m.source == "AUDIT" and m.kind == "action"]
    out.append(v("AUDIT-10-01", "audit_observes_only", inj, "audit only observed and reported", "{n} audit interventions in execution"))
    again = run(r, failure=True)
    out.append(v("AUDIT-5.4-01", "deterministic_execution", [] if again.digest() == log.digest() else ["digest"],
                 "re-executing the same inputs gives a byte-identical log", "re-execution differs"))
    return out


IMPLEMENTS = {
    "INTEROP-5-02": ("external_rulings_not_binding", "IMPLEMENTED", None),
    "INTEROP-3-01": ("external_not_governed", "PARTIAL", "'Governed' is observed as a directive addressed to the external system."),
    "INTEROP-5-01": ("exports_as_evidence", "IMPLEMENTED", None),
    "INTEROP-5-03": ("compliance_by_subjects", "PARTIAL", "The external ruling is a declared event."),
    "INTEROP-6-01": ("economic_channels", "PARTIAL", "Interactions are declared; 'MAY' read as the permitted channels."),
    "INTEROP-6-02": ("justice_weighted_translation", "PARTIAL", "No translation function is given: UNKNOWN."),
    "INTEROP-6-04": ("external_values_flagged", "IMPLEMENTED", None),
    "INTEROP-7-04": ("blackbox_not_authoritative", "IMPLEMENTED", None),
    "INTEROP-8-01": ("external_info_as_i1", "PARTIAL", "I1 classification and non-use as PTL are checked; INFO transitions are not modelled."),
    "INTEROP-8-02": ("no_external_validation_for_ptl", "IMPLEMENTED", None),
    "INTEROP-9-02": ("internal_execution_unaffected", "IMPLEMENTED", None),
    "INTEROP-9-03": ("no_rollback", "IMPLEMENTED", None),
    "INTEROP-9-04": ("no_crisis_from_interop", "IMPLEMENTED", None),
    "INTEROP-10-02": ("no_external_decision_dependency", "IMPLEMENTED", None),
    "INTEROP-10-03": ("no_governance_by_api", "IMPLEMENTED", None),
    "INTEROP-10-04": ("no_silent_norm_import", "PARTIAL", "Norm import is observed as execution of an external ruling."),
    "INTEROP-11-03": ("boundary_events_recorded", "IMPLEMENTED", None),
    "RESILIENCE-5.3-03": ("mirror_unaltered", "IMPLEMENTED", None),
    "RESILIENCE-5.7-03": ("entry_point_invalidated", "IMPLEMENTED", None),
    "AUDIT-EpistemicMetadataVerification-01": ("operational_outputs_have_metadata", "IMPLEMENTED", None),
    "AUDIT-EpistemicMetadataVerification-04": ("metadata_deviation_reported", "IMPLEMENTED", None),
    "AUDIT-10-01": ("audit_observes_only", "IMPLEMENTED", None),
    "AUDIT-5.4-01": ("deterministic_execution", "PARTIAL", "Determinism of this module's execution only."),
    "CRISIS-4-01": ("ptl_loss_triggers_crisis", "PARTIAL", "Only the PTL-loss trigger; 'correction tolerance' is not defined (declared input)."),
    "INTEROP-1-01": ("excluded_functions_refused", "PARTIAL", "The three exclusions are observed as refusals of declared requests; "
                     "binding external rulings are also checked under §5."),
    "INTEROP-2-01": ("purely_translational", "PARTIAL", "'Purely translational' is observed as: INTEROP emits records only, no action."),
    "INTEROP-3-02": ("defined_interfaces", "PARTIAL", "The interfaces are a declared lab list; their formal specification is not modelled."),
    "INTEROP-3-03": ("deterministic_translation", "PARTIAL", "Determinism of the declared mapping (same input, same output, both runs); "
                     "the mapping itself is a lab stand-in: no translation function is given (§6, UNKNOWN in INTEROP-6-02)."),
    "INTEROP-3-04": ("no_normative_leakage", "PARTIAL", "Leakage is observed through declared events: execution of an external ruling, "
                     "compliance acts, consent inferences, an accepted external norm."),
    "INTEROP-4.3-01": ("compatibility_not_consent", "PARTIAL", "Observed as an explicit inference record; implicit treatment is not observable."),
    "INTEROP-5-04": ("no_regime_adjudication", "PARTIAL", "Observed as the refusal of a declared request."),
    "INTEROP-10-01": ("no_automatic_harmonization", "PARTIAL", "Observed as the refusal of a declared request."),
    "INTEROP-12-01": ("no_geopolitical_resolution", "PARTIAL", "Observed as the refusal of a declared request."),
    "INTEROP-12-02": ("no_legal_unification", "PARTIAL", "Observed as the refusal of a declared request."),
    "INTEROP-12-03": ("no_compliance_guarantee", "PARTIAL", "Observed as the refusal of a declared request."),
    "INTEROP-12-04": ("no_enforcement_bridge", "PARTIAL", "Observed as the refusal of a declared request."),
    "INTEROP-12-05": ("compatibility_not_convergence", "PARTIAL", "Read as a conjunction: interaction through defined interfaces "
                      "(compatibility) and no harmonization, unification or adopted external norm (no convergence)."),
}


class InteropFailureModule(LabModule):
    id = "interop_failure"
    version = "1.3.0"
    title = {"en": "Failure of an external interface (S-LAB-10)", "ru": "Отказ внешнего интерфейса (S-LAB-10)"}
    summary = {"en": "An external court, market, data provider or API fails or pushes in: does the inside keep running "
                     "unchanged, with nothing external becoming binding?",
               "ru": "Внешний суд, рынок, поставщик данных или API отказывает или давит: продолжает ли внутренняя часть "
                     "работать без изменений, не становится ли внешнее обязательным?"}
    protocols = ["DKP-8-INTEROP-001", "DKP-6-RESILIENCE-001", "DKP-8-AUDIT-001", "DKP-4-CRISIS-001"]
    example_order = ["external_outage", "mirror_outage_untrusted", "registered_sources_lost", "tolerance_missing",
                     "faulty_boundary", "former_lab_premise"]
    alternative_examples: List[str] = []
    implements = IMPLEMENTS
    tests = ["tests/lab/test_interop_failure_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-IO-1", "source": "missing", "text": {
            "en": "'Correction tolerance' for PTL loss (CRISIS §4) is a declared share of lost sources; the corpus gives no value.",
            "ru": "'Допуск коррекции' потерь PTL (CRISIS §4) — объявленная доля потерянных источников; в корпусе значения нет."}},
        {"id": "H-IO-2", "source": "text", "text": {
            "en": "A provider's sources are either an External System (INTEROP §3: 'not governed by DKP protocols'; §8: only "
                  "untrusted I1, never a substitute for PTL verification) or registered PTL sources governed by ORACLE. "
                  "The outage of the first is an interop failure (§9: no Crisis); of the second, a loss of PTL outputs (CRISIS §4).",
            "ru": "Источники провайдера — либо внешняя система (INTEROP §3: 'not governed by DKP protocols'; §8: только "
                  "недоверенный I1, не замена PTL-верификации), либо зарегистрированные источники PTL под ORACLE. Отказ "
                  "первых — отказ интероперабельности (§9: без кризиса); вторых — потеря выходов PTL (CRISIS §4)."}},
    ]
    inputs = {
        "horizon_steps": {"type": "int", "min": 2, "max": 2000, "default": 24, "unit": "h", "source": "user",
                          "label": {"en": "Hours", "ru": "Часов"}},
        "internal_sources": {"type": "int", "min": 1, "max": 1000, "default": 8, "source": "user",
                             "label": {"en": "Internal PTL sources", "ru": "Внутренние источники PTL"}},
        "mirror_sources": {"type": "int", "min": 0, "max": 1000, "default": 2, "source": "user",
                           "label": {"en": "Sources of the outside provider", "ru": "Источники внешнего провайдера"}},
        "mirror_role": {"type": "enum", "values": ["untrusted_interop", "registered_ptl_source"], "default": "untrusted_interop",
                        "source": "user", "label": {"en": "Role of the provider's sources (H-IO-2)",
                                                    "ru": "Роль источников провайдера (H-IO-2)"}},
        "ptl_loss_tolerance": {"type": "number", "min": -1, "max": 1, "default": 0.25, "source": "missing",
                               "label": {"en": "PTL loss tolerance (-1: not defined; H-IO-1)", "ru": "Допуск потерь PTL (-1: не определён; H-IO-1)"}},
        "external_failure_window": {"type": "pair", "min": 0, "max": 10 ** 6, "default": [6, 14], "unit": "h", "source": "user",
                                    "label": {"en": "External system unreliable from/to hour", "ru": "Внешняя система ненадёжна с/до часа"}},
        "external_ruling_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 8, "unit": "h", "source": "user",
                                 "label": {"en": "External ruling arrives at hour", "ru": "Внешнее решение приходит в час"}},
        "external_value_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 3, "unit": "h", "source": "user",
                                "label": {"en": "External value via asset bridge at hour", "ru": "Внешняя ценность через мост в час"}},
        "blackbox_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 10, "unit": "h", "source": "user",
                          "label": {"en": "Black-box input at hour", "ru": "Вход 'чёрного ящика' в час"}},
        "external_info_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 12, "unit": "h", "source": "user",
                               "label": {"en": "External consensus claim at hour", "ru": "Внешний 'консенсус' в час"}},
        "export_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 5, "unit": "h", "source": "user",
                        "label": {"en": "A DKP output is exported to an external court at hour (INTEROP §5)",
                                  "ru": "Выход DKP передаётся во внешний суд в час (INTEROP §5)"}},
        "human_validation_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 4, "unit": "h", "source": "user",
                                  "label": {"en": "Output mirrored for human validation at hour", "ru": "Выход отражён для проверки человеком в час"}},
        "stripping_entry_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 16, "unit": "h", "source": "user",
                                 "label": {"en": "Third-party entry point strips metadata from hour (-1: never)",
                                           "ru": "Сторонняя точка входа срезает метаданные с часа (-1: никогда)"}},
        "request_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 2, "unit": "h", "source": "user",
                         "label": {"en": "Out-of-scope requests arrive at hour (-1: never)", "ru": "Запросы вне сферы приходят в час (-1: никогда)"}},
        "out_of_scope_requests": {"type": "list", "min_items": 0, "max_items": len(REQUESTS), "items": {"type": "enum", "values": list(REQUESTS)},
                                  "default": list(REQUESTS), "source": "user",
                                  "label": {"en": "Requests for functions INTEROP excludes (§1, §5, §10, §12)",
                                            "ru": "Запросы функций, которые INTEROP исключает (§1, §5, §10, §12)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        if not all(float(x).is_integer() for x in r["external_failure_window"]):
            p.append("input.external_failure_window: whole hours")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if len(set(r["out_of_scope_requests"])) != len(r["out_of_scope_requests"]):
            p.append("input.out_of_scope_requests: repeated request")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r, failure=True)
        base = run(r, failure=False)
        res = checks(r, log, base)
        msgs = log.messages()
        outputs = {"internal_decisions": sum(1 for m in msgs if m.source == "DKP"),
                   "internal_decisions_without_failure": sum(1 for m in base.messages() if m.source == "DKP"),
                   "boundary_events": sum(1 for m in msgs if m.source == "INTEROP"),
                   "requests_refused": sum(1 for m in msgs if m.source == "INTEROP" and m.value.get("response") == "refused"),
                   "crisis_entered": any(m.source == "CRISIS" and m.value.get("enter") for m in msgs),
                   "messages": [m.as_dict() for m in msgs if m.source != "AUDIT"][:300],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        role = {"untrusted_interop": ("an External System: readings enter as untrusted I1, not as PTL (INTEROP §3, §8)",
                                      "внешняя система: показания входят как недоверенный I1, а не как PTL (INTEROP §3, §8)"),
                "registered_ptl_source": ("registered PTL sources: their outage is a loss of PTL outputs (CRISIS §4), not an "
                                          "interop failure", "зарегистрированные источники PTL: их отказ — потеря выходов PTL "
                                          "(CRISIS §4), а не отказ интероперабельности")}[r["mirror_role"]]
        explain = [{"en": f"The provider's {r['mirror_sources']} sources are {role[0]}.",
                    "ru": f"{r['mirror_sources']} источников провайдера — {role[1]}."},
                   {"en": f"{outputs['internal_decisions']} internal decisions with the external failure, "
                          f"{outputs['internal_decisions_without_failure']} without; {outputs['boundary_events']} boundary records; "
                          f"crisis entered: {outputs['crisis_entered']}.",
                    "ru": f"Внутренних решений при отказе: {outputs['internal_decisions']}, без отказа: "
                          f"{outputs['internal_decisions_without_failure']}; записей на границе: {outputs['boundary_events']}; "
                          f"кризис: {outputs['crisis_entered']}."}]
        if "mirror_feeds_ptl" in r["faults"]:
            explain.append({"en": "Counterexample: the external mirror is counted as PTL — the premise under which the lab "
                                  "once reported F-013; INTEROP §8 forbids it.",
                            "ru": "Контрпример: внешнее зеркало засчитано как PTL — посылка, при которой лаборатория "
                                  "когда-то сообщила F-013; INTEROP §8 это запрещает."})
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"internal_decisions": outputs["internal_decisions"],
                "decisions_lost_to_failure": outputs["internal_decisions_without_failure"] - outputs["internal_decisions"],
                "crisis_entered": outputs["crisis_entered"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "external_outage": {},
            "mirror_outage_untrusted": {"mirror_sources": 4, "ptl_loss_tolerance": 0.25},
            "registered_sources_lost": {"mirror_sources": 4, "ptl_loss_tolerance": 0.25, "mirror_role": "registered_ptl_source"},
            "tolerance_missing": {"mirror_sources": 4, "ptl_loss_tolerance": -1, "mirror_role": "registered_ptl_source"},
            "faulty_boundary": {"faults": ["binding_external_ruling", "blackbox_authoritative", "info_substitutes_ptl",
                                           "alter_mirror", "audit_masks"]},
            "former_lab_premise": {"mirror_sources": 4, "ptl_loss_tolerance": 0.25,
                                   "faults": ["mirror_feeds_ptl", "crisis_from_interop"]},
            "faulty_legal_economic": {"faults": ["govern_external", "export_as_ruling", "system_complies", "direct_ledger_write"]},
            "faulty_scope": {"faults": ["interop_overreach", "undeclared_interface", "nondeterministic_translation",
                                        "compatibility_as_consent"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"fractional_window": {"external_failure_window": [1.5, 3]}, "unknown_fault": {"faults": ["obey"]}}
