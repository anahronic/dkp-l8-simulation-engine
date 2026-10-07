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
from lab.core.schema import LabInputError

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
EXCEPTION = {"declared": {"type": "bool", "default": False},
             "days": {"type": "int", "min": 0, "max": 3650, "default": 10},
             "scope": {"type": "str", "default": "festival_zone"},
             "touches_factual_claim": {"type": "bool", "default": False}}


def full_subject(**kw):
    return {**{k: f["default"] for k, f in SUBJECT["fields"].items() if "default" in f}, **kw}


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
                                         "signal": "competence signal"})
        if s["credential"] and "credential_privilege" in faults:
            put("action", "EDU", 1, {"subject": s["id"], "advanced_access": "granted by diploma"}, [a.event_id])
        if not passed:
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
    for t in r["translations"]:
        use = t["meaning_preserved"] or "lossy_translation" in faults
        put("action" if use else "notice", "CULTURE", 3, {"translation": f"{t['source']}->{t['target']}",
                                                          "meaning_preserved": t["meaning_preserved"], "used": use,
                                                          "reason": None if use else "lossy translation refused (§4.2)"})
    put("evaluation", "CULTURE", 4, {"metrics": ["interface availability per language", "access neutrality"] +
                                     (["culture efficiency ranking"] if "cultural_ranking" in faults else [])})
    put("action", "CULTURE", 4, {"programme": "minority archive", "participation": "mandatory" if "mandatory_participation" in faults
                                 else "voluntary", "self_identification_required": False})
    ex = r["cultural_exception"]
    if ex["declared"]:
        enforced = "exception_enforced" in faults
        put("notice", "CULTURE", 5, {"cultural_exception": ex["scope"], "temporary": not enforced,
                                     "until_day": None if enforced else 5 + ex["days"], "enforceable": enforced, "logged": True,
                                     "exempts_factual_claim": ex["touches_factual_claim"] and "culture_exempts_claim" in faults,
                                     "conflict_rules": "DKP-7-SCOPE-001"})
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
    binding = [m.event_id for m in msgs if m.source == "CULTURE" and m.value.get("enforceable")]
    out.append(v("CULTURE-11-05", "informational_without_l8", binding if not r["l8_bundle_present"] else [],
                 "cultural interactions informational and non-binding (no L8 calibration)", "{n} binding cultural interactions"))
    return out


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
    "CULTURE-3-02": ("exception_non_enforceable", "IMPLEMENTED", None),
    "CULTURE-9-04": ("no_verification_exemption", "IMPLEMENTED", None),
    "CULTURE-9-01": ("no_override_of_ptl", "PARTIAL", "Observed as exemption of a factual claim."),
    "CULTURE-11-05": ("informational_without_l8", "PARTIAL", "No binding cultural mechanism is modelled."),
}


class EduCultureModule(LabModule):
    id = "edu_culture"
    version = "1.0.0"
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
        }

    def failure_examples(self) -> Dict[str, Dict[str, Any]]:
        return {"repeated_id": {"subjects": [{"id": "a"}, {"id": "a"}]},
                "bad_language": {"subjects": [{"id": "a", "language": "English!"}]},
                "negative_failures": {"subjects": [{"id": "a", "failures": -1}]}}
