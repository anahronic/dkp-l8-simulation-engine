#!/usr/bin/env python3
"""
Validate requirement registry files against the pinned corpus.

    python -m lab.tools.check_registry [FILE_OR_DIR ...]

Checks for every requirement:
  - schema fields and enum values;
  - the id is unique across the registry and starts with the document prefix;
  - ``quote`` occurs verbatim in the source document (after removing Markdown
    bold markers and backslash escapes, and collapsing whitespace);
  - ``section`` names a heading of the document (number or title), or "0";
  - coverage / implementation consistency (IMPLEMENTED or PARTIAL needs an
    implementation and tests; NOT_IMPLEMENTED/BLOCKED/NOT_COMPUTABLE need a gap).
Exit status 1 if any problem is found.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List

LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(LAB_ROOT, "registry", "protocol_catalog.json")
SNAPSHOT = os.path.join(LAB_ROOT, "corpus", "world-aad3e86")
REQ_DIR = os.path.join(LAB_ROOT, "registry", "requirements")

KINDS = {"formula", "constraint", "contract", "state_transition", "dynamic_model", "definition"}
CHECKABLE = {"yes", "partial", "no"}
NUMERIC = {"text", "calibration", "hypothesis", "missing", "none"}
COVERAGE = {"IMPLEMENTED", "PARTIAL", "NOT_IMPLEMENTED", "BLOCKED", "NOT_COMPUTABLE"}
REQUIRED = ["id", "section", "title", "quote", "interpretation", "kind", "checkable", "inputs",
            "criterion", "numeric_source", "normative_dependencies", "data_dependencies", "gap",
            "hypotheses_needed", "coverage", "implementation", "tests",
            "interpretation_status", "decision_status", "open_questions"]
# DRAFT_UNREVIEWED: machine draft, not a confirmed reading; TEXT_VERIFIED: its wording was read
# against the literal text by the lab's semantic verification gate (lab/registry/verifications.json,
# derived by sync_coverage) — not a human review; REVIEWED: checked by a human reviewer;
# CONFIRMED_BY_AUTHOR: the author accepted the reading.  No tool sets REVIEWED or CONFIRMED_BY_AUTHOR.
INTERPRETATION = {"DRAFT_UNREVIEWED", "TEXT_VERIFIED", "REVIEWED", "CONFIRMED_BY_AUTHOR"}
# UNRESOLVED: an open point needs a decision — by the author, by L8 calibration, by data or by lab
# work; ``open_point.origin`` says which (draft classification unless text-verified)
DECISION = {"UNRESOLVED", "NONE_IDENTIFIED"}
ORIGINS = ("normative_ambiguity", "architecture_definition", "l8_parameter", "empirical_model_data",
           "external_dependency", "implementation_only")
AUTHOR_ORIGINS = ("normative_ambiguity", "architecture_definition")
QUESTION_STATUS = {"UNRESOLVED", "WITHDRAWN"}
OPEN_QUESTIONS = os.path.join(LAB_ROOT, "registry", "open_questions.json")
PREFIXES = os.path.join(LAB_ROOT, "registry", "prefixes.json")


def normalize(text: str) -> str:
    text = text.replace("**", "").replace("\\", "")
    text = text.replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def load_catalog() -> Dict[str, Any]:
    with open(CATALOG, encoding="utf-8") as f:
        return {d["id"]: d for d in json.load(f)["documents"]}


def doc_text(doc: Dict[str, Any]) -> str:
    rel = doc["path"]
    with open(os.path.join(SNAPSHOT, rel), encoding="utf-8") as f:
        return f.read()


def section_names(doc: Dict[str, Any]) -> set:
    names = {"0"}
    for s in doc["sections"]:
        if s["number"]:
            names.add(s["number"])
        names.add(s["title"])
    return names


def check_file(path: str, catalog: Dict[str, Any], seen_ids: Dict[str, str]) -> List[str]:
    problems: List[str] = []
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    doc_id = reg.get("doc_id")
    if doc_id not in catalog:
        return [f"{path}: unknown doc_id {doc_id!r}"]
    doc = catalog[doc_id]
    if reg.get("doc_sha256") != doc["sha256"]:
        problems.append(f"{doc_id}: doc_sha256 does not match the pinned document")
    text = normalize(doc_text(doc))
    sections = section_names(doc)
    prefix = reg.get("prefix")
    for i, r in enumerate(reg.get("requirements", [])):
        where = f"{doc_id}[{i}] {r.get('id')}"
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            problems.append(f"{where}: missing fields {missing}")
            continue
        if not str(r["id"]).startswith(f"{prefix}-"):
            problems.append(f"{where}: id does not start with prefix {prefix}-")
        if r["id"] in seen_ids:
            problems.append(f"{where}: duplicate id (also in {seen_ids[r['id']]})")
        seen_ids[r["id"]] = doc_id
        if r["kind"] not in KINDS:
            problems.append(f"{where}: kind {r['kind']!r}")
        if r["checkable"] not in CHECKABLE:
            problems.append(f"{where}: checkable {r['checkable']!r}")
        if r["numeric_source"] not in NUMERIC:
            problems.append(f"{where}: numeric_source {r['numeric_source']!r}")
        if r["coverage"] not in COVERAGE:
            problems.append(f"{where}: coverage {r['coverage']!r}")
        if not r["quote"] or normalize(r["quote"]) not in text:
            problems.append(f"{where}: quote not found verbatim: {r['quote'][:80]!r}")
        if r["section"] not in sections:
            problems.append(f"{where}: section {r['section']!r} is not a heading of the document")
        if r["coverage"] in ("IMPLEMENTED", "PARTIAL"):
            if not r["implementation"] or not r["tests"]:
                problems.append(f"{where}: {r['coverage']} needs implementation and tests")
        elif not r["gap"]:
            problems.append(f"{where}: {r['coverage']} needs a gap reason")
        if r["interpretation_status"] not in INTERPRETATION:
            problems.append(f"{where}: interpretation_status {r['interpretation_status']!r}")
        if r["decision_status"] not in DECISION:
            problems.append(f"{where}: decision_status {r['decision_status']!r}")
        needs = bool(r["hypotheses_needed"]) or bool(r["open_questions"])
        if needs and r["decision_status"] != "UNRESOLVED":
            problems.append(f"{where}: open decisions but decision_status {r['decision_status']}")
        op = r.get("open_point")
        if op is not None:
            if r["decision_status"] != "UNRESOLVED":
                problems.append(f"{where}: open_point on a provision without an open decision")
            if op.get("origin") not in ORIGINS or op.get("source") not in ("codex_draft", "text_verified"):
                problems.append(f"{where}: open_point {op!r}")
    return problems


def check_open_questions(seen_ids: Dict[str, str]) -> List[str]:
    """Every requirement linked by an open question exists, unless its document is not registered yet."""
    with open(OPEN_QUESTIONS, encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    with open(PREFIXES, encoding="utf-8") as f:
        prefix_doc = {p: d for d, p in json.load(f).items()}
    registered = set(seen_ids.values())
    problems, ids = [], set()
    for q in qs:
        if q["id"] in ids:
            problems.append(f"open_questions: duplicate {q['id']}")
        ids.add(q["id"])
        if q.get("status") not in QUESTION_STATUS:
            problems.append(f"open_questions {q['id']}: status {q.get('status')!r}")
        if q.get("category") not in ORIGINS:
            problems.append(f"open_questions {q['id']}: category {q.get('category')!r}")
        elif q["status"] == "UNRESOLVED" and q["category"] not in AUTHOR_ORIGINS:
            problems.append(f"open_questions {q['id']}: an author question must be normative_ambiguity or "
                            f"architecture_definition, not {q['category']}")
        if q.get("status") == "WITHDRAWN" and not (q.get("withdrawn") or {}).get("reason"):
            problems.append(f"open_questions {q['id']}: WITHDRAWN without a reason")
        for rid in q["requirements"]:
            doc = prefix_doc.get(rid.split("-", 1)[0])
            if rid not in seen_ids and doc in registered:
                problems.append(f"open_questions {q['id']}: unknown requirement {rid}")
    return problems


def main(argv: List[str]) -> int:
    catalog = load_catalog()
    targets = argv or [REQ_DIR]
    files: List[str] = []
    for t in targets:
        if os.path.isdir(t):
            files += sorted(os.path.join(t, n) for n in os.listdir(t) if n.endswith(".json"))
        else:
            files.append(t)
    seen: Dict[str, str] = {}
    problems: List[str] = []
    total = 0
    for p in files:
        problems += check_file(p, catalog, seen)
        with open(p, encoding="utf-8") as f:
            total += len(json.load(f).get("requirements", []))
    if not argv:
        problems += check_open_questions(seen)
    for line in problems:
        print(line)
    print(f"{len(files)} files, {total} requirements, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
