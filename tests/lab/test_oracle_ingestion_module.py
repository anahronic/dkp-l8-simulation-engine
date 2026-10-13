"""ORACLE INGESTION module: admission, caps, staleness, aggregation, outputs, halt, Mercy deferral, isolation, finality."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.oracle_ingestion import FAULTS, OracleIngestionModule

M = OracleIngestionModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "accept_human_input": ({}, ["ORACLE-3-01", "ORACLE-1-01"]),
    "accept_proprietary": ({}, ["ORACLE-7-02"]),
    "accept_unsigned": ({}, ["ORACLE-7-01"]),
    "ptl_absolute": ({}, ["ORACLE-EpistemicInterpretationNote-04"]),
    "normalize_at_ingestion": ({}, ["ORACLE-7-03"]),
    "no_owner_cap": (EX["few_owners"], ["ORACLE-8-01", "ORACLE-8-02"]),
    "redistribute_excess": (EX["few_owners"], ["ORACLE-8-02"]),
    "no_slashing": (EX["few_owners"], ["ORACLE-8-02"]),
    "silence_as_zero": ({}, ["ORACLE-9-03"]),
    "vote_aggregation": (EX["orbital_bias"], ["ORACLE-10-01"]),
    "nondeterministic": ({}, ["ORACLE-10-02"]),
    "within_class_divergence": (EX["within_class_spread"], ["ORACLE-6-02"]),
    "no_halt": ({}, ["ORACLE-13-01"]),
    "halt_erases_l1": ({}, ["ORACLE-13-02"]),
    "enforce_on_b": ({}, ["ORACLE-12-06"]),
    "normalize_b": ({}, ["ORACLE-12-05"]),
    "mercy_without_confirmation": (EX["mercy_human_cause"], ["ORACLE-14-01", "ORACLE-14-02"]),
    "mercy_extends_ttl": (EX["mercy_natural"], ["ORACLE-14-03", "ORACLE-9-03"]),
    "accept_layer_override": ({}, ["ORACLE-15-01", "ORACLE-EpistemicInterpretationNote-02"]),
    "emit_intent": ({}, ["ORACLE-5.3-01"]),
    "in_place_change": ({}, ["ORACLE-18-01"]),
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


def test_owner_caps_need_fifteen_owners_to_avoid_a_halt():
    """With the 4% owner cap and H-OI-2, total confidence = 4% x owners: 10 owners halt at once, 15 stay at the 60% line."""
    few = run(**EX["few_owners"]).outputs
    assert few["evaluations"][0]["aggregate_confidence"] == 0.4 and few["halts"][0]["min"] == 0
    fifteen = run(**EX["fifteen_owners"]).outputs
    assert fifteen["evaluations"][0]["aggregate_confidence"] == 0.6 and not fifteen["halts"]


def test_silent_class_halts_on_coverage():
    out = run().outputs
    h = [x for x in out["halts"] if x["halt"] == "systemic"][0]
    assert h["min"] == 1560 and h["reasons"] == ["coverage < 80%"] and h["l1_state"] == "preserved"


def test_mercy_defers_only_a_natural_cause():
    assert not [h for h in run(**EX["mercy_natural"]).outputs["halts"] if h["halt"] == "systemic"]
    assert [h for h in run(**EX["mercy_human_cause"]).outputs["halts"] if h["halt"] == "systemic"]


def test_b_never_enforces_without_bundle():
    d = [x for x in run().outputs["decisions"] if "b_enforcement" in x]
    assert d and not d[0]["executed"]
    d = [x for x in run(**EX["bundle_attached"]).outputs["decisions"] if "b_enforcement" in x]
    assert d[0]["executed"]


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
