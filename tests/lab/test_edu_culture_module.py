"""EDU and CULTURE module: failures bring help, nothing binds without L8, no language or culture has priority."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.edu_culture import FAULTS, EduCultureModule

M = EduCultureModule()
EX = M.examples()
EXC = EX["cultural_exception"]
CAL = EX["hypothetical_calibration"]


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) in ("reference", "alternative")])
def test_examples_break_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "punish_literacy_failure": ({}, ["EDU-Safeguards-01", "EDU-9-04"]),
    "permanent_exclusion": ({}, ["EDU-Safeguards-02", "EDU-8-05"]),
    "gate_basic_rights": ({}, ["EDU-11-05"]),
    "restrict_without_bundle": ({}, ["EDU-12-04", "EDU-12-02"]),
    "irreversible_restriction": (CAL, ["EDU-12-01", "EDU-12-03"]),
    "no_remediation": ({}, ["EDU-Safeguards-05", "EDU-8-01"]),
    "belief_screening": ({}, ["EDU-9-03", "EDU-7-05", "EDU-2-04"]),
    "credential_privilege": ({}, ["EDU-4-02", "EDU-9-05"]),
    "profile_learning_data": ({}, ["EDU-10-06"]),
    "language_as_competence": ({}, ["CULTURE-5-05", "EDU-7-04"]),
    "cultural_ranking": ({}, ["CULTURE-4.3-01", "CULTURE-4.3-02", "CULTURE-0-01"]),
    "default_dominant_language": ({}, ["CULTURE-8-02", "CULTURE-4.1-03"]),
    "lossy_translation": ({}, ["CULTURE-4.2-02"]),
    "mandatory_participation": ({}, ["CULTURE-7-01", "CULTURE-6-02"]),
    "exception_enforced": (EXC, ["CULTURE-9-02", "CULTURE-3-02"]),
    "culture_exempts_claim": (EXC, ["CULTURE-9-04"]),
    "culture_resolves_conflict": (EXC, ["CULTURE-9-03"]),
    "undeclared_mechanism": (EXC, ["CULTURE-11-03"]),
    "audit_refused": ({}, ["EDU-10-03"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    base, expected = FAULT_CASES[fault]
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    for rid in expected:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_failures_bring_help_and_no_restriction_without_l8():
    out = run().outputs
    assert sum(1 for x in out["responses"] if x.get("remediation")) == 3
    assert not any(x.get("advanced_functions") == "temporarily restricted" for x in out["responses"])
    cal = run(**CAL).outputs
    assert sum(1 for x in cal["responses"] if x.get("advanced_functions") == "temporarily restricted") == 3


def test_minority_language_assessed_in_its_own_language():
    a = {x["subject"]: x["assessment_language"] for x in run().outputs["assessments"]}
    assert a["s4"] == "lang_c" and a["s2"] == "lang_b"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
