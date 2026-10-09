"""SENSOR LOSS module (S-LAB-03): global null-output state, regional alternative, recovery readings, N_eff gap."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.sensor_loss import FAULTS, SensorLossModule

M = SensorLossModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", ["region_lost_global", "n_eff_min_missing", "inconsistency_window"])
def test_text_in_force_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


def test_regional_reading_conflicts_with_the_patch():
    st = statuses(run(scope_reading="regional"))
    for rid in ("CRISISPATCH-4.2-01", "CRISISPATCH-4.3-01", "CRISISPATCH-9-01", "CRISISPATCH-3-05"):
        assert st[rid] == "FAIL", rid


def test_resuming_old_outputs_conflicts_with_reentry():
    assert statuses(run(recovery_reading="resume_outputs"))["ETRANS-4.4-02"] == "FAIL"
    assert statuses(run())["ETRANS-4.4-02"] == "PASS"


def test_missing_n_eff_min_is_unknown_not_a_decision():
    res = run(n_eff_min=-1)
    assert statuses(res)["CRISISPATCH-2-01"] == "UNKNOWN"
    assert res.outputs["null_output_steps"] == 0          # nothing is enforced or stopped on a guess


def test_sybil_sources_mask_a_collapse_only_when_counting_sources():
    by_sources = run(n_eff_basis="sources", sybil_sources=40)
    by_owners = run(n_eff_basis="owners", sybil_sources=40)
    assert by_sources.outputs["null_output_steps"] == 0
    assert by_owners.outputs["null_output_steps"] == 12
    s, o = statuses(by_sources), statuses(by_owners)
    # counted over sources, one Sybil owner carries the system through the loss: RESILIENCE §5.8, §5.1, §11 fail
    assert (s["RESILIENCE-5.8-02"], s["RESILIENCE-5.1-01"], s["RESILIENCE-11-01"]) == ("FAIL", "FAIL", "FAIL")
    assert (o["RESILIENCE-5.8-02"], o["RESILIENCE-5.1-01"], o["RESILIENCE-11-01"]) == ("PASS", "PASS", "PASS")


FAULT_CASES = {
    "fallback_authority": ["CRISISPATCH-4.1-01"],
    "partial_enforcement": ["CRISISPATCH-4.2-01", "CRISISPATCH-3-05"],
    "priority_routing": ["CRISISPATCH-4.3-01"],
    "manual_restart": ["CRISISPATCH-5.2-02", "CRISISPATCH-6-01"],
    "stop_measurement": ["CRISISPATCH-3-06", "CRISISPATCH-5.1-01"],
    "precedent": ["CRISISPATCH-7-01", "CRISISPATCH-9-04"],
    "escalate_from_region": ["SCOPE-8-05"],
    "accept_injection": ["CRISISPATCH-8.1-01"],
    "absorb_external": ["CRISISPATCH-4.1-02"],
    "wait_for_certification": ["CRISISPATCH-6-02"],
    "crisis_via_enforcement": ["CRISISPATCH-7-02"],
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_coverage_boundary_and_caps():
    st = statuses(run())                                   # 4 of 5 regions covered = 80 %: no halt
    assert st["ORACLE-13-01"] == "NOT_APPLICABLE" and st["ORACLE-8-01"] == "PASS"
    res = run(regions=4)                                   # 3 of 4 = 75 % < 80 %: systemic halt
    assert res.outputs["systemic_halt_steps"] == 12 and statuses(res)["ORACLE-13-01"] == "PASS"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
