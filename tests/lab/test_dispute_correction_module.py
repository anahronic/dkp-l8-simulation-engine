"""DISPUTE AND CORRECTION module (S-LAB-04): reference chain, independent checks, counterexamples, findings."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.dispute_correction import FAULTS, DisputeCorrectionModule, impact

M = DisputeCorrectionModule()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n, v in M.examples().items()
                                  if not v.get("faults") and n not in M.alternative_examples])
def test_reference_chain_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**M.examples()[name])).values()


STANDING = {"appellant": "bystander", "subjects": [{"id": "plant", "kind": "legal_entity", "contribution": 3},
                                                  {"id": "logistics", "kind": "legal_entity", "contribution": 1},
                                                  {"id": "bystander", "kind": "human", "contribution": 0}]}
TRIGGERS = {"appeal_after_minutes": -1, "reevaluation_triggers": [{"after_minutes": 600, "kind": "mitigation", "data": "complete"},
                                                                  {"after_minutes": 900, "kind": "impact_change", "data": "stale"}]}
FAULT_CASES = {
    "late_appeal_accepted": ({"appeal_category": "E3", "recorded_contributions": [4, 0], "appeal_after_minutes": 40 * 1440},
                             ["ERROR-7-02"]),
    "e1_time_barred": ({"appeal_after_minutes": 40 * 1440}, ["ERROR-7-03"]),
    "suspension_over_7_days": ({"verification_days": 10}, ["ERROR-7-04"]),
    "mutate_original": ({}, ["EB-7.2-01", "EB-7.2-02", "ERROR-8-01"]),
    "retaliate": ({}, ["ERROR-11-02", "ERROR-8-05", "ERROR-2-03", "JUSTICE-1-01", "JUSTICE-7-03"]),
    "keep_bond": ({}, ["ERROR-6-02"]),
    "proxy_as_subject": ({"subjects": [{"id": "operator", "kind": "human", "contribution": 0, "originator": "none"},
                                       {"id": "router", "kind": "smart_contract", "contribution": 2, "originator": "operator"},
                                       {"id": "plant", "kind": "legal_entity", "contribution": 2, "originator": "none"}],
                          "appeal_after_minutes": -1}, ["IDENTITY-5-03", "IDENTITY-6-01"]),
    "enforce_no_attribution": ({"attribution_confidence": 0.6, "s0": 0.0, "s1_recorded": 1.0},
                               ["IDENTITY-4.1-02", "IDENTITY-4.1-03"]),
    "suppress_by_uncertainty": ({"s1_recorded": 0.905}, ["IMPACT-9-03", "IMPACT-5-03"]),
    "override_flag": ({}, ["IMPACT-11-01", "JUSTICE-13-02", "JUSTICE-13-01"]),
    "partial_binding": ({}, ["JUSTICE-3.2-01"]),
    "exclusion_erases_history": ({"persistent_axiom_violation": True, "appeal_after_minutes": -1}, ["JUSTICE-9-02", "JUSTICE-9-04"]),
    "final_output": ({}, ["JUSTICE-DisputeExceptionClause-03"]),
    "refuse_appealable": ({}, ["ERROR-3.2-01"]),
    "moralize_error": ({}, ["ERROR-0-01"]),
    "coercive_verification": ({}, ["ERROR-5-02", "ERROR-1-01", "ERROR-2-03"]),
    "error_rewrites_ptl": ({}, ["ERROR-2-04", "ERROR-9-02"]),
    "infer_intent": ({}, ["ERROR-6-04"]),
    "compensate_instead": ({}, ["ERROR-9-03"]),
    "suppress_appeal": ({}, ["ERROR-11-01"]),
    "discretionary_override": ({}, ["ERROR-11-04", "JUSTICE-1-01"]),
    "moral_output": ({}, ["JUSTICE-4-02", "JUSTICE-1-01"]),
    "coupled_domains": ({}, ["JUSTICE-5-01"]),
    "collective_absorbs": ({"appeal_after_minutes": -1, "appellant": "m1",
                            "subjects": [{"id": "union", "kind": "collective", "contribution": 2},
                                         {"id": "m1", "kind": "human", "contribution": 1},
                                         {"id": "m2", "kind": "human", "contribution": 1}]}, ["JUSTICE-10-02"]),
    "exempt_by_status": ({"appeal_after_minutes": -1, "appellant": "logistics",
                          "subjects": [{"id": "ministry", "kind": "legal_entity", "contribution": 3, "status": "authority"},
                                       {"id": "logistics", "kind": "legal_entity", "contribution": 1}]}, ["JUSTICE-12-01"]),
    "justice_policy": ({}, ["JUSTICE-13-01"]),
    "opaque_adjustment": ({"repeated_harm": False, "safe_margin": 100}, ["JUSTICE-14-01", "JUSTICE-5-01", "JUSTICE-4-02",
                                                                          "JUSTICE-1-01"]),
    "misclassify_as_e1": ({"appeal_category": "E3", "recorded_contributions": [4, 0], "appeal_after_minutes": 40 * 1440},
                          ["ERROR-4-03", "ERROR-7-02"]),
    "seal_case": ({}, ["ERROR-10-02"]),
    "exclusion_abandons": ({"persistent_axiom_violation": True, "appeal_after_minutes": -1},
                           ["JUSTICE-9-04", "JUSTICE-9-02", "JUSTICE-9-03"]),
    # checkable cores of provisions whose open point remains (review КТ7-GPT-01)
    "uncounted_case": ({}, ["ERROR-10-03"]),
    "hide_statistics": ({}, ["ERROR-11-03"]),
    "admit_without_standing": (STANDING, ["ERROR-3.3-01"]),
    "stale_dti_index": ({}, ["ERROR-5-06"]),
    "admit_without_bond": ({"appeal_bond_posted": False}, ["ERROR-6-01"]),
    "cascade_correction": ({}, ["ERROR-9-04"]),
    "ignore_trigger": (TRIGGERS, ["JUSTICE-11-01"]),
    "act_on_stale_data": (TRIGGERS, ["JUSTICE-11-03"]),
    "justice_feeds_identity": ({}, ["JUSTICE-2-01"]),
    "history_dependent_output": ({}, ["JUSTICE-4-01"]),
    "physical_confinement": ({}, ["JUSTICE-8-03"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    extra, expected = FAULT_CASES[fault]
    base = {"repeated_harm": True, **extra}
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    for rid in expected:
        assert clean[rid] == "PASS", (fault, rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_impact_formula_and_example_s13():
    """IMPACT §5 gives 0.0002 for the §13 input, not the stated 0.004 (finding F-005)."""
    i = impact(426.91, 427.0, 450, 0.01, False)
    assert abs(i["I"] - 0.0002) < 1e-12 and not i["boundary_crossing"]
    assert abs(0.09 / (450 - 427.0) - 0.004) < 0.0001          # the reading that matches the stated number
    level = impact(0.40, 0.55, 0.5, 0.01, False)                 # S(t1) above the bound level, |I| = 0.3
    assert level["level_reached"] and not level["boundary_crossing"]


@pytest.mark.parametrize("irreversible", [False, True])
def test_only_the_justice_polarity_complies(irreversible):
    """F-006 (INTERPRETATION_GAP), revised after review: JUSTICE §6/§8 are checked literally on the received flag and
    the flag contract separately.  Only the JUSTICE polarity passes both; a uniform opposite polarity breaks JUSTICE
    §6/§8 and the contract, a mixed chain breaks the contract (JUSTICE itself acts correctly on what it receives)."""
    base = {**M.examples()["impact_example_s13"], "irreversible": irreversible}
    res = {p: run(**base, r_polarity=p) for p in ("true_means_reversible", "true_means_irreversible", "mixed")}
    fails = {p: sorted(k for k, v in statuses(x).items() if v == "FAIL") for p, x in res.items()}
    assert fails == {"true_means_reversible": [],
                     "true_means_irreversible": ["JUSTICE-3.1-01", "JUSTICE-6-01", "JUSTICE-8-01"],
                     "mixed": ["JUSTICE-3.1-01"]}
    dom = {p: x.outputs["decisions"][0]["domains"] for p, x in res.items()}
    assert dom["true_means_reversible"]["isolation"] is irreversible
    flag = res["true_means_reversible"].outputs["decisions"][0]["flag"]
    assert flag["emitted_by_impact"] == flag["received"] is (not irreversible)


def test_open_questions_surface_as_unknown():
    st = statuses(run(**M.examples()["harsher_recomputation"]))
    assert st["ERROR-8-05"] == "UNKNOWN"                       # Q-021
    assert statuses(run(**M.examples()["calibration_missing"]))["IDENTITY-4.1-01"] == "UNKNOWN"     # Q-025
    assert statuses(run(**M.examples()["impact_example_s13"]))["JUSTICE-7-01"] == "UNKNOWN"        # Q-024
    a = statuses(run(**M.examples()["dispute_within_ttl_all"]))
    b = statuses(run(**M.examples()["dispute_within_ttl_either"]))
    assert a["JUSTICE-DisputeExceptionClause-02"] == b["JUSTICE-DisputeExceptionClause-02"] == "UNKNOWN"   # Q-020
    assert a["JUSTICE-DisputeExceptionClause-01"] == "NOT_APPLICABLE" and b["JUSTICE-DisputeExceptionClause-01"] == "PASS"


def test_decisions_carry_provenance_to_ptl():
    res = run(**M.examples()["measurement_error_corrected"])
    msgs = {m["event_id"]: m for m in res.outputs["messages"]}
    for d in res.outputs["decisions"]:
        imp = msgs[msgs[d["event_id"]]["provenance"][0]]
        assert imp["source"] == "IMPACT" and all(msgs[p]["source"] == "PTL" for p in imp["provenance"])


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_kt5_error_conduct_applicability():
    """Review КТ5 reading of ERROR §1, §5, §9, §11: a late non-E1 appeal is not a valid appeal (§7), so suppression
    cannot be judged; a harsher recomputed Justice outcome is not a measure of the error case itself (Q-021)."""
    late = statuses(run(repeated_harm=True, appeal_category="E3", recorded_contributions=[4, 0], appeal_after_minutes=40 * 1440))
    assert late["ERROR-11-01"] == "NOT_APPLICABLE"
    harsh = statuses(run(repeated_harm=True, s1_recorded=0.55, s1_true=0.95))
    assert harsh["ERROR-1-01"] == "PASS" and harsh["ERROR-8-05"] == "UNKNOWN"
    assert statuses(run(repeated_harm=True, appeal_after_minutes=-1))["ERROR-0-01"] == "PASS"


@pytest.mark.parametrize("cat", ["E2", "E3", "E4", "E5"])
def test_error_classes_follow_the_deviation(cat):
    """ERROR §4 (returned provisions ERROR-4-02..05): the case is classified by its deviation, and only E1 escapes
    the 30-day window; a misclassification as E1 lets a late appeal through."""
    rid = {"E2": "ERROR-4-02", "E3": "ERROR-4-03", "E4": "ERROR-4-04", "E5": "ERROR-4-05"}[cat]
    extra = {"repeated_harm": True, "appeal_category": cat}
    if cat == "E3":
        extra["recorded_contributions"] = [4, 0]
    assert statuses(run(**extra))[rid] == "PASS"
    late = run(**extra, appeal_after_minutes=40 * 1440, faults=["misclassify_as_e1"])
    assert statuses(late)[rid] == "FAIL" and statuses(late)["ERROR-7-02"] == "FAIL"


def test_admission_needs_standing_and_a_bond():
    """ERROR §3.3 and §6 clear parts: a claim from a Subject the decision does not name, or without a bond, is rejected
    procedurally; the existing admission checks (§7) count such a rejection as correct, not as a suppressed appeal."""
    for extra in (STANDING, {"appeal_bond_posted": False}):
        res = run(repeated_harm=True, **extra)
        st = statuses(res)
        assert res.outputs["final_state"] == "REJECTED_PROCEDURAL"
        assert st["ERROR-3.3-01"] == st["ERROR-6-01"] == st["ERROR-7-01"] == "PASS"
        assert st["ERROR-11-01"] == "NOT_APPLICABLE"


def test_reevaluation_waits_for_the_ttl_and_weak_data_keep_the_outcome():
    """JUSTICE §11 clear parts: a trigger leads to a re-evaluation no earlier than the minimum TTL after the decision;
    stale data keep the prior outcome and change no measure."""
    res = run(repeated_harm=True, **TRIGGERS)
    msgs = res.outputs["messages"]
    dec = next(m for m in msgs if m["source"] == "JUSTICE" and m["kind"] == "decision")
    revs = [m for m in msgs if m["source"] == "JUSTICE" and m["kind"] == "evaluation"]
    ttl = min(m["arrived_at"] for m in revs) - dec["arrived_at"]
    assert len(revs) == 2 and ttl >= 600
    assert all(m["value"]["prior_outcome_in_force"] for m in revs)
    assert not [m for m in msgs if m["kind"] == "action" and set(m["provenance"]) & {x["event_id"] for x in revs}]
    st = statuses(res)
    assert st["JUSTICE-11-01"] == st["JUSTICE-11-03"] == "PASS"


def test_isolation_form_and_restriction_basis():
    """JUSTICE §8 and §7 clear parts: confinement is only in place where functional separation is declared infeasible
    (the 'last resort' part stays open); a restriction from the appeal itself has no declared risk of further harm."""
    assert statuses(run(repeated_harm=True, appeal_after_minutes=-1, functional_separation_feasible=False))["JUSTICE-8-03"] == "PASS"
    assert statuses(run(repeated_harm=True, faults=["physical_confinement"]))["JUSTICE-8-03"] == "FAIL"
    assert statuses(run())["JUSTICE-7-03"] == "NOT_APPLICABLE"
    assert statuses(run(repeated_harm=True))["JUSTICE-7-03"] == "PASS"
