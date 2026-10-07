"""TRANSPORT CAPACITY module (S-LAB-09): queues, seats and RED apart; standing rules; counterexamples; F-015."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.transport_capacity import FAULTS, TransportCapacityModule

M = TransportCapacityModule()
THIN = {"policy": "standing_allowed", "vehicles_per_hour": [4] * 6 + [9] * 4 + [5] * 6 + [9] * 4 + [3] * 4}
RED = {"policy": "standing_allowed", "red_per_km": 0.02, "red_reading": "channel_separated", "red_insurance": "outside_ptl"}


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", ["seated_only", "standing_allowed", "more_vehicles", "red_insurance_outside_ptl",
                                  "thin_service", "bench_interior"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


FAULT_CASES = {
    "standing_as_standard": (THIN, ["TRANSPORT-5-03"]),
    "passenger_adaptation": (THIN, ["TRANSPORT-5-04"]),
    "red_as_tax": (RED, ["TRANSPORT-7.2-01", "TRANSPORT-7.2-02"]),
    "justice_from_red": (RED, ["TRANSPORTA-A.1-01", "TRANSPORT-11-02"]),
    "ban_private": (RED, ["TRANSPORT-8-01"]),
    "moral_weighting": (RED, ["TRANSPORT-7.3-03"]),
    "undeclared_proxy": (RED, ["ORACLE-5.2-02"]),
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


def test_queues_seats_and_externalities_are_reported_apart():
    seated, standing = run(), run(policy="standing_allowed")
    assert seated.outputs["queues"]["max_queue"] > 0 and seated.outputs["seats"]["standing_hours_total"] == 0
    assert standing.outputs["queues"]["max_queue"] == 0 and standing.outputs["seats"]["standing_hours_total"] > 0
    assert seated.outputs["external"]["red"] is None                              # no RED coefficient in the corpus


def test_open_parameters_stay_unknown():
    st = statuses(run())
    for rid in ("TRANSPORT-4-01", "TRANSPORT-4.2-01", "TRANSPORT-8-02", "TRANSPORT-7.1-01", "TRANSPORT-7.2-01"):
        assert st[rid] == "UNKNOWN", rid


def test_red_insurance_exposure_conflicts_with_oracle():
    """F-015 (CONFIRMED): PTL quantifying 'systemic insurance exposure' (TRANSPORT §7.1) against ORACLE §1 'physical
    state only'.  The former claim that a single RED violates IMPACT §5/§10 is an interpretation gap: UNKNOWN."""
    lit = statuses(run(red_per_km=0.02))
    assert lit["ORACLE-1-02"] == "FAIL" and lit["IMPACT-10-02"] == "UNKNOWN"
    assert statuses(run(red_per_km=0.02, red_reading="channel_separated"))["IMPACT-10-02"] == "PASS"
    assert statuses(run(red_per_km=0.02, red_insurance="outside_ptl"))["ORACLE-1-02"] == "PASS"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
