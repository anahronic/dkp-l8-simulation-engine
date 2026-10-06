#!/usr/bin/env python3
"""
Write the coverage that installed modules declare (``implements``) into the registry.

    python -m lab.tools.sync_coverage           update lab/registry/requirements/*.json
    python -m lab.tools.sync_coverage --check   exit 1 if the registry differs from the declarations

Coverage is never typed into the registry by hand: IMPLEMENTED / PARTIAL come from a
module's ``implements`` table, and tests/lab/test_registry.py checks that every declared
check is actually emitted when the module's examples run.  A requirement that a module
no longer declares falls back to NOT_IMPLEMENTED (or NOT_COMPUTABLE if not checkable).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

from lab.tools.check_registry import REQ_DIR

NOT_IMPLEMENTED_GAP = "No lab check implemented yet."


def declared() -> Dict[str, Dict[str, Any]]:
    """requirement id -> merged declaration.  Several modules may check one provision (in different
    scenarios): the first by module id is the primary implementation, the others are listed in
    ``implementation.also``; coverage is IMPLEMENTED if any module implements it fully."""
    from lab.modules import MODULES
    by_rid: Dict[str, list] = {}
    for mid in sorted(MODULES):
        m = MODULES[mid]
        for rid, (check, coverage, note) in m.implements.items():
            by_rid.setdefault(rid, []).append({"module": m.id, "version": m.version, "check": check,
                                               "coverage": coverage, "note": note, "tests": list(m.tests)})
    out: Dict[str, Dict[str, Any]] = {}
    for rid, decls in by_rid.items():
        full = any(d["coverage"] == "IMPLEMENTED" for d in decls)
        notes = [f"{d['module']}: {d['note']}" if len(decls) > 1 else d["note"]
                 for d in decls if d["coverage"] == "PARTIAL" and d["note"]]
        out[rid] = {**decls[0], "coverage": "IMPLEMENTED" if full else "PARTIAL",
                    "note": " ".join(notes) or None,
                    "tests": sorted({t for d in decls for t in d["tests"]}),
                    "also": [{"module": d["module"], "version": d["version"], "check": d["check"]} for d in decls[1:]]}
    return out


def question_links() -> Dict[str, list]:
    """requirement id -> open question ids (lab/registry/open_questions.json)."""
    with open(os.path.join(os.path.dirname(REQ_DIR), "open_questions.json"), encoding="utf-8") as f:
        qs = json.load(f)["questions"]
    out: Dict[str, list] = {}
    for q in qs:
        if q["status"] == "UNRESOLVED":
            for rid in q["requirements"]:
                out.setdefault(rid, []).append(q["id"])
    return {k: sorted(v) for k, v in out.items()}


def synced(reg: Dict[str, Any], decl: Dict[str, Dict[str, Any]],
           links: Optional[Dict[str, list]] = None) -> Dict[str, Any]:
    reg = json.loads(json.dumps(reg))
    links = question_links() if links is None else links
    for r in reg["requirements"]:
        # derived status fields: interpretation is never upgraded here
        r.setdefault("interpretation_status", "DRAFT_UNREVIEWED")
        r["open_questions"] = links.get(r["id"], [])
        r["decision_status"] = "UNRESOLVED" if (r.get("hypotheses_needed") or r["open_questions"]) \
            else "NONE_IDENTIFIED"
        d = decl.get(r["id"])
        base_gap = (r.get("gap") or "").replace(NOT_IMPLEMENTED_GAP, "").strip() or None
        if d:
            r["coverage"] = d["coverage"]
            r["implementation"] = {"module": d["module"], "version": d["version"], "check": d["check"]}
            if d["also"]:
                r["implementation"]["also"] = d["also"]
            r["tests"] = d["tests"]
            r["gap"] = d["note"] if d["coverage"] == "PARTIAL" else None
        elif r["coverage"] in ("IMPLEMENTED", "PARTIAL") or r["implementation"] is not None:
            r["coverage"] = "NOT_COMPUTABLE" if r["checkable"] == "no" else "NOT_IMPLEMENTED"
            r["implementation"] = None
            r["tests"] = []
            r["gap"] = (base_gap + " " if base_gap else "") + NOT_IMPLEMENTED_GAP
    return reg


def main(argv=None) -> int:
    check_only = "--check" in (argv or sys.argv[1:])
    decl = declared()
    seen = set()
    drift = []
    for name in sorted(os.listdir(REQ_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(REQ_DIR, name)
        with open(path, encoding="utf-8") as f:
            reg = json.load(f)
        new = synced(reg, decl)
        seen |= {r["id"] for r in reg["requirements"]}
        if new != reg:
            drift.append(name)
            if not check_only:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(new, indent=1, ensure_ascii=False) + "\n")
    missing = sorted(set(decl) - seen)
    if missing:
        print("declared but not in the registry:", missing)
        return 1
    print(("drift in: " if check_only else "updated: ") + (", ".join(drift) or "nothing"))
    return 1 if (check_only and drift) else 0


if __name__ == "__main__":
    sys.exit(main())
