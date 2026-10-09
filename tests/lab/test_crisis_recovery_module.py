"""CRISIS AND RECOVERY module (S-LAB-06): PTL-anchored entry, prohibitions, exit, recovery, counterexamples."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.crisis_recovery import FAULTS, CrisisRecoveryModule

M = CrisisRecoveryModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_breaks_no_rule(name):
    res = run(**M.examples()[name])
    fails = [c for c in res.checks if c.status == "FAIL"]
    # the only FAIL a compliant run may show is the registered §12.1/§12.3 conflict (F-043), under either reading
    assert all(c.evidence.get("tag") == "rule_conflict" and c.evidence.get("finding") == "F-043" for c in fails), \
        [c.requirement_id for c in fails]


FAULT_CASES = {
    "forecast_entry": ({}, ["CRISIS-4-02"]),
    "emergency_authority": ({}, ["CRISIS-7-01"]),
    "suspend_ptl_logging": ({}, ["CRISIS-7-01"]),
    "unlogged_human": ({}, ["CRISIS-8-02"]),
    "status_priority": ({}, ["CRISIS-7-03", "CRISIS-7-04"]),
    "delayed_collapse": ({}, ["CRISIS-9-05"]),
    "finance_early": ({}, ["CRISIS-9-02"]),
    "valid_crisis_output": ({}, ["CRISIS-12.1-01"]),
    "cite_precedent": ({}, ["CRISIS-Non-PrecedentRule_-01"]),
    "no_broadcast": ({"ptl_divergence_window": [20, 26]}, ["CRISIS-10-02"]),
    "stale_confirmation": ({"confirmation_gap_window": [20, 24]}, ["CRISIS-5-07"]),
    "upgrade_during_crisis": ({}, ["UPGRADE-2-05", "UPGRADE-11-01"]),
    "elevate_scope": ({}, ["CRISIS-1-04"]),
    "missing_metadata": ({}, ["CRISIS-12-01"]),
    "transfer_interpretation": ({}, ["CRISIS-12.2-01"]),
    "parameter_by_decree": ({}, ["CRISIS-Non-PrecedentRule_-04"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    extra, expected = FAULT_CASES[fault]
    clean, broken = statuses(run(**extra)), statuses(run(**extra, faults=[fault]))
    for rid in expected:
        assert clean[rid] in ("PASS", "UNKNOWN"), (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_sustained_d3_gap_between_defense_and_crisis():
    """F-010: DEFENSE escalates at the first D3 hour; CRISIS enters only after the declared 'sustained' time."""
    sustained = run().outputs
    immediate = run(d3_reading="immediate").outputs
    assert (sustained["defense_escalation_hour"], sustained["crisis_entry_hour"]) == (10, 15)
    assert immediate["crisis_entry_hour"] == 10
    assert statuses(run())["CRISIS-4-01"] == "UNKNOWN"


def test_exit_and_sequential_recovery():
    res = run()
    assert res.outputs["exit_hour"] == 40
    layers = {s["step"]: s["layers"] for s in res.outputs["states"]}
    assert layers[41]["L1"] and not layers[41]["L2"]          # L1 back, finance waits for Justice (hour 60)
    assert layers[60]["L2"] and not layers[59]["L2"]


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
