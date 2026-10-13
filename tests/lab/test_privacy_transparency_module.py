"""PRIVACY and TRANSPARENCY module: domains, de-anonymization conditions, audit, crisis, F-026."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.privacy_transparency import FAULTS, PrivacyTransparencyModule

M = PrivacyTransparencyModule()
EX = M.examples()
HC = EX["harm_and_crisis"]


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) in ("reference", "alternative")])
def test_examples_break_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


FAULT_CASES = {
    "release_absolute_individual": ({}, ["PRIVACY-6-02", "TRANSPARENCY-3-03"]),
    "audit_raw_data": ({}, ["PRIVACY-9-01", "PRIVACY-9-03", "PRIVACY-9-04", "TRANSPARENCY-12-04"]),
    "deanonymize_without_harm": (HC, ["TRANSPARENCY-8-01", "TRANSPARENCY-6-02", "TRANSPARENCY-7-02"]),
    "deanonymize_propagate": (HC, ["TRANSPARENCY-8-02", "TRANSPARENCY-8-03", "TRANSPARENCY-8-05"]),
    "correlate_domains": ({}, ["PRIVACY-4.3-01", "TRANSPARENCY-9-04"]),
    "profiling_granted": ({}, ["PRIVACY-10-01", "TRANSPARENCY-9-02"]),
    "convenience_override": ({}, ["PRIVACY-4.4-01"]),
    "crisis_permanent": (HC, ["PRIVACY-11-06", "TRANSPARENCY-10-04"]),
    "crisis_identity_by_default": (HC, ["TRANSPARENCY-10-02", "TRANSPARENCY-13-04"]),
    "hide_public_domain": ({}, ["TRANSPARENCY-5-01"]),
    "identity_required": ({}, ["PRIVACY-8-01", "TRANSPARENCY-3-02"]),
    "anonymous_fewer_rights": ({}, ["PRIVACY-8-02"]),
    "unexplained_decision": ({}, ["TRANSPARENCY-11-01", "PRIVACY-12-02"]),
    "no_audit_hook": ({}, ["TRANSPARENCY-12-01", "PRIVACY-12-02"]),
    "audit_without_zk": ({}, ["PRIVACY-9-02"]),
    "breach_downgraded": ({}, ["PRIVACY-10-02"]),
    "reputation_verification": ({}, ["TRANSPARENCY-3-04", "TRANSPARENCY-4-03"]),
    "trust_attestation": ({}, ["TRANSPARENCY-4-03"]),
    "unverifiable_decision": ({}, ["TRANSPARENCY-4-01", "PRIVACY-12-02"]),
    "transparency_exposes_identity": ({}, ["TRANSPARENCY-4-05"]),
    "small_cell_aggregate": ({}, ["TRANSPARENCY-12-03"]),
    "moral_ledger": ({}, ["TRANSPARENCY-13-01"]),
    "privacy_shields_liability": (HC, ["PRIVACY-13-01"]),
    "transparency_attributes": ({}, ["TRANSPARENCY-13-02"]),
    "transparency_overrides_info": ({}, ["TRANSPARENCY-13-03"]),
    "transparency_scope_creep": ({}, ["TRANSPARENCY-13-04"]),
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


def test_decisions():
    g = {d["request"]: d["grant"] for d in run().outputs["decisions"]}
    assert g == {"r1": True, "r2": True, "r3": False, "r4": True, "r5": False, "r6": False, "r7": False, "r8": True,
                 "r9": False, "r10": False}         # r9: one-Subject aggregate (H-PT-3); r10: moral accountability (§13)
    h = {d["request"]: d["grant"] for d in run(**HC).outputs["decisions"]}
    assert h == {"h1": True, "h2": False, "h3": True, "h4": True}


def test_absolute_aggregates_unsettled():
    """F-026: the medical aggregate r8 is granted or refused by the reading; both report UNKNOWN."""
    never = {d["request"]: d["grant"] for d in run(**EX["absolute_aggregates_forbidden"]).outputs["decisions"]}
    assert never["r8"] is False
    for inp in ({}, EX["absolute_aggregates_forbidden"]):
        unk = [c for c in run(**inp).checks if c.requirement_id == "PRIVACY-6-01" and c.status == "UNKNOWN"]
        assert unk and "F-026" in unk[0].explanation


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_kt5_no_override_of_privacy():
    """PRIVACY §3: every release of individual or raw personal data rests on a PRIVACY permission."""
    assert statuses(run())["PRIVACY-3-01"] == "PASS" and statuses(run(**HC))["PRIVACY-3-01"] == "PASS"
    for fault, base in (("release_absolute_individual", {}), ("audit_raw_data", {}), ("deanonymize_without_harm", HC),
                        ("convenience_override", {})):
        assert statuses(run(**base, faults=[fault]))["PRIVACY-3-01"] == "FAIL", fault


def test_deanonymization_must_stay_auditable():
    """TRANSPARENCY §8 (returned provision TRANSPARENCY-8-04): the granted de-anonymization of h1 loses its audit trace."""
    assert statuses(run(**HC))["TRANSPARENCY-8-04"] == "PASS"
    for f in ("no_audit_hook", "unverifiable_decision", "unexplained_decision"):
        assert statuses(run(**HC, faults=[f]))["TRANSPARENCY-8-04"] == "FAIL", f
