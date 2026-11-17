"""Records one author review decision (A6) in an append-only log: lab/registry/author_reviews.jsonl.

    python -m lab.tools.review_record WORKCYCLE-2-01 confirmed --reviewer "<author>" [--note "..."]
    python -m lab.tools.review_record Q-065 answered --reviewer "<author>" --note "<the author's answer>"

Decisions: confirmed | rejected | needs_change (provisions); answered | withdrawn | deferred (open questions).
Nothing is approved automatically: every entry needs an explicit --reviewer. The log is the version history (each entry
keeps the SHA-256 of the item as it was reviewed, so a later registry change shows the review as stale). The registry
itself is not modified; promoting reviewed items is a separate, deliberate registry change.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
REG = ROOT / "lab" / "registry"
LOG = REG / "author_reviews.jsonl"
PROVISION = {"confirmed", "rejected", "needs_change"}
QUESTION = {"answered", "withdrawn", "deferred"}


def items():
    out = {}
    for f in sorted((REG / "requirements").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for r in d.get("requirements", []):
            out[r["id"]] = ("provision", d.get("doc_id"), r)
    oq = json.loads((REG / "open_questions.json").read_text(encoding="utf-8"))
    for q in (oq if isinstance(oq, list) else oq.get("questions", [])):
        out[q["id"]] = ("question", None, q)
    return out


def digest(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("id")
    ap.add_argument("decision")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    known = items()
    if a.id not in known:
        sys.exit(f"unknown id {a.id}")
    kind, doc, item = known[a.id]
    allowed = PROVISION if kind == "provision" else QUESTION
    if a.decision not in allowed:
        sys.exit(f"{a.id} is a {kind}; decision must be one of {sorted(allowed)}")
    if not a.reviewer.strip():
        sys.exit("--reviewer is required")
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "id": a.id, "kind": kind, "document": doc,
             "decision": a.decision, "reviewer": a.reviewer.strip(), "note": a.note, "item_sha256": digest(item)}
    with LOG.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False))


if __name__ == "__main__":
    main()
