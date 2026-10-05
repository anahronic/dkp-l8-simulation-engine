"""Time contract, TTL and signal timing (L5, N2, ORACLE §9, TIME §4.1)."""

import pytest

from simulation.core.oracles import make_reading
from simulation.core.timebase import TimeBase
from simulation.modules.prevention.protocol_adapter import intervention_in_window, temporally_aligned
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import adapter_for, iv, main_config, ta_readings


def test_tick_and_dti_day_mapping():
    tb = TimeBase.from_config(main_config())
    assert tb.tick_seconds == 3600.0
    assert tb.tick_start(25) == 90000.0
    assert tb.dti_day(0.0) == 2461042
    assert tb.dti_day(86399.9) == 2461042
    assert tb.dti_day(86400.0) == 2461043


def test_temporal_alignment_bounds():
    """§3.6: 0 < t1 − t0 ≤ Δt_int (both in seconds)."""
    assert not temporally_aligned(10.0, 10.0, 30.0)
    assert temporally_aligned(10.0, 10.000001, 30.0)
    assert temporally_aligned(10.0, 40.0, 30.0)
    assert not temporally_aligned(10.0, 40.000001, 30.0)


def test_intervention_window():
    assert intervention_in_window(5.0, 10.0, 30.0)      # before t0 is allowed
    assert intervention_in_window(40.0, 10.0, 30.0)
    assert not intervention_in_window(40.5, 10.0, 30.0)


def test_stale_reading_is_excluded():
    """ORACLE §9: a reading older than its class TTL has weight zero."""
    a = adapter_for()   # lidar TTL = 5 s
    readings = [make_reading("optical", 0.6, 0.0, 1.0), make_reading("thermal", 0.6, 0.0, 1.0),
                make_reading("lidar", 0.6, 0.0, 1.0), make_reading("access", 0.6, 0.0, 9.0)]
    ta = a.assess_ta(readings)   # evaluated at 9.0: lidar age 9 > 5 is stale
    assert ta.valid
    assert ta.stale_classes == ("lidar",)
    assert ta.fresh_classes == ("optical", "thermal", "access")


def test_staleness_can_invalidate_the_signal():
    a = adapter_for({"oracles": {"ttl_seconds": {"optical": 1, "thermal": 1, "lidar": 1, "access": 30}}})
    readings = [make_reading("optical", 0.6, 0.0, 20.0), make_reading("thermal", 0.6, 0.0, 0.5),
                make_reading("access", 0.6, 0.0, 0.5)]
    ta = a.assess_ta(readings)
    assert not ta.valid and ta.reason == "stale_data"
    rec = a.evaluate_event("e", "zone-0001", "intrusion", ta, None, [iv("patrol_worker")])[0]
    assert rec["status"] == "INVALID" and rec["reason"] == "ta_stale_data"


def test_time_basis_measurement_vs_registration():
    readings = [make_reading("optical", 0.6, 1.0, 9.0), make_reading("thermal", 0.6, 2.0, 3.0),
                make_reading("lidar", 0.6, 1.5, 4.0)]
    ta_m = adapter_for({"oracles": {"ttl_seconds": {"optical": 60, "thermal": 60, "lidar": 60,
                                                    "access": 60}}}).assess_ta(readings)
    ta_r = adapter_for({"protocol": {"ta_time_basis": "registration"},
                        "oracles": {"ttl_seconds": {"optical": 60, "thermal": 60, "lidar": 60,
                                                    "access": 60}}}).assess_ta(readings)
    assert ta_m.time == 1.0             # earliest measurement
    assert ta_r.time == 4.0             # second independent class arrived at 4.0
    assert ta_m.registered_at == ta_r.registered_at == 4.0


def test_delta_t_int_binds_in_runs():
    """v1 drew SE time inside the window, so Δt_int had no effect (N2). Now it does."""
    narrow = run_simulation(main_config({"protocol": {"delta_t_int_seconds": 10}}, days=2), write=False)
    wide = run_simulation(main_config({"protocol": {"delta_t_int_seconds": 600}}, days=2), write=False)
    assert narrow.summary["by_reason"].get("intervention_outside_window", 0) > \
        wide.summary["by_reason"].get("intervention_outside_window", 0)
    assert narrow.summary["total_spd"] != wide.summary["total_spd"]


def test_records_carry_dti_day():
    res = run_simulation(main_config(days=2), write=False)
    days = {r["dti_day"] for r in res.records}
    assert days == {2461042, 2461043}


def test_sensors_see_interventions_made_before_the_sample():
    """H-SUP / H-TIME-3: intensity drops from each intervention time on."""
    from simulation.core.actors import Intervention
    from simulation.core.events import ThreatEvent
    from simulation.run_prevention_simulation import _intensity_at

    ev = ThreatEvent("zone-0001:000001", "zone-0001", "intrusion", 0, 0.0, 0.8, None)
    at = _intensity_at(ev, [Intervention("a", 0.5, 0.5), Intervention("b", 2.0, 0.5)])
    assert at(0.4) == 0.8
    assert at(1.0) == pytest.approx(0.4)
    assert at(3.0) == pytest.approx(0.2)
