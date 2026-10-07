"""
TRANSPORT CAPACITY module — scenario S-LAB-09.

DKP-5-TRANSPORT-001 and its Appendix A (PPDI components, standing only as an exception, regular
standing = structurally under-provisioned → capacity expansion, interior layout, RED as
externality compensation redirected to high-PPDI infrastructure, no bans or punishment, no Justice
outcomes) → DKP-1-IMPACT-001 (no aggregation across channels) and DKP-0-ORACLE-001.

Queues, seats and external effects are computed separately, as the lab specification asks.  What
the texts leave open is declared:
  * H-TR-1 passenger behaviour: the share choosing a private car grows with waiting and standing —
    an explicit model; TRANSPORT §8 *claims* comfort lowers private demand, the model *assumes* it,
    so the claim cannot be tested here (UNKNOWN);
  * PPDI has components but no formula and no minimum: no composite index is computed;
  * "regular" standing has no threshold; RED has no coefficient (its economic side depends on
    DKP-2-ECONOMIC-001, which is not in the corpus);
  * TRANSPORT §7.1 has the Physical Truth Layer quantify harm that includes "systemic insurance
    exposure", an economic quantity; ORACLE §1: "The PTL produces physical state only" (finding
    F-015, confirmed).  Alternative: insurance exposure quantified outside PTL (H-TR-4);
  * RED is "computed via DKP-0-ORACLE-001 and DKP-1-IMPACT-001" (§7.2); where its channels are
    combined is not said.  If IMPACT combined them, IMPACT §5/§10 would forbid it; nothing says it
    does, so the lab reports UNKNOWN, not a conflict (H-TR-3).
"""

from __future__ import annotations

from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

RED_CHANNELS = ("mortality_risk", "medical_load", "infrastructure_degradation", "insurance_exposure")
# an economic exposure, not a physical state: ORACLE §1 "The PTL produces physical state only" / "does not ... assign value"
NON_PHYSICAL = ("insurance_exposure",)
FAULTS = {
    "standing_as_standard": "regular standing is not classified as under-provisioning",
    "passenger_adaptation": "under-provisioning is answered by asking passengers to adapt",
    "red_as_tax": "RED goes to the general budget as a levy",
    "justice_from_red": "high RED triggers a Justice outcome for drivers",
    "ban_private": "private cars are banned on the corridor",
    "moral_weighting": "RED modulation uses a reputation score",
    "undeclared_proxy": "RED is emitted without its proxy model, uncertainty and non-subjectivity statement",
}
DEFAULT_DEMAND = [40] * 6 + [300, 650, 500, 250] + [150] * 6 + [420, 650, 450, 200] + [80] * 4


def simulate(r: Dict[str, Any]):
    """Hour-by-hour deterministic queue over r['days'] days; behaviour updated once per day (H-TR-1)."""
    faults = set(r["faults"])
    seats = r["seats_per_vehicle"] + (r["seats_per_vehicle"] // 5 if r["interior"] == "bench" else 0)
    p_private = r["private_base_share"]
    days = []
    hours = []
    for d in range(r["days"]):
        q = 0.0
        seated = standing = waits = 0.0
        stand_hours = 0
        overload_hours = 0
        for h in range(24):
            k = d * 24 + h
            demand = r["demand"][h] * (0 if "ban_private" in faults else 1)
            arrivals = (r["demand"][h] if "ban_private" in faults else demand * (1 - p_private))
            vehicles = r["vehicles_per_hour"][h]
            cap_seat = vehicles * seats
            emergency = k in set(r["emergency_hours"])
            allow_stand = r["policy"] == "standing_allowed" or emergency
            q += arrivals
            overload = q > cap_seat
            overload_hours += overload
            s = min(q, cap_seat)
            q -= s
            st = min(q, vehicles * r["standing_per_vehicle"]) if allow_stand else 0.0
            q -= st
            seated += s
            standing += st
            stand_hours += st > 0
            density = st / max(1, vehicles) / r["vehicle_floor_m2"]
            waits += q / max(1.0, cap_seat + (vehicles * r["standing_per_vehicle"] if allow_stand else 0))
            hours.append({"hour": k, "arrivals": round(arrivals, 3), "seated": round(s, 3), "standing": round(st, 3),
                          "queue_end": round(q, 3), "emergency": emergency, "overload": overload,
                          "standing_density_m2": round(density, 4)})
        seated_share = seated / max(1e-9, seated + standing)
        mean_wait = waits / 24
        private_trips = sum(r["demand"]) * p_private if "ban_private" not in faults else 0.0
        days.append({"day": d, "private_share": round(p_private, 6), "seated_share": round(seated_share, 6),
                     "standing_hours": stand_hours, "overload_hours": overload_hours,
                     "mean_wait_h": round(mean_wait, 6), "private_km": round(private_trips * r["private_trip_km"], 3)})
        # H-TR-1: next day's private share from today's waiting and standing
        p_private = min(1.0, max(0.0, r["private_base_share"] + r["k_wait"] * mean_wait + r["k_stand"] * (1 - seated_share)))
    return days, hours, seats


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    days, hours, seats = simulate(r)
    log = EventLog("hour", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:05d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  measured_at=k if kind == "observation" else None,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    for d in days:
        k = d["day"] * 24 + 23
        ppdi = put("evaluation", "TRANSPORT/PPDI", k, {
            "day": d["day"], "seated_trip_share": d["seated_share"],
            "seat_width_mm": r["seat_width_mm"] - (50 if r["interior"] == "bench" else 0),
            "forced_contact": any(x["standing_density_m2"] > r["contact_density_m2"] and not x["emergency"]
                                  for x in hours if x["hour"] // 24 == d["day"]),
            "vibration_noise_ok": r["vibration_noise_ok"], "thermal_ok": r["thermal_ok"],
            "max_crowd_density_m2": max(x["standing_density_m2"] for x in hours if x["hour"] // 24 == d["day"]),
            "composite": "not computed: no PPDI formula or minimum in the corpus", "published": True})
        regular = d["standing_hours"] / 24 > r["regular_standing_share"] if r["regular_standing_share"] >= 0 else None
        if regular and "standing_as_standard" not in faults:
            c = put("notice", "TRANSPORT", k, {"classification": "Structurally under-provisioned", "day": d["day"]}, [ppdi.event_id])
            remedy = "ask passengers to adapt" if "passenger_adaptation" in faults else "capacity expansion"
            put("action", "TRANSPORT", k, {"response": remedy}, [c.event_id])
        if r["red_per_km"] >= 0:
            per = {ch: d["private_km"] * r["red_per_km"] / len(RED_CHANNELS) for ch in RED_CHANNELS}
            ptl_channels = [ch for ch in RED_CHANNELS if r["red_insurance"] == "ptl_quantified" or ch not in NON_PHYSICAL]
            if r["red_reading"] == "single_delta":
                red = {"RED": round(sum(per[ch] for ch in ptl_channels), 6)}
            else:
                red = {ch: round(per[ch], 6) for ch in ptl_channels}
            weight = "reputation score" if "moral_weighting" in faults else "PTL-confirmed risk profile"
            proxy = {} if "undeclared_proxy" in faults else {
                "classification": "proxy-based measurement (ORACLE §5.2)",
                "proxy_model": "declared coefficient × private kilometres (H-TR-2)",
                "uncertainty": {k2: round(v2 * r["red_uncertainty"], 6) for k2, v2 in red.items()},
                "not_a_subjective_state": True}
            rm = put("evaluation", "TRANSPORT/RED", k, {"day": d["day"], **red, "modulation": weight, **proxy,
                                                        "quantified_by": "PTL (TRANSPORT §7.1)", "channels": ptl_channels,
                                                        "unit": "model unit (no coefficient in the corpus)"}, [ppdi.event_id])
            cost = sum(v for v in red.values())
            prov = [rm.event_id]
            if len(ptl_channels) < len(RED_CHANNELS):
                outside = {ch: round(per[ch], 6) for ch in RED_CHANNELS if ch not in ptl_channels}
                ins = put("evaluation", "L2/RED-INSURANCE", k, {"day": d["day"], **outside,
                                                                "quantified_by": "outside PTL (no protocol named in the corpus)"},
                          [ppdi.event_id])
                cost += sum(outside.values())
                prov.append(ins.event_id)
            dest = "general budget levy" if "red_as_tax" in faults else "high-PPDI transport infrastructure fund"
            put("action", "LEDGER", k, {"externality_cost": round(cost, 6), "destination": dest}, prov)
            if "justice_from_red" in faults:
                put("decision", "JUSTICE", k, {"outcome": "restriction", "basis": "high RED"}, [rm.event_id])
        if "ban_private" in faults and d["day"] == 0:
            put("action", "TRANSPORT", 0, {"ban": "private vehicles on the corridor"})
    return log, days, hours, seats


def checks(r, log: EventLog, days, hours) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    ppdi = [m for m in msgs if m.source == "TRANSPORT/PPDI"]
    out.append(CheckResult("TRANSPORT-4-01", "ppdi_published", UNKNOWN,
                           f"PPDI components published for {len(ppdi)} days; the composite PPDI cannot be computed: the "
                           "corpus gives no formula"))
    need = ("seated_trip_share", "seat_width_mm", "forced_contact", "vibration_noise_ok", "thermal_ok", "max_crowd_density_m2")
    out.append(v("TRANSPORT-4.1-01", "ppdi_components", [m.event_id for m in ppdi if not all(x in m.value for x in need)],
                 "every listed PPDI component is reported from measurable quantities", "{n} days with missing components"))
    out.append(v("TRANSPORT-4.1-02", "no_forced_contact", [m.value["day"] for m in ppdi if m.value["forced_contact"]],
                 f"standing density stayed at or below {r['contact_density_m2']} persons/m² outside emergencies (a physical "
                 "stand-in: 'non-consenting' cannot be measured by PTL, ORACLE §5.3; F-016)",
                 "{n} days with forced bodily contact (standing density above the declared contact threshold)"))
    out.append(CheckResult("TRANSPORT-4.2-01", "degrading_mode_classification", UNKNOWN,
                           "the minimum PPDI threshold is not given; classification as Physically Degrading cannot be decided"))
    stand = [x for x in hours if x["standing"] > 0]
    out.append(v("TRANSPORT-5-02", "standing_only_exceptional", [x["hour"] for x in stand if not (x["emergency"] or x["overload"])],
                 f"all {len(stand)} standing hours were emergencies or overloads", "{n} standing hours outside the listed exceptions"))
    if r["regular_standing_share"] < 0:
        out.append(CheckResult("TRANSPORT-5-03", "regular_standing_classified", UNKNOWN,
                               "'regularly' has no threshold; whether standing is regular cannot be decided"))
        out.append(na("TRANSPORT-5-04", "capacity_expansion", "response to under-provisioning", "no classification possible"))
    else:
        regular_days = [d["day"] for d in days if d["standing_hours"] / 24 > r["regular_standing_share"]]
        classified = {m.value["day"] for m in msgs if m.value and m.value.get("classification") == "Structurally under-provisioned"}
        out.append(v("TRANSPORT-5-03", "regular_standing_classified", [d for d in regular_days if d not in classified],
                     f"{len(regular_days)} days of regular standing, each classified as structurally under-provisioned"
                     if regular_days else "standing was never regular", "{n} days of regular standing not classified"))
        responses = [m for m in msgs if m.source == "TRANSPORT" and m.kind == "action" and "response" in m.value]
        if classified:
            out.append(v("TRANSPORT-5-04", "capacity_expansion", [m.event_id for m in responses if m.value["response"] != "capacity expansion"]
                         + ([] if responses else ["no response"]),
                         "under-provisioning answered by capacity expansion, not passenger adaptation",
                         "{n} responses asking passengers to adapt"))
        else:
            out.append(na("TRANSPORT-5-04", "capacity_expansion", "response to under-provisioning", "no under-provisioning"))
    out.append(v("TRANSPORT-6-01", "individual_seating", ["bench"] if r["interior"] == "bench" and r["core_route"] else [],
                 f"interior: {r['interior']} seating", "continuous bench seating on a core route"))
    reds = [m for m in msgs if m.source == "TRANSPORT/RED"]
    if r["red_per_km"] < 0:
        for rid, chk in (("TRANSPORT-7.1-01", "red_quantified"), ("TRANSPORT-7.2-01", "red_redirected")):
            out.append(CheckResult(rid, chk, UNKNOWN, "RED has no coefficient in the corpus, and its economic treatment depends on "
                                   "DKP-2-ECONOMIC-001, which is not in the corpus (Q-014)"))
        out.append(na("TRANSPORT-7.2-02", "red_not_a_tax", "use of RED", "RED not computed"))
        out.append(na("TRANSPORT-7.3-03", "no_moral_weighting", "RED modulation", "RED not computed"))
        out.append(na("IMPACT-10-02", "no_aggregated_score", "aggregation of RED", "RED not computed"))
        out.append(na("ORACLE-1-02", "ptl_physical_state_only", "RED quantified by PTL", "RED not computed"))
    else:
        out.append(CheckResult("TRANSPORT-7.1-01", "red_quantified", PASS if reds else FAIL,
                               f"RED quantified per day ({r['red_reading']}), in model units with a declared coefficient"))
        ledger = [m for m in msgs if m.source == "LEDGER"]
        bad = [m.event_id for m in ledger if m.value["destination"] != "high-PPDI transport infrastructure fund"]
        out.append(v("TRANSPORT-7.2-01", "red_redirected", bad, "RED recorded as externality cost and redirected to high-PPDI infrastructure",
                     "{n} RED entries sent elsewhere"))
        out.append(v("TRANSPORT-7.2-02", "red_not_a_tax", bad, "RED treated as damage compensation, not as a tax",
                     "{n} RED entries treated as a levy"))
        out.append(v("TRANSPORT-7.3-03", "no_moral_weighting", [m.event_id for m in reds if m.value["modulation"] != "PTL-confirmed risk profile"],
                     "RED modulation uses PTL-confirmed risk profiles only", "{n} RED modulations with reputation weighting"))
        if r["red_reading"] == "single_delta":
            out.append(CheckResult("IMPACT-10-02", "no_aggregated_score", UNKNOWN,
                                   "RED is one delta 'computed via DKP-0-ORACLE-001 and DKP-1-IMPACT-001' (TRANSPORT §7.2); "
                                   "the corpus does not say whether IMPACT itself combines the channels (then §5/§10 would "
                                   "forbid it) or only supplies channel outputs (F-015, interpretation gap)"))
        else:
            out.append(CheckResult("IMPACT-10-02", "no_aggregated_score", PASS,
                                   "RED kept channel-separated (reading 'channel_separated'); no aggregate impact score"))
        bad = [m.event_id for m in reds if set(m.value["channels"]) & set(NON_PHYSICAL)]
        out.append(CheckResult(
            "ORACLE-1-02", "ptl_physical_state_only", FAIL if bad else PASS,
            ("TRANSPORT §7.1 has the Physical Truth Layer quantify harm including 'systemic insurance exposure', an "
             "economic quantity; ORACLE §1: 'The PTL produces physical state only'. Rule conflict between texts in "
             f"force (F-015); {len(bad)} RED outputs") if bad else
            "RED quantified by PTL covers physical channels only; insurance exposure is quantified outside PTL (H-TR-4)",
            evidence={"tag": "rule_conflict", "violations": bad[:10]} if bad else {}))
    if reds:
        bad = [m.event_id for m in reds if not (m.value.get("proxy_model") and m.value.get("uncertainty") is not None
                                                 and m.value.get("not_a_subjective_state") is True)]
        out.append(v("ORACLE-5.2-02", "red_proxy_declared", bad,
                     "every RED output declares its proxy model, propagated uncertainty and that it is not a subjective state",
                     "{n} RED outputs without proxy declarations"))
    else:
        out.append(na("ORACLE-5.2-02", "red_proxy_declared", "RED as a proxy measurement", "RED not computed"))
    excluded = ("intent", "dignity", "belief", "responsibility", "consent", "moral", "cultural", "social_harm")
    bad = [m.event_id for m in msgs if m.source.startswith("PTL") and any(x in " ".join(map(str, m.value)) for x in excluded)]
    out.append(v("ORACLE-5.3-01", "no_excluded_domain_outputs", bad,
                 "no PTL output concerns intent, dignity, belief, responsibility, consent or moral/social harm; PPDI is "
                 "composed in L5 from physical components (consent is not measured: F-016)",
                 "{n} PTL outputs concerning excluded domains"))
    bans = [m.event_id for m in msgs if m.value and m.value.get("ban")]
    out.append(v("TRANSPORT-8-01", "no_bans_or_punishment", bans, "no ban, moral pressure or punitive enforcement used",
                 "{n} bans on private transport"))
    out.append(CheckResult("TRANSPORT-8-02", "comfort_driven_shift", UNKNOWN,
                           "the claim that comfort lowers private demand is assumed by the declared behaviour model H-TR-1, "
                           "so this experiment cannot test it; it needs observed data"))
    just = [m.event_id for m in msgs if m.source == "JUSTICE"]
    for rid, chk in (("TRANSPORTA-A.1-01", "no_justice_trigger"), ("TRANSPORTA-A.1-02", "degradation_signal_only"),
                     ("TRANSPORT-11-02", "no_justice_outcomes")):
        out.append(v(rid, chk, just, "low PPDI and high RED produced no Justice outcome", "{n} Justice outcomes from transport metrics"))
    return out


IMPLEMENTS = {
    "TRANSPORT-4-01": ("ppdi_published", "PARTIAL", "Components published; the composite has no formula: UNKNOWN."),
    "TRANSPORT-4.1-01": ("ppdi_components", "PARTIAL", "Vibration, noise and thermal comfort are declared inputs."),
    "TRANSPORT-4.1-02": ("no_forced_contact", "PARTIAL", "Forced contact = standing density above a declared threshold."),
    "TRANSPORT-4.2-01": ("degrading_mode_classification", "PARTIAL", "No PPDI minimum in the corpus: UNKNOWN."),
    "TRANSPORT-5-02": ("standing_only_exceptional", "IMPLEMENTED", None),
    "TRANSPORT-5-03": ("regular_standing_classified", "PARTIAL", "'Regularly' is a declared share of service hours."),
    "TRANSPORT-5-04": ("capacity_expansion", "IMPLEMENTED", None),
    "TRANSPORT-6-01": ("individual_seating", "PARTIAL", "Interior layout is a declared input."),
    "TRANSPORT-7.1-01": ("red_quantified", "PARTIAL", "RED coefficient declared; ECONOMIC-001 missing."),
    "TRANSPORT-7.2-01": ("red_redirected", "IMPLEMENTED", None),
    "TRANSPORT-7.2-02": ("red_not_a_tax", "IMPLEMENTED", None),
    "TRANSPORT-7.3-03": ("no_moral_weighting", "IMPLEMENTED", None),
    "TRANSPORT-8-01": ("no_bans_or_punishment", "IMPLEMENTED", None),
    "TRANSPORT-8-02": ("comfort_driven_shift", "PARTIAL", "An empirical claim the behaviour model assumes: UNKNOWN."),
    "TRANSPORT-11-02": ("no_justice_outcomes", "IMPLEMENTED", None),
    "TRANSPORTA-A.1-01": ("no_justice_trigger", "IMPLEMENTED", None),
    "TRANSPORTA-A.1-02": ("degradation_signal_only", "IMPLEMENTED", None),
    "IMPACT-10-02": ("no_aggregated_score", "PARTIAL", "Where RED combines its channels is not defined: UNKNOWN for a single delta (F-015)."),
    "ORACLE-1-02": ("ptl_physical_state_only", "PARTIAL", "Checked on RED only: PTL asked to quantify an economic exposure (F-015)."),
    "ORACLE-5.2-02": ("red_proxy_declared", "IMPLEMENTED", None),
    "ORACLE-5.3-01": ("no_excluded_domain_outputs", "PARTIAL", "Checked on the module's own PTL messages; the PPDI consent component cannot be measured (F-016)."),
}


class TransportCapacityModule(LabModule):
    id = "transport_capacity"
    version = "1.1.0"
    title = {"en": "Transport capacity (S-LAB-09)", "ru": "Транспортная вместимость (S-LAB-09)"}
    summary = {"en": "A corridor at rush hour: queues, seats and external harm side by side — is standing an exception, "
                     "is under-provisioning met by more capacity, and does RED fund better transport without punishing anyone?",
               "ru": "Коридор в час пик: очереди, места и внешний вред рядом — исключение ли стоя, отвечают ли на нехватку "
                     "новой вместимостью, идёт ли RED на лучший транспорт без наказаний?"}
    protocols = ["DKP-5-TRANSPORT-001", "DKP-5-TRANSPORT-001-APPENDIX-A", "DKP-1-IMPACT-001", "DKP-0-ORACLE-001"]
    example_order = ["seated_only", "standing_allowed", "thin_service", "more_vehicles", "red_single_delta",
                     "red_channel_separated", "red_insurance_outside_ptl", "faulty_transport", "bench_interior"]
    alternative_examples = ["red_channel_separated", "red_insurance_outside_ptl"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_transport_capacity_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-TR-1", "source": "hypothesis", "text": {
            "en": "Behaviour: next day's private-car share = base + k_wait × mean wait (h) + k_stand × standing share.",
            "ru": "Поведение: доля личных авто на следующий день = база + k_wait × среднее ожидание (ч) + k_stand × доля стоящих."}},
        {"id": "H-TR-2", "source": "missing", "text": {
            "en": "'Regular' standing = standing in more than the declared share of hours of a day; forced contact = standing "
                  "density above the declared persons per m²; RED coefficient per private km. None is in the corpus.",
            "ru": "'Регулярно' стоя = стоя дольше объявленной доли часов суток; вынужденный контакт = плотность стоящих выше "
                  "объявленной на м²; коэффициент RED на км. В корпусе их нет."}},
        {"id": "H-TR-3", "source": "alternative", "text": {
            "en": "RED form: 'single_delta' (TRANSPORT §7.1: one delta) or 'channel_separated'. Where the channels are combined "
                  "is not defined ('computed via' ORACLE and IMPACT, §7.2); IMPACT-10-02 is UNKNOWN for a single delta (F-015).",
            "ru": "Форма RED: 'single_delta' (TRANSPORT §7.1: одна дельта) или 'channel_separated'. Где каналы объединяются, "
                  "не определено ('computed via' ORACLE и IMPACT, §7.2); для одной дельты IMPACT-10-02 = UNKNOWN (F-015)."}},
        {"id": "H-TR-4", "source": "alternative", "text": {
            "en": "Insurance exposure: 'ptl_quantified' — PTL quantifies it with the other channels (TRANSPORT §7.1, against "
                  "ORACLE §1: F-015); 'outside_ptl' — quantified outside PTL by a protocol the corpus does not name.",
            "ru": "Страховая нагрузка: 'ptl_quantified' — PTL оценивает её вместе с другими каналами (TRANSPORT §7.1, вопреки "
                  "ORACLE §1: F-015); 'outside_ptl' — оценивается вне PTL протоколом, которого корпус не называет."}},
    ]
    inputs = {
        "days": {"type": "int", "min": 1, "max": 365, "default": 5, "unit": "day", "source": "user", "label": {"en": "Days", "ru": "Дней"}},
        "demand": {"type": "list", "min_items": 24, "max_items": 24, "items": {"type": "number", "min": 0, "max": 10 ** 6},
                   "default": DEFAULT_DEMAND, "unit": "passengers/h", "source": "user",
                   "label": {"en": "Travel demand per hour of day", "ru": "Спрос на поездки по часам"}},
        "vehicles_per_hour": {"type": "list", "min_items": 24, "max_items": 24, "items": {"type": "int", "min": 0, "max": 1000},
                              "default": [4] * 6 + [12] * 4 + [8] * 6 + [12] * 4 + [4] * 4, "source": "user",
                              "label": {"en": "Vehicles per hour", "ru": "Машин в час"}},
        "seats_per_vehicle": {"type": "int", "min": 1, "max": 500, "default": 40, "source": "user",
                              "label": {"en": "Seats per vehicle", "ru": "Мест на машину"}},
        "standing_per_vehicle": {"type": "int", "min": 0, "max": 500, "default": 40, "source": "user",
                                 "label": {"en": "Standing places per vehicle", "ru": "Мест стоя на машину"}},
        "vehicle_floor_m2": {"type": "number", "min": 1, "max": 1000, "default": 12, "unit": "m²", "source": "user",
                             "label": {"en": "Standing floor area per vehicle", "ru": "Площадь для стоящих"}},
        "interior": {"type": "enum", "values": ["individual_seats", "bench"], "default": "individual_seats", "source": "user",
                     "label": {"en": "Interior layout", "ru": "Планировка салона"}},
        "core_route": {"type": "bool", "default": True, "source": "user", "label": {"en": "Core route", "ru": "Основной маршрут"}},
        "seat_width_mm": {"type": "int", "min": 300, "max": 1000, "default": 480, "unit": "mm", "source": "user",
                          "label": {"en": "Individual seat width", "ru": "Ширина сиденья"}},
        "policy": {"type": "enum", "values": ["seated_only", "standing_allowed"], "default": "seated_only", "source": "user",
                   "label": {"en": "Operating policy", "ru": "Режим работы"}},
        "emergency_hours": {"type": "list", "min_items": 0, "max_items": 1000, "items": {"type": "int", "min": 0, "max": 10 ** 6},
                            "default": [], "unit": "h", "source": "user",
                            "label": {"en": "Emergency hours (standing permitted)", "ru": "Аварийные часы (стоя разрешено)"}},
        "regular_standing_share": {"type": "number", "min": -1, "max": 1, "default": 0.1, "source": "missing",
                                   "label": {"en": "'Regular' standing: share of hours (-1: undefined; H-TR-2)",
                                             "ru": "'Регулярно' стоя: доля часов (-1: не определено; H-TR-2)"}},
        "contact_density_m2": {"type": "number", "min": 0, "max": 20, "default": 2.5, "unit": "persons/m²", "source": "missing",
                               "label": {"en": "Forced-contact density (H-TR-2)", "ru": "Плотность вынужденного контакта (H-TR-2)"}},
        "vibration_noise_ok": {"type": "bool", "default": True, "source": "user",
                               "label": {"en": "Vibration and noise within limits", "ru": "Вибрация и шум в пределах"}},
        "thermal_ok": {"type": "bool", "default": True, "source": "user", "label": {"en": "Thermal comfort within range", "ru": "Температура в пределах"}},
        "private_base_share": {"type": "number", "min": 0, "max": 1, "default": 0.2, "source": "hypothesis",
                               "label": {"en": "Base private-car share (H-TR-1)", "ru": "Базовая доля личных авто (H-TR-1)"}},
        "k_wait": {"type": "number", "min": 0, "max": 10, "default": 0.3, "source": "hypothesis",
                   "label": {"en": "Sensitivity to waiting (H-TR-1)", "ru": "Чувствительность к ожиданию (H-TR-1)"}},
        "k_stand": {"type": "number", "min": 0, "max": 10, "default": 0.4, "source": "hypothesis",
                    "label": {"en": "Sensitivity to standing (H-TR-1)", "ru": "Чувствительность к стоянию (H-TR-1)"}},
        "private_trip_km": {"type": "number", "min": 0, "max": 1000, "default": 10, "unit": "km", "source": "user",
                            "label": {"en": "Private trip length", "ru": "Длина поездки на авто"}},
        "red_per_km": {"type": "number", "min": -1, "max": 10 ** 6, "default": -1, "source": "missing",
                       "label": {"en": "RED per private km (-1: undefined; H-TR-2)", "ru": "RED на км (-1: не определено; H-TR-2)"}},
        "red_uncertainty": {"type": "number", "min": 0, "max": 10, "default": 0.25, "source": "hypothesis",
                            "label": {"en": "Relative uncertainty of RED", "ru": "Относительная неопределённость RED"}},
        "red_reading": {"type": "enum", "values": ["single_delta", "channel_separated"], "default": "single_delta",
                        "source": "alternative", "label": {"en": "RED form (H-TR-3)", "ru": "Форма RED (H-TR-3)"}},
        "red_insurance": {"type": "enum", "values": ["ptl_quantified", "outside_ptl"], "default": "ptl_quantified",
                          "source": "alternative", "label": {"en": "Insurance exposure quantified (H-TR-4)",
                                                             "ru": "Кто оценивает страховую нагрузку (H-TR-4)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        if len(set(r["faults"])) != len(r["faults"]):
            raise LabInputError(["input.faults: repeated fault"])
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log, days, hours, seats = run(r)
        res = checks(r, log, days, hours)
        reds = [m.value for m in log.messages() if m.source == "TRANSPORT/RED"]
        outputs = {"days": days, "hours": hours[:72], "seats_per_vehicle_effective": seats,
                   "queues": {"max_queue": max(x["queue_end"] for x in hours), "mean_wait_h_last_day": days[-1]["mean_wait_h"]},
                   "seats": {"seated_share_last_day": days[-1]["seated_share"], "standing_hours_total": sum(d["standing_hours"] for d in days)},
                   "external": {"private_km_total": round(sum(d["private_km"] for d in days), 3), "red": reds[-1] if reds else None},
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        last = days[-1]
        explain = [{"en": f"Last day: private share {last['private_share']:.1%}, seated {last['seated_share']:.1%}, "
                          f"{last['standing_hours']} standing hours, mean wait {last['mean_wait_h']:.2f} h "
                          f"(behaviour model H-TR-1 is declared, not measured).",
                    "ru": f"Последний день: доля авто {last['private_share']:.1%}, сидя {last['seated_share']:.1%}, "
                          f"часов со стоящими {last['standing_hours']}, среднее ожидание {last['mean_wait_h']:.2f} ч "
                          f"(модель поведения H-TR-1 объявлена, а не измерена)."}]
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        last = outputs["days"][-1]
        return {"private_share_last_day": last["private_share"], "seated_share_last_day": last["seated_share"],
                "standing_hours_total": outputs["seats"]["standing_hours_total"],
                "max_queue": outputs["queues"]["max_queue"], "private_km_total": outputs["external"]["private_km_total"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "seated_only": {},
            "standing_allowed": {"policy": "standing_allowed"},
            "thin_service": {"policy": "standing_allowed", "vehicles_per_hour": [4] * 6 + [9] * 4 + [5] * 6 + [9] * 4 + [3] * 4},
            "more_vehicles": {"vehicles_per_hour": [4] * 6 + [18] * 4 + [8] * 6 + [18] * 4 + [4] * 4},
            "red_single_delta": {"red_per_km": 0.02},
            "red_channel_separated": {"red_per_km": 0.02, "red_reading": "channel_separated"},
            "red_insurance_outside_ptl": {"red_per_km": 0.02, "red_insurance": "outside_ptl"},
            "faulty_transport": {"policy": "standing_allowed", "red_per_km": 0.02,
                                 "faults": ["passenger_adaptation", "red_as_tax", "justice_from_red", "ban_private"]},
            "bench_interior": {"interior": "bench", "core_route": False},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"short_demand": {"demand": [100] * 12}, "unknown_fault": {"faults": ["fine_drivers"]}}
