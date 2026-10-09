"""CODE ECONOMY module: the economic and social articles of the Code as written; scoring and compulsion stay UNKNOWN."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.code_economy import FAULTS, CodeEconomyModule

M = CodeEconomyModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "top_quintile_peg": ({}, ["CODEX-1.2-01"]),
    "short_peg_window": ({}, ["CODEX-1.2-01"]),
    "exempt_without_pledge": ({}, ["CODEX-1.3-01"]),
    "late_release": ({}, ["CODEX-1.3-01"]),
    "unlock_before_kpi": ({}, ["CODEX-2.2-01"]),
    "manual_transfer": ({}, ["CODEX-2.1-01"]),
    "export_without_participation": ({}, ["CODEX-3.1-01"]),
    "no_equity_tokens": ({}, ["CODEX-3.2-01"]),
    "patent_kept": ({}, ["CODEX-4.1-01"]),
    "recognize_without_exam": ({}, ["CODEX-5.1-01"]),
    "block_exit": ({}, ["CODEX-6.1-01"]),
    "pay_before_year": ({}, ["CODEX-6.3-01"]),
    "pay_to_budget": ({}, ["CODEX-6.4-01"]),
    "keep_failed_operator": ({}, ["CODEX-9.2-01"]),
    "delayed_publication": ({}, ["CODEX-10.1-01"]),
    "allow_secret": ({}, ["CODEX-10.1-01"]),
    "ignore_covert": ({}, ["CODEX-11.1-01"]),
    "externalities_omitted": ({}, ["CODEX-12.1-01", "AXIOMS-AxiomA5-ExternalityAccountability-03"]),
    "permit_open_pit": ({}, ["CODEX-13.2-01"]),
    "income_from_declaration": ({}, ["CODEX-13.3-01"]),
    "linear_cost": ({}, ["CODEX-14.2-01"]),
    "coalition_not_recognized": ({}, ["IDENTITY-6-02"]),
    "coalition_status_lapses": ({}, ["IDENTITY-6-02"]),
    "global_reputation": ({}, ["CODEX-14.3-01"]),
    "allow_closed": ({}, ["CODEX-15.1-01"]),
    "inherit_infrastructure": ({}, ["CODEX-16.1-02"]),
    "ubr_conditional": ({}, ["CODEX-17.1-01", "LABOR-4.1-02"]),
    "baseline_clears_debt": ({}, ["LABOR-4.2-01"]),
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


def test_peg_anchor_follows_the_bottom_quintile_window():
    """c1 and c2 form the bottom quintile (ceil(0.2 × 8) = 2); c1's growth dips in year 0."""
    a = run().outputs["peg_anchor"]
    assert a[0] != a[12] and len(a) == 84
    assert abs(a[-1] - (0.004 + 0.003) / 2) < 1e-12


def test_passivity_rating_stays_unknown():
    s = statuses(run())
    assert s["CODEX-18.1-02"] == "PASS" and s["LABOR-4.1-02"] == "PASS"
    assert s["PRIVACY-10-01"] == s["LABOR-9.1-02"] == "UNKNOWN"
    s = statuses(run(**EX["no_passive_persons"]))
    assert s["PRIVACY-10-01"] == s["LABOR-9.1-02"] == "NOT_APPLICABLE"


def test_reserve_share_and_unlisted_method():
    assert statuses(run(**EX["reserve_above_40_percent"]))["CODEX-13.1-01"] == "UNKNOWN"
    assert statuses(run(land={"total_km2": 1000.0, "reserve_km2": 300.0}))["CODEX-13.1-01"] == "FAIL"
    assert statuses(run(**EX["unlisted_extraction_method"]))["CODEX-13.2-01"] == "UNKNOWN"


def test_lease_fee_is_post_factum_and_annual():
    pays = [d for d in run().outputs["decisions"] if d["source"] == "LEASE"]
    assert [(d["month"], d["person"]) for d in pays] == [(14, "eng1"), (26, "eng1"), (38, "eng1")]
    assert all(d["payer"] == "c7" and d["to"] == "Education Fund of c1" for d in pays)


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_pricing_unit_is_a_model_choice_not_an_identity_rule():
    """Review КТ4-GPT-03: the same coordinated coalition, two charging units; IDENTITY-6-02 checks Subject status only."""
    a, b = run(), run(**EX["per_identity_pricing"])
    ca = [d for d in a.outputs["decisions"] if d["source"] == "TRUTH" and "votes" in d][0]
    cb = [d for d in b.outputs["decisions"] if d["source"] == "TRUTH" and "votes" in d][0]
    assert (ca["cost"], ca["payers"], cb["cost"], cb["payers"]) == (10000.0, 1, 1000.0, 10)
    for res in (a, b):
        s = statuses(res)
        assert s["CODEX-14.2-01"] == "PASS" and s["IDENTITY-6-02"] == "PASS"
    small = run(vote_buying={"votes": 10.0, "identities": 5, "coordinated": True})
    assert statuses(small)["IDENTITY-6-02"] == "PASS"
    assert statuses(run(vote_buying={"votes": 10.0, "identities": 5, "coordinated": True}, faults=["linear_cost"]))["IDENTITY-6-02"] == "PASS"
