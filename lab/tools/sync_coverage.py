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
from typing import Any, Dict

from lab.tools.check_registry import REQ_DIR

NOT_IMPLEMENTED_GAP = "No lab check implemented yet."


def declared() -> Dict[str, Dict[str, Any]]:
    from lab.modules import MODULES
    out: Dict[str, Dict[str, Any]] = {}
    for m in MODULES.values():
        for rid, (check, coverage, note) in m.implements.items():
            if rid in out:
                raise ValueError(f"{rid} is declared by two modules")
            out[rid] = {"module": m.id, "version": m.version, "check": check, "coverage": coverage,
                        "note": note, "tests": list(m.tests)}
    return out


def synced(reg: Dict[str, Any], decl: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    reg = json.loads(json.dumps(reg))
    for r in reg["requirements"]:
        d = decl.get(r["id"])
        base_gap = (r.get("gap") or "").replace(NOT_IMPLEMENTED_GAP, "").strip() or None
        if d:
            r["coverage"] = d["coverage"]
            r["implementation"] = {"module": d["module"], "version": d["version"], "check": d["check"]}
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
