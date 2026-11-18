"""Red-team models of the v3 remediation proposals: pinned outcomes (synthetic rule logic, not evidence)."""
import pytest

from dkp8 import redteam as R

RUNS = {r["id"]: r for r in R.run_all()}


def test_every_scenario_is_labelled_and_mapped():
    assert len(RUNS) >= 40
    for r in RUNS.values():
        assert r["label"] == R.LABEL and r["package"] in {"T1", "T2", "T3", "T4", "T5", "T6", "T7"}
        assert r["cases"] and r["outcome"]


def test_collective_mechanisms_hit_uninvolved_subjects():
    assert RUNS["T1-KS-current"]["result"]["uninvolved_affected"] == 999_880
    assert RUNS["T1-DMS-current"]["result"]["fires"] and RUNS["T1-DMS-current"]["result"]["insider_gain"]
    assert not RUNS["T1-DMS-removed"]["result"]["fires"]


def test_tenfold_multiplier_is_not_proportional_even_on_own_collateral():
    assert not RUNS["T1-10x-on-collateral"]["result"]["proportional"]
    assert RUNS["T1-collateral-bounded"]["result"]["proportional"]
    assert RUNS["T1-collateral-insufficient"]["result"]["taken_beyond_collateral"] == 0


def test_global_trigger_on_unvalidated_index_is_exploitable():
    attack = RUNS["T1-Bt-trigger-current"]["result"]
    assert attack["true_state_above_min"] and attack["kill_switches_fired"] and attack["regions_disconnected"] == 190
    assert not RUNS["T1-Bt-diagnostic"]["result"]["kill_switches_fired"]


@pytest.mark.parametrize("prefix,blocked", [("T1-authority-A.1a six-nod", True), ("T1-authority-A.4 Council ", True),
                                            ("T1-authority-ORACLE 14 Me", False), ("T1-authority-proposal: en", False),
                                            ("T1-authority-external eme", False)])
def test_fallback_authority(prefix, blocked):
    assert RUNS[prefix]["result"]["violates_no_fallback_authority"] is blocked


def test_manifest_properties_are_separate():
    assert RUNS["T2-valid"]["result"]["state"] == "VALID" and "FOUNDING_ASSUMPTION" in RUNS["T2-valid"]["result"]["legitimacy"]
    assert RUNS["T2-forged"]["result"]["state"] == "UNAUTHORIZED"
    assert RUNS["T2-competing-histories"]["result"]["state"] == "NON_ENFORCEABLE"
    assert RUNS["T2-rollback"]["result"]["state"] == "NON_ENFORCEABLE"
    assert RUNS["T2-signer-capture"]["result"]["state"] == "VALID"          # capture is invisible internally
    assert RUNS["T2-signer-capture"]["blast_radius"]["detectable_internally"] is False


def test_tampering_and_broken_links_are_detected():
    seeds = {f"g{i}": bytes([i + 1]) * 32 for i in range(3)}
    g = R.genesis(seeds, 2, {"X": "a" * 64})
    t = R.transition(g, {"X": "b" * 64}, {"g0": seeds["g0"], "g1": seeds["g1"]})
    t["body"]["protocols"]["X"] = "c" * 64                                   # changed after signing
    assert R.verify_chain([g, t])["state"] == "UNAUTHORIZED"
    t2 = R.transition(g, {"X": "b" * 64}, {"g0": seeds["g0"], "g1": seeds["g1"]})
    t2["body"]["prev"] = "0" * 64
    assert R.verify_chain([g, t2])["state"] == "INVALID"


def test_attribution_and_resource_limits():
    ev = RUNS["T3-distributed-evasion"]["result"]
    assert ev["state"] == "NO_ATTRIBUTION" and ev["impact_recorded"] == 2 and not ev["liability_imposed_on_unidentified"]
    assert RUNS["T3-resource-cap"]["result"]["verdict"] == "NEEDS_AUTHOR_DECISION"
    assert RUNS["T3-cap-as-sanction"]["result"]["verdict"] == "BLOCKED"


def test_electorate_attacks():
    assert RUNS["T4-deactivation-no-snapshot"]["result"]["passes"]
    assert not RUNS["T4-deactivation-snapshot"]["result"]["passes"]
    assert RUNS["T4-sybil-no-owner-graph"]["result"]["passes"]
    assert not RUNS["T4-sybil-owner-graph"]["result"]["passes"]
    assert not RUNS["T4-blocking-minority"]["result"]["passes"]
    assert RUNS["T4-fork-compulsory"]["result"]["verdict"] == "BLOCKED"
    assert RUNS["T4-fork-ownership-stays"]["result"]["non_consenting_assets_transferred"] == 0


def test_failure_domains_and_states():
    assert RUNS["T5-common-firmware"]["result"]["n_eff"] == 1
    assert RUNS["T5-independent"]["result"]["n_eff"] == 3
    assert RUNS["T5-unknown-provenance"]["result"]["n_eff"] == 2
    assert R.n_eff({"a": set(), "b": set()}, unknown={"a", "b"})["n_eff"] == 1
    assert RUNS["T5-state-no-threshold"]["result"]["state"] == "NULL_OUTPUT"
    assert RUNS["T5-local-degradation"]["result"] == {"state": "DIVERGENCE_FREEZE", "frozen_domains": ["air"]}
    assert RUNS["T5-hidden-systemic"]["result"]["state"] == "NULL_OUTPUT"
    assert not RUNS["T5-manual-restore"]["result"]["restored"]
    c11 = RUNS["T5-C11-roles"]["result"]
    assert c11["detected"] and not c11["wealth_gates_detection"] and c11["wealth_gates_dispute"]


def test_models_reserve_and_recovery():
    assert RUNS["T6-shared-assumptions"]["result"]["state"] == "INFORMATIONAL_ONLY"
    assert RUNS["T6-disagreement"]["result"]["state"] == "UNATTRIBUTABLE"
    assert RUNS["T6-recovery"]["result"]["auto_promoted"] == 1
    assert RUNS["T6-recovery-proposal"]["result"]["auto_promoted"] == 0
    lawfare = RUNS["T6-reserve-lawfare"]["result"]
    assert lawfare["refused_without_reversal"] == 90 and lawfare["exhausted"] and lawfare["funding_rule"] == R.UNKNOWN


def test_economic_boundaries_and_time_operands():
    ubr = RUNS["T7-ubr"]["result"]
    assert ubr["life"]["granted"] and not ubr["life"]["depends_on_score"] and not ubr["extra"]["granted"]
    assert not RUNS["T7-coordination"]["result"]["sanction_admissible"]
    ops = RUNS["T7-dti-operand"]["result"]
    assert ops["DTI:0"] == {"kind": "DTI", "epoch": True}
    assert ops["DTI:1"]["dy"] == 1 and ops["DTI:1"]["doy"] == 1 and ops["DTI:361"]["dy"] == 2 and ops["DTI:361"]["doy"] == 1
    assert "error" in ops["UNTYPED:5"]
