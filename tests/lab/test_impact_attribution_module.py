"""IMPACT ATTRIBUTION module: channel-separated measurement and attribution as IMPACT and IDENTITY write them."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.impact_attribution import FAULTS, ImpactAttributionModule

M = ImpactAttributionModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


def test_untraceable_impact_fails_only_the_binding_invariant():
    s = statuses(run(**EX["untraceable_impact"]))
    assert [k for k, x in s.items() if x == "FAIL"] == ["IDENTITY-4-01"] and s["IDENTITY-4-02"] == "PASS"


FAULT_CASES = {
    "aggregate_score": ({}, ["IMPACT-5-04", "IMPACT-3-01"]),
    "modify_bound": ({}, ["IMPACT-6-03"]),
    "no_crossing_flag": ({}, ["IMPACT-5-03"]),
    "local_default_boundary": ({}, ["IMPACT-8-02"]),
    "no_externality_without_boundary": ({}, ["IMPACT-8-04"]),
    "nondeterministic_uncertainty": ({}, ["IMPACT-9-02"]),
    "accept_layer_override": ({}, ["IMPACT-11-01"]),
    "subjective_reversibility": (EX["benign_irreversible"], ["IMPACT-7-02"]),
    "intent_exemption": ({}, ["IDENTITY-3.3-01"]),
    "omission_ignored": ({}, ["IDENTITY-3.2-02"]),
    "delegate_shift": ({}, ["IDENTITY-5-01"]),
    "contract_as_subject": ({}, ["IDENTITY-5-03", "IDENTITY-5-04"]),
    "status_exemption": ({}, ["IDENTITY-12-01"]),
    "dissolution_erases": ({}, ["IDENTITY-7-02"]),
    "equal_split": ({}, ["IDENTITY-6-01"]),
    "force_degraded_attribution": (EX["low_confidence_crossing"], ["IDENTITY-4.1-01", "IDENTITY-4.1-05"]),
    "cascade_on_no_attribution": (EX["low_confidence_crossing"], ["IDENTITY-4.1-02"]),
    "speculative_attribution": ({}, ["IDENTITY-10-02"]),
    "identity_measures_magnitude": ({}, ["IDENTITY-13-01"]),
    "require_physical_damage": ({}, ["IDENTITY-11-02"]),
    "breach_unflagged": ({}, ["IDENTITY-13-02"]),
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


def test_attribution_weights():
    att = {a["impact"]: a for a in run().outputs["attribution"]}
    assert att["river_pollutant"]["weights"] == {"contractor": 0.6, "plant_co": 0.2, "regulator": 0.2}
    assert att["aquifer"]["weights"] == {"farm_a": 0.5, "farm_coalition": 0.5}     # AI delegate's share returns to farm_a
    assert "noise_late" not in att                                                   # no declared bound: not emitted


def test_impact_flags():
    imp = {o["channel"]: o for o in run().outputs["impact"]}
    assert imp["river_pollutant"]["crossing"] and imp["river_pollutant"]["X"] and not imp["river_pollutant"]["R"]
    assert imp["aquifer"]["X"] and imp["aquifer"]["boundary"] == "undefined"
    assert imp["co2_air"]["boundary"] == "planetary" and not imp["co2_air"]["X"]


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
