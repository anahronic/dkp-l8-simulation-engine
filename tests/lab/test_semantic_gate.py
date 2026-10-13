"""Semantic verification gate: findings, reference FAILs and author questions are verified against the literal text."""

import json
import os
import re

from lab.core import verification
from lab.tools.check_registry import REQ_DIR

REG = os.path.join(os.path.dirname(__file__), "..", "..", "lab", "registry")
V = verification.load()


def _questions():
    with open(os.path.join(REG, "open_questions.json"), encoding="utf-8") as f:
        return json.load(f)["questions"]


def test_every_quote_is_verbatim_in_the_pinned_corpus():
    assert verification.quote_problems(V) == []


def test_every_finding_is_classified_after_verification():
    cls = verification.classifications(V)
    assert set(cls) == set(verification.finding_ids())
    assert "UNVERIFIED_FINDING" not in cls.values(), [f for f, c in cls.items() if c == "UNVERIFIED_FINDING"]
    assert all(f["classification"] in verification.FINDING_CLASSES[:3] and f["conclusion"] for f in V["findings"])


def test_finding_documents_state_their_classification():
    for fid, c in verification.classifications(V).items():
        with open(os.path.join(verification.FINDINGS_DIR, f"{fid}.md"), encoding="utf-8") as f:
            head = f.read(1200)
        assert re.search(r"\*\*Classification:\*\* " + c, head), fid


def test_every_reference_fail_is_verified():
    """A FAIL in a reference example is a statement about the texts: it needs a verification record whose origin is
    a confirmed finding.  FAILs of noncompliant cases need a record that the provision is literal."""
    from lab.tools.trace import observe
    obs = observe()
    ref = {r["requirement"]: r for r in V["reference_fails"]}
    cls = verification.classifications(V)
    for rid in obs["reference_fails"]:
        assert rid in ref, f"unverified reference FAIL {rid}: {obs['reference_fails'][rid]}"
        assert ref[rid]["origin"] == "CONFIRMED_FINDING" and cls[ref[rid]["finding"]] == "CONFIRMED_FINDING", rid
    nc = {r["requirement"] for r in V["noncompliant_cases"]}
    assert set(obs["noncompliant"]) <= nc, set(obs["noncompliant"]) - nc
    assert set(ref) == set(obs["reference_fails"]), "stale verification records"


def test_every_finding_states_its_effect():
    """Review of checkpoint 4: wording defects, missing definitions and contradictions are not one risk measure."""
    eff = V["effects"]
    for f in V["findings"]:
        assert f.get("effect") in eff, f["id"]
        if f["classification"] == "INTERPRETATION_GAP":
            assert f["effect"] == "reading_dependent", f["id"]
        if f["classification"] == "IMPLEMENTATION_BUG":
            assert f["effect"] == "lab_error", f["id"]
    assert {f["id"] for f in V["findings"] if f["effect"] == "wording_only"} >= {"F-034", "F-038"}


def test_rule_conflict_fails_cite_a_confirmed_finding():
    from lab.modules import MODULES
    cls = verification.classifications(V)
    for m in MODULES.values():
        for name, inp in m.examples().items():
            if m.example_kind(name) != "reference":
                continue
            for c in m.evaluate(m.validate(inp)).checks:
                if c.status == "FAIL" and (c.evidence or {}).get("tag") in ("rule_conflict", "corpus_inconsistency"):
                    cited = re.findall(r"F-\d{3}", c.explanation)
                    assert cited and all(cls[f] == "CONFIRMED_FINDING" for f in cited), (m.id, name, c.requirement_id)


def test_questions_follow_the_gate():
    qs = {q["id"]: q for q in _questions()}
    ver = {q["id"]: q for q in V["questions"]}
    assert set(qs) == set(ver)
    for qid, q in qs.items():
        assert (q["status"], q["category"]) == (ver[qid]["status"], ver[qid]["category"]), qid
        if q["status"] == "UNRESOLVED":
            assert q["category"] in verification.AUTHOR_ORIGINS, qid
        else:
            assert q["status"] == "WITHDRAWN" and q["withdrawn"]["reason"], qid


def test_codex_draft_never_creates_author_questions():
    """The draft classification may flag candidates; only verified records create questions."""
    cls = verification.load_classification()
    if cls is None:
        return
    assert cls["status"] == "DRAFT_UNREVIEWED"
    for rid, it in cls["items"].items():
        assert it["primary"] in verification.ORIGINS
        # the candidate flag is the draft's; a primary corrected by the lab's reading (reconciled) may leave it behind
        if it["author_question_candidate"] and not it.get("reconciled"):
            assert it["primary"] in verification.AUTHOR_ORIGINS, rid
    linked = {rid for q in _questions() for rid in q["requirements"]}
    assert all(q["verification"].endswith(q["id"]) for q in _questions())
    assert linked <= {rid for f in os.listdir(REQ_DIR) if f.endswith(".json")
                      for rid in (r["id"] for r in json.load(open(os.path.join(REQ_DIR, f), encoding="utf-8"))["requirements"])}


def test_text_verified_is_derived_and_not_a_human_review():
    read = verification.verified_provisions(V)
    for name in os.listdir(REQ_DIR):
        if name.endswith(".json"):
            with open(os.path.join(REQ_DIR, name), encoding="utf-8") as f:
                for r in json.load(f)["requirements"]:
                    assert (r["interpretation_status"] == "TEXT_VERIFIED") == (r["id"] in read), r["id"]
                    assert r["interpretation_status"] in ("DRAFT_UNREVIEWED", "TEXT_VERIFIED")


KINDS = {"contradiction", "authority_difference", "broken_reference", "inconsistent_values", "missing_definition",
         "systemic_blocker", "reading_dependent", "lab_error"}


def test_findings_carry_the_proof_their_kind_needs():
    """Review 2026-10-08: a verbatim quote shows the words exist, not that the conclusion follows.  Contradictions need
    a structured analysis, missing definitions the documents, terms and reference chain searched."""
    for f in V["findings"]:
        assert f["kind"] in KINDS, f["id"]
        assert (f["kind"] == "lab_error") == (f["classification"] == "IMPLEMENTATION_BUG"), f["id"]
        if f["kind"] in ("reading_dependent", "authority_difference"):
            assert f["classification"] == "INTERPRETATION_GAP", f["id"]
        if f["kind"] in ("contradiction", "authority_difference"):
            a = f["analysis"]
            for side in ("rule_a", "rule_b"):
                assert all(a[side].get(k) for k in ("text", "subject", "object", "scope", "conditions", "modality")), f["id"]
            assert a["joint_compliance"] and a["priority"] and a["result"], f["id"]
        if f["kind"] == "missing_definition":
            sr = f["searched"]
            assert sr["documents"] and sr["terms"] and sr["reference_chain"], f["id"]


def test_agent_reading_quote_check_and_human_acceptance_are_separate():
    assert "human_acceptance" in V["acceptance"] and "quote_check" in V["acceptance"]
    for sec in ("findings", "reference_fails", "noncompliant_cases", "questions"):
        for rec in V[sec]:
            acc = rec["acceptance"]
            assert acc["agent_reading"] is True and acc["quote_check"] == "automatic"
            assert acc["human_accepted"] is False          # no human has accepted any record yet (A6 open)
