"""H-TTL-2 (GPT 7 Q1, GPT 8 §3–§4): TTL per signal vs re-applied at the decision instant."""

import pytest

from simulation.core.oracles import make_reading
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import adapter_for, iv, main_config

ALL4 = ("optical", "thermal", "lidar", "access")


def _adapter(mode, ttl, eps=0.15):
    return adapter_for({"protocol": {"ttl_reference": mode, "epsilon_consistency": eps},
                        "oracles": {"ttl_seconds": ttl}})


def _ta(values, t=0.0):
    return [make_reading(c, v, t) for c, v in zip(ALL4, values)]


def test_partial_expiry_recomputes_everything():
    """GPT 8 §3: two TA classes expire by the decision; TA, S and C are recomputed."""
    ttl = {"optical": 1, "thermal": 1, "lidar": 20, "access": 20}
    ta, se = _ta([0.4, 0.4, 0.8, 0.8]), _ta([0.2] * 4, t=10.0)
    sig = _adapter("signal", ttl, eps=0.5).evaluate_event("e", "zone-0001", "intrusion", ta, se,
                                                          [iv("patrol_worker", time=2.0)])[0]
    dec = _adapter("decision", ttl, eps=0.5).evaluate_event("e", "zone-0001", "intrusion", ta, se,
                                                            [iv("patrol_worker", time=2.0)])[0]
    assert sig["ta"]["intensity"] == 0.4 and sig["factors"]["S"] == pytest.approx(0.5)
    assert sig["factors"]["C"] == 1.0 and sig["SPD"] == pytest.approx(1.0 * 0.5)
    assert dec["ta"]["intensity"] == 0.8 and dec["factors"]["S"] == pytest.approx(0.75)
    assert dec["factors"]["C"] == 0.5 and dec["SPD"] == pytest.approx(1.0 * 0.75 * 0.5)
    assert dec["ta_signal"]["intensity"] == 0.4          # what the signal-time view was
    assert dec["decision_at"] == 10.0


def test_ta_expired_at_decision_is_invalid():
    ttl = {c: 5 for c in ALL4}
    ta, se = _ta([0.8] * 4), _ta([0.2] * 4, t=10.0)
    sig = _adapter("signal", ttl).evaluate_event("e", "zone-0001", "intrusion", ta, se, [iv("patrol_worker")])[0]
    dec = _adapter("decision", ttl).evaluate_event("e", "zone-0001", "intrusion", ta, se, [iv("patrol_worker")])[0]
    assert sig["status"] == "POSITIVE"                  # GPT 7 §6 example
    assert dec["status"] == "INVALID" and dec["reason"] == "ta_stale_data_at_decision"


def test_early_completion_within_ttl_is_recognized_in_decision_mode():
    """GPT 8 §4: TTL < Δt_int does not make recognition impossible."""
    ttl = {c: 5 for c in ALL4}
    rec = _adapter("decision", ttl).evaluate_event("e", "zone-0001", "intrusion", _ta([0.8] * 4),
                                                   _ta([0.2] * 4, t=3.0), [iv("patrol_worker", time=1.0)])[0]
    assert rec["status"] == "POSITIVE" and rec["SPD"] == pytest.approx(0.75)


def test_se_expired_at_decision():
    """A late TA arrival sets the decision instant; the short-TTL SE classes are stale by then."""
    ttl = {"optical": 60, "thermal": 60, "lidar": 3, "access": 3}
    ta = [make_reading("optical", 0.8, 0.0, 20.0), make_reading("thermal", 0.8, 0.0, 0.0),
          make_reading("lidar", 0.8, 0.0, 0.5), make_reading("access", 0.8, 0.0, 0.5)]
    se = [make_reading("lidar", 0.2, 5.0, 5.5), make_reading("access", 0.2, 5.0, 5.5)]
    sig = _adapter("signal", ttl).evaluate_event("e", "zone-0001", "intrusion", ta, se, [iv("patrol_worker")])[0]
    dec = _adapter("decision", ttl).evaluate_event("e", "zone-0001", "intrusion", ta, se, [iv("patrol_worker")])[0]
    assert sig["status"] == "POSITIVE"
    assert dec["decision_at"] == 20.0
    assert dec["status"] == "INVALID" and dec["reason"] == "se_stale_data_at_decision"


def test_age_equal_to_ttl_is_fresh():
    ttl = {c: 10 for c in ALL4}
    rec = _adapter("decision", ttl).evaluate_event("e", "zone-0001", "intrusion", _ta([0.8] * 4),
                                                   _ta([0.2] * 4, t=10.0), [iv("patrol_worker")])[0]
    assert rec["status"] == "POSITIVE"


def test_decision_instant_uses_original_availability():
    """The clock is set by the latest arrival before filtering; dropping a late stale reading
    does not move the decision instant backwards."""
    ttl = {"optical": 60, "thermal": 60, "lidar": 60, "access": 1}
    ta = _ta([0.8] * 4)
    se = [make_reading(c, 0.2, 5.0, 5.0) for c in ("optical", "thermal", "lidar")] + \
         [make_reading("access", 0.2, 5.0, 25.0)]
    rec = _adapter("decision", ttl).evaluate_event("e", "zone-0001", "intrusion", ta, se, [iv("patrol_worker")])[0]
    assert rec["decision_at"] == 25.0
    assert "access" in rec["se"]["stale_classes"]


def test_filtering_never_turns_consistent_into_inconsistent():
    """Dropping readings can only narrow Δ_oracle; an informational TA schedules no SE."""
    ttl = {"optical": 1, "thermal": 60, "lidar": 60, "access": 60}
    ta = _ta([0.3, 0.8, 0.8, 0.8])        # Δ = 0.5 > ε: informational at signal time
    rec = _adapter("decision", ttl).evaluate_event("e", "zone-0001", "intrusion", ta, None, [iv("patrol_worker")])[0]
    assert rec["status"] == "INFORMATIONAL" and rec["reason"] == "oracle_inconsistency"


def test_both_modes_run_and_have_distinct_inputs():
    a = run_simulation(main_config({"protocol": {"ttl_reference": "signal"}}, days=2), write=False)
    b = run_simulation(main_config({"protocol": {"ttl_reference": "decision"}}, days=2), write=False)
    assert a.manifest["input_id"] != b.manifest["input_id"]
    assert all(r["ttl_reference"] == "decision" for r in b.records)
