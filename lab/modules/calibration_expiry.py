"""
CALIBRATION EXPIRY module — scenario S-LAB-05.

DKP-8-SIMULATION-001 (signed Calibration Bundle; non-enforceable without a valid one; expiry
invalidates dependent outputs: INVALID, "Calibration expired", "Awaiting recalibration"; no legacy
values; recalibration restores validity; no override of a failed simulation; recalibration
triggers) → DKP-5-HABITAT-001 (SPDI composite index, thresholds only from the bundle, activation
gate, no manual interpretation, remediation without forced displacement) →
DKP-4-EPISTEMIC-TRANSITIONS-001 (expiry as a downgrade: suspension, re-entry by new outputs).

No Calibration Bundle exists in the corpus.  The bundle here is a **hypothetical, declared**
input (source `calibration`), used only to exercise the rules about bundles; its numbers are not
proposals for SPDI.  A global halt must not follow from expiry alone (lab specification S-LAB-05).
SIMULATION §10 requires recalibration on environmental drift but does not say whether the old
bundle stays valid until then: two readings (H-CE-2).
"""

from __future__ import annotations

from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

COMPONENTS = ("living_space", "quiet", "light", "air")
FAULTS = {
    "enforce_after_expiry": "remediation is still triggered after the bundle expired",
    "legacy_threshold": "outputs after expiry still carry the expired SPDI model and threshold",
    "manual_interpretation": "remediation is triggered from raw values without a valid bundle",
    "unsigned_bundle_used": "an unsigned bundle is used for enforcement",
    "global_halt_on_expiry": "calibration expiry puts the whole system into the null-output state",
    "reactivate_old_outputs": "after recalibration, remediation reuses pre-expiry evaluations",
    "override_failed_simulation": "a bundle is issued although the recalibration simulation failed",
    "forced_displacement": "forced displacement is used as the default remedy",
}

BUNDLE = {"type": "object", "fields": {
    "issued_day": {"type": "int", "min": 0, "max": 10 ** 6, "default": 0},
    "validity_days": {"type": "int", "min": 1, "max": 10 ** 5, "default": 60},
    "signed": {"type": "bool", "default": True},
    "spdi_min": {"type": "number", "min": 0, "max": 1, "default": 0.5},
    "component_critical": {"type": "number", "min": 0, "max": 1, "default": 0.2},
    "weights": {"type": "list", "min_items": 4, "max_items": 4, "items": {"type": "number", "min": 0, "max": 1},
                "default": [0.25, 0.25, 0.25, 0.25]},
    "confidence_bound": {"type": "number", "min": 0, "max": 1, "default": 0.05},
    "audit_linked": {"type": "bool", "default": True},
}}


def components(r, h: int, day: int) -> List[float]:
    """PTL-measured components of habitat h (deterministic; some habitats degrade from a declared day)."""
    base = [round(0.45 + 0.5 * (((h + 1) * (j + 3) * 37) % 100) / 100, 4) for j in range(len(COMPONENTS))]
    if h < r["degraded_habitats"] and day >= r["degradation_day"]:
        base = [round(x * 0.4, 4) for x in base]
    return base


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    b = r["bundle"]
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=(), epistemic=None):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:05d}-{n['i']:06d}", kind=kind, source=source, arrived_at=k,
                                  measured_at=k if kind == "observation" else None,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  epistemic=epistemic, provenance=tuple(prov), order=order[kind]))

    bundles = []
    if b["signed"] or "unsigned_bundle_used" in faults:
        bundles.append({"id": "CB-1", "from": b["issued_day"], "to": b["issued_day"] + b["validity_days"], "signed": b["signed"],
                        "weights": b["weights"], "spdi_min": b["spdi_min"], "critical": b["component_critical"]})
    if r["recalibration_day"] >= 0 and (r["recalibration_passes"] or "override_failed_simulation" in faults):
        bundles.append({"id": "CB-2", "from": r["recalibration_day"], "to": r["recalibration_day"] + b["validity_days"],
                        "signed": True, "weights": b["weights"], "spdi_min": b["spdi_min"], "critical": b["component_critical"],
                        "simulation_passed": r["recalibration_passes"]})
    for cb in bundles:
        put("notice", "SIMULATION", cb["from"], {"bundle": cb["id"], "signed": cb["signed"], "thresholds": {"SPDI_min": cb["spdi_min"],
            "component_critical": cb["critical"]}, "model": {"weights": cb["weights"], "aggregation": "weighted sum"},
            "confidence_bound": b["confidence_bound"], "validity_window": [cb["from"], cb["to"]],
            "assumptions": "hypothetical bundle for the lab", "audit_linked": b["audit_linked"],
            "simulation_passed": cb.get("simulation_passed", True)})
    if r["recalibration_day"] >= 0 and not r["recalibration_passes"]:
        put("notice", "SIMULATION", r["recalibration_day"], {"simulation": "failed", "resolution": "redesign and re-simulation"})
    last_eval: Dict[int, str] = {}
    open_violation: Dict[int, bool] = {}
    expired_announced = set()
    fault_done = set()
    for k in range(r["horizon_days"]):
        active = next((cb for cb in bundles if cb["from"] <= k < cb["to"]), None)
        drift_hold = (r["drift_day"] >= 0 and k >= r["drift_day"] and r["drift_reading"] == "trigger_suspends"
                      and active is not None and active["from"] <= r["drift_day"])
        valid = active is not None and (active["signed"] or "unsigned_bundle_used" in faults) and not drift_hold
        expired = active is None and any(cb["to"] <= k for cb in bundles)
        for cb in bundles:
            if cb["to"] == k and cb["id"] not in expired_announced:
                expired_announced.add(cb["id"])
                if "global_halt_on_expiry" in faults:
                    put("notice", "CRISIS-PATCH", k, {"state": "NO_ENFORCEMENT", "reason": "calibration expired"})
        for h in range(r["habitats"]):
            comp = components(r, h, k)
            obs = put("observation", "PTL", k, {"habitat": h, "components": dict(zip(COMPONENTS, comp))})
            if valid:
                spdi = round(sum(w * c for w, c in zip(active["weights"], comp)), 6)
                admissible = spdi >= active["spdi_min"] and min(comp) >= active["critical"]
                value = {"habitat": h, "SPDI": spdi, "SPDI_min": active["spdi_min"], "admissible": admissible,
                         "bundle": active["id"]}
                md = {"validity_state": "VALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
                      "scope_ref": f"HABITAT/{active['id']}", "revalidation_required": False, "dispute_allowed": True}
            else:
                value = {"habitat": h, "components": dict(zip(COMPONENTS, comp)), "informational": True}
                if "legacy_threshold" in faults and expired:
                    old = bundles[0]
                    value.update(SPDI=round(sum(w * c for w, c in zip(old["weights"], comp)), 6), SPDI_min=old["spdi_min"])
                md = {"validity_state": "INVALID", "confidence_state": "SUFFICIENT_DATA", "consistency_state": "CONSISTENT",
                      "scope_ref": "HABITAT/uncalibrated", "revalidation_required": True, "dispute_allowed": True}
                if expired or drift_hold:
                    md.update(reason="Calibration expired" if expired else "Recalibration required (drift)",
                              remediation="Awaiting recalibration")
                else:
                    md.update(reason="No calibration bundle")
            ev = put("evaluation", "HABITAT", k, value, [obs.event_id], epistemic=md)
            violation = valid and b["audit_linked"] and not value["admissible"]
            old_spdi = sum(w * c for w, c in zip(b["weights"], comp))
            manual = ("manual_interpretation" in faults and not valid and not expired and sum(comp) / len(comp) < 0.5
                      and ("manual", h) not in fault_done)
            late = "enforce_after_expiry" in faults and expired and old_spdi < b["spdi_min"] and ("late", h) not in fault_done
            if manual or late:
                fault_done.add(("manual" if manual else "late", h))
                put("action", "HABITAT", k, {"habitat": h, "remedy": "remediation plan", "relocation_assistance": "offered"},
                    [ev.event_id])
            if violation and not open_violation.get(h):
                prov = [ev.event_id]
                if "reactivate_old_outputs" in faults and h in last_eval and valid and active["id"] == "CB-2":
                    prov = [last_eval[h]]
                remedy = "forced displacement" if "forced_displacement" in faults else "remediation plan"
                put("action", "HABITAT", k, {"habitat": h, "remedy": remedy, "relocation_assistance": "offered"}, prov)
                open_violation[h] = True
            if valid and value["admissible"]:
                open_violation[h] = False
            if not valid:
                open_violation[h] = False
            if valid:
                last_eval[h] = ev.event_id
    return log, bundles


def checks(r, log: EventLog, bundles) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    valid_days = set()
    for cb in bundles:
        if cb["signed"] and cb.get("simulation_passed", True):
            valid_days |= set(range(cb["from"], cb["to"]))
    if r["drift_day"] >= 0 and r["drift_reading"] == "trigger_suspends":
        first = next((cb for cb in bundles if cb["from"] <= r["drift_day"] < cb["to"]), None)
        if first:
            valid_days -= set(range(r["drift_day"], first["to"]))
    actions = [m for m in msgs if m.source == "HABITAT" and m.kind == "action"]
    evals = [m for m in msgs if m.source == "HABITAT" and m.kind == "evaluation"]
    out.append(v("SIMULATION-4-02", "no_enforcement_without_valid_bundle", [m.event_id for m in actions if m.arrived_at not in valid_days],
                 "every remediation happened under a valid, signed Calibration Bundle",
                 "{n} remediations without a valid bundle"))
    for rid, chk in (("HABITAT-6-01", "activation_gate"), ("HABITAT-6-02", "informational_without_bundle")):
        out.append(v(rid, chk, [m.event_id for m in actions if m.arrived_at not in valid_days],
                     "enforcement only through the activation gate; SPDI informational otherwise",
                     "{n} enforcement acts outside the activation gate"))
    nobundle = [m.event_id for m in actions if m.arrived_at not in valid_days and not any(cb["to"] <= m.arrived_at for cb in bundles)]
    out.append(v("HABITAT-6-03", "no_manual_interpretation", nobundle, "no remediation from manual reading of raw values",
                 "{n} remediations from manual interpretation"))
    used = [m for m in msgs if m.source == "SIMULATION" and m.value.get("bundle")]
    out.append(v("SIMULATION-9-01", "signed_complete_bundle",
                 [m.event_id for m in used if not m.value["signed"] or not all(m.value.get(x) for x in
                  ("thresholds", "model", "confidence_bound", "validity_window", "assumptions"))],
                 "every bundle is signed and carries thresholds, model, aggregation, confidence bounds, validity window and assumptions",
                 "{n} bundles unsigned or incomplete"))
    expiry_days = sorted(cb["to"] for cb in bundles)
    gaps = [k for k in range(r["horizon_days"]) if k not in valid_days and any(t <= k for t in expiry_days)]
    if gaps:
        gs = set(gaps)
        out.append(v("SIMULATION-10-02", "expiry_invalidates_enforcement", [m.event_id for m in actions if m.arrived_at in gs],
                     f"no enforcement in {len(gaps)} days after expiry", "{n} enforcement acts on an expired bundle"))
        bad = [m.event_id for m in evals if m.arrived_at in gs and not (m.epistemic["validity_state"] == "INVALID"
               and m.epistemic.get("reason") in ("Calibration expired", "Recalibration required (drift)")
               and m.epistemic.get("remediation") == "Awaiting recalibration")]
        out.append(v("SIMULATION-CalibrationExpirationEpistemicHandling-01", "expired_output_metadata", bad,
                     "every dependent output after expiry is INVALID with 'Calibration expired' and 'Awaiting recalibration'",
                     "{n} outputs after expiry without the required metadata"))
        bad = [m.event_id for m in evals if m.arrived_at in gs and ("SPDI_min" in m.value or "SPDI" in m.value)]
        out.append(v("SIMULATION-CalibrationExpirationEpistemicHandling-03", "no_legacy_values", bad,
                     "no expired model or threshold appears in outputs after expiry", "{n} outputs with legacy calibration values"))
        halts = [m.event_id for m in msgs if m.source == "CRISIS-PATCH"]
        out.append(v("CRISISPATCH-2-01", "no_global_halt_from_expiry", halts,
                     "calibration expiry alone did not put the system into the null-output state",
                     "{n} global null-output states triggered by calibration expiry"))
        first_gap = gaps[0]
        downs = [m for m in evals if m.arrived_at == first_gap]
        out.append(v("ETRANS-4.1-01", "expiry_downgrade_flags", [m.event_id for m in downs if not m.epistemic["revalidation_required"]],
                     "at expiry every dependent output requires revalidation", "{n} outputs without revalidation flag at expiry"))
    else:
        for rid, chk in (("SIMULATION-10-02", "expiry_invalidates_enforcement"),
                         ("SIMULATION-CalibrationExpirationEpistemicHandling-01", "expired_output_metadata"),
                         ("SIMULATION-CalibrationExpirationEpistemicHandling-03", "no_legacy_values"),
                         ("CRISISPATCH-2-01", "no_global_halt_from_expiry"), ("ETRANS-4.1-01", "expiry_downgrade_flags")):
            out.append(na(rid, chk, "calibration expiry", "no bundle expires within the horizon"))
    recal = [cb for cb in bundles if cb["id"] == "CB-2"]
    if r["recalibration_day"] >= 0:
        if r["recalibration_passes"]:
            after = [m for m in evals if m.arrived_at >= r["recalibration_day"] and m.arrived_at in valid_days]
            out.append(v("SIMULATION-CalibrationExpirationEpistemicHandling-02", "recalibration_restores",
                         [] if after and all(m.epistemic["validity_state"] == "VALID" for m in after) else ["not restored"],
                         "successful recalibration restored VALID outputs", "validity not restored after recalibration"))
            old = {m.event_id for m in evals if m.arrived_at < r["recalibration_day"]}
            reused = [m.event_id for m in actions if m.arrived_at >= r["recalibration_day"] and old & set(m.provenance)]
            out.append(v("ETRANS-4.4-02", "no_reactivation_after_recalibration", reused,
                         "remediation after recalibration rests on new evaluations", "{n} remediations reuse pre-expiry evaluations"))
            out.append(na("SIMULATION-12-01", "no_override_of_failed_simulation", "failed simulation", "the recalibration passed"))
        else:
            out.append(v("SIMULATION-12-01", "no_override_of_failed_simulation", [cb["id"] for cb in recal],
                         "the failed recalibration produced no bundle (redesign and re-simulation only)",
                         "a bundle was issued despite the failed simulation"))
            out.append(na("SIMULATION-CalibrationExpirationEpistemicHandling-02", "recalibration_restores", "recalibration",
                          "the recalibration simulation failed"))
            out.append(na("ETRANS-4.4-02", "no_reactivation_after_recalibration", "re-entry", "no successful recalibration"))
    else:
        for rid, chk in (("SIMULATION-CalibrationExpirationEpistemicHandling-02", "recalibration_restores"),
                         ("ETRANS-4.4-02", "no_reactivation_after_recalibration"),
                         ("SIMULATION-12-01", "no_override_of_failed_simulation")):
            out.append(na(rid, chk, "recalibration", "no recalibration in this experiment"))
    if r["drift_day"] >= 0:
        recal_after = r["recalibration_day"] >= r["drift_day"] and r["recalibration_passes"]
        if not recal_after:
            out.append(CheckResult("SIMULATION-10-01", "drift_requires_recalibration", FAIL,
                                   "environmental drift occurred and no successful recalibration followed"))
        else:
            kept = [m.event_id for m in actions if r["drift_day"] <= m.arrived_at < r["recalibration_day"]]
            out.append(CheckResult("SIMULATION-10-01", "drift_requires_recalibration", UNKNOWN if r["drift_reading"] == "valid_until_expiry" else PASS,
                                   f"recalibration followed the drift (day {r['recalibration_day']}); under '{r['drift_reading']}' the "
                                   f"pre-drift bundle {'kept' if r['drift_reading'] == 'valid_until_expiry' else 'did not keep'} enforcing "
                                   f"({len(kept)} remediations meanwhile). Whether a trigger suspends the bundle is not stated (Q-034)",
                                   evidence={"remediations_between": len(kept)}))
    else:
        out.append(na("SIMULATION-10-01", "drift_requires_recalibration", "recalibration triggers", "no drift declared"))
    spdis = [m.value["SPDI"] for m in evals if "SPDI" in m.value]
    out.append(v("HABITAT-4-01", "spdi_range", [x for x in spdis if not 0 <= x <= 1], "every SPDI lies in [0, 1]", "{n} SPDI values outside [0, 1]"))
    calibrated = [m for m in evals if "admissible" in m.value]
    bad = [m.event_id for m in calibrated if m.value["admissible"] != (m.value["SPDI"] >= m.value["SPDI_min"]
           and min(log.get(m.provenance[0]).value["components"].values()) >= r["bundle"]["component_critical"])]
    for rid, chk in (("HABITAT-5-01", "spdi_threshold"), ("HABITAT-5-02", "component_thresholds")):
        out.append(v(rid, chk, bad, "admissibility = SPDI ≥ SPDI_min and every component ≥ its critical threshold",
                     "{n} admissibility decisions inconsistent with the thresholds"))
    violations = [m for m in calibrated if not m.value["admissible"]]
    if violations:
        handled = {log.get(p).value["habitat"] for a in actions for p in a.provenance}
        missing = sorted({m.value["habitat"] for m in violations if r["bundle"]["audit_linked"]} - handled)
        out.append(v("HABITAT-10-01", "remediation_initiated", missing, "a remediation plan was initiated for every confirmed violation",
                     "{n} confirmed violations without remediation"))
    else:
        out.append(na("HABITAT-10-01", "remediation_initiated", "remediation", "no confirmed violation"))
    if actions:
        out.append(v("HABITAT-10-04", "no_forced_displacement", [m.event_id for m in actions if m.value["remedy"] == "forced displacement"],
                     "no forced displacement used as a remedy", "{n} forced displacements"))
    else:
        out.append(na("HABITAT-10-04", "no_forced_displacement", "remedies", "no remediation"))
    return out


IMPLEMENTS = {
    "SIMULATION-4-02": ("no_enforcement_without_valid_bundle", "IMPLEMENTED", None),
    "SIMULATION-9-01": ("signed_complete_bundle", "PARTIAL", "The bundle is hypothetical (none exists); its signature is a flag."),
    "SIMULATION-10-01": ("drift_requires_recalibration", "PARTIAL", "Whether a trigger suspends the bundle before expiry is not stated (Q-034)."),
    "SIMULATION-10-02": ("expiry_invalidates_enforcement", "IMPLEMENTED", None),
    "SIMULATION-CalibrationExpirationEpistemicHandling-01": ("expired_output_metadata", "IMPLEMENTED", None),
    "SIMULATION-CalibrationExpirationEpistemicHandling-02": ("recalibration_restores", "IMPLEMENTED", None),
    "SIMULATION-CalibrationExpirationEpistemicHandling-03": ("no_legacy_values", "IMPLEMENTED", None),
    "SIMULATION-12-01": ("no_override_of_failed_simulation", "PARTIAL", "Override is modelled as issuing a bundle after a failed simulation."),
    "HABITAT-4-01": ("spdi_range", "PARTIAL", "SPDI by the hypothetical bundle's weighted sum; the corpus defines no SPDI model."),
    "HABITAT-5-01": ("spdi_threshold", "PARTIAL", "SPDI_min from the hypothetical bundle."),
    "HABITAT-5-02": ("component_thresholds", "PARTIAL", "Component thresholds from the hypothetical bundle."),
    "HABITAT-6-01": ("activation_gate", "IMPLEMENTED", None),
    "HABITAT-6-02": ("informational_without_bundle", "IMPLEMENTED", None),
    "HABITAT-6-03": ("no_manual_interpretation", "IMPLEMENTED", None),
    "HABITAT-10-01": ("remediation_initiated", "PARTIAL", "Remediation plans are events; their content is not modelled."),
    "HABITAT-10-04": ("no_forced_displacement", "IMPLEMENTED", None),
    "CRISISPATCH-2-01": ("no_global_halt_from_expiry", "PARTIAL", "Checks only that expiry alone does not trigger the null-output state."),
    "ETRANS-4.1-01": ("expiry_downgrade_flags", "IMPLEMENTED", None),
    "ETRANS-4.4-02": ("no_reactivation_after_recalibration", "IMPLEMENTED", None),
}


class CalibrationExpiryModule(LabModule):
    id = "calibration_expiry"
    version = "1.0.0"
    title = {"en": "Calibration expiry (S-LAB-05)", "ru": "Истечение калибровки (S-LAB-05)"}
    summary = {"en": "A Calibration Bundle runs out: do habitat outputs turn INVALID, does enforcement stop without a "
                     "global halt, and does recalibration restore validity with new outputs?",
               "ru": "Пакет калибровки истекает: становятся ли выходы по жилью недействительными, останавливается ли "
                     "принуждение без глобальной остановки, восстанавливает ли перекалибровка действие новыми выходами?"}
    protocols = ["DKP-8-SIMULATION-001", "DKP-5-HABITAT-001", "DKP-4-EPISTEMIC-TRANSITIONS-001"]
    example_order = ["expiry_and_recalibration", "faulty_expiry", "failed_recalibration", "drift_kept_until_expiry",
                     "drift_suspends", "never_calibrated"]
    alternative_examples = ["drift_suspends"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_calibration_expiry_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-CE-1", "source": "calibration", "text": {
            "en": "The Calibration Bundle is hypothetical: no bundle exists in the corpus. Its SPDI weights and thresholds only exercise the rules.",
            "ru": "Пакет калибровки гипотетический: в корпусе его нет. Его веса SPDI и пороги нужны только для проверки правил."}},
        {"id": "H-CE-2", "source": "alternative", "text": {
            "en": "After a recalibration trigger (drift): 'valid_until_expiry' — the bundle stays valid until its window ends; "
                  "'trigger_suspends' — enforcement waits for recalibration (Q-034).",
            "ru": "После триггера перекалибровки (дрейф): 'valid_until_expiry' — пакет действует до конца окна; "
                  "'trigger_suspends' — принуждение ждёт перекалибровки (Q-034)."}},
        {"id": "H-CE-3", "source": "hypothesis", "text": {
            "en": "Without a valid bundle, outputs show raw PTL components only (no SPDI): the SPDI model is a calibration value.",
            "ru": "Без действующего пакета выходы показывают только исходные компоненты PTL (без SPDI): модель SPDI — калибровочная величина."}},
    ]
    inputs = {
        "horizon_days": {"type": "int", "min": 2, "max": 5000, "default": 120, "unit": "DTI-Day", "source": "user",
                         "label": {"en": "Days", "ru": "Дней"}},
        "habitats": {"type": "int", "min": 1, "max": 200, "default": 12, "source": "user",
                     "label": {"en": "Habitats", "ru": "Жилищ"}},
        "degraded_habitats": {"type": "int", "min": 0, "max": 200, "default": 3, "source": "user",
                              "label": {"en": "Habitats that degrade", "ru": "Жилищ, которые деградируют"}},
        "degradation_day": {"type": "int", "min": 0, "max": 10 ** 6, "default": 20, "unit": "DTI-Day", "source": "user",
                            "label": {"en": "Degradation from day", "ru": "Деградация с дня"}},
        "bundle": {**BUNDLE, "default": {"issued_day": 0, "validity_days": 60, "signed": True, "spdi_min": 0.5,
                                         "component_critical": 0.2, "weights": [0.25, 0.25, 0.25, 0.25],
                                         "confidence_bound": 0.05, "audit_linked": True},
                   "source": "calibration",
                   "label": {"en": "Hypothetical Calibration Bundle (none exists; H-CE-1)", "ru": "Гипотетический пакет калибровки (его нет; H-CE-1)"}},
        "recalibration_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": 75, "unit": "DTI-Day", "source": "user",
                              "label": {"en": "Recalibration on day (-1: none)", "ru": "Перекалибровка в день (-1: нет)"}},
        "recalibration_passes": {"type": "bool", "default": True, "source": "user",
                                 "label": {"en": "Recalibration simulation passes", "ru": "Симуляция перекалибровки успешна"}},
        "drift_day": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "unit": "DTI-Day", "source": "user",
                      "label": {"en": "Environmental drift on day (-1: none)", "ru": "Дрейф среды в день (-1: нет)"}},
        "drift_reading": {"type": "enum", "values": ["valid_until_expiry", "trigger_suspends"], "default": "valid_until_expiry",
                          "source": "alternative", "label": {"en": "Bundle after a trigger (H-CE-2)", "ru": "Пакет после триггера (H-CE-2)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        if abs(sum(r["bundle"]["weights"]) - 1) > 1e-9:
            p.append("input.bundle.weights: must sum to 1")
        if r["degraded_habitats"] > r["habitats"]:
            p.append("input.degraded_habitats: more than habitats")
        if r["habitats"] * r["horizon_days"] > 200000:
            p.append("input: at most 200000 habitat-days")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, bundles = run(r)
        res = checks(r, log, bundles)
        msgs = log.messages()
        evals = [m for m in msgs if m.source == "HABITAT" and m.kind == "evaluation"]
        by_day: Dict[int, Dict[str, int]] = {}
        for m in evals:
            d = by_day.setdefault(m.arrived_at, {"VALID": 0, "INVALID": 0})
            d[m.epistemic["validity_state"]] += 1
        remediations = [m for m in msgs if m.source == "HABITAT" and m.kind == "action"]
        outputs = {"bundles": [{k: v for k, v in cb.items() if k != "weights"} for cb in bundles],
                   "valid_output_days": sum(1 for d in by_day.values() if d["VALID"]),
                   "invalid_output_days": sum(1 for d in by_day.values() if not d["VALID"]),
                   "remediations": [{"day": m.arrived_at, **m.value} for m in remediations],
                   "global_halt": any(m.source == "CRISIS-PATCH" for m in msgs),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        explain = [{"en": f"Outputs VALID on {outputs['valid_output_days']} days, INVALID on {outputs['invalid_output_days']} "
                          f"days; {len(remediations)} remediation plans; global halt: {outputs['global_halt']}. "
                          "The bundle is hypothetical — none exists in the corpus.",
                    "ru": f"Выходы действительны {outputs['valid_output_days']} дн., недействительны {outputs['invalid_output_days']} дн.; "
                          f"планов исправления: {len(remediations)}; глобальная остановка: {outputs['global_halt']}. "
                          "Пакет гипотетический — в корпусе его нет."}]
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"valid_output_days": outputs["valid_output_days"], "invalid_output_days": outputs["invalid_output_days"],
                "remediations": len(outputs["remediations"]), "global_halt": outputs["global_halt"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "expiry_and_recalibration": {},
            "faulty_expiry": {"faults": ["enforce_after_expiry", "legacy_threshold", "global_halt_on_expiry", "forced_displacement"]},
            "failed_recalibration": {"recalibration_passes": False},
            "drift_kept_until_expiry": {"drift_day": 30, "recalibration_day": 45},
            "drift_suspends": {"drift_day": 30, "recalibration_day": 45, "drift_reading": "trigger_suspends"},
            "never_calibrated": {"bundle": {"issued_day": 0, "validity_days": 60, "signed": False, "spdi_min": 0.5,
                                            "component_critical": 0.2, "weights": [0.25, 0.25, 0.25, 0.25],
                                            "confidence_bound": 0.05, "audit_linked": True}, "recalibration_day": -1},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"weights_not_normalised": {"bundle": {"weights": [0.5, 0.5, 0.5, 0.5]}},
                "too_many_degraded": {"degraded_habitats": 50}}
