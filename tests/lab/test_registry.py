"""Catalog, corpus pin, requirement registry and declared coverage (TZ §5)."""

import json
import os
import shutil

import pytest

from lab.core.registry import catalog, coverage_table, requirements
from lab.modules import MODULES
from lab.tools import build_catalog
from lab.tools.check_registry import main as check_registry_main
from lab.tools.sync_coverage import declared, main as sync_main


def test_catalog_counts_are_computed():
    c = build_catalog.build()
    assert c["counts"]["protocols"] == 35
    assert c["counts"]["documents"] == 39
    assert c["counts"]["by_kind"] == {"addendum": 1, "appendix": 1, "codex": 1, "glossary": 1, "protocol": 35}
    ids = [d["id"] for d in c["documents"]]
    assert len(ids) == len(set(ids))


def test_catalog_file_is_current():
    with open(build_catalog.CATALOG_JSON, encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk == json.loads(json.dumps(build_catalog.build()))


def test_unresolved_dependencies_are_reported_not_substituted():
    unresolved = {u["raw"]: u["referenced_by"] for u in catalog()["unresolved_dependencies"]}
    assert unresolved == {"DKP-2-ECONOMIC-001": ["DKP-5-TRANSPORT-001"],
                          "DKP-PTL-REG-DATA-001": ["DKP-6-RESILIENCE-001"]}
    assert [a["raw"] for a in catalog()["ambiguous_references"]] == ["DKP-7"]


def test_broken_section_references_are_reported():
    """Every 'DKP-X Section N' / 'Section N of DKP-X' / own-section reference is checked against
    the target's headings, and a title given in parentheses must be that section's heading.
    At World aad3e86 two are broken (findings F-004, F-009)."""
    sr = catalog()["section_references"]
    assert sr["checked"] >= 40
    assert [(r["from"], r["target"], r["section"], r["status"]) for r in sr["broken"]] == [
        ("DKP-2-FINANCE-001", "DKP-4-ERROR-001", "4.1", "SECTION_NOT_FOUND"),
        ("DKP-4-CRISIS-001", "DKP-4-CRISIS-001", "8", "TITLE_MISMATCH")]


def test_corpus_pin_detects_a_changed_file(tmp_path, monkeypatch):
    snap = tmp_path / "snap"
    shutil.copytree(build_catalog.SNAPSHOT_DIR, snap)
    target = next(snap.rglob("DKP-1-PREVENTION-001.md"))
    target.write_bytes(target.read_bytes() + b"\nchanged\n")
    monkeypatch.setattr(build_catalog, "SNAPSHOT_DIR", str(snap))
    with pytest.raises(build_catalog.CorpusError, match="changed"):
        build_catalog.verify()


def test_registry_is_valid():
    assert check_registry_main([]) == 0


def test_coverage_has_no_drift():
    assert sync_main(["--check"]) == 0


def test_every_declared_check_is_emitted_by_examples():
    from lab.core.run import run_request
    emitted = set()
    for m in MODULES.values():
        req = {"schema": "dkp-lab-input/1", "module": m.id,
               "variants": [{"name": n, "input": m.examples()[n]} for n in m.ordered_examples()[:6]]}
        if m.id == "prevention":   # the large examples are exercised in test_prevention_module
            req["variants"] = [v for v in req["variants"] if v["name"] in ("smoke_default", "freshness_at_signal")]
        doc = run_request(req)
        for v in doc["variants"].values():
            emitted |= {c["requirement_id"] for c in v["checks"]}
    missing = set(declared()) - emitted
    assert not missing, f"declared but never emitted: {sorted(missing)}"


def test_coverage_table_lists_every_document():
    rows = coverage_table()
    assert len(rows) == 39
    reg = [r for r in rows if r["registered"]]
    assert all(r["requirements"] == len(requirements(r["id"])) for r in reg)


def test_traceability_files_are_current():
    """lab/registry/traceability.json and lab/TRACEABILITY.md match the registry, modules and examples."""
    from lab.tools import trace
    assert trace.main(["--check"]) == 0


def test_every_requirement_is_marked_as_draft_and_decisions_are_explicit():
    from lab.tools.trace import registry
    for reg in registry().values():
        for r in reg["requirements"]:
            # no tool sets a human review; TEXT_VERIFIED comes only from the semantic verification gate
            assert r["interpretation_status"] in ("DRAFT_UNREVIEWED", "TEXT_VERIFIED")
            if r["hypotheses_needed"] or r["open_questions"]:
                assert r["decision_status"] == "UNRESOLVED"
