#!/usr/bin/env python3
"""
Import a Codex classification of open points (output of classify_prompt.md) as a DRAFT.

    python -m lab.tools.codex.import_classification OUT_DIR [--model NAME] [--date YYYY-MM-DD]

OUT_DIR holds one ``<DOC_ID>.json`` per document (classify_schema.json).  The result is
``lab/registry/unresolved_classification.json``: for every provision whose decision is open
(``decision_status == UNRESOLVED``) the origin of the open point — one of the six categories
below — with Codex's one-sentence rationale.  It is a machine draft: it never creates an author
question and never changes a provision's meaning.  Where the lab has verified a provision
against the literal text (``lab/registry/verifications.json``) the verified origin wins.

Rules enforced here, whatever the draft says:
  * every id must be an UNRESOLVED provision of that document, once;
  * ``author_question_candidate`` stays true only for normative_ambiguity or
    architecture_definition (missing calibration, data, documents or code are never author
    questions); corrections are counted in the provenance.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict

from lab.tools.check_registry import REQ_DIR

LAB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(LAB, "registry", "unresolved_classification.json")
PROMPT = os.path.join(LAB, "tools", "codex", "classify_prompt.md")
CATEGORIES = ("normative_ambiguity", "architecture_definition", "l8_parameter", "empirical_model_data",
              "external_dependency", "implementation_only")
AUTHOR_CATEGORIES = ("normative_ambiguity", "architecture_definition")


def unresolved() -> Dict[str, str]:
    out = {}
    for name in sorted(os.listdir(REQ_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(REQ_DIR, name), encoding="utf-8") as f:
                reg = json.load(f)
            for r in reg["requirements"]:
                if r["decision_status"] == "UNRESOLVED":
                    out[r["id"]] = reg["doc_id"]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="gpt-6-astra via OpenAI Codex CLI 0.160.1 (reasoning effort high, read-only sandbox)")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args(argv)
    open_ids = unresolved()
    items: Dict[str, Dict[str, Any]] = {}
    problems, corrected, docs = [], 0, []
    for name in sorted(os.listdir(args.out_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(args.out_dir, name), encoding="utf-8") as f:
            d = json.load(f)
        docs.append(d["doc_id"])
        for it in d["items"]:
            rid = it["id"]
            if open_ids.get(rid) != d["doc_id"]:
                problems.append(f"{name}: {rid} is not an UNRESOLVED provision of {d['doc_id']}")
                continue
            if rid in items:
                problems.append(f"{name}: {rid} classified twice")
                continue
            if it["primary"] not in CATEGORIES or (it["secondary"] is not None and it["secondary"] not in CATEGORIES):
                problems.append(f"{name}: {rid} unknown category")
                continue
            cand = bool(it["author_question_candidate"])
            if cand and it["primary"] not in AUTHOR_CATEGORIES:
                cand, corrected = False, corrected + 1
            items[rid] = {"document": d["doc_id"], "primary": it["primary"],
                          "secondary": it["secondary"] if it["secondary"] != it["primary"] else None,
                          "author_question_candidate": cand, "rationale": it["rationale"].strip()}
    if problems:
        print("\n".join(problems))
        return 1
    with open(PROMPT, "rb") as f:
        prompt_sha = hashlib.sha256(f.read()).hexdigest()
    pending = sorted({doc for rid, doc in open_ids.items() if rid not in items})
    out = {
        "schema": "dkp-lab-unresolved-classification/1",
        "status": "DRAFT_UNREVIEWED",
        "note": ("Machine draft of the origin of each open point (provisions with decision_status UNRESOLVED). "
                 "Not a normative reading and not an author question: author questions are created only after "
                 "manual verification against the literal text (lab/registry/verifications.json), and only for "
                 "normative_ambiguity or architecture_definition."),
        "categories": {
            "normative_ambiguity": "the wording admits readings that change a result and the corpus does not settle it",
            "architecture_definition": "a structural definition (data model, interface, state machine, mapping, referenced symbol) is missing and not derivable",
            "l8_parameter": "a number, threshold, duration, model or calibration assigned to L8 (DKP-8-SIMULATION-001)",
            "empirical_model_data": "needs real-world data or an empirical, causal or behavioural model",
            "external_dependency": "depends on a document, system or actor outside the corpus",
            "implementation_only": "the text is clear enough; only lab code, a record or a data structure is missing"},
        "provenance": {"tool": "lab/tools/codex/classify_prompt.md + classify_schema.json", "prompt_sha256": prompt_sha,
                       "model": args.model, "date": args.date, "documents": docs,
                       "author_candidate_flags_corrected": corrected,
                       "documents_pending": pending},
        "items": dict(sorted(items.items())),
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(items)} of {len(open_ids)} open points classified; {corrected} author flags corrected; "
          f"pending: {', '.join(pending) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
