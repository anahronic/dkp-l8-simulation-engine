"""EPISTEMIC GATE module: outputs stay bounded, complete, disputable evaluations (EB §4-§13)."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.epistemic_gate import FAULTS, EpistemicGateModule

M = EpistemicGateModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "audit_only_enforcement": ["EB-5.x-08", "EB-5.x-07", "EB-5.x-02"],
    "propagate_incomplete": ["EB-5.x-04"],
    "repair_downstream": ["EB-5.x-06"],
    "conditional_fallback": ["EB-5.x-05"],
    "scope_drift": ["EB-4-02"],
    "degraded_in_critical": ["EB-10-01"],
    "truth_reading": ["EB-12-01", "EB-4-01"],
    "mutate_on_dispute": ["EB-7.2-01"],
    "no_delta": ["EB-7.2-04"],
    "suppress_dispute": ["EB-3-01", "EB-6-01"],
    "silence_invalidates": ["EB-9-02"],
    "keep_stale_active": ["EB-4-04", "EB-3-03"],
    "final_output": ["EB-6-01"],
    "skip_l8_tests": ["EB-13-01"],
    "allow_override": ["EB-0-01"],
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_production_layer_marks_incomplete_outputs():
    o = {x["output"]: x for x in run().outputs["outputs"]}
    assert o["asset_revoke"]["operational_validity"] == "INVALID"     # scope_ref undefined
    assert o["labor_score"]["operational_validity"] == "INVALID"      # LABOR declares no no-output conditions
    assert o["fire_alert"]["emitted"] == "NO_OUTPUT"                  # critical and degraded
    assert o["quiet_sensor"]["reliability"] == "maintained" and o["air_index"]["reliability"] == "degraded"


def test_dispute_keeps_original_and_reports_delta():
    d = {x["output"]: x for x in run().outputs["disputes"] if x["accepted"]}
    assert d["water_quota"]["original"] == 1.0 and d["water_quota"]["delta"] == -0.2
    assert d["water_quota"]["executed_consequences"].startswith("not rolled back")


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
