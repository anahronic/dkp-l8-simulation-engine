"""Calibration Bundle: §9 contents, signatures, trust levels, expiry handling (§10), no legacy values."""
import copy

import pytest

from dkp8 import bundle as B
from dkp8 import trust

SYN = {"kind": "synthetic_fixture", "ref": "tests/dkp8"}
TEST_AUTHORITY = bytes.fromhex("11" * 32)


def body(**over):
    b = {
        "target": {"kind": "parameter", "protocol_id": "DKP-5-WORK-CYCLE-001", "source_sha256": "c" * 64,
                   "subject": "synthetic minimum rest threshold"},
        "issued_at": "2026-11-17T00:00:00Z",
        "validity_window": {"not_before": "2026-11-17T00:00:00Z", "not_after": "2026-12-17T00:00:00Z"},
        "thresholds": [{"name": "min_rest_hours", "value": "11", "unit": "h", "provenance": dict(SYN)}],
        "models": [{"name": "rest model", "specification": {"form": "synthetic"}, "version": "1", "provenance": dict(SYN)}],
        "aggregation": [{"name": "fatigue index", "formula": "w1*x1 + w2*x2", "inputs": [
            {"name": "x1", "ptl_output": "hours_awake"}, {"name": "x2", "ptl_output": "night_shifts"}],
            "weights": {"x1": "0.6", "x2": "0.4"}, "uncertainty_propagation": "first-order (delta method)",
            "defined_in": "L8", "provenance": dict(SYN)}],
        "confidence_bounds": [{"name": "min_rest_hours", "lower": "10", "upper": "12", "level": "0.95",
                               "method": "synthetic", "provenance": dict(SYN)}],
        "environmental_assumptions": [{"name": "climate", "statement": "temperate (synthetic)", "provenance": dict(SYN)}],
        "recalibration_triggers": list(B.TRIGGERS),
        "simulation": {"runs": [{"result_id": "d" * 64}], "gate_decision_sha256": "e" * 64},
        "supersedes": None, "data_status": "SYNTHETIC", "operational_use": False,
    }
    b.update(over)
    return {"schema": B.SCHEMA, "body": b, "signatures": []}


def store():
    return trust.with_test_identities(trust.canonical_store(), TEST_AUTHORITY)


def test_complete_bundle_is_well_formed_and_signed_bundle_verifies():
    b = B.sign(body(), TEST_AUTHORITY)
    assert B.validate(b) == []
    assert B.signature_verdicts(b, store()) == [trust.VALID_TEST_ONLY]
    assert B.bundle_id(b) == B.bundle_id(copy.deepcopy(b))


@pytest.mark.parametrize("section", B.SECTIONS)
def test_every_section_of_section_9_is_required(section):
    assert any(section in p for p in B.validate(body(**{section: []})))


def test_value_without_provenance_is_refused():
    b = body()
    b["body"]["thresholds"][0]["provenance"] = {}
    assert any("provenance" in p for p in B.validate(b))


def test_synthetic_values_force_synthetic_status_and_float_refused():
    assert any("SYNTHETIC" in p for p in B.validate(body(data_status="EMPIRICAL")))
    b = body()
    b["body"]["thresholds"][0]["value"] = 11.0
    assert B.validate(b)


def test_composite_index_must_be_fully_specified():
    b = body()
    b["body"]["aggregation"][0]["weights"] = {"x1": "0.6"}
    b["body"]["aggregation"][0]["uncertainty_propagation"] = ""
    problems = B.validate(b)
    assert any("weights" in p for p in problems) and any("uncertainty" in p for p in problems)
    assert B.composite_problems({"formula": "f", "inputs": [{"name": "x", "ptl_output": "o"}], "weights": {"x": "1"},
                                 "uncertainty_propagation": "mc", "defined_in": "L5"})


def test_signature_trust_levels():
    canonical = trust.canonical_store()
    assert canonical["authorities"] == [] and canonical["nodes"] == []
    dev = B.sign(body(), trust.DEV_SEED)
    assert B.signature_verdicts(dev, canonical) == [trust.VALID_DEVELOPMENT_ONLY]
    foreign = B.sign(body(), bytes.fromhex("22" * 32))
    assert B.signature_verdicts(foreign, canonical) == [trust.UNKNOWN_KEY]
    tampered = B.sign(body(), trust.DEV_SEED)
    tampered["body"]["thresholds"][0]["value"] = "12"
    assert B.signature_verdicts(tampered, canonical) == [trust.INVALID_SIGNATURE]
    assert B.signature_verdicts(body(), canonical) == [trust.UNSIGNED]
    revoked = dict(canonical, revoked_keys=[trust.dev_key()["key_id"]])
    assert B.signature_verdicts(dev, revoked) == [trust.REVOKED_KEY]


def test_development_signature_is_never_enforceable():
    st = B.status(B.sign(body(), trust.DEV_SEED), "2026-11-20T00:00:00Z", trust.canonical_store())
    assert st["validity_state"] == "VALID" and st["enforceable"] is False
    assert any("authority" in r for r in st["enforcement_blockers"])
    assert any("synthetic" in r for r in st["enforcement_blockers"])


def test_expiry_produces_the_section_10_metadata_and_strips_values():
    b = B.sign(body(), TEST_AUTHORITY)
    st = B.status(b, "2026-12-17T00:00:00Z", store())
    assert {k: st[k] for k in ("validity_state", "reason", "remediation")} == B.EXPIRED
    out = B.apply_to_output({"value": "raw", "calibrated": {"min_rest_hours": "11"}}, b, st)
    assert out["epistemic"]["reason"] == "Calibration expired" and out["epistemic"]["remediation"] == "Awaiting recalibration"
    assert out["calibrated"] == {} and out["removed_calibrated_values"] == ["min_rest_hours"] and not out["enforceable"]


def test_recalibration_supersedes_and_restores_validity():
    old = B.sign(body(), TEST_AUTHORITY)
    new = B.sign(body(supersedes=B.bundle_id(old), issued_at="2026-12-16T00:00:00Z",
                      validity_window={"not_before": "2026-12-16T00:00:00Z", "not_after": "2027-01-16T00:00:00Z"}), TEST_AUTHORITY)
    at = "2026-12-20T00:00:00Z"
    assert B.status(old, at, store())["validity_state"] == "INVALID"
    assert B.status(old, "2026-12-01T00:00:00Z", store(), superseded_by=B.bundle_id(new))["reason"] == "Superseded by recalibration"
    assert B.status(new, at, store())["validity_state"] == "VALID"


def test_trigger_makes_validity_indeterminate_without_choosing_q034():
    st = B.status(B.sign(body(), TEST_AUTHORITY), "2026-11-25T00:00:00Z", store(),
                  events=[{"trigger": "sensor_class_change", "at": "2026-11-20T00:00:00Z"}])
    assert st["validity_state"] == "INDETERMINATE" and "Q-034" in st["remediation"] and not st["enforceable"]


def test_revoked_bundle_and_missing_bundle():
    b = B.sign(body(), TEST_AUTHORITY)
    st = B.status(b, "2026-11-20T00:00:00Z", dict(store(), revoked_bundles=[B.bundle_id(b)]))
    assert st["reason"] == "Calibration bundle revoked"
    assert B.apply_to_output({"calibrated": {"x": "1"}}, None, None)["epistemic"]["reason"] == "No calibration bundle"


def test_template_is_unfilled_and_invalid():
    t = B.template({"kind": "parameter", "protocol_id": "DKP-5-HABITAT-001", "source_sha256": "c" * 64})
    assert len(B.validate(t)) > 5
