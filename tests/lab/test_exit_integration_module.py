"""EXIT AND INTEGRATION module (S-LAB-07): phases, exit rights, restitution tail, counterexamples."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.exit_integration import FAULTS, ExitIntegrationModule

M = ExitIntegrationModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", ["join_then_leave", "shock_and_rollback", "liabilities_mix", "settlement_after_halt"])
def test_reference_breaks_no_rule(name):
    """F-011 after review: SCOPE §2 sets aside the EXIT §6 stability purpose; the rest of the cooling period is
    UNKNOWN under SCOPE §9 (dependency protection may or may not be a stability goal)."""
    st = statuses(run(**M.examples()[name]))
    assert "FAIL" not in st.values() and st["SCOPE-9-02"] == "UNKNOWN"
    assert statuses(run(**{**M.examples()[name], "cooling_purposes": ["settlement"]}))["SCOPE-9-02"] == "PASS"
    assert statuses(run(**{**M.examples()[name], "cooling_purposes": ["settlement", "stability"]}))["SCOPE-9-02"] == "FAIL"


FAULT_CASES = {
    "auto_progression": ["INTEGRATION-4.2-02"],
    "skip_phase": ["INTEGRATION-4.2-01"],
    "phase0_effects": ["INTEGRATION-5.1-01"],
    "shock_ignored": ["INTEGRATION-7-01"],
    "retroactive": ["INTEGRATION-11-03"],
    "require_approval": ["EXIT-4-02", "EXIT-5-03"],
    "punitive_tail": ["EXIT-9-03"],
    "post_declaration_obligation": ["EXIT-9-04"],
    "collect_after_exit": ["EXIT-12-02"],
    "reentry_penalty": ["EXIT-13-03"],
    "protocol_bound_settlement": ["SCOPE-9-04", "SCOPE-9-07"],
    "settle_during_halt": ["ASSETS-2-02"],
    "release_before_tail": ["FINANCE-10-03"],
    "stability_veto": ["EXIT-0-02", "EXIT-2-01"],
    "exit_as_failure": ["EXIT-1-01"],
    "criminalize_exit": ["EXIT-2-01"],
    "erase_on_exit": ["EXIT-8-04", "EXIT-12-03"],
    "crisis_redefines_exit": ["EXIT-11-04"],
    "scope_creep": ["INTEGRATION-2-04", "INTEGRATION-4.4-01", "INTEGRATION-11-05"],
    "undefined_phase": ["INTEGRATION-3-02"],
    "shadow_as_proof": ["INTEGRATION-5.1-04"],
    "divergence_as_failure": ["INTEGRATION-9-03"],
    "conditional_aid": ["INTEGRATION-11-02"],
    "exit_out_of_procedure": ["EXIT-3-03"],
    "cooling_escalation": ["EXIT-6-03"],
    "cooling_restricts": ["EXIT-6-03"],
    "abrupt_severance": ["EXIT-7-01", "EXIT-3-03"],
    "benefits_after_exit": ["EXIT-8-01"],
    "annul_responsibility": ["EXIT-8-03"],
    "crisis_exit_precedent": ["EXIT-11-03"],
    "rollback_erases": ["INTEGRATION-7-04"],
    "rollback_skips_phases": ["INTEGRATION-3-06"],
}
EXTRA = {"shock_ignored": {"shock_window": [95, 110]}, "settle_during_halt": {"ptl_halt_window": [276, 282]},
         "crisis_redefines_exit": {"crisis_window": [262, 280]}, "crisis_exit_precedent": {"crisis_window": [262, 280]},
         "rollback_erases": {"shock_window": [95, 110]}, "rollback_skips_phases": {"shock_window": [95, 110]},
         "punitive_tail": {"liabilities": [{"day": 100, "kind": "verified_harm", "verified": True},
                                           {"day": 120, "kind": "punitive", "verified": True}]}}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    extra = EXTRA.get(fault, {})
    clean, broken = statuses(run(**extra)), statuses(run(**extra, faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_exit_timing_and_crisis_readings():
    """F-011, F-012: cooling delays exit; the SCOPE crisis reading suspends it (EXIT §4 fails)."""
    plain = run().outputs
    assert (plain["exit_declared_day"], plain["exit_executed_day"]) == (260, 284)        # 14 cooling + 10 phase days
    no_cooling = run(cooling_days=0).outputs
    assert no_cooling["exit_executed_day"] == 270
    paused = run(crisis_window=[262, 280], crisis_exit_reading="scope_crisis_suspension")
    assert paused.outputs["exit_executed_day"] == 302 and statuses(paused)["EXIT-4-03"] == "FAIL"
    kept = run(crisis_window=[262, 280])
    assert kept.outputs["exit_executed_day"] == 284 and statuses(kept)["EXIT-11-01"] == "PASS"


def test_restitution_tail_only_verified_prior_liabilities():
    res = run(**M.examples()["liabilities_mix"])
    tail = [m for m in res.outputs["messages"] if m["source"] == "RESTITUTION"]
    assert [m["value"]["kind"] for m in tail] == ["verified_harm"]          # ideological, projected, post-declaration dropped


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
