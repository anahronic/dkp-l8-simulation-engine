"""EDITION AND FINALITY module: the clause table against the pinned text, the gate, dating and the digest list."""

import re

import pytest

from lab.core.registry import catalog, requirements
from lab.core.schema import LabInputError
from lab.modules.edition_finality import (DEP, DEPENDENTS, FAULTS, FINALITY, FULL, INC, MAY_IFACE, NEW, PUB, SIM, UNSPEC,
                                          EditionFinalityModule, dependents)
from lab.tools.check_registry import doc_text, normalize

M = EditionFinalityModule()
EX = M.examples()
DOCS = {d["id"]: d for d in catalog()["documents"]}


def run(**inp):
    return M.evaluate(M.validate(inp))


def statuses(res):
    return {c.requirement_id: c.status for c in res.checks}


PHRASES = {NEW: ["new protocol identifier"], INC: ["incompatibility"],
           FULL: ["full-system simulation", "full-system revalidation", "system simulation"],
           SIM: ["simulation under dkp-8-simulation-001", "simulation and audit"], DEP: ["re-simulation of all dependent protocols"],
           PUB: ["public disclosure"], "stage:audit": ["simulation and audit"], UNSPEC: ["explicit compatibility declaration."],
           DEPENDENTS: ["across all dependent protocols"], MAY_IFACE: ["re-simulation of affected interfaces may"],
           "version_increment": ["version increment"], "compatibility_audit": ["compatibility audit"], "migration_path": ["migration path"]}


def phrase_in(tok, text):
    if tok.startswith("compat:") and tok not in PHRASES:
        ds = tok[7:].split("+")
        return f"compatibility declaration with {ds[0].lower()}" in text and all(d.lower() in text for d in ds)
    return any(p in text for p in PHRASES[tok])


def finality_text(doc):
    d = DOCS[doc]
    heads = d["sections"]
    i = next(k for k, h in enumerate(heads) if "Finality" in h["title"])
    end = next((h["line"] for h in heads[i + 1:] if h["level"] <= heads[i]["level"]), None)
    lines = doc_text(d).split("\n")[heads[i]["line"] - 1:(end - 1) if end else None]
    return normalize("\n".join(lines)).lower()


@pytest.mark.parametrize("doc", sorted(FINALITY))
def test_table_matches_the_pinned_clause(doc):
    proc, extra, items, pres, integ = FINALITY[doc]
    text = finality_text(doc)
    reg = {r["id"]: normalize(r["quote"]).lower() for r in requirements(doc)}
    assert "controlled procedure of dkp-4-upgrade-001" in reg[proc]
    for tok in extra:
        assert phrase_in(tok, text), (doc, tok)
    for rid, toks in items:
        for tok in toks:
            assert phrase_in(tok, reg[rid]) or (rid in ("IDENTITY-14-02",) and phrase_in(tok, text)), (rid, tok)
    for rid in pres:
        assert "presentation-only" in reg[rid] or "recorded only by" in reg[rid]
    assert (integ is not None) == ("edition integrity" in text)
    if integ:
        assert reg[integ].startswith("edition integrity")


def test_every_clause_with_the_upgrade_procedure_is_in_the_table():
    with_clause = {d for d in DOCS if "controlled procedure of DKP-4-UPGRADE-001: proposal" in doc_text(DOCS[d])}
    assert with_clause == set(FINALITY)


def test_pinned_digest_list_matches_the_pinned_documents():
    rm = catalog()["corpus"]["release_manifest"]
    assert rm["header"] == ["Dikenocracy release 2026-10-04"]
    assert all(rm["entries"][d["path"]] == d["sha256"] for d in DOCS.values())
    assert len(rm["entries"]) == len(DOCS) + 1                     # plus the compiled TXT edition, not pinned


def test_scope_dependents_readings():
    assert dependents("depends_on") == ["DKP-1-EPISTEMIC-BOUNDARIES-001", "DKP-6-RESILIENCE-001"]
    assert len(dependents("references")) == 17 and set(dependents("depends_on")) <= set(dependents("references"))


@pytest.mark.parametrize("name", [n for n in EX if M.example_kind(n) == "reference"])
def test_reference_breaks_no_rule(name):
    assert "FAIL" not in statuses(run(**EX[name])).values()


def test_every_document_example_exercises_every_provision():
    st = statuses(run(**EX["every_document"]))
    assert set(st) == set(M.implements) and "NOT_APPLICABLE" not in st.values()
    assert sorted(k for k, v in st.items() if v == "UNKNOWN") == ["CRISIS-11-01", "ERROR-12-03", "UPGRADE-12-02"]


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_fault_is_detected(fault):
    clean, broken = statuses(run()), statuses(run(faults=[fault]))
    assert any(broken[k] == "FAIL" and clean[k] == "PASS" for k in broken), fault


def test_gate_decisions_and_editions():
    out = run().outputs
    d = {x["change"]: x for x in out["decisions"]}
    assert d["info_v2"]["identifier"] == "DKP-5-INFO-002" and d["scope_v2"]["identifier"] == "DKP-7-SCOPE-002"
    assert d["audit_direct"]["missing"] == ["channel:upgrade"] and not d["audit_direct"]["accepted"]
    assert d["privacy_half"]["missing"] == ["compat:DKP-7-SCOPE-001+DKP-7-TRANSPARENCY-001"]
    assert d["crisis_light"]["missing"] == ["sim:full_system"]
    assert not d["justice_typo"]["upgrade"] and d["justice_typo"]["identifier"] == "DKP-1-JUSTICE-001"
    rel = {r["release"]: r for r in out["releases"]}
    assert rel["r2"]["new_or_changed_editions"] == [] and rel["r3"]["new_or_changed_editions"] == []
    assert rel["r4"]["new_or_changed_editions"] == ["DKP-5-INFO-001", "DKP-7-SCOPE-002"]
    assert all(not r["unlisted"] for r in out["releases"])
    assert [(a["activation"], a["activation_day"]) for a in out["activations"]] == [("info_v2", 40), ("error_v2", 40), ("scope_v2", 70)]


def test_strict_record_reading_breaks_edition_integrity():
    st = statuses(run(**EX["strict_record_reading"]))
    assert st["INFO-14-03"] == "PASS" and st["INFO-14-04"] == "FAIL" and st["UPGRADE-12-07"] == "FAIL"


@pytest.mark.parametrize("name", sorted(M.failure_examples()))
def test_invalid_inputs_are_refused(name):
    with pytest.raises(LabInputError):
        M.validate(M.failure_examples()[name])


def test_identifiers_increment_the_number():
    from lab.modules.edition_finality import next_identifier
    assert next_identifier("DKP-5-TRANSPORT-001-APPENDIX-A", set()) == "DKP-5-TRANSPORT-002-APPENDIX-A"
    assert next_identifier("DKP-4-ERROR-001", {"DKP-4-ERROR-002"}) == "DKP-4-ERROR-003"
    assert re.fullmatch(r"DKP-7-SCOPE-002", next_identifier("DKP-7-SCOPE-001", set()))
