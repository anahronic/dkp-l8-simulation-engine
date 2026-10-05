"""§9.3 recurrence (H-T-1..3; A3, U3): clock, window, equal times, history unit, order independence."""

import math
import random

import pytest

from simulation.modules.prevention.protocol_adapter import RecurrenceHistory
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import adapter_for, iv, main_config, ta_readings

CLASSES = ["optical", "thermal", "lidar", "access"]


def _history(key_fields=("actor",), threshold=3, decay=0.9, window=None, mode="retrospective"):
    return RecurrenceHistory(key_fields, threshold, decay, window, mode)


def _series(h, key, times):
    for i, t in enumerate(times):
        h.add(key, t, t, f"e{i:05d}")
    return [h.factor(key, t, t, f"e{i:05d}") for i, t in enumerate(times)]


@pytest.mark.parametrize("threshold,first_decayed", [(1, 2), (3, 4), (5, 6)])
def test_onset(threshold, first_decayed):
    ts = _series(_history(threshold=threshold), ("a",), [float(t) for t in range(10)])
    assert ts[:first_decayed - 1] == [1.0] * (first_decayed - 1)
    assert ts[first_decayed - 1] == pytest.approx(0.9)


def test_future_occurrences_are_not_counted():
    """U3: an occurrence at t = 100 is not 'previous' for t = 5 (v2.0 gave T = 0.5)."""
    h = _history(threshold=1, decay=0.5, window=10.0)
    h.add(("a",), 100.0, 100.0, "late")
    assert h.factor(("a",), 5.0, 5.0, "early") == 1.0


def test_window_is_half_open():
    h = _history(threshold=1, decay=0.5, window=10.0)
    h.add(("a",), 0.0, 0.0, "e0")
    assert h.factor(("a",), 10.0, 10.0, "e1") == 0.5      # t0 − W ≤ t0' : included
    assert h.factor(("a",), 10.0001, 10.0001, "e1") == 1.0  # older than the window


def test_equal_times_are_not_earlier_and_ids_do_not_matter():
    for ids in (("a-event", "b-event"), ("z-event", "b-event")):
        h = _history(threshold=1, decay=0.5)
        h.add(("a",), 7.0, 7.0, ids[0])
        assert h.factor(("a",), 7.0, 7.0, ids[1]) == 1.0


def test_as_of_decision_ignores_occurrences_confirmed_later():
    h = _history(threshold=1, decay=0.5, mode="as_of_decision")
    h.add(("a",), 0.0, 50.0, "e0")                 # t0 = 0, confirmed only at 50
    assert h.factor(("a",), 10.0, 20.0, "e1") == 1.0   # decided at 20: not yet known
    assert h.factor(("a",), 10.0, 60.0, "e1") == 0.5   # decided at 60: known
    r = _history(threshold=1, decay=0.5, mode="retrospective")
    r.add(("a",), 0.0, 50.0, "e0")
    assert r.factor(("a",), 10.0, 20.0, "e1") == 0.5


def _event_readings(t):
    return ta_readings([0.8] * 4, t=t), ta_readings([0.2] * 4, t=t + 5.0)


def _prepare_all(adapter, times, actors=("patrol_worker",)):
    out = []
    for i, t in enumerate(times):
        ta, se = _event_readings(t)
        ivs = [iv(a, order=j, time=t + 2.0, claim=1.0 / len(actors)) for j, a in enumerate(actors)]
        out.append(adapter.prepare(f"zone-0001:{i:06d}:intrusion", "zone-0001", "intrusion", ta, se, ivs))
    return out


def test_two_pass_result_does_not_depend_on_processing_order():
    overlay = {"protocol": {"recurrence": {"threshold": 1, "decay": 0.5, "key": ["actor"], "window_seconds": 1000.0}}}
    times = [5.0, 100.0, 50.0, 7.5, 300.0, 299.0, 1500.0]
    chrono = adapter_for(overlay).finalize(_prepare_all(adapter_for(overlay), sorted(times)))
    rng = random.Random(7)
    for _ in range(5):
        a = adapter_for(overlay)
        pes = _prepare_all(a, sorted(times))
        rng.shuffle(pes)
        assert a.finalize(pes) == chrono
    by_t0 = sorted((r["ta"]["time"], r["factors"]["T"]) for r in chrono)
    assert [t for _, t in by_t0] == [1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125, 1.0]   # 1500: window [500, 1500) is empty


def test_several_threats_same_channel_same_tick():
    """Two events of one channel inside one tick: the earlier t0 counts for the later one only."""
    overlay = {"protocol": {"recurrence": {"threshold": 1, "decay": 0.5, "key": ["actor", "channel"]}}}
    a = adapter_for(overlay)
    pes = _prepare_all(a, [40.0, 10.0])          # processed late-first
    recs = {r["event_id"]: r for r in a.finalize(pes)}
    assert recs["zone-0001:000001:intrusion"]["factors"]["T"] == 1.0   # t0 = 10
    assert recs["zone-0001:000000:intrusion"]["factors"]["T"] == 0.5   # t0 = 40


def test_one_occurrence_per_event_and_key():
    """Key without actor: two subjects of one event register a single occurrence."""
    overlay = {"protocol": {"recurrence": {"threshold": 1, "decay": 0.5, "key": ["zone", "channel"]},
                            "attribution_rule": "proportional"}}
    a = adapter_for(overlay)
    pes = _prepare_all(a, [0.0, 100.0], actors=("patrol_worker", "optimizer_actor"))
    recs = a.finalize(pes)
    assert a.history.snapshot() == {"zone-0001|intrusion": 2}
    later = [r for r in recs if r["event_id"].endswith("000001:intrusion")]
    assert all(r["factors"]["T"] == 0.5 for r in later)


def test_sum_bounded_for_one_fixed_key():
    """For T = ρ^max(0, n − k) the sum over one key is ≤ k + ρ/(1 − ρ) (12 for k=3, ρ=0.9).
    This is a property of this rule and one key only — not a guarantee of PREVENTION (A3)."""
    total = math.fsum(_series(_history(), ("a",), [float(t) for t in range(5000)]))
    assert total <= 3 + 0.9 / 0.1 + 1e-9
    assert total == pytest.approx(12.0, abs=1e-6)


def test_new_key_starts_a_new_series():
    h = _history()
    _series(h, ("a",), [float(t) for t in range(50)])
    assert h.factor(("a-renamed",), 51.0, 51.0, "x") == 1.0


def test_v1_rule_decays_honest_work():
    """Reported, not endorsed: with key actor+channel over the whole run, routine work decays."""
    res = run_simulation(main_config(days=5), write=False)
    assert res.summary["evaluation"]["honest_decayed_fraction"] > 0.5
    windowed = run_simulation(main_config({"protocol": {"recurrence": {
        "key": ["actor", "zone", "channel"], "window_seconds": 86400}}}, days=5), write=False)
    assert windowed.summary["evaluation"]["honest_decayed_fraction"] < \
        res.summary["evaluation"]["honest_decayed_fraction"]
