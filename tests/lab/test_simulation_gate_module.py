"""SIMULATION GATE module: the hard pre-activation gate of SIMULATION §1-§14."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.simulation_gate import FAULTS, SimulationGateModule

M = SimulationGateModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    assert any(broken[k] == "FAIL" and clean[k] == "PASS" for k in broken), fault


def test_eligibility():
    el = {s["change"]: (s["eligible"], s["classes"]) for s in run().outputs["simulations"]}
    assert el["ttl_rule"] == (True, []) and el["spdi_v2"] == (True, [])
    assert el["crisis_fast"][1] == ["F2"] and el["habitat_rule"][1] == ["F1"] and el["interop_x"][1] == ["F4"]
    assert el["dam_rule"][1] == ["F3"] and not el["plain_rule"][0] and not el["index_w"][0] and not el["bundle_z"][0]
    gate = {g["change"]: g for g in run().outputs["gate"] if "activated" in g}
    assert gate["spdi_v2"]["eligible"] and not gate["spdi_v2"]["activated"]      # eligibility does not mandate deployment
    assert run().outputs["operational_use"] is False


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
