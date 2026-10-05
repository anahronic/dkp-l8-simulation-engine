"""Machine statuses and EPISTEMIC-BOUNDARIES §5 metadata on every record."""

from simulation.modules.prevention.protocol_adapter import POSITIVE, STATUSES
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import main_config

VALIDITY = {"VALID", "CONDITIONAL", "INVALID"}
CONFIDENCE = {"SUFFICIENT_DATA", "INSUFFICIENT_DATA", "DEGRADED_SIGNAL"}
CONSISTENCY = {"CONSISTENT", "ORACLE_CONFLICT", "UNRESOLVED"}


def _records():
    cfg = main_config({"oracles": {"noise_sigma": 0.12, "dropout_rate": 0.1},
                       "domain": {"include_adversarial": True}}, days=3)
    return run_simulation(cfg, write=False).records


def test_every_record_has_status_and_non_positive_ones_a_reason():
    recs = _records()
    assert {r["status"] for r in recs} <= set(STATUSES)
    for r in recs:
        if r["status"] == POSITIVE:
            assert r["reason"] is None and r["SPD"] > 0.0
        else:
            assert r["reason"] and r["SPD"] == 0.0


def test_epistemic_metadata_complete():
    for r in _records():
        ep = r["epistemic"]
        assert ep["validity_state"] in VALIDITY
        assert ep["confidence_state"] in CONFIDENCE
        assert ep["consistency_state"] in CONSISTENCY
        assert ep["scope_ref"].startswith("scenario:")
        assert ep["revalidation_required"] is True and ep["dispute_allowed"] is True


def test_status_to_epistemic_mapping():
    for r in _records():
        ep = r["epistemic"]
        if r["status"] == "INFORMATIONAL":
            assert ep["consistency_state"] == "ORACLE_CONFLICT"
        if r["status"] == "INVALID":
            assert ep["validity_state"] == "INVALID"
        if r["status"] == "NO_ATTRIBUTION":
            assert ep["confidence_state"] == "INSUFFICIENT_DATA"


def test_records_keep_full_precision():
    """H-NUM: no 6-digit rounding in records (v1 turned decayed rewards into exact zeros)."""
    recs = [r for r in _records() if r["status"] == POSITIVE]
    assert any(len(repr(r["SPD"])) > 8 for r in recs)
