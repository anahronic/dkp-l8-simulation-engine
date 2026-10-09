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


BASE = {"no_wind_down": EX["single_attack"], "vpi_not_terminated": EX["vpi_lapse"]}


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
