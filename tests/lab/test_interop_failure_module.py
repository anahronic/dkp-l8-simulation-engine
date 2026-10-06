"""INTEROP FAILURE module (S-LAB-10): boundary rules, unchanged internal execution, mirror conflict (F-013)."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.interop_failure import FAULTS, InteropFailureModule

M = InteropFailureModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", ["external_outage", "tolerance_missing"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


FAULT_CASES = {
    "binding_external_ruling": ["INTEROP-5-02", "INTEROP-9-02"],
    "unflagged_external_value": ["INTEROP-6-04"],
    "blackbox_authoritative": ["INTEROP-7-04"],
    "info_substitutes_ptl": ["INTEROP-8-02"],
    "external_dependency": ["INTEROP-10-02", "INTEROP-10-03", "INTEROP-9-02"],
    "alter_mirror": ["RESILIENCE-5.3-03"],
    "keep_bad_entry_point": ["RESILIENCE-5.7-03"],
    "rollback_on_failure": ["INTEROP-9-03"],
    "audit_masks": ["AUDIT-EpistemicMetadataVerification-04"],
    "audit_modifies": ["AUDIT-10-01"],
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_mirror_failure_conflict():
    """F-013: losing a mirrored oracle beyond tolerance violates CRISIS §4 or INTEROP §9, whichever rule is followed."""
    interop = run(mirror_sources=4, ptl_loss_tolerance=0.25)
    ptl = run(mirror_sources=4, ptl_loss_tolerance=0.25, interop_crisis_reading="ptl_rule")
    assert statuses(interop)["CRISIS-4-01"] == "FAIL" and statuses(interop)["INTEROP-9-04"] == "PASS"
    assert statuses(ptl)["INTEROP-9-04"] == "FAIL" and statuses(ptl)["CRISIS-4-01"] == "PASS"
    assert ptl.outputs["internal_decisions"] == 16 and interop.outputs["internal_decisions"] == 24


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
