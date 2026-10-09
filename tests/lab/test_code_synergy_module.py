"""CODE SYNERGY module: Appendix A, Peace Staking and Kill Switches as written; open states stay UNKNOWN."""

import pytest

from lab.core.schema import LabInputError
from lab.modules.code_synergy import FAULTS, CodeSynergyModule

M = CodeSynergyModule()
EX = M.examples()


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule_except_the_documented_conflict(name):
    """The only reference FAIL is ORACLE-12-06, the rule conflict of F-036 (Kill Switches on B(t) without a bundle)."""
    res = run(**EX[name])
    fails = [c for c in res.checks if c.status == "FAIL"]
    assert all(c.requirement_id == "ORACLE-12-06" and "F-036" in c.explanation for c in fails), [c.requirement_id for c in fails]


def test_noncompliant_cases_fail_only_the_broken_provision():
    def fails(n):
        return [k for k, s in statuses(run(**EX[n])).items() if s == "FAIL" and k != "ORACLE-12-06"]
    assert fails("human_testimony_as_ptl") == ["ORACLE-3-01"]
    assert fails("declared_discretionary_council") == ["SCOPE-3-19"]
    assert fails("equation_violated_181_days") == ["CODEX-A.1-01"]
    assert fails("equation_violated_180_days") == ["CODEX-A.1-01"]
    assert fails("indirect_ownership_breach") == ["CODEX-A.6-01"]


FAULT_CASES = {
    "ignore_b_min": ({}, ["CODEX-A.1-04"]),
    "altered_genesis_header": ({}, ["CODEX-GenesisBlock_0_TechnicalSpecification_-01"]),
    "edit_genesis_message": ({"genesis_change_requests": ["immutable_message", "physical_anchors"]},
                             ["CODEX-GenesisBlock_0_TechnicalSpecification_-03", "CODEX-GenesisBlock_0_TechnicalSpecification_-04"]),
    "kill_switch_during_mercy": ({}, ["CODEX-A.4-01", "CODEX-A.1-04"]),
    "accept_on_chain_tuning": (EX["tuning_attempts"], ["CODEX-A.1a-01", "CODEX-A.1-03"]),
    "accept_protocol_tuning": (EX["tuning_attempts"], ["CODEX-A.1a-03"]),
    "accept_unsimulated_upgrade": (EX["tuning_attempts"], ["CODEX-A.1a-02"]),
    "early_system_failure": (EX["equation_violated_180_days"], ["CODEX-A.1a-04"]),
    "accept_external_feed": ({}, ["CODEX-A.2-01"]),
    "accept_late_hash": ({}, ["CODEX-A.2-08"]),
    "no_arbitration": (EX["resolved_divergence"], ["CODEX-A.2-12"]),
    "count_unconfirmed_nodes": (EX["unconfirmed_spare_node"], ["CODEX-A.3-04"]),
    "dead_man_partial": (EX["node_seized"], ["CODEX-A.3-05"]),
    "ineligible_member": ({}, ["CODEX-A.4-02"]),
    "execute_inadmissible": ({}, ["CODEX-A.4-06", "CODEX-A.4-08", "CODEX-A.4-03"]),
    "connect_without_referendum": (EX["connection_by_legislative_act"], ["CODEX-A.5-03"]),
    "miss_indirect_ownership": (EX["indirect_ownership_breach"], ["CODEX-A.6-02"]),
    "lenient_cap_violation": (EX["indirect_ownership_breach"], ["CODEX-A.6-02"]),
    "smooth_during_snap": ({}, ["CODEX-1.4-01"]),
    "flat_stake": ({}, ["CODEX-7.1-01"]),
    "dividends_to_aggressor": ({}, ["CODEX-7.2-01"]),
    "no_slashing": ({}, ["CODEX-7.3-01"]),
    "no_disconnect": ({}, ["CODEX-8.1-01"]),
    "write_off_damage_only": ({}, ["CODEX-8.2-01"]),
    "kill_switch_in_phase_1": (EX["phase_1_aggressor"], ["INTEGRATION-5.2-01"]),
    "audit_gap_in_mercy": ({}, ["AUDIT-11-01", "AUDIT-11-02"]),
}


def test_every_fault_has_a_case():
    assert set(FAULT_CASES) == set(FAULTS)


@pytest.mark.parametrize("fault", sorted(FAULT_CASES))
def test_fault_is_detected(fault):
    base, expected = FAULT_CASES[fault]
    clean, broken = statuses(run(**base)), statuses(run(**base, faults=[fault]))
    for rid in expected:
        # CODEX-A.1-04 is UNKNOWN when the activation is right (its targets are undefined, F-029); a fault makes it FAIL
        assert clean[rid] == ("UNKNOWN" if rid == "CODEX-A.1-04" else "PASS"), (rid, clean[rid])
        assert broken[rid] == "FAIL", (fault, rid, broken[rid])


def test_kill_switches_wait_for_mercy_then_activate():
    ks = run().outputs["kill_switches"]
    glob = [(k["day"], k["all_kill_switches"]) for k in ks if "all_kill_switches" in k]
    assert glob == [(120, "suspended"), (300, "active")]
    east = [(k["day"], k["disconnected"]) for k in ks if k.get("region") == "east"]
    assert east == [(60, True), (120, False), (300, True)]


def test_strict_thresholds():
    """'B(t) < B_min', '> VEI-6', '> 10% per month', '> 7%' are strict; 67% and the caps are inclusive."""
    flat = {"from_day": 0, "l0": 0.68, "l1": 0.68, "l2": 0.68, "cause": "natural"}
    assert statuses(run(ptl_segments=[flat], mercy_events=[]))["CODEX-A.1-04"] == "NOT_APPLICABLE"
    m = run(mercy_events=[{"day": 50, "kind": "eruption", "magnitude": 6, "crisis_scope_days": 365}]).outputs["mercy"]
    assert m[0]["mercy"] == "not triggered"
    snap = run(indicator_drops=[{"day": 60, "region": "south", "drop": 0.10, "aggressor": "east"}])
    assert statuses(snap)["CODEX-1.4-01"] == "NOT_APPLICABLE"
    con = run(connections=[{"territory": "t", "day": 200, "mechanism": "referendum", "yes_share": 0.67}]).outputs["network"]
    assert [x for x in con if x.get("territory") == "t"][0]["connected"] is True
    own = run(ownership=[{"holder": "o", "l0_share": 0.007, "geo_share": 0.02}])
    assert statuses(own)["CODEX-A.6-01"] == "PASS"


def test_open_states_stay_unknown():
    """F-018, F-027, F-028, F-029, F-030, F-031, F-032: the lab does not pick a reading."""
    assert statuses(run(**EX["unresolved_divergence"]))["CODEX-A.2-12"] == "UNKNOWN"
    assert statuses(run(**EX["mercy_shorter_crisis_scope"]))["CODEX-A.4-01"] == "UNKNOWN"
    assert statuses(run(**EX["mercy_without_crisis_scope"]))["CODEX-A.4-01"] == "UNKNOWN"
    assert statuses(run())["ORACLE-3-01"] == "UNKNOWN"
    assert statuses(run(**EX["human_weight_zero"]))["ORACLE-3-01"] == "PASS"
    assert statuses(run(**EX["b_recovers"]))["CODEX-A.1-04"] == "UNKNOWN"
    assert statuses(run(**EX["equation_violated_181_days"]))["CODEX-A.1a-04"] == "UNKNOWN"
    s = statuses(run(**EX["phase_1_aggressor"]))
    assert s["CODEX-7.3-01"] == s["CODEX-8.1-01"] == s["CODEX-8.2-01"] == "UNKNOWN"
    assert s["INTEGRATION-5.2-01"] == "PASS"
    assert statuses(run())["SCOPE-3-19"] == "UNKNOWN"
    assert statuses(run(**EX["provenance_validators"]))["ORACLE-3-01"] == "UNKNOWN"


def test_fixed_predicates_give_pass_or_fail_not_unknown():
    """Review КТ4: once the input fixes the predicate, the specific prohibition decides."""
    assert statuses(run(**EX["human_testimony_as_ptl"]))["ORACLE-3-01"] == "FAIL"
    assert statuses(run(**EX["declared_discretionary_council"]))["SCOPE-3-19"] == "FAIL"
    assert statuses(run(**EX["rule_bound_council"]))["SCOPE-3-19"] == "PASS"


def test_f036_scope_of_the_conflict():
    """Strict threshold, absent vs not-valid bundle, valid bundle."""
    at = statuses(run(**EX["at_threshold"]))
    assert at["CODEX-A.1-04"] == "NOT_APPLICABLE" and at["ORACLE-12-06"] == "NOT_APPLICABLE"
    for name in ("natural_drop_with_mercy", "expired_bundle"):
        s = statuses(run(**EX[name]))
        assert s["CODEX-A.1-04"] == "UNKNOWN" and s["ORACLE-12-06"] == "FAIL", name
    s = statuses(run(**EX["bundle_attached"]))
    assert s["CODEX-A.1-04"] == "UNKNOWN" and s["ORACLE-12-06"] == "PASS"


def test_alternative_mercy_reading_breaks_the_scope_bound():
    s = statuses(run(**EX["mercy_fixed_180_reading"]))
    assert s["CODEX-A.4-07"] == "FAIL" and s["CODEX-A.4-01"] == "PASS"


def test_mercy_suspends_kill_switches_not_slashing():
    out = run(**EX["eruption_vei_7"]).outputs
    east = [(k["day"], k["disconnected"]) for k in out["kill_switches"] if k.get("region") == "east"]
    assert east == [(230, True)]
    final = out["network"][-1]["regions"]["east"]
    assert final["stake"] == 0.0


def test_dead_man_switch_redistributes():
    net = run(**EX["node_seized"]).outputs["network"]
    dm = [x for x in net if "dead_man_switch" in x][0]
    assert dm["burned"] == dm["stakes_total"] * 0.5 and "neom" not in dm["distributed_to"] and len(dm["distributed_to"]) == 6


def test_sortition_is_reproducible():
    a = [x for x in run().outputs["mercy"] if "council" in x][0]["council"]
    b = [x for x in run().outputs["mercy"] if "council" in x][0]["council"]
    c = [x for x in run(seed=8).outputs["mercy"] if "council" in x][0]["council"]
    assert a == b and a != c and len(a) == 9


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])
