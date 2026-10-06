"""
INTEROP FAILURE module — failure of an external interface (scenario S-LAB-10).

DKP-8-INTEROP-001 (translation only; external rulings, values, information and black-box inputs
never authoritative; graceful degradation without effect on internal execution, no rollback, no
Crisis or Mercy) → DKP-6-RESILIENCE-001 (mirrored outputs not altered §5.3; entry points keep PTL
metadata, otherwise local invalidation §5.7) → DKP-8-AUDIT-001 (epistemic metadata verification,
D2 reporting, observation only, determinism).

The internal execution is computed twice — with and without the external failure — and compared
message by message.  One pair of rules collides when the external system is an oracle mirror
feeding PTL (finding F-013): INTEROP §9 says interop failure SHALL NOT trigger Crisis; CRISIS §4
enters crisis on "verified loss or divergence of PTL outputs beyond correction tolerance".  The
tolerance itself is not defined (input marked `missing`).
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
    "audit_modifies": "audit injects a corrective action into live execution",
}


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
    entry_valid = True
    crisis = False
    total = r["internal_sources"] + r["mirror_sources"]
    for k in range(r["horizon_steps"]):
        down = failure and lo <= k < hi
        mirror_ok = r["mirror_sources"] if not down else 0
        ptl = put("observation", "PTL", k, {"internal_sources": r["internal_sources"], "mirror_sources": mirror_ok,
                                            "share": (r["internal_sources"] + mirror_ok) / total})
        loss = 1 - (r["internal_sources"] + mirror_ok) / total
        beyond = r["ptl_loss_tolerance"] >= 0 and loss > r["ptl_loss_tolerance"]
        if down:
            put("notice", "INTEROP", k, {"boundary": "degraded", "channels": ["legal", "finance", "info", "oracle_mirror"]}, [ptl.event_id])
            if "rollback_on_failure" in faults and k == lo:
                put("action", "INTEROP", k, {"rollback": "DKP state to hour 0"}, [ptl.event_id])
        if beyond and r["interop_crisis_reading"] == "ptl_rule" and not crisis:
            put("notice", "CRISIS", k, {"enter": "C3", "trigger": "loss of PTL outputs beyond tolerance", "cause": "oracle mirror"},
                [ptl.event_id])
            crisis = True
        if crisis and not beyond:
            put("notice", "CRISIS", k, {"exit": True}, [ptl.event_id])
            crisis = False
        # external events at the boundary
        ext: Dict[str, Message] = {}
        if failure and k == r["external_ruling_step"]:
            ext["ruling"] = put("observation", "EXTERNAL/LEGAL", k, {"ruling": "suspend subject X", "binding_claimed": True})
            put("notice", "INTEROP", k, {"boundary_event": "external ruling received", "internal_status": "not binding"},
                [ext["ruling"].event_id])
        if k == r["external_value_step"]:
            flag = "unflagged_external_value" not in faults
            ext["value"] = put("observation", "EXTERNAL/FINANCE", k, {"asset_bridge": 1000.0, "externally_sourced": flag,
                                                                       "justice_weighted": "not computed: no translation function"})
            put("notice", "INTEROP", k, {"boundary_event": "external value", "translation_rule": "flag + FINANCE constraints"},
                [ext["value"].event_id])
        if failure and k == r["blackbox_step"]:
            ext["blackbox"] = put("observation", "EXTERNAL/BLACKBOX", k, {"control": "proprietary recommendation"})
            put("notice", "INTEROP", k, {"boundary_event": "black-box input", "authoritative": False}, [ext["blackbox"].event_id])
        if failure and k == r["external_info_step"]:
            ext["info"] = put("observation", "EXTERNAL/INFO", k, {"claim": "institutional consensus", "class": "I1"})
            put("notice", "INTEROP", k, {"boundary_event": "external information", "class": "I1 (untrusted)"}, [ext["info"].event_id])
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
        crisis = [m.event_id for m in msgs if m.source == "CRISIS" and m.value.get("enter")]
        out.append(v("INTEROP-9-04", "no_crisis_from_interop", crisis, "no Crisis or Mercy triggered by the interop failure",
                     "crisis entered because a mirrored oracle failed (reading 'ptl_rule', F-013)"))
        lossy = [m for m in msgs if m.source == "PTL" and r["ptl_loss_tolerance"] >= 0 and 1 - m.value["share"] > r["ptl_loss_tolerance"]]
        if lossy:
            if crisis:
                out.append(CheckResult("CRISIS-4-01", "ptl_loss_triggers_crisis", PASS,
                                       f"PTL lost more than the declared tolerance in {len(lossy)} hours; crisis entered (CRISIS §4)"))
            else:
                out.append(CheckResult("CRISIS-4-01", "ptl_loss_triggers_crisis", FAIL,
                                       f"PTL lost more than the declared tolerance ({r['ptl_loss_tolerance']}) in {len(lossy)} hours "
                                       "because a mirrored oracle failed, and no crisis was entered (INTEROP §9 forbids it). "
                                       "Rule conflict between texts in force (F-013)",
                                       evidence={"tag": "rule_conflict", "hours": len(lossy)}))
        elif r["ptl_loss_tolerance"] < 0:
            out.append(CheckResult("CRISIS-4-01", "ptl_loss_triggers_crisis", UNKNOWN,
                                   "'correction tolerance' for PTL loss is not defined; whether the mirror failure is a crisis "
                                   "trigger cannot be decided (F-013)"))
        else:
            out.append(na("CRISIS-4-01", "ptl_loss_triggers_crisis", "PTL loss", "PTL loss stays within the declared tolerance"))
    else:
        for rid, chk in (("INTEROP-9-02", "internal_execution_unaffected"), ("INTEROP-9-03", "no_rollback"),
                         ("INTEROP-9-04", "no_crisis_from_interop"), ("CRISIS-4-01", "ptl_loss_triggers_crisis")):
            out.append(na(rid, chk, "external failure", "no external failure in this experiment"))

    def uses(src):
        ids = ext_ids(src)
        return [m.event_id for m in decisions if ids & set(m.provenance)]
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
    if ext_ids("EXTERNAL/INFO"):
        bad = uses("EXTERNAL/INFO")
        out.append(v("INTEROP-8-02", "no_external_validation_for_ptl", bad,
                     "external consensus did not replace PTL verification", "{n} decisions based on external consensus"))
        out.append(v("INTEROP-8-01", "external_info_as_i1", [m.event_id for m in msgs if m.source == "EXTERNAL/INFO" and m.value.get("class") != "I1"],
                     "external information ingested as I1 (untrusted)", "{n} external claims ingested above I1"))
    else:
        out.append(na("INTEROP-8-02", "no_external_validation_for_ptl", "external information", "no external information"))
        out.append(na("INTEROP-8-01", "external_info_as_i1", "external information", "no external information"))
    api = uses("EXTERNAL/API")
    for rid, chk in (("INTEROP-10-02", "no_external_decision_dependency"), ("INTEROP-10-03", "no_governance_by_api")):
        out.append(v(rid, chk, api, "no internal decision depends on an external decision system or API",
                     "{n} internal decisions depend on an external API"))
    boundary = [m for m in msgs if m.source == "INTEROP" and m.value.get("boundary_event")]
    out.append(v("INTEROP-11-03", "boundary_events_recorded",
                 [] if boundary or not (ext_ids("EXTERNAL/LEGAL") | ext_ids("EXTERNAL/FINANCE") | ext_ids("EXTERNAL/INFO")) else ["none"],
                 f"{len(boundary)} boundary events recorded for review", "external events without boundary records"))
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
    "INTEROP-6-02": ("justice_weighted_translation", "PARTIAL", "No translation function is given: UNKNOWN."),
    "INTEROP-6-04": ("external_values_flagged", "IMPLEMENTED", None),
    "INTEROP-7-04": ("blackbox_not_authoritative", "IMPLEMENTED", None),
    "INTEROP-8-01": ("external_info_as_i1", "PARTIAL", "I1 classification is recorded; INFO transitions are not modelled."),
    "INTEROP-8-02": ("no_external_validation_for_ptl", "IMPLEMENTED", None),
    "INTEROP-9-02": ("internal_execution_unaffected", "IMPLEMENTED", None),
    "INTEROP-9-03": ("no_rollback", "IMPLEMENTED", None),
    "INTEROP-9-04": ("no_crisis_from_interop", "PARTIAL", "Conflicts with CRISIS §4 when the external system is an oracle mirror (F-013)."),
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
    "CRISIS-4-01": ("ptl_loss_triggers_crisis", "PARTIAL", "'Correction tolerance' is not defined (declared input)."),
}


class InteropFailureModule(LabModule):
    id = "interop_failure"
    version = "1.0.0"
    title = {"en": "Failure of an external interface (S-LAB-10)", "ru": "Отказ внешнего интерфейса (S-LAB-10)"}
    summary = {"en": "An external court, market, data provider or API fails or pushes in: does the inside keep running "
                     "unchanged, with nothing external becoming binding?",
               "ru": "Внешний суд, рынок, поставщик данных или API отказывает или давит: продолжает ли внутренняя часть "
                     "работать без изменений, не становится ли внешнее обязательным?"}
    protocols = ["DKP-8-INTEROP-001", "DKP-6-RESILIENCE-001", "DKP-8-AUDIT-001", "DKP-4-CRISIS-001"]
    example_order = ["external_outage", "mirror_loss_beyond_tolerance", "mirror_loss_ptl_rule", "faulty_boundary", "tolerance_missing"]
    alternative_examples = ["mirror_loss_ptl_rule"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_interop_failure_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-IO-1", "source": "missing", "text": {
            "en": "'Correction tolerance' for PTL loss (CRISIS §4) is a declared share of lost sources; the corpus gives no value.",
            "ru": "'Допуск коррекции' потерь PTL (CRISIS §4) — объявленная доля потерянных источников; в корпусе значения нет."}},
        {"id": "H-IO-2", "source": "alternative", "text": {
            "en": "When a mirrored oracle fails: 'interop_rule' — no crisis (INTEROP §9); 'ptl_rule' — crisis on PTL loss beyond tolerance (CRISIS §4); F-013.",
            "ru": "При отказе зеркала оракула: 'interop_rule' — кризиса нет (INTEROP §9); 'ptl_rule' — кризис при потере PTL сверх допуска (CRISIS §4); F-013."}},
    ]
    inputs = {
        "horizon_steps": {"type": "int", "min": 2, "max": 2000, "default": 24, "unit": "h", "source": "user",
                          "label": {"en": "Hours", "ru": "Часов"}},
        "internal_sources": {"type": "int", "min": 1, "max": 1000, "default": 8, "source": "user",
                             "label": {"en": "Internal PTL sources", "ru": "Внутренние источники PTL"}},
        "mirror_sources": {"type": "int", "min": 0, "max": 1000, "default": 2, "source": "user",
                           "label": {"en": "Sources mirrored from an external oracle", "ru": "Источники из внешнего зеркала оракула"}},
        "ptl_loss_tolerance": {"type": "number", "min": -1, "max": 1, "default": 0.25, "source": "missing",
                               "label": {"en": "PTL loss tolerance (-1: not defined; H-IO-1)", "ru": "Допуск потерь PTL (-1: не определён; H-IO-1)"}},
        "interop_crisis_reading": {"type": "enum", "values": ["interop_rule", "ptl_rule"], "default": "interop_rule",
                                   "source": "alternative", "label": {"en": "Mirror failure (H-IO-2)", "ru": "Отказ зеркала (H-IO-2)"}},
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
        "human_validation_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 4, "unit": "h", "source": "user",
                                  "label": {"en": "Output mirrored for human validation at hour", "ru": "Выход отражён для проверки человеком в час"}},
        "stripping_entry_step": {"type": "int", "min": -1, "max": 10 ** 6, "default": 16, "unit": "h", "source": "user",
                                 "label": {"en": "Third-party entry point strips metadata from hour (-1: never)",
                                           "ru": "Сторонняя точка входа срезает метаданные с часа (-1: никогда)"}},
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
                   "crisis_entered": any(m.source == "CRISIS" and m.value.get("enter") for m in msgs),
                   "messages": [m.as_dict() for m in msgs if m.source != "AUDIT"][:300],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        explain = [{"en": f"{outputs['internal_decisions']} internal decisions with the external failure, "
                          f"{outputs['internal_decisions_without_failure']} without; {outputs['boundary_events']} boundary records; "
                          f"crisis entered: {outputs['crisis_entered']}.",
                    "ru": f"Внутренних решений при отказе: {outputs['internal_decisions']}, без отказа: "
                          f"{outputs['internal_decisions_without_failure']}; записей на границе: {outputs['boundary_events']}; "
                          f"кризис: {outputs['crisis_entered']}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"internal_decisions": outputs["internal_decisions"],
                "decisions_lost_to_failure": outputs["internal_decisions_without_failure"] - outputs["internal_decisions"],
                "crisis_entered": outputs["crisis_entered"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "external_outage": {},
            "mirror_loss_beyond_tolerance": {"mirror_sources": 4, "ptl_loss_tolerance": 0.25},
            "mirror_loss_ptl_rule": {"mirror_sources": 4, "ptl_loss_tolerance": 0.25, "interop_crisis_reading": "ptl_rule"},
            "faulty_boundary": {"faults": ["binding_external_ruling", "blackbox_authoritative", "info_substitutes_ptl",
                                           "alter_mirror", "audit_masks"]},
            "tolerance_missing": {"ptl_loss_tolerance": -1},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"fractional_window": {"external_failure_window": [1.5, 3]}, "unknown_fault": {"faults": ["obey"]}}
