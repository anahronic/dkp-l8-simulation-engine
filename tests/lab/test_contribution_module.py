"""CONTRIBUTION module (S-LAB-01): Contribution Records from the unchanged PREVENTION bench."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.contribution import FAULTS, NOT_MONEY, ContributionModule

M = ContributionModule()
ADV = {"base": "main", "num_days": 5, "include_adversarial": True}


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(M.evaluate(M.validate(M.examples()[name]))).values()


FAULT_CASES = {
    "recognize_unattributed": ["LABOR-3.1-01", "LABOR-3.2-02", "IDENTITY-4.1-03"],
    "count_declared_claims": ["LABOR-5.2-02"],
    "reward_self_induced": ["PREV-9.1-01"],
    "fictitious_subject": ["LABOR-11-02"],
    "mutate_record": ["LABOR-3.3-01"],
    "strip_metadata": ["EB-5.x-01"],
    "ignore_inconsistency": ["LABOR-2-02"],
    "accept_stale": ["ORACLE-9-02"],
    "wrong_time_index": ["TIME-5.2-01"],
}
STALE = {"num_days": 5, "arrival_delay_seconds": [0.1, 5.0], "ttl_reference": "decision"}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    base = STALE if fault == "accept_stale" else ADV
    clean = statuses(M.evaluate(M.validate(base)))
    broken = statuses(M.evaluate(M.validate({**base, "faults": [fault]})))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_recognition_is_not_money_and_functions_stay_unknown():
    res = M.evaluate(M.validate({}))
    assert res.outputs["recognition_by_subject"]["unit"] == NOT_MONEY
    st = statuses(res)
    assert st["LABOR-8.1-02"] == st["LABOR-5.2-01"] == "UNKNOWN"
    assert all(c["justice_adjustment"].startswith("not computed") for c in res.outputs["contribution_records"])


def test_bench_is_unchanged_and_records_match_positive_results():
    """Recognition equals the bench's own POSITIVE totals: the module adds records, never SPD."""
    res = M.evaluate(M.validate(ADV))
    totals = res.outputs["bench_summary"]["subject_totals"]
    rec = res.outputs["recognition_by_subject"]["values"]
    for subject, spd in rec.items():
        assert abs(spd - totals[subject]) < 1e-9


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
