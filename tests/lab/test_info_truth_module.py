"""INFO TRUTH module: PTL-only truth, I1 non-blocking, informational without a bundle, annotation not removal."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.info_truth import FAULTS, InfoTruthModule

M = InfoTruthModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) in ("reference", "alternative")])
def test_examples_break_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


SYS = EX["systemic_disinformation"]
FAULT_CASES = {
    "remove_record": (SYS, ["INFO-InformationalArbitration_Non-RemovalPrinciple_-01"]),
    "penalize_isolated_i3": ({}, ["INFO-InformationalArbitration_Non-RemovalPrinciple_-04"]),
    "evaluate_opinion": ({}, ["INFO-0-01", "INFO-2-01", "INFO-3-03", "INFO-3-04"]),
    "enforce_without_bundle": (SYS, ["INFO-9-02", "INFO-2-02", "INFO-9-01"]),
    "popularity_truth": ({}, ["INFO-5-02", "INFO-5-01", "INFO-5-03"]),
    "i1_blocks": ({}, ["INFO-6.2-01", "INFO-6.2-02"]),
    "annotation_penalty": ({}, ["INFO-InformationalArbitration_Non-RemovalPrinciple_-03", "INFO-10-01"]),
    "manual_truth": ({}, ["INFO-9-03", "INFO-3-04", "INFO-5-03"]),
    "missing_annotation_fields": (SYS, ["INFO-InformationalArbitration_Non-RemovalPrinciple_-02"]),
    "no_audit_escalation": (SYS, ["INFO-11-01"]),
    "suspend_account": (SYS, ["INFO-8-01", "INFO-0-02"]),
    "info_overreach": ({}, ["INFO-13-01"]),
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "early_annotation": (M.examples()["late_inconsistency"], ["INFO-6.1-01", "INFO-5-03"]),
    "late_inconsistency_ignored": (M.examples()["late_inconsistency"], ["INFO-6.1-03"]),
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


def test_classes_follow_ptl_only():
    assert run().outputs["classes"] == {"c1": "I3", "c2": "I2", "o1": "I0", "c3": "I1"}   # 5000 repetitions decide nothing
    assert run(**SYS).outputs["classes"] == {"c1": "I4", "c2": "I3", "c4": "I1"}


def test_without_bundle_nothing_beyond_annotation():
    out = run(**SYS).outputs
    assert out["remediation_steps"] == 0 and len(out["annotations"]) == 2
    st = statuses(run())
    assert st["INFO-6.1-02"] == st["INFO-6.1-04"] == "UNKNOWN"                              # T1/T2 do not exist (F-014)
    hyp = run(**EX["hypothetical_bundle"]).outputs
    assert hyp["remediation_steps"] == 1 and hyp["classes"]["c5"] == "annotation"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_temporal_rules_need_declared_thresholds():
    """INFO §6.1 clear parts run only under declared T1/T2 (L8 bundle); without a bundle they are N/A, and a late PTL
    inconsistency reclassifies the claim under the declared values."""
    st = statuses(run())
    assert st["INFO-6.1-01"] == st["INFO-6.1-03"] == "NOT_APPLICABLE"
    res = run(**M.examples()["late_inconsistency"])
    assert res.outputs["classes"]["c6"] in ("I3", "I4") and statuses(res)["INFO-6.1-03"] == "PASS"
