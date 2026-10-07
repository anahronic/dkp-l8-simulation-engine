"""Calibration map (F-014 decomposition): verbatim quotes, declared stand-ins, no invented bundle."""

import re

from lab.modules import MODULES
from lab.tools import calibration_map as cm

M = cm.load()


def test_quotes_are_verbatim_and_inputs_exist():
    assert cm.quote_problems(M) == []
    assert cm.input_problems(M) == []


def test_lab_stand_ins_are_declared_as_missing_values():
    """A value the corpus lacks enters a module only as a declared input marked missing (or hypothesis), never as text."""
    for sec in ("deferred_to_l8", "missing_values"):
        for rec in M[sec]:
            for mod, inp in re.findall(r"\b([a-z_]+)\.([a-z_0-9]+)", rec.get("lab_input") or ""):
                if inp == "bundle":
                    continue
                assert MODULES[mod].inputs[inp]["source"] in ("missing", "hypothesis"), (mod, inp)


def test_every_registrable_document_has_a_status():
    rows = cm.protocol_table(M, cm.constants())
    assert len(rows) == 38
    assert {r["category"] for r in rows} <= {"non_enforceable", "undetermined", "not_a_protocol", "calibration_protocol"}
    assert sorted(r["document"] for r in rows if r["category"] == "undetermined") == \
        ["DKP-0-ORACLE-001", "DKP-1-AXIOMS-001", "DKP-7-SCOPE-001"]


def test_known_constants_are_found():
    found = {c["id"]: c["values"] for c in cm.constants()}
    assert "7%" in found["ORACLE-11-01"] and "14 days" in found["ORACLE-11-03"]
    assert any("30" in v for v in found["ERROR-7-02"])
    assert any("30" in v for v in found["UPGRADE-Post-CrisisCooldownRule-02"])


def test_markdown_is_current():
    assert cm.main(["--check"]) == 0
