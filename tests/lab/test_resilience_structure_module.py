"""RESILIENCE STRUCTURE module: no single point, no person, no override, intact entry points, anti-Sybil, crisis boundary."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.resilience_structure import FAULTS, ResilienceStructureModule

M = ResilienceStructureModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


def test_concentrated_owner_fails_only_the_cap():
    assert [k for k, s in statuses(run(**EX["concentrated_owner"])).items() if s == "FAIL"] == ["RESILIENCE-5.8-01"]


BASE = {"enforce_below_neff": EX["collapse_below_neff"]}


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    base = BASE.get(fault, {})
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    # N_eff is undefined (F-007): its checks are UNKNOWN when right and FAIL when enforcement runs below the declared minimum
    assert any(broken[k] == "FAIL" and clean[k] in ("PASS", "UNKNOWN") for k in broken), fault


def test_entry_points_invalidated_locally():
    eps = {x["entry_point"]: x for x in run().outputs["structure"] if "entry_point" in x}
    assert eps["portal_a"]["status"] == "valid"
    assert eps["portal_b"]["status"] == eps["portal_c"]["status"] == "locally invalidated"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
