"""ECONOMIC ACCESS module: FINANCE §11 and ASSETS §2/§8/§10-§12 under Justice outcomes and disputes."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.economic_access import FAULTS, EconomicAccessModule

M = EconomicAccessModule()
HALT = {"ptl_halt_window": [1, 5]}
LATE = {"horizon_days": 45, "dispute": {"filed_day": 35, "validated_day": 36, "resolved_day": 39}}
TRANSFER = {"justice": [], "dispute": {"filed_day": -1}, "transfer": {"day": 5, "asset": "home"}}
SHELL = {"assets": [{"id": "home", "essential": True}, {"id": "holding", "bound_to_subject": False}]}


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in M.examples() if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


FAULT_CASES = {
    "finance_ignores_exclusion": ({}, ["FINANCE-11.1-01"]),
    "alternative_pathway": ({}, ["FINANCE-11.1-02"]),
    "restore_on_filing": ({}, ["FINANCE-11.1-03", "FINANCE-11.2-02"]),
    "late_restore": ({}, ["FINANCE-11.2-01"]),
    "accrue_during_status_quo": ({}, ["FINANCE-11.2-03"]),
    "time_preference_discount": ({}, ["FINANCE-ExplicitTimePreferenceProhibition-01"]),
    "revoke_life_access": ({}, ["ASSETS-11-02"]),
    "no_escrow": ({}, ["ASSETS-8.3-02"]),
    "prejudice": ({}, ["ASSETS-8.3-05"]),
    "missing_metadata_enforced": ({}, ["ASSETS-8.3-06", "ASSETS-8.3-07", "ASSETS-8.3-08"]),
    "act_during_halt": (HALT, ["ASSETS-2-02"]),
    "no_return": ({}, ["ASSETS-8.3-04"]),
    "committee_override": ({}, ["ASSETS-ReallocationTransparencyConstraint-02"]),
    "late_dispute_accepted": (LATE, ["ASSETS-8.3-01", "ERROR-7-02"]),
    "transfer_without_obligations": ({**TRANSFER, "transfer": {"day": 5, "asset": "home", "obligations_transferred": False}},
                                     ["ASSETS-10-01"]),
    "inheritance_clears_attribution": (TRANSFER, ["ASSETS-10-02"]),
    "accept_shell": (SHELL, ["ASSETS-12-02", "ASSETS-IdentityBindingRequirement-01"]),
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


def test_access_follows_the_justice_domain():
    res = run()
    acts = [(m["value"]["access"], m["value"]["day"]) for m in res.outputs["financial_access"] if "access" in m["value"]]
    assert acts == [("suspended", 2), ("restored", 18)]
    assert run(dispute={"outcome": "rejected"}).outputs["suspended_at_end"] is True


def test_no_interest_during_the_status_quo():
    """FINANCE §11.2(b): 7 days of the ERROR §7 suspension (days 7-13) carry no interest."""
    assert run().outputs["interest_accrued"] == pytest.approx(1000 * 0.001 * (39 - 7))
    assert run(status_quo_days=0).outputs["interest_accrued"] == pytest.approx(1000 * 0.001 * 39)


def test_open_values_stay_unknown():
    assert statuses(run())["FINANCE-11.2-04"] == "UNKNOWN"                   # no identity TTL in ORACLE §17
    assert statuses(run(identity_ttl_minutes=60))["FINANCE-11.2-04"] == "PASS"
    gap = statuses(run(**M.examples()["delayed_execution_clock_gap"]))
    assert gap["ASSETS-8.3-01"] == gap["ERROR-7-02"] == "UNKNOWN"            # two clocks (H-EA-3)


def test_revocation_waits_for_the_halt_and_escrow_returns():
    res = run(**HALT)
    assert res.outputs["revocation_execution_day"] == 5
    ok = run()
    assert ok.outputs["assets_final"] == {"home": "held", "workshop": "held", "vehicle": "held"}
    rej = run(dispute={"outcome": "rejected"})
    released = [m["value"] for m in rej.outputs["asset_events"] if "escrow_released" in m["value"]]
    assert {x["to"] for x in released} == {"mitigation pool"}


def test_slow_polling_is_a_noncompliant_case():
    assert statuses(run(**M.examples()["slow_polling"]))["FINANCE-11.2-01"] == "FAIL"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
