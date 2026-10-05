"""World model fixes: unique subject ids (N4), bias applied (N6), truth isolation (N3), farming."""

import dataclasses
import inspect

from simulation.modules.prevention.protocol_adapter import ObservedIntervention, PreventionProtocolAdapter
from simulation.run_prevention_simulation import run_simulation
from tests.simulation.helpers import adapter_for, iv, main_config, ta_readings


def test_actor_ids_are_unique_across_zones():
    """v1 used actor-<profile>-<n> with n reset per zone: 9 subjects became 3."""
    res = run_simulation(main_config(days=2, zones=3), write=False)
    ids = {r["actor_id"] for r in res.records}
    assert all(i.split("/")[0] == r_zone for i, r_zone in
               {(r["actor_id"], r["zone_id"]) for r in res.records})
    assert len(ids) == res.summary["subject_count"]
    assert res.summary["subject_count"] == 3 * 3   # patrol, weak, optimizer in each of 3 zones


def test_recurrence_counters_are_per_subject():
    res = run_simulation(main_config(days=2, zones=3), write=False)
    keys = set(res.recurrence)
    zones_in_keys = {k.split("/")[0] for k in keys}
    assert zones_in_keys == {"zone-0001", "zone-0002", "zone-0003"}


def test_bias_range_is_applied():
    a = run_simulation(main_config(days=2), write=False)
    b = run_simulation(main_config({"oracles": {"bias_range": [-0.3, 0.3]}}, days=2), write=False)
    assert a.records != b.records
    assert b.summary["events"]["ta_informational"] > a.summary["events"]["ta_informational"]


def test_attack_bias_only_in_declared_phase():
    base = run_simulation(main_config(days=2), write=False)
    ta_only = run_simulation(main_config({"attack": {"oracle_bias": {
        "classes": ["optical", "thermal", "lidar", "access"], "bias": 0.1, "phase": "ta"}}}, days=2), write=False)
    def by_key(res):
        return {(r["event_id"], r["actor_id"]): r for r in res.records}
    b, t = by_key(base), by_key(ta_only)
    assert b.keys() == t.keys()      # the attack draws no randomness
    shifted = [t[k]["ta"]["intensity"] - b[k]["ta"]["intensity"] for k in b
               if b[k]["ta"]["intensity"] is not None and b[k]["ta"]["intensity"] > 0.2]
    assert shifted and all(abs(d - 0.1) < 1e-9 for d in shifted)
    same_se = [(b[k]["se"]["intensity"], t[k]["se"]["intensity"]) for k in b
               if b[k]["se"] is not None and t[k]["se"] is not None]
    assert same_se and all(x == y for x, y in same_se)   # SE untouched by a TA-phase attack


def test_adapter_interfaces_take_no_truth():
    """N3: the adapter sees observations only."""
    fields = {f.name for f in dataclasses.fields(ObservedIntervention)}
    assert fields == {"actor_id", "order", "time", "claim", "linkage_observed"}
    params = set(inspect.signature(PreventionProtocolAdapter.evaluate_event).parameters)
    assert params == {"self", "event_id", "zone_id", "channel", "ta", "se", "interventions"}


def test_same_observations_same_output_whatever_the_truth():
    """Whether the threat was self-induced is invisible unless the observed linkage shows it."""
    def run():
        a = adapter_for()
        ta = a.assess_ta(ta_readings([0.8] * 4))
        se = a.assess_se(ta_readings([0.2] * 4, t=5.0))
        return a.evaluate_event("e", "zone-0001", "intrusion", ta, se, [iv("adversarial_actor", linkage=0.1)])
    assert run() == run()


def test_farmer_creates_threats_and_detection_matters():
    farm = {"domain": {"include_adversarial": True, "actors": {"adversarial_actor": {"self_induce_rate": 0.2}}}}
    blind = run_simulation(main_config(dict(farm, oracles={"linkage_detection": {"detection_probability": 0.0}}),
                                       days=3), write=False)
    seen = run_simulation(main_config(dict(farm, oracles={"linkage_detection": {"detection_probability": 1.0}}),
                                      days=3), write=False)
    assert blind.summary["events"]["threats_induced"] > 0
    assert seen.summary["evaluation"]["self_induced_spd_to_creator"] == 0.0
    assert blind.summary["evaluation"]["self_induced_records_by_creator"] > 0
    assert seen.summary["by_reason"]["self_induced_linkage"] > 0
