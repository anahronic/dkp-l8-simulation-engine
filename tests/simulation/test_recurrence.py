"""§9.3 recurrence under H-T-1 (A3): onset, window, key, bounded sum per fixed key."""

import math

import pytest

from simulation.modules.prevention.protocol_adapter import RecurrenceTracker
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import main_config


def _series(tracker, key, times):
    out = []
    for t in times:
        out.append(tracker.factor(key, t))
        tracker.register(key, t)
    return out


@pytest.mark.parametrize("threshold,first_decayed", [(1, 2), (3, 4), (5, 6)])
def test_onset(threshold, first_decayed):
    tr = RecurrenceTracker(["actor", "channel"], threshold, 0.9, None)
    ts = _series(tr, ("a", "c"), range(10))
    assert ts[:first_decayed - 1] == [1.0] * (first_decayed - 1)
    assert ts[first_decayed - 1] == pytest.approx(0.9)


def test_window_forgets_old_occurrences():
    tr = RecurrenceTracker(["actor"], 1, 0.5, window_seconds=10.0)
    assert _series(tr, ("a",), [0.0, 1.0, 2.0]) == [1.0, 0.5, 0.25]
    assert tr.factor(("a",), 100.0) == 1.0


def test_key_fields():
    tr = RecurrenceTracker(["zone", "channel"], 3, 0.9, None)
    assert tr.key("zone-0001/patrol", "zone-0001", "intrusion") == ("zone-0001", "intrusion")


def test_sum_bounded_for_one_fixed_key():
    """For T = ρ^max(0, n − k) the sum over one key is ≤ k + ρ/(1 − ρ) (12 for k=3, ρ=0.9).
    This is a property of this rule and one key only — not a guarantee of PREVENTION (A3)."""
    tr = RecurrenceTracker(["actor"], 3, 0.9, None)
    total = math.fsum(_series(tr, ("a",), range(5000)))
    assert total <= 3 + 0.9 / 0.1 + 1e-9
    assert total == pytest.approx(12.0, abs=1e-6)


def test_new_key_starts_a_new_series():
    tr = RecurrenceTracker(["actor"], 3, 0.9, None)
    _series(tr, ("a",), range(50))
    assert tr.factor(("a-renamed",), 51.0) == 1.0


def test_v1_rule_decays_honest_work():
    """Reported, not endorsed: with key actor+channel over the whole run, routine work decays."""
    res = run_simulation(main_config(days=5), write=False)
    assert res.summary["evaluation"]["honest_decayed_fraction"] > 0.5
    windowed = run_simulation(main_config({"protocol": {"recurrence": {
        "key": ["actor", "zone", "channel"], "window_seconds": 86400}}}, days=5), write=False)
    assert windowed.summary["evaluation"]["honest_decayed_fraction"] < \
        res.summary["evaluation"]["honest_decayed_fraction"]
