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
