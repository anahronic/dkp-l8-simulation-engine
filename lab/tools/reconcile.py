#!/usr/bin/env python3
"""
Reading of provisions whose draft open point is ``implementation_only`` (review КТ5).

    python -m lab.tools.reconcile            write lab/registry/reconciliations.json from lab/registry/reconciliation_input.json
    python -m lab.tools.reconcile --check    exit 1 if the written file is stale or inconsistent with the registry

Each decision in ``reconciliation_input.json`` is the lab's reading of one provision against the pinned text:
  * ``confirmed``: the text is clear and no author choice is needed; the provision gets a lab check (named here
    from the registry's implementation after ``sync_coverage``);
  * ``reclassified``: the draft origin is wrong; ``origin_after`` names the open point that blocks it, and the
    classification file is updated to it.  A reclassified provision may still have a lab check under a named
    reading (coverage PARTIAL); its open point stays, recorded by an open question where one is raised.
A decision may also correct ``checkable`` (e.g. a draft ``no`` where a partial, observable check exists).

Review of checkpoint 6: every confirmed decision carries a ``closure``.  ``closed``: the draft open point
(implementation_only, i.e. missing lab code) is closed now that the check exists, and the agent's ``answer`` says how
the text settles the draft need; the provision's decision_status becomes NONE_IDENTIFIED by agent reading and its open
point is removed (the draft origin, its need and the reason stay here).  ``open``: something other than code remains
(a missing formula, an undefined criterion, an external artifact, a contested reading); the open point stays with
that ``origin`` and ``reason``.  A PARTIAL coverage is a limit of the check, recorded as ``coverage_limit``, not an
open point.  The reading is the agent's; nothing here is a human acceptance (A6).
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
RECORD = "lab/registry/reconciliations.json"
CLOSURE_STATES = ("closed", "open")


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
            if impl:                               # a check under a named reading may exist while the open point stays
                item["check"] = f"{impl['module']}:{impl['check']}"
            if r.get("open_questions"):
                item["questions"] = r["open_questions"]
        else:
            item["check"] = f"{impl.get('module')}:{impl.get('check')}" if impl else None
            c = d["closure"]
            item["closure"] = {"state": c["state"], "draft_need": r.get("hypotheses_needed") or [],
                               "coverage_limit": r["gap"] if r["coverage"] == "PARTIAL" else None}
            if c["state"] == "closed":
                item["closure"].update(answer=c["answer"], decision_status_after="NONE_IDENTIFIED")
            else:
                item["closure"].update(origin=c["origin"], reason=c["reason"], decision_status_after="UNRESOLVED")
        if "checkable" in d:
            item["checkable"] = d["checkable"]
        items.append(item)
    counts = {"confirmed": sum(1 for x in items if x["verdict"] == "confirmed"),
              "reclassified": sum(1 for x in items if x["verdict"] == "reclassified"),
              "confirmed_closed": sum(1 for x in items if (x.get("closure") or {}).get("state") == "closed"),
              "confirmed_open": sum(1 for x in items if (x.get("closure") or {}).get("state") == "open"),
              "human_accepted": sum(1 for x in items if x["acceptance"]["human_accepted"])}
    return {"schema": "dkp-lab-reconciliation/2", "rule": inp["rule"], "closure_rule": inp["closure_rule"],
            "counts": counts, "items": items}


def apply_side_effects() -> None:
    """Classification origins and checkable values follow the decisions."""
    with open(INPUT, encoding="utf-8") as f:
        inp = json.load(f)
    with open(CLASSIFICATION, encoding="utf-8") as f:
        cls = json.load(f)
    changed = False
    for rid, d in inp["decisions"].items():
        it = cls["items"].setdefault(rid, {})
        c = d.get("closure") or {}
        assert (d["verdict"] == "confirmed") == bool(c) and c.get("state", "closed") in CLOSURE_STATES, rid
        # the classification holds the open point that remains; the draft origin stays in the reconciliation record
        if d["verdict"] == "reclassified":
            want = {"primary": d["origin_after"]}
        elif c["state"] == "closed":
            want = {"primary": "implementation_only", "closed": RECORD}
        else:
            want = {"primary": c["origin"], "residual_reason": c["reason"]}
        want.update(reconciled=RECORD, rationale_reconciled=d["reason"])
        new = {k: v for k, v in it.items() if k not in ("closed", "residual_reason")}
        new.update(want)
        if new != it:
            it.clear()
            it.update(new)
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
