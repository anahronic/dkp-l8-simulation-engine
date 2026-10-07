"""
Semantic verification gate (lab/registry/verifications.json).

A finding, a FAIL of a reference example, a normative conflict, a systemic blocker or an author
question gets that status only after the provisions involved have been read against the literal
pinned text.  This module loads the records, checks that every quote is verbatim, and derives:

  * the classification of each finding (UNVERIFIED_FINDING when no record exists);
  * the provisions whose wording was read (interpretation_status TEXT_VERIFIED — a check by the
    lab's author model, not a human review);
  * the verified origin of open points that override the Codex draft classification.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(LAB, "registry")
VERIFICATIONS = os.path.join(REG, "verifications.json")
CLASSIFICATION = os.path.join(REG, "unresolved_classification.json")
FINDINGS_DIR = os.path.join(LAB, "findings")

FINDING_CLASSES = ("CONFIRMED_FINDING", "INTERPRETATION_GAP", "IMPLEMENTATION_BUG", "UNVERIFIED_FINDING")
ORIGINS = ("normative_ambiguity", "architecture_definition", "l8_parameter", "empirical_model_data",
           "external_dependency", "implementation_only")
AUTHOR_ORIGINS = ("normative_ambiguity", "architecture_definition")


def load() -> Dict[str, Any]:
    with open(VERIFICATIONS, encoding="utf-8") as f:
        return json.load(f)


def load_classification() -> Optional[Dict[str, Any]]:
    if not os.path.exists(CLASSIFICATION):
        return None
    with open(CLASSIFICATION, encoding="utf-8") as f:
        return json.load(f)


def finding_ids() -> List[str]:
    return sorted(n[:-3] for n in os.listdir(FINDINGS_DIR) if re.fullmatch(r"F-\d{3}\.md", n))


def classifications(v: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """finding id -> class; findings without a record are UNVERIFIED_FINDING."""
    v = v or load()
    rec = {f["id"]: f["classification"] for f in v["findings"]}
    return {fid: rec.get(fid, "UNVERIFIED_FINDING") for fid in finding_ids()}


def records(v: Dict[str, Any]):
    for sec in ("findings", "reference_fails", "noncompliant_cases", "questions"):
        for rec in v[sec]:
            yield sec, rec


def quote_problems(v: Optional[Dict[str, Any]] = None) -> List[str]:
    """Every quote must occur verbatim (after markdown normalization); 'absent' strings must not."""
    from lab.tools.check_registry import doc_text, load_catalog, normalize
    v = v or load()
    cat = load_catalog()
    texts: Dict[str, str] = {}
    out = []
    for sec, rec in records(v):
        where = f"{sec}:{rec.get('id') or rec.get('requirement')}"
        if not rec.get("quotes"):
            out.append(f"{where}: no quote")
        for q in rec.get("quotes", []):
            if q["doc"] not in cat:
                out.append(f"{where}: unknown document {q['doc']}")
                continue
            t = texts.setdefault(q["doc"], normalize(doc_text(cat[q["doc"]])))
            if "absent" in q:
                if q["absent"] in t:
                    out.append(f"{where}: {q['doc']} contains {q['absent']!r}, recorded as absent")
            elif normalize(q["text"]) not in t:
                out.append(f"{where}: quote not found in {q['doc']}: {q['text'][:80]!r}")
    return out


def verified_provisions(v: Optional[Dict[str, Any]] = None, regs: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
    """requirement id -> verification records that read its wording.  A provision counts as read when
    a record names it (reference_fails, noncompliant_cases) or when a quote of a record overlaps the
    provision's own quote in the same document (one contains the other)."""
    from lab.tools.check_registry import REQ_DIR, normalize
    v = v or load()
    if regs is None:
        regs = {}
        for name in sorted(os.listdir(REQ_DIR)):
            if name.endswith(".json"):
                with open(os.path.join(REQ_DIR, name), encoding="utf-8") as f:
                    reg = json.load(f)
                regs[reg["doc_id"]] = reg
    by_doc = {d: [(r["id"], normalize(r["quote"])) for r in reg["requirements"]] for d, reg in regs.items()}
    out: Dict[str, Set[str]] = {}
    for sec, rec in records(v):
        tag = f"{sec}:{rec.get('id') or rec.get('requirement')}"
        if rec.get("requirement"):
            out.setdefault(rec["requirement"], set()).add(tag)
        for q in rec.get("quotes", []):
            if "text" not in q:
                continue
            qt = normalize(q["text"])
            if len(qt) < 12:                       # too short to identify a provision
                continue
            for rid, rq in by_doc.get(q["doc"], []):
                if qt in rq or (len(rq) >= 12 and rq in qt):
                    out.setdefault(rid, set()).add(tag)
    return {k: sorted(s) for k, s in sorted(out.items())}
