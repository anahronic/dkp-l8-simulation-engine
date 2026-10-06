"""CALIBRATION EXPIRY module (S-LAB-05): bundle validity, expiry handling, recalibration, counterexamples."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.calibration_expiry import FAULTS, CalibrationExpiryModule

M = CalibrationExpiryModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


UNSIGNED = {"bundle": {"signed": False}, "recalibration_day": -1}
FAULT_CASES = {
    "enforce_after_expiry": ({}, ["SIMULATION-10-02", "SIMULATION-4-02"]),
    "legacy_threshold": ({}, ["SIMULATION-CalibrationExpirationEpistemicHandling-03"]),
    "manual_interpretation": (UNSIGNED, ["HABITAT-6-03"]),
    "unsigned_bundle_used": ({"bundle": {"signed": False}}, ["SIMULATION-9-01", "SIMULATION-4-02"]),
    "global_halt_on_expiry": ({}, ["CRISISPATCH-2-01"]),
    "reactivate_old_outputs": ({}, ["ETRANS-4.4-02"]),
    "override_failed_simulation": ({"recalibration_passes": False}, ["SIMULATION-12-01"]),
    "forced_displacement": ({}, ["HABITAT-10-04"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    extra, expected = FAULT_CASES[fault]
    clean, broken = statuses(run(**extra)), statuses(run(**extra, faults=[fault]))
    for rid in expected:
        assert clean[rid] in ("PASS", "NOT_APPLICABLE"), (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_expiry_invalidates_without_global_halt():
    res = run()
    assert res.outputs["invalid_output_days"] == 15 and not res.outputs["global_halt"]       # days 60-74 until recalibration
    st = statuses(res)
    assert st["SIMULATION-CalibrationExpirationEpistemicHandling-01"] == "PASS"
    assert st["SIMULATION-CalibrationExpirationEpistemicHandling-02"] == "PASS"


def test_without_any_bundle_nothing_is_enforced():
    res = run(**M.examples()["never_calibrated"])
    assert res.outputs["remediations"] == [] and res.outputs["valid_output_days"] == 0


def test_drift_readings():
    kept = run(**M.examples()["drift_kept_until_expiry"])
    held = run(**M.examples()["drift_suspends"])
    assert statuses(kept)["SIMULATION-10-01"] == "UNKNOWN"
    assert held.outputs["invalid_output_days"] > kept.outputs["invalid_output_days"]


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
