"""Regressions for the review of 2.1.0 (GPT 9): V21-N1 overlay conflicts, V21-N2 event identity."""

import copy
import itertools

import pytest

from simulation.compare_candidates import compare, find_conflicts, overlay_digest
from simulation.core.config import ConfigError, overlay_assignments, validate_config
from simulation.core.events import ThreatEvent
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import main_config

ALL4 = ["optical", "thermal", "lidar", "access"]
NO_BIAS = {"attack": {"oracle_bias": None}}
BIAS = {"attack": {"oracle_bias": {"classes": ALL4, "bias": 0.1, "phase": "ta"}}}


def _conflicts(*overlays):
    return find_conflicts({overlay_digest(o): o for o in overlays})


# ── V21-N1 ──────────────────────────────────────────────────────────────

def test_null_block_against_filled_block_is_a_conflict():
    found = _conflicts(NO_BIAS, BIAS)
    assert found and {c["kind"] for c in found} == {"block_vs_field"}
    assert all(["attack", "oracle_bias"] in c["paths"].values() for c in found)


def test_conflicting_pair_is_not_evaluated_on_the_real_engine():
    rep = compare(main_config(days=1), {"no_bias": NO_BIAS, "bias": BIAS}, [42])
    (pair,) = rep["pairwise_joint"]
    assert pair["evaluated"] is False and pair["conflicts"]


def test_equal_values_are_not_a_conflict():
    assert _conflicts(BIAS, copy.deepcopy(BIAS)) == [] or overlay_digest(BIAS) == overlay_digest(copy.deepcopy(BIAS))
    same_leaf = {"attack": {"oracle_bias": {"classes": ALL4, "bias": 0.1, "phase": "ta"}},
                 "protocol": {"epsilon_consistency": 0.2}}
    assert _conflicts(BIAS, same_leaf) == []


def test_compatible_edits_of_one_block_are_not_a_conflict():
    a = {"protocol": {"recurrence": {"decay": 0.8}}}
    b = {"protocol": {"recurrence": {"window_seconds": 86400}}}
    assert _conflicts(a, b) == []
    rep = compare(main_config(days=1), {"a": a, "b": b}, [1])
    (pair,) = rep["pairwise_joint"]
    assert pair["evaluated"]
    assert pair["config"]["protocol"]["recurrence"]["decay"] == 0.8
    assert pair["config"]["protocol"]["recurrence"]["window_seconds"] == 86400


def test_conflict_decision_ignores_names_and_order():
    overlays = [NO_BIAS, BIAS, {"protocol": {"epsilon_consistency": 0.2}}]
    ref = None
    for perm in itertools.permutations(overlays):
        names = {f"n{i}{len(perm) - i}": o for i, o in enumerate(perm)}
        rep = compare({"params": {}, "simulation": {"seed": 0}}, names, [1],
                      run_fn=lambda cfg: None, metrics={}, invariants={})
        decision = sorted((tuple(p["members"]), p["evaluated"]) for p in rep["pairwise_joint"])
        assert ref is None or decision == ref
        ref = decision


def test_assignments_use_tuple_paths():
    a = overlay_assignments({"domain": {"channels": {"a.b": {"weight": 1.0}}}})
    assert a == {("domain", "channels", "a.b", "weight"): 1.0}


# ── V21-N2 ──────────────────────────────────────────────────────────────

def _farm_config(channels):
    cfg = main_config(days=1)
    cfg["domain"]["include_adversarial"] = True
    cfg["domain"]["actor_order"] = ["farmer"]
    cfg["domain"]["actors"] = {"farmer": {
        "strategy": "adversarial", "effectiveness": 0.75, "effectiveness_range": None,
        "response_rate": 1.0, "response_delay_seconds": [2.0, 2.0], "attribution_claim": 1.0,
        "self_induce_rate": 1.0}}
    cfg["domain"]["channels"] = {
        channels[0]: {"weight": 1.0, "activation_rate": 0.0, "intensity_range": [0.4, 0.4]},
        channels[1]: {"weight": 2.0, "activation_rate": 1.0, "intensity_range": [0.8, 0.8]}}
    cfg["oracles"].update(noise_sigma=0.0, dropout_rate=0.0, bias_range=[0.0, 0.0],
                          measurement_delay_seconds=[0.0, 0.0], arrival_delay_seconds=[0.0, 0.0],
                          ttl_seconds={c: 60.0 for c in ALL4})
    cfg["oracles"]["linkage_detection"].update(detection_probability=0.0, undetected_score_range=[0.0, 0.0])
    cfg["protocol"]["recurrence"]["decay"] = 1.0
    return cfg


def test_gpt_colliding_names_are_rejected():
    with pytest.raises(ConfigError, match="risk:induced:farmer"):
        validate_config(_farm_config(["risk", "risk:induced:farmer"]))


@pytest.mark.parametrize("where,name", [("channel", "a:b"), ("channel", "a/b"), ("channel", "a.b"),
                                        ("channel", ""), ("actor", "x:y"), ("actor", "x/y"),
                                        ("class", "opt:ical")])
def test_separators_in_names_are_rejected(where, name):
    cfg = main_config(days=1)
    if where == "channel":
        cfg["domain"]["channels"][name] = cfg["domain"]["channels"].pop("intrusion")
    elif where == "actor":
        cfg["domain"]["actors"][name] = cfg["domain"]["actors"].pop("weak_worker")
        cfg["domain"]["actor_order"] = [name if a == "weak_worker" else a for a in cfg["domain"]["actor_order"]]
    else:
        cfg["oracles"]["classes"] = [name if c == "optical" else c for c in cfg["oracles"]["classes"]]
        cfg["oracles"]["ttl_seconds"][name] = cfg["oracles"]["ttl_seconds"].pop("optical")
    with pytest.raises(ConfigError):
        validate_config(cfg)


def test_valid_names_keep_threats_apart():
    """GPT's world with legal names: 72 threats, 72 ids, truth intact, Σ A ≤ 1 per threat."""
    res = run_simulation(_farm_config(["risk", "risk_induced_farmer"]), write=False)
    ids = [r["event_id"] for r in res.records]
    assert res.summary["events"]["threats_total"] == 72 == len(ids) == len(set(ids))
    risk = [r for r in res.records if r["risk_channel"] == "risk"]
    assert risk and all(r["truth"]["own_threat"] and r["truth"]["true_intensity"] == 0.4 for r in risk)
    assert res.summary["evaluation"]["max_sum_A_per_event"] <= 1.0


def test_duplicate_event_id_is_refused(monkeypatch):
    import simulation.run_prevention_simulation as runner

    class Twin(runner.EventEngine):
        def natural(self, *a, **k):
            ev = super().natural(*a, **k)
            return None if ev is None else ThreatEvent("same-id", ev.zone_id, ev.risk_channel, ev.tick,
                                                       ev.event_time, ev.true_intensity, None)
    monkeypatch.setattr(runner, "EventEngine", Twin)
    with pytest.raises(RuntimeError, match="duplicate event id"):
        run_simulation(main_config(days=1), write=False)
