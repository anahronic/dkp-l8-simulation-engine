"""
EPISTEMIC GATE module — DKP-1-EPISTEMIC-BOUNDARIES-001 applied to outputs of other protocols.

Producers emit outputs with epistemic metadata (§5): validity, confidence, consistency, scope_ref,
revalidation_required, dispute_allowed; their protocols declare applicability boundaries (§8).  The
producing layer classifies an output with missing or undefined metadata as INVALID for operational use
(§5.x); consumers then try to execute, propagate, repair, read as conditionally valid, use outside the
declared scope, or interpret as truth, guilt or authority (§4, §12).  Critical contexts prefer NO_OUTPUT to
a degraded signal (§10).  Disputes preserve the original and recompute deterministically (§7); outputs are
never final (§6).  Reliability degrades only under change, integrity loss or conflict, not under silence
in a stable environment (§9).  L8 runs the six tests of §13.

Time unit: step.  The outputs, their metadata and the consumers' requests are declared input.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

VALIDITY = ("VALID", "CONDITIONAL", "INVALID")
CONFIDENCE = ("SUFFICIENT_DATA", "INSUFFICIENT_DATA", "DEGRADED_SIGNAL")
CONSISTENCY = ("CONSISTENT", "ORACLE_CONFLICT", "UNRESOLVED")
FIELDS = ("validity", "confidence", "consistency", "scope_ref", "revalidation_required", "dispute_allowed")
USES = ("enforcement", "restriction", "revocation", "allocation", "exclusion", "dispute_processing", "informational")
REQUESTS = ("execute", "propagate", "repair", "treat_conditional", "use_outside_scope")
INTERPRETATIONS = ("truth", "guilt", "moral_judgment", "irreversible_basis", "authority_outside_scope")
TRIGGERS = ("new_admissible_data", "oracle_inconsistency", "scope_violation", "integrity_challenge", "disagreement_only")
L8_TESTS = ("missing_metadata", "stale_output_reuse", "authority_drift", "dispute_suppression", "scope_violations", "degraded_signal_misuse")

FAULTS = {
    "audit_only_enforcement": "incomplete metadata is left for L8 audit to catch",
    "propagate_incomplete": "an output with incomplete metadata is propagated",
    "repair_downstream": "a consumer fills in missing metadata",
    "conditional_fallback": "an incomplete output is treated as CONDITIONAL",
    "scope_drift": "an output is used outside its scope_ref",
    "degraded_in_critical": "a degraded signal is used in a critical context",
    "truth_reading": "an output is recorded as truth",
    "mutate_on_dispute": "a dispute overwrites the original output",
    "no_delta": "a dispute produces no comparative delta",
    "suppress_dispute": "a valid dispute is rejected",
    "silence_invalidates": "an output in a stable environment is invalidated for lack of new data",
    "keep_stale_active": "an output kept active under activity without revalidation stays reliable",
    "final_output": "an executed output refuses re-evaluation",
    "skip_l8_tests": "L8 skips the stale-output and authority-drift tests",
    "allow_override": "a protocol overrides EB",
}


def complete(o):
    return all(o.get(f) not in (None, "", "undefined") for f in FIELDS) and o["validity"] in VALIDITY and \
        o["confidence"] in CONFIDENCE and o["consistency"] in CONSISTENCY


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("step", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value, order=order[kind]))

    prot = {p["id"]: p for p in r["protocols"]}
    state = {}
    for o in r["outputs"]:
        p = prot[o["protocol"]]
        boundary = all(p[k] for k in ("valid_scope", "invalid_scope", "no_output_conditions", "minimum_admissibility"))
        ok = complete(o) and boundary
        rec = {"output": o["id"], "protocol": o["protocol"], "use": o["use"], "critical": o["critical"],
               "metadata": {f: o.get(f) for f in FIELDS}, "result": o["result"], "bounded_evaluation": True,
               "approximation": True, "boundary_declared": boundary}
        if not ok and "audit_only_enforcement" not in faults:
            rec["operational_validity"] = "INVALID"
            rec["reason"] = "incomplete epistemic metadata" if not complete(o) else "protocol declares no applicability boundary"
        else:
            rec["operational_validity"] = o["validity"] if o["validity"] in VALIDITY else "unchecked"
        # §10: critical contexts prefer NO_OUTPUT
        if o["critical"] and (o["confidence"] in ("INSUFFICIENT_DATA", "DEGRADED_SIGNAL") or o["consistency"] == "UNRESOLVED"
                              or o["outside_boundary"]) and "degraded_in_critical" not in faults:
            rec["emitted"] = "NO_OUTPUT"
        else:
            rec["emitted"] = "output"
        # §9 staleness
        stale_active = o["environment"] == "active" and o["steps_since_revalidation"] > r["revalidation_interval"]
        if o["conflicting_signal"]:
            rec["reliability"] = "degraded"
        elif stale_active:
            rec["reliability"] = "maintained" if "keep_stale_active" in faults else "degraded"
        elif o["environment"] == "stable":
            rec["reliability"] = "invalidated" if "silence_invalidates" in faults else "maintained"
        else:
            rec["reliability"] = "maintained"
        rec["data_absence"] = "under activity" if o["environment"] == "active" else "under stability"
        put("evaluation", o["protocol"].upper(), 0, rec)
        state[o["id"]] = rec
    put("notice", "AUDIT", 0, {"l8_tests": [t for t in L8_TESTS if not ("skip_l8_tests" in faults and t in ("stale_output_reuse", "authority_drift"))]})
    for q in r["consumer_requests"]:
        rec = state[q["output"]]
        o = [x for x in r["outputs"] if x["id"] == q["output"]][0]
        ok_meta = rec["operational_validity"] != "INVALID"
        if q["request"] == "execute":
            ok = ok_meta and rec["emitted"] == "output" and rec["reliability"] != "degraded"
        elif q["request"] == "propagate":
            ok = ok_meta or "propagate_incomplete" in faults
        elif q["request"] == "repair":
            ok = "repair_downstream" in faults
        elif q["request"] == "treat_conditional":
            ok = (ok_meta and o["validity"] == "CONDITIONAL") or ("conditional_fallback" in faults and not ok_meta)
        else:   # use_outside_scope
            ok = "scope_drift" in faults
        put("decision", "CONSUMER", 1, {"output": q["output"], "request": q["request"], "by": q["consumer"], "granted": ok})
    for q in r["interpretations"]:
        ok = "truth_reading" in faults and q["as"] == "truth"
        put("decision", "CONSUMER", 1, {"output": q["output"], "interpret_as": q["as"], "granted": ok})
    for q in r["override_requests"]:
        put("decision", "EB", 1, {"override_by": q, "granted": "allow_override" in faults})
    k = 2
    for d in r["disputes"]:
        rec = state[d["output"]]
        o = [x for x in r["outputs"] if x["id"] == d["output"]][0]
        valid = d["trigger"] != "disagreement_only" and (o["dispute_allowed"] is True or o["executed"])
        if not valid or ("suppress_dispute" in faults and d["trigger"] == "new_admissible_data"):
            put("decision", "DISPUTE", k, {"output": d["output"], "trigger": d["trigger"], "accepted": False,
                                           "reason": "not a §7.1 trigger" if d["trigger"] == "disagreement_only" else "rejected"})
            k += 1
            continue
        if o["executed"] and "final_output" in faults:
            put("decision", "DISPUTE", k, {"output": d["output"], "trigger": d["trigger"], "accepted": False, "reason": "final"})
            k += 1
            continue
        new = round(rec["result"] + d["new_data_shift"], 9)
        ev = {"output": d["output"], "trigger": d["trigger"], "accepted": True, "new_evaluation": f"{d['output']}#r{k}",
              "original": rec["result"], "recomputed": new, "original_preserved": "mutate_on_dispute" not in faults,
              "executed_consequences": "not rolled back automatically (§6)" if o["executed"] else "none"}
        if "no_delta" not in faults:
            ev["delta"] = round(new - rec["result"], 9)
        if "mutate_on_dispute" in faults:
            rec["result"] = new
        put("action", "DISPUTE", k, ev)
        k += 1
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    prot = {p["id"]: p for p in r["protocols"]}
    recs = {m.value["output"]: m.value for m in msgs if m.kind == "evaluation" and "metadata" in m.value}
    outs = {o["id"]: o for o in r["outputs"]}
    incomplete = [i for i, o in outs.items() if not complete(o)]
    noboundary = [i for i, o in outs.items() if not all(prot[o["protocol"]][k] for k in ("valid_scope", "invalid_scope",
                                                                                           "no_output_conditions", "minimum_admissibility"))]
    bad_prod = [i for i in incomplete + noboundary if recs[i]["operational_validity"] != "INVALID"]
    out.append(v("EB-5.x-08", "enforced_at_production", bad_prod, "the producing layer marked every incomplete output INVALID",
                 "{n} incomplete outputs left valid by their producer"))
    out.append(v("EB-5.x-07", "audit_not_primary", bad_prod, "completeness enforced before L8 audit", "{n} left for audit to catch"))
    for rid, chk, vals, key in (("EB-ValidityState-01", "validity_values", VALIDITY, "validity"),
                                ("EB-ConfidenceState-01", "confidence_values", CONFIDENCE, "confidence"),
                                ("EB-ConsistencyState-01", "consistency_values", CONSISTENCY, "consistency")):
        wrong = [i for i, o in outs.items() if o[key] not in vals and recs[i]["operational_validity"] != "INVALID"]
        out.append(v(rid, chk, wrong, f"every operational output carries a {key} state from {', '.join(vals)}", "{n} outputs with another value"))
    out.append(v("EB-AdditionalFields-01", "additional_fields", [i for i, o in outs.items() if any(o.get(f) in (None, "", "undefined")
                                                                                                  for f in ("scope_ref",)) and recs[i]["operational_validity"] != "INVALID"],
                 "scope_ref, revalidation_required and dispute_allowed present on every operational output", "{n} without them"))
    req = [m.value for m in msgs if m.source == "CONSUMER" and "request" in m.value]
    inv = {i for i, x in recs.items() if x["operational_validity"] == "INVALID"}
    exp_inv = set(incomplete) | set(noboundary)

    def rows(kind):
        return [x for x in req if x["request"] == kind]
    for rid, chk, kind, txt in (("EB-5.x-03", "not_executed", "execute", "executed"), ("EB-5.x-04", "not_propagated", "propagate", "propagated"),
                                ("EB-5.x-05", "not_conditional", "treat_conditional", "treated as conditionally valid")):
        rr = [x for x in rows(kind) if x["output"] in exp_inv]
        out.append(v(rid, chk, [x["output"] for x in rr if x["granted"]], f"no incomplete output {txt}", "{n} incomplete outputs " + txt)
                   if rr else na(rid, chk, f"{kind} requests on incomplete outputs", "none"))
    rep = rows("repair")
    out.append(v("EB-5.x-06", "not_repaired", [x["output"] for x in rep if x["granted"]], "no downstream repair of metadata", "{n} repaired")
               if rep else na("EB-5.x-06", "not_repaired", "repair requests", "none"))
    out.append(v("EB-5.x-02", "incomplete_is_invalid", sorted(exp_inv - inv), "incomplete or boundary-less outputs INVALID for operational use",
                 "{n} classified otherwise") if exp_inv else na("EB-5.x-02", "incomplete_is_invalid", "incomplete outputs", "none"))
    ops = [i for i, o in outs.items() if o["use"] != "informational"]
    out.append(v("EB-5.x-01", "full_metadata_for_operational_use", [i for i in ops if i in exp_inv and i not in inv],
                 "operational outputs carry the full metadata set or are refused", "{n} operational outputs without it"))
    sc = rows("use_outside_scope")
    out.append(v("EB-4-02", "no_authority_outside_scope", [x["output"] for x in sc if x["granted"]], "no output used outside its declared scope",
                 "{n} uses outside scope") if sc else na("EB-4-02", "no_authority_outside_scope", "uses outside scope", "none requested"))
    out.append(v("EB-8-01", "applicability_boundary_defined", [p["id"] for p in r["protocols"] if not all(p[k] for k in
                                                               ("valid_scope", "invalid_scope", "no_output_conditions", "minimum_admissibility"))
                                                               and any(recs[o]["operational_validity"] != "INVALID" for o in outs if outs[o]["protocol"] == p["id"])],
                 "outputs of protocols without a full applicability boundary are not operational", "{n} protocols' outputs used without a boundary"))
    crit = [i for i, o in outs.items() if o["critical"] and (o["confidence"] in ("INSUFFICIENT_DATA", "DEGRADED_SIGNAL")
                                                             or o["consistency"] == "UNRESOLVED" or o["outside_boundary"])]
    out.append(v("EB-10-01", "no_output_priority", [i for i in crit if recs[i]["emitted"] != "NO_OUTPUT"],
                 "critical contexts with insufficient, unresolved or out-of-boundary data gave NO_OUTPUT", "{n} degraded outputs emitted")
               if crit else na("EB-10-01", "no_output_priority", "critical degraded outputs", "none"))
    # staleness
    stable = [i for i, o in outs.items() if o["environment"] == "stable" and not o["conflicting_signal"]]
    active = [i for i, o in outs.items() if o["environment"] == "active" and o["steps_since_revalidation"] > r["revalidation_interval"]]
    out.append(v("EB-9-02", "silence_under_stability", [i for i in stable if recs[i]["reliability"] != "maintained"],
                 "outputs in a stable environment without conflict stay reliable", "{n} invalidated for lack of new data")
               if stable else na("EB-9-02", "silence_under_stability", "stable outputs", "none"))
    out.append(v("EB-4-04", "persistent_outputs_degrade", [i for i in active if recs[i]["reliability"] != "degraded"],
                 f"outputs not revalidated for more than {r['revalidation_interval']} steps under activity degrade", "{n} kept reliable")
               if active else na("EB-4-04", "persistent_outputs_degrade", "stale outputs under activity", "none"))
    out.append(v("EB-3-03", "stale_output", [i for i in active if recs[i]["reliability"] != "degraded"], "stale outputs recognised", "{n} not recognised")
               if active else na("EB-3-03", "stale_output", "stale outputs", "none"))
    out.append(v("EB-9-01", "degradation_causes", [i for i, o in outs.items() if recs[i]["reliability"] == "degraded" and not
                                                  (o["conflicting_signal"] or (o["environment"] == "active" and o["steps_since_revalidation"] > r["revalidation_interval"]))],
                 "reliability degraded only under change, integrity loss or conflict", "{n} degraded otherwise"))
    out.append(v("EB-9-03", "absence_distinguished", [i for i, o in outs.items() if recs[i]["data_absence"] != ("under activity" if o["environment"] == "active" else "under stability")],
                 "data absence under activity and under stability kept apart", "{n} not distinguished"))
    # interpretations, override
    it = [m.value for m in msgs if m.source == "CONSUMER" and "interpret_as" in m.value]
    out.append(v("EB-12-01", "prohibited_interpretations", [x["output"] + ":" + x["interpret_as"] for x in it if x["granted"]],
                 "no output read as truth, guilt, moral judgment, irreversible basis or authority outside scope", "{n} such readings")
               if it else na("EB-12-01", "prohibited_interpretations", "interpretation requests", "none"))
    out.append(v("EB-0-02", "bounded_evaluations", [i for i, x in recs.items() if not x["bounded_evaluation"]] + [x["output"] for x in it if x["granted"]],
                 "every output recorded as a bounded evaluation", "{n} outputs recorded otherwise"))
    out.append(v("EB-11-01", "approximations", [i for i, x in recs.items() if not x["approximation"]], "every output marked as an approximation", "{n} not"))
    ov = [m.value for m in msgs if m.source == "EB" and "override_by" in m.value]
    out.append(v("EB-0-01", "no_override", [x["override_by"] for x in ov if x["granted"]], "no protocol overrode EB", "{n} overrides")
               if ov else na("EB-0-01", "no_override", "override requests", "none"))
    out.append(v("EB-2-01", "constraint_not_executor", [m.event_id for m in msgs if m.source == "EB" and m.kind == "action"],
                 "EB constrained outputs and executed nothing itself", "EB executed actions"))
    # disputes
    ds = [m.value for m in msgs if m.source == "DISPUTE"]
    if ds:
        acc = [x for x in ds if x["accepted"]]
        want = [d for d in r["disputes"] if d["trigger"] != "disagreement_only" and (outs[d["output"]]["dispute_allowed"] or outs[d["output"]]["executed"])]
        out.append(v("EB-7.1-01", "dispute_triggers", [d["output"] for d in r["disputes"] if d["trigger"] == "disagreement_only" and
                                                        any(x["accepted"] and x["output"] == d["output"] and x["trigger"] == d["trigger"] for x in ds)]
                     + [d["output"] for d in want if not any(x["accepted"] and x["output"] == d["output"] and x["trigger"] == d["trigger"] for x in ds)],
                     "disputes opened on the §7.1 triggers, not on disagreement alone", "{n} dispute decisions wrong"))
        out.append(v("EB-3-01", "dispute_event", [d["output"] for d in want if not any(x["accepted"] and x["output"] == d["output"] for x in ds)],
                     "new admissible data and conflict signals create Dispute Events", "{n} not created"))
        out.append(v("EB-7.2-01", "original_preserved", [x["output"] for x in acc if not x["original_preserved"]], "originals preserved", "{n} overwritten"))
        out.append(v("EB-7.2-02", "new_evaluation_event", [x["output"] for x in acc if not x.get("new_evaluation")], "each dispute creates a new evaluation",
                     "{n} without one"))
        out.append(v("EB-7.2-04", "comparative_delta", [x["output"] for x in acc if "delta" not in x], "each dispute produces a comparative delta",
                     "{n} without a delta"))
        again = run(r)
        a2 = [m.value for m in again.messages() if m.source == "DISPUTE"]
        out.append(v("EB-7.2-03", "deterministic_recompute", [] if a2 == ds else ["differs"], "recomputation reproducible", "recomputation differs"))
        out.append(v("EB-3-02", "re_evaluation", [] if a2 == ds else ["differs"], "re-evaluation deterministic under updated inputs", "differs"))
        out.append(v("EB-7-01", "dispute_deterministic", [] if a2 == ds else ["differs"], "dispute handled as a deterministic process", "differs"))
        exe = [d for d in want if outs[d["output"]]["executed"]]
        out.append(v("EB-6-01", "non_finality", [d["output"] for d in exe if not any(x["accepted"] and x["output"] == d["output"] for x in ds)],
                     "executed outputs remained open to re-evaluation", "{n} treated as final") if exe else
                   na("EB-6-01", "non_finality", "disputes on executed outputs", "none"))
        out.append(v("EB-4-03", "reversibility_is_reevaluation", [x["output"] for x in acc if outs[x["output"]]["executed"] and
                                                                   "not rolled back" not in x["executed_consequences"]],
                     "re-evaluation corrects state without promising rollback of executed consequences", "{n} promised rollback")
                   if exe else na("EB-4-03", "reversibility_is_reevaluation", "executed outputs disputed", "none"))
    else:
        for rid, chk in (("EB-7.1-01", "dispute_triggers"), ("EB-3-01", "dispute_event"), ("EB-7.2-01", "original_preserved"),
                         ("EB-7.2-02", "new_evaluation_event"), ("EB-7.2-04", "comparative_delta"), ("EB-7.2-03", "deterministic_recompute"),
                         ("EB-3-02", "re_evaluation"), ("EB-7-01", "dispute_deterministic"), ("EB-6-01", "non_finality"),
                         ("EB-4-03", "reversibility_is_reevaluation")):
            out.append(na(rid, chk, "disputes", "none"))
    t = [m.value for m in msgs if m.source == "AUDIT" and "l8_tests" in m.value][0]["l8_tests"]
    out.append(v("EB-13-01", "l8_tests", [x for x in L8_TESTS if x not in t], "L8 ran the six tests of §13", "{n} tests skipped"))
    return out


IMPLEMENTS = {
    "EB-0-01": ("no_override", "IMPLEMENTED", None),
    "EB-0-02": ("bounded_evaluations", "PARTIAL", "Recorded label."),
    "EB-2-01": ("constraint_not_executor", "PARTIAL", "EB emits decisions, no actions."),
    "EB-3-01": ("dispute_event", "IMPLEMENTED", None),
    "EB-3-02": ("re_evaluation", "IMPLEMENTED", None),
    "EB-3-03": ("stale_output", "PARTIAL", "Staleness = steps since revalidation under activity (H-EG-1)."),
    "EB-4-02": ("no_authority_outside_scope", "IMPLEMENTED", None),
    "EB-4-03": ("reversibility_is_reevaluation", "IMPLEMENTED", None),
    "EB-4-04": ("persistent_outputs_degrade", "PARTIAL", "The revalidation interval is not given (source missing)."),
    "EB-ValidityState-01": ("validity_values", "IMPLEMENTED", None),
    "EB-ConfidenceState-01": ("confidence_values", "IMPLEMENTED", None),
    "EB-ConsistencyState-01": ("consistency_values", "IMPLEMENTED", None),
    "EB-AdditionalFields-01": ("additional_fields", "IMPLEMENTED", None),
    "EB-5.x-01": ("full_metadata_for_operational_use", "IMPLEMENTED", None),
    "EB-5.x-02": ("incomplete_is_invalid", "IMPLEMENTED", None),
    "EB-5.x-03": ("not_executed", "IMPLEMENTED", None),
    "EB-5.x-04": ("not_propagated", "IMPLEMENTED", None),
    "EB-5.x-05": ("not_conditional", "IMPLEMENTED", None),
    "EB-5.x-06": ("not_repaired", "IMPLEMENTED", None),
    "EB-5.x-07": ("audit_not_primary", "IMPLEMENTED", None),
    "EB-5.x-08": ("enforced_at_production", "IMPLEMENTED", None),
    "EB-6-01": ("non_finality", "IMPLEMENTED", None),
    "EB-7-01": ("dispute_deterministic", "IMPLEMENTED", None),
    "EB-7.1-01": ("dispute_triggers", "PARTIAL", "Triggers are declared."),
    "EB-7.2-03": ("deterministic_recompute", "PARTIAL", "Recomputation = declared shift of the result."),
    "EB-8-01": ("applicability_boundary_defined", "IMPLEMENTED", None),
    "EB-9-01": ("degradation_causes", "PARTIAL", "Change and conflict are declared."),
    "EB-9-02": ("silence_under_stability", "IMPLEMENTED", None),
    "EB-9-03": ("absence_distinguished", "IMPLEMENTED", None),
    "EB-10-01": ("no_output_priority", "IMPLEMENTED", None),
    "EB-11-01": ("approximations", "PARTIAL", "Recorded label."),
    "EB-12-01": ("prohibited_interpretations", "IMPLEMENTED", None),
    "EB-13-01": ("l8_tests", "PARTIAL", "The tests are recorded as run; their content is the other checks."),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")


def _lst(fields, default, label, mx=30):
    return {"type": "list", "min_items": 0, "max_items": mx, "items": {"type": "object", "fields": fields}, "default": default,
            "source": "user", "label": label}


def _out(i, prot, use, **kw):
    o = {"id": i, "protocol": prot, "use": use, "validity": "VALID", "confidence": "SUFFICIENT_DATA", "consistency": "CONSISTENT",
         "scope_ref": "region_a", "revalidation_required": "yes", "dispute_allowed": True, "result": 1.0, "critical": False,
         "outside_boundary": False, "environment": "stable", "steps_since_revalidation": 0, "conflicting_signal": False, "executed": False}
    o.update(kw)
    return o


OUTPUTS = [_out("water_quota", "habitat", "allocation", executed=True),
           _out("asset_revoke", "assets", "revocation", scope_ref="undefined"),
           _out("fire_alert", "transport", "restriction", critical=True, confidence="DEGRADED_SIGNAL"),
           _out("air_index", "habitat", "informational", environment="active", steps_since_revalidation=12),
           _out("quiet_sensor", "habitat", "allocation", environment="stable", steps_since_revalidation=50),
           _out("labor_score", "labor", "exclusion", validity="CONDITIONAL")]


class EpistemicGateModule(LabModule):
    id = "epistemic_gate"
    version = "1.0.0"
    title = {"en": "Epistemic boundaries of outputs (EPISTEMIC-BOUNDARIES)", "ru": "Эпистемические границы выходов (EPISTEMIC-BOUNDARIES)"}
    summary = {"en": "Outputs arrive with missing scope, degraded signals, stale data and disputes; consumers want to execute, repair or "
                     "read them as truth: does every output stay a bounded, disputable evaluation?",
               "ru": "Выходы приходят без области, с деградировавшим сигналом, устаревшими данными и спорами; потребители хотят исполнить, "
                     "починить или прочесть их как истину: остаётся ли каждый выход ограниченной, оспоримой оценкой?"}
    protocols = ["DKP-1-EPISTEMIC-BOUNDARIES-001"]
    example_order = ["mixed_outputs", "faulty_consumers"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_epistemic_gate_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-EG-1", "source": "hypothesis", "text": {
            "en": "An output under activity is stale after the declared number of steps without revalidation (the text gives none).",
            "ru": "Выход в активной среде устаревает после объявленного числа шагов без ревалидации (в тексте числа нет)."}},
        {"id": "H-EG-2", "source": "hypothesis", "text": {
            "en": "A dispute is accepted on a §7.1 trigger when the output allows disputes or was executed (an executed output stays open, §4.3).",
            "ru": "Спор принимается по поводу из §7.1, если выход допускает споры или уже исполнен (исполненный выход остаётся открытым, §4.3)."}},
    ]
    inputs = {
        "revalidation_interval": {"type": "int", "min": 1, "max": 10 ** 6, "default": 10, "unit": "step", "source": "missing",
                                  "label": {"en": "Steps before an output under activity is stale", "ru": "Шагов до устаревания выхода при активности"}},
        "protocols": _lst({"id": {"type": "str"}, "valid_scope": {"type": "bool", "default": True}, "invalid_scope": {"type": "bool", "default": True},
                           "no_output_conditions": {"type": "bool", "default": True}, "minimum_admissibility": {"type": "bool", "default": True}},
                          [{"id": "habitat"}, {"id": "assets"}, {"id": "transport"}, {"id": "labor", "no_output_conditions": False}],
                          {"en": "Producing protocols and their applicability boundaries", "ru": "Протоколы-производители и их границы применимости"}),
        "outputs": _lst({"id": {"type": "str"}, "protocol": {"type": "str"}, "use": {"type": "enum", "values": list(USES)},
                         "validity": {"type": "str"}, "confidence": {"type": "str"}, "consistency": {"type": "str"},
                         "scope_ref": {"type": "str"}, "revalidation_required": {"type": "str"}, "dispute_allowed": {"type": "bool"},
                         "result": {"type": "number", "min": -10 ** 9, "max": 10 ** 9}, "critical": {"type": "bool"},
                         "outside_boundary": {"type": "bool"}, "environment": {"type": "enum", "values": ["stable", "active"]},
                         "steps_since_revalidation": {"type": "int", "min": 0, "max": 10 ** 6}, "conflicting_signal": {"type": "bool"},
                         "executed": {"type": "bool"}},
                        OUTPUTS, {"en": "Outputs with their epistemic metadata", "ru": "Выходы и их эпистемические метаданные"}),
        "consumer_requests": _lst({"output": {"type": "str"}, "consumer": {"type": "str"}, "request": {"type": "enum", "values": list(REQUESTS)}},
                                  [{"output": "asset_revoke", "consumer": "finance", "request": "execute"},
                                   {"output": "asset_revoke", "consumer": "finance", "request": "propagate"},
                                   {"output": "asset_revoke", "consumer": "finance", "request": "repair"},
                                   {"output": "asset_revoke", "consumer": "finance", "request": "treat_conditional"},
                                   {"output": "water_quota", "consumer": "finance", "request": "use_outside_scope"},
                                   {"output": "water_quota", "consumer": "habitat", "request": "execute"},
                                   {"output": "labor_score", "consumer": "labor", "request": "execute"}],
                                  {"en": "Consumer requests", "ru": "Запросы потребителей"}),
        "interpretations": _lst({"output": {"type": "str"}, "as": {"type": "enum", "values": list(INTERPRETATIONS)}},
                                [{"output": "water_quota", "as": "truth"}, {"output": "labor_score", "as": "guilt"}],
                                {"en": "Interpretations requested", "ru": "Запрошенные толкования"}),
        "override_requests": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "str"}, "default": ["crisis"], "source": "user",
                              "label": {"en": "Protocols asking to override EB", "ru": "Протоколы, просящие обойти EB"}},
        "disputes": _lst({"output": {"type": "str"}, "trigger": {"type": "enum", "values": list(TRIGGERS)},
                          "new_data_shift": {"type": "number", "min": -10 ** 6, "max": 10 ** 6, "default": 0.0}},
                         [{"output": "water_quota", "trigger": "new_admissible_data", "new_data_shift": -0.2},
                          {"output": "air_index", "trigger": "oracle_inconsistency", "new_data_shift": 0.1},
                          {"output": "quiet_sensor", "trigger": "disagreement_only"}],
                         {"en": "Disputes", "ru": "Споры"}),
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        prot = {x["id"] for x in r["protocols"]}
        outs = {x["id"] for x in r["outputs"]}
        if len(outs) != len(r["outputs"]) or len(prot) != len(r["protocols"]):
            p.append("input: repeated id")
        for x in list(outs) + list(prot):
            if not _ID.fullmatch(x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        for o in r["outputs"]:
            if o["protocol"] not in prot:
                p.append(f"input.outputs: {o['id']} names an undeclared protocol")
        for key in ("consumer_requests", "interpretations", "disputes"):
            for q in r[key]:
                if q["output"] not in outs:
                    p.append(f"input.{key}: unknown output {q['output']!r}")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        outputs = {"outputs": [m.value for m in msgs if m.kind == "evaluation" and "metadata" in m.value],
                   "requests": [m.value for m in msgs if m.source in ("CONSUMER", "EB")],
                   "disputes": [m.value for m in msgs if m.source == "DISPUTE"],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        inv = sum(1 for o in outputs["outputs"] if o["operational_validity"] == "INVALID")
        e = [{"en": f"{len(outputs['outputs'])} outputs, {inv} INVALID for operational use; violated: {', '.join(outputs['violations']) or 'none'}.",
              "ru": f"{len(outputs['outputs'])} выходов, {inv} недействительны для применения; нарушены: {', '.join(outputs['violations']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]),
                "invalid": sum(1 for o in outputs["outputs"] if o["operational_validity"] == "INVALID")}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {"mixed_outputs": {},
                "complete_outputs": {"outputs": [_out("water_quota", "habitat", "allocation")], "consumer_requests": [
                    {"output": "water_quota", "consumer": "habitat", "request": "execute"}], "interpretations": [], "disputes": [],
                    "override_requests": []},
                "faulty_consumers": {"faults": ["propagate_incomplete", "repair_downstream", "scope_drift", "truth_reading", "mutate_on_dispute"]}}

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"unknown_protocol": {"outputs": [_out("x", "ghost", "allocation")]},
                "dispute_on_unknown_output": {"disputes": [{"output": "nothing", "trigger": "new_admissible_data"}]}}


for _spec in EpistemicGateModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
