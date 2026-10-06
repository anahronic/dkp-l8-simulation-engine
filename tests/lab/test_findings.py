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


def test_f001_synchronous_change_triggers_no_reevaluation():
    assert totals("F-001") == {
        "declared_events": (1, 24, "ACTIVE", 0, 0, 18, 0),
        "every_step": (2, 6, "INACTIVE", 0, 0, 0, 0),
        "material_change_5pct": (2, 6, "INACTIVE", 3, 0, 0, 0),
    }


def test_f002_asynchronous_sampling_reports_a_divergence():
    assert totals("F-002") == {
        "orbital_every_4h": (2, 6, "INACTIVE", 4, 2, 0, 0),
        "orbital_every_1h": (1, 24, "ACTIVE", 0, 0, 18, 0),
    }


def test_f003_slow_class_keeps_outputs_suspended():
    assert totals("F-003") == {
        "orbital_every_90min": (2, 4, "SUSPENDED", 32, 0, 0, 0),
        "orbital_every_10min": (1, 36, "ACTIVE", 0, 0, 0, 0),
    }


def test_f004_broken_cross_reference():
    broken = catalog()["section_references"]["broken"]
    assert [(b["from"], b["line"], b["text"]) for b in broken] == [
        ("DKP-2-FINANCE-001", 243, "DKP-4-ERROR-001 Section 4.1")]
