"""
CONTRIBUTION module — prevention and recognition of contribution (scenario S-LAB-01).

DKP-1-PREVENTION-001 bench (v2.1.1, unchanged; ORACLE freshness of TA/SE, EB metadata)
→ DKP-1-IDENTITY-001 (binding to identifiable Subjects) → DKP-2-LABOR-001 (Contribution
Records: immutable, time-indexed; recognition only of measured, attributable contribution).

The bench produces one record per (event, responder).  This module turns them into §6.3
messages — TA and SE observations (measured, then registered), the bench evaluation, and a
LABOR Contribution Record for each recognised contribution — and checks LABOR and IDENTITY
provisions on them.  Generator truth (who created a threat, true linkage) is never used to
recognise anything; it is only reported by the bench's own evaluation.

What the texts do not define is not invented:
  * LABOR §5.2 justice recovery function — records say "not computed";
  * LABOR §8.1 compensation — SPD stays PREVENTION's recognition score, never money;
  * proportionality of compensation to measured impact cannot be checked without it.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message, epistemic_problems
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.run import canonical_json, sha256_text
from lab.modules.prevention import PreventionModule
from lab.modules.time import canonical, dy_doy

MS = 1000                                   # bench times are seconds; the log uses integer milliseconds
FAULTS = {
    "recognize_unattributed": "NO_ATTRIBUTION records are recognised as contribution",
    "count_declared_claims": "declared claims without measured reduction are recognised",
    "reward_self_induced": "contribution is recognised for threats the actor created",
    "fictitious_subject": "a contribution is credited to another Subject than the actor",
    "mutate_record": "a Contribution Record is changed after creation",
    "strip_metadata": "Contribution Records are emitted without scope_ref",
    "ignore_inconsistency": "records made under oracle inconsistency are recognised",
    "accept_stale": "records whose TA or SE was stale or invalid are recognised",
    "wrong_time_index": "the DTI time index of a record is shifted by one day",
    "labor_feeds_ptl": "a PTL observation is derived from a Contribution Record (review КТ7-GPT-01 core of LABOR-2-01)",
}
NOT_MONEY = "SPD (PREVENTION recognition score); not money, not Capital Units"


def ms(seconds: float) -> int:
    return int(round(seconds * MS))


def recognised(rec: Dict[str, Any], faults=()) -> bool:
    """LABOR §3.1, §5.2: recognised only with measured reduction (POSITIVE, SPD > 0) and causal attribution."""
    if rec["status"] == "POSITIVE" and rec["SPD"] > 0:
        return True
    if "recognize_unattributed" in faults and rec["status"] == "NO_ATTRIBUTION":
        return True
    if "count_declared_claims" in faults and rec["status"] == "ZERO_MERIT" and rec["claim"] > 0 \
            and rec["reason"] == "intervention_outside_window":
        return True
    if "reward_self_induced" in faults and rec["reason"] == "self_induced_linkage":
        return True
    if "ignore_inconsistency" in faults and rec["status"] == "INFORMATIONAL":
        return True
    if "accept_stale" in faults and rec["status"] == "INVALID":
        return True
    return False


def build(r: Dict[str, Any], records: List[Dict[str, Any]]):
    faults = set(r["faults"])
    log = EventLog("millisecond", tie_rule="arrival; observation < evaluation < notice; then event_id")
    store: Dict[str, Dict[str, Any]] = {}
    subjects = sorted({rec["actor_id"] for rec in records})
    for k, rec in enumerate(records):
        prov = []
        for leg in ("ta", "se"):
            x = rec.get(leg)
            if not x or (x.get("time") is None and x.get("evaluated_at") is None):
                continue
            measured = None if x.get("time") is None else ms(x["time"])          # invalid TA/SE: nothing measured
            arrived = ms(x["registered_at"]) if x.get("registered_at") is not None else ms(x["evaluated_at"])
            m = log.append(Message(event_id=f"{leg}-{k:05d}", kind="observation", source=f"PTL/{leg.upper()}",
                                   measured_at=measured, arrived_at=arrived,
                                   value={"intensity": x["intensity"], "valid": x["valid"], "consistent": x["consistent"],
                                          "stale_classes": list(x.get("stale_classes") or [])},
                                   unit="intensity"))
            prov.append(m.event_id)
        decided = rec["decision_at"] if rec["decision_at"] is not None else rec["intervention_time"]
        at = max([ms(decided)] + [log.get(p).arrived_at for p in prov])
        ev = log.append(Message(event_id=f"prev-{k:05d}", kind="evaluation", source="PREVENTION", arrived_at=at,
                                value={"event": rec["event_id"], "actor": rec["actor_id"], "status": rec["status"],
                                       "reason": rec["reason"], "SPD": rec["SPD"], "claim": rec["claim"],
                                       "risk_channel": rec["risk_channel"]},
                                epistemic=rec["epistemic"], provenance=tuple(prov), order=1))
        if not recognised(rec, faults):
            continue
        subject = rec["actor_id"]
        if "fictitious_subject" in faults:
            subject = next((s for s in subjects if s != subject), subject)
        md = dict(rec["epistemic"])
        if "strip_metadata" in faults:
            md.pop("scope_ref", None)
        day = r["start_dti_day"] + int(decided // 86400) + (1 if "wrong_time_index" in faults else 0)
        cr = {"record_id": f"CR-{k:05d}", "subject": subject, "activity": f"prevention:{rec['risk_channel']}",
              "measured_impact": prov, "bench_record": ev.event_id,
              "justice_adjustment": "not computed: LABOR §5.2 gives no recovery function",
              "recognition": {"value": rec["SPD"], "unit": NOT_MONEY},
              "time_index": {"dti_day": day, "dy": canonical(*dy_doy(day)), "decision_at_s": decided},
              "epistemic": md}
        store[cr["record_id"]] = copy.deepcopy(cr)
        log.append(Message(event_id=cr["record_id"], kind="notice", source="LABOR", arrived_at=at, value=cr,
                           epistemic=md, provenance=tuple([ev.event_id] + prov), order=2))
    if "labor_feeds_ptl" in faults and store:
        first = log.get(sorted(store)[0])
        log.append(Message(event_id="ta-feedback", kind="observation", source="PTL/TA", measured_at=first.arrived_at,
                           arrived_at=first.arrived_at, value={"intensity": 0.0, "valid": True, "consistent": True, "stale_classes": []},
                           unit="intensity", provenance=(first.event_id,), order=3))
    if "mutate_record" in faults and store:
        first = sorted(store)[0]
        store[first]["recognition"]["value"] = round(store[first]["recognition"]["value"] * 2, 12)
    return log, store


def run_checks(r, records, log: EventLog, store) -> List[CheckResult]:
    out: List[CheckResult] = []
    msgs = log.messages()
    crs = [m for m in msgs if m.source == "LABOR"]
    bench = {m.event_id: m for m in msgs if m.source == "PREVENTION"}

    def verdict(rid, check, bad, ok, no, evidence=None):
        ev = dict(evidence or {})
        if bad:
            ev["violations"] = bad[:10]
        return CheckResult(rid, check, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=ev)

    def na(rid, check, what, why):
        return CheckResult(rid, check, NOT_APPLICABLE, what, applicability=why)

    if crs:
        bad = [m.event_id for m in crs if sha256_text(canonical_json(m.value)) != sha256_text(canonical_json(store[m.event_id]))
               or "dti_day" not in m.value["time_index"]]
        out.append(verdict("LABOR-3.3-01", "record_immutable_time_indexed", bad,
                           f"all {len(crs)} Contribution Records are time-indexed (DTI-Day) and unchanged since creation",
                           "{n} Contribution Records changed after creation or lack a time index"))
        bad = [m.event_id for m in crs if not (m.value["subject"] and m.value["activity"] and m.value["measured_impact"]
                                               and "justice_adjustment" in m.value)]
        out.append(verdict("LABOR-3.3-02", "record_links", bad,
                           "every record links a Subject, an activity, measured impact outputs and a justice adjustment "
                           "field (the adjustment itself is not computed: no function in §5.2)",
                           "{n} records miss a required link"))
        bad = [m.event_id for m in crs if bench[m.value["bench_record"]].value["status"] != "POSITIVE"
               or bench[m.value["bench_record"]].value["SPD"] <= 0]
        out.append(verdict("LABOR-3.1-01", "only_measured_attributed_contribution", bad,
                           "contribution is recognised only for measured, causally attributed reductions (POSITIVE)",
                           "{n} records recognise contribution without measured, attributed reduction"))
        declared = [m.event_id for m in crs if bench[m.value["bench_record"]].value["status"] == "ZERO_MERIT"]
        out.append(verdict("LABOR-5.2-02", "no_declarative_recognition", declared,
                           "declared claims without measured reduction are not recognised",
                           "{n} declarative claims recognised"))
        out.append(verdict("LABOR-3.2-02", "impact_only_evaluation", declared + [
            m.event_id for m in crs if bench[m.value["bench_record"]].value["status"] == "NO_ATTRIBUTION"],
            "recognition depends on measured impact only, not on declared claims",
            "{n} recognitions rest on something other than measured, attributed impact"))
        actors = {bench[m.value["bench_record"]].value["actor"] for m in crs}
        bad = [m.event_id for m in crs if m.value["subject"] != bench[m.value["bench_record"]].value["actor"]]
        out.append(verdict("LABOR-11-02", "no_proxy_or_fictitious_participation", bad,
                           "every record is credited to the actor whose measured intervention it records",
                           "{n} records credited to another Subject"))
        bad = [m.event_id for m in crs if m.value["subject"] not in {rec["actor_id"] for rec in records}
               or not all(log.get(p).kind == "observation" for p in m.value["measured_impact"])]
        out.append(verdict("LABOR-11-01", "identity_bound_traceable", bad,
                           f"records bind to {len(actors)} identifiable Subjects and trace to TA/SE observations",
                           "{n} records not bound to an identifiable Subject or not traceable to measurements"))
        bad = [m.event_id for m in crs if epistemic_problems(m.epistemic)]
        out.append(verdict("EB-5.x-01", "record_metadata", bad,
                           "every Contribution Record carries the full EB §5 metadata set",
                           "{n} Contribution Records lack EB §5 metadata"))
        ratios = sorted({round(bench[m.value["bench_record"]].value["SPD"] /
                               max(1e-12, log.get(m.value["measured_impact"][-1]).value["intensity"]), 6) for m in crs})
        named = ("capital_units", "asset_access", "restriction_relaxation", "rights_restoration")              # LABOR §8.1
        other = [f for f in r["compensation_forms"] if f not in named]
        out.append(CheckResult("LABOR-8.1-01", "compensation_forms", UNKNOWN if other else PASS,
                               f"compensation also takes forms §8.1 does not name ({', '.join(other)}); whether its list is exhaustive "
                               "is not said" if other else f"compensation takes only forms §8.1 names: {', '.join(r['compensation_forms']) or 'none'}",
                               evidence={"forms": list(r["compensation_forms"])}))
        out.append(CheckResult("LABOR-8.1-02", "compensation_proportional", UNKNOWN,
                               "LABOR §8.1 compensation is not defined; SPD (W·S·A·C·T) is PREVENTION's recognition "
                               "score and is not proportional to measured impact alone", evidence={"spd_per_se_intensity": ratios[:10]}))
        out.append(CheckResult("LABOR-5.2-01", "justice_recovery_function", UNKNOWN,
                               "justice recovery is 'a deterministic function' of impact, relevance and horizon; the "
                               "function is not given, so no recovery is computed"))
        positive = [k for k, m in bench.items() if m.value["status"] == "POSITIVE" and m.value["SPD"] > 0]
        missing = [k for k in positive if k not in {m.value["bench_record"] for m in crs}]
        out.append(verdict("LABOR-8.2-01", "nonmarket_prevention_recognised", missing,
                           f"all {len(positive)} measured preventive contributions are recognised as labor",
                           "{n} measured preventive contributions not recognised"))
    else:
        why = "no contribution was recognised in this experiment"
        for rid, chk in (("LABOR-3.3-01", "record_immutable_time_indexed"), ("LABOR-3.3-02", "record_links"),
                         ("LABOR-3.1-01", "only_measured_attributed_contribution"), ("LABOR-5.2-02", "no_declarative_recognition"),
                         ("LABOR-3.2-02", "impact_only_evaluation"), ("LABOR-11-02", "no_proxy_or_fictitious_participation"),
                         ("LABOR-11-01", "identity_bound_traceable"), ("EB-5.x-01", "record_metadata"),
                         ("LABOR-8.1-02", "compensation_proportional"), ("LABOR-5.2-01", "justice_recovery_function"),
                         ("LABOR-8.1-01", "compensation_forms"),
                         ("LABOR-8.2-01", "nonmarket_prevention_recognised")):
            out.append(na(rid, chk, "Contribution Records", why))
    # LABOR §2 clear part: data flow from PTL into LABOR, never the reverse
    labor = {m.event_id for m in crs}
    back = [m.event_id for m in msgs if m.source.startswith("PTL") and set(m.provenance) & labor]
    back += [m.event_id for m in crs if not any(log.get(p).source.startswith("PTL") for p in m.value["measured_impact"])]
    out.append(verdict("LABOR-2-01", "labor_downstream_of_ptl", back,
                       f"{len(crs)} Contribution Records derive from PTL observations; no PTL record derives from LABOR",
                       "{n} reversed or missing PTL data flows") if crs else
               na("LABOR-2-01", "labor_downstream_of_ptl", "data flow", "no Contribution Record"))
    incons = [k for k, m in bench.items() if m.value["status"] == "INFORMATIONAL"]
    if incons:
        bad = [m.event_id for m in crs if m.value["bench_record"] in incons]
        out.append(verdict("LABOR-2-02", "no_participation_rules_under_inconsistency", bad,
                           f"no contribution recognised from {len(incons)} records made under oracle inconsistency",
                           "{n} contributions recognised under oracle inconsistency"))
    else:
        out.append(na("LABOR-2-02", "no_participation_rules_under_inconsistency", "participation under PTL divergence",
                      "no oracle inconsistency in this experiment"))
    stale = [m for m in msgs if m.kind == "observation" and (m.value["stale_classes"] or not m.value["valid"])]
    if stale:
        invalid = {m.event_id for m in stale if not m.value["valid"]}
        excluded = sum(1 for m in stale if m.value["valid"])
        bad = [m.event_id for m in crs if invalid & set(m.value["measured_impact"])]
        out.append(verdict("ORACLE-9-02", "no_recognition_from_stale_data", bad,
                           f"no contribution rests on any of {len(invalid)} observations made invalid by stale data; "
                           f"{excluded} valid observations had stale classes excluded (weight zero)",
                           "{n} contributions rest on observations made invalid by stale data",
                           {"invalid_observations": len(invalid), "valid_with_stale_classes_excluded": excluded}))
    else:
        out.append(na("ORACLE-9-02", "no_recognition_from_stale_data", "stale observations",
                      "no TA or SE observation was stale or invalid in this experiment"))
    if crs:
        from lab.modules.time import YEAR
        bad = []
        for m in crs:
            ti = m.value["time_index"]
            expect_day = r["start_dti_day"] + int(ti["decision_at_s"] // 86400)
            dy, doy = expect_day // YEAR, expect_day % YEAR + 1                 # TIME §5.1, independent of dy_doy()
            if ti["dti_day"] != expect_day or ti["dy"] != f"DY{dy}-{doy:03d}":
                bad.append(m.event_id)
        out.append(verdict("TIME-5.2-01", "record_time_index", bad,
                           "every record's time index is the DTI-Day of its decision in canonical DYdddd-DOY form",
                           "{n} records have a wrong DTI time index"))
        na_ids = {k for k, b in bench.items() if b.value["status"] == "NO_ATTRIBUTION"}
        bad = [m.event_id for m in crs if m.value["bench_record"] in na_ids]
        out.append(verdict("IDENTITY-4.1-03", "no_imputed_attribution", bad,
                           "no NO_ATTRIBUTION record is turned into a credited contribution",
                           "{n} NO_ATTRIBUTION records credited to a Subject"))
    else:
        out.append(na("TIME-5.2-01", "record_time_index", "time index of records", "no Contribution Record"))
        out.append(na("IDENTITY-4.1-03", "no_imputed_attribution", "imputed attribution", "no Contribution Record"))
    selfi = [k for k, m in bench.items() if m.value["reason"] == "self_induced_linkage"]
    if selfi:
        bad = [m.event_id for m in crs if m.value["bench_record"] in selfi]
        out.append(verdict("PREV-9.1-01", "no_recognition_for_own_threat", bad,
                           f"none of {len(selfi)} self-induced threats gives its creator a Contribution Record",
                           "{n} Contribution Records for self-created threats"))
    else:
        out.append(na("PREV-9.1-01", "no_recognition_for_own_threat", "self-created threats",
                      "no self-induced threat in this experiment"))
    return out


IMPLEMENTS = {
    "LABOR-2-01": ("labor_downstream_of_ptl", "PARTIAL", "Clear part only: data flow from PTL into LABOR; the layer terms stay open."),
    "LABOR-2-02": ("no_participation_rules_under_inconsistency", "PARTIAL", "Oracle inconsistency of the bench stands for PTL divergence; systemic halt is not modelled."),
    "LABOR-3.1-01": ("only_measured_attributed_contribution", "PARTIAL", "Voluntariness and 'sustained' are not modelled."),
    "LABOR-3.2-02": ("impact_only_evaluation", "PARTIAL", "Invariance is checked against declared claims and attribution only."),
    "LABOR-3.3-01": ("record_immutable_time_indexed", "IMPLEMENTED", None),
    "LABOR-3.3-02": ("record_links", "PARTIAL", "The justice adjustment is a field marked 'not computed' (§5.2 gives no function)."),
    "LABOR-5.2-01": ("justice_recovery_function", "PARTIAL", "The recovery function is not given: UNKNOWN."),
    "LABOR-5.2-02": ("no_declarative_recognition", "IMPLEMENTED", None),
    "LABOR-8.1-01": ("compensation_forms", "PARTIAL", "The forms offered are declared; a form outside the list gives UNKNOWN."),
    "LABOR-8.1-02": ("compensation_proportional", "PARTIAL", "Compensation is not defined: UNKNOWN; SPD is not renamed money."),
    "LABOR-8.2-01": ("nonmarket_prevention_recognised", "PARTIAL", "Prevention is the only non-market contribution modelled."),
    "LABOR-11-01": ("identity_bound_traceable", "IMPLEMENTED", None),
    "LABOR-11-02": ("no_proxy_or_fictitious_participation", "IMPLEMENTED", None),
    "EB-5.x-01": ("record_metadata", "IMPLEMENTED", None),
    "PREV-9.1-01": ("no_recognition_for_own_threat", "PARTIAL", "Self-induced linkage as detected by the bench."),
    "ORACLE-9-02": ("no_recognition_from_stale_data", "PARTIAL", "Staleness as flagged by the bench's TTL rule (PREVENTION §3.6; open question Q-015)."),
    "TIME-5.2-01": ("record_time_index", "IMPLEMENTED", None),
    "IDENTITY-4.1-03": ("no_imputed_attribution", "PARTIAL", "Recognition, not enforcement, is checked here."),
}

_PREV = PreventionModule()


class ContributionModule(LabModule):
    id = "contribution"
    version = "1.1.0"
    title = {"en": "Prevention and recognition of contribution (S-LAB-01)",
             "ru": "Предотвращение и признание вклада (S-LAB-01)"}
    summary = {"en": "Who gets a Contribution Record for preventing harm? Only measured, attributable reductions; "
                     "no reward for one's own threats; recognition is not money.",
               "ru": "Кто получает запись о вкладе за предотвращение вреда? Только за измеренное и привязанное "
                     "снижение риска; без награды за собственные угрозы; признание — не деньги."}
    protocols = ["DKP-1-PREVENTION-001", "DKP-0-ORACLE-001", "DKP-0-TIME-001", "DKP-1-IDENTITY-001",
                 "DKP-2-LABOR-001", "DKP-1-EPISTEMIC-BOUNDARIES-001"]
    example_order = ["smoke", "with_adversary", "proportional_attribution", "stale_at_decision", "faulty_recognition"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_contribution_module.py"]
    causal_note = _PREV.causal_note
    hypotheses = list(_PREV.hypotheses) + [
        {"id": "H-CO-1", "source": "hypothesis", "text": {
            "en": "A Contribution Record is created for each POSITIVE bench record (measured, attributed reduction); its "
                  "justice adjustment and compensation are not computed because the texts give no function.",
            "ru": "Запись о вкладе создаётся для каждой записи стенда со статусом POSITIVE (измеренное и привязанное "
                  "снижение); поправка справедливости и компенсация не вычисляются: в текстах нет функции."}}]
    inputs = {**_PREV.inputs,
              "start_dti_day": {"type": "int", "min": 0, "max": 10 ** 8, "default": 2461042, "source": "user",
                                "label": {"en": "DTI-Day of the scenario start", "ru": "DTI-Day начала сценария"}},
              "compensation_forms": {"type": "list", "min_items": 0, "max_items": 6, "source": "user",
                                     "items": {"type": "enum", "values": ["capital_units", "asset_access", "restriction_relaxation",
                                                                         "rights_restoration", "status_title", "payment_by_hours"]},
                                     "default": ["capital_units", "rights_restoration"],
                                     "label": {"en": "Forms of compensation offered (LABOR §8.1)", "ru": "Формы компенсации (LABOR §8.1)"}},
              "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS),
                         "items": {"type": "enum", "values": list(FAULTS)}, "default": [], "source": "user",
                         "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                         "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                                  "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}}}

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        _PREV.validate({k: v for k, v in r.items() if k in _PREV.inputs})
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        prev_in = {k: v for k, v in r.items() if k in _PREV.inputs}
        _PREV.progress = self.progress
        bench = _PREV.evaluate(prev_in)
        _PREV.progress = None
        records = bench.records or []
        log, store = build(r, records)
        checks = run_checks(r, records, log, store)
        crs = [m.value for m in log.messages() if m.source == "LABOR"]
        by_subject: Dict[str, float] = {}
        for c in crs:
            by_subject[c["subject"]] = round(by_subject.get(c["subject"], 0.0) + c["recognition"]["value"], 12)
        outputs = {
            "bench_summary": bench.outputs["summary"],
            "contribution_records": crs,
            "recognition_by_subject": {"unit": NOT_MONEY, "values": by_subject},
            "not_recognised": {s: sum(1 for x in records if x["status"] == s) for s in
                               ("NO_ATTRIBUTION", "ZERO_MERIT", "INFORMATIONAL", "INVALID")},
            "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()},
        }
        n_self = sum(1 for x in records if x["reason"] == "self_induced_linkage")
        explain = [
            {"en": f"{len(records)} bench records; {len(crs)} Contribution Records (measured, attributed reductions). "
                   f"Not recognised: {outputs['not_recognised']}.",
             "ru": f"Записей стенда: {len(records)}; записей о вкладе: {len(crs)} (измеренное и привязанное снижение). "
                   f"Не признано: {outputs['not_recognised']}."},
            {"en": f"Recognition by Subject ({NOT_MONEY}): {by_subject or 'none'}.",
             "ru": f"Признание по субъектам (SPD — оценка PREVENTION, не деньги): {by_subject or 'нет'}."},
            {"en": "Justice adjustment (LABOR §5.2) and compensation (§8.1) are not computed: the texts give no function.",
             "ru": "Поправка справедливости (LABOR §5.2) и компенсация (§8.1) не вычисляются: в текстах нет функции."},
        ]
        if n_self:
            explain.append({"en": f"{n_self} records concern threats created by the responder; none gives a Contribution Record.",
                            "ru": f"Записей об угрозах, созданных самим участником: {n_self}; записей о вкладе по ним нет."})
        return ModuleResult(outputs=outputs, checks=checks, explain=explain, records=crs)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"contribution_records": len(outputs["contribution_records"]),
                "subjects_recognised": len(outputs["recognition_by_subject"]["values"]),
                "spd_recognised": round(sum(outputs["recognition_by_subject"]["values"].values()), 6),
                "no_attribution": outputs["not_recognised"]["NO_ATTRIBUTION"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "smoke": {},
            "with_adversary": {"base": "main", "num_days": 5, "include_adversarial": True},
            "proportional_attribution": {"attribution_rule": "proportional"},
            "stale_at_decision": {"num_days": 5, "arrival_delay_seconds": [0.1, 5.0], "ttl_reference": "decision"},
            "faulty_recognition": {"base": "main", "num_days": 5, "include_adversarial": True,
                                   "faults": ["recognize_unattributed", "reward_self_induced", "mutate_record"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"adversary_in_smoke": {"include_adversarial": True}, "unknown_fault": {"faults": ["pay_everyone"]}}
