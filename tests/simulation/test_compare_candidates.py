"""Candidate bench (B1–B4): identity, order, copies, additivity of rows, joint activation."""

import json
from types import SimpleNamespace

import pytest

from simulation.compare_candidates import compare, find_conflicts
from tests.simulation.helpers import main_config

# ── toy world: r = a·b, invariant r ≤ 1 (review item B4) ──────────────────

TOY_BASE = {"params": {"a": 1.0, "b": 0.5, "c": 0.0}}
TOY_METRICS = {
    "r": (lambda res: res.r, "lower", "toy product"),
    "c": (lambda res: res.c, "none", "toy unrelated parameter"),
}
TOY_INVARIANTS = {"r_le_1": lambda res: res.r <= 1.0}


def toy_run(cfg):
    p = cfg["params"]
    seed = cfg["simulation"]["seed"]
    return SimpleNamespace(r=p["a"] * p["b"] + 0.0 * seed, c=p["c"])


def toy(candidates, seeds=(1, 2)):
    base = dict(TOY_BASE, simulation={"seed": 0})
    return compare(base, candidates, list(seeds), run_fn=toy_run, metrics=TOY_METRICS,
                   invariants=TOY_INVARIANTS)


K1 = {"params": {"a": 2.0}}            # r = 1.0 alone
K2 = {"params": {"b": 1.0}}            # r = 1.0 alone
K3 = {"params": {"c": 5.0}}


def test_joint_violation_detected_when_each_alone_passes():
    rep = toy({"K1": K1, "K2": K2})
    assert all(row["invariants_hold"]["r_le_1"] for row in rep["candidates"].values())
    (pair,) = rep["pairwise_joint"]
    assert pair["evaluated"] and pair["joint_breaks_invariant"] == ["r_le_1"]
    assert pair["mean"]["r"] == 2.0
    assert pair["interaction"]["r"] == pytest.approx(2.0 - 0.5 - (0.5 + 0.5))


def test_report_does_not_depend_on_candidate_order():
    a = toy({"K1": K1, "K2": K2, "K3": K3})
    b = toy({"K3": K3, "K2": K2, "K1": K1})
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_copies_are_reported_once():
    rep = toy({"K1": K1, "K1_copy": {"params": {"a": 2.0}}, "K2": K2})
    assert len(rep["candidates"]) == 2
    row = next(r for r in rep["candidates"].values() if "K1" in r["names"])
    assert row["names"] == ["K1", "K1_copy"] and row["copies"] == ["K1_copy"]


def test_adding_a_candidate_does_not_change_other_rows():
    small = toy({"K1": K1})
    big = toy({"K1": K1, "K2": K2, "K3": K3})
    for d, row in small["candidates"].items():
        assert big["candidates"][d] == row
    assert small["baseline"] == big["baseline"]


def test_baseline_present_and_nothing_selected():
    rep = toy({"K1": K1})
    assert rep["baseline"]["mean"]["r"] == 0.5
    assert rep["selection"] is None
    assert "not normative" in rep["directions_status"]


def test_conflicting_overlays_are_not_merged():
    rep = toy({"K1": K1, "K1b": {"params": {"a": 3.0}}})
    (pair,) = rep["pairwise_joint"]
    assert not pair["evaluated"]
    assert pair["conflicts"][0]["path"] == "params.a"
    assert find_conflicts({"x": K1, "y": K2}) == []


def test_real_engine_integration():
    base = main_config(days=1)
    rep = compare(base, {"proportional": {"protocol": {"attribution_rule": "proportional"}},
                         "window_1d": {"protocol": {"recurrence": {"key": ["actor", "zone", "channel"],
                                                                   "window_seconds": 86400}}}}, [1])
    assert len(rep["candidates"]) == 2
    assert all(all(row["invariants_hold"].values()) for row in rep["candidates"].values())
    (pair,) = rep["pairwise_joint"]
    assert pair["evaluated"] and all(pair["invariants_hold"].values())
