"""Attribution (§6, §12; L6, N1): eligibility before allocation, rule behaviour, Σ A ≤ 1."""

import itertools
import math

import pytest

from simulation.modules.prevention.protocol_adapter import allocate_attribution
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import adapter_for, iv, main_config, ta_readings

CLAIMS = [("a", 0.7), ("b", 0.6), ("c", 0.3)]


def _event(adapter, interventions):
    ta = adapter.assess_ta(ta_readings([0.8] * 4))
    se = adapter.assess_se(ta_readings([0.2] * 4, t=5.0))
    recs = adapter.evaluate_event("e", "zone-0001", "intrusion", ta, se, interventions)
    return {r["actor_id"].split("/")[1]: r for r in recs}


def test_within_budget_claims_are_kept():
    out = allocate_attribution([("a", 0.4), ("b", 0.3)], "ambiguity_zero")
    assert out == {"a": (0.4, None), "b": (0.3, None)}


def test_ambiguity_zero_gives_no_attribution():
    out = allocate_attribution([("a", 0.7), ("b", 0.6)], "ambiguity_zero")
    assert out == {"a": (0.0, "attribution_ambiguity"), "b": (0.0, "attribution_ambiguity")}


@pytest.mark.parametrize("rule", ["ambiguity_zero", "proportional"])
def test_order_invariant_rules(rule):
    results = {tuple(sorted(allocate_attribution(list(p), rule).items())) for p in itertools.permutations(CLAIMS)}
    assert len(results) == 1


def test_list_order_depends_on_order():
    """Kept only as a labelled comparison hypothesis: the v1 behaviour (L6)."""
    ab = allocate_attribution([("a", 0.7), ("b", 0.6)], "list_order")
    ba = allocate_attribution([("b", 0.6), ("a", 0.7)], "list_order")
    assert ab["a"][0] == 0.7 and ab["b"][0] == pytest.approx(0.3)
    assert ba["b"][0] == 0.6 and ba["a"][0] == pytest.approx(0.4)


@pytest.mark.parametrize("claims", [[0.7, 0.6], [1 / 3] * 4, [0.1] * 11, [0.9, 0.9, 0.9]])
def test_proportional_never_exceeds_one(claims):
    out = allocate_attribution([(str(i), c) for i, c in enumerate(claims)], "proportional")
    assert math.fsum(s for s, _ in out.values()) <= 1.0


def test_ineligible_first_subject_does_not_consume_budget():
    """N1: v1 spent the budget before checking; a self-induced first responder starved the honest one."""
    a = adapter_for()
    recs = _event(a, [iv("adversarial_actor", order=0, linkage=0.9),
                      iv("patrol_worker", order=1, linkage=0.0)])
    assert recs["adversarial_actor"]["status"] == "ZERO_MERIT"
    assert recs["adversarial_actor"]["reason"] == "self_induced_linkage"
    assert recs["adversarial_actor"]["factors"]["A"] is None
    assert recs["patrol_worker"]["status"] == "POSITIVE"
    assert recs["patrol_worker"]["factors"]["A"] == 1.0


def test_out_of_window_subject_does_not_consume_budget():
    a = adapter_for()
    recs = _event(a, [iv("weak_worker", order=0, time=100.0), iv("patrol_worker", order=1, time=2.0)])
    assert recs["weak_worker"]["reason"] == "intervention_outside_window"
    assert recs["patrol_worker"]["status"] == "POSITIVE" and recs["patrol_worker"]["factors"]["A"] == 1.0


def test_two_eligible_full_claims_are_ambiguous():
    a = adapter_for()
    recs = _event(a, [iv("patrol_worker", order=0), iv("optimizer_actor", order=1)])
    for r in recs.values():
        assert r["status"] == "NO_ATTRIBUTION" and r["reason"] == "attribution_ambiguity"
        assert r["epistemic"]["confidence_state"] == "INSUFFICIENT_DATA"   # IDENTITY §4.1


def test_zero_claim_is_no_attribution():
    a = adapter_for()
    recs = _event(a, [iv("passive_bystander", claim=0.0)])
    assert recs["passive_bystander"]["status"] == "NO_ATTRIBUTION"
    assert recs["passive_bystander"]["reason"] == "zero_claim"


@pytest.mark.parametrize("rule", ["ambiguity_zero", "proportional", "list_order"])
def test_sum_of_shares_per_event_at_most_one_in_runs(rule):
    res = run_simulation(main_config({"protocol": {"attribution_rule": rule}}, days=3), write=False)
    assert res.summary["evaluation"]["max_sum_A_per_event"] <= 1.0


def test_actor_order_changes_nothing_under_order_invariant_rules():
    for rule in ("ambiguity_zero", "proportional"):
        cfg = main_config({"protocol": {"attribution_rule": rule}}, days=3)
        rev = main_config({"protocol": {"attribution_rule": rule}}, days=3)
        rev["domain"]["actors"] = dict(reversed(list(cfg["domain"]["actors"].items())))
        a = run_simulation(cfg, write=False).summary["subject_totals"]
        b = run_simulation(rev, write=False).summary["subject_totals"]
        assert a.keys() == b.keys()
        # actor RNG streams are forked by profile name, so totals match up to float summation order
        for k in a:
            assert a[k] == pytest.approx(b[k], rel=1e-12, abs=1e-15)
