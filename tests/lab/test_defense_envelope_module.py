"""DEFENSE ENVELOPE module: D-states, VPI authorization, action limits, volunteers, claims, logs, isolation."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.defense_envelope import FAULTS, DefenseEnvelopeModule

M = DefenseEnvelopeModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


BASE = {"no_wind_down": EX["single_attack"], "vpi_not_terminated": EX["vpi_lapse"], "vpi_skip_revalidation": EX["vpi_two_episodes"]}


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    base = BASE.get(fault, {})
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    assert any(broken[k] == "FAIL" and clean[k] == "PASS" for k in broken), fault


def test_actions_admitted_and_refused():
    acts = {a["action"]: a for a in run().outputs["actions"]}
    assert {k for k, a in acts.items() if a["executed"]} == {"shield_grid", "intercept_1", "evacuate", "neutralize_src"}
    assert any("§4.6" in r for r in acts["intercept_2"]["reasons"])           # risky action, no consent
    assert any("§4.2" in r for r in acts["intel_block"]["reasons"])
    assert any("feasible method" in r for r in acts["neutralize_alt"]["reasons"])
    assert any("§7" in r for r in acts["sanction_x"]["reasons"])


def test_lapse_falls_back_to_d1_and_wind_down_stays_unknown():
    lv = [x["level"] for x in run().outputs["levels"]]
    assert lv == ["D1.5", "D1", "D2", "D3", "D1", "D0"]
    assert statuses(run())["DEFENSE-8-04"] == "UNKNOWN"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


VPI2 = "DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-02"
PROBE_KT5_01 = {"horizon_steps": 20, "ptl_timeline": [{"from_step": 0, "harm": "vpi", "trajectory_ttl_steps": 3},
                                                      {"from_step": 2, "harm": "none"},
                                                      {"from_step": 10, "harm": "vpi", "trajectory_ttl_steps": 3},
                                                      {"from_step": 15, "harm": "none"}], "actions": [], "refusals": []}
PROBE_KT5_02 = {"horizon_steps": 5, "ptl_timeline": [{"from_step": 0, "harm": "active", "confirmed": True},
                                                     {"from_step": 1, "harm": "active", "confirmed": False}],
                "actions": [{"id": "evacuate", "step": 2, "kind": "evacuation", "domain": "life"}], "refusals": []}


def test_kt5_01_each_vpi_authorization_is_its_own_episode():
    """Review КТ5-GPT-01: grant 0, terminate 2; grant 10, revalidate 13, terminate 15 — all within TTL 3."""
    res = run(**PROBE_KT5_01)
    assert statuses(res)[VPI2] == "PASS"
    assert statuses(res)["DEFENSE-EpistemicClassificationofTrajectory-BasedAuthorization-03"] == "PASS"
    broken = run(**PROBE_KT5_01, faults=["vpi_skip_revalidation"])               # a real missed refresh in the second episode
    c = {x.requirement_id: x for x in broken.checks}[VPI2]
    assert c.status == "FAIL" and c.evidence["violations"] == ["authorization at step 10: 5 steps from 10 to 15 (TTL 3)"]


def test_kt5_02_no_evacuation_exception():
    """Review КТ5-GPT-02: confirmation lapsed under activity — the evacuation is refused; forcing it fails §4.1."""
    acts = {a["action"]: a for a in run(**PROBE_KT5_02).outputs["actions"]}
    assert not acts["evacuate"]["executed"] and any("§4.1" in x for x in acts["evacuate"]["reasons"])
    assert statuses(run(**PROBE_KT5_02))["DEFENSE-4.1-01"] == "PASS"
    assert statuses(run(**PROBE_KT5_02, faults=["act_without_confirmation"]))["DEFENSE-4.1-01"] == "FAIL"


def test_kt5_02_evidence_validity_under_stability_and_lost_integrity():
    """EB §9: absence of data under stability keeps the earlier confirmation usable; lost integrity does not."""
    res = run(**EX["evacuation_stable_absence"])
    acts = {a["action"]: a for a in res.outputs["actions"]}
    assert acts["evacuate"]["executed"] and acts["evacuate"]["ptl_evidence"].startswith("ptl-0000-")   # the step-0 observation
    assert statuses(res)["DEFENSE-4.1-01"] == "PASS"
    acts = {a["action"]: a for a in run(**EX["evacuation_integrity_lost"]).outputs["actions"]}
    assert not acts["evacuate"]["executed"]
    assert statuses(run(**EX["evacuation_integrity_lost"], faults=["act_without_confirmation"]))["DEFENSE-4.1-01"] == "FAIL"
