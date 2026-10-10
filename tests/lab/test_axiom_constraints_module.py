"""AXIOM CONSTRAINTS module: axioms before optimization, priority, A7 only among equivalents, A1a, F-022..F-025."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.axiom_constraints import FAULTS, AxiomConstraintsModule

M = AxiomConstraintsModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


LIFE = EX["benefit_against_life"]
FAULT_CASES = {
    "axiom_computes_metric": ({}, ["AXIOMS-2-03"]),
    "axiom_as_weight": ({}, ["AXIOMS-3-01"]),
    "narrative_override": ({}, ["AXIOMS-AxiomA3-PhysicalRealitySupremacy-02"]),
    "axioms_as_truth": ({}, ["AXIOMS-EpistemicClarification-04"]),
    "utility_override": (LIFE, ["AXIOMS-5-02", "AXIOMS-1-01", "AXIOMS-AxiomA1-PreservationofLife-03",
                                "AXIOMS-AxiomA1-PreservationofLife-01"]),
    "weighted_axioms": (LIFE, ["AXIOMS-5-03", "AXIOMS-7-02"]),
    "suspend_for_efficiency": ({}, ["AXIOMS-5-01", "AXIOMS-7-03"]),
    "human_override": (LIFE, ["AXIOMS-7-04"]),
    "lower_overrides_higher": (EX["dilemma_lexicographic"], ["AXIOMS-6-01", "AXIOMS-5-04"]),
    "suffering_primary": (EX["suffering_tiebreak"], ["AXIOMS-AxiomA7-MinimumSufferingConstraint-03", "AXIOMS-5-02"]),
    "context_reinterpretation": (EX["suffering_tiebreak"], ["AXIOMS-7-05"]),
    "infer_minimum_required": (EX["minimum_required_claim"], ["AXIOMS-AxiomA1-PreservationofLife-04"]),
    "compel_service": ({}, ["AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-01",
                            "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-02"]),
    "punish_refusal": ({}, ["AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-04",
                            "AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-05"]),
    "benefit_free_riders": ({}, ["AXIOMS-AxiomA1a-RiskSymmetryandVoluntaryLethalRisk-03"]),
    "missing_metadata": ({}, ["AXIOMS-EpistemicClarification-02"]),
    "classify_axioms": ({}, ["AXIOMS-EpistemicClarification-01"]),
    "axiom_shield": ({}, ["AXIOMS-EpistemicClarification-03"]),
    "unmodelled_necessity": ({"candidates": [{"id": "levee", "utility": 7, "irreversible": True, "necessity_verified": True}]},
                             ["AXIOMS-AxiomA4-IrreversibilityAversion-02"]),
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


def test_choices():
    assert run(**LIFE).outputs["chosen"] == "safe"                          # utility 100 never buys an A1 violation
    assert run(**EX["suffering_tiebreak"]).outputs["chosen"] == "y"        # A7 among equivalents, then utility
    assert run(**EX["irreversible_with_alternative"]).outputs["chosen"] == "weir"


def test_dilemma_readings():
    """F-024: no axiom-clean action — §5.4 picks the lowest-priority violation, §5.2 leaves no action."""
    assert run(**EX["dilemma_lexicographic"]).outputs["chosen"] == "hide"   # A6 is the least important violated axiom
    assert run(**EX["dilemma_no_action"]).outputs["chosen"] is None
    assert statuses(run(**EX["dilemma_lexicographic"]))["AXIOMS-5-02"] == "UNKNOWN"


def test_a4_readings():
    """F-025: A4 says SHOULD."""
    assert run(**EX["a4_as_recommendation"]).outputs["chosen"] == "dam"
    assert statuses(run(**EX["a4_as_recommendation"]))["AXIOMS-AxiomA4-IrreversibilityAversion-01"] == "UNKNOWN"


def test_undefined_references_stay_unknown():
    assert statuses(run(**EX["minimum_required_claim"]))["AXIOMS-AxiomA1-PreservationofLife-02"] == "UNKNOWN"   # F-023
    assert statuses(run(**EX["axiom_modification"]))["AXIOMS-8-02"] == "UNKNOWN"                               # F-022


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
