"""UPGRADE LIFECYCLE module: hard constraints, simulation, cooling-off, activation conditions, rollback, F-020."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.upgrade_lifecycle import FAULTS, UpgradeLifecycleModule

M = UpgradeLifecycleModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FIX = {"proposals": [{"id": "u1", "deviation_day": 50},
                     {"id": "fix", "submitted_day": 51, "results_published_day": 52, "announced_day": 53,
                      "activation_day": 90, "fixes": "u1"}]}
FAULT_CASES = {
    "direct_patch_accepted": ({}, ["UPGRADE-0-01"]),
    "discretionary_tuning": ({}, ["UPGRADE-11-02", "UPGRADE-0-01"]),
    "upgrade_in_crisis": ({"crisis_window": [0, 10]}, ["UPGRADE-4.3-01", "UPGRADE-11-01"]),
    "skip_completeness": ({"proposals": [{"id": "a", "missing_items": ["before_after"]}]}, ["UPGRADE-5-02"]),
    "weaken_axiom_accepted": ({"proposals": [{"id": "a", "weakens_axioms": True}]}, ["UPGRADE-4.1-01", "UPGRADE-2-03"]),
    "degrade_defense_accepted": ({"proposals": [{"id": "a", "targets": ["defense"], "degrades_defense_crisis": True}]},
                                 ["UPGRADE-4.5-01", "UPGRADE-4.6-02"]),
    "no_simulation": ({"proposals": [{"id": "a"}, {"id": "b", "simulation_passed": False}]}, ["UPGRADE-6-01", "UPGRADE-11-03"]),
    "short_cooling": ({"proposals": [{"id": "a"}, {"id": "b", "activation_day": 25}]}, ["UPGRADE-Post-CrisisCooldownRule-02"]),
    "activate_with_open_appeal": ({"open_appeals": [[38, 45]], "proposals": [{"id": "a"}, {"id": "b", "activation_day": 60}]},
                                  ["UPGRADE-8-01"]),
    "unannounced": ({"proposals": [{"id": "a"}, {"id": "b", "announced_day": -1, "activation_day": 60}]}, ["UPGRADE-8-01",
                                                                                                          "UPGRADE-4.4-01"]),
    "no_rollback": (FIX, ["UPGRADE-9-01", "UPGRADE-9-03"]),
    "stack_fix": (FIX, ["UPGRADE-9-02"]),
    "ignore_correlation": (EX["correlated_initiators"], ["UPGRADE-7-02"]),
    "presentation_as_upgrade": (EX["presentation_only"], ["UPGRADE-3-02", "UPGRADE-12-03"]),
    "threshold_as_cosmetic": ({}, ["UPGRADE-3-01"]),
    "results_only": ({}, ["UPGRADE-6-03", "UPGRADE-4.4-01"]),
    "erase_artifact": ({}, ["UPGRADE-10-01"]),
    "refuse_error_in_cooldown": (EX["error_in_cooldown"], ["UPGRADE-Post-CrisisCooldownRule-03"]),
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


def test_rejections_name_their_rule():
    st = run(**EX["rejections"]).outputs["status"]
    assert st == {"incomplete": "rejected", "axiom": "rejected", "ptl": "rejected", "weaker_defense": "rejected",
                  "failed_sim": "rejected", "ok": "active"}


def test_rollback_then_fix():
    out = run(**EX["deviation_and_rollback"]).outputs
    assert out["status"] == {"u1": "rolled_back", "fix": "active"} and out["version"]["current"] == "fix"


def test_post_crisis_stabilization_is_undefined():
    """F-020: AUDIT does not define the period; layered upgrades after a Crisis are held and the check is UNKNOWN."""
    res = run(**EX["after_crisis_layered"])
    assert res.outputs["status"] == {"justice_change": "held", "social_change": "active"}
    assert statuses(res)["UPGRADE-Post-CrisisCooldownRule-01"] == "UNKNOWN"
    declared = run(**EX["after_crisis_declared_stabilization"])
    assert declared.outputs["status"] == {"early": "rejected", "later": "active"}
    assert statuses(declared)["UPGRADE-Post-CrisisCooldownRule-01"] == "PASS"


def test_open_values_stay_unknown():
    st = statuses(run())
    assert st["UPGRADE-7-01"] == st["UPGRADE-7-03"] == "UNKNOWN"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
