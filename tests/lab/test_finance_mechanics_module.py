"""FINANCE MECHANICS module: direction of the cost of capital, credit, savings, reserve and leverage basis, exclusions."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.finance_mechanics import FAULTS, REQUESTS, FinanceMechanicsModule

M = FinanceMechanicsModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items() if not v.get("faults")])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


FAULT_CASES = {
    "jwcoc_inverted": ["FINANCE-3.2-02"],
    "exposure_ignored": ["FINANCE-3.2-02"],
    "denominated_cu": ["FINANCE-3.1-01"],
    "earmarked_cu": ["FINANCE-3.1-01"],
    "credit_as_right": ["FINANCE-5.1-02", "FINANCE-5.1-01"],
    "perpetual_credit": ["FINANCE-5.1-02"],
    "discretionary_return": ["FINANCE-6.1-02", "FINANCE-12-02"],
    "percentage_reserve": ["FINANCE-6.2-01"],
    "volatility_leverage": ["FINANCE-9-02"],
    "finance_overreach": ["FINANCE-1-01", "FINANCE-13-01"],
    "override_justice": ["FINANCE-1-01", "FINANCE-13-01"],
    "override_attribution": ["FINANCE-13-01"],
    "inject_judgment": ["FINANCE-13-01"],
    "default_penalty": ["FINANCE-8.1-02"],
    "time_preference": ["FINANCE-ExplicitTimePreferenceProhibition-02", "FINANCE-ExplicitTimePreferenceProhibition-03"],
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "rate_uses_volatility": ["FINANCE-3.2-01"],
    "limit_uses_savings": ["FINANCE-5.2-01"],
    "price_allocation": ["FINANCE-7-02"],
    "deploy_before_internalization": ["FINANCE-10-02"],
    "excess_restitution": ["FINANCE-8.2-02"],
}
EXTRA = {"default_penalty": {"defaults": [{"subject": "C", "day": 5}]},
         "excess_restitution": {"defaults": [{"subject": "C", "day": 5}]},
         "deploy_before_internalization": {"external_deployments": [{"id": "x1", "day": 5, "risk_internalized_day": 3}]}}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    extra = EXTRA.get(fault, {})
    clean, broken = statuses(run(**extra)), statuses(run(**extra, faults=[fault]))
    for rid in FAULT_CASES[fault]:
        assert clean[rid] == "PASS", (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_credit_is_conditional_not_a_right():
    """§5.1: D exceeds the axiomatic bound (condition b) and is refused; a Subject meeting a-c gets a term."""
    res = run()
    assert res.outputs["credit_issued"] == ["A", "B", "C"] and res.outputs["credit_refused"] == ["D"]


def test_reserve_and_leverage_basis_is_metamorphic():
    """H-FM-3: reserve unchanged when only balances change; leverage unchanged when only volatility changes."""
    base = run()
    calm = run(subjects=[dict(s, volatility=0.0) for s in M.validate({})["subjects"]])
    assert base.outputs["leverage_limits"] == calm.outputs["leverage_limits"]
    big = run(subjects=[dict(s, credit_request=2 * s["credit_request"], projected_output=2 * s["projected_output"])
                        for s in M.validate({})["subjects"]], safety_margin=20000.0)
    assert big.outputs["reserve_first_last"] == base.outputs["reserve_first_last"]


def test_direction_needs_a_comparable_pair():
    one = statuses(run(subjects=[{"id": "A", "justice": "positive"}]))
    assert one["FINANCE-3.2-02"] == "NOT_APPLICABLE"


def test_requests_are_refused_where_excluded():
    for kind, rids in REQUESTS.items():
        res = run(requests=[kind])
        assert res.outputs["requests_refused"] == 1
        broken = statuses(run(requests=[kind], faults=["finance_overreach"]))
        assert all(broken[r] == "FAIL" for r in rids), kind


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_kt6_03_plateaus_are_impact_based():
    """Review КТ6-GPT-03: §6.2 and §9 fix the basis, not the shape.  A step or plateau function of impact exposure passes;
    a balance-based reserve and a volatility-based limit still fail."""
    import math
    from lab.modules import finance_mechanics as fm
    r = M.validate({})
    pick = lambda res: {c.requirement_id: c.status for c in res}
    orig_r, orig_l = fm.reserve_of, fm.leverage_of
    try:
        fm.reserve_of = lambda sp, e, o, faults: 100.0 * math.ceil(e / 10.0)          # (0, 0), (4, 100), (10, 100)
        fm.leverage_of = lambda sp, bound, e, vol, faults: 5000.0 if e < 7 else 0.0
        st = pick(fm.checks(r, fm.run(r)))
        assert st["FINANCE-6.2-01"] == "PASS" and st["FINANCE-9-02"] == "PASS"
    finally:
        fm.reserve_of, fm.leverage_of = orig_r, orig_l
    assert statuses(run(faults=["percentage_reserve"]))["FINANCE-6.2-01"] == "FAIL"
    assert statuses(run(faults=["volatility_leverage"]))["FINANCE-9-02"] == "FAIL"


def test_discounting_only_from_projected_impact_change():
    """Explicit Time Preference Prohibition (returned provision -02): a discount exists only where projected impact changes."""
    st = statuses(run(**M.examples()["default_and_trend"]))
    assert st["FINANCE-ExplicitTimePreferenceProhibition-02"] == "PASS" and st["FINANCE-8.1-02"] == "PASS"
    assert statuses(run(faults=["time_preference"]))["FINANCE-ExplicitTimePreferenceProhibition-02"] == "FAIL"


def test_core_checks_are_not_applicable_without_their_records():
    """Review КТ7-GPT-01: a clear part with nothing to judge is N/A, not PASS (no deployment, no default)."""
    st = statuses(run())
    assert st["FINANCE-10-02"] == "NOT_APPLICABLE" and st["FINANCE-8.2-02"] == "NOT_APPLICABLE"
    st = statuses(run(defaults=[{"subject": "C", "day": 5}],
                      external_deployments=[{"id": "x1", "day": 5, "risk_internalized_day": 3}]))
    assert st["FINANCE-10-02"] == "PASS" and st["FINANCE-8.2-02"] == "PASS"


def test_deployment_on_the_day_of_internalization_is_in_order_late_internalization_is_not():
    """FINANCE §10 clear part: internalization precedes or coincides with deployment; later internalization fails."""
    ok = statuses(run(external_deployments=[{"id": "x1", "day": 4, "risk_internalized_day": 4}]))
    late = statuses(run(external_deployments=[{"id": "x1", "day": 4, "risk_internalized_day": 6}]))
    assert ok["FINANCE-10-02"] == "PASS" and late["FINANCE-10-02"] == "FAIL"
