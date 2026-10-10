"""
PROPERTY RIGHTS module: granting, conditionality, concentration and critical assets (DKP-2-ASSETS-001 §3.2, §4, §5, §7, §9).

Subjects ask for Property Rights over assets.  ASSETS grants a right only under the §4 conditions
(a-d) and never on prior possession, inheritance without obligation transfer or a contract detached
from impact alone; every right is conditional (§3.2, §5): when a condition later fails, the right is
degraded.  Assets of the §9 categories are designated Non-Privatizable or Conditionally Privatizable
and held only under stewardship, always revocable.  Accumulations declared as increasing systemic
fragility, coercive dominance or cascading harm draw one of the §7 responses.

Revocation, reallocation, disputes and Justice-driven access are module economic_access.  What the
text leaves open is declared:
  * H-PR-1: §9 lists the categories without saying which are Non-Privatizable and which Conditionally
    Privatizable; the designation is an input per category;
  * H-PR-2: §7 thresholds are "derived from impact metrics" but not given; whether an accumulation
    triggers §7 is a declared flag (ASSETS-7-01 is reclassified l8_parameter);
  * the §4 conditions (non-negative net justice contribution, use within impact bounds, axiomatic
    priorities, mitigation capacity) are declared values of each request.
Time unit: DTI-Day.
"""

from __future__ import annotations

from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

CRITICAL = ("biosphere_critical", "water_air_ecology", "informational_commons")          # ASSETS §9
CATEGORIES = ("ordinary",) + CRITICAL
SOLE_BASES = ("prior_possession", "inheritance_without_obligations", "contract_only")     # ASSETS §4
BASES = ("conditions",) + SOLE_BASES
RESPONSES = ("graduated_restriction", "enforced_divestment", "reallocation")              # ASSETS §7
PERSISTENCE = ["justice contribution non-negative", "use within impact constraints", "restitution obligations satisfied"]   # §5

FAULTS = {
    "absolute_right": "a granted right is recorded as permanent and stays in force when its conditions fail",
    "grant_by_possession": "a right is granted on prior possession alone",
    "privatize_commons": "a §9 asset is granted as ordinary private property",
    "ignore_concentration": "an accumulation declared as increasing systemic fragility draws no §7 response",
}

REQUEST = {"type": "object", "fields": {
    "id": {"type": "str"},
    "subject": {"type": "str"},
    "asset": {"type": "str"},
    "category": {"type": "enum", "values": list(CATEGORIES), "default": "ordinary"},
    "basis": {"type": "enum", "values": list(BASES), "default": "conditions"},
    "justice_contribution": {"type": "number", "min": -1000, "max": 1000, "default": 1.0},
    "use_within_bounds": {"type": "bool", "default": True},
    "axioms_ok": {"type": "bool", "default": True},
    "mitigation_capacity": {"type": "bool", "default": True},
    "condition_fails_day": {"type": "int", "min": -1, "max": 3650, "default": -1}}}
HOLDING = {"type": "object", "fields": {
    "subject": {"type": "str"},
    "assets": {"type": "int", "min": 1, "max": 10 ** 6, "default": 1},
    "increases_fragility": {"type": "bool", "default": False},
    "response": {"type": "enum", "values": list(RESPONSES), "default": "graduated_restriction"}}}
REQUESTS_DEFAULT = [
    {"id": "q1", "subject": "coop_a", "asset": "workshop", "condition_fails_day": 6},
    {"id": "q2", "subject": "estate_b", "asset": "farmland", "basis": "prior_possession"},
    {"id": "q3", "subject": "heir_c", "asset": "warehouse", "basis": "inheritance_without_obligations"},
    {"id": "q4", "subject": "utility_d", "asset": "aquifer", "category": "water_air_ecology"},
    {"id": "q5", "subject": "firm_e", "asset": "quarry", "justice_contribution": -2.0},
]
HOLDINGS_DEFAULT = [{"subject": "grid_holder", "assets": 40, "increases_fragility": True, "response": "enforced_divestment"},
                    {"subject": "coop_a", "assets": 2}]


def conditions(q: Dict[str, Any]) -> Dict[str, bool]:
    return {"a_non_negative_justice": q["justice_contribution"] >= 0, "b_use_within_bounds": q["use_within_bounds"],
            "c_axioms": q["axioms_ok"], "d_mitigation_capacity": q["mitigation_capacity"]}


def run(r: Dict[str, Any]) -> EventLog:
    faults = set(r["faults"])
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:04d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  measured_at=k if kind == "observation" else None,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    rights = {}
    for q in r["requests"]:
        req = put("observation", "REQUEST", 0, dict(q))
        cond = conditions(q)
        ev = put("evaluation", "ASSETS", 0, {"request": q["id"], "conditions": cond, "basis": q["basis"]}, [req.event_id])
        sole = q["basis"] in SOLE_BASES and not ("grant_by_possession" in faults and q["basis"] == "prior_possession")
        if q["category"] in CRITICAL:
            designation = r["critical_designation"][q["category"]]
            put("notice", "ASSETS", 0, {"asset": q["asset"], "designation": designation, "category": q["category"]}, [req.event_id])
        if sole or not all(cond.values()):
            why = (f"basis '{q['basis']}' alone (§4)" if sole else "conditions " + ", ".join(c for c, ok in cond.items() if not ok))
            put("decision", "ASSETS", 0, {"request": q["id"], "granted": False, "reason": why}, [ev.event_id])
            continue
        if q["category"] in CRITICAL and r["critical_designation"][q["category"]] == "non_privatizable" \
                and "privatize_commons" not in faults:
            put("decision", "ASSETS", 0, {"request": q["id"], "granted": False, "reason": "Non-Privatizable asset (§9)"}, [ev.event_id])
            continue
        form = "ordinary" if q["category"] == "ordinary" or "privatize_commons" in faults else "stewardship"
        g = put("decision", "ASSETS", 0, {"request": q["id"], "granted": True, "subject": q["subject"], "asset": q["asset"],
                                          "form": form, "granted_by": "system rule (ASSETS §4 a-d)",
                                          "persistence_conditions": [] if "absolute_right" in faults else PERSISTENCE,
                                          "revocable": "absolute_right" not in faults,
                                          **({"permanent": True} if "absolute_right" in faults else {})}, [ev.event_id])
        rights[q["id"]] = g
    for k in range(1, r["horizon_days"]):
        for q in r["requests"]:
            if q["condition_fails_day"] == k and q["id"] in rights:
                f = put("observation", "JUSTICE", k, {"subject": q["subject"], "net_justice_contribution": -1.0})
                if "absolute_right" not in faults:
                    put("action", "ASSETS", k, {"right": rights[q["id"]].event_id, "status": "suspended",
                                                "reason": "a §5 condition failed"}, [f.event_id, rights[q["id"]].event_id])
    for hd in r["holdings"]:
        h = put("observation", "IMPACT", 0, {"holder": hd["subject"], "assets": hd["assets"],
                                             "increases_fragility": hd["increases_fragility"]})
        if hd["increases_fragility"] and "ignore_concentration" not in faults:
            put("action", "ASSETS", 0, {"holder": hd["subject"], "response": hd["response"],
                                        "basis": "impact-based concentration (§7; thresholds not given, H-PR-2)"}, [h.event_id])
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    req = {m.value["id"]: m.value for m in msgs if m.source == "REQUEST"}
    dec = {m.value["request"]: m for m in msgs if m.source == "ASSETS" and m.kind == "decision"}
    granted = {q: m for q, m in dec.items() if m.value["granted"]}
    bad = []
    for q, m in granted.items():
        g = m.value
        if g.get("permanent") or not g.get("revocable") or not g.get("persistence_conditions"):
            bad.append(f"{q}: right recorded as absolute or permanent")
        k = req[q]["condition_fails_day"]
        if 0 < k < r["horizon_days"] and not any(x.source == "ASSETS" and x.value.get("right") == m.event_id and x.arrived_at == k
                                                 for x in msgs):
            bad.append(f"{q}: right kept after a §5 condition failed on day {k}")
    out.append(v("ASSETS-3.2-01", "property_right_conditional", bad,
                 f"{len(granted)} right(s) granted by system rule, conditional, revocable and suspended when a condition failed",
                 "{n} rights that are absolute, permanent or not contingent") if granted else
               na("ASSETS-3.2-01", "property_right_conditional", "Property Rights", "no right granted"))
    sole = [q for q, x in req.items() if x["basis"] in SOLE_BASES]
    out.append(v("ASSETS-4-02", "no_grant_on_sole_basis", [f"{q}: granted on {req[q]['basis']}" for q in sole if q in granted],
                 f"{len(sole)} request(s) resting on prior possession, inheritance without obligations or a contract alone refused",
                 "{n} rights granted on an excluded basis") if sole else
               na("ASSETS-4-02", "no_grant_on_sole_basis", "excluded bases", "no request rests on an excluded basis"))
    crit = [q for q, x in req.items() if x["category"] in CRITICAL]
    des = {m.value["asset"]: m.value["designation"] for m in msgs if m.source == "ASSETS" and m.value.get("designation")}
    bad = [f"{q}: no designation" for q in crit if req[q]["asset"] not in des]
    bad += [f"{q}: granted as {granted[q].value['form']}" for q in crit if q in granted
            and (granted[q].value["form"] != "stewardship" or not granted[q].value.get("revocable"))]
    bad += [f"{q}: Non-Privatizable asset granted" for q in crit if q in granted and des.get(req[q]["asset"]) == "non_privatizable"]
    out.append(v("ASSETS-9-01", "critical_assets_designated", bad,
                 f"{len(crit)} §9 asset(s) designated ({', '.join(sorted(set(des.values()))) or '-'}; split by H-PR-1) and held only "
                 "under revocable stewardship", "{n} §9 assets privatized or not designated") if crit else
               na("ASSETS-9-01", "critical_assets_designated", "§9 assets", "no request concerns a §9 asset"))
    flagged = [m for m in msgs if m.source == "IMPACT" and m.value["increases_fragility"]]
    resp = {m.value["holder"] for m in msgs if m.source == "ASSETS" and m.value.get("response") in RESPONSES}
    out.append(v("ASSETS-7-01", "concentration_response", [m.value["holder"] for m in flagged if m.value["holder"] not in resp],
                 f"{len(flagged)} accumulation(s) declared as increasing systemic fragility drew a §7 response "
                 "(the threshold itself is not given: H-PR-2)", "{n} flagged accumulations without a §7 response") if flagged else
               na("ASSETS-7-01", "concentration_response", "concentration", "no accumulation declared as increasing fragility"))
    return out


IMPLEMENTS = {
    "ASSETS-3.2-01": ("property_right_conditional", "PARTIAL", "The §5 conditions are declared events."),
    "ASSETS-4-02": ("no_grant_on_sole_basis", "IMPLEMENTED", None),
    "ASSETS-7-01": ("concentration_response", "PARTIAL", "The trigger is a declared flag: thresholds are not given (H-PR-2; "
                    "reclassified l8_parameter)."),
    "ASSETS-9-01": ("critical_assets_designated", "PARTIAL", "Non-Privatizable vs Conditionally Privatizable per category is declared "
                    "(H-PR-1)."),
}


class PropertyRightsModule(LabModule):
    id = "property_rights"
    version = "1.0.0"
    title = {"en": "Property rights: granting, conditions, critical assets", "ru": "Права собственности: выдача, условия, критические активы"}
    summary = {"en": "Subjects ask for property rights. Are rights granted only under the ASSETS conditions, never on possession "
                     "alone, kept only while the conditions hold, and are water, air and commons held only in revocable stewardship?",
               "ru": "Субъекты просят права собственности. Выдаются ли права только при условиях ASSETS, а не по одному владению, "
                     "сохраняются ли лишь пока выполняются условия, держатся ли вода, воздух и общие блага только в отзывном управлении?"}
    protocols = ["DKP-2-ASSETS-001"]
    example_order = ["five_requests", "all_critical_non_privatizable", "faulty_property"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_property_rights_module.py"]
    hypotheses = [
        {"id": "H-PR-1", "source": "hypothesis", "text": {
            "en": "§9 lists the categories designated Non-Privatizable or Conditionally Privatizable without assigning them; "
                  "the designation is declared per category.",
            "ru": "§9 перечисляет категории, отнесённые к Non-Privatizable или Conditionally Privatizable, не распределяя их; "
                  "отнесение объявляется для каждой категории."}},
        {"id": "H-PR-2", "source": "missing", "text": {
            "en": "§7 concentration thresholds are 'derived from impact metrics' but not given; whether an accumulation triggers §7 "
                  "is a declared flag.",
            "ru": "Пороги концентрации §7 'выводятся из метрик воздействия', но не заданы; срабатывание §7 — объявленный признак."}},
    ]
    inputs = {
        "horizon_days": {"type": "int", "min": 1, "max": 3650, "default": 10, "unit": "DTI-Day", "source": "user",
                         "label": {"en": "DTI-Days", "ru": "DTI-дней"}},
        "requests": {"type": "list", "min_items": 0, "max_items": 30, "items": REQUEST, "default": REQUESTS_DEFAULT, "source": "user",
                     "label": {"en": "Requests for Property Rights (§4 conditions declared)", "ru": "Запросы прав собственности (условия §4 объявлены)"}},
        "holdings": {"type": "list", "min_items": 0, "max_items": 30, "items": HOLDING, "default": HOLDINGS_DEFAULT, "source": "user",
                     "label": {"en": "Accumulations (§7 trigger declared, H-PR-2)", "ru": "Накопления (срабатывание §7 объявлено, H-PR-2)"}},
        "critical_designation": {"type": "object", "source": "hypothesis",
                                 "fields": {c: {"type": "enum", "values": ["non_privatizable", "conditionally_privatizable"],
                                                "default": "conditionally_privatizable"} for c in CRITICAL},
                                 "default": {c: "conditionally_privatizable" for c in CRITICAL},
                                 "label": {"en": "Designation of §9 categories (H-PR-1)", "ru": "Отнесение категорий §9 (H-PR-1)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [q["id"] for q in r["requests"]]
        if len(set(ids)) != len(ids):
            p.append("input.requests: repeated id")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        granted = sorted(m.value["request"] for m in msgs if m.source == "ASSETS" and m.kind == "decision" and m.value["granted"])
        refused = sorted(m.value["request"] for m in msgs if m.source == "ASSETS" and m.kind == "decision" and not m.value["granted"])
        outputs = {"granted": granted, "refused": refused,
                   "messages": [m.as_dict() for m in msgs][:300],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        explain = [{"en": f"Granted: {', '.join(granted) or 'none'}; refused: {', '.join(refused) or 'none'}.",
                    "ru": f"Выдано: {', '.join(granted) or 'нет'}; отказано: {', '.join(refused) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"granted": len(outputs["granted"]), "refused": len(outputs["refused"])}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "five_requests": {},
            "all_critical_non_privatizable": {"critical_designation": {c: "non_privatizable" for c in CRITICAL}},
            "faulty_property": {"faults": ["absolute_right", "grant_by_possession", "privatize_commons", "ignore_concentration"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_request": {"requests": [{"id": "q", "subject": "s", "asset": "a"}] * 2},
                "unknown_basis": {"requests": [{"id": "q", "subject": "s", "asset": "a", "basis": "conquest"}]}}


for _q in REQUESTS_DEFAULT:
    _q.update(resolve(_q, REQUEST["fields"]))
for _h in HOLDINGS_DEFAULT:
    _h.update(resolve(_h, HOLDING["fields"]))
