"""CBF (L4, N7): standard estimators, order independence, observed input, audit-only."""

import itertools
import statistics

import pytest

from simulation.core.cbf import CBFRegistry
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import main_config


def _cbf(xs):
    r = CBFRegistry()
    for x in xs:
        r.update("z", "c", x)
    return r.get("z", "c")


@pytest.mark.parametrize("xs", [[0, 1], [0, 1, 2], [0.88] * 3 + [0.92] * 3, [1, 2, 3, 4, 5]])
def test_matches_reference_estimators(xs):
    """GPT 6 table: v1 gave 0.790569 for 0,1,2 (neither estimator)."""
    c = _cbf(xs)
    assert c.std_population == pytest.approx(statistics.pstdev(xs), rel=1e-12)
    assert c.std_sample == pytest.approx(statistics.stdev(xs), rel=1e-12)


def test_order_does_not_matter():
    """v1: 0,1,2 → 0.790569 but 0,2,1 → 0.707107."""
    values = {round(_cbf(p).std_population, 12) for p in itertools.permutations([0, 1, 2, 5.5])}
    assert len(values) == 1


def test_small_samples():
    c = _cbf([0.4])
    assert c.std_population == 0.0 and c.std_sample is None
    assert CBFRegistry().get("z", "c") is None


def test_fed_with_observed_ta_and_not_used_for_spd():
    res = run_simulation(main_config(days=2), write=False)
    assert sum(r["sample_count"] for r in res.cbf) == res.summary["events"]["ta_valid_consistent"]
    assert all(r["source"] == "observed_ta_intensity" for r in res.cbf)
    # audit-only: SPD records carry no CBF field
    assert all("cbf" not in rec and "CBF" not in rec["factors"] for rec in res.records)
