"""Phase 3 scenarios: each checks what its name claims (A1, A2, A4, N5, N6)."""

import pytest

from simulation.modules.prevention.adversarial_scenarios import (
    SIMULATED, attribution_rules, early_prevention, oracle_degradation, risk_farming, ta_inflation,
)
from simulation.phase3_report import linkage_sweep, run_metrics, se_ta_sweep
from simulation.run_prevention_simulation import run_simulation

DAYS = 3


def _run(cfg):
    res = run_simulation(cfg, write=False)
    return run_metrics(res.records, res.summary)


def test_all_scenarios_are_valid_configs():
    for factory in SIMULATED.values():
        for cfg in factory(num_days=1).values():
            run_simulation(cfg, write=False)


def test_s2_independent_ta_bias_raises_reward_but_partial_bias_is_caught():
    """A2: scaling TA and SE together is not the only case; a TA-only bias on all classes
    raises S, a TA-only bias on two classes mostly ends in oracle inconsistency."""
    v = ta_inflation(num_days=DAYS)
    base, all_cls, two_cls = (_run(v[k]) for k in ("baseline", "b_ta_bias_all_classes", "b_ta_bias_2_classes"))
    assert all_cls["mean_S_evaluated"] > base["mean_S_evaluated"]
    assert two_cls["events"]["ta_informational"] > base["events"]["ta_informational"]


def test_s1_farmer_reward_depends_on_linkage_detection():
    v = risk_farming(num_days=DAYS)
    blind, seen = _run(v["detect_0.0"]), _run(v["detect_1.0"])
    assert blind["events"]["threats_induced"] > 0
    assert seen["evaluation"]["self_induced_spd_to_creator"] == 0.0
    assert blind["evaluation"]["self_induced_records_by_creator"] > 0


def test_s5_only_list_order_depends_on_actor_order():
    v = attribution_rules(num_days=DAYS)
    for rule in ("ambiguity_zero", "proportional"):
        assert _run(v[rule])["total_spd"] == pytest.approx(_run(v[f"{rule}_reversed"])["total_spd"], rel=1e-12)
    assert _run(v["list_order"])["subject_totals"] != _run(v["list_order_reversed"])["subject_totals"]


def test_s6_registration_basis_creates_more_temporal_failures():
    """A4 / GPT case 2: taking t₀ from record arrival instead of measurement adds failures."""
    v = early_prevention(num_days=DAYS)
    meas, reg = _run(v["basis_measurement"]), _run(v["basis_registration"])
    assert reg["by_reason"].get("temporal_window", 0) > meas["by_reason"].get("temporal_window", 0)
    assert meas["interventions_before_t0"] > 0


def test_s7_bias_applied_and_slow_arrival_goes_stale():
    v = oracle_degradation(num_days=DAYS)
    clean, bias, slow = _run(v["clean"]), _run(v["bias_only"]), _run(v["slow_arrival_ttl"])
    assert bias["events"]["ta_informational"] > clean["events"]["ta_informational"]
    assert slow["by_reason"].get("ta_stale_data", 0) > 0


def test_s9_linkage_threshold_is_a_real_step():
    sweep = linkage_sweep()
    assert sweep["0.5"] > 0.0 and sweep["0.500001"] == 0.0


def test_s10_suppression_is_continuous_at_se_equals_ta():
    """A1: v1 Phase 2 called SE/TA 0.99 → 1.00 a discontinuity; S goes 0.01 → 0 continuously."""
    s = se_ta_sweep()
    assert s["0.99"] == pytest.approx(0.01)
    assert s["0.999"] == pytest.approx(0.001)
    assert s["0.9999"] == pytest.approx(0.0001)
    assert s["1.0"] == 0.0


def test_s12_unchanged_channels_are_identical():
    """U5: tripling one channel's activation rate leaves the other channels' records unchanged."""
    from simulation.modules.prevention.adversarial_scenarios import ISOLATION_CHANNEL, channel_isolation
    from simulation.phase3_report import isolation_check
    v = channel_isolation(num_days=DAYS)
    a, b = (run_simulation(v[k], write=False) for k in ("baseline", "one_channel_rate_x3"))
    check = isolation_check(a.records, b.records, ISOLATION_CHANNEL)
    assert check["identical"] and check["unchanged_channel_records_a"] > 0


def test_s1_decay_control_changes_only_t():
    """GPT 7 D1: decay 1.0 vs 0.9 on the same world; only Tₖ-dependent outputs move."""
    v = risk_farming(num_days=DAYS)
    base, flat = (run_simulation(v[k], write=False) for k in ("detect_0.0", "detect_0.0_decay_1.0"))
    keys = ("event_id", "actor_id", "truth", "ta", "se", "intervention_time", "claim", "linkage_observed")
    assert [{k: r[k] for k in keys} for r in base.records] == [{k: r[k] for k in keys} for r in flat.records]
    assert flat.summary["evaluation"]["honest_decayed_fraction"] == 0.0
