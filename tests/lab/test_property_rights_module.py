"""PROPERTY RIGHTS module: granting under ASSETS §4, conditional rights (§3.2, §5), §7 responses, §9 critical assets."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.property_rights import CRITICAL, FAULTS, PropertyRightsModule

M = PropertyRightsModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


FAULT_CASES = {
    "absolute_right": ["ASSETS-3.2-01"],
    "grant_by_possession": ["ASSETS-4-02"],
    "privatize_commons": ["ASSETS-9-01"],
    "ignore_concentration": ["ASSETS-7-01"],
    "no_suspension_on_failure": ["ASSETS-3.2-01"],
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_grants_follow_section_4():
    """q1 meets a-d; q2/q3 rest on an excluded basis; q4 is water (stewardship); q5 has a negative justice contribution."""
    res = run()
    assert res.outputs["granted"] == ["q1", "q4"] and res.outputs["refused"] == ["q2", "q3", "q5"]
    np = run(critical_designation={c: "non_privatizable" for c in CRITICAL})
    assert "q4" in np.outputs["refused"] and statuses(np)["ASSETS-9-01"] == "PASS"


def test_nothing_to_judge_is_not_applicable():
    st = statuses(run(requests=[], holdings=[]))
    assert all(v == "NOT_APPLICABLE" for v in st.values())


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


@pytest.mark.parametrize("day,suspended", [(-1, 0), (0, 1), (1, 1)])
def test_kt6_02_condition_failure_on_every_day_including_the_grant_day(day, suspended):
    """Review КТ6-GPT-02: -1 means no failure; 0 is the grant day and is handled like any other day (ASSETS §5)."""
    inp = {"horizon_days": 3, "requests": [{"id": "q", "subject": "s", "asset": "a", "condition_fails_day": day}], "holdings": []}
    res = run(**inp)
    susp = [x for x in res.outputs["messages"] if x.get("source") == "ASSETS" and (x.get("value") or {}).get("status") == "suspended"]
    assert len(susp) == suspended and statuses(res)["ASSETS-3.2-01"] == "PASS"
    broken = statuses(run(**inp, faults=["no_suspension_on_failure"]))["ASSETS-3.2-01"]
    assert broken == ("PASS" if day == -1 else "FAIL")                          # only the suspension is missing
