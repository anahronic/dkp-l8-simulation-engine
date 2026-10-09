"""HABITAT DIGNITY module: physical SPDI, threshold governance, activation gate, remediation, integrity, scope, audit."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.habitat_dignity import FAULTS, HabitatDignityModule

M = HabitatDignityModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


BASE = {"remediate_without_bundle": EX["no_bundle"], "manual_interpretation": EX["no_bundle"]}


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    base = BASE.get(fault, {})
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    assert any(broken[k] == "FAIL" and clean[k] == "PASS" for k in broken), fault


def test_gate_and_remediation():
    plans = [d["remediation_plan"] for d in run().outputs["decisions"] if "remediation_plan" in d]
    assert plans == ["dense_estate", "fenced_zone"]
    for name in ("no_bundle", "expired_bundle"):
        out = run(**EX[name]).outputs
        assert not [d for d in out["decisions"] if "remediation_plan" in d]
        assert all(e["violation_flag"] is None and e["informational_only"] for e in out["evaluations"])
    ev = {e["site"]: e for e in run().outputs["evaluations"]}
    assert ev["self_report"]["spdi"] is None and "market_value" not in ev["north_block"]["inputs"]


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
