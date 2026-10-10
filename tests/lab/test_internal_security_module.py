"""INTERNAL SECURITY module: S0-S4 durations, evidence-only actions, effects via triggers, hard bans, F-021."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.internal_security import FAULTS, InternalSecurityModule

M = InternalSecurityModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "consider_motivation": ({}, ["INTSEC-3.2-02"]),
    "extra_trigger": ({}, ["INTSEC-6-01"]),
    "cap_breach_downgraded": ({"node_shares": EX["concentrated_nodes"]["node_shares"]}, ["INTSEC-8-07"]),
    "predictive_trigger": (EX["unconfirmed_prediction"], ["INTSEC-4.2-01", "INTSEC-11-01", "INTSEC-4.1-01"]),
    "throttle_in_s1": ({}, ["INTSEC-7.1-02", "INTSEC-7.1-01"]),
    "overstay": (EX["persisting_compromise"], ["INTSEC-5-04", "INTSEC-5-06"]),
    "direct_execution": ({}, ["INTSEC-2-03", "INTSEC-2-02", "INTSEC-11-05", "INTSEC-7.2-01"]),
    "act_during_halt": (EX["halt_during_violation"], ["INTSEC-6-03"]),
    "no_crisis_escalation": (EX["systemic"], ["INTSEC-5-05", "INTSEC-7.4-01"]),
    "collective_punishment": ({}, ["INTSEC-8-02"]),
    "mass_surveillance": ({}, ["INTSEC-8-01"]),
    "secret_rule": ({}, ["INTSEC-8-04"]),
    "missing_due_process": ({}, ["INTSEC-9-01"]),
    "permanent_exclusion": ({}, ["INTSEC-8-03"]),
    "ideological_justification": ({}, ["INTSEC-8-05"]),
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


def test_states_follow_confirmed_evidence():
    assert [(t["day"], t["state"]) for t in run().outputs["states"]] == [(2, "S1"), (6, "S2"), (15, "S0")]
    assert run(**EX["unconfirmed_prediction"]).outputs["states"] == []
    sys = run(**EX["systemic"]).outputs["states"]
    assert [(t["day"], t["state"]) for t in sys] == [(2, "S3"), (5, "S4"), (9, "S0")]


def test_reentry_reading_changes_containment():
    """F-021 (INTERPRETATION_GAP): a 10-day active compromise under the 3-day S3 limit."""
    pulses = run(**EX["persisting_compromise"]).outputs
    once = run(**EX["persisting_compromise_once"]).outputs
    assert [(t["day"], t["state"]) for t in pulses["states"]] == [(3, "S3"), (6, "S0"), (7, "S3"), (10, "S0"), (11, "S3"), (13, "S0")]
    assert (pulses["contained_days"], once["contained_days"]) == (8, 3)


def test_actions_wait_for_the_halt():
    acts = run(**EX["halt_during_violation"]).outputs["actions"]
    assert min(a["arrived_at"] for a in acts if a["value"]["state"] == "S2") == 9


def test_node_cap_is_a_noncompliant_case():
    assert statuses(run(**EX["concentrated_nodes"]))["INTSEC-8-06"] == "FAIL"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_kt5_node_cap_breach_is_critical():
    """INTERNAL-SEC §8: a concentration above 4 % is a critical architectural breach (8-07), not a policy deviation."""
    shares = {"node_shares": EX["concentrated_nodes"]["node_shares"]}
    assert statuses(run(**shares))["INTSEC-8-07"] == "PASS"
    assert statuses(run(**shares, faults=["cap_breach_downgraded"]))["INTSEC-8-07"] == "FAIL"
    assert statuses(run())["INTSEC-8-07"] == "NOT_APPLICABLE"
    assert statuses(run(**EX["unconfirmed_prediction"], faults=["predictive_trigger"]))["INTSEC-6-01"] == "FAIL"
