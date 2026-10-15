"""EXIT AND INTEGRATION module (S-LAB-07): phases, exit rights, restitution tail, counterexamples."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.exit_integration import FAULTS, ExitIntegrationModule

M = ExitIntegrationModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", ["join_then_leave", "shock_and_rollback", "liabilities_mix", "settlement_after_halt",
                                  "critical_asset_exit"])
def test_reference_breaks_no_rule(name):
    """F-011 after review: SCOPE §2 sets aside the EXIT §6 stability purpose; the rest of the cooling period is
    UNKNOWN under SCOPE §9 (dependency protection may or may not be a stability goal)."""
    st = statuses(run(**M.examples()[name]))
    assert "FAIL" not in st.values() and st["SCOPE-9-02"] == "UNKNOWN"
    assert statuses(run(**{**M.examples()[name], "cooling_purposes": ["settlement"]}))["SCOPE-9-02"] == "PASS"
    assert statuses(run(**{**M.examples()[name], "cooling_purposes": ["settlement", "stability"]}))["SCOPE-9-02"] == "FAIL"


FAULT_CASES = {
    "auto_progression": ["INTEGRATION-4.2-02", "INTEGRATION-0-01", "INTEGRATION-5.3-02", "INTEGRATION-11-01", "INTEGRATION-5.1-03", "INTEGRATION-6-01"],
    "skip_phase": ["INTEGRATION-4.2-01", "INTEGRATION-0-01", "INTEGRATION-11-01", "INTEGRATION-5.1-03", "INTEGRATION-6-01"],
    "phase0_effects": ["INTEGRATION-5.1-01", "INTEGRATION-11-04", "INTEGRATION-3-03"],
    "shock_ignored": ["INTEGRATION-7-01"],
    "retroactive": ["INTEGRATION-11-03"],
    "require_approval": ["EXIT-4-02", "EXIT-5-03", "EXIT-14-01", "EXIT-4-01", "EXIT-4-04", "EXIT-0-01", "EXIT-10-01"],
    "punitive_tail": ["EXIT-9-03", "EXIT-14-02", "EXIT-3-05", "EXIT-9-02"],
    "post_declaration_obligation": ["EXIT-9-04", "EXIT-14-02", "EXIT-3-05", "EXIT-9-02"],
    "collect_after_exit": ["EXIT-12-02", "EXIT-3-01"],
    "reentry_penalty": ["EXIT-13-03", "EXIT-13-02"],
    "protocol_bound_settlement": ["SCOPE-9-04", "SCOPE-9-07"],
    "settle_during_halt": ["ASSETS-2-02"],
    "release_before_tail": ["FINANCE-10-03"],
    "stability_veto": ["EXIT-0-02", "EXIT-2-01", "EXIT-14-01", "EXIT-4-01", "EXIT-4-04", "EXIT-0-01"],
    "exit_as_failure": ["EXIT-1-01", "EXIT-0-03", "EXIT-14-02", "EXIT-14-03"],
    "criminalize_exit": ["EXIT-2-01", "EXIT-0-03", "EXIT-14-03"],
    "erase_on_exit": ["EXIT-8-04", "EXIT-12-03"],
    "crisis_redefines_exit": ["EXIT-11-04"],
    "scope_creep": ["INTEGRATION-2-04", "INTEGRATION-4.4-01", "INTEGRATION-11-05", "INTEGRATION-11-04"],
    "undefined_phase": ["INTEGRATION-3-02", "INTEGRATION-0-01"],
    "shadow_as_proof": ["INTEGRATION-5.1-04", "INTEGRATION-5.1-03"],
    "divergence_as_failure": ["INTEGRATION-9-03", "INTEGRATION-2-03"],
    "conditional_aid": ["INTEGRATION-11-02", "INTEGRATION-2-01"],
    "exit_out_of_procedure": ["EXIT-3-03", "INTEGRATION-5.4-01"],
    "cooling_escalation": ["EXIT-6-03", "EXIT-3-04"],
    "cooling_restricts": ["EXIT-6-03", "EXIT-3-04"],
    "abrupt_severance": ["EXIT-7-01", "EXIT-3-03", "INTEGRATION-5.4-01"],
    "benefits_after_exit": ["EXIT-8-01", "EXIT-3-01"],
    "annul_responsibility": ["EXIT-8-03"],
    "crisis_exit_precedent": ["EXIT-11-03"],
    "rollback_erases": ["INTEGRATION-7-04"],
    "rollback_skips_phases": ["INTEGRATION-3-06", "INTEGRATION-3-03"],
    "settlement_penalty": ["EXIT-10-03"],
    "settlement_authority": ["EXIT-10-04"],
    "collective_punishment": ["EXIT-14-02"],
    "exit_deprivation": ["EXIT-14-03"],
    "post_exit_regulation": ["EXIT-15-01", "EXIT-15-02", "EXIT-3-01"],
    "phase0_without_agreement": ["INTEGRATION-5.1-02"],
    "phase3_uncleared": ["INTEGRATION-5.3-02"],
    "alignment_condition": ["INTEGRATION-2-03", "INTEGRATION-9-02"],
    "political_audit": ["INTEGRATION-10-02"],
    "political_assessment": ["INTEGRATION-6-02"],
    "delay_without_critical": ["EXIT-10-01"],
    "settlement_obligation": ["EXIT-10-05"],
    "post_exit_profiling": ["EXIT-12-04"],
    "indefinite_suspension": ["EXIT-2-02"],
    "exit_audit_gap": [],
    "rollback_penalty": ["INTEGRATION-4.3-01"],
    "no_reaffirmation": ["INTEGRATION-5.4-02"],
    "skip_verification": ["INTEGRATION-6-01"],
    "retroactive_risk": ["INTEGRATION-8-01"],
    "shared_reserve_exposure": ["INTEGRATION-8-02"],
    "language_harmonization": ["INTEGRATION-9-02"],
    "undeclared_phase2_scope": [],
}
EXTRA = {"shock_ignored": {"shock_window": [95, 110]}, "settlement_obligation": {"system_critical_asset": True},
         "indefinite_suspension": {"crisis_window": [262, 280], "crisis_exit_reading": "scope_crisis_suspension"},
         "rollback_penalty": {"shock_window": [95, 110]}, "settlement_penalty": {"system_critical_asset": True},
         "settlement_authority": {"system_critical_asset": True}, "settle_during_halt": {"ptl_halt_window": [276, 282]},
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


def test_kt7_03_cooling_simulation_needs_a_bound_record_not_a_flag():
    """Review КТ7-GPT-03: EXIT §6 'declared, simulated, auditable'.  Declaration may PASS; the simulation part is UNKNOWN
    without a record, FAIL for a record bound to another duration or scope, and still UNKNOWN for a matching record whose
    content the lab cannot verify.  The UNKNOWN never disappears behind the declaration PASS."""
    def parts(**kw):
        return {c.check: c.status for c in run(**kw).checks if c.requirement_id == "EXIT-6-04"}
    assert parts() == {"cooling_parameters_declared": "PASS", "cooling_parameters_simulated": "UNKNOWN"}
    ok = {"simulation_id": "sim-cooling-1", "cooling_days": 14, "exit_scope": "regional"}
    assert parts(cooling_simulation_record=ok)["cooling_parameters_simulated"] == "UNKNOWN"
    assert parts(cooling_simulation_record=dict(ok, cooling_days=30))["cooling_parameters_simulated"] == "FAIL"
    assert parts(cooling_simulation_record=dict(ok, exit_scope="individual"))["cooling_parameters_simulated"] == "FAIL"
    with pytest.raises(LabInputError):                            # an empty reference is refused, not read as a record
        M.validate({"cooling_simulation_record": dict(ok, simulation_id="")})


def test_exit_obstruction_is_measured_against_the_declared_delays():
    """EXIT §14: an approval vote holds the exit three days beyond cooling and phases; a system-critical asset may delay it."""
    assert run(faults=["require_approval"]).outputs["exit_executed_day"] == 287
    crit = run(system_critical_asset=True)
    assert crit.outputs["exit_executed_day"] == 304 and statuses(crit)["EXIT-14-01"] == "PASS"


def test_core_checks_with_an_unknown_part():
    """Review КТ7-GPT-01 cores: EXIT-7-03 and INTEGRATION-5.2-02 check the clear part (audit continuity, declared scope);
    the simulation part stays UNKNOWN and the counterexample breaks only the clear part."""
    def parts(**kw):
        return {(c.requirement_id, c.check): c.status for c in run(**kw).checks
                if c.requirement_id in ("EXIT-7-03", "INTEGRATION-5.2-02")}
    clean = parts()
    assert clean[("EXIT-7-03", "phase_audit_continuity")] == "PASS" and clean[("EXIT-7-03", "phase_plan_simulated")] == "UNKNOWN"
    assert clean[("INTEGRATION-5.2-02", "phase2_scope_declared")] == "PASS"
    assert clean[("INTEGRATION-5.2-02", "phase2_interface_simulated")] == "UNKNOWN"
    assert parts(faults=["exit_audit_gap"])[("EXIT-7-03", "phase_audit_continuity")] == "FAIL"
    assert parts(faults=["undeclared_phase2_scope"])[("INTEGRATION-5.2-02", "phase2_scope_declared")] == "FAIL"


def test_exit_from_phase_2_and_no_collection_after_exit():
    """INTEGRATION §5.3 core: exit from Phase 2 carries no penalty; the run stops observing the region after exit."""
    st = statuses(run(**M.examples()["exit_from_phase_2"]))
    assert st["INTEGRATION-5.3-03"] == "PASS" and st["EXIT-12-02"] == "PASS" and st["EXIT-3-01"] == "PASS"
    for f in ("exit_as_failure", "collective_punishment", "exit_deprivation"):
        assert statuses(run(**M.examples()["exit_from_phase_2"], faults=[f]))["INTEGRATION-5.3-03"] == "FAIL", f
