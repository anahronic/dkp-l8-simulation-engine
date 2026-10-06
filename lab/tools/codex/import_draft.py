#!/usr/bin/env python3
"""
Turn a Codex draft (output of requirements_prompt.md) into a registry file.

    python -m lab.tools.codex.import_draft DRAFT.json PREFIX [--model NAME]

Adds the document hash, the prefix, provenance and coverage fields.  New entries
start as NOT_IMPLEMENTED (or NOT_COMPUTABLE when the draft says checkable == "no");
coverage becomes IMPLEMENTED/PARTIAL only when a lab check and its tests exist.
The result must pass lab.tools.check_registry before it is committed.
"""

from __future__ import annotations

import argparse
import json
import re
import os
import sys

from lab.tools.check_registry import REQ_DIR, doc_text, load_catalog, normalize, section_names

NOT_IMPLEMENTED_GAP = "No lab check implemented yet."


def resolve_section(doc, raw_text: str, quote: str, section: str):
    """Keep the draft's section if it is a heading; otherwise use the heading under which
    the quote actually stands, and keep the draft's label separately."""
    if section in section_names(doc):
        return section, None
    words = normalize(quote).split(" ")
    if not words or not words[0]:
        return section, None
    pattern = r"\s+".join(re.escape(w) for w in words)
    cleaned = raw_text.replace("**", "").replace("\\", "")      # same line count as the raw text
    m = re.search(pattern, cleaned)
    if not m:
        return section, None
    line = cleaned[:m.start()].count("\n") + 1
    heads = [s for s in doc["sections"] if s["line"] <= line]
    if not heads:
        return "0", section
    h = heads[-1]
    return (h["number"] or h["title"]), section


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("prefix")
    ap.add_argument("--model", default="codex (OpenAI), model from local config")
    args = ap.parse_args(argv)
    with open(args.draft, encoding="utf-8") as f:
        draft = json.load(f)
    catalog = load_catalog()
    doc = catalog[draft["doc_id"]]
    raw_text = doc_text(doc)
    prefix = args.prefix.strip()
    reqs = []
    for r in draft["requirements"]:
        r = dict(r)
        # ids are identifiers: a section given by heading title may contain spaces
        rid = re.sub(r"\s+", "", r["id"])                   # stray CR/whitespace from the prompt
        rid = re.sub("[‐-―−]", "-", rid)      # typographic hyphens
        r["id"] = re.sub(r"[^A-Za-z0-9._-]", "_", rid)
        section, label = resolve_section(doc, raw_text, r["quote"], r["section"])
        r["section"] = section
        if label:
            r["section_label"] = label      # the draft's finer label (e.g. a list item "A.1a")
        if r["checkable"] == "no":
            r["coverage"] = "NOT_COMPUTABLE"
            r["gap"] = r["gap"] or "Not decidable by a program from the text."
        else:
            r["coverage"] = "NOT_IMPLEMENTED"
            r["gap"] = (r["gap"] + " " if r["gap"] else "") + NOT_IMPLEMENTED_GAP
        r["implementation"] = None
        r["tests"] = []
        r["interpretation_status"] = "DRAFT_UNREVIEWED"    # never upgraded by a tool
        r["decision_status"] = "UNRESOLVED" if r.get("hypotheses_needed") else "NONE_IDENTIFIED"
        r["open_questions"] = []
        reqs.append(r)
    out = {
        "schema": "dkp-lab-requirements/1",
        "doc_id": draft["doc_id"],
        "doc_sha256": doc["sha256"],
        "prefix": prefix,
        "provenance": {
            "drafted_by": args.model,
            "prompt": "lab/tools/codex/requirements_prompt.md",
            "review": "machine-checked by lab.tools.check_registry (verbatim quotes, sections, ids); "
                      "interpretations are unreviewed drafts (interpretation_status per requirement)",
            "review_notes": [],
        },
        "draft_notes": draft.get("notes", ""),
        "requirements": reqs,
    }
    path = os.path.join(REQ_DIR, f"{draft['doc_id']}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{path}: {len(reqs)} requirements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
