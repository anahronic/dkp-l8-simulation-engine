"""SCOPE GATE module: only what SCOPE explicitly permits is executed; everything else is refused and flagged."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.scope_gate import FAULTS, ScopeGateModule

M = ScopeGateModule()
EX = M.examples()
OTHER = EX["other_attempts"]


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "allow_unlisted": ({}, ["SCOPE-2-02", "SCOPE-0-01"]),
    "allow_s3": ({}, ["SCOPE-3-18", "SCOPE-3-19"]),
    "allow_unbounded_s1": ({}, ["SCOPE-3-04", "SCOPE-3-03"]),
    "allow_unanchored_s1": (OTHER, ["SCOPE-3-05", "SCOPE-3-03"]),
    "allow_s2_curriculum": ({}, ["SCOPE-3-15"]),
    "allow_s2_ranking": ({}, ["SCOPE-3-16"]),
    "defer_to_protocol": ({}, ["SCOPE-2-01"]),
    "allow_axiom_interpretation": ({}, ["SCOPE-4-01"]),
    "allow_min_conditions_outside_crisis": ({}, ["SCOPE-4-03", "SCOPE-4-06"]),
    "crisis_by_inference": ({}, ["SCOPE-5-02", "SCOPE-5-03", "SCOPE-4-04"]),
    "allow_new_right_in_crisis": ({}, ["SCOPE-5-08"]),
    "allow_precedent": ({}, ["SCOPE-5-11"]),
    "keep_crisis_after_exit": ({}, ["SCOPE-5-12"]),
    "grant_unbounded_authority": ({}, ["SCOPE-6-02"]),
    "allow_self_extension": ({}, ["SCOPE-6-05"]),
    "renew_without_simulation": (OTHER, ["SCOPE-6-06"]),
    "no_collapse_on_stabilization": ({}, ["SCOPE-6-04"]),
    "vector_persistence": ({}, ["SCOPE-3-11"]),
    "convert_neutralized": ({}, ["SCOPE-7-03"]),
    "allow_expansion": ({}, ["SCOPE-8-01"]),
    "escalate_during_audit": ({}, ["SCOPE-8-03"]),
    "single_sensor_escalation": ({}, ["SCOPE-8-05"]),
    "exit_fee": ({}, ["SCOPE-9-08"]),
    "post_exit_conditions": ({}, ["SCOPE-9-06"]),
    "deny_audit_trail": ({}, ["SCOPE-10-02"]),
    "unflagged_violation": ({}, ["SCOPE-11-01", "SCOPE-3-19"]),
    "no_critical_fault": ({}, ["SCOPE-11-02"]),
    "direct_scope_change": ({}, ["SCOPE-12-01", "SCOPE-0-01"]),
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


def test_default_deny_and_flags():
    out = run().outputs
    refused = [g["item"] for g in out["gate"] if g.get("executed") is False]
    flagged = [a["flag"] for a in out["audit"] if "flag" in a]
    assert refused and sorted(refused) == sorted(flagged)
    assert {a["critical_system_fault"] for a in out["audit"] if "critical_system_fault" in a} >= {"defense", "finance", "crisis"}


def test_scope_audit_blocks_and_stays_open():
    """F-035: the audit has no end; an independent confirmation does not reopen S0 -> S1."""
    out = run(**EX["confirmed_during_audit"]).outputs
    esc = [g for g in out["gate"] if "escalation" in g.get("item", "")]
    assert esc and not esc[0]["executed"]
    assert statuses(run(**EX["confirmed_during_audit"]))["SCOPE-8-04"] == "UNKNOWN"


def test_authority_lifecycle():
    gate = run().outputs["gate"]
    ends = {g["authority"]: g["ended"] for g in gate if "ended" in g}
    assert ends == {"evac_lead": 58, "grid_ctl": 42}   # evac_lead renewed to 71, collapsed at stabilization (58); grid_ctl self-extension refused
    assert not any(g.get("authority") == "open_ended" for g in gate)


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
