"""WORK-CYCLE module: Cycle6 rosters and 24/7 coverage (scenario S-LAB-08)."""

import pytest

from lab.core.checks import FAIL, NOT_APPLICABLE, PASS, UNKNOWN
from lab.core.schema import LabInputError
from lab.modules.work_cycle import WorkCycleModule

M = WorkCycleModule()


def run(**inp):
    r = M.evaluate(M.validate(inp))
    return {c.requirement_id: c.status for c in r.checks}, r.outputs


def test_staffed_default_covers_every_hour():
    st, out = run()
    assert out["coverage"]["deficit_hours"] == 0
    assert st["WORKCYCLE-8.1-01"] == PASS and st["WORKCYCLE-7-01"] == PASS
    assert not [k for k, v in st.items() if v == FAIL]


def test_understaffed_shows_deficit():
    st, out = run(workers=10)
    assert out["coverage"]["deficit_hours"] > 0 and st["WORKCYCLE-8.1-01"] == FAIL
    assert out["workers_lower_bound_flat"] == 18         # 4 staff × 24 h / 8 h / (4/6)


def test_three_consecutive_workdays_is_a_planning_failure():
    st, _ = run(pattern=["W", "W", "W", "R", "W", "R"])
    assert st["WORKCYCLE-4.2-01"] == FAIL and st["WORKCYCLE-7-01"] == FAIL and st["WORKCYCLE-8.1-02"] == FAIL
    assert st["WORKCYCLE-7-02"] == PASS                  # reported against the roster, not a worker
    st2, _ = run(pattern=["W", "W", "W", "R", "W", "R"], compensation_declared=True)
    assert st2["WORKCYCLE-7-01"] == UNKNOWN


def test_aligned_phases_leave_rest_days_unstaffed():
    _, out = run(phase_offsets="aligned")
    assert out["coverage"]["deficit_hours"] > 0


def test_changed_text_values_fail_the_allocation_checks():
    st, _ = run(presence_hours=10, work_hours=7, recovery_hours=3, work_before_recovery=4)
    assert st["WORKCYCLE-5.1-01"] == FAIL and st["WORKCYCLE-5.2-01"] == NOT_APPLICABLE


def test_year_accounting_on_a_full_year():
    st, _ = run(horizon_days=360, workers=6, shift_starts=[0])
    assert st["WORKCYCLE-6-03"] == PASS


def test_invalid_inputs_refused():
    for inp in M.failure_examples().values():
        with pytest.raises(LabInputError):
            M.validate(inp)
    with pytest.raises(LabInputError):
        M.validate({"demand": [1] * 23})


def test_refusal_is_respected_and_not_punished():
    """LABOR §9.1: outside a declared crisis refusing workers are not scheduled and not penalised."""
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"refusing_workers": 6})).checks}
    assert (st["LABOR-9.1-01"], st["LABOR-9.1-02"], st["LABOR-6-01"]) == ("PASS", "PASS", "PASS")
    for fault, rid in (("assign_refusers", "LABOR-9.1-01"), ("penalize_refusal", "LABOR-9.1-02")):
        st = {c.requirement_id: c.status for c in M.evaluate(M.validate({"refusing_workers": 6, "faults": [fault]})).checks}
        assert st[rid] == "FAIL", fault


def test_roster_days_are_dti_labels():
    res = M.evaluate(M.validate({"start_dti_day": 2461042, "horizon_days": 6}))
    assert res.outputs["roster_days"][0] == "DY6836-083"
    assert {c.requirement_id: c.status for c in res.checks}["TIME-5.1-01"] == "PASS"


from lab.modules.work_cycle import FAULTS  # noqa: E402


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    base = {"refusing_workers": 6} if fault in ("assign_refusers", "penalize_refusal") else \
        {"refusing_workers": 6, "crisis_window": [3, 7]} if fault in ("permanent_obligation", "post_crisis_penalty") else {}
    clean = {c.requirement_id: c.status for c in M.evaluate(M.validate(base)).checks}
    broken = {c.requirement_id: c.status for c in M.evaluate(M.validate(dict(base, faults=[fault]))).checks}
    assert any(broken[k] == "FAIL" and clean[k] == "PASS" for k in broken), fault


def test_one_year_recovery_and_cycles():
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(M.examples()["one_year"])).checks}
    assert st["WORKCYCLE-6-03"] == st["WORKCYCLE-6-04"] == st["WORKCYCLE-4.2-03"] == "PASS"


def test_recovery_requests():
    d = {x["request"]: x for x in M.evaluate(M.validate({})).outputs["recovery_requests"]}
    assert not d["monetize"]["granted"] and not d["work_task"]["granted"]
    assert d["meal"]["granted"] and not d["meal"]["justification_required"]


def test_crisis_draft_is_time_limited():
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(M.examples()["crisis_draft"])).checks}
    assert st["LABOR-9.1-01"] == st["LABOR-9.2-03"] == "PASS"
    st = {c.requirement_id: c.status for c in M.evaluate(M.validate(M.examples()["crisis_draft_faulty"])).checks}
    assert st["LABOR-9.2-03"] == "FAIL"
