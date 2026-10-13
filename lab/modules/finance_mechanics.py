"""
FINANCE MECHANICS module: cost of capital, credit, savings, reserves and leverage (DKP-2-FINANCE-001 §1, §3-§6, §9, §13).

A few Subjects with a Justice outcome class, a declared impact exposure and a market price volatility
ask for credit and hold savings for a number of DTI-Days.  FINANCE prices capital, decides credit
under the §5.1 conditions, repays it, pays savings returns, sizes the Systemic Reserve Pool and sets
leverage limits; requests for functions FINANCE excludes (§1, §13) are refused.

FINANCE gives no formula for any of these (JWCoC §3.2, interest §4.1, savings §6.1, reserves §6.2,
leverage §9): the module uses declared lab stand-ins (input ``stand_in``, source ``missing``; see
lab/CALIBRATION_MAP.md).  The checks never test the stand-in values.  They test only what the text
fixes for any formula: the direction of the cost of capital (§3.2), determinism and recomputability
(§6.1), the basis of reserves and leverage (impact, not a percentage or volatility: §6.2, §9), CU
without units or lots (§3.1), credit as a conditional, temporary imbalance (§5.1), and the exclusions
of §1 and §13.  The basis checks are metamorphic: the run is repeated with only the balance, or only
the volatility, changed.

Readings (H-FM-1..3) are listed below; the §5.1 conditions themselves are declared values here.
Time unit: DTI-Day.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

CLASSES = ("positive", "neutral", "negative")                      # H-FM-2: a Subject's Justice history, as a class
SIGN = {"positive": 1, "neutral": 0, "negative": -1}
REQUESTS = {                                                       # functions FINANCE excludes, and where
    "create_fiat_regime": ("FINANCE-1-01",), "manage_fiat_regime": ("FINANCE-1-01",),
    "override_justice_outcome": ("FINANCE-1-01", "FINANCE-13-01"), "subjective_valuation": ("FINANCE-1-01",),
    "preference_aggregation": ("FINANCE-1-01",), "override_identity_attribution": ("FINANCE-13-01",),
    "inject_policy": ("FINANCE-13-01",)}
RATE_FIELDS = {"subject", "justice", "exposure", "rate", "formula"}  # what a cost-of-capital record may carry

FAULTS = {
    "jwcoc_inverted": "a positive Justice contribution raises the cost of capital",
    "exposure_ignored": "impact exposure does not raise the cost of capital",
    "denominated_cu": "ledger entries carry a currency unit",
    "earmarked_cu": "CU from savings returns are booked at a different value than other CU",
    "credit_as_right": "credit is issued to a Subject that fails the §5.1 conditions, as an entitlement",
    "perpetual_credit": "credit is issued without a term and never closes",
    "discretionary_return": "a savings return includes an adjustment not derivable from its recorded inputs",
    "percentage_reserve": "the reserve is sized as a share of outstanding credit",
    "volatility_leverage": "leverage limits shrink with market price volatility",
    "finance_overreach": "FINANCE carries out a function §1 or §13 excludes when asked",
    "override_justice": "FINANCE re-grades a Subject's Justice outcome before pricing",
    "override_attribution": "a credit is booked to a Subject other than the one IDENTITY attributes it to",
    "inject_judgment": "a moral label is written into a cost-of-capital record",
}

SUBJECT = {"type": "object", "fields": {
    "id": {"type": "str"},
    "justice": {"type": "enum", "values": list(CLASSES), "default": "neutral", "source": "user"},
    "impact_exposure": {"type": "number", "min": 0, "max": 1000, "default": 2.0, "source": "user"},
    "volatility": {"type": "number", "min": 0, "max": 10, "default": 0.5, "source": "user"},
    "savings": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0.0, "source": "user"},
    "credit_request": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0.0, "source": "user"},
    "credit_term_days": {"type": "int", "min": 1, "max": 3650, "default": 30, "source": "user"},
    "projected_output": {"type": "number", "min": 0, "max": 10 ** 9, "default": 0.0, "source": "user"}}}
STAND_IN = {"type": "object", "fields": {
    "rate_base": {"type": "number", "min": 0, "max": 1, "default": 0.04},
    "rate_per_contribution": {"type": "number", "min": 0, "max": 1, "default": 0.02},
    "rate_per_exposure_unit": {"type": "number", "min": 0, "max": 1, "default": 0.005},
    "savings_rate_per_day": {"type": "number", "min": 0, "max": 0.01, "default": 0.0001},
    "reserve_per_impact_unit": {"type": "number", "min": 0, "max": 10 ** 6, "default": 100.0},
    "leverage_per_headroom": {"type": "number", "min": 0, "max": 10 ** 6, "default": 1000.0}}}
SUBJECTS_DEFAULT = [
    {"id": "A", "justice": "positive", "impact_exposure": 2.0, "volatility": 0.3, "savings": 1000.0, "credit_request": 500.0,
     "credit_term_days": 30, "projected_output": 800.0},
    {"id": "B", "justice": "neutral", "impact_exposure": 2.0, "volatility": 0.9, "savings": 500.0, "credit_request": 500.0,
     "credit_term_days": 30, "projected_output": 800.0},
    {"id": "C", "justice": "neutral", "impact_exposure": 6.0, "volatility": 0.3, "credit_request": 400.0,
     "credit_term_days": 20, "projected_output": 600.0},
    {"id": "D", "justice": "negative", "impact_exposure": 12.0, "volatility": 0.5, "credit_request": 300.0,
     "credit_term_days": 10, "projected_output": 500.0},
]


def rate_of(sp: Dict[str, Any], justice: str, exposure: float, faults) -> float:
    """Lab stand-in for JWCoC (FINANCE §3.2 gives no function)."""
    step = -sp["rate_per_contribution"] if "jwcoc_inverted" in faults else sp["rate_per_contribution"]
    per_exp = 0.0 if "exposure_ignored" in faults else sp["rate_per_exposure_unit"]
    return round(sp["rate_base"] - step * SIGN[justice] + per_exp * exposure, 10)


def reserve_of(sp: Dict[str, Any], exposure_total: float, outstanding: float, faults) -> float:
    """Lab stand-in for SRP sizing (§6.2: impact-based)."""
    if "percentage_reserve" in faults:
        return round(0.1 * outstanding, 6)
    return round(sp["reserve_per_impact_unit"] * exposure_total, 6)


def leverage_of(sp: Dict[str, Any], bound: float, exposure: float, volatility: float, faults) -> float:
    """Lab stand-in for the leverage limit (§9: impact-based): headroom to the axiomatic bound."""
    limit = max(0.0, bound - exposure) * sp["leverage_per_headroom"]
    if "volatility_leverage" in faults:
        limit = limit / (1.0 + volatility)
    return round(limit, 6)


def run(r: Dict[str, Any]) -> EventLog:
    faults = set(r["faults"])
    sp = r["stand_in"]
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower().replace('/', '-')}-{k:04d}-{n['i']:05d}", kind=kind, source=source,
                                  arrived_at=k, measured_at=k if kind == "observation" else None,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    def book(k, subject, cu, entry, prov, of=None):
        v = {"subject": subject, "cu": cu, "entry": entry, "operation_of": of or subject}
        if "denominated_cu" in faults:
            v["unit"] = "EUR"
        if "earmarked_cu" in faults and entry == "savings_return":
            v["value_factor"] = 0.9
        return put("action", "FINANCE/LEDGER", k, v, prov)

    credits: Dict[str, Dict[str, Any]] = {}
    balance: Dict[str, float] = {}
    aggregate = 0.0
    for s in r["subjects"]:
        sid = s["id"]
        jus = put("observation", "JUSTICE", 0, {"subject": sid, "outcome": s["justice"]})
        imp = put("observation", "IMPACT", 0, {"subject": sid, "exposure": s["impact_exposure"]})
        mkt = put("observation", "MARKET", 0, {"subject": sid, "volatility": s["volatility"]})
        ident = put("observation", "IDENTITY", 0, {"subject": sid, "attributed_to": sid})
        used = "neutral" if "override_justice" in faults and s["justice"] == "negative" else s["justice"]
        rate = rate_of(sp, used, s["impact_exposure"], faults)
        rv = {"subject": sid, "justice": used, "exposure": s["impact_exposure"], "rate": rate, "formula": "stand-in JWCoC/1"}
        if "inject_judgment" in faults and s["justice"] == "negative":
            rv["judgment"] = "irresponsible borrower"
        price = put("evaluation", "FINANCE", 0, rv, [jus.event_id, imp.event_id])
        lev = leverage_of(sp, r["impact_bound"], s["impact_exposure"], s["volatility"], faults)
        put("evaluation", "FINANCE", 0, {"leverage_limit": lev, "subject": sid, "exposure": s["impact_exposure"],
                                         "bound": r["impact_bound"], "formula": "stand-in headroom/1"}, [imp.event_id, mkt.event_id])
        if s["savings"] > 0:
            balance[sid] = s["savings"]
            book(0, sid, s["savings"], "deposit", [ident.event_id])
        if s["credit_request"] > 0:
            cu, term = s["credit_request"], s["credit_term_days"]
            cond = {"a_output_covers_repayment": s["projected_output"] >= cu * (1 + rate * term / 365),
                    "b_within_axiomatic_bound": s["impact_exposure"] <= r["impact_bound"],
                    "c_within_safety_margin": aggregate + cu <= r["safety_margin"]}
            ev = put("evaluation", "FINANCE", 0, {"credit_conditions": cond, "subject": sid, "requested": cu}, [price.event_id])
            if all(cond.values()) or "credit_as_right" in faults:
                aggregate += cu
                due = None if "perpetual_credit" in faults else term
                prov = [price.event_id] if "credit_as_right" in faults else [ev.event_id]
                act = put("decision", "FINANCE", 0, {"credit_issue": sid, "cu": cu, "rate": rate, "term_days": due, "due_day": due,
                                                     "basis": "entitlement" if "credit_as_right" in faults else "FINANCE §5.1 a-c"}, prov)
                to = "holding:" + sid if "override_attribution" in faults else sid
                book(0, to, cu, "credit", [act.event_id, ident.event_id], of=sid)
                credits[sid] = {"outstanding": cu, "daily": cu / term, "due": due, "exposure": s["impact_exposure"], "issue": act.event_id}
            else:
                put("notice", "FINANCE", 0, {"credit_refused": sid, "failed": sorted(c for c, ok in cond.items() if not ok)}, [ev.event_id])
    for k in range(r["horizon_days"]):
        if k == r["request_day"]:
            for kind in r["requests"]:
                q = put("observation", "EXTERNAL/REQUEST", k, {"request": kind})
                if "finance_overreach" in faults:
                    put("action", "FINANCE", k, {"perform": kind}, [q.event_id])
                else:
                    put("notice", "FINANCE", k, {"request": kind, "response": "refused", "basis": list(REQUESTS[kind])}, [q.event_id])
        if k > 0:
            for sid in sorted(credits):
                c = credits[sid]
                if c["outstanding"] <= 0 or c["due"] is None:
                    continue
                pay = c["outstanding"] if k >= c["due"] else min(c["daily"], c["outstanding"])
                c["outstanding"] = round(c["outstanding"] - pay, 9)
                book(k, sid, -pay, "repayment", [c["issue"]])
                if c["outstanding"] <= 1e-9:
                    c["outstanding"] = 0.0
                    put("notice", "FINANCE", k, {"credit_closed": sid}, [c["issue"]])
            for sid in sorted(balance):
                ret = round(balance[sid] * sp["savings_rate_per_day"], 9)
                if "discretionary_return" in faults and k == 10 and sid == sorted(balance)[0]:
                    ret = round(ret + 5.0, 9)
                ev = put("evaluation", "FINANCE", k, {"savings_return": sid, "balance": balance[sid], "days": 1,
                                                      "rate_per_day": sp["savings_rate_per_day"], "return": ret,
                                                      "formula": "stand-in balance*rate_per_day*days/1"})
                book(k, sid, ret, "savings_return", [ev.event_id])
                balance[sid] = round(balance[sid] + ret, 9)
        active = [c for c in credits.values() if c["outstanding"] > 0]
        exp_total = round(sum(c["exposure"] for c in active), 9)
        outstanding = round(sum(c["outstanding"] for c in active), 9)
        put("evaluation", "FINANCE", k, {"reserve": reserve_of(sp, exp_total, outstanding, faults), "exposure_total": exp_total,
                                         "outstanding": outstanding, "formula": "stand-in impact/1"})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    justice = {m.value["subject"]: m.value["outcome"] for m in msgs if m.source == "JUSTICE"}
    attributed = {m.value["subject"]: m.value["attributed_to"] for m in msgs if m.source == "IDENTITY"}
    rates = [m.value for m in msgs if m.source == "FINANCE" and "rate" in m.value and "subject" in m.value and "credit_issue" not in m.value]
    ledger = [m for m in msgs if m.source == "FINANCE/LEDGER"]

    # §3.2 direction: pairs that differ in one factor only
    bad, pairs = [], 0
    for a in rates:
        for b in rates:
            if a["subject"] >= b["subject"]:
                continue
            ja, jb = SIGN[justice[a["subject"]]], SIGN[justice[b["subject"]]]
            if a["exposure"] == b["exposure"] and ja != jb:
                pairs += 1
                better, worse = (a, b) if ja > jb else (b, a)
                if not better["rate"] < worse["rate"]:
                    bad.append(f"{better['subject']} ({justice[better['subject']]}) {better['rate']} not below "
                               f"{worse['subject']} ({justice[worse['subject']]}) {worse['rate']}")
            if ja == jb and a["exposure"] != b["exposure"]:
                pairs += 1
                lo, hi = (a, b) if a["exposure"] < b["exposure"] else (b, a)
                if not hi["rate"] > lo["rate"]:
                    bad.append(f"{hi['subject']} exposure {hi['exposure']} rate {hi['rate']} not above "
                               f"{lo['subject']} exposure {lo['exposure']} rate {lo['rate']}")
    out.append(v("FINANCE-3.2-02", "cost_direction", bad,
                 f"{pairs} pairs of Subjects differing in one factor: better Justice history priced lower, higher impact "
                 "exposure priced higher (Justice outcome as recorded by JUSTICE)",
                 "{n} pairs priced against the direction of §3.2") if pairs else
               na("FINANCE-3.2-02", "cost_direction", "cost direction", "no two Subjects differ in exactly one of the two factors"))

    # §3.1 CU: unitless, fungible
    bad = [m.event_id for m in ledger if set(m.value) - {"subject", "cu", "entry", "operation_of"}]
    out.append(v("FINANCE-3.1-01", "cu_unitless_fungible", bad,
                 f"{len(ledger)} ledger entries in bare CU: no unit, no lot-dependent value",
                 "{n} ledger entries with a unit or a lot-dependent value") if ledger else
               na("FINANCE-3.1-01", "cu_unitless_fungible", "CU ledger", "no ledger entry"))

    # §5.1 credit: conditional, temporary
    issues = [m for m in msgs if m.source == "FINANCE" and m.value.get("credit_issue")]
    bad = []
    for m in issues:
        conds = [log.get(e).value.get("credit_conditions") for e in m.provenance]
        conds = [c for c in conds if c is not None]
        if not conds or not all(conds[0].values()):
            bad.append(f"{m.value['credit_issue']}: issued without the §5.1 conditions holding")
        if not m.value.get("term_days"):
            bad.append(f"{m.value['credit_issue']}: no term")
        else:
            due = m.arrived_at + m.value["term_days"]
            closed = [x for x in msgs if x.source == "FINANCE" and x.value.get("credit_closed") == m.value["credit_issue"]]
            if due < r["horizon_days"] and not (closed and closed[0].arrived_at <= due):
                bad.append(f"{m.value['credit_issue']}: not closed by day {due}")
    refused = [m for m in msgs if m.source == "FINANCE" and m.value.get("credit_refused")]
    out.append(v("FINANCE-5.1-02", "credit_temporary_conditional", bad,
                 f"{len(issues)} credits issued only where the §5.1 conditions held, each with a term and closed by it; "
                 f"{len(refused)} refused", "{n} credits issued as a right or without an end") if issues else
               na("FINANCE-5.1-02", "credit_temporary_conditional", "credit", "no credit issued"))

    # §6.1 savings returns: recomputable from the recorded inputs; the same input gives the same log
    rets = [m for m in msgs if m.source == "FINANCE" and m.value.get("savings_return")]
    booked = {e: m for m in ledger if m.value["entry"] == "savings_return" for e in m.provenance}
    bad = [m.event_id for m in rets if m.value["return"] != round(m.value["balance"] * m.value["rate_per_day"] * m.value["days"], 9)
           or m.event_id not in booked or booked[m.event_id].value["cu"] != m.value["return"]]
    again = run(r)
    if again.digest() != log.digest():
        bad.append("re-execution differs")
    out.append(v("FINANCE-6.1-02", "savings_deterministic_auditable", bad,
                 f"{len(rets)} savings returns recompute from their recorded inputs and are booked as computed; re-execution is identical",
                 "{n} savings returns not derivable from their recorded inputs") if rets else
               na("FINANCE-6.1-02", "savings_deterministic_auditable", "savings returns", "no savings"))

    # §6.2 reserves: impact-based, not percentage-based (log + metamorphic: balances doubled)
    res = [m.value for m in msgs if m.source == "FINANCE" and "reserve" in m.value]
    by_exp: Dict[float, set] = {}
    for x in res:
        by_exp.setdefault(x["exposure_total"], set()).add(x["reserve"])
    # §6.2 fixes the basis only: the same impact exposure gives the same reserve, and balances alone never move it.  The shape
    # of an impact-based function (growth, steps, plateaus) is not fixed by the text (review КТ6-GPT-03).
    bad = [f"exposure {e}: reserves {sorted(s)} vary with the outstanding balance" for e, s in sorted(by_exp.items()) if len(s) > 1]
    doubled = dict(r, subjects=[dict(s, credit_request=2 * s["credit_request"], projected_output=2 * s["projected_output"])
                                for s in r["subjects"]], safety_margin=2 * r["safety_margin"])
    res2 = [m.value["reserve"] for m in run(doubled).messages() if m.source == "FINANCE" and "reserve" in m.value]
    if res2 != [x["reserve"] for x in res]:
        bad.append("doubling every credit (same Subjects, same impact) changes the reserve")
    out.append(v("FINANCE-6.2-01", "reserve_impact_based", bad,
                 f"the reserve is the same wherever the impact exposure is the same ({len(by_exp)} exposure levels: "
                 + ", ".join(f"{e:g} -> {min(s):g}" for e, s in sorted(by_exp.items())[:6])
                 + ") and is unchanged when only balances change", "{n} signs of a balance-based (percentage) reserve") if len(by_exp) > 1 or any(x["outstanding"] for x in res) else
               na("FINANCE-6.2-01", "reserve_impact_based", "reserves", "no outstanding credit"))

    # §9 leverage: impact-based, not volatility-based (log + metamorphic: volatility changed)
    levs = {m.value["subject"]: m.value for m in msgs if m.source == "FINANCE" and "leverage_limit" in m.value}
    calm = dict(r, subjects=[dict(s, volatility=0.0) for s in r["subjects"]])
    levs2 = {m.value["subject"]: m.value["leverage_limit"] for m in run(calm).messages()
             if m.source == "FINANCE" and "leverage_limit" in m.value}
    bad = [f"{s}: limit {x['leverage_limit']} becomes {levs2[s]} when only volatility changes" for s, x in sorted(levs.items())
           if levs2.get(s) != x["leverage_limit"]]
    # §9 fixes the basis only: the same impact exposure (under the same bound) gives the same limit; whether the limit falls
    # with exposure is not stated (review КТ6-GPT-03, applied to §9 as well)
    for a in levs.values():
        for b in levs.values():
            if a["subject"] < b["subject"] and a["exposure"] == b["exposure"] and a["bound"] == b["bound"] \
                    and a["leverage_limit"] != b["leverage_limit"]:
                bad.append(f"{a['subject']} and {b['subject']}: same exposure {a['exposure']}, limits {a['leverage_limit']} "
                           f"and {b['leverage_limit']}")
    out.append(v("FINANCE-9-02", "leverage_impact_based", bad,
                 f"{len(levs)} leverage limits: equal for equal impact exposure and unchanged when only price volatility changes",
                 "{n} signs of a volatility-based leverage limit") if levs else
               na("FINANCE-9-02", "leverage_impact_based", "leverage", "no Subject"))

    # §1 and §13: exclusions; Justice outcome and identity attribution used as given; no judgment in FINANCE records
    reqs = [m for m in msgs if m.source == "EXTERNAL/REQUEST"]
    performed = {log.get(m.provenance[0]).value["request"] for m in msgs if m.source == "FINANCE" and m.value.get("perform")}
    regraded = [f"{x['subject']}: Justice {justice[x['subject']]} priced as {x['justice']}" for x in rates if x["justice"] != justice[x["subject"]]]
    rebooked = [f"{m.value['operation_of']}: booked to {m.value['subject']}" for m in ledger
                if m.value["subject"] != attributed.get(m.value["operation_of"])]
    judged = [f"{x['subject']}: {sorted(set(x) - RATE_FIELDS)}" for x in rates if set(x) - RATE_FIELDS]
    for rid, chk, extra, ok in (
            ("FINANCE-1-01", "finance_exclusions", regraded,
             "no fiat regime, no subjective valuation or preference aggregation; Justice outcomes used as recorded"),
            ("FINANCE-13-01", "cross_layer_isolation", regraded + rebooked + judged,
             "identity attribution and Justice outcomes used as given; no policy, ideology or moral judgment in FINANCE records")):
        mine = [m for m in reqs if rid in REQUESTS[m.value["request"]]]
        bad = [f"{m.value['request']} performed" for m in mine if m.value["request"] in performed] + extra
        out.append(v(rid, chk, bad, f"{len(mine)} excluded request(s) refused; " + ok, "{n} breaches of the FINANCE exclusions"))
    return out


IMPLEMENTS = {
    "FINANCE-1-01": ("finance_exclusions", "PARTIAL", "Exclusions observed as refusals of declared requests and as the Justice outcome "
                     "used unchanged; a fiat regime is not modelled beyond the request."),
    "FINANCE-3.1-01": ("cu_unitless_fungible", "PARTIAL", "Observed on ledger entries (no unit, no lot-dependent value)."),
    "FINANCE-3.2-02": ("cost_direction", "PARTIAL", "Direction only, on pairs differing in one factor; JWCoC has no formula "
                       "(stand-in, CALIBRATION_MAP); Justice history as a declared class (H-FM-2)."),
    "FINANCE-5.1-02": ("credit_temporary_conditional", "PARTIAL", "The §5.1 conditions are declared values; 'temporary' as a term "
                       "and closure by it."),
    "FINANCE-6.1-02": ("savings_deterministic_auditable", "PARTIAL", "Recomputability and determinism; the return formula is a stand-in."),
    "FINANCE-6.2-01": ("reserve_impact_based", "PARTIAL", "Basis only (H-FM-3, metamorphic): equal exposure gives an equal "
                       "reserve, balances alone do not move it; the sizing function and its shape are not given."),
    "FINANCE-9-02": ("leverage_impact_based", "PARTIAL", "Basis only (H-FM-3, metamorphic): equal exposure gives an equal limit, "
                     "volatility alone does not move it; the limit function and its shape are not given."),
    "FINANCE-13-01": ("cross_layer_isolation", "PARTIAL", "Observed as attribution and Justice outcome used as given, refusals, "
                      "and no fields beyond the pricing record."),
}


class FinanceMechanicsModule(LabModule):
    id = "finance_mechanics"
    version = "1.1.0"
    title = {"en": "Finance mechanics: cost of capital, credit, reserves, leverage",
             "ru": "Финансовая механика: цена капитала, кредит, резервы, плечо"}
    summary = {"en": "Several Subjects borrow and save. Does the cost of capital move in the direction FINANCE fixes, is credit "
                     "conditional and temporary, and are reserves and leverage set by impact rather than by a percentage or by volatility?",
               "ru": "Несколько субъектов берут кредит и копят. Движется ли цена капитала в направлении, заданном FINANCE, условен ли "
                     "и временен ли кредит, задаются ли резервы и плечо воздействием, а не процентом или волатильностью?"}
    protocols = ["DKP-2-FINANCE-001"]
    example_order = ["four_subjects", "faulty_pricing", "faulty_basis", "faulty_scope"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_finance_mechanics_module.py"]
    hypotheses = [
        {"id": "H-FM-1", "source": "missing", "text": {
            "en": "FINANCE gives no formula for JWCoC (§3.2), interest (§4.1), savings returns (§6.1), reserve sizing (§6.2) or "
                  "leverage limits (§9). The module uses declared stand-ins; only properties the text fixes are checked.",
            "ru": "FINANCE не даёт формул для JWCoC (§3.2), процента (§4.1), доходности сбережений (§6.1), размера резервов "
                  "(§6.2) и пределов плеча (§9). Модуль использует объявленные заглушки; проверяются только свойства, заданные текстом."}},
        {"id": "H-FM-2", "source": "text", "text": {
            "en": "'Positive justice contribution' and 'negative or risky impact exposure' (§3.2) are read as a class of the "
                  "Subject's Justice history (positive / neutral / negative) and a declared impact exposure.",
            "ru": "'Positive justice contribution' и 'negative or risky impact exposure' (§3.2) читаются как класс истории "
                  "Справедливости субъекта (положительный / нейтральный / отрицательный) и объявленная подверженность воздействию."}},
        {"id": "H-FM-3", "source": "text", "text": {
            "en": "'Impact-based, not percentage-based' (§6.2): the same impact exposure gives the same reserve, and the reserve "
                  "does not change when only outstanding balances change. 'Impact-based, not volatility-based' (§9): the same "
                  "impact exposure gives the same limit, and the limit does not change when only price volatility changes. The "
                  "shape of either function (growth, steps, plateaus) is not fixed by the text.",
            "ru": "'Impact-based, not percentage-based' (§6.2): одинаковое воздействие даёт одинаковый резерв, и резерв не меняется, "
                  "когда меняются только остатки. 'Impact-based, not volatility-based' (§9): одинаковое воздействие даёт одинаковый "
                  "предел, и предел не меняется, когда меняется только волатильность цены. Форма функций (рост, ступени, плато) "
                  "текстом не задана."}},
    ]
    inputs = {
        "horizon_days": {"type": "int", "min": 2, "max": 3650, "default": 40, "unit": "DTI-Day", "source": "user",
                         "label": {"en": "DTI-Days", "ru": "DTI-дней"}},
        "subjects": {"type": "list", "min_items": 1, "max_items": 50, "items": SUBJECT, "default": SUBJECTS_DEFAULT, "source": "user",
                     "label": {"en": "Subjects (Justice class, impact exposure, volatility, savings, credit)",
                               "ru": "Субъекты (класс Справедливости, воздействие, волатильность, сбережения, кредит)"}},
        "impact_bound": {"type": "number", "min": 0, "max": 1000, "default": 10.0, "source": "missing",
                         "label": {"en": "Axiomatic impact bound (impact units; not given)", "ru": "Аксиоматическая граница воздействия (не задана)"}},
        "safety_margin": {"type": "number", "min": 0, "max": 10 ** 12, "default": 10000.0, "unit": "CU", "source": "missing",
                          "label": {"en": "Systemic safety margin for aggregate credit (not given)",
                                    "ru": "Системный запас для совокупного кредита (не задан)"}},
        "stand_in": {**STAND_IN, "source": "missing", "default": {k: f["default"] for k, f in STAND_IN["fields"].items()},
                     "label": {"en": "Lab stand-ins for the formulas FINANCE does not give (H-FM-1)",
                               "ru": "Заглушки лаборатории для формул, которых нет в FINANCE (H-FM-1)"}},
        "request_day": {"type": "int", "min": -1, "max": 3650, "default": 1, "unit": "DTI-Day", "source": "user",
                        "label": {"en": "Excluded requests arrive on day (-1: never)", "ru": "Исключённые запросы приходят в день (-1: никогда)"}},
        "requests": {"type": "list", "min_items": 0, "max_items": len(REQUESTS), "items": {"type": "enum", "values": list(REQUESTS)},
                     "default": list(REQUESTS), "source": "user",
                     "label": {"en": "Requests for functions FINANCE excludes (§1, §13)", "ru": "Запросы функций, исключённых FINANCE (§1, §13)"}},
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        ids = [s["id"] for s in r["subjects"]]
        if len(set(ids)) != len(ids):
            p.append("input.subjects: repeated id")
        for key in ("faults", "requests"):
            if len(set(r[key])) != len(r[key]):
                p.append(f"input.{key}: repeated item")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        rates = {m.value["subject"]: m.value["rate"] for m in msgs if m.source == "FINANCE" and "formula" in m.value
                 and m.value.get("formula", "").startswith("stand-in JWCoC")}
        issued = sorted(m.value["credit_issue"] for m in msgs if m.source == "FINANCE" and m.value.get("credit_issue"))
        refused = sorted(m.value["credit_refused"] for m in msgs if m.source == "FINANCE" and m.value.get("credit_refused"))
        reserves = [m.value["reserve"] for m in msgs if m.source == "FINANCE" and "reserve" in m.value]
        outputs = {"cost_of_capital": rates, "credit_issued": issued, "credit_refused": refused,
                   "reserve_first_last": [reserves[0], reserves[-1]] if reserves else [],
                   "leverage_limits": {m.value["subject"]: m.value["leverage_limit"] for m in msgs if "leverage_limit" in (m.value or {})},
                   "requests_refused": sum(1 for m in msgs if m.source == "FINANCE" and m.value.get("response") == "refused"),
                   "stand_in": "declared (H-FM-1): values are not FINANCE values",
                   "messages": [m.as_dict() for m in msgs][:300],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        explain = [{"en": f"Cost of capital (stand-in): {rates}. Credit issued to {issued or 'nobody'}, refused to {refused or 'nobody'}.",
                    "ru": f"Цена капитала (заглушка): {rates}. Кредит выдан: {issued or 'никому'}, отказано: {refused or 'никому'}."},
                   {"en": "The values are lab stand-ins (H-FM-1); the checks test direction, basis and determinism, not the values.",
                    "ru": "Значения — заглушки лаборатории (H-FM-1); проверяются направление, основание и детерминизм, а не значения."}]
        return ModuleResult(outputs=outputs, checks=res, explain=explain)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"credit_issued": len(outputs["credit_issued"]), "credit_refused": len(outputs["credit_refused"]),
                "requests_refused": outputs["requests_refused"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "four_subjects": {},
            "faulty_pricing": {"faults": ["jwcoc_inverted", "override_justice", "inject_judgment"]},
            "faulty_basis": {"faults": ["percentage_reserve", "volatility_leverage", "discretionary_return"]},
            "faulty_scope": {"faults": ["finance_overreach", "override_attribution", "denominated_cu", "credit_as_right"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_subject": {"subjects": [{"id": "A"}, {"id": "A"}]},
                "zero_term": {"subjects": [{"id": "A", "credit_request": 10.0, "credit_term_days": 0}]},
                "unknown_fault": {"faults": ["print_money"]}}


for _s in SUBJECTS_DEFAULT:
    _s.update(resolve(_s, SUBJECT["fields"]))
