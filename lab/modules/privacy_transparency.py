"""
PRIVACY AND TRANSPARENCY module — DKP-7-PRIVACY-001 and DKP-7-TRANSPARENCY-001 on data requests.

Each request asks to publish or process data of one domain at one level (aggregate, anonymized,
individual) for one purpose.  The reference gatekeeper applies both protocols:

  * public by default (TRANSPARENCY §5): protocol texts, governance logic, system metrics, state
    transitions — at structural and aggregate level only;
  * absolute privacy domains (PRIVACY §6): medical/biological, mental, intimate, beliefs, private
    communications — never at the individual level, never for audit;
  * conditional domains (PRIVACY §7): economic, resources, mobility, education, platform — anonymized or
    aggregated; individual level only when triggered by higher-layer enforcement within Scope and, for
    the identity link, only under TRANSPARENCY §8 (PTL-verified material harm, attribution required, no
    anonymous path), minimal, time-bound, auditable, case-bound;
  * audit (PRIVACY §9): anonymized data, zero-knowledge verification, no raw personal data;
  * forbidden (PRIVACY §10, TRANSPARENCY §9): mass surveillance, profiling, scoring, cross-domain identity
    correlation, forced transparency as punishment, social control; convenience never justifies erosion;
  * crisis (PRIVACY §11, TRANSPARENCY §10): anonymity reduced only inside a bounded Crisis Scope for direct
    life preservation — temporary, logged, reversible, ending with the Crisis; action transparency rises,
    identity exposure does not by default;
  * every decision explains itself with protocol references (TRANSPARENCY §11) and leaves an audit hook (§12).

Not settled by the text (H-PT-2, finding F-026): may *aggregate* statistics of an absolute privacy domain
be published?  §6 says the domains "SHALL ALWAYS remain private and non-public" and are "non-auditable at
the individual level".  Such requests are decided by the declared reading and reported UNKNOWN.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError

ABSOLUTE = ("medical", "mental", "intimate", "beliefs", "private_comms")
CONDITIONAL = ("economic", "resources", "mobility", "education", "platform")
PUBLIC = ("protocol_text", "governance_logic", "system_metrics", "state_transitions")
DOMAINS = ABSOLUTE + CONDITIONAL + PUBLIC + ("identity",)
PURPOSES = ("publication", "audit", "enforcement", "crisis_life_preservation", "analytics", "profiling", "scoring",
            "punishment")
FORBIDDEN_PURPOSES = ("profiling", "scoring", "punishment")
FAULTS = {
    "release_absolute_individual": "individual medical or belief data is released",
    "audit_raw_data": "an audit reads raw personal data",
    "deanonymize_without_harm": "a Subject is de-anonymized without PTL-verified harm",
    "deanonymize_propagate": "a de-anonymization is reused beyond its case and has no time bound",
    "correlate_domains": "datasets of several domains are linked to one identity",
    "profiling_granted": "a profiling request is granted",
    "convenience_override": "individual data is processed for analytics",
    "crisis_permanent": "a crisis anonymity reduction does not end with the Crisis",
    "crisis_identity_by_default": "identity exposure is raised by default during a Crisis",
    "hide_public_domain": "governance logic is withheld",
    "identity_required": "participation is refused without identity disclosure",
    "anonymous_fewer_rights": "anonymous participants lose access to a system function",
    "unexplained_decision": "a decision is given without reason or protocol reference",
    "no_audit_hook": "a decision leaves no audit hook",
    "audit_without_zk": "an audit verifies by comparing full datasets instead of zero-knowledge proofs",
    "breach_downgraded": "a request for a prohibited practice is recorded as a mere policy deviation",
}
REQUEST = {"type": "object", "fields": {
    "id": {"type": "str"},
    "domain": {"type": "enum", "values": list(DOMAINS)},
    "level": {"type": "enum", "values": ["aggregate", "anonymized", "individual"], "default": "aggregate"},
    "purpose": {"type": "enum", "values": list(PURPOSES), "default": "publication"},
    "linked_domains": {"type": "list", "min_items": 0, "max_items": 10, "items": {"type": "enum", "values": list(DOMAINS)},
                       "default": []},
    "harm_verified": {"type": "bool", "default": False},
    "attribution_required": {"type": "bool", "default": False},
    "anonymous_path": {"type": "bool", "default": True},
    "scope_trigger": {"type": "bool", "default": False},
    "in_crisis_scope": {"type": "bool", "default": False}}}


def full(**kw) -> Dict[str, Any]:
    """A request with every declared default filled in (list defaults are not resolved by the schema)."""
    return {**{k: f["default"] for k, f in REQUEST["fields"].items() if "default" in f}, **kw}


def decide(q: Dict[str, Any], absolute_aggregate: str) -> Dict[str, Any]:
    """Reference decision for one request (independent of the generator's faults)."""
    d, lvl, p = q["domain"], q["level"], q["purpose"]
    refs: List[str] = []
    if p in FORBIDDEN_PURPOSES:
        return {"grant": False, "reason": f"{p} is forbidden", "refs": ["PRIVACY §10", "TRANSPARENCY §9"]}
    if q["linked_domains"]:
        return {"grant": False, "reason": "cross-domain identity correlation", "refs": ["PRIVACY §4.3, §10", "TRANSPARENCY §9"]}
    if p == "analytics" and lvl == "individual":
        return {"grant": False, "reason": "analytical value does not justify privacy erosion", "refs": ["PRIVACY §4.4"]}
    if d in PUBLIC:
        if lvl == "individual":
            return {"grant": False, "reason": "public transparency is structural and aggregate only", "refs": ["TRANSPARENCY §5"]}
        return {"grant": True, "reason": "public by default", "refs": ["TRANSPARENCY §5"]}
    if p == "audit":
        if lvl == "individual":
            return {"grant": False, "reason": "audit uses anonymized data and zero-knowledge proofs", "refs": ["PRIVACY §9"]}
        if d in ABSOLUTE:
            return {"grant": False, "reason": "absolute domains are non-auditable at the individual level", "refs": ["PRIVACY §6, §9"]}
        return {"grant": True, "reason": "anonymized audit with zero-knowledge verification", "refs": ["PRIVACY §9", "TRANSPARENCY §12"]}
    if d in ABSOLUTE:
        if lvl == "individual":
            return {"grant": False, "reason": "absolute privacy domain", "refs": ["PRIVACY §6"]}
        ok = absolute_aggregate == "aggregate_allowed"
        return {"grant": ok, "reason": "aggregate of an absolute domain (reading " + absolute_aggregate + ", F-026)",
                "refs": ["PRIVACY §6"], "unsettled": True}
    if p == "crisis_life_preservation" and lvl == "individual":
        ok = q["in_crisis_scope"]
        return {"grant": ok, "reason": "anonymity reduced inside the Crisis Scope for life preservation" if ok
                else "no declared Crisis Scope", "refs": ["PRIVACY §11", "TRANSPARENCY §10"], "crisis": ok}
    if lvl == "individual":
        ok = q["scope_trigger"] and q["harm_verified"] and q["attribution_required"] and not q["anonymous_path"]
        return {"grant": ok, "reason": "conditional de-anonymization" if ok else "individual disclosure without the §8 conditions",
                "refs": ["PRIVACY §7", "TRANSPARENCY §8"], "deanonymization": ok}
    return {"grant": True, "reason": "anonymized or aggregate exposure of a conditional domain", "refs": ["PRIVACY §7"]}


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("request", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    for k, q in enumerate(r["requests"]):
        o = put("observation", "REQUEST", k, {"request": q["id"], **{f: q[f] for f in q if f != "id"}})
        dec = decide(q, r["absolute_aggregate_reading"])
        if "release_absolute_individual" in faults and q["domain"] in ABSOLUTE and q["level"] == "individual":
            dec = {**dec, "grant": True, "reason": "released"}
        if "audit_raw_data" in faults and q["purpose"] == "audit":
            dec = {**dec, "grant": True, "raw_data": True}
        if "deanonymize_without_harm" in faults and q["level"] == "individual" and q["domain"] in CONDITIONAL + ("identity",):
            dec = {**dec, "grant": True, "deanonymization": True}
        if "correlate_domains" in faults and q["linked_domains"]:
            dec = {**dec, "grant": True}
        if "profiling_granted" in faults and q["purpose"] == "profiling":
            dec = {**dec, "grant": True}
        if "convenience_override" in faults and q["purpose"] == "analytics" and q["level"] == "individual":
            dec = {**dec, "grant": True}
        if "hide_public_domain" in faults and q["domain"] == "governance_logic":
            dec = {**dec, "grant": False, "reason": "withheld"}
        v = {"request": q["id"], "grant": dec["grant"], "reason": dec["reason"], "protocol_refs": dec["refs"],
             "audit_hook": True, "level": q["level"], "domain": q["domain"]}
        if "unexplained_decision" in faults and k == 0:
            v.pop("reason")
            v.pop("protocol_refs")
        if "no_audit_hook" in faults and k == 0:
            v["audit_hook"] = False
        if dec.get("raw_data"):
            v["raw_personal_data"] = True
        if dec.get("deanonymization") and dec["grant"]:
            v.update({"minimal": True, "time_bound_until": k + 30, "case_bound": q["id"]})
            if "deanonymize_propagate" in faults:
                v.update({"time_bound_until": None, "case_bound": None})
        if dec.get("crisis") and dec["grant"]:
            v.update({"temporary": True, "logged": True, "reversible": True, "ends_with_crisis": "crisis_permanent" not in faults})
        if q["purpose"] == "audit" and v["grant"]:                                                   # PRIVACY §9
            v["verification"] = "full data comparison" if "audit_without_zk" in faults else "zero-knowledge proof"
        if q["purpose"] in FORBIDDEN_PURPOSES or q["linked_domains"]:                                  # PRIVACY §10
            v["classification"] = "policy deviation" if "breach_downgraded" in faults else                 "critical system integrity breach" + ("" if v["grant"] else " (attempted)")
        put("decision", "PRIVACY", k, v, [o.event_id])
    k = len(r["requests"])
    if r["crisis_scope_active"]:
        put("notice", "TRANSPARENCY", k, {"crisis_scope": True, "action_transparency": "increased",
                                          "identity_exposure": "increased" if "crisis_identity_by_default" in faults else "unchanged",
                                          "emergency_log": True})
    part = r["participants"]
    put("action", "PARTICIPATION", k, {"anonymous_participants": part["anonymous"], "identified_participants": part["identified"],
                                        "identity_required": "identity_required" in faults,
                                        "functions_for_anonymous": "reduced" if "anonymous_fewer_rights" in faults else "full"})
    put("notice", "PRIVACY", k, {"rules_published": True, "thresholds_published": True,
                                 "subject_verifiable": True, "re_identification_threshold": r["reidentification_k"]})
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

    reqs = {q["id"]: q for q in r["requests"]}
    decs = {m.value["request"]: m for m in msgs if m.source == "PRIVACY" and m.kind == "decision"}
    exp = {qid: decide(q, r["absolute_aggregate_reading"]) for qid, q in reqs.items()}
    unsettled = [qid for qid, e in exp.items() if e.get("unsettled")]

    def against(pred):
        return [qid for qid, q in reqs.items() if pred(q) and decs[qid].value["grant"] != exp[qid]["grant"]]

    def applies(pred):
        return any(pred(q) for q in reqs.values())

    groups = [
        (("PRIVACY-6-01", "PRIVACY-6-02", "TRANSPARENCY-3-03"), "absolute_domains",
         lambda q: q["domain"] in ABSOLUTE and q["level"] == "individual", "absolute privacy domains never released individually"),
        (("PRIVACY-7-01", "PRIVACY-7-02"), "conditional_domains",
         lambda q: q["domain"] in CONDITIONAL and q["purpose"] not in ("audit",) + FORBIDDEN_PURPOSES and not q["linked_domains"],
         "conditional domains exposed only anonymized/aggregated, individually only under the Scope and §8 conditions"),
        (("TRANSPARENCY-8-01", "TRANSPARENCY-6-02", "TRANSPARENCY-7-02"), "deanonymization_conditions",
         lambda q: q["level"] == "individual" and q["domain"] in CONDITIONAL + ("identity",) and q["purpose"] in ("enforcement", "publication"),
         "de-anonymization only with PTL-verified harm, required attribution and no anonymous path"),
        (("PRIVACY-9-01", "PRIVACY-9-03", "PRIVACY-9-04", "TRANSPARENCY-12-04"), "audit_without_personal_data",
         lambda q: q["purpose"] == "audit", "audits on anonymized data with zero-knowledge proofs, no raw personal data"),
        (("PRIVACY-10-01", "TRANSPARENCY-9-02", "TRANSPARENCY-9-03"), "prohibited_purposes",
         lambda q: q["purpose"] in FORBIDDEN_PURPOSES, "profiling, scoring and forced transparency refused"),
        (("PRIVACY-4.3-01", "TRANSPARENCY-9-04", "PRIVACY-4.1-02"), "no_cross_domain_linkage",
         lambda q: bool(q["linked_domains"]), "no linking of datasets across domains to an identity"),
        (("PRIVACY-4.4-01", "PRIVACY-4.2-01"), "no_convenience_erosion",
         lambda q: q["purpose"] == "analytics" and q["level"] == "individual", "analytical value never justified individual data"),
        (("TRANSPARENCY-5-01", "TRANSPARENCY-5-02"), "public_by_default",
         lambda q: q["domain"] in PUBLIC, "protocol texts, governance logic, metrics and state transitions public at aggregate level"),
    ]
    for rids, chk, pred, ok in groups:
        if applies(pred):
            bad = against(pred)
            if chk == "audit_without_personal_data":
                bad += [m.value["request"] for m in decs.values() if m.value.get("raw_personal_data")]
            for rid in rids:
                out.append(v(rid, chk, sorted(set(bad)), ok, "{n} requests decided against the rule"))
        else:
            for rid in rids:
                out.append(na(rid, chk, "matching requests", "no such request"))
    audits = [m for m in decs.values() if reqs[m.value["request"]]["purpose"] == "audit" and m.value["grant"]]
    out.append(v("PRIVACY-9-02", "zero_knowledge_audit", [m.value["request"] for m in audits if m.value.get("verification") != "zero-knowledge proof"],
                 f"{len(audits)} granted audits verified by zero-knowledge proofs", "{n} audits verified otherwise")
               if audits else na("PRIVACY-9-02", "zero_knowledge_audit", "granted audits", "none"))
    prohibited = [m for m in decs.values() if reqs[m.value["request"]]["purpose"] in FORBIDDEN_PURPOSES or reqs[m.value["request"]]["linked_domains"]]
    out.append(v("PRIVACY-10-02", "prohibited_practice_critical",
                 [m.value["request"] for m in prohibited if not str(m.value.get("classification", "")).startswith("critical system integrity breach")],
                 f"{len(prohibited)} requests for prohibited practices recorded as critical system integrity breaches",
                 "{n} prohibited practices not recorded as critical breaches")
               if prohibited else na("PRIVACY-10-02", "prohibited_practice_critical", "prohibited practices", "none requested"))
    deanon = [m for m in decs.values() if m.value["grant"] and m.value["level"] == "individual"
              and reqs[m.value["request"]]["domain"] in CONDITIONAL + ("identity",)
              and reqs[m.value["request"]]["purpose"] != "crisis_life_preservation"]
    if deanon:
        bad = [m.value["request"] for m in deanon if not (m.value.get("minimal") and m.value.get("time_bound_until") is not None
                                                          and m.value.get("case_bound") == m.value["request"])]
        for rid in ("TRANSPARENCY-8-02", "TRANSPARENCY-8-03", "TRANSPARENCY-8-05"):
            out.append(v(rid, "deanonymization_bounded", bad, "every de-anonymization minimal, time-bound and case-bound",
                         "{n} de-anonymizations not bounded"))
    else:
        for rid in ("TRANSPARENCY-8-02", "TRANSPARENCY-8-03", "TRANSPARENCY-8-05"):
            out.append(na(rid, "deanonymization_bounded", "de-anonymization", "none granted"))
    crisis = [m for m in decs.values() if reqs[m.value["request"]]["purpose"] == "crisis_life_preservation" and m.value["grant"]]
    if crisis:
        bad = [m.value["request"] for m in crisis if not all(m.value.get(f) for f in ("temporary", "logged", "reversible", "ends_with_crisis"))]
        for rid in ("PRIVACY-11-02", "PRIVACY-11-03", "PRIVACY-11-04", "PRIVACY-11-05", "PRIVACY-11-06", "TRANSPARENCY-10-04"):
            out.append(v(rid, "crisis_reduction_bounded", bad,
                         "crisis anonymity reductions inside the Crisis Scope, for life preservation, temporary, logged, reversible",
                         "{n} crisis reductions not bounded"))
    else:
        for rid in ("PRIVACY-11-02", "PRIVACY-11-03", "PRIVACY-11-04", "PRIVACY-11-05", "PRIVACY-11-06", "TRANSPARENCY-10-04"):
            out.append(na(rid, "crisis_reduction_bounded", "crisis reductions", "none granted"))
    cn = [m for m in msgs if m.source == "TRANSPARENCY" and m.value.get("crisis_scope")]
    if cn:
        bad = [m.event_id for m in cn if m.value["identity_exposure"] != "unchanged" or m.value["action_transparency"] != "increased"]
        for rid in ("TRANSPARENCY-10-01", "TRANSPARENCY-10-02", "TRANSPARENCY-10-03", "PRIVACY-11-01"):
            out.append(v(rid, "crisis_transparency", bad, "during the Crisis Scope action transparency rose, identity exposure did not, "
                         "emergency measures logged; privacy not suspended", "{n} crisis notices raising identity exposure"))
    else:
        for rid in ("TRANSPARENCY-10-01", "TRANSPARENCY-10-02", "TRANSPARENCY-10-03", "PRIVACY-11-01"):
            out.append(na(rid, "crisis_transparency", "Crisis Scope", "no Crisis Scope active"))
    part = [m for m in msgs if m.source == "PARTICIPATION"][0]
    out.append(v("PRIVACY-8-01", "right_to_anonymity", ["identity required"] if part.value["identity_required"] else [],
                 "participation possible without identity disclosure", "participation required identity"))
    out.append(v("TRANSPARENCY-3-02", "no_identity_condition", ["identity required"] if part.value["identity_required"] else [],
                 "identity disclosure is not a condition of participation", "participation required identity"))
    out.append(v("PRIVACY-8-02", "anonymous_full_rights", ["reduced"] if part.value["functions_for_anonymous"] != "full" else [],
                 "anonymous participants keep full access to system functions", "anonymous participants lost access"))
    bad = [m.value["request"] for m in decs.values() if not m.value.get("reason") or not m.value.get("protocol_refs")]
    out.append(v("TRANSPARENCY-11-01", "explained_decisions", bad, "every decision explains why and names its protocol references",
                 "{n} unexplained decisions"))
    bad = [m.value["request"] for m in decs.values() if not m.value.get("audit_hook")]
    out.append(v("TRANSPARENCY-12-01", "audit_hooks", bad, "every decision exposes an audit hook", "{n} decisions without audit hook"))
    pub = [m for m in msgs if m.source == "PRIVACY" and m.value.get("rules_published")]
    for rid in ("PRIVACY-12-01", "PRIVACY-12-03", "PRIVACY-12-04"):
        out.append(v(rid, "privacy_rules_public", [] if pub else ["not published"],
                     "privacy rules, thresholds and guarantees published and verifiable by Subjects", "privacy rules not published"))
    if r["reidentification_k"] < 0:
        out.append(CheckResult("PRIVACY-4-05", "breach_threshold", UNKNOWN,
                               "a Privacy Breach is identity reconstruction 'beyond defined thresholds'; no threshold is defined"))
    else:
        out.append(CheckResult("PRIVACY-4-05", "breach_threshold", PASS,
                               f"declared re-identification threshold k = {r['reidentification_k']} (not from the corpus)"))
    if unsettled:
        out.append(CheckResult("PRIVACY-6-01", "absolute_aggregate", UNKNOWN,
                               f"{len(unsettled)} requests for aggregate statistics of an absolute privacy domain: §6 keeps the "
                               "domains 'private and non-public' and 'non-auditable at the individual level'; whether aggregates "
                               f"are allowed is not said (F-026; reading '{r['absolute_aggregate_reading']}')"))
    return out


IMPLEMENTS = {
    "PRIVACY-6-01": ("absolute_domains", "PARTIAL", "Aggregates of an absolute domain are not settled (F-026): UNKNOWN."),
    "PRIVACY-6-02": ("absolute_domains", "IMPLEMENTED", None),
    "TRANSPARENCY-3-03": ("absolute_domains", "PARTIAL", "Private life as the absolute privacy domains."),
    "PRIVACY-7-01": ("conditional_domains", "IMPLEMENTED", None),
    "PRIVACY-7-02": ("conditional_domains", "IMPLEMENTED", None),
    "TRANSPARENCY-8-01": ("deanonymization_conditions", "IMPLEMENTED", None),
    "TRANSPARENCY-6-02": ("deanonymization_conditions", "PARTIAL", "Scope authorization is a declared trigger."),
    "TRANSPARENCY-7-02": ("deanonymization_conditions", "PARTIAL", "AXIOMS mandates are not modelled."),
    "TRANSPARENCY-8-02": ("deanonymization_bounded", "IMPLEMENTED", None),
    "TRANSPARENCY-8-03": ("deanonymization_bounded", "IMPLEMENTED", None),
    "TRANSPARENCY-8-05": ("deanonymization_bounded", "IMPLEMENTED", None),
    "PRIVACY-9-01": ("audit_without_personal_data", "IMPLEMENTED", None),
    "PRIVACY-9-03": ("audit_without_personal_data", "IMPLEMENTED", None),
    "PRIVACY-9-04": ("audit_without_personal_data", "IMPLEMENTED", None),
    "TRANSPARENCY-12-04": ("audit_without_personal_data", "IMPLEMENTED", None),
    "PRIVACY-10-01": ("prohibited_purposes", "PARTIAL", "Purposes are declared on the request."),
    "PRIVACY-9-02": ("zero_knowledge_audit", "PARTIAL", "The verification method is recorded, not executed."),
    "PRIVACY-10-02": ("prohibited_practice_critical", "PARTIAL", "Purposes and linkage are declared on the request."),
    "TRANSPARENCY-9-02": ("prohibited_purposes", "IMPLEMENTED", None),
    "TRANSPARENCY-9-03": ("prohibited_purposes", "IMPLEMENTED", None),
    "PRIVACY-4.3-01": ("no_cross_domain_linkage", "PARTIAL", "Linkage is declared on the request; re-identification risk is not computed."),
    "TRANSPARENCY-9-04": ("no_cross_domain_linkage", "IMPLEMENTED", None),
    "PRIVACY-4.1-02": ("no_cross_domain_linkage", "PARTIAL", "Total aggregation observed as cross-domain linkage."),
    "PRIVACY-4.4-01": ("no_convenience_erosion", "IMPLEMENTED", None),
    "PRIVACY-4.2-01": ("no_convenience_erosion", "PARTIAL", "Minimum exposure observed for analytics requests."),
    "TRANSPARENCY-5-01": ("public_by_default", "IMPLEMENTED", None),
    "TRANSPARENCY-5-02": ("public_by_default", "IMPLEMENTED", None),
    "PRIVACY-11-02": ("crisis_reduction_bounded", "IMPLEMENTED", None),
    "PRIVACY-11-03": ("crisis_reduction_bounded", "IMPLEMENTED", None),
    "PRIVACY-11-04": ("crisis_reduction_bounded", "IMPLEMENTED", None),
    "PRIVACY-11-05": ("crisis_reduction_bounded", "IMPLEMENTED", None),
    "PRIVACY-11-06": ("crisis_reduction_bounded", "IMPLEMENTED", None),
    "TRANSPARENCY-10-04": ("crisis_reduction_bounded", "IMPLEMENTED", None),
    "TRANSPARENCY-10-01": ("crisis_transparency", "IMPLEMENTED", None),
    "TRANSPARENCY-10-02": ("crisis_transparency", "IMPLEMENTED", None),
    "TRANSPARENCY-10-03": ("crisis_transparency", "IMPLEMENTED", None),
    "PRIVACY-11-01": ("crisis_transparency", "IMPLEMENTED", None),
    "PRIVACY-8-01": ("right_to_anonymity", "IMPLEMENTED", None),
    "PRIVACY-8-02": ("anonymous_full_rights", "IMPLEMENTED", None),
    "TRANSPARENCY-3-02": ("no_identity_condition", "IMPLEMENTED", None),
    "TRANSPARENCY-11-01": ("explained_decisions", "IMPLEMENTED", None),
    "TRANSPARENCY-12-01": ("audit_hooks", "IMPLEMENTED", None),
    "PRIVACY-12-01": ("privacy_rules_public", "IMPLEMENTED", None),
    "PRIVACY-12-03": ("privacy_rules_public", "PARTIAL", "Publication flag; verification by Subjects is not modelled."),
    "PRIVACY-12-04": ("privacy_rules_public", "PARTIAL", "Publication flag."),
    "PRIVACY-4-05": ("breach_threshold", "PARTIAL", "No re-identification threshold in the corpus: UNKNOWN unless declared."),
}


class PrivacyTransparencyModule(LabModule):
    id = "privacy_transparency"
    version = "1.0.0"
    title = {"en": "Privacy and transparency (PRIVACY, TRANSPARENCY)", "ru": "Приватность и прозрачность (PRIVACY, TRANSPARENCY)"}
    summary = {"en": "Requests to publish or process data: is the system verifiable without exposing people, and is a "
                     "person's identity revealed only when harm is verified and nothing anonymous would do?",
               "ru": "Запросы на публикацию или обработку данных: проверяема ли система без раскрытия людей и раскрывается ли "
                     "личность только при подтверждённом вреде, когда анонимного пути нет?"}
    protocols = ["DKP-7-PRIVACY-001", "DKP-7-TRANSPARENCY-001", "DKP-8-AUDIT-001", "DKP-4-CRISIS-001"]
    example_order = ["mixed_requests", "harm_and_crisis", "absolute_aggregates_forbidden", "faulty_disclosure"]
    alternative_examples = ["absolute_aggregates_forbidden"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_privacy_transparency_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-PT-1", "source": "hypothesis", "text": {
            "en": "Each request declares domain, level, purpose, linked domains and the §8 conditions; the module decides and "
                  "checks, it does not detect harm or re-identification risk.",
            "ru": "Каждый запрос объявляет домен, уровень, цель, связанные домены и условия §8; модуль решает и проверяет, но не "
                  "обнаруживает вред или риск повторной идентификации."}},
        {"id": "H-PT-2", "source": "alternative", "text": {
            "en": "Aggregates of an absolute privacy domain: 'aggregate_allowed' (§6 forbids the individual level) or "
                  "'never' (§6 'SHALL ALWAYS remain private and non-public') (F-026).",
            "ru": "Агрегаты абсолютно приватного домена: 'aggregate_allowed' (§6 запрещает индивидуальный уровень) или 'never' "
                  "(§6 'SHALL ALWAYS remain private and non-public') (F-026)."}},
        {"id": "H-PT-3", "source": "missing", "text": {
            "en": "The re-identification threshold of a Privacy Breach ('beyond defined thresholds') is not defined.",
            "ru": "Порог повторной идентификации для Privacy Breach ('beyond defined thresholds') не определён."}},
    ]
    inputs = {
        "requests": {"type": "list", "min_items": 1, "max_items": 40, "items": REQUEST, "source": "user",
                     "default": [full(id="r1", domain="governance_logic"),
                                 full(id="r2", domain="mobility", level="aggregate"),
                                 full(id="r3", domain="medical", level="individual"),
                                 full(id="r4", domain="economic", level="anonymized", purpose="audit"),
                                 full(id="r5", domain="platform", level="individual", purpose="profiling"),
                                 full(id="r6", domain="mobility", level="individual", purpose="analytics"),
                                 full(id="r7", domain="economic", level="aggregate", linked_domains=["mobility"]),
                                 full(id="r8", domain="medical", level="aggregate")],
                     "label": {"en": "Data requests (H-PT-1)", "ru": "Запросы данных (H-PT-1)"}},
        "absolute_aggregate_reading": {"type": "enum", "values": ["aggregate_allowed", "never"], "default": "aggregate_allowed",
                                       "source": "alternative", "label": {"en": "Aggregates of absolute domains (H-PT-2)",
                                                                         "ru": "Агрегаты абсолютных доменов (H-PT-2)"}},
        "crisis_scope_active": {"type": "bool", "default": False, "source": "user",
                                "label": {"en": "Crisis Scope active", "ru": "Действует Crisis Scope"}},
        "participants": {"type": "object", "source": "user", "label": {"en": "Participants", "ru": "Участники"},
                         "fields": {"anonymous": {"type": "int", "min": 0, "max": 10 ** 9, "default": 40},
                                    "identified": {"type": "int", "min": 0, "max": 10 ** 9, "default": 60}},
                         "default": {"anonymous": 40, "identified": 60}},
        "reidentification_k": {"type": "int", "min": -1, "max": 10 ** 6, "default": -1, "source": "missing",
                               "label": {"en": "Re-identification threshold k (-1: undefined; H-PT-3)", "ru": "Порог k (-1: не определён)"}},
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
        for x in ids:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                p.append(f"input.requests: id {x!r}")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        decs = [m.value for m in log.messages() if m.source == "PRIVACY" and m.kind == "decision"]
        outputs = {"decisions": decs, "granted": sum(1 for d in decs if d["grant"]),
                   "refused": sum(1 for d in decs if not d["grant"]),
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        e = [{"en": f"{d['request']} ({d['domain']}, {d['level']}): {'granted' if d['grant'] else 'refused'} — "
                    f"{d.get('reason', '—')} [{', '.join(d.get('protocol_refs', []))}]",
              "ru": f"{d['request']} ({d['domain']}, {d['level']}): {'разрешено' if d['grant'] else 'отказано'} — "
                    f"{d.get('reason', '—')} [{', '.join(d.get('protocol_refs', []))}]"} for d in decs][:30]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"granted": outputs["granted"], "refused": outputs["refused"]}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        harm = [{"id": "h1", "domain": "identity", "level": "individual", "purpose": "enforcement", "harm_verified": True,
                 "attribution_required": True, "anonymous_path": False, "scope_trigger": True},
                {"id": "h2", "domain": "economic", "level": "individual", "purpose": "enforcement", "harm_verified": False,
                 "scope_trigger": True},
                {"id": "h3", "domain": "mobility", "level": "individual", "purpose": "crisis_life_preservation",
                 "in_crisis_scope": True},
                {"id": "h4", "domain": "state_transitions"}]
        return {
            "mixed_requests": {},
            "harm_and_crisis": {"requests": harm, "crisis_scope_active": True},
            "absolute_aggregates_forbidden": {"absolute_aggregate_reading": "never"},
            "faulty_disclosure": {"faults": ["release_absolute_individual", "profiling_granted", "correlate_domains",
                                             "convenience_override", "identity_required"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_id": {"requests": [{"id": "a", "domain": "medical"}, {"id": "a", "domain": "economic"}]},
                "unknown_domain": {"requests": [{"id": "a", "domain": "dreams"}]},
                "bad_id": {"requests": [{"id": "A-1", "domain": "medical"}]}}
