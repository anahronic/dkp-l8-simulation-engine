"""
EDUCATION AND CULTURE module — DKP-5-EDU-001 and DKP-5-CULTURE-001 for a population of Subjects.

Every Subject takes an open, criteria-declared system-literacy assessment in a language of their choice
(EDU §5, §7; CULTURE §4.2, §5: language is never a proxy for competence).  A failed assessment is a
corrective signal: free remediation at once, enhanced support on repeated failure, never punishment,
exclusion, change of legal status or a gate to basic rights (EDU §5 Safeguards, §8, §11).  Access to
advanced functions may be restricted only temporarily, reversibly, with confidence bounds and review
intervals calibrated in L8 — and without an L8 calibration the signal is informational only (EDU §12),
which is the state of the corpus (F-014).  Assessments never test belief or loyalty; credentials carry no
authority; learning data are minimal and never used for profiling (EDU §4, §9, §10).

Culture: no language or culture is a default or has priority; interfaces let each Subject choose the
language and support every language in use, minority ones included; translations keep meaning, agency
and intent; cultures are never ranked, scored or optimized; participation is voluntary and affiliation
changes nothing; a Cultural Exception is temporary, scoped, non-enforceable and logged and never exempts a
factual claim from verification or blocks a PTL harm signal (CULTURE §4–§11).  Time unit: DTI-Day.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from lab.core.bus import EventLog, Message
from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN, CheckResult
from lab.core.module import LabModule, ModuleResult
from lab.core.schema import LabInputError, resolve

FAULTS = {
    "punish_literacy_failure": "a failed assessment leads to a penalty",
    "permanent_exclusion": "a failed assessment leads to permanent exclusion from system functions",
    "gate_basic_rights": "a basic right depends on passing the assessment",
    "restrict_without_bundle": "advanced functions are restricted without L8 calibration",
    "irreversible_restriction": "a competence restriction has no review interval",
    "no_remediation": "no free remediation follows a failed assessment",
    "belief_screening": "the assessment includes a loyalty or belief item",
    "credential_privilege": "a diploma grants access without competence",
    "profile_learning_data": "learning data are reused for profiling",
    "language_as_competence": "the assessment is only offered in the dominant language",
    "cultural_ranking": "a metric ranks cultures",
    "default_dominant_language": "interfaces default to the dominant language",
    "lossy_translation": "a translation that alters meaning is used",
    "mandatory_participation": "participation in a cultural programme is required",
    "exception_enforced": "a Cultural Exception is enforced and has no end",
    "culture_exempts_claim": "cultural context exempts a factual claim from verification",
    "culture_resolves_conflict": "a local council resolves the conflict instead of the SCOPE rules",
    "undeclared_mechanism": "a Cultural Exception declares neither duration nor reversibility",
    "audit_refused": "an audit of educational content is refused",
    "admit_any_module": "an educational module is deployed whatever its properties",
    "rank_by_assessment": "Subjects are ranked by their assessment results",
    "label_as_intelligence": "assessment outcomes are published as intelligence scores",
    "failure_as_fault": "a failed assessment is recorded as a fault marker",
    "nonreproducible_assessment": "the assessment outcome is not reproducible from its recorded performance",
    "culture_overreach": "CULTURE carries out requests §2, §4.3 and §5 exclude (doctrine, justification by productivity, conformity)",
    "persistence_by_scale": "support for a culture's persistence requires a minimum number of speakers",
    "asymmetric_neutrality": "the dominant language is denied an assessment offered to the minority languages",
    "assimilation_incentive": "a tax credit is offered on condition of adopting the dominant language",
    "worldview_gate": "access to education is denied on the basis of a declared worldview",
}
SUBJECT = {"type": "object", "fields": {
    "id": {"type": "str"},
    "language": {"type": "str", "default": "lang_a"},
    "literacy_passed": {"type": "bool", "default": True},
    "failures": {"type": "int", "min": 0, "max": 100, "default": 0},
    "credential": {"type": "bool", "default": False},
    "minority": {"type": "bool", "default": False}}}
TRANSLATION = {"type": "object", "fields": {"source": {"type": "str"}, "target": {"type": "str"},
                                            "meaning_preserved": {"type": "bool", "default": True}}}
DEFINES = ("culture", "worldview", "morality", "intelligence", "personal_values", "moral_correctness", "political_correctness",
           "personal_success")                                                          # EDU §1, §2, §11: never defined by EDU
MODULE = {"type": "object", "fields": {
    "id": {"type": "str"},
    "domain": {"type": "str", "default": "system_literacy"},                            # §3: a specific competence domain
    "bounded": {"type": "bool", "default": True},
    "verification": {"type": "enum", "values": ["observable_performance", "attendance", "statement_of_belief"],
                     "default": "observable_performance"},
    "access": {"type": "enum", "values": ["open_source", "publicly_inspectable", "closed"], "default": "open_source"},
    "path": {"type": "enum", "values": ["chosen", "uniform_mandatory"], "default": "chosen"},
    "required_assent": {"type": "list", "min_items": 0, "max_items": 5, "items": {"type": "str"}, "default": []},
    "alignment_condition": {"type": "enum", "values": ["none", "worldview", "political"], "default": "none"},
    "conformity_sanction": {"type": "bool", "default": False},
    "ideological_narrative": {"type": "bool", "default": False},
    "defines": {"type": "list", "min_items": 0, "max_items": len(DEFINES), "items": {"type": "enum", "values": list(DEFINES)},
                "default": []}}}
MODULES_DEFAULT = [
    {"id": "system_literacy", "domain": "system_literacy"},
    {"id": "grid_safety", "domain": "energy_safety"},
    {"id": "history_sources", "domain": "source_criticism", "access": "publicly_inspectable"},
    {"id": "loyalty_course", "domain": "civic_values", "verification": "statement_of_belief", "required_assent": ["the system is just"],
     "alignment_condition": "worldview", "conformity_sanction": True, "ideological_narrative": True, "defines": ["moral_correctness"],
     "path": "uniform_mandatory", "access": "closed"},
    {"id": "civic_success", "domain": "civic_participation", "alignment_condition": "political",
     "defines": ["personal_success", "intelligence", "worldview", "political_correctness"]},
]


def module_problems(m: Dict[str, Any]) -> List[str]:
    """Why a declared educational module may not be deployed (EDU §2, §3, §4, §6, §9, §10, §11)."""
    out = []
    if not m["bounded"] or not m["domain"] or m["verification"] != "observable_performance":
        out.append("not a bounded, verifiable module of one competence domain (§3)")
    if m["required_assent"]:
        out.append("mandates belief acceptance (§6)")
    if m["alignment_condition"] != "none":
        out.append(f"requires {m['alignment_condition']} alignment (§6, §9)")
    if m["conformity_sanction"]:
        out.append("enforces conformity (§6)")
    if m["ideological_narrative"]:
        out.append("imposes an ideological narrative (§2, §9)")
    if m["defines"]:
        out.append("defines " + ", ".join(m["defines"]) + " (§1, §2, §11)")
    if m["path"] != "chosen":
        out.append("enforces a uniform educational path (§11)")
    if m["access"] == "closed":
        out.append("neither open-source nor publicly inspectable (§10)")
    return out


EXCEPTION = {"declared": {"type": "bool", "default": False},
             "days": {"type": "int", "min": 0, "max": 3650, "default": 10},
             "scope": {"type": "str", "default": "festival_zone"},
             "touches_factual_claim": {"type": "bool", "default": False}}


def full_subject(**kw):
    return {**{k: f["default"] for k, f in SUBJECT["fields"].items() if "default" in f}, **kw}


CULTURE_REQUESTS = {"define_moral_doctrine": "CULTURE-2-02", "define_belief_system": "CULTURE-2-02",
                    "justify_by_productivity": "CULTURE-4.3-03", "enforce_conformity": "CULTURE-5-01"}
JUSTIFICATIONS = ("economic performance", "demographic scale", "productivity metrics")              # CULTURE §4.3


def run(r: Dict[str, Any]):
    faults = set(r["faults"])
    log = EventLog("DTI-Day", tie_rule="observation < evaluation < decision < action < notice; then event_id")
    order = {"observation": 0, "evaluation": 1, "decision": 2, "action": 3, "notice": 4}
    n = {"i": 0}

    def put(kind, source, k, value, prov=()):
        n["i"] += 1
        return log.append(Message(event_id=f"{source.lower()}-{k:03d}-{n['i']:05d}", kind=kind, source=source, arrived_at=k,
                                  decided_at=k if kind in ("decision", "action") else None, value=value,
                                  provenance=tuple(prov), order=order[kind]))

    langs = sorted({s["language"] for s in r["subjects"]})
    dominant = r["dominant_language"]
    supported = [dominant] if "language_as_competence" in faults else langs
    put("notice", "INTERFACE", 0, {"supported_languages": langs, "default_language": dominant if "default_dominant_language" in faults
                                   else "user choice", "loaded_symbols": False})
    bundle = r["l8_bundle_present"]
    for s in r["subjects"]:
        lang = s["language"] if s["language"] in supported else dominant
        items = ["layer structure", "rights and obligations", "risk attribution", "appeal pathways", "scope and exit"]
        if "belief_screening" in faults:
            items.append("loyalty to the system")
        passed = s["literacy_passed"] and (lang == s["language"])
        a = put("evaluation", "EDU", 1, {"subject": s["id"], "assessment_language": lang, "items": items,
                                         "criteria_declared": True, "open": True, "passed": passed,
                                         "method": "observable performance", "performance_record": s["literacy_passed"],
                                         "outcome_reproduced": passed if "nonreproducible_assessment" not in faults else not passed,
                                         "signal": "intelligence score" if "label_as_intelligence" in faults else "competence signal"})
        if s["credential"] and "credential_privilege" in faults:
            put("action", "EDU", 1, {"subject": s["id"], "advanced_access": "granted by diploma"}, [a.event_id])
        if not passed:
            if "failure_as_fault" in faults:
                put("notice", "EDU", 1, {"subject": s["id"], "fault_marker": "failed system literacy"}, [a.event_id])
            if "no_remediation" not in faults:
                put("action", "EDU", 1, {"subject": s["id"], "remediation": "free, automatic",
                                         "support": "enhanced" if s["failures"] >= 1 else "targeted modules"}, [a.event_id])
            if "punish_literacy_failure" in faults:
                put("action", "EDU", 1, {"subject": s["id"], "penalty": "fee"}, [a.event_id])
            if "permanent_exclusion" in faults:
                put("action", "EDU", 1, {"subject": s["id"], "excluded": "permanent"}, [a.event_id])
            if "gate_basic_rights" in faults:
                put("action", "EDU", 1, {"subject": s["id"], "basic_right_withheld": "appeal"}, [a.event_id])
            if bundle or "restrict_without_bundle" in faults:
                rv = {"subject": s["id"], "advanced_functions": "temporarily restricted", "reversible": True,
                      "review_interval_days": None if "irreversible_restriction" in faults else 30,
                      "confidence_bounds": "from L8 bundle" if bundle else None}
                put("action", "EDU", 1, rv, [a.event_id])
            else:
                put("notice", "EDU", 1, {"subject": s["id"], "advanced_functions": "not restricted",
                                         "reason": "no L8 calibration: educational signal informational only (EDU §12)"},
                    [a.event_id])
        put("action", "EDU", 2, {"subject": s["id"], "learning_data": "minimized",
                                 "use": "profiling" if "profile_learning_data" in faults else "education only"})
    if "rank_by_assessment" in faults:
        put("notice", "EDU", 2, {"ranking": sorted(s["id"] for s in r["subjects"])})
    for md in r["edu_modules"]:
        why = module_problems(md)
        ok = not why or "admit_any_module" in faults
        put("decision", "EDU", 0, {"edu_module": md["id"], "deployed": ok, "refused_for": [] if ok else why,
                                   "properties": {k: md[k] for k in md if k != "id"}})
    for t in r["translations"]:
        use = t["meaning_preserved"] or "lossy_translation" in faults
        put("action" if use else "notice", "CULTURE", 3, {"translation": f"{t['source']}->{t['target']}",
                                                          "meaning_preserved": t["meaning_preserved"], "used": use,
                                                          "reason": None if use else "lossy translation refused (§4.2)"})
    put("evaluation", "CULTURE", 4, {"metrics": ["interface availability per language", "access neutrality"] +
                                     (["culture efficiency ranking"] if "cultural_ranking" in faults else [])})
    put("action", "CULTURE", 4, {"programme": "minority archive", "participation": "mandatory" if "mandatory_participation" in faults
                                 else "voluntary", "self_identification_required": False})
    if "assimilation_incentive" in faults:
        put("action", "CULTURE", 4, {"incentive": "tax credit", "condition": "adopt the dominant language"})
    if "worldview_gate" in faults and r["subjects"]:
        put("action", "EDU", 1, {"subject": r["subjects"][0]["id"], "education_access": "denied", "basis": "declared worldview"})
    for q in r["culture_requests"]:
        rq = put("observation", "REQUEST", 4, {"request": q})
        if "culture_overreach" in faults:
            put("action", "CULTURE", 4, {"performed": q}, [rq.event_id])
        else:
            put("notice", "CULTURE", 4, {"request": q, "refused": True, "basis": CULTURE_REQUESTS[q]}, [rq.event_id])
    speakers: Dict[str, int] = {}
    for x in r["subjects"]:
        speakers[x["language"]] = speakers.get(x["language"], 0) + 1
    dominant = max(sorted(speakers), key=lambda l: speakers[l]) if speakers else None
    for lang in sorted(speakers):
        small = "persistence_by_scale" in faults and speakers[lang] < 2
        put("evaluation", "CULTURE", 4, {"language_treatment": lang, "dominant": lang == dominant, "interface": True,
                                         "assessment_offered": not ("asymmetric_neutrality" in faults and lang == dominant),
                                         "persistence_supported": not small,
                                         "criteria": ["demographic scale"] if small else []})
    ex = r["cultural_exception"]
    if ex["declared"]:
        enforced = "exception_enforced" in faults
        undeclared = "undeclared_mechanism" in faults
        put("notice", "CULTURE", 5, {"cultural_exception": ex["scope"], "temporary": not enforced,
                                     "until_day": None if enforced else 5 + ex["days"], "enforceable": enforced, "logged": True,
                                     "exempts_factual_claim": ex["touches_factual_claim"] and "culture_exempts_claim" in faults,
                                     "conflict_rules": "local council" if "culture_resolves_conflict" in faults else "DKP-7-SCOPE-001",
                                     **({} if undeclared else {"duration_days": ex["days"], "reversible": True})})
    for i in range(r["content_audits"]):
        put("notice", "AUDIT", 6, {"content_audit": i, "under": "DKP-8-AUDIT-001", "allowed": "audit_refused" not in faults})
    return log


def culture_checks(r: Dict[str, Any], msgs) -> List[CheckResult]:
    """CULTURE §2, §4.3, §5, §7 (review КТ5 reading)."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})

    reqs = [m.value["request"] for m in msgs if m.source == "REQUEST" and "request" in m.value]
    done = {m.value["performed"] for m in msgs if m.source == "CULTURE" and m.value.get("performed")}
    treat = [m.value for m in msgs if m.source == "CULTURE" and "language_treatment" in m.value]
    for rid, chk, ok in (("CULTURE-2-02", "no_doctrine", "CULTURE defined no belief system or moral doctrine"),
                         ("CULTURE-5-01", "no_conformity_enforcement", "no cultural conformity enforced"),
                         ("CULTURE-4.3-03", "persistence_without_justification",
                          "no culture had to justify its persistence by economic performance, scale or productivity")):
        mine = [q for q in reqs if CULTURE_REQUESTS[q] == rid]
        bad = [f"{q} carried out" for q in mine if q in done]
        if rid == "CULTURE-4.3-03":
            bad += [f"{t['language_treatment']}: persistence conditioned on {', '.join(t['criteria'])}" for t in treat
                    if set(t["criteria"]) & set(JUSTIFICATIONS) or not t["persistence_supported"]]
        out.append(v(rid, chk, bad, f"{len(mine)} such request(s) refused; " + ok, "{n} breaches"))
    keys = ("interface", "assessment_offered", "persistence_supported", "criteria")
    shapes = {tuple(str(t[k]) for k in keys) for t in treat}
    out.append(v("CULTURE-7-03", "neutrality_both_ways",
                 [] if len(shapes) <= 1 else [f"{t['language_treatment']} ({'dominant' if t['dominant'] else 'minority'}): "
                                              + ", ".join(f"{k}={t[k]}" for k in keys) for t in treat],
                 f"{len(treat)} languages, dominant and minority, treated identically (interface, assessment, persistence)",
                 "unequal treatment of dominant and minority cultures") if treat else
               CheckResult("CULTURE-7-03", "neutrality_both_ways", NOT_APPLICABLE, "cultural neutrality",
                           applicability="no language in use"))
    return out


def outcomes(msgs) -> Dict[str, Any]:
    """What governance did to each Subject: assessment result and the kinds of EDU acts addressed to it."""
    out: Dict[str, Any] = {}
    for m in msgs:
        if m.source == "EDU" and m.value.get("subject"):
            o = out.setdefault(m.value["subject"], {"passed": None, "acts": []})
            if "passed" in m.value:
                o["passed"] = m.value["passed"]
            elif m.kind == "action":
                o["acts"].append(sorted(k for k in m.value if k != "subject"))
    return out


def returned_checks(r: Dict[str, Any], msgs) -> List[CheckResult]:
    """Provisions returned to work after the reading of the Codex-draft open points (review of checkpoint 6)."""
    out: List[CheckResult] = []

    def v(rid, chk, bad, ok, no):
        return CheckResult(rid, chk, FAIL if bad else PASS, no.format(n=len(bad)) if bad else ok,
                           evidence={"violations": bad[:10]} if bad else {})
    if r["subjects"]:
        # metamorphic: the same Subjects with one language and no minority flag must be treated the same way
        same = dict(r, subjects=[dict(x, language=r["dominant_language"], minority=False) for x in r["subjects"]])
        a, b = outcomes(msgs), outcomes(run(same).messages())
        diff = [f"{k}: {a[k]} vs {b.get(k)}" for k in sorted(a) if a[k] != b.get(k)]
        langs = sorted({x["language"] for x in r["subjects"]})
        out.append(v("CULTURE-4.1-02", "language_agnostic", diff,
                     f"governance outcomes for {len(a)} Subjects ({len(langs)} languages) are unchanged when every Subject is "
                     "given the dominant language: culture-neutral and language-agnostic", "{n} outcomes that depend on language"))
        out.append(v("CULTURE-7-02", "affiliation_affects_nothing", diff,
                     "no Subject's rights, access or outcomes change with its cultural affiliation (language, minority status)",
                     "{n} outcomes that change with cultural affiliation"))
    else:
        for rid, chk in (("CULTURE-4.1-02", "language_agnostic"), ("CULTURE-7-02", "affiliation_affects_nothing")):
            out.append(CheckResult(rid, chk, NOT_APPLICABLE, "cultural neutrality", applicability="no Subject"))
    inc = [m.event_id for m in msgs if m.source in ("CULTURE", "EDU") and m.value.get("incentive")
           and m.value.get("condition")]
    out.append(v("CULTURE-5-03", "no_assimilation_incentive", inc, "no economic incentive is tied to cultural assimilation",
                 "{n} incentives tied to assimilation"))
    gate = [m.event_id for m in msgs if m.source == "EDU" and m.value.get("education_access") == "denied"
            and any(w in str(m.value.get("basis")) for w in ("opinion", "worldview", "belief"))]
    out.append(v("EDU-2-05", "no_worldview_gate", gate, "no access to education was restricted on opinion or worldview",
                 "{n} restrictions of access on opinion or worldview"))
    disc = [f"{m.value['subject']}: {k}" for m in msgs if m.source == "EDU" and m.kind == "action"
            for k in ("penalty", "excluded", "basic_right_withheld") if k in m.value]
    out.append(v("EDU-8-04", "not_disciplinary", disc,
                 "educational outcomes led to remediation only: no penalty, exclusion or withheld right",
                 "{n} uses of education as enforcement or discipline"))
    return out


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

    subj = {s["id"]: s for s in r["subjects"]}
    assess = {m.value["subject"]: m for m in msgs if m.source == "EDU" and m.kind == "evaluation"}
    acts = [m for m in msgs if m.source == "EDU" and m.kind == "action"]
    failed = [sid for sid, s in subj.items() if not s["literacy_passed"]]
    # assessments
    bad = [sid for sid, m in assess.items() if m.value["assessment_language"] != subj[sid]["language"]]
    for rid, chk in (("CULTURE-5-05", "language_not_competence_proxy"), ("EDU-7-04", "minimal_language_bias"),
                     ("CULTURE-5-02", "minority_languages_served")):
        out.append(v(rid, chk, bad, "every Subject assessed in their own language", "{n} Subjects assessed in another language"))
    bad = [sid for sid, m in assess.items() if any("loyal" in i or "belief" in i for i in m.value["items"])]
    for rid, chk in (("EDU-9-03", "no_belief_screening"), ("EDU-7-05", "no_ideology_items"), ("EDU-2-04", "no_belief_evaluation")):
        out.append(v(rid, chk, bad, "assessments test system competence only", "{n} assessments with belief or loyalty items"))
    bad = [sid for sid, m in assess.items() if not (m.value["criteria_declared"] and m.value["open"])]
    for rid in ("EDU-7-02", "EDU-7-03", "EDU-10-02"):
        out.append(v(rid, "open_declared_assessment", bad, "assessments open with declared criteria", "{n} closed assessments"))
    bad = [m.value["subject"] for m in acts if m.value.get("advanced_access") == "granted by diploma"]
    for rid, chk in (("EDU-4-02", "competence_over_credential"), ("EDU-9-05", "no_credential_privilege")):
        out.append(v(rid, chk, bad, "no access granted by credentials", "{n} accesses granted by diploma"))
    if failed:
        rem = {m.value["subject"] for m in acts if m.value.get("remediation") == "free, automatic"}
        out.append(v("EDU-Safeguards-05", "free_remediation", [s for s in failed if s not in rem],
                     "free, automatic remediation for every failed assessment", "{n} failures without remediation"))
        out.append(v("EDU-8-01", "targeted_modules", [s for s in failed if s not in rem],
                     "targeted modules offered", "{n} failures without modules"))
        bad = [m.value["subject"] for m in acts if m.value.get("penalty")]
        for rid, chk in (("EDU-Safeguards-01", "no_punishment"), ("EDU-9-04", "no_punitive_education"),
                         ("EDU-8-03", "support_not_penalty"), ("EDU-9-06", "no_penalty_substitution")):
            out.append(v(rid, chk, bad, "no penalty for failed assessments", "{n} penalties"))
        bad = [m.value["subject"] for m in acts if m.value.get("excluded")]
        for rid, chk in (("EDU-Safeguards-02", "no_permanent_exclusion"), ("EDU-8-05", "no_permanent_denial")):
            out.append(v(rid, chk, bad, "no permanent exclusion", "{n} permanent exclusions"))
        bad = [m.value["subject"] for m in acts if m.value.get("basic_right_withheld")]
        for rid, chk in (("EDU-11-05", "not_a_rights_gate"), ("EDU-Safeguards-03", "legal_status_unchanged")):
            out.append(v(rid, chk, bad, "basic rights and legal status independent of the assessment", "{n} rights withheld"))
        restr = [m for m in acts if m.value.get("advanced_functions") == "temporarily restricted"]
        if not r["l8_bundle_present"]:
            for rid, chk in (("EDU-12-04", "informational_without_l8"), ("EDU-12-02", "restriction_calibrated")):
                out.append(v(rid, chk, [m.value["subject"] for m in restr],
                             "no L8 calibration: failed assessments restricted nothing (informational signals)",
                             "{n} restrictions without L8 calibration"))
        else:
            for rid, chk in (("EDU-12-04", "informational_without_l8"), ("EDU-12-02", "restriction_calibrated")):
                out.append(na(rid, chk, "uncalibrated restriction", "a (hypothetical) bundle is declared"))
        if restr:
            bad = [m.value["subject"] for m in restr if not m.value.get("reversible") or not m.value.get("review_interval_days")]
            for rid, chk in (("EDU-12-01", "restriction_reversible"), ("EDU-12-03", "review_intervals"),
                             ("EDU-Safeguards-04", "only_temporary_restriction")):
                out.append(v(rid, chk, bad, "restrictions temporary, reversible, with review intervals",
                             "{n} restrictions without review"))
        else:
            for rid, chk in (("EDU-12-01", "restriction_reversible"), ("EDU-12-03", "review_intervals"),
                             ("EDU-Safeguards-04", "only_temporary_restriction")):
                out.append(na(rid, chk, "restrictions", "none applied"))
    else:
        for rid, chk in (("EDU-Safeguards-05", "free_remediation"), ("EDU-8-01", "targeted_modules"),
                         ("EDU-Safeguards-01", "no_punishment"), ("EDU-9-04", "no_punitive_education"),
                         ("EDU-8-03", "support_not_penalty"), ("EDU-9-06", "no_penalty_substitution"),
                         ("EDU-Safeguards-02", "no_permanent_exclusion"), ("EDU-8-05", "no_permanent_denial"),
                         ("EDU-11-05", "not_a_rights_gate"), ("EDU-Safeguards-03", "legal_status_unchanged"),
                         ("EDU-12-04", "informational_without_l8"), ("EDU-12-02", "restriction_calibrated"),
                         ("EDU-12-01", "restriction_reversible"), ("EDU-12-03", "review_intervals"),
                         ("EDU-Safeguards-04", "only_temporary_restriction")):
            out.append(na(rid, chk, "failed assessments", "every Subject passed"))
    bad = [m.value["subject"] for m in acts if m.value.get("use") == "profiling"]
    for rid, chk in (("EDU-10-06", "learning_data_not_profiled"), ("EDU-10-04", "learning_data_minimized")):
        out.append(v(rid, chk, bad, "learning data minimized and used for education only", "{n} learning records profiled"))
    # culture
    ui = [m for m in msgs if m.source == "INTERFACE"][0]
    bad = [] if ui.value["default_language"] == "user choice" else [ui.value["default_language"]]
    for rid, chk in (("CULTURE-8-02", "no_default_culture"), ("CULTURE-4.1-03", "no_reference_culture"),
                     ("CULTURE-4.1-01", "no_systemic_priority"), ("CULTURE-8-01", "selectable_context")):
        out.append(v(rid, chk, bad, "interfaces default to the Subject's choice; no culture is a default",
                     "interfaces default to a dominant language"))
    langs = sorted({s["language"] for s in subj.values()})
    out.append(v("CULTURE-4.2-01", "all_languages_supported", sorted(set(langs) - set(ui.value["supported_languages"])),
                 f"interfaces support all {len(langs)} languages in use", "{n} languages unsupported"))
    tr = [m for m in msgs if m.source == "CULTURE" and "translation" in m.value]
    if tr:
        out.append(v("CULTURE-4.2-02", "semantic_fidelity", [m.value["translation"] for m in tr if m.value["used"] and not m.value["meaning_preserved"]],
                     "only meaning-preserving translations used", "{n} lossy translations used"))
    else:
        out.append(na("CULTURE-4.2-02", "semantic_fidelity", "translations", "none"))
    met = [m for m in msgs if m.source == "CULTURE" and "metrics" in m.value][0]
    bad = [x for x in met.value["metrics"] if "ranking" in x or "efficiency" in x or "progress" in x]
    for rid, chk in (("CULTURE-4.3-01", "no_cultural_optimization"), ("CULTURE-4.3-02", "no_cultural_metrics"),
                     ("CULTURE-0-01", "no_ranking"), ("CULTURE-11-01", "no_enforceable_rankings")):
        out.append(v(rid, chk, bad, "no metric ranks, scores or optimizes a culture", "{n} cultural ranking metrics"))
    prog = [m for m in msgs if m.source == "CULTURE" and "programme" in m.value]
    bad = [m.event_id for m in prog if m.value["participation"] != "voluntary" or m.value["self_identification_required"]]
    for rid, chk in (("CULTURE-7-01", "voluntary_participation"), ("CULTURE-6-02", "no_obligations_from_preservation")):
        out.append(v(rid, chk, bad, "cultural participation voluntary, no self-identification required",
                     "{n} mandatory programmes"))
    exc = [m for m in msgs if m.value.get("cultural_exception")]
    if exc:
        bad = [m.event_id for m in exc if not m.value["temporary"] or m.value["enforceable"] or not m.value["logged"]]
        for rid, chk in (("CULTURE-9-02", "exception_bounded"), ("CULTURE-3-02", "exception_non_enforceable")):
            out.append(v(rid, chk, bad, "the Cultural Exception is temporary, scoped, non-enforceable and logged",
                         "{n} exceptions enforced or unbounded"))
        bad = [m.event_id for m in exc if m.value["exempts_factual_claim"]]
        for rid, chk in (("CULTURE-9-04", "no_verification_exemption"), ("CULTURE-9-01", "no_override_of_ptl")):
            out.append(v(rid, chk, bad, "no factual claim exempted from verification by cultural context",
                         "{n} factual claims exempted"))
    else:
        for rid, chk in (("CULTURE-9-02", "exception_bounded"), ("CULTURE-3-02", "exception_non_enforceable"),
                         ("CULTURE-9-04", "no_verification_exemption"), ("CULTURE-9-01", "no_override_of_ptl")):
            out.append(na(rid, chk, "Cultural Exception", "none declared"))
    if exc:
        out.append(v("CULTURE-9-03", "conflicts_by_scope", [m.event_id for m in exc if m.value.get("conflict_rules") != "DKP-7-SCOPE-001"],
                     "conflicts behind the Cultural Exception are resolved by the SCOPE rules", "{n} conflicts resolved otherwise"))
        out.append(v("CULTURE-11-03", "mechanism_declared", [m.event_id for m in exc if not m.value.get("cultural_exception")
                                                             or "duration_days" not in m.value or "reversible" not in m.value],
                     "the Cultural Exception declares its scope, duration and reversibility", "{n} mechanisms without these declarations"))
    else:
        for rid, chk in (("CULTURE-9-03", "conflicts_by_scope"), ("CULTURE-11-03", "mechanism_declared")):
            out.append(na(rid, chk, "Cultural Exception", "none declared"))
    aud = [m for m in msgs if m.source == "AUDIT" and "content_audit" in m.value]
    out.append(v("EDU-10-03", "content_auditable", [m.event_id for m in aud if not m.value["allowed"]],
                 f"{len(aud)} audits of educational content under DKP-8-AUDIT-001 allowed", "{n} audits refused")
               if aud else na("EDU-10-03", "content_auditable", "content audits", "none requested"))
    if "profile_learning_data" in r["faults"]:
        out.append(CheckResult("EDU-10-05", "learning_data_protected", FAIL, "individual learning data were reused for profiling"))
    else:
        out.append(CheckResult("EDU-10-05", "learning_data_protected", UNKNOWN,
                               "learning data are minimized and not profiled; EDU §10 protects them 'under DKP-7-SCOPE-001', "
                               "which contains no data-protection rules (F-040, Q-059)"))
    # EDU content: declared modules through the deployment gate
    mods = [m.value for m in msgs if m.source == "EDU" and "edu_module" in m.value]
    dep = [x for x in mods if x["deployed"]]

    def props(pred):
        return [x["edu_module"] for x in dep if pred(x["properties"])]
    if mods:
        refused = len(mods) - len(dep)
        for rid, chk, pred, ok in (
                ("EDU-6-01", "no_mandated_belief", lambda p: p["required_assent"], "no deployed module mandates belief acceptance"),
                ("EDU-6-02", "no_worldview_alignment", lambda p: p["alignment_condition"] == "worldview", "no deployed module requires worldview alignment"),
                ("EDU-9-02", "no_political_conditioning", lambda p: p["alignment_condition"] == "political" or
                 "political_correctness" in p["defines"], "no deployed module conditions on politics or defines political correctness"),
                ("EDU-6-03", "no_conformity_enforcement", lambda p: p["conformity_sanction"], "no deployed module enforces cultural or moral conformity"),
                ("EDU-2-02", "no_ideological_narrative", lambda p: p["ideological_narrative"], "no deployed module imposes an ideological narrative"),
                ("EDU-9-01", "no_indoctrination", lambda p: p["ideological_narrative"] or p["required_assent"],
                 "no deployed module indoctrinates (ideological narrative or required assent)"),
                ("EDU-4-03", "free_of_ideological_enforcement", lambda p: p["required_assent"] or p["alignment_condition"] != "none"
                 or p["conformity_sanction"] or p["ideological_narrative"], "deployed content is free of ideological enforcement"),
                ("EDU-2-03", "no_correctness_definition", lambda p: {"moral_correctness", "political_correctness"} & set(p["defines"]),
                 "no deployed module defines moral or political correctness"),
                ("EDU-1-01", "no_defined_values", lambda p: {"culture", "worldview", "morality", "intelligence", "personal_values"} & set(p["defines"]),
                 "no deployed module defines culture, worldview, morality, intelligence or personal values"),
                ("EDU-11-01", "no_success_definition", lambda p: {"personal_success", "intelligence"} & set(p["defines"]),
                 "no deployed module defines personal success or intelligence"),
                ("EDU-11-03", "no_uniform_path", lambda p: p["path"] != "chosen", "no deployed module enforces a uniform educational path"),
                ("EDU-10-01", "open_or_inspectable", lambda p: p["access"] == "closed", "every deployed module is open-source or publicly inspectable"),
                ("EDU-3-03", "bounded_verifiable_module", lambda p: not (p["bounded"] and p["domain"] and p["verification"] == "observable_performance"),
                 "every deployed module is bounded, verifiable and aimed at one competence domain")):
            out.append(v(rid, chk, props(pred), f"{ok} ({len(dep)} deployed, {refused} refused)", "{n} deployed modules against the rule"))
    else:
        for rid, chk in (("EDU-6-01", "no_mandated_belief"), ("EDU-6-02", "no_worldview_alignment"), ("EDU-9-02", "no_political_conditioning"),
                         ("EDU-6-03", "no_conformity_enforcement"), ("EDU-2-02", "no_ideological_narrative"), ("EDU-9-01", "no_indoctrination"),
                         ("EDU-4-03", "free_of_ideological_enforcement"), ("EDU-2-03", "no_correctness_definition"),
                         ("EDU-1-01", "no_defined_values"), ("EDU-11-01", "no_success_definition"), ("EDU-11-03", "no_uniform_path"),
                         ("EDU-10-01", "open_or_inspectable"), ("EDU-3-03", "bounded_verifiable_module")):
            out.append(na(rid, chk, "educational modules", "none declared"))
    # assessments: reproducible, signals of competence, no ranking, no fault marker
    ev = [m for m in msgs if m.source == "EDU" and m.kind == "evaluation" and "assessment_language" in m.value]
    bad = [m.value["subject"] for m in ev if m.value["method"] != "observable performance" or not m.value["criteria_declared"]
           or m.value["outcome_reproduced"] != m.value["passed"]]
    out.append(v("EDU-3-04", "assessment_event", bad, f"{len(ev)} assessments are open, observable-performance events whose outcome "
                 "is reproduced from the record", "{n} assessments not reproducible or not observable"))
    out.append(v("EDU-4-05", "outcomes_reproducible", [m.value["subject"] for m in ev if m.value["outcome_reproduced"] != m.value["passed"]],
                 "every educational outcome is reproduced from its recorded performance and auditable", "{n} outcomes not reproducible"))
    out.append(v("EDU-7-06", "competence_signals", [m.value["subject"] for m in ev if m.value["signal"] != "competence signal"],
                 "outcomes are published as competence signals only", "{n} outcomes labelled as worth or intelligence"))
    rank = [m.event_id for m in msgs if m.source == "EDU" and "ranking" in m.value]
    out.append(v("EDU-0-01", "not_a_ranking", rank + [m.value["subject"] for m in ev if m.value["signal"] != "competence signal"],
                 "education produced no social ranking and no value judgment of Subjects", "{n} rankings or value labels"))
    marks = [m.value["subject"] for m in msgs if m.source == "EDU" and "fault_marker" in m.value]
    failed = [m for m in ev if not m.value["passed"]]
    out.append(v("EDU-Safeguards-06", "failure_is_signal", marks, f"{len(failed)} failed assessments became corrective signals (remediation), "
                 "none a fault marker", "{n} failures recorded as faults") if failed else
               na("EDU-Safeguards-06", "failure_is_signal", "failed assessments", "none"))
    binding = [m.event_id for m in msgs if m.source == "CULTURE" and m.value.get("enforceable")]
    out.append(v("CULTURE-11-05", "informational_without_l8", binding if not r["l8_bundle_present"] else [],
                 "cultural interactions informational and non-binding (no L8 calibration)", "{n} binding cultural interactions"))
    return out + culture_checks(r, msgs) + returned_checks(r, msgs)


IMPLEMENTS = {
    "CULTURE-5-05": ("language_not_competence_proxy", "IMPLEMENTED", None),
    "EDU-7-04": ("minimal_language_bias", "PARTIAL", "Assessment language only; other bias sources are not modelled."),
    "CULTURE-5-02": ("minority_languages_served", "PARTIAL", "Observed in assessments and interface support."),
    "EDU-9-03": ("no_belief_screening", "IMPLEMENTED", None),
    "EDU-7-05": ("no_ideology_items", "IMPLEMENTED", None),
    "EDU-2-04": ("no_belief_evaluation", "IMPLEMENTED", None),
    "EDU-7-02": ("open_declared_assessment", "PARTIAL", "Declared flags."),
    "EDU-7-03": ("open_declared_assessment", "PARTIAL", "Declared flags."),
    "EDU-10-02": ("open_declared_assessment", "PARTIAL", "Declared flags."),
    "EDU-4-02": ("competence_over_credential", "IMPLEMENTED", None),
    "EDU-9-05": ("no_credential_privilege", "IMPLEMENTED", None),
    "EDU-Safeguards-05": ("free_remediation", "IMPLEMENTED", None),
    "EDU-8-01": ("targeted_modules", "IMPLEMENTED", None),
    "EDU-Safeguards-01": ("no_punishment", "IMPLEMENTED", None),
    "EDU-9-04": ("no_punitive_education", "IMPLEMENTED", None),
    "EDU-8-03": ("support_not_penalty", "IMPLEMENTED", None),
    "EDU-9-06": ("no_penalty_substitution", "IMPLEMENTED", None),
    "EDU-Safeguards-02": ("no_permanent_exclusion", "IMPLEMENTED", None),
    "EDU-8-05": ("no_permanent_denial", "IMPLEMENTED", None),
    "EDU-11-05": ("not_a_rights_gate", "IMPLEMENTED", None),
    "EDU-Safeguards-03": ("legal_status_unchanged", "PARTIAL", "Observed as withheld rights."),
    "EDU-12-04": ("informational_without_l8", "IMPLEMENTED", None),
    "EDU-12-02": ("restriction_calibrated", "IMPLEMENTED", None),
    "EDU-12-01": ("restriction_reversible", "IMPLEMENTED", None),
    "EDU-12-03": ("review_intervals", "PARTIAL", "Confidence bounds come from a hypothetical bundle."),
    "EDU-Safeguards-04": ("only_temporary_restriction", "IMPLEMENTED", None),
    "EDU-10-06": ("learning_data_not_profiled", "IMPLEMENTED", None),
    "EDU-10-04": ("learning_data_minimized", "PARTIAL", "Declared minimization."),
    "CULTURE-8-02": ("no_default_culture", "IMPLEMENTED", None),
    "CULTURE-4.1-03": ("no_reference_culture", "IMPLEMENTED", None),
    "CULTURE-4.1-01": ("no_systemic_priority", "PARTIAL", "Observed as interface defaults."),
    "CULTURE-8-01": ("selectable_context", "IMPLEMENTED", None),
    "CULTURE-4.2-01": ("all_languages_supported", "IMPLEMENTED", None),
    "CULTURE-4.2-02": ("semantic_fidelity", "PARTIAL", "Meaning preservation is declared per translation."),
    "CULTURE-4.3-01": ("no_cultural_optimization", "IMPLEMENTED", None),
    "CULTURE-4.3-02": ("no_cultural_metrics", "IMPLEMENTED", None),
    "CULTURE-0-01": ("no_ranking", "IMPLEMENTED", None),
    "CULTURE-11-01": ("no_enforceable_rankings", "IMPLEMENTED", None),
    "CULTURE-7-01": ("voluntary_participation", "IMPLEMENTED", None),
    "CULTURE-6-02": ("no_obligations_from_preservation", "IMPLEMENTED", None),
    "CULTURE-9-02": ("exception_bounded", "IMPLEMENTED", None),
    "CULTURE-2-02": ("no_doctrine", "PARTIAL", "Observed through declared requests and CULTURE records."),
    "CULTURE-4.3-03": ("persistence_without_justification", "PARTIAL", "Persistence support is a recorded per-language decision."),
    "CULTURE-5-01": ("no_conformity_enforcement", "PARTIAL", "Observed through declared requests and CULTURE records."),
    "CULTURE-7-03": ("neutrality_both_ways", "PARTIAL", "Neutrality observed as identical per-language treatment."),
    # returned to work after the reading of the Codex-draft open points (review of checkpoint 6)
    "CULTURE-4.1-02": ("language_agnostic", "PARTIAL", "Metamorphic over the declared Subjects: outcomes with every Subject in the dominant language."),
    "CULTURE-7-02": ("affiliation_affects_nothing", "PARTIAL", "Affiliation = declared language and minority status; metamorphic comparison."),
    "CULTURE-5-03": ("no_assimilation_incentive", "PARTIAL", "Observed as incentives with a cultural condition."),
    "EDU-2-05": ("no_worldview_gate", "PARTIAL", "Observed as access decisions whose basis is opinion or worldview."),
    "EDU-8-04": ("not_disciplinary", "PARTIAL", "Observed as penalties, exclusions or withheld rights following assessments."),
    "CULTURE-9-03": ("conflicts_by_scope", "PARTIAL", "Observed as the rules named for the Cultural Exception."),
    "CULTURE-11-03": ("mechanism_declared", "PARTIAL", "The Cultural Exception is the mechanism modelled."),
    "EDU-10-03": ("content_auditable", "PARTIAL", "Audit requests are declared."),
    "EDU-10-05": ("learning_data_protected", "PARTIAL", "Referenced rules are absent from SCOPE (F-040)."),
    "EDU-6-01": ("no_mandated_belief", "PARTIAL", "Module properties are declared."),
    "EDU-6-02": ("no_worldview_alignment", "PARTIAL", "Module properties are declared."),
    "EDU-9-02": ("no_political_conditioning", "PARTIAL", "Module properties are declared."),
    "EDU-6-03": ("no_conformity_enforcement", "PARTIAL", "Module properties are declared."),
    "EDU-2-02": ("no_ideological_narrative", "PARTIAL", "Module properties are declared."),
    "EDU-9-01": ("no_indoctrination", "PARTIAL", "Indoctrination observed as an ideological narrative or required assent."),
    "EDU-4-03": ("free_of_ideological_enforcement", "PARTIAL", "Module properties are declared."),
    "EDU-2-03": ("no_correctness_definition", "PARTIAL", "Module properties are declared."),
    "EDU-1-01": ("no_defined_values", "PARTIAL", "Module properties are declared."),
    "EDU-11-01": ("no_success_definition", "PARTIAL", "Module properties are declared."),
    "EDU-11-03": ("no_uniform_path", "PARTIAL", "Module properties are declared."),
    "EDU-10-01": ("open_or_inspectable", "PARTIAL", "Access is declared."),
    "EDU-3-03": ("bounded_verifiable_module", "PARTIAL", "Boundaries and verification method are declared."),
    "EDU-3-04": ("assessment_event", "PARTIAL", "Performance is a declared outcome; the outcome is recomputed from it."),
    "EDU-4-05": ("outcomes_reproducible", "PARTIAL", "Performance is a declared outcome; the outcome is recomputed from it."),
    "EDU-7-06": ("competence_signals", "IMPLEMENTED", None),
    "EDU-0-01": ("not_a_ranking", "IMPLEMENTED", None),
    "EDU-Safeguards-06": ("failure_is_signal", "IMPLEMENTED", None),
    "CULTURE-3-02": ("exception_non_enforceable", "IMPLEMENTED", None),
    "CULTURE-9-04": ("no_verification_exemption", "IMPLEMENTED", None),
    "CULTURE-9-01": ("no_override_of_ptl", "PARTIAL", "Observed as exemption of a factual claim."),
    "CULTURE-11-05": ("informational_without_l8", "PARTIAL", "No binding cultural mechanism is modelled."),
}


class EduCultureModule(LabModule):
    id = "edu_culture"
    version = "1.2.0"
    title = {"en": "Education and culture (EDU, CULTURE)", "ru": "Образование и культура (EDU, CULTURE)"}
    summary = {"en": "A population speaking several languages takes the system-literacy assessment: does failing only bring "
                     "help, does no language or culture get priority, and does anything restrict people while L8 is uncalibrated?",
               "ru": "Население на нескольких языках проходит оценку системной грамотности: приносит ли провал только помощь, "
                     "не получает ли какой-то язык или культура приоритет и ограничивается ли кто-то, пока L8 не откалиброван?"}
    protocols = ["DKP-5-EDU-001", "DKP-5-CULTURE-001", "DKP-8-SIMULATION-001"]
    example_order = ["population", "hypothetical_calibration", "cultural_exception", "faulty_education"]
    alternative_examples = ["hypothetical_calibration"]
    implements = IMPLEMENTS
    tests = ["tests/lab/test_edu_culture_module.py"]
    causal_note = None
    hypotheses = [
        {"id": "H-EC-1", "source": "hypothesis", "text": {
            "en": "Assessment results, languages, credentials and translation fidelity are declared; the module checks how the "
                  "system responds to them.",
            "ru": "Результаты оценки, языки, дипломы и точность перевода объявляются; модуль проверяет реакцию системы на них."}},
        {"id": "H-EC-2", "source": "missing", "text": {
            "en": "No L8 calibration exists for competence-based restrictions (EDU §12); a bundle can only be declared as a "
                  "labelled hypothesis.",
            "ru": "Калибровки L8 для ограничений по компетенции (EDU §12) нет; пакет можно объявить только как помеченную гипотезу."}},
    ]
    inputs = {
        "subjects": {"type": "list", "min_items": 1, "max_items": 50, "items": SUBJECT, "source": "user",
                     "default": [full_subject(id="s1", language="lang_a"), full_subject(id="s2", language="lang_b", minority=True),
                                 full_subject(id="s3", language="lang_a", literacy_passed=False),
                                 full_subject(id="s4", language="lang_c", minority=True, literacy_passed=False, failures=2),
                                 full_subject(id="s5", language="lang_a", credential=True, literacy_passed=False)],
                     "label": {"en": "Subjects (H-EC-1)", "ru": "Субъекты (H-EC-1)"}},
        "dominant_language": {"type": "str", "default": "lang_a", "source": "user",
                              "label": {"en": "Most widespread language", "ru": "Самый распространённый язык"}},
        "translations": {"type": "list", "min_items": 0, "max_items": 20, "items": TRANSLATION, "source": "user",
                         "default": [{"source": "lang_a", "target": "lang_b", "meaning_preserved": True},
                                     {"source": "lang_a", "target": "lang_c", "meaning_preserved": False}],
                         "label": {"en": "Translations", "ru": "Переводы"}},
        "l8_bundle_present": {"type": "bool", "default": False, "source": "missing",
                              "label": {"en": "L8 calibration for competence restrictions (none exists; H-EC-2)",
                                        "ru": "Калибровка L8 для ограничений (не существует; H-EC-2)"}},
        "edu_modules": {"type": "list", "min_items": 0, "max_items": 20, "items": MODULE, "default": MODULES_DEFAULT, "source": "user",
                        "label": {"en": "Educational modules proposed for deployment (properties declared)",
                                  "ru": "Учебные модули к развёртыванию (свойства объявлены)"}},
        "content_audits": {"type": "int", "min": 0, "max": 20, "default": 1, "source": "user",
                           "label": {"en": "Audits of educational content requested (EDU §10)", "ru": "Запрошено аудитов учебного содержания (EDU §10)"}},
        "culture_requests": {"type": "list", "min_items": 0, "max_items": len(CULTURE_REQUESTS),
                             "items": {"type": "enum", "values": list(CULTURE_REQUESTS)}, "default": list(CULTURE_REQUESTS),
                             "source": "user", "label": {"en": "Requests CULTURE §2, §4.3, §5 exclude",
                                                         "ru": "Запросы, исключённые CULTURE §2, §4.3, §5"}},
        "cultural_exception": {"type": "object", "fields": EXCEPTION, "default": {k: f["default"] for k, f in EXCEPTION.items()},
                               "source": "user", "label": {"en": "Cultural Exception", "ru": "Культурное исключение"}},
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
        names = ids + [s["language"] for s in r["subjects"]] + [r["dominant_language"], r["cultural_exception"]["scope"]] + \
            [x for t in r["translations"] for x in (t["source"], t["target"])]
        for x in names:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", x):
                p.append(f"input: identifier {x!r} must be lowercase letters, digits or _")
        if len(set(r["faults"])) != len(r["faults"]):
            p.append("input.faults: repeated fault")
        if p:
            raise LabInputError(p)
        return r

    def evaluate(self, r: Dict[str, Any]) -> ModuleResult:
        log = run(r)
        res = checks(r, log)
        msgs = log.messages()
        outputs = {"assessments": [m.value for m in msgs if m.source == "EDU" and m.kind == "evaluation"],
                   "responses": [m.value for m in msgs if m.source == "EDU" and m.kind in ("action", "notice")],
                   "culture": [m.value for m in msgs if m.source in ("CULTURE", "INTERFACE")],
                   "event_log": {"time_unit": log.time_unit, "messages": len(log), "digest": log.digest()}}
        failed = [a["subject"] for a in outputs["assessments"] if not a["passed"]]
        e = [{"en": f"{len(failed)} of {len(r['subjects'])} Subjects failed the assessment ({', '.join(failed) or 'none'}); "
                    + ("they received free remediation and no restriction (no L8 calibration)."
                       if not r["l8_bundle_present"] else "temporary, reviewed restrictions under the declared bundle."),
              "ru": f"{len(failed)} из {len(r['subjects'])} не прошли оценку ({', '.join(failed) or 'нет'}); "
                    + ("им предложено бесплатное обучение, ограничений нет (нет калибровки L8)."
                       if not r["l8_bundle_present"] else "временные ограничения с пересмотром по объявленному пакету.")}]
        return ModuleResult(outputs=outputs, checks=res, explain=e)

    def comparison_metrics(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"failed": sum(1 for a in outputs["assessments"] if not a["passed"]),
                "restricted": sum(1 for x in outputs["responses"] if x.get("advanced_functions") == "temporarily restricted")}

    def examples(self) -> Dict[str, Dict[str, Any]]:
        return {
            "population": {},
            "hypothetical_calibration": {"l8_bundle_present": True},
            "cultural_exception": {"cultural_exception": {"declared": True, "days": 7, "scope": "festival_zone",
                                                          "touches_factual_claim": True}},
            "faulty_education": {"faults": ["punish_literacy_failure", "belief_screening", "language_as_competence",
                                             "cultural_ranking", "default_dominant_language"]},
            "faulty_content": {"faults": ["admit_any_module", "rank_by_assessment", "label_as_intelligence", "failure_as_fault",
                                          "nonreproducible_assessment"]},
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_id": {"subjects": [{"id": "a"}, {"id": "a"}]},
                "bad_language": {"subjects": [{"id": "a", "language": "English!"}]},
                "negative_failures": {"subjects": [{"id": "a", "failures": -1}]}}


for _spec in EduCultureModule.inputs.values():
    if _spec["type"] == "list" and _spec["items"]["type"] == "object":
        _spec["default"] = [resolve(x, _spec["items"]["fields"]) for x in _spec["default"]]
