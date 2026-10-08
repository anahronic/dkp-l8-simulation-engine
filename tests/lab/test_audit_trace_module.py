"""AUDIT TRACE module: immutable trace, replay, D1-D4 classification, procedural responses, no interference."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.audit_trace import FAULTS, AuditTraceModule

M = AuditTraceModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "record_private": ["AUDIT-4-02"], "skip_out_of_scope_kind": ["AUDIT-4-01"], "mutable_trace": ["AUDIT-3-02"], "no_replay": ["AUDIT-6-01"],
    "ignore_nondeterminism": ["AUDIT-5.4-01"], "metadata_as_d1": ["AUDIT-EpistemicMetadataVerification-04"],
    "no_axiom_escalation": ["AUDIT-5.1-02"], "allow_runtime_tuning": ["AUDIT-5.3-02"], "scope_expansion_unflagged": ["AUDIT-5.2-01"],
    "attribution_loss_ignored": ["AUDIT-5.5-01"], "no_halt_on_d3": ["AUDIT-8-03"], "d4_without_review": ["AUDIT-8-04"],
    "punish": ["AUDIT-8-05"], "inject_correction": ["AUDIT-10-01"], "mask_failure": ["AUDIT-3-04"], "delay_halt": ["AUDIT-10-01"],
    "suspend_in_mercy": ["AUDIT-11-01"], "closed_method": ["AUDIT-9-02"], "direct_change": ["AUDIT-12-01"],
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_levels_and_responses():
    out = run().outputs
    lv = {d["event"]: d["level"] for d in out["deviations"]}
    assert lv == {"e3": "D3", "e4": "D2", "e5": "D2", "e7": "D3", "e8": "D3", "e9": "D3", "e10": "D4", "e11": "D1", "e16": "D2"}
    assert {x["event"] for x in out["trace"]} >= {"e2", "e15"} and "e13" not in {x["event"] for x in out["trace"]}


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
