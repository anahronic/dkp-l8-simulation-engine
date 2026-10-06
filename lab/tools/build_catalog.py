#!/usr/bin/env python3
"""
Build lab/registry/protocol_catalog.json from the pinned corpus snapshot.

    python -m lab.tools.build_catalog            verify CORPUS.json, write the catalog
    python -m lab.tools.build_catalog --freeze   (re)write CORPUS.json from the files
    python -m lab.tools.build_catalog --compare-local DIR
                                                  compare a local mirror with the snapshot

The number of protocols is computed from the documents (front matter
``kind: protocol``), never maintained by hand.  References to other documents
are resolved only against document ids and the explicit alias table in
lab/registry/aliases.json; everything else is reported as unresolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import yaml

LAB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_DIR = os.path.join(LAB_ROOT, "corpus")
SNAPSHOT_DIR = os.path.join(CORPUS_DIR, "world-aad3e86")
CORPUS_JSON = os.path.join(CORPUS_DIR, "CORPUS.json")
ALIASES_JSON = os.path.join(LAB_ROOT, "registry", "aliases.json")
CATALOG_JSON = os.path.join(LAB_ROOT, "registry", "protocol_catalog.json")

WORLD_REPOSITORY = "https://github.com/anahronic/World"
WORLD_COMMIT = "aad3e86ca293d61c7c6d3a0a05741d23676f0e18"
SITE = "https://dikenocracy.com/pages/protocols/"

REF_RE = re.compile(r"DKP-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_ID = r"DKP-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
_NUM = r"[0-9]+(?:\.[0-9]+)*"
# references to a section of a document: "DKP-X Section 4.1", "DKP-X §3", "Section 7.1 of DKP-X",
# "Appendix A.4 / Article 12 of the Code of Planetary Synergy", and bare "Section 4.1" / "§4.1" (own document)
SECTION_REF_RES = [
    ("id_first", re.compile(rf"({_ID}),? (?:§ ?|[Ss]ection )({_NUM})")),
    ("section_first", re.compile(rf"(?:[Ss]ection |§ ?)({_NUM}) of ({_ID})")),
    ("codex", re.compile(r"((?:Appendix [A-Z]\.[0-9]+)|(?:Article [0-9]+)) of the Code of Planetary Synergy")),
    ("own", re.compile(rf"(?<!§)(?:[Ss]ection |§ ?)({_NUM})(?![0-9.]*x)(?! of (?:DKP|the Code))")),
]
CODEX_ID = "CODE-OF-PLANETARY-SYNERGY"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
NUMBER_RE = re.compile(r"^((?:[A-Z]\.)?\d+(?:\.(?:\d+|x))*|[A-Z]\.\d+(?:\.\d+)*)[.)]?\s+(.*)$")
BOLD_LINE_RE = re.compile(r"^\*\*([^*].*?)\*\*\s*$")


def _read(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def _files() -> List[str]:
    out = []
    for dirpath, _, names in os.walk(SNAPSHOT_DIR):
        for n in names:
            if n.endswith(".md"):
                out.append(os.path.relpath(os.path.join(dirpath, n), SNAPSHOT_DIR).replace(os.sep, "/"))
    return sorted(out)


def freeze() -> Dict[str, Any]:
    files = {}
    for rel in _files():
        data = _read(os.path.join(SNAPSHOT_DIR, rel))
        files[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    manifest = {"repository": WORLD_REPOSITORY, "commit": WORLD_COMMIT,
                "snapshot_dir": "lab/corpus/world-aad3e86",
                "note": "Byte copies (LF) of every Markdown document under Dikenocracy/ at the commit.",
                "files": files}
    with open(CORPUS_JSON, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return manifest


class CorpusError(RuntimeError):
    pass


def verify() -> Dict[str, Any]:
    """Actual bytes against CORPUS.json; raise on any difference, missing or extra file."""
    with open(CORPUS_JSON, encoding="utf-8") as f:
        manifest = json.load(f)
    actual = set(_files())
    pinned = set(manifest["files"])
    problems = [f"missing: {p}" for p in sorted(pinned - actual)]
    problems += [f"not pinned: {p}" for p in sorted(actual - pinned)]
    for rel in sorted(pinned & actual):
        h = hashlib.sha256(_read(os.path.join(SNAPSHOT_DIR, rel))).hexdigest()
        if h != manifest["files"][rel]["sha256"]:
            problems.append(f"changed: {rel}")
    if problems:
        raise CorpusError("corpus snapshot does not match CORPUS.json: " + "; ".join(problems))
    return manifest


def _front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            return yaml.safe_load(text[4:end]) or {}, text[end + 5:]
    return {}, text


def _clean(s: str) -> str:
    return s.replace("**", "").replace("\\", "").strip()


def _headings(body: str, offset_lines: int) -> List[Dict[str, Any]]:
    """Markdown headings, plus whole-line bold text used as headings in some documents
    (e.g. AXIOMS '**5. Axiom Evaluation Rules**'); bold pseudo-headings get level 7."""
    out = []
    for i, line in enumerate(body.split("\n"), start=1 + offset_lines):
        m = HEADING_RE.match(line)
        b = BOLD_LINE_RE.match(line) if not m else None
        if not (m or b):
            continue
        title = _clean(m.group(2) if m else b.group(1))
        n = NUMBER_RE.match(title)
        out.append({"level": len(m.group(1)) if m else 7, "number": n.group(1) if n else None,
                    "title": n.group(2) if n else title, "line": i})
    return out


def _depends(meta: Optional[str]) -> List[str]:
    if not meta:
        return []
    for part in str(meta).split("·"):
        part = part.strip()
        if part.lower().startswith("depends on:"):
            return [x.strip() for x in part.split(":", 1)[1].split(",") if x.strip()]
    return []


def _kind(rel: str, fm: Dict[str, Any]) -> str:
    k = fm.get("kind")
    if k == "protocol":
        return "protocol"
    if k == "addendum":
        return "addendum"
    if k == "appendix":
        return "appendix"
    if k == "code":
        return "codex"
    if "Glossary" in rel:
        return "glossary"
    return str(k or "unknown")


def build() -> Dict[str, Any]:
    manifest = verify()
    with open(ALIASES_JSON, encoding="utf-8") as f:
        aliases = json.load(f)
    docs: Dict[str, Dict[str, Any]] = {}
    texts: Dict[str, str] = {}
    for rel in sorted(manifest["files"]):
        raw = _read(os.path.join(SNAPSHOT_DIR, rel)).decode("utf-8")
        fm, body = _front_matter(raw)
        offset = raw[:len(raw) - len(body)].count("\n")
        doc_id = os.path.splitext(os.path.basename(rel))[0].replace(" ", "-").upper()
        kind = _kind(rel, fm)
        layer_m = re.search(r"/(L\d)_", rel)
        heads = _headings(body, offset)
        title = next((h["title"] for h in heads if h["level"] <= 3), None)
        if kind in ("codex", "appendix") and fm.get("id"):
            title = str(fm["id"])
        parent = None
        if kind in ("addendum", "appendix"):
            parent = re.sub(r"-(PATCH|APPENDIX-A)$", "", doc_id)
        slug = fm.get("slug")
        docs[doc_id] = {
            "id": doc_id,
            "front_matter_id": fm.get("id"),
            "kind": kind,
            "parent": parent,
            "layer": layer_m.group(1) if layer_m else None,
            "title": title,
            "path": f"Dikenocracy/{rel}" if not rel.startswith("Dikenocracy/") else rel,
            "sha256": manifest["files"][rel]["sha256"],
            "bytes": manifest["files"][rel]["bytes"],
            "last_updated": str(fm["last_updated"]) if fm.get("last_updated") else None,
            "site_url": f"{SITE}{slug}.html" if slug else None,
            "declared_dependencies": _depends(fm.get("meta")),
            "sections": heads,
        }
        texts[doc_id] = raw

    ids = set(docs)
    unresolved: Dict[str, List[str]] = {}
    ambiguous: Dict[str, List[str]] = {}
    for doc_id, raw in texts.items():
        refs: Dict[str, Dict[str, Any]] = {}
        for ln, line in enumerate(raw.split("\n"), start=1):
            for m in REF_RE.finditer(line):
                token = m.group(0).rstrip("-")
                if token in aliases["not_references"]:
                    continue
                if token in ids:
                    target, status = token, "resolved"
                elif token in aliases["aliases"]:
                    target, status = aliases["aliases"][token], "alias"
                elif token in aliases["ambiguous"]:
                    target, status = None, "AMBIGUOUS_REFERENCE"
                    ambiguous.setdefault(token, []).append(doc_id)
                else:
                    target, status = None, "UNRESOLVED_DEPENDENCY"
                    unresolved.setdefault(token, []).append(doc_id)
                entry = refs.setdefault(token, {"raw": token, "target": target, "status": status, "lines": []})
                entry["lines"].append(ln)
        docs[doc_id]["references"] = sorted(refs.values(), key=lambda r: r["raw"])
        for dep in docs[doc_id]["declared_dependencies"]:
            if dep not in ids and dep not in aliases["aliases"]:
                unresolved.setdefault(dep, []).append(doc_id)

    section_refs = _section_references(docs, texts, aliases)
    counts = {}
    for d in docs.values():
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    return {
        "schema": "dkp-lab-catalog/1",
        "corpus": {"repository": manifest["repository"], "commit": manifest["commit"],
                   "snapshot_dir": manifest["snapshot_dir"],
                   "corpus_json_sha256": hashlib.sha256(_read(CORPUS_JSON)).hexdigest()},
        "counts": {"documents": len(docs), "by_kind": dict(sorted(counts.items())),
                   "protocols": counts.get("protocol", 0),
                   "accompanying": len(docs) - counts.get("protocol", 0)},
        "documents": [docs[k] for k in sorted(docs)],
        "unresolved_dependencies": [{"raw": k, "referenced_by": sorted(set(v))} for k, v in sorted(unresolved.items())],
        "ambiguous_references": [{"raw": k, "referenced_by": sorted(set(v)), "note": aliases["ambiguous"][k]}
                                 for k, v in sorted(ambiguous.items())],
        "section_references": {"checked": len(section_refs),
                               "broken": [r for r in section_refs if r["status"] != "resolved"]},
    }


def _has_section(doc: Dict[str, Any], text: str, label: str) -> bool:
    if label.startswith("Article "):
        return re.search(rf"^{re.escape(label)}\.", text, flags=re.M) is not None
    if label.startswith("Appendix "):
        label = label.split(" ", 1)[1]
    return any(h["number"] == label for h in doc["sections"])


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _section_of(heads: List[Dict[str, Any]], h: Dict[str, Any]) -> str:
    """Number of the numbered section that contains heading h (h itself if numbered)."""
    if h["number"]:
        return h["number"]
    prev = [x for x in heads if x["line"] < h["line"] and x["number"]]
    return prev[-1]["number"] if prev else ""


def _section_references(docs, texts, aliases) -> List[Dict[str, Any]]:
    """Every reference to a numbered section, with whether that section exists in the target."""
    out = []
    for doc_id, raw in texts.items():
        for ln, line in enumerate(raw.split("\n"), start=1):
            seen = set()
            for kind, rx in SECTION_REF_RES:
                for m in rx.finditer(line):
                    if any(a <= m.start() < b for a, b in seen):
                        continue
                    seen.add((m.start(), m.end()))
                    if kind == "id_first":
                        token, label = m.group(1), m.group(2)
                    elif kind == "section_first":
                        label, token = m.group(1), m.group(2)
                    elif kind == "codex":
                        token, label = CODEX_ID, m.group(1)
                    else:
                        token, label = doc_id, m.group(1)
                    target = token if token in docs else aliases["aliases"].get(token)
                    named = re.match(r"\s*\(([A-Z][^)]{3,80})\)", line[m.end():])
                    entry = {"from": doc_id, "line": ln, "kind": kind, "target": target or token, "section": label}
                    if target is None:
                        status = "TARGET_UNRESOLVED"
                    elif not _has_section(docs[target], texts[target], label):
                        status = "SECTION_NOT_FOUND"
                    elif named and kind != "codex":
                        # "Section N (Title)": the title must be the heading of section N
                        want = _norm_title(named.group(1))
                        heads = docs[target]["sections"]
                        title_n = next((h["title"] for h in heads if h["number"] == label), "")
                        if _norm_title(title_n) == want:
                            status = "resolved"
                        else:
                            status = "TITLE_MISMATCH"
                            entry["heading_of_section"] = title_n
                            entry["title_found_under"] = sorted({_section_of(heads, h) for h in heads
                                                                 if _norm_title(h["title"]) == want})
                        entry["title"] = named.group(1)
                    else:
                        status = "resolved"
                    out.append({**entry, "status": status, "text": m.group(0)})
    return sorted(out, key=lambda r: (r["from"], r["line"], r["text"]))


def compare_local(local_dir: str) -> List[str]:
    """Compare a local mirror (e.g. E:/002 Dikenocracy/Canonical) by file name."""
    manifest = verify()
    by_name = {os.path.basename(rel): v["sha256"] for rel, v in manifest["files"].items()}
    report = []
    seen = set()
    for dirpath, _, names in os.walk(local_dir):
        for n in sorted(names):
            if not n.endswith(".md"):
                continue
            h = hashlib.sha256(_read(os.path.join(dirpath, n))).hexdigest()
            seen.add(n)
            if n not in by_name:
                report.append(f"extra in local mirror: {n}")
            elif by_name[n] != h:
                report.append(f"differs: {n}")
    report += [f"missing in local mirror: {n}" for n in sorted(set(by_name) - seen)]
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--compare-local", metavar="DIR")
    args = ap.parse_args(argv)
    if args.freeze:
        m = freeze()
        print(f"pinned {len(m['files'])} files")
    if args.compare_local:
        rep = compare_local(args.compare_local)
        print("\n".join(rep) if rep else "local mirror identical to the snapshot")
        return 0
    catalog = build()
    with open(CATALOG_JSON, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(catalog, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    c = catalog["counts"]
    print(f"documents {c['documents']}, protocols {c['protocols']}, accompanying {c['accompanying']}, "
          f"unresolved {[u['raw'] for u in catalog['unresolved_dependencies']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
