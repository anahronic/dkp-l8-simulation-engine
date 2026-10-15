#!/usr/bin/env python3
"""
Reading of draft open points against the pinned corpus (reviews КТ5 and of checkpoint 6).

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
open point.

The same review asked for the remaining Codex-draft open points of uncovered provisions to be read the same way
(``draft_origin`` names the draft): ``kept`` (the draft origin holds; ``partial_check`` says whether a clear core
could be checked without deciding it), ``reclassified`` (another origin), or ``returned`` (the corpus settles what
the draft said was missing; the provision is resolvable and needs a lab check, after which it carries a ``closure``
like a confirmed one).  The reading is the agent's; nothing here is a human acceptance (A6).
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
VERDICTS = ("confirmed", "reclassified", "kept", "returned")


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
        draft = d.get("draft_origin", "implementation_only")
        item = {"id": rid, "document": r["document"], "quote": r["quote"], "draft_origin": draft,
                "verdict": d["verdict"], "reason": d["reason"],
                "acceptance": {"agent_reading": True, "human_accepted": False}}
        if d["verdict"] in ("reclassified", "kept"):
            item["origin_after"] = d.get("origin_after", draft)
            if "partial_check" in d:
                item["partial_check"] = d["partial_check"]
            if "partial_check_revised" in d:          # review КТ7-GPT-01: the earlier flag and the individual reason
                item["partial_check_revised"] = d["partial_check_revised"]
            if impl:                               # a check under a named reading may exist while the open point stays
                item["check"] = f"{impl['module']}:{impl['check']}"
            if r.get("open_questions"):
                item["questions"] = r["open_questions"]
        else:                                      # confirmed or returned: only lab code was (or is) missing
            item["check"] = f"{impl.get('module')}:{impl.get('check')}" if impl else None
            c = d.get("closure") if d["verdict"] == "returned" else d["closure"]
            item["closure"] = None                 # a returned provision awaiting its lab check
            if c:
                item["closure"] = {"state": c["state"], "draft_need": r.get("hypotheses_needed") or [],
                                   "coverage_limit": r["gap"] if r["coverage"] == "PARTIAL" else None}
                if c["state"] == "closed":
                    item["closure"].update(answer=c["answer"], decision_status_after="NONE_IDENTIFIED")
                else:
                    item["closure"].update(origin=c["origin"], reason=c["reason"], decision_status_after="UNRESOLVED")
        if "checkable" in d:
            item["checkable"] = d["checkable"]
        items.append(item)
    by = lambda v: sum(1 for x in items if x["verdict"] == v)
    counts = {"confirmed": by("confirmed"), "reclassified": by("reclassified"), "kept": by("kept"),
              "returned": by("returned"),
              "returned_awaiting_check": sum(1 for x in items if x["verdict"] == "returned" and not x["closure"]),
              "closure_closed": sum(1 for x in items if (x.get("closure") or {}).get("state") == "closed"),
              "closure_open": sum(1 for x in items if (x.get("closure") or {}).get("state") == "open"),
              "human_accepted": sum(1 for x in items if x["acceptance"]["human_accepted"]),
              "partial_check": sum(1 for x in items if x.get("partial_check")),
              "partial_check_revised": sum(1 for x in items if x.get("partial_check_revised"))}
    out = {"schema": "dkp-lab-reconciliation/3", "rule": inp["rule"], "closure_rule": inp["closure_rule"],
           "reading_rule": inp["reading_rule"]}
    if "core_revision_rule" in inp:
        out["core_revision_rule"] = inp["core_revision_rule"]
    return {**out, "counts": counts, "items": items}


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
        assert d["verdict"] in VERDICTS and c.get("state", "closed") in CLOSURE_STATES, rid
        assert (d["verdict"] != "confirmed" or c) and (not c or d["verdict"] in ("confirmed", "returned")), rid
        # the classification holds the open point that remains; the draft origin stays in the reconciliation record
        if d["verdict"] in ("reclassified", "kept"):
            want = {"primary": d.get("origin_after", d.get("draft_origin"))}
        elif not c:
            want = {"primary": "implementation_only"}
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
