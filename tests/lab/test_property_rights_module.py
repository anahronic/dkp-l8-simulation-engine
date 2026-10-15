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
    "absolute_right": ["ASSETS-3.2-01", "ASSETS-1-01", "ASSETS-5-02", "ASSETS-5-01", "ASSETS-9-02"],
    "grant_by_possession": ["ASSETS-4-02", "ASSETS-1-01"],
    "privatize_commons": ["ASSETS-9-01"],
    "ignore_concentration": ["ASSETS-7-01"],
    "no_suspension_on_failure": ["ASSETS-3.2-01", "ASSETS-5-02", "ASSETS-5-01"],
    "anonymous_holding": ["ASSETS-12-01"],
    "assets_overrides": ["ASSETS-13-01", "ASSETS-1-01", "ASSETS-1-02", "ASSETS-4-01"],
    "only_requesting_right": ["ASSETS-3.2-01", "ASSETS-5-02", "ASSETS-5-01"],
    "assets_feed_ptl": ["ASSETS-2-01"],
    "transfer_drops_attribution": ["ASSETS-6-01"],
    "price_threshold": ["ASSETS-7-02"],
}
TWO_RIGHTS = {"horizon_days": 3, "holdings": [],
              "requests": [{"id": "q1", "subject": "s", "asset": "a1", "condition_fails_day": 0},
                           {"id": "q2", "subject": "s", "asset": "a2", "condition_fails_day": -1}]}
EXTRA = {"only_requesting_right": TWO_RIGHTS, "transfer_drops_attribution": {"transfers": [{"request": "q1", "to": "coop_b", "day": 2}]}}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    extra = EXTRA.get(fault, {})
    clean, broken = statuses(run(**extra)), statuses(run(**extra, faults=[fault]))
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


@pytest.mark.parametrize("same_subject", [True, False])
@pytest.mark.parametrize("day", [0, 1])
def test_kt7_02_justice_result_reaches_every_right_of_the_subject(same_subject, day):
    """Review КТ7-GPT-02: a negative Justice result of a Subject degrades all its active rights; another Subject's right
    is untouched.  Both checks of the condition (ASSETS-3.2-01, -5-02) agree."""
    inp = {"horizon_days": 3, "holdings": [],
           "requests": [{"id": "q1", "subject": "s", "asset": "a1", "condition_fails_day": day},
                        {"id": "q2", "subject": "s" if same_subject else "t", "asset": "a2", "condition_fails_day": -1}]}
    res = run(**inp)
    st = statuses(res)
    assert st["ASSETS-3.2-01"] == st["ASSETS-5-02"] == "PASS"
    suspended = [m for m in res.outputs["messages"] if m["value"].get("status") == "suspended"]
    assert len(suspended) == (2 if same_subject else 1) and all(m["arrived_at"] == day for m in suspended)


def test_kt7_02_removed_reaction_is_found_by_both_checks():
    """Negative journal mutation: drop the suspension of the second right of the same Subject."""
    from lab.core.bus import EventLog
    from lab.modules import property_rights as pr
    r = M.validate(TWO_RIGHTS)
    log = pr.run(r)
    g2 = next(m.event_id for m in log.messages() if m.source == "ASSETS" and m.kind == "decision" and m.value.get("request") == "q2")
    bad = EventLog(log.time_unit, tie_rule=log.tie_rule)
    for m in log.messages():
        if not (m.value.get("status") == "suspended" and m.value.get("right") == g2):
            bad.append(m)
    st = {c.requirement_id: c.status for c in pr.checks(r, bad)}
    assert st["ASSETS-3.2-01"] == st["ASSETS-5-02"] == "FAIL"


def test_kt7_02_use_condition_concerns_one_right():
    """A failed use condition is declared for one right; the Subject's other right stays in force."""
    res = run(horizon_days=3, holdings=[], requests=[
        {"id": "q1", "subject": "s", "asset": "a1", "condition_fails_day": 0, "failure_kind": "asset_use"},
        {"id": "q2", "subject": "s", "asset": "a2"}])
    st = statuses(res)
    assert st["ASSETS-3.2-01"] == st["ASSETS-5-02"] == "PASS"
    assert len([m for m in res.outputs["messages"] if m["value"].get("status") == "suspended"]) == 1
