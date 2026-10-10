#!/usr/bin/env python3
"""
Reading of provisions whose draft open point is ``implementation_only`` (review КТ5).

    python -m lab.tools.reconcile            write lab/registry/reconciliations.json from lab/registry/reconciliation_input.json
    python -m lab.tools.reconcile --check    exit 1 if the written file is stale or inconsistent with the registry

Each decision in ``reconciliation_input.json`` is the lab's reading of one provision against the pinned text:
  * ``confirmed``: the text is clear and no author choice is needed; the provision gets a lab check (named here
    from the registry's implementation after ``sync_coverage``);
  * ``reclassified``: the draft origin is wrong; ``origin_after`` names the open point that blocks it, and the
    classification file is updated to it.
A decision may also correct ``checkable`` (e.g. a draft ``no`` where a partial, observable check exists).  The
reading is the agent's; nothing here is a human acceptance (A6).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(LAB, "registry")
INPUT = os.path.join(REG, "reconciliation_input.json")
OUTPUT = os.path.join(REG, "reconciliations.json")
CLASSIFICATION = os.path.join(REG, "unresolved_classification.json")
REQ_DIR = os.path.join(REG, "requirements")


def registry() -> Dict[str, Dict[str, Any]]:
    out = {}
    for name in sorted(os.listdir(REQ_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(REQ_DIR, name), encoding="utf-8") as f:
                d = json.load(f)
            for r in d["requirements"]:
                out[r["id"]] = {**r, "document": d["doc_id"]}
    return out


def build() -> Dict[str, Any]:
    with open(INPUT, encoding="utf-8") as f:
        inp = json.load(f)
    reg = registry()
    items: List[Dict[str, Any]] = []
    for rid in sorted(inp["decisions"]):
        d = inp["decisions"][rid]
        r = reg[rid]
        impl = r.get("implementation") or {}
        item = {"id": rid, "document": r["document"], "quote": r["quote"], "draft_origin": "implementation_only",
                "verdict": d["verdict"], "reason": d["reason"],
                "acceptance": {"agent_reading": True, "human_accepted": False}}
        if d["verdict"] == "reclassified":
            item["origin_after"] = d["origin_after"]
        else:
            item["check"] = f"{impl.get('module')}:{impl.get('check')}" if impl else None
        if "checkable" in d:
            item["checkable"] = d["checkable"]
        items.append(item)
    counts = {"confirmed": sum(1 for x in items if x["verdict"] == "confirmed"),
              "reclassified": sum(1 for x in items if x["verdict"] == "reclassified")}
    return {"schema": "dkp-lab-reconciliation/1", "rule": inp["rule"], "counts": counts, "items": items}


def apply_side_effects() -> None:
    """Classification origins and checkable values follow the decisions."""
    with open(INPUT, encoding="utf-8") as f:
        inp = json.load(f)
    with open(CLASSIFICATION, encoding="utf-8") as f:
        cls = json.load(f)
    changed = False
    for rid, d in inp["decisions"].items():
        it = cls["items"].setdefault(rid, {})
        want = d["origin_after"] if d["verdict"] == "reclassified" else "implementation_only"
        if it.get("primary") != want or it.get("reconciled") != "lab/registry/reconciliations.json" or                 it.get("rationale_reconciled") != d["reason"]:
            it.update(primary=want, reconciled="lab/registry/reconciliations.json", rationale_reconciled=d["reason"])
            changed = True
    if changed:
        with open(CLASSIFICATION, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(cls, indent=1, ensure_ascii=False) + "\n")
    for name in sorted(os.listdir(REQ_DIR)):
        if not name.endswith(".json"):
            continue
        p = os.path.join(REQ_DIR, name)
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        dirty = False
        for r in doc["requirements"]:
            d = inp["decisions"].get(r["id"])
            if d and "checkable" in d and r["checkable"] != d["checkable"]["to"]:
                assert r["checkable"] == d["checkable"]["from"], r["id"]
                r["checkable"] = d["checkable"]["to"]
                r["checkable_reconciled"] = {"from": d["checkable"]["from"], "by": "lab reading",
                                             "record": "lab/registry/reconciliations.json"}
                dirty = True
        if dirty:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        with open(OUTPUT, encoding="utf-8") as f:
            stale = json.load(f) != build()
        print("reconciliations stale" if stale else "reconciliations current")
        return 1 if stale else 0
    apply_side_effects()
    out = build()
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(out['items'])} decisions: {out['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
