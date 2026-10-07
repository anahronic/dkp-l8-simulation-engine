"""INTEROP FAILURE module (S-LAB-10): boundary rules, unchanged internal execution, roles of a provider's sources (F-013)."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.interop_failure import FAULTS, InteropFailureModule

M = InteropFailureModule()
REG = {"mirror_sources": 4, "ptl_loss_tolerance": 0.25, "mirror_role": "registered_ptl_source"}


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


FAULT_CASES = {
    "binding_external_ruling": ({}, ["INTEROP-5-02", "INTEROP-9-02"]),
    "unflagged_external_value": ({}, ["INTEROP-6-04"]),
    "blackbox_authoritative": ({}, ["INTEROP-7-04"]),
    "info_substitutes_ptl": ({}, ["INTEROP-8-02"]),
    "external_dependency": ({}, ["INTEROP-10-02", "INTEROP-10-03", "INTEROP-9-02"]),
    "alter_mirror": ({}, ["RESILIENCE-5.3-03"]),
    "keep_bad_entry_point": ({}, ["RESILIENCE-5.7-03"]),
    "rollback_on_failure": ({}, ["INTEROP-9-03"]),
    "audit_masks": ({}, ["AUDIT-EpistemicMetadataVerification-04"]),
    "audit_modifies": ({}, ["AUDIT-10-01"]),
    "mirror_feeds_ptl": ({}, ["INTEROP-8-01", "INTEROP-8-02"]),
    "crisis_from_interop": ({}, ["INTEROP-9-02", "INTEROP-9-04"]),
    "no_crisis_on_ptl_loss": (REG, ["CRISIS-4-01"]),
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


def test_source_roles_do_not_collide():
    """F-013 (IMPLEMENTATION_BUG): an external mirror is untrusted I1 and never PTL (INTEROP §3, §8), so its outage
    leaves PTL and internal execution intact; a loss of registered PTL sources is a CRISIS §4 event, not interop."""
    ext, reg = run(mirror_sources=4, ptl_loss_tolerance=0.25), run(**REG)
    assert statuses(ext)["CRISIS-4-01"] == "NOT_APPLICABLE" and statuses(ext)["INTEROP-9-04"] == "PASS"
    assert ext.outputs["internal_decisions"] == 24 and not ext.outputs["crisis_entered"]
    assert statuses(reg)["CRISIS-4-01"] == "PASS" and statuses(reg)["INTEROP-9-04"] == "PASS"
    assert reg.outputs["internal_decisions"] == reg.outputs["internal_decisions_without_failure"] == 16
    assert statuses(run(**{**REG, "ptl_loss_tolerance": -1}))["CRISIS-4-01"] == "UNKNOWN"
    former = statuses(run(**M.examples()["former_lab_premise"]))
    assert {k for k, v in former.items() if v == "FAIL"} == {"INTEROP-8-01", "INTEROP-8-02", "INTEROP-9-02", "INTEROP-9-04"}


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
