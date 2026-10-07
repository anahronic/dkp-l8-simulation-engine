"""Findings F-001..F-004 (lab/findings): the minimal reproductions keep giving the documented numbers.

These are regressions of open gaps, not of desired behaviour: if a protocol or a module
changes and a number moves, the finding file must be revisited, not silently updated.
"""

import json
import os

from lab.core.registry import catalog
from lab.core.run import run_request

FINDINGS = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "findings")


def totals(name):
    with open(os.path.join(FINDINGS, f"{name}.request.json"), encoding="utf-8") as f:
        doc = run_request(json.load(f))
    out = {}
    for v, res in doc["variants"].items():
        t = res["outputs"]["totals"]
        out[v] = (t["evaluations"], t["penalty_units"], t["final_mode"], t["steps_suspended"],
                  t["steps_divergence"], t["steps_enforced_against_current_state"], res["summary"]["counts"]["FAIL"])
    return out


def test_f001_was_a_lab_error_now_caught_by_etrans_4_2():
    """F-001 (IMPLEMENTATION_BUG): new admissible data trigger re-evaluation; the former lab reading
    ('declared_events') is now detected as a violation of ETRANS §4.2."""
    assert totals("F-001") == {
        "new_admissible_data": (2, 6, "INACTIVE", 0, 0, 0, 0),
        "declared_events_former_lab_reading": (1, 24, "ACTIVE", 0, 0, 18, 1),
        "material_change_5pct": (2, 6, "INACTIVE", 3, 0, 0, 0),
    }


def test_f002_asynchronous_sampling_reports_a_divergence():
    """F-002 (INTERPRETATION_GAP, depends on H-FC-3): asynchronous sampling freezes transactions; both re-evaluate."""
    assert totals("F-002") == {
        "orbital_every_4h": (2, 6, "INACTIVE", 4, 2, 0, 0),
        "orbital_every_1h": (2, 6, "INACTIVE", 0, 0, 0, 0),
    }


def test_f003_slow_class_keeps_outputs_suspended():
    assert totals("F-003") == {
        "orbital_every_90min": (2, 4, "SUSPENDED", 32, 0, 0, 0),
        "orbital_every_10min": (1, 36, "ACTIVE", 0, 0, 0, 0),
    }


def test_f005_and_f006_impact_and_reversibility():
    with open(os.path.join(FINDINGS, "F-005.request.json"), encoding="utf-8") as f:
        doc = run_request(json.load(f))
    rows = {n: (v["outputs"]["impact"][0]["I"], v["outputs"]["impact"][0]["boundary_crossing"],
                v["outputs"]["impact"][0]["level_reached"]) for n, v in doc["variants"].items()}
    assert rows["example_s13"] == (0.0002, False, False)
    assert rows["level_crossed"][1:] == (False, True)
    with open(os.path.join(FINDINGS, "F-006.request.json"), encoding="utf-8") as f:
        doc = run_request(json.load(f))
    rows = {n: (v["outputs"]["impact"][0]["R"], v["outputs"]["decisions"][0]["domains"]["restitution"],
                v["outputs"]["decisions"][0]["domains"]["isolation"],
                sorted(c["requirement_id"] for c in v["checks"] if c["status"] == "FAIL"))
            for n, v in doc["variants"].items()}
    assert rows == {                                    # (Rᵢ emitted, restitution, isolation, FAIL)
        "reversible_justice_polarity": (True, True, False, []),
        "irreversible_justice_polarity": (False, False, True, []),
        "reversible_impact_name_polarity": (False, True, False, []),
        "irreversible_impact_name_polarity": (True, False, True, []),
        "reversible_mixed": (False, False, True, ["JUSTICE-6-01", "JUSTICE-8-01"]),
        "irreversible_mixed": (True, True, False, ["JUSTICE-6-01", "JUSTICE-8-01"])}


def test_f007_n_eff_undefined():
    with open(os.path.join(FINDINGS, "F-007.request.json"), encoding="utf-8") as f:
        doc = run_request(json.load(f))
    nulls = {n: v["outputs"]["null_output_steps"] for n, v in doc["variants"].items()}
    trig = {n: next(c["status"] for c in v["checks"] if c["requirement_id"] == "CRISISPATCH-2-01")
            for n, v in doc["variants"].items()}
    assert nulls == {"n_eff_min_missing": 0, "owners_45": 12, "sources_45_sybil": 0, "owners_45_sybil": 12}
    assert trig["n_eff_min_missing"] == "UNKNOWN"


def test_f008_quotes_still_contradict():
    """The pinned texts still say both things (F-008)."""
    from lab.tools.check_registry import normalize
    base = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "corpus", "world-aad3e86", "Dikenocracy", "Protocols")
    crisis = normalize(open(os.path.join(base, "L4_FailSafe", "DKP-4-CRISIS-001.md"), encoding="utf-8").read())
    oracle = normalize(open(os.path.join(base, "L0_Physical_Truth", "DKP-0-ORACLE-001.md"), encoding="utf-8").read())
    assert "allowing limited extension of oracle data TTLs" in crisis
    assert "DOES NOT modify TTL values" in oracle and "modify TTL values," in oracle


def test_f010_sustained_d3_gap():
    with open(os.path.join(FINDINGS, "F-010.request.json"), encoding="utf-8") as f:
        doc = run_request(json.load(f))
    got = {n: (v["outputs"]["defense_escalation_hour"], v["outputs"]["crisis_entry_hour"]) for n, v in doc["variants"].items()}
    assert got == {"sustained_6h": (10, 15), "sustained_24h": (10, 33), "immediate": (10, 10)}


def test_f011_f012_exit_conflicts():
    def run(name):
        with open(os.path.join(FINDINGS, f"{name}.request.json"), encoding="utf-8") as f:
            return run_request(json.load(f))["variants"]
    v = run("F-011")
    assert {n: (x["outputs"]["exit_executed_day"], next(c["status"] for c in x["checks"] if c["requirement_id"] == "SCOPE-9-02"))
            for n, x in v.items()} == {"cooling_14": (284, "FAIL"), "cooling_0": (270, "PASS")}
    v = run("F-012")
    assert {n: (x["outputs"]["exit_executed_day"], next(c["status"] for c in x["checks"] if c["requirement_id"] == "EXIT-4-03"))
            for n, x in v.items()} == {"never_suspended": (284, "PASS"), "scope_crisis_suspension": (302, "FAIL")}


def test_f013_was_a_lab_premise_now_a_counterexample():
    with open(os.path.join(FINDINGS, "F-013.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    rows = {n: (x["outputs"]["internal_decisions"], x["outputs"]["crisis_entered"],
                {c["requirement_id"]: c["status"] for c in x["checks"]}["CRISIS-4-01"],
                sorted(c["requirement_id"] for c in x["checks"] if c["status"] == "FAIL")) for n, x in v.items()}
    assert rows == {"external_mirror_outage": (24, False, "NOT_APPLICABLE", []),
                    "former_lab_premise": (16, True, "NOT_APPLICABLE",
                                           ["INTEROP-8-01", "INTEROP-8-02", "INTEROP-9-02", "INTEROP-9-04"]),
                    "registered_sources_lost": (16, True, "PASS", []),
                    "registered_tolerance_missing": (24, False, "UNKNOWN", [])}


def test_f014_bundle_precondition_text():
    from lab.tools.check_registry import normalize
    base = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "corpus", "world-aad3e86", "Dikenocracy", "Protocols")
    sim = normalize(open(os.path.join(base, "L8_Infrastructure", "DKP-8-SIMULATION-001.md"), encoding="utf-8").read())
    assert "Protocols lacking an attached and valid L8 Calibration Bundle are NON-ENFORCEABLE by definition." in sim
    corpus = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "corpus")
    names = [f for _, _, fs in os.walk(corpus) for f in fs]
    assert not any("calibration" in f.lower() and "bundle" in f.lower() for f in names)     # no bundle in the corpus


def test_f015_insurance_exposure_and_red_aggregation():
    with open(os.path.join(FINDINGS, "F-015.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    st = {n: tuple(next(c["status"] for c in x["checks"] if c["requirement_id"] == rid) for rid in ("ORACLE-1-02", "IMPACT-10-02"))
          for n, x in v.items()}
    assert st == {"single_delta_as_written": ("FAIL", "UNKNOWN"), "channel_separated": ("FAIL", "PASS"),
                  "insurance_outside_ptl": ("PASS", "UNKNOWN"), "channel_separated_insurance_outside_ptl": ("PASS", "PASS")}


def test_f016_consent_not_measurable_by_ptl():
    from lab.tools.check_registry import normalize
    base = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "corpus", "world-aad3e86", "Dikenocracy", "Protocols")
    tr = normalize(open(os.path.join(base, "L5_Social", "DKP-5-TRANSPORT-001.md"), encoding="utf-8").read())
    oracle = normalize(open(os.path.join(base, "L0_Physical_Truth", "DKP-0-ORACLE-001.md"), encoding="utf-8").read())
    assert "forced bodily contact between non-consenting passengers" in tr
    assert "The PTL SHALL NOT emit outputs concerning:" in oracle and "- consent," in oracle


def test_f004_broken_cross_reference():
    broken = catalog()["section_references"]["broken"]
    assert [(b["from"], b["line"], b["text"]) for b in broken] == [
        ("DKP-2-FINANCE-001", 243, "DKP-4-ERROR-001 Section 4.1"),
        ("DKP-4-CRISIS-001", 280, "Section 8")]                 # F-009: the named rule is under §6


def test_f019_two_dispute_clocks():
    with open(os.path.join(FINDINGS, "F-019.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    rows = {n: (x["outputs"]["dispute_accepted"], x["outputs"]["revocation_execution_day"],
                {c["requirement_id"]: c["status"] for c in x["checks"]}["ASSETS-8.3-01"]) for n, x in v.items()}
    assert rows == {"same_day_execution": (False, 2, "PASS"), "execution_clock": (True, 12, "UNKNOWN"),
                    "recording_clock": (False, 12, "UNKNOWN")}


def test_f020_stabilization_period_undefined():
    with open(os.path.join(FINDINGS, "F-020.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    rows = {n: (x["outputs"]["status"]["justice_change"],
                {c["requirement_id"]: c["status"] for c in x["checks"]}["UPGRADE-Post-CrisisCooldownRule-01"]) for n, x in v.items()}
    assert rows == {"period_undefined": ("held", "UNKNOWN"), "declared_20_days": ("rejected", "PASS"),
                    "declared_0_days": ("active", "PASS")}


def test_f021_reentry_after_expiry():
    with open(os.path.join(FINDINGS, "F-021.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    rows = {n: (x["outputs"]["contained_days"], "FAIL" in {c["status"] for c in x["checks"]}) for n, x in v.items()}
    assert rows == {"evidence_driven": (8, False), "episode_once": (3, False)}


def _chosen_and_open(fid):
    with open(os.path.join(FINDINGS, f"{fid}.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    return {n: (x["outputs"]["chosen"], sorted(c["requirement_id"] for c in x["checks"] if c["status"] == "UNKNOWN"))
            for n, x in v.items()}


def test_f022_to_f025_axioms():
    assert _chosen_and_open("F-022") == {"share_70": ("a", ["AXIOMS-8-02"]), "share_50": ("a", ["AXIOMS-8-02"])}
    assert _chosen_and_open("F-023") == {"claim_refused": ("wait", ["AXIOMS-AxiomA1-PreservationofLife-02"])}
    assert _chosen_and_open("F-024") == {"lexicographic": ("hide", ["AXIOMS-1-01", "AXIOMS-5-02"]),
                                         "no_admissible_action": (None, ["AXIOMS-1-01", "AXIOMS-5-02", "AXIOMS-5-04"])}
    assert _chosen_and_open("F-025") == {"constraint": ("weir", []),
                                         "recommendation": ("dam", ["AXIOMS-AxiomA4-IrreversibilityAversion-01"])}


def test_f026_absolute_aggregates():
    with open(os.path.join(FINDINGS, "F-026.request.json"), encoding="utf-8") as f:
        v = run_request(json.load(f))["variants"]
    rows = {n: (x["outputs"]["decisions"][0]["grant"],
                any(c["requirement_id"] == "PRIVACY-6-01" and c["status"] == "UNKNOWN" for c in x["checks"])) for n, x in v.items()}
    assert rows == {"aggregate_allowed": (True, True), "never": (False, True)}
