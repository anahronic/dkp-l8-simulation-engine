"""AI SUBJECT module: execute and stop — no ranking, recommendation, friction, smoothing, optimization or 'help'."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.ai_subject import FAULTS, AiSubjectModule

M = AiSubjectModule()
EX = M.examples()
CR = EX["crisis_entry"]
DET = EX["deterministic_rule"]


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "recommend": ({}, ["AISUBJECT-2-03", "AISUBJECT-9-01"]),
    "rank_options": ({}, ["AISUBJECT-2-02"]),
    "frame_options": ({}, ["AISUBJECT-2-07"]),
    "choose_without_rule": ({}, ["AISUBJECT-2-01", "AISUBJECT-2-06"]),
    "justify": ({}, ["AISUBJECT-2-04"]),
    "absorb_responsibility": (DET, ["AISUBJECT-3-01", "AISUBJECT-3-02"]),
    "ai_as_authority": ({}, ["AISUBJECT-1-01"]),
    "fragment_identity": ({}, ["AISUBJECT-3-03", "AISUBJECT-3-04"]),
    "exit_friction": ({}, ["AISUBJECT-4-01", "AISUBJECT-4-02"]),
    "retention_nudge": ({}, ["AISUBJECT-4-03"]),
    "smooth_ptl": ({}, ["AISUBJECT-5-02", "AISUBJECT-5-01"]),
    "suppress_anomaly": ({}, ["AISUBJECT-5-03"]),
    "optimize_objective": ({}, ["AISUBJECT-6-01", "AISUBJECT-6-02"]),
    "minimize_dissent": ({}, ["AISUBJECT-6-03"]),
    "crisis_by_inference": ({"crisis": {"ptl_confirmed": True, "state_machine_entry": False}},
                            ["AISUBJECT-7-01", "AISUBJECT-7-02"]),
    "help_under_uncertainty": ({}, ["AISUBJECT-8-03", "AISUBJECT-8-04"]),
    "self_modify": ({}, ["AISUBJECT-8-01"]),
    "audit_gap": (CR, ["AISUBJECT-7-10", "AISUBJECT-7-07"]),
    "resolve_value_conflict": ({}, ["AISUBJECT-2-05"]),
    "crisis_precedent": (CR, ["AISUBJECT-7-08"]),
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "goal_overrides_constraint": ({}, ["AISUBJECT-1-03"]),
    "open_ended_crisis_action": (M.examples()["crisis_entry"], ["AISUBJECT-7-06"]),
    "ttl_extension_without_mercy": ({}, ["AISUBJECT-7-09"]),
    "learned_authority": ({}, ["AISUBJECT-8-02"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    base, expected = FAULT_CASES[fault]
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    for rid in expected:
        assert clean[rid] in ("PASS",), (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_selection_is_external_without_a_rule():
    log = run().outputs["agent_log"]
    assert any(m["value"].get("selection") == "external" for m in log)
    assert not any(m["kind"] == "decision" for m in log)


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_ttl_extension_needs_crisis_mercy():
    """AI-SUBJECT §7.5 clear part: outside a crisis no extension is applied; in a crisis only the Mercy-authorized class."""
    calm = [m["value"] for m in run().outputs["agent_log"] if "ttl_extension" in m["value"]]
    crisis = [m["value"] for m in run(**M.examples()["crisis_entry"]).outputs["agent_log"] if "ttl_extension" in m["value"]]
    assert not any(x["applied"] for x in calm)
    assert {x["ttl_extension"] for x in crisis if x["applied"]} == {"seismic"}
