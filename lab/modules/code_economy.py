"""
CODE ECONOMY module — the economic and social articles of the Code of Planetary Synergy.

Code of Planetary Synergy §1-§6 and §9-§18: two circuits and the Mirror Peg (§1), conditioned emission
in tranches (§2), raw exports and equity tokens (§3), technological inheritance (§4), qualification (§5),
exit and talent leasing (§6), Regional Operators (§9), the Glass Pocket (§10), lobbying (§11), full product
cost (§12), reserves (§13), Proof-of-Truth (§14), open algorithms (§15), inheritance (§16), UBR (§17) and
social contribution (§18).  Cross-checks: DKP-1-AXIOMS-001 A5 (full cost), DKP-1-IDENTITY-001 §6
(coordinated identities are one Subject), DKP-2-LABOR-001 §4.1 and §9.1, DKP-7-PRIVACY-001 §10.

Time unit: month.  The Code gives the rules; it gives no amounts (lease fee, equity share, fortune
threshold, UBR quantities), no peg function and no definition of 'developed nations'.  Those enter as
declared inputs (source missing) or hypotheses, and checks that depend on them stay PARTIAL.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

PEG_MONTHS = 60            # §1.2 "5-year moving average"
QUINTILE = 0.20            # §1.2 "bottom 20% of countries"
PUBLIC_DOMAIN_MONTHS = 60  # §1.3 "after 5 years", §4.1 "5 years after patent registration"
LEASE_WAIT_MONTHS = 12     # §6.3 "only after a year of successful work"
RESERVE_SHARE = 0.40       # §13.1 "40% of land"
RESERVE_METHODS = ("robotized_tunnel", "bio_leaching")      # §13.2 examples of invisible extraction
PROHIBITED_METHODS = ("open_pit", "logging")                # §13.2 "Open pits and logging are prohibited."
OPEN_SOURCE_DOMAINS = ("resource_allocation", "social_rating", "news_feed")   # §15.1
UBR_SET = ("food", "shelter", "connectivity")               # §17.1
ACTIVITIES = ("education", "creativity", "socially_useful")  # §18.1

FAULTS = {
    "top_quintile_peg": "the Mirror Peg follows the top 20% of countries",
    "short_peg_window": "the Mirror Peg uses a 3-year average",
    "exempt_without_pledge": "Venture capital is exempted without the Open Tech Pledge",
    "late_release": "pledged developments are released after 6 years",
    "unlock_before_kpi": "a tranche is unlocked before its KPI is physically verified",
    "manual_transfer": "a global fund pays outside a targeted smart contract",
    "export_without_participation": "a raw export is permitted without participation in the value chain",
    "no_equity_tokens": "processors issue no equity tokens to the exporting country",
    "patent_kept": "a life-support patent stays private after 5 years",
    "recognize_without_exam": "a diploma is recognized without the AI exam",
    "block_exit": "a citizen's departure is refused",
    "pay_before_year": "the lease fee is paid before a year of successful work",
    "pay_to_budget": "the lease fee goes to the government budget",
    "keep_failed_operator": "an Operator who missed the KPI keeps the contract",
    "delayed_publication": "budget transactions are published a month late",
    "allow_secret": "a secret expenditure item is accepted",
    "ignore_covert": "covert lobbying is not classified as an offense",
    "externalities_omitted": "prices omit disposal and restoration costs",
    "permit_open_pit": "an open pit is permitted in a reserve",
    "income_from_declaration": "Biosphere Operator income is set from a declaration, not sensor data",
    "per_identity_cost": "vote-buying cost is charged per identity, so splitting into identities is cheaper",
    "global_reputation": "validator votes are weighted by overall reputation, not by field",
    "allow_closed": "a closed-source algorithm allocates resources",
    "inherit_infrastructure": "infrastructure capital passes to heirs",
    "ubr_conditional": "UBR is withheld from passive persons",
}


def _ma(r, months_window, bottom=True):
    """Peg anchor per month: mean over the window of the mean monthly growth of the quintile."""
    cs = sorted(r["countries"], key=lambda c: (c["gdp_per_capita"], c["id"]))
    n = max(1, math.ceil(QUINTILE * len(cs)))
    q = cs[:n] if bottom else cs[-n:]
    out = []
    for m in range(r["months"]):
        hist = []
        for k in range(m - months_window + 1, m + 1):     # month k of the horizon; k < 0 is history
            y = (k + PEG_MONTHS) // 12                     # growth list starts 5 years before month 0
            hist.append(sum(c["growth"][y] for c in q) / len(q))
        out.append(round(sum(hist) / len(hist), 9))
    return [c["id"] for c in q], out


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("month", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, m, value):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{m:04d}-{n['i']:05d}", kind=kind, source=source, arrived_at=m,
                                  decided_at=m if kind in ("decision", "action") else None, value=value, order=order[kind]))

    H = r["months"]
    # §1.2 Mirror Peg
    quint, anchor = _ma(r, 36 if "short_peg_window" in faults else PEG_MONTHS, bottom="top_quintile_peg" not in faults)
    put("evaluation", "PEG", 0, {"development_quintile": quint, "anchor": anchor,
                                 "pegged": sorted(c["id"] for c in r["countries"] if c["developed"]),
                                 "peg_function": "not defined (§1.2 'rigidly pegged')"})
    # §1.3 Venture Gateway
    for v in r["venture"]:
        ex = v["pledge"] or "exempt_without_pledge" in faults
        put("decision", "VENTURE", 0, {"fund": v["id"], "exempt": ex, "pledge": v["pledge"]})
        if v["pledge"]:
            for d in v["developments"]:
                rel = d + PUBLIC_DOMAIN_MONTHS + (12 if "late_release" in faults else 0)
                if rel < H:
                    put("action", "VENTURE", rel, {"fund": v["id"], "development_month": d, "public_domain": True})
    # §2 conditioned emission
    for t in r["tranches"]:
        if t["channel"] != "smart_contract" and "manual_transfer" not in faults:
            put("decision", "FUND", 0, {"tranche": t["id"], "paid": False, "reason": "§2.1: only through targeted smart contracts"})
            continue
        if not t["targeted"] and "manual_transfer" not in faults:
            put("decision", "FUND", 0, {"tranche": t["id"], "paid": False, "reason": "§2.1: the smart contract names no target"})
            continue
        if "unlock_before_kpi" in faults:
            m = 0
        elif t["kpi_verified_month"] >= 0:
            m = t["kpi_verified_month"]
        else:
            put("decision", "FUND", 0, {"tranche": t["id"], "paid": False, "reason": "§2.2: KPI not physically verified"})
            continue
        if m < H:
            put("action", "FUND", m, {"tranche": t["id"], "paid": True, "channel": t["channel"], "amount": t["amount"]})
    # §3 raw exports
    for e in r["exports"]:
        ok = e["participates"] or "export_without_participation" in faults
        put("decision", "TRADE", 0, {"export": e["id"], "exporter": e["exporter"], "permitted": ok})
        if ok and "no_equity_tokens" not in faults:
            for p in e["processors"]:
                put("action", "TRADE", 0, {"equity_tokens": e["exporter"], "processor": p, "share": r["equity_share"],
                                           "resource": e["resource"]})
    # §4 technological inheritance
    for p in r["patents"]:
        if (p["life_support"] or p["venture"]) and "patent_kept" not in faults:
            m = p["registered_month"] + PUBLIC_DOMAIN_MONTHS
            if m < H:
                put("action", "PATENT", m, {"patent": p["id"], "public_domain": True})
    # §5 qualification
    for d in r["diplomas"]:
        put("decision", "QUAL", 0, {"diploma": d["person"],
                                    "recognized_everywhere": d["passed_ai_exam"] or "recognize_without_exam" in faults})
    # §6 exit and talent leasing
    for x in r["relocations"]:
        m = x["month"]
        put("decision", "EXIT", m, {"person": x["person"], "leave": "block_exit" not in faults, "from": x["donor"], "to": x["recipient"],
                                    "relocation_paid_by": "global fund" if x["depressed_zone"] else "not covered (not a depressed zone)"})
        if "block_exit" in faults:
            continue
        first = m + (1 if "pay_before_year" in faults else LEASE_WAIT_MONTHS)
        if x["successful_months"] >= LEASE_WAIT_MONTHS or "pay_before_year" in faults:
            k = first
            while k < H and k - m <= max(x["successful_months"], 1):
                put("action", "LEASE", k, {"person": x["person"], "payer": x["recipient"], "fee": r["lease_fee"],
                                           "to": "government budget of " + x["donor"] if "pay_to_budget" in faults
                                           else "Education Fund of " + x["donor"]})
                k += 12
    # §9 Regional Operators
    for o in r["operators"]:
        end = o["start_month"] + o["kpi_months"]
        if o["irremovable"]:
            put("decision", "GOV", o["start_month"], {"operator": o["region"], "hired": False,
                                                      "reason": "§9.1: no irremovable power"})
            continue
        put("action", "GOV", o["start_month"], {"operator": o["region"], "hired": True, "until": end})
        if end < H:
            met = o["kpi_achieved"] >= o["kpi_target"]
            keep = met or "keep_failed_operator" in faults
            put("action", "GOV", end, {"operator": o["region"], "kpi_met": met,
                                       "contract": "completed" if met else ("kept" if keep else "terminated automatically")})
    # §10 Glass Pocket
    for b in r["budget"]:
        if b["secret"] and "allow_secret" not in faults:
            put("decision", "BUDGET", b["month"], {"transaction": b["id"], "accepted": False, "reason": "§10.1: secret items are prohibited"})
            continue
        pub = b["month"] + (1 if "delayed_publication" in faults else 0)
        put("action", "BUDGET", min(pub, H - 1), {"transaction": b["id"], "accepted": True, "booked": b["month"], "published": pub})
    # §11 lobbying
    for l in r["lobbying"]:
        put("decision", "LAW", 0, {"interaction": l["id"], "covert": l["covert"],
                                   "criminal_offense": l["covert"] and "ignore_covert" not in faults})
    # §12 full product cost
    for g in r["goods"]:
        price = g["base_cost"] + (0 if "externalities_omitted" in faults else g["disposal_cost"] + g["restoration_cost"])
        put("decision", "MARKET", 0, {"good": g["id"], "price": round(price, 9)})
    # §13 reserves
    put("evaluation", "BIOSPHERE", 0, {"reserve_share": round(r["land"]["reserve_km2"] / r["land"]["total_km2"], 9)})
    for p in r["extraction_permits"]:
        if not p["in_reserve"]:
            ok = True
        elif p["method"] in PROHIBITED_METHODS:
            ok = "permit_open_pit" in faults
        else:
            ok = p["method"] in RESERVE_METHODS
        put("decision", "BIOSPHERE", 0, {"permit": p["site"], "method": p["method"], "in_reserve": p["in_reserve"], "permitted": ok,
                                         "basis": "listed invisible method" if p["method"] in RESERVE_METHODS else
                                         ("prohibited" if p["method"] in PROHIBITED_METHODS else "method not listed; surface test undefined")})
    w = r["operator_income_weights"]
    for p in r["reserve_residents"]:
        if "income_from_declaration" in faults:
            inc, basis = p["declared_income"], ["declaration"]
        else:
            inc, basis = w["biomass"] * p["biomass"] + w["co2"] * p["co2_reduction"] + w["biodiversity"] * p["biodiversity"], \
                ["biomass", "co2_reduction", "biodiversity"]
        put("action", "BIOSPHERE", 0, {"resident": p["person"], "status": "Biosphere Operator", "income": round(inc, 9),
                                       "inputs": basis})
    # §14 Proof-of-Truth
    for s in r["statements"]:
        put("decision", "TRUTH", 0, {"statement": s, "sent_to_validators": True})
    vb = r["vote_buying"]
    per = vb["votes"] / vb["identities"]
    cost = vb["identities"] * per ** 2 if "per_identity_cost" in faults and vb["coordinated"] else \
        (vb["votes"] ** 2 if vb["coordinated"] else vb["identities"] * per ** 2)
    put("evaluation", "TRUTH", 0, {"votes": vb["votes"], "identities": vb["identities"], "coordinated": vb["coordinated"],
                                   "charged_as": "one Subject (IDENTITY §6)" if vb["coordinated"] and "per_identity_cost" not in faults
                                   else "per identity", "cost": round(cost, 9)})
    for v in r["validators"]:
        rep = v["overall_reputation"] if "global_reputation" in faults else v["field_reputation"]
        put("decision", "TRUTH", 0, {"validator": v["id"], "field": v["field"], "weight": rep})
    # §15 open algorithms
    for a in r["algorithms"]:
        need = a["domain"] in OPEN_SOURCE_DOMAINS
        ok = a["open_source"] or not need or "allow_closed" in faults
        put("decision", "ALGO", 0, {"algorithm": a["id"], "domain": a["domain"], "open_source": a["open_source"], "deployed": ok})
    # §16 inheritance
    for e in r["estates"]:
        m = e["death_month"]
        total = e["personal"] + e["infrastructure"]
        ultra = total >= r["ultra_large_threshold"]
        heirs = 0.0 if ultra else e["personal"]
        if "inherit_infrastructure" in faults:
            heirs += e["infrastructure"]
        put("action", "ESTATE", m, {"owner": e["owner"], "to_heirs": heirs,
                                    "to_global_development_fund": total if ultra else 0.0,
                                    "infrastructure_not_inherited": 0.0 if "inherit_infrastructure" in faults else e["infrastructure"],
                                    "power_inherited": False, "ultra_large": ultra,
                                    "infrastructure_destination": "Global Development Fund" if ultra else "not defined"})
    # §17-§18 UBR and contribution
    for p in r["persons"]:
        passive = p["activity"] == "none"
        ubr = [] if passive and "ubr_conditional" in faults else list(UBR_SET)
        put("action", "UBR", 0, {"person": p["person"], "ubr": ubr, "activity": p["activity"],
                                 "additional_benefits_rating": "reduced" if passive else "standard",
                                 "open": "F-033" if passive else None})
    return log


def checks(r: Dict[str, Any], log: EventLog) -> List[CheckResult]:
    msgs = log.messages()
    out: List[CheckResult] = []
    H = r["months"]

    def v(rid, chk, bad, ok, no, ev=None):
        e = dict(ev or {})
        if bad:
            e["violations"] = bad[:10]
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok, evidence=e)

    def unk(rid, chk, why, ev=None):
        return CheckResult(rid, chk, UNKNOWN, why, evidence=dict(ev or {}))

    def na(rid, chk, what, why):
        return CheckResult(rid, chk, NOT_APPLICABLE, what, applicability=why)

    def by(src, key=None):
        return [m for m in msgs if m.source == src and (key is None or key in m.value)]

    # §1.1 circuits: every asset in exactly one circuit
    bad = [a["id"] for a in r["assets"] if a["circuit"] not in ("basic", "venture")]
    out.append(v("CODEX-1.1-01", "two_circuits", bad, f"{len(r['assets'])} assets classified into the Basic or the Venture circuit",
                 "{n} assets outside both circuits", {"note": "what makes the circuits 'independent' is not defined"}))
    # §1.2 Mirror Peg, recomputed with explicit loops
    cs = sorted(r["countries"], key=lambda c: (c["gdp_per_capita"], c["id"]))
    k = max(1, math.ceil(QUINTILE * len(cs)))
    q = cs[:k]
    flat = []  # monthly quintile growth from month -60
    for mm in range(-PEG_MONTHS, H):
        y = (mm + PEG_MONTHS) // 12
        flat.append(sum(c["growth"][y] for c in q) / len(q))
    want = [round(sum(flat[i + 1:i + 1 + PEG_MONTHS]) / PEG_MONTHS, 9) for i in range(H)]
    peg = by("PEG")[0].value
    bad = ([] if peg["development_quintile"] == [c["id"] for c in q] else ["quintile"]) + \
        ([] if all(abs(a - b) < 1e-9 for a, b in zip(peg["anchor"], want)) else ["anchor"])
    if bad:
        out.append(v("CODEX-1.2-01", "mirror_peg_anchor", bad, "", "the peg anchor is not the 5-year average of the bottom quintile ({n})"))
    else:
        out.append(CheckResult("CODEX-1.2-01", "mirror_peg_anchor", PASS,
                               f"anchor = 5-year moving average of the growth of the bottom {k} of {len(cs)} countries; the peg function "
                               "itself and 'developed nations' are not defined (declared)", evidence={"quintile": peg["development_quintile"]}))
    # §1.3 Venture Gateway
    vd = by("VENTURE", "exempt")
    rel = {(m.value["fund"], m.value["development_month"]): m.arrived_at for m in by("VENTURE", "public_domain")}
    if r["venture"]:
        bad = [x.value["fund"] for x in vd if x.value["exempt"] and not x.value["pledge"]]
        for f in r["venture"]:
            if f["pledge"]:
                for d in f["developments"]:
                    due = d + PUBLIC_DOMAIN_MONTHS
                    if due < H and rel.get((f["id"], d)) != due:
                        bad.append(f"{f['id']}:{d}")
        out.append(v("CODEX-1.3-01", "venture_gateway", bad, "exemptions only with the Open Tech Pledge; pledged developments public "
                     "5 years after creation (H-CE-2)", "{n} exemptions or releases against §1.3"))
    else:
        out.append(na("CODEX-1.3-01", "venture_gateway", "Venture funds", "none declared"))
    # §2 tranches
    paid = {m.value["tranche"]: m for m in by("FUND", "paid") if m.value["paid"]}
    if r["tranches"]:
        bad = [t["id"] for t in r["tranches"] if t["id"] in paid and not (t["channel"] == "smart_contract" and t["targeted"])]
        out.append(v("CODEX-2.1-01", "targeted_smart_contracts", bad, "global funds paid only through targeted smart contracts",
                     "{n} payments outside a targeted smart contract"))
        bad = [t["id"] for t in r["tranches"] if t["id"] in paid and
               (t["kpi_verified_month"] < 0 or paid[t["id"]].arrived_at < t["kpi_verified_month"])]
        bad += [t["id"] for t in r["tranches"] if t["id"] not in paid and t["channel"] == "smart_contract" and t["targeted"]
                and 0 <= t["kpi_verified_month"] < H]
        out.append(v("CODEX-2.2-01", "tranche_on_verified_kpi", bad, "each tranche unlocked when its KPI was physically verified",
                     "{n} tranches unlocked early or not at all"))
    else:
        for rid, chk in (("CODEX-2.1-01", "targeted_smart_contracts"), ("CODEX-2.2-01", "tranche_on_verified_kpi")):
            out.append(na(rid, chk, "tranches", "none declared"))
    # §3 exports
    td = {m.value["export"]: m.value for m in by("TRADE", "export")}
    toks = [(m.value["equity_tokens"], m.value["processor"]) for m in by("TRADE", "equity_tokens")]
    if r["exports"]:
        out.append(v("CODEX-3.1-01", "export_requires_participation",
                     [e["id"] for e in r["exports"] if td[e["id"]]["permitted"] and not e["participates"]],
                     "raw exports permitted only to exporters in the value chain", "{n} exports permitted without participation"))
        bad = [f"{e['exporter']}->{p}" for e in r["exports"] if td[e["id"]]["permitted"] for p in e["processors"]
               if (e["exporter"], p) not in toks]
        out.append(v("CODEX-3.2-01", "equity_tokens", bad, "every processor of an exported resource issued equity tokens to the exporter "
                     "(share declared, source missing)", "{n} processors without equity tokens to the exporter"))
    else:
        for rid, chk in (("CODEX-3.1-01", "export_requires_participation"), ("CODEX-3.2-01", "equity_tokens")):
            out.append(na(rid, chk, "raw exports", "none declared"))
    # §4 patents
    pd = {m.value["patent"]: m.arrived_at for m in by("PATENT")}
    due = [p for p in r["patents"] if (p["life_support"] or p["venture"]) and p["registered_month"] + PUBLIC_DOMAIN_MONTHS < H]
    if due:
        out.append(v("CODEX-4.1-01", "public_domain_after_5_years",
                     [p["id"] for p in due if pd.get(p["id"]) != p["registered_month"] + PUBLIC_DOMAIN_MONTHS],
                     "life-support and Venture technologies entered the public domain 5 years after registration", "{n} patents kept private"))
    else:
        out.append(na("CODEX-4.1-01", "public_domain_after_5_years", "patents due", "no qualifying patent reaches 5 years within the horizon"))
    # §5
    qd = {m.value["diploma"]: m.value for m in by("QUAL")}
    if r["diplomas"]:
        out.append(v("CODEX-5.1-01", "ai_exam_recognition",
                     [d["person"] for d in r["diplomas"] if qd[d["person"]]["recognized_everywhere"] != d["passed_ai_exam"]],
                     "diplomas recognized in all jurisdictions exactly when the AI exam was passed", "{n} recognitions against §5.1"))
    else:
        out.append(na("CODEX-5.1-01", "ai_exam_recognition", "diplomas", "none declared"))
    # §6
    ex = {m.value["person"]: m.value for m in by("EXIT", "leave")}
    lease = by("LEASE")
    if r["relocations"]:
        out.append(v("CODEX-6.1-01", "absolute_exit", [p for p, x in ex.items() if not x["leave"]],
                     "every citizen left without restriction", "{n} departures refused"))
        out.append(v("CODEX-6.1-02", "relocation_costs",
                     [x["person"] for x in r["relocations"] if (ex[x["person"]]["relocation_paid_by"] == "global fund") != x["depressed_zone"]],
                     "relocation from depressed zones paid by the global fund", "{n} relocations paid against §6.1"))
        bad6, bad63, bad64 = [], [], []
        for x in r["relocations"]:
            pays = [m for m in lease if m.value["person"] == x["person"]]
            if x["successful_months"] >= LEASE_WAIT_MONTHS and x["month"] + LEASE_WAIT_MONTHS < H and not pays:
                bad6.append(x["person"])
            bad6 += [x["person"] for m in pays if m.value["payer"] != x["recipient"]]
            bad63 += [x["person"] for m in pays if m.arrived_at - x["month"] < LEASE_WAIT_MONTHS
                      or x["successful_months"] < LEASE_WAIT_MONTHS]
            bad64 += [x["person"] for m in pays if m.value["to"] != "Education Fund of " + x["donor"]]
        out.append(v("CODEX-6.2-01", "lease_fee", sorted(set(bad6)), "the recipient country paid the annual Lease Fee to the donor "
                     "(amount declared, source missing)", "{n} relocations without the recipient's annual fee"))
        out.append(v("CODEX-6.3-01", "post_factum", sorted(set(bad63)), "no fee before a year of successful work",
                     "{n} fees paid before a year of successful work"))
        out.append(v("CODEX-6.4-01", "education_fund", sorted(set(bad64)), "fees paid to the Education Fund of the region of origin",
                     "{n} fees paid to a government budget"))
    else:
        for rid, chk in (("CODEX-6.1-01", "absolute_exit"), ("CODEX-6.1-02", "relocation_costs"), ("CODEX-6.2-01", "lease_fee"),
                         ("CODEX-6.3-01", "post_factum"), ("CODEX-6.4-01", "education_fund")):
            out.append(na(rid, chk, "relocations", "none declared"))
    # §9
    gov = by("GOV", "operator")
    if r["operators"]:
        out.append(v("CODEX-9.1-01", "no_irremovable_power",
                     [m.value["operator"] for m in gov if m.value.get("hired") and
                      [o for o in r["operators"] if o["region"] == m.value["operator"]][0]["irremovable"]],
                     "every territory managed by a removable Regional Operator", "{n} irremovable offices"))
        bad = []
        for o in r["operators"]:
            end = o["start_month"] + o["kpi_months"]
            ends = [m.value for m in gov if m.value["operator"] == o["region"] and "contract" in m.value]
            if o["irremovable"] or end >= H:
                continue
            want = "completed" if o["kpi_achieved"] >= o["kpi_target"] else "terminated automatically"
            if not ends or ends[0]["contract"] != want:
                bad.append(o["region"])
        out.append(v("CODEX-9.2-01", "kpi_contract", bad, "contracts ran for the KPI period and ended automatically on a missed KPI",
                     "{n} contracts not ended as §9.2 requires"))
    else:
        for rid, chk in (("CODEX-9.1-01", "no_irremovable_power"), ("CODEX-9.2-01", "kpi_contract")):
            out.append(na(rid, chk, "Operators", "none declared"))
    # §10
    bd = by("BUDGET")
    if r["budget"]:
        bad = [m.value["transaction"] for m in bd if m.value.get("accepted") and
               ([b for b in r["budget"] if b["id"] == m.value["transaction"]][0]["secret"] or m.value["published"] != m.value["booked"])]
        out.append(v("CODEX-10.1-01", "glass_pocket", bad, "every transaction public in the month it was booked (H-CE-5); no secret items",
                     "{n} transactions secret or published late"))
    else:
        out.append(na("CODEX-10.1-01", "glass_pocket", "budget transactions", "none declared"))
    # §11
    lw = by("LAW")
    if r["lobbying"]:
        out.append(v("CODEX-11.1-01", "covert_lobbying", [m.value["interaction"] for m in lw if m.value["covert"] and not m.value["criminal_offense"]],
                     "every covert interaction classified as an offense", "{n} covert interactions not classified"))
    else:
        out.append(na("CODEX-11.1-01", "covert_lobbying", "interactions", "none declared"))
    # §12 and AXIOMS A5
    pr = {m.value["good"]: m.value["price"] for m in by("MARKET")}
    bad = [g["id"] for g in r["goods"] if pr[g["id"]] + 1e-9 < g["base_cost"] + g["disposal_cost"] + g["restoration_cost"]]
    for rid, chk in (("CODEX-12.1-01", "full_product_cost"), ("AXIOMS-AxiomA5-ExternalityAccountability-03", "externalities_in_cost")):
        if r["goods"]:
            out.append(v(rid, chk, bad, "every price includes full disposal and restoration cost", "{n} prices without the full cost"))
        else:
            out.append(na(rid, chk, "goods", "none declared"))
    # §13
    share = r["land"]["reserve_km2"] / r["land"]["total_km2"]
    if abs(share - RESERVE_SHARE) < 1e-9:
        out.append(CheckResult("CODEX-13.1-01", "reserve_share", PASS, "40% of land declared a Biosphere Reserve"))
    elif share < RESERVE_SHARE:
        out.append(v("CODEX-13.1-01", "reserve_share", [round(share, 6)], "", f"only {share:.1%} of land is reserve"))
    else:
        out.append(unk("CODEX-13.1-01", "reserve_share", f"{share:.1%} of land is reserve: '40% of land is declared' does not say "
                       "whether 40% is exact or a minimum (H-CE-6)"))
    pm = {m.value["permit"]: m.value for m in by("BIOSPHERE", "permit")}
    if r["extraction_permits"]:
        bad = [p["site"] for p in r["extraction_permits"] if p["in_reserve"] and pm[p["site"]]["permitted"] and p["method"] not in RESERVE_METHODS]
        other = [p["site"] for p in r["extraction_permits"] if p["in_reserve"] and p["method"] == "other"]
        if bad:
            out.append(v("CODEX-13.2-01", "invisible_extraction", bad, "", "{n} reserve permits for surface-disturbing methods"))
        elif other:
            out.append(unk("CODEX-13.2-01", "invisible_extraction", "a reserve permit asks for an unlisted method; the text gives examples "
                           "and no test of 'surface layer integrity'", {"sites": other}))
        else:
            out.append(v("CODEX-13.2-01", "invisible_extraction", [], "reserve extraction only by listed invisible methods; no open pits or logging", ""))
    else:
        out.append(na("CODEX-13.2-01", "invisible_extraction", "extraction permits", "none declared"))
    res = by("BIOSPHERE", "resident")
    if r["reserve_residents"]:
        w = r["operator_income_weights"]
        bad = []
        for p in r["reserve_residents"]:
            m = [x.value for x in res if x.value["resident"] == p["person"]][0]
            want = w["biomass"] * p["biomass"] + w["co2"] * p["co2_reduction"] + w["biodiversity"] * p["biodiversity"]
            if m["status"] != "Biosphere Operator" or abs(m["income"] - want) > 1e-6 or "declaration" in m["inputs"]:
                bad.append(p["person"])
        out.append(v("CODEX-13.3-01", "sensor_income", bad, "reserve residents are Biosphere Operators paid from sensor data "
                     "(income function declared, source missing)", "{n} residents paid otherwise"))
    else:
        out.append(na("CODEX-13.3-01", "sensor_income", "reserve residents", "none declared"))
    # §14
    st = by("TRUTH", "statement")
    if r["statements"]:
        out.append(v("CODEX-14.1-01", "statements_verified", [m.value["statement"] for m in st if not m.value["sent_to_validators"]],
                     "every public statement of an official went to the validator network", "{n} statements not verified"))
    else:
        out.append(na("CODEX-14.1-01", "statements_verified", "statements", "none declared"))
    vb = r["vote_buying"]
    got = by("TRUTH", "votes")[0].value
    want = vb["votes"] ** 2 if vb["coordinated"] else vb["identities"] * (vb["votes"] / vb["identities"]) ** 2
    bad = [] if abs(got["cost"] - round(want, 9)) < 1e-6 else [got["cost"]]
    out.append(v("CODEX-14.2-01", "quadratic_cost", bad, f"buying {vb['votes']:g} votes costs Votes² = {want:g} (the prose says "
                 "'exponentially': F-034)", "vote-buying cost is not Votes² for the buying Subject"))
    if vb["coordinated"]:
        out.append(v("IDENTITY-6-02", "coordinated_identities_one_subject", bad,
                     f"{vb['identities']} coordinated identities charged as one Subject", "coordinated identities charged separately"))
    else:
        out.append(na("IDENTITY-6-02", "coordinated_identities_one_subject", "coordination", "the identities do not coordinate"))
    vw = {m.value["validator"]: m.value for m in by("TRUTH", "validator")}
    if r["validators"]:
        out.append(v("CODEX-14.3-01", "field_weight", [x["id"] for x in r["validators"] if vw[x["id"]]["weight"] != x["field_reputation"]],
                     "votes weighted by reputation in the statement's field (EigenTrust values declared)",
                     "{n} votes weighted by another reputation"))
    else:
        out.append(na("CODEX-14.3-01", "field_weight", "validators", "none declared"))
    # §15
    al = {m.value["algorithm"]: m.value for m in by("ALGO")}
    if r["algorithms"]:
        out.append(v("CODEX-15.1-01", "open_algorithms",
                     [a["id"] for a in r["algorithms"] if a["domain"] in OPEN_SOURCE_DOMAINS and al[a["id"]]["deployed"] and not a["open_source"]],
                     "every algorithm influencing allocation, rating or feeds is open source", "{n} closed algorithms deployed"))
    else:
        out.append(na("CODEX-15.1-01", "open_algorithms", "algorithms", "none declared"))
    # §16
    es = {m.value["owner"]: m.value for m in by("ESTATE")}
    if r["estates"]:
        thr = r["ultra_large_threshold"]
        bad1 = [e["owner"] for e in r["estates"] if e["personal"] + e["infrastructure"] < thr and abs(es[e["owner"]]["to_heirs"] - e["personal"]) > 1e-9]
        bad2 = [e["owner"] for e in r["estates"] if es[e["owner"]]["to_heirs"] > e["personal"] + 1e-9 or es[e["owner"]]["power_inherited"]]
        bad3 = [e["owner"] for e in r["estates"] if e["personal"] + e["infrastructure"] >= thr and
                abs(es[e["owner"]]["to_global_development_fund"] - e["personal"] - e["infrastructure"]) > 1e-9]
        out.append(v("CODEX-16.1-01", "personal_assets_heritable", bad1, "personal assets of ordinary estates passed to heirs",
                     "{n} ordinary estates not inherited"))
        out.append(v("CODEX-16.1-02", "no_infrastructure_inheritance", bad2, "no infrastructure capital or power passed to heirs",
                     "{n} estates passed infrastructure or power to heirs"))
        out.append(v("CODEX-16.1-03", "ultra_large_return", bad3, "ultra-large fortunes returned to the Global Development Fund "
                     "(threshold declared, source missing; whole fortune, H-CE-8)", "{n} ultra-large fortunes not returned"))
    else:
        for rid, chk in (("CODEX-16.1-01", "personal_assets_heritable"), ("CODEX-16.1-02", "no_infrastructure_inheritance"),
                         ("CODEX-16.1-03", "ultra_large_return")):
            out.append(na(rid, chk, "estates", "no death in the horizon"))
    # §17-§18, LABOR, PRIVACY
    ub = {m.value["person"]: m.value for m in by("UBR")}
    if r["persons"]:
        bad = [p for p, x in ub.items() if sorted(x["ubr"]) != sorted(UBR_SET)]
        out.append(v("CODEX-17.1-01", "ubr_by_birth", bad, "every person received food, shelter and connectivity", "{n} persons without the full UBR"))
        out.append(v("LABOR-4.1-02", "baseline_not_contingent", bad, "survival access did not depend on activity", "{n} persons lost baseline access"))
        passive = [p for p, x in ub.items() if x["activity"] == "none"]
        bad = [p for p, x in ub.items() if (x["additional_benefits_rating"] == "reduced") != (x["activity"] == "none")]
        out.append(v("CODEX-18.1-01", "contribution_obligation", [p for p, x in ub.items() if x["activity"] not in ACTIVITIES + ("none",)],
                     f"{len(ub) - len(passive)} of {len(ub)} UBR recipients take part in education, creativity or socially useful activity",
                     "{n} activities outside §18.1"))
        out.append(v("CODEX-18.1-02", "passivity_rating", bad, f"total passivity reduced the rating for additional benefits ({len(passive)} persons)",
                     "{n} ratings against §18.1"))
        if passive:
            for rid, chk, txt in (("PRIVACY-10-01", "no_social_credit_scoring", "social credit scoring and behavioral profiling are forbidden"),
                                  ("LABOR-9.1-02", "refusal_not_punished", "refusal of participation does not trigger punishment")):
                out.append(unk(rid, chk, f"{len(passive)} persons received a reduced rating for total passivity (Code §18.1); {txt}: "
                               "whether that rating is such a practice is not said (F-033)"))
        else:
            for rid, chk in (("PRIVACY-10-01", "no_social_credit_scoring"), ("LABOR-9.1-02", "refusal_not_punished")):
                out.append(na(rid, chk, "passivity ratings", "no person is totally passive"))
    return out


IMPLEMENTS = {
    "CODEX-1.1-01": ("two_circuits", "PARTIAL", "Classification only; 'independent' is not defined."),
    "CODEX-1.2-01": ("mirror_peg_anchor", "PARTIAL", "The anchor is computed; the peg function and 'developed nations' are not defined."),
    "CODEX-1.3-01": ("venture_gateway", "PARTIAL", "The 5 years run from the development (H-CE-2)."),
    "CODEX-2.1-01": ("targeted_smart_contracts", "PARTIAL", "Channel and target are declared."),
    "CODEX-2.2-01": ("tranche_on_verified_kpi", "PARTIAL", "KPI verification is a declared month."),
    "CODEX-3.1-01": ("export_requires_participation", "PARTIAL", "Participation is a declared flag."),
    "CODEX-3.2-01": ("equity_tokens", "PARTIAL", "The token share is not given (source missing)."),
    "CODEX-4.1-01": ("public_domain_after_5_years", "IMPLEMENTED", None),
    "CODEX-5.1-01": ("ai_exam_recognition", "PARTIAL", "The standard and the exam are not defined."),
    "CODEX-6.1-01": ("absolute_exit", "IMPLEMENTED", None),
    "CODEX-6.1-02": ("relocation_costs", "PARTIAL", "'Depressed zone' is a declared flag."),
    "CODEX-6.2-01": ("lease_fee", "PARTIAL", "The fee amount is not given (source missing)."),
    "CODEX-6.3-01": ("post_factum", "PARTIAL", "Success is a declared number of months."),
    "CODEX-6.4-01": ("education_fund", "IMPLEMENTED", None),
    "CODEX-9.1-01": ("no_irremovable_power", "PARTIAL", "Irremovability is a declared flag."),
    "CODEX-9.2-01": ("kpi_contract", "IMPLEMENTED", None),
    "CODEX-10.1-01": ("glass_pocket", "PARTIAL", "'Real-time' = the month of booking (H-CE-5)."),
    "CODEX-11.1-01": ("covert_lobbying", "PARTIAL", "Covertness is a declared flag."),
    "CODEX-12.1-01": ("full_product_cost", "PARTIAL", "Disposal and restoration costs are declared."),
    "AXIOMS-AxiomA5-ExternalityAccountability-03": ("externalities_in_cost", "PARTIAL", "Same check as Code §12.1."),
    "CODEX-13.1-01": ("reserve_share", "IMPLEMENTED", None),
    "CODEX-13.2-01": ("invisible_extraction", "PARTIAL", "Listed methods only; no surface-integrity test."),
    "CODEX-13.3-01": ("sensor_income", "PARTIAL", "The income function is not given (source missing)."),
    "CODEX-14.1-01": ("statements_verified", "PARTIAL", "Routing to validators only."),
    "CODEX-14.2-01": ("quadratic_cost", "IMPLEMENTED", None),
    "IDENTITY-6-02": ("coordinated_identities_one_subject", "PARTIAL", "Coordination is a declared flag."),
    "CODEX-14.3-01": ("field_weight", "PARTIAL", "EigenTrust values are declared."),
    "CODEX-15.1-01": ("open_algorithms", "PARTIAL", "Domains are declared."),
    "CODEX-16.1-01": ("personal_assets_heritable", "IMPLEMENTED", None),
    "CODEX-16.1-02": ("no_infrastructure_inheritance", "PARTIAL", "Destination of infrastructure capital outside ultra-large estates is not defined."),
    "CODEX-16.1-03": ("ultra_large_return", "PARTIAL", "Threshold not given (source missing); whole fortune (H-CE-8)."),
    "CODEX-17.1-01": ("ubr_by_birth", "PARTIAL", "Quantities are not given."),
    "LABOR-4.1-02": ("baseline_not_contingent", "PARTIAL", "UBR stands for the baseline."),
    "CODEX-18.1-01": ("contribution_obligation", "PARTIAL", "Activities are declared."),
    "CODEX-18.1-02": ("passivity_rating", "PARTIAL", "The rating scale is not given; relation to PRIVACY and LABOR: F-033."),
    "PRIVACY-10-01": ("no_social_credit_scoring", "PARTIAL", "Only the Code's passivity rating is examined (F-033)."),
    "LABOR-9.1-02": ("refusal_not_punished", "PARTIAL", "Only the Code's passivity rating is examined (F-033)."),
}

_ID = re.compile(r"[a-z0-9][a-z0-9_]{0,23}")
COUNTRIES = [{"id": i, "gdp_per_capita": g, "developed": dev, "growth": [gr] * 12}
             for i, g, dev, gr in (("c1", 900.0, False, 0.004), ("c2", 1500.0, False, 0.003), ("c3", 4000.0, False, 0.002),
                                   ("c4", 9000.0, False, 0.002), ("c5", 20000.0, True, 0.001), ("c6", 30000.0, True, 0.001),
                                   ("c7", 45000.0, True, 0.0015), ("c8", 60000.0, True, 0.001))]
COUNTRIES[0]["growth"] = [0.004] * 5 + [-0.002] + [0.004] * 6


def _obj(fields, default=None):
    spec = {"type": "object", "fields": fields}
    if default is not None:
        spec["default"] = default
    return spec


def _lst(fields, default, label, source="user", mx=20):
    return {"type": "list", "min_items": 0, "max_items": mx, "items": _obj(fields), "default": default, "source": source, "label": label}


S, N, B, I = {"type": "str"}, {"type": "number", "min": 0, "max": 10 ** 12}, {"type": "bool"}, {"type": "int", "min": -1, "max": 600}


class CodeEconomyModule(LabModule):
    id = "code_economy"
    version = "1.0.0"
    title = {"en": "Code of Planetary Synergy: economy and society (§1-§6, §9-§18)",
             "ru": "Кодекс планетарной синергии: экономика и общество (§1-§6, §9-§18)"}
    summary = {"en": "Pegs, tranches, exports, patents, talent leases, Operators, budgets, reserves, vote buying, inheritance and UBR: "
                     "does each rule of the Code hold, and where does the Code meet DKP's limits on scoring and compulsion?",
               "ru": "Привязки, транши, экспорт, патенты, аренда талантов, операторы, бюджеты, заповедники, покупка голосов, "
                     "наследование и БОР: выполняется ли каждое правило Кодекса и где Кодекс встречает запреты DKP на рейтинги и принуждение?"}
    protocols = ["CODE-OF-PLANETARY-SYNERGY", "DKP-1-AXIOMS-001", "DKP-1-IDENTITY-001", "DKP-2-LABOR-001", "DKP-7-PRIVACY-001"]
    example_order = ["reference_economy", "no_passive_persons", "faulty_economy"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_code_economy_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-CE-1", "source": "hypothesis", "text": {
            "en": "Bottom quintile = the ceil(20%) countries with the lowest declared GDP per capita; their growth is averaged without "
                  "weights; the 5-year window is 60 monthly values of yearly growth rates. The peg function is not defined: only the "
                  "anchor is computed.",
            "ru": "Нижний квинтиль = ceil(20%) стран с наименьшим ВВП на душу; рост усредняется без весов; окно 5 лет — 60 месячных "
                  "значений годовых темпов. Функция привязки не определена: вычисляется только ориентир."}},
        {"id": "H-CE-2", "source": "hypothesis", "text": {
            "en": "§1.3: the 5 years run from the month a pledged development is created (§4.1 counts from patent registration).",
            "ru": "§1.3: 5 лет отсчитываются с месяца создания разработки (§4.1 считает от регистрации патента)."}},
        {"id": "H-CE-3", "source": "hypothesis", "text": {
            "en": "Lease Fee: paid every 12 months from the end of the first year of successful work while the work continues.",
            "ru": "Арендная плата: каждые 12 месяцев с конца первого года успешной работы, пока работа продолжается."}},
        {"id": "H-CE-4", "source": "hypothesis", "text": {
            "en": "Vote buying: Cost = Votes² per Subject; identities that coordinate are one Subject (IDENTITY §6).",
            "ru": "Покупка голосов: стоимость = голоса² на субъекта; согласованные идентичности — один субъект (IDENTITY §6)."}},
        {"id": "H-CE-5", "source": "hypothesis", "text": {
            "en": "'Real-time' publication: in the month the transaction is booked.",
            "ru": "Публикация 'в реальном времени': в месяц проводки."}},
        {"id": "H-CE-6", "source": "hypothesis", "text": {
            "en": "Reserve share: exactly 40% passes, less fails, more is UNKNOWN (exact share or minimum is not said).",
            "ru": "Доля заповедников: ровно 40% — PASS, меньше — FAIL, больше — UNKNOWN (точная доля или минимум — не сказано)."}},
        {"id": "H-CE-7", "source": "hypothesis", "text": {
            "en": "Biosphere Operator income = declared linear function of biomass index, CO2 reduction and biodiversity.",
            "ru": "Доход биосферного оператора = объявленная линейная функция индекса биомассы, снижения CO2 и биоразнообразия."}},
        {"id": "H-CE-8", "source": "hypothesis", "text": {
            "en": "An ultra-large fortune (declared threshold) returns whole to the Global Development Fund; the title says "
                  "'Progressive Inheritance Tax' but the article gives no rate.",
            "ru": "Сверхкрупное состояние (объявленный порог) целиком возвращается в Глобальный фонд развития; заголовок говорит о "
                  "'прогрессивном налоге', но ставки нет."}},
    ]
    inputs = {
        "months": {"type": "int", "min": 12, "max": 240, "default": 84, "unit": "month", "source": "user",
                   "label": {"en": "Months simulated", "ru": "Месяцев моделирования"}},
        "countries": {"type": "list", "min_items": 1, "max_items": 30, "source": "user",
                      "label": {"en": "Countries (GDP per capita, yearly growth from 5 years before month 0)",
                                "ru": "Страны (ВВП на душу, годовой рост с 5 лет до месяца 0)"},
                      "items": _obj({"id": S, "gdp_per_capita": N, "developed": {"type": "bool", "default": False},
                                     "growth": {"type": "list", "min_items": 1, "max_items": 30,
                                                "items": {"type": "number", "min": -1, "max": 1}}}),
                      "default": COUNTRIES},
        "assets": _lst({"id": S, "circuit": {"type": "enum", "values": ["basic", "venture", "unclassified"]}},
                       [{"id": "farmland", "circuit": "basic"}, {"id": "fusion_lab", "circuit": "venture"}],
                       {"en": "Assets by circuit", "ru": "Активы по контурам"}),
        "venture": _lst({"id": S, "pledge": B, "developments": {"type": "list", "min_items": 0, "max_items": 10, "default": [],
                                                                 "items": {"type": "int", "min": 0, "max": 600}}},
                        [{"id": "orbit_fund", "pledge": True, "developments": [6]}, {"id": "dark_fund", "pledge": False, "developments": [0]}],
                        {"en": "Venture funds", "ru": "Венчурные фонды"}),
        "tranches": _lst({"id": S, "channel": {"type": "enum", "values": ["smart_contract", "manual"]},
                          "targeted": {"type": "bool", "default": True}, "kpi_verified_month": I, "amount": N},
                         [{"id": "school_t1", "channel": "smart_contract", "kpi_verified_month": 10, "amount": 5.0},
                          {"id": "clinic_t1", "channel": "smart_contract", "kpi_verified_month": -1, "amount": 3.0},
                          {"id": "road_cash", "channel": "manual", "kpi_verified_month": 4, "amount": 2.0}],
                         {"en": "Fund tranches (KPI verified in month, -1 = not yet)", "ru": "Транши (KPI подтверждён в месяц, -1 = нет)"}),
        "exports": _lst({"id": S, "exporter": S, "resource": S, "participates": B,
                         "processors": {"type": "list", "min_items": 0, "max_items": 10, "items": S, "default": []}},
                        [{"id": "x1", "exporter": "c1", "resource": "cobalt", "participates": True, "processors": ["cell_plant", "ev_plant"]},
                         {"id": "x2", "exporter": "c2", "resource": "timber", "participates": False, "processors": ["mill"]}],
                        {"en": "Raw-material exports", "ru": "Экспорт сырья"}),
        "equity_share": {"type": "number", "min": 0, "max": 1, "default": 0.05, "source": "missing",
                         "label": {"en": "Equity token share per processor (§3.2)", "ru": "Доля токенов на переработчика (§3.2)"}},
        "patents": _lst({"id": S, "life_support": B, "venture": B, "registered_month": {"type": "int", "min": -600, "max": 600}},
                        [{"id": "water_filter", "life_support": True, "venture": False, "registered_month": -12},
                         {"id": "game_engine", "life_support": False, "venture": False, "registered_month": 0}],
                        {"en": "Patents", "ru": "Патенты"}),
        "diplomas": _lst({"person": S, "passed_ai_exam": B},
                         [{"person": "p1", "passed_ai_exam": True}, {"person": "p2", "passed_ai_exam": False}],
                         {"en": "Diplomas", "ru": "Дипломы"}),
        "relocations": _lst({"person": S, "donor": S, "recipient": S, "month": {"type": "int", "min": 0, "max": 600},
                             "depressed_zone": B, "successful_months": {"type": "int", "min": 0, "max": 600}},
                            [{"person": "eng1", "donor": "c1", "recipient": "c7", "month": 2, "depressed_zone": True, "successful_months": 40},
                             {"person": "doc2", "donor": "c3", "recipient": "c6", "month": 5, "depressed_zone": False, "successful_months": 8}],
                            {"en": "Relocating specialists", "ru": "Переезжающие специалисты"}),
        "lease_fee": {"type": "number", "min": 0, "max": 10 ** 9, "default": 1.0, "source": "missing",
                      "label": {"en": "Annual Lease Fee (§6.2)", "ru": "Годовая арендная плата (§6.2)"}},
        "operators": _lst({"region": S, "start_month": {"type": "int", "min": 0, "max": 600}, "kpi_months": {"type": "int", "min": 1, "max": 600},
                           "kpi_target": N, "kpi_achieved": N, "irremovable": {"type": "bool", "default": False}},
                          [{"region": "delta", "start_month": 0, "kpi_months": 24, "kpi_target": 100.0, "kpi_achieved": 120.0},
                           {"region": "gamma", "start_month": 0, "kpi_months": 24, "kpi_target": 100.0, "kpi_achieved": 60.0},
                           {"region": "omega", "start_month": 0, "kpi_months": 24, "kpi_target": 1.0, "kpi_achieved": 1.0, "irremovable": True}],
                          {"en": "Regional Operators", "ru": "Региональные операторы"}),
        "budget": _lst({"id": S, "month": {"type": "int", "min": 0, "max": 600}, "secret": {"type": "bool", "default": False}},
                       [{"id": "b1", "month": 3}, {"id": "b2", "month": 7}, {"id": "b3", "month": 9, "secret": True}],
                       {"en": "Budget transactions", "ru": "Бюджетные операции"}),
        "lobbying": _lst({"id": S, "covert": B}, [{"id": "l1", "covert": True}, {"id": "l2", "covert": False}],
                         {"en": "Contacts of private capital with legislative algorithms or Operators", "ru": "Контакты частного капитала"}),
        "goods": _lst({"id": S, "base_cost": N, "disposal_cost": N, "restoration_cost": N},
                      [{"id": "phone", "base_cost": 100.0, "disposal_cost": 8.0, "restoration_cost": 12.0}],
                      {"en": "Goods (costs)", "ru": "Товары (издержки)"}),
        "land": _obj({"total_km2": {"type": "number", "min": 1, "max": 10 ** 9}, "reserve_km2": N},
                     {"total_km2": 1000.0, "reserve_km2": 400.0}) | {"source": "user", "label": {"en": "Land", "ru": "Суша"}},
        "extraction_permits": _lst({"site": S, "in_reserve": B,
                                    "method": {"type": "enum", "values": list(RESERVE_METHODS) + list(PROHIBITED_METHODS) + ["other"]}},
                                   [{"site": "s1", "in_reserve": True, "method": "robotized_tunnel"},
                                    {"site": "s2", "in_reserve": True, "method": "open_pit"},
                                    {"site": "s3", "in_reserve": False, "method": "open_pit"}],
                                   {"en": "Extraction permits", "ru": "Разрешения на добычу"}),
        "operator_income_weights": _obj({"biomass": N, "co2": N, "biodiversity": N}, {"biomass": 1.0, "co2": 1.0, "biodiversity": 1.0})
        | {"source": "missing", "label": {"en": "Biosphere Operator income weights (§13.3)", "ru": "Веса дохода биосферного оператора (§13.3)"}},
        "reserve_residents": _lst({"person": S, "biomass": N, "co2_reduction": N, "biodiversity": N, "declared_income": N},
                                  [{"person": "r1", "biomass": 0.8, "co2_reduction": 0.3, "biodiversity": 0.6, "declared_income": 5.0}],
                                  {"en": "Reserve residents (sensor data)", "ru": "Жители заповедников (данные датчиков)"}),
        "statements": {"type": "list", "min_items": 0, "max_items": 20, "items": S, "default": ["minister_speech_1"], "source": "user",
                       "label": {"en": "Public statements of officials", "ru": "Публичные заявления должностных лиц"}},
        "vote_buying": _obj({"votes": {"type": "number", "min": 1, "max": 10 ** 6}, "identities": {"type": "int", "min": 1, "max": 10 ** 4},
                             "coordinated": B}, {"votes": 100.0, "identities": 10, "coordinated": True})
        | {"source": "user", "label": {"en": "Vote-buying attempt", "ru": "Попытка купить голоса"}},
        "validators": _lst({"id": S, "field": S, "field_reputation": {"type": "number", "min": 0, "max": 1},
                            "overall_reputation": {"type": "number", "min": 0, "max": 1}},
                           [{"id": "v1", "field": "climate", "field_reputation": 0.9, "overall_reputation": 0.4}],
                           {"en": "Validators (declared EigenTrust)", "ru": "Валидаторы (объявленный EigenTrust)"}),
        "algorithms": _lst({"id": S, "domain": {"type": "enum", "values": list(OPEN_SOURCE_DOMAINS) + ["other"]}, "open_source": B},
                           [{"id": "alloc", "domain": "resource_allocation", "open_source": True},
                            {"id": "feed_x", "domain": "news_feed", "open_source": False},
                            {"id": "game_ai", "domain": "other", "open_source": False}],
                           {"en": "Algorithms", "ru": "Алгоритмы"}),
        "ultra_large_threshold": {"type": "number", "min": 0, "max": 10 ** 12, "default": 1000.0, "source": "missing",
                                  "label": {"en": "Ultra-large fortune threshold (§16.1)", "ru": "Порог сверхкрупного состояния (§16.1)"}},
        "estates": _lst({"owner": S, "personal": N, "infrastructure": N, "death_month": {"type": "int", "min": 0, "max": 600}},
                        [{"owner": "o1", "personal": 50.0, "infrastructure": 20.0, "death_month": 30},
                         {"owner": "o2", "personal": 900.0, "infrastructure": 400.0, "death_month": 40}],
                        {"en": "Estates", "ru": "Наследства"}),
        "persons": _lst({"person": S, "activity": {"type": "enum", "values": list(ACTIVITIES) + ["none"]}},
                        [{"person": "u1", "activity": "education"}, {"person": "u2", "activity": "socially_useful"},
                         {"person": "u3", "activity": "none"}],
                        {"en": "UBR recipients and their activity", "ru": "Получатели БОР и их занятия"}),
        "faults": {"type": "list", "min_items": 0, "max_items": len(FAULTS), "items": {"type": "enum", "values": list(FAULTS)},
                   "default": [], "source": "user",
                   "label": {"en": "Deliberate faults (counterexamples)", "ru": "Намеренные ошибки (контрпримеры)"},
                   "help": {"en": "; ".join(f"{k}: {v}" for k, v in FAULTS.items()),
                            "ru": "Каждая ошибка отключает одно правило, чтобы показать, что проверка её ловит."}},
    }

    def validate(self, value: Dict[str, Any]) -> Dict[str, Any]:
        r = super().validate(value)
        p = []
        years = 5 + math.ceil(r["months"] / 12)
        for c in r["countries"]:
            if len(c["growth"]) < years:
                p.append(f"input.countries: {c['id']} needs {years} yearly growth values (5 years of history + the horizon)")
        ids = [c["id"] for c in r["countries"]]
        names = ids + [x["id"] for x in r["assets"]] + [x["person"] for x in r["persons"]] + [x["owner"] for x in r["estates"]] + \
            [x["region"] for x in r["operators"]] + [x["id"] for x in r["tranches"]] + r["statements"]
        for x in names:
            if not _ID.fullmatch(x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        for key, col in (("countries", ids), ("persons", [x["person"] for x in r["persons"]]),
                         ("relocations", [x["person"] for x in r["relocations"]]), ("tranches", [x["id"] for x in r["tranches"]]),
                         ("operators", [x["region"] for x in r["operators"]]), ("estates", [x["owner"] for x in r["estates"]]),
                         ("budget", [x["id"] for x in r["budget"]]), ("patents", [x["id"] for x in r["patents"]]),
                         ("diplomas", [x["person"] for x in r["diplomas"]]), ("validators", [x["id"] for x in r["validators"]]),
                         ("algorithms", [x["id"] for x in r["algorithms"]]), ("exports", [x["id"] for x in r["exports"]]),
                         ("venture", [x["id"] for x in r["venture"]]), ("lobbying", [x["id"] for x in r["lobbying"]]),
                         ("extraction_permits", [x["site"] for x in r["extraction_permits"]]),
                         ("reserve_residents", [x["person"] for x in r["reserve_residents"]]), ("goods", [x["id"] for x in r["goods"]])):
            if len(set(col)) != len(col):
                p.append(f"input.{key}: repeated id")
        for x in r["relocations"]:
            if x["donor"] not in ids or x["recipient"] not in ids or x["donor"] == x["recipient"]:
                p.append(f"input.relocations: {x['person']} needs two different declared countries")
        for x in r["exports"]:
            if x["exporter"] not in ids:
                p.append(f"input.exports: unknown exporter {x['exporter']!r}")
        if r["land"]["reserve_km2"] > r["land"]["total_km2"]:
            p.append("input.land: reserve larger than the land")
        if r["vote_buying"]["identities"] > r["vote_buying"]["votes"]:
            p.append("input.vote_buying: more identities than votes")
        if any(e["death_month"] >= r["months"] for e in r["estates"]):
            p.append("input.estates: death beyond the horizon")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        outputs = {"decisions": [{"month": m.arrived_at, "source": m.source, **{k: x for k, x in m.value.items() if k != "anchor"}}
                                 for m in msgs],
                   "peg_anchor": [m.value["anchor"] for m in msgs if m.source == "PEG"][0],
                   "violations": sorted(c.requirement_id for c in res if c.status == FAIL),
                   "unknown": sorted(c.requirement_id for c in res if c.status == UNKNOWN),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": f"{len(log)} decisions; violated: {', '.join(outputs['violations']) or 'none'}; undecided: "
                    f"{', '.join(outputs['unknown']) or 'none'}.",
              "ru": f"{len(log)} решений; нарушены: {', '.join(outputs['violations']) or 'нет'}; не решено: "
                    f"{', '.join(outputs['unknown']) or 'нет'}."}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"violations": len(outputs["violations"]), "unknown": len(outputs["unknown"]),
                "peg_anchor_last": outputs["peg_anchor"][-1]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "reference_economy": {},
            "no_passive_persons": {"persons": [{"person": "u1", "activity": "education"}, {"person": "u2", "activity": "creativity"}]},
            "reserve_above_40_percent": {"land": {"total_km2": 1000.0, "reserve_km2": 450.0}},
            "unlisted_extraction_method": {"extraction_permits": [{"site": "s4", "in_reserve": True, "method": "other"}]},
            "uncoordinated_buyers": {"vote_buying": {"votes": 100.0, "identities": 10, "coordinated": False}},
            "faulty_economy": {"faults": ["unlock_before_kpi", "pay_to_budget", "allow_secret", "per_identity_cost", "ubr_conditional"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"short_growth_history": {"countries": [{"id": "c1", "gdp_per_capita": 1.0, "growth": [0.01] * 3}]},
                "reserve_larger_than_land": {"land": {"total_km2": 10.0, "reserve_km2": 20.0}},
                "unknown_exporter": {"exports": [{"id": "x", "exporter": "zz", "resource": "ore", "participates": True}]},
                "same_donor_and_recipient": {"relocations": [{"person": "a", "donor": "c1", "recipient": "c1", "month": 0,
                                                              "depressed_zone": False, "successful_months": 0}]}}


def _resolve_defaults(inputs: Dict[str, Dict[str, Any]]) -> None:
    """The schema copies defaults as written; nested defaults are filled here once, so every default is complete."""
    for spec in inputs.values():
        if spec["type"] == "list" and spec["items"]["type"] == "object":
            spec["default"] = [resolve(x, spec["items"]["fields"]) for x in spec["default"]]
        elif spec["type"] == "object":
            spec["default"] = resolve(spec["default"], spec["fields"])


_resolve_defaults(CodeEconomyModule.inputs)
