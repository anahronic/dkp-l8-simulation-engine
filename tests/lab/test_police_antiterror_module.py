"""POLICE and ANTITERROR module: PTL-only triggers, detention and force limits, T-states with refresh, bans."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.police_antiterror import FAULTS, PoliceAntiterrorModule

M = PoliceAntiterrorModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


GAP = EX["sustained_with_refresh_gap"]
FAULT_CASES = {
    "act_on_suspicion": (EX["unconfirmed_report"], ["POLICE-3-06", "POLICE-4-01", "ANTITERROR-4.1-01"]),
    "invalid_order": (EX["orders_and_protest"], ["POLICE-2-05"]),
    "indefinite_detention": ({}, ["POLICE-5.1-02", "POLICE-5.1-05"]),
    "no_review": ({}, ["POLICE-5.1-04"]),
    "excess_force": ({}, ["POLICE-5.2-02"]),
    "lethal_force": ({}, ["POLICE-5.2-04"]),
    "unattributed": ({}, ["POLICE-6-01", "POLICE-6-03"]),
    "unscoped_extension": (EX["crisis_extension"], ["POLICE-8-02"]),
    "no_refresh_persist": (GAP, ["ANTITERROR-5-05"]),
    "lockdown_beyond_zone": ({}, ["ANTITERROR-6-04"]),
    "content_control": (GAP, ["ANTITERROR-6-03"]),
    "no_termination": ({}, ["ANTITERROR-8-04"]),
    "no_t3_escalation": (EX["mass_casualty"], ["ANTITERROR-5-04"]),
    "collective_responsibility": ({}, ["ANTITERROR-2-02", "ANTITERROR-7-01"]),
    "suppress_dissent": (EX["orders_and_protest"], ["ANTITERROR-7-02"]),
    "retrospective": ({}, ["ANTITERROR-7-03"]),
    "not_forwarded": ({}, ["ANTITERROR-8-02"]),
    "impose_sanction": ({}, ["ANTITERROR-11-01"]),
    "terror_on_combatants": ({"streams": [{"from_hour": 2, "to_hour": 6, "kind": "terror_event", "zone": "z1", "target": "combatants"}]},
                             ["ANTITERROR-3.3-01", "ANTITERROR-5-01"]),
    "run_prohibited": ({}, ["POLICE-2-02", "POLICE-7-04"]),
    "crisis_overreach": ({"crisis_window": [0, 12], "crisis_extension_scope": "z1", "horizon_hours": 20}, ["POLICE-8-04"]),
    "police_verdict": ({}, ["POLICE-0-02", "POLICE-2-03"]),
    "interpret_intent": ({}, ["POLICE-3-04"]),
    "profile_by_belief": ({}, ["POLICE-7-01", "POLICE-7-04", "POLICE-0-01"]),
    "expand_authority": ({}, ["POLICE-7-03", "POLICE-7-04"]),
    "police_overreach": ({}, ["POLICE-10-01", "POLICE-0-02", "POLICE-2-03", "POLICE-3-04", "POLICE-0-01"]),
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


def test_states_need_refresh_and_end_on_cessation():
    st = [(s["hour"], s["state"]) for s in run(**GAP).outputs["terror_states"]]
    assert st == [(2, "T2"), (6, "T0"), (8, "T2"), (12, "T0")]
    mc = run(**EX["mass_casualty"]).outputs
    assert [(s["hour"], s["state"]) for s in mc["terror_states"]] == [(1, "T1"), (4, "T3"), (9, "T0")]
    assert mc["crisis_escalations"] == 1


def test_no_ptl_no_action():
    out = run(**EX["unconfirmed_report"]).outputs
    assert (out["police_actions"], out["antiterror_actions"]) == (0, 0)


def test_invalid_order_refused_and_protest_untouched():
    res = run(**EX["orders_and_protest"])
    msgs = res.outputs["messages"]
    assert any(m["value"].get("order_refused") == "L3" for m in msgs)
    assert not any(m["kind"] == "action" and 10 <= m["arrived_at"] < 14 for m in msgs)


def test_positive_lethal_admission_stays_unknown():
    """F-023 after review: a declared CRISIS authorization does not establish the A1 minimum-required conditions."""
    st = statuses(run(faults=["lethal_force"], crisis_lethal_authorized=True))
    assert st["POLICE-5.2-04"] == "UNKNOWN"
    assert statuses(run(faults=["lethal_force"]))["POLICE-5.2-04"] == "FAIL"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_kt5_scope_requests_are_refused_where_excluded():
    """Review КТ5 reading of POLICE §0, §2, §3, §10: each excluded request is refused; carried out, it fails exactly
    the provisions that exclude it."""
    from lab.modules.police_antiterror import SCOPE_REQUESTS
    for q, rids in SCOPE_REQUESTS.items():
        clean = statuses(run(scope_requests=[q]))
        assert all(clean[x] == "PASS" for x in rids), q
        broken = statuses(run(scope_requests=[q], faults=["police_overreach"]))
        assert all(broken[x] == "FAIL" for x in rids), q
