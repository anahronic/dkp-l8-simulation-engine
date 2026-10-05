"""U1 (order carried no identity) and U5 (shared random streams)."""

import copy
import json

from simulation.core.config import canonical_json, config_digest
from simulation.run_prevention_simulation import main, run_simulation
from tests.simulation.helpers import main_config


def _reverse_mappings(cfg):
    out = copy.deepcopy(cfg)
    for key in ("channels", "actors"):
        out["domain"][key] = dict(reversed(list(cfg["domain"][key].items())))
    out["oracles"]["ttl_seconds"] = dict(reversed(list(cfg["oracles"]["ttl_seconds"].items())))
    return out


def test_mapping_order_changes_nothing():
    for rule in ("ambiguity_zero", "list_order"):
        cfg = main_config({"protocol": {"attribution_rule": rule}}, days=3)
        a, b = run_simulation(cfg, write=False), run_simulation(_reverse_mappings(cfg), write=False)
        assert a.manifest["input_id"] == b.manifest["input_id"]
        assert a.manifest["result_id"] == b.manifest["result_id"]


def test_canonical_json_round_trip_reproduces_the_run():
    """GPT 7: v2.0 gave 7034 → 7059 records with the same input_id after this round trip."""
    cfg = main_config(days=3, zones=2)
    rt = json.loads(canonical_json(cfg))
    a, b = run_simulation(cfg, write=False), run_simulation(rt, write=False)
    assert (a.manifest["input_id"], a.manifest["result_id"]) == (b.manifest["input_id"], b.manifest["result_id"])


def test_replay_from_exported_config_file(tmp_path):
    cfg = main_config(days=2, out=str(tmp_path / "first"))
    first = run_simulation(cfg, write=True)
    resolved = tmp_path / "first" / "config_resolved.json"
    assert main(["--config", str(resolved), "--output-dir", str(tmp_path / "replay")]) == 0
    replay = json.loads((tmp_path / "replay" / "run_manifest.json").read_text())
    assert replay["input_id"] == first.manifest["input_id"]
    assert replay["result_id"] == first.manifest["result_id"]


def test_actor_order_is_identity_and_matters_only_for_list_order():
    for rule, same_result in (("ambiguity_zero", True), ("proportional", True), ("list_order", False)):
        cfg = main_config({"protocol": {"attribution_rule": rule}}, days=3)
        rev = copy.deepcopy(cfg)
        rev["domain"]["actor_order"] = list(reversed(cfg["domain"]["actor_order"]))
        assert config_digest(cfg) != config_digest(rev)
        a, b = run_simulation(cfg, write=False), run_simulation(rev, write=False)
        assert a.manifest["input_id"] != b.manifest["input_id"]
        assert (a.manifest["result_id"] == b.manifest["result_id"]) is same_result


def _by_key(records, exclude_channel):
    return {(r["event_id"], r["actor_id"]): r for r in records if r["risk_channel"] != exclude_channel}


def test_changing_one_channel_leaves_other_channels_identical():
    """U5: threats, subjects' actions, sensor draws and outcomes on unchanged channels."""
    ch = "unauthorized_adult_proximity"
    base = run_simulation(main_config(days=5), write=False)
    changed = run_simulation(main_config({"domain": {"channels": {ch: {"activation_rate": 0.75,
                                                                       "intensity_range": [0.5, 0.9]}}}},
                                         days=5), write=False)
    a, b = _by_key(base.records, ch), _by_key(changed.records, ch)
    assert a and a == b


def test_changing_one_actor_leaves_other_actors_draws_identical():
    base = run_simulation(main_config(days=3), write=False)
    changed = run_simulation(main_config({"domain": {"actors": {"weak_worker": {"response_rate": 0.1,
                                                                                "response_delay_seconds": [1, 5]}}}},
                                         days=3), write=False)

    def acts(res):
        return {(r["event_id"], r["actor_id"]): (r["intervention_time"], r["truth"]["effectiveness"],
                                                 r["linkage_observed"])
                for r in res.records if not r["actor_id"].endswith("/weak_worker")}
    a, b = acts(base), acts(changed)
    assert a and a == b
    # TA readings of an event are drawn per sensor, event and phase: unchanged unless an
    # intervention happened before the sample (physics, declared in H-SUP)
    ta_a = {r["event_id"]: r["ta"]["evaluated_at"] for r in base.records}
    ta_b = {r["event_id"]: r["ta"]["evaluated_at"] for r in changed.records}
    common = set(ta_a) & set(ta_b)
    assert common and all(ta_a[e] == ta_b[e] for e in common)
