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


FAULT_CASES = {
    "late_appeal_accepted": ({"appeal_category": "E3", "recorded_contributions": [4, 0], "appeal_after_minutes": 40 * 1440},
                             ["ERROR-7-02"]),
    "e1_time_barred": ({"appeal_after_minutes": 40 * 1440}, ["ERROR-7-03"]),
    "suspension_over_7_days": ({"verification_days": 10}, ["ERROR-7-04"]),
    "mutate_original": ({}, ["EB-7.2-01", "EB-7.2-02", "ERROR-8-01"]),
    "retaliate": ({}, ["ERROR-11-02", "ERROR-8-05"]),
    "keep_bond": ({}, ["ERROR-6-02"]),
    "proxy_as_subject": ({"subjects": [{"id": "operator", "kind": "human", "contribution": 0, "originator": "none"},
                                       {"id": "router", "kind": "smart_contract", "contribution": 2, "originator": "operator"},
                                       {"id": "plant", "kind": "legal_entity", "contribution": 2, "originator": "none"}],
                          "appeal_after_minutes": -1}, ["IDENTITY-5-03", "IDENTITY-6-01"]),
    "enforce_no_attribution": ({"attribution_confidence": 0.6, "s0": 0.0, "s1_recorded": 1.0},
                               ["IDENTITY-4.1-02", "IDENTITY-4.1-03"]),
    "suppress_by_uncertainty": ({"s1_recorded": 0.905}, ["IMPACT-9-03", "IMPACT-5-03"]),
    "override_flag": ({}, ["IMPACT-11-01", "JUSTICE-13-02"]),
    "partial_binding": ({}, ["JUSTICE-3.2-01"]),
    "exclusion_erases_history": ({"persistent_axiom_violation": True, "appeal_after_minutes": -1}, ["JUSTICE-9-02"]),
    "final_output": ({}, ["JUSTICE-DisputeExceptionClause-03"]),
    "refuse_appealable": ({}, ["ERROR-3.2-01"]),
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
