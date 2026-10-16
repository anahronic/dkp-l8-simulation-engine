"""Versioned source corpus of the Keeper (GPT КТ8 TZ §10).

Builds fragments from pinned sources only:
  protocol / code / glossary   the lab corpus snapshot lab/corpus/world-<commit> (checked against CORPUS.json)
  lab_doc / finding / question / module   lab documents, findings with their classification, author questions with their
                                status, module manifests (from the same engine commit)
Every fragment carries fid, cite (the id the model must use), document_id, section, heading, source_type, status,
revision, sha256 of its text, url and the text.  An optional Russian translation directory adds `search_ru` to protocol
fragments: a retrieval key only, never shown and never passed to the model (the translation is not published).

Usage: python -m keeper.corpus build OUT_DIR [--ru DIR] [--site WEBSITE_DIR]
Writes OUT_DIR/corpus-<version>.jsonl and OUT_DIR/corpus-<version>.json (manifest; with --site, the comparison of
sections with the site's protocol pages).
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from typing import Any, Dict, Iterator, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB = os.path.join(ROOT, "lab")
SITE = "https://dikenocracy.com"
MAX_CHARS = 1800
UNMATCHED: List[str] = []                                 # corpus headings without an id on the site page
HEAD = re.compile(r"^(#{2,6})\s+(.*\S)\s*$")
NUM = re.compile(r"^(?:Section\s+)?((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+(.*)$")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(heading: str, seen: Dict[str, int]) -> str:
    """Heading id as on the site's protocol pages: "4.1 Cycle Structure" -> "41-cycle-structure"; hyphens collapsed, at
    most 60 characters, a repeated id gets -1, -2 ... (``seen`` is per page)."""
    s = re.sub(r"[^a-z0-9_\- ]", "", heading.lower())                 # non-ASCII (subscripts, Greek) dropped
    s = "-".join(s.split())[:60].strip("-")                              # space runs -> one hyphen; "--" kept
    n = seen.get(s, 0)
    seen[s] = n + 1
    return f"{s}-{n}" if n else s


def short_name(doc_id: str) -> str:
    """DKP-5-WORK-CYCLE-001 -> WORK-CYCLE; DKP-4-CRISIS-001-PATCH -> CRISIS-PATCH."""
    m = re.fullmatch(r"DKP-\d+-(.+?)-\d{3}(?:-(.+))?", doc_id)
    return m.group(1) + ("-" + m.group(2) if m and m.group(2) else "") if m else doc_id


def sections(text: str) -> Iterator[Dict[str, Any]]:
    """Split Markdown at headings; yield {level, heading, number, body} (front matter and title block kept as §0-)."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    cur = {"level": 1, "heading": "", "number": "", "lines": []}
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            if "".join(cur["lines"]).strip():
                yield cur
            heading = m.group(2).strip().strip("*").strip()
            n = NUM.match(heading)
            cur = {"level": len(m.group(1)), "heading": heading, "number": n.group(1) if n else "", "lines": []}
        elif not re.fullmatch(r"-{3,}\s*", line):
            cur["lines"].append(line)
    if "".join(cur["lines"]).strip():
        yield cur


def parts(body: str) -> List[str]:
    """Paragraph-aligned pieces of at most MAX_CHARS (a longer single paragraph stays whole)."""
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", body.strip()):
        if cur and len(cur) + len(para) + 2 > MAX_CHARS:
            out.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    return out + ([cur] if cur else [])


def norm(heading: str) -> str:
    h = unicodedata.normalize("NFKC", html.unescape(re.sub(r"<[^>]+>", "", heading)))
    return " ".join(h.replace("*", "").replace("\\", "").lower().split())


def site_anchors(website: Optional[str], page: Optional[str]) -> Optional[Dict[str, List[str]]]:
    """Heading text -> ids in page order, read from the site's own protocol page (the ids are not re-derived)."""
    path = os.path.join(website, "pages", "protocols", f"{page}.html") if website and page else ""
    if not path or not os.path.exists(path):
        return None
    out: Dict[str, List[str]] = {}
    for m in re.finditer(r'<h[1-6][^>]*\bid="([^"]+)"[^>]*>(.*?)</h[1-6]>', open(path, encoding="utf-8").read(), re.S):
        out.setdefault(norm(m.group(2)), []).append(m.group(1))
    return out


def protocol_fragments(snapshot: str, manifest: Dict[str, Any], ru_dir: Optional[str],
                       website: Optional[str] = None) -> List[Dict[str, Any]]:
    frags = []
    for rel, meta in sorted(manifest["files"].items()):
        path = os.path.join(snapshot, rel)
        raw = open(path, encoding="utf-8").read()
        assert sha(raw) == meta["sha256"] or hashlib.sha256(open(path, "rb").read()).hexdigest() == meta["sha256"], rel
        name = os.path.basename(rel)[:-3]
        if name == "DKP-5-TRANSPORT-001-APPENDIX-A":                # its own page name on the site
            doc_id, kind, page = name, "protocol", "appendix-a-design-rationale-safeguards-normative"
        elif name.startswith("DKP-"):
            doc_id, kind, page = name, "protocol", name.lower()
        elif name.startswith("CODE"):
            doc_id, kind, page = "CODE-OF-PLANETARY-SYNERGY", "code", "code-of-planetary-synergy"
        else:
            doc_id, kind, page = "GLOSSARY", "glossary", None
        cite_doc = {"protocol": short_name(doc_id), "code": "CODE", "glossary": "GLOSSARY"}[kind]
        ru = ru_sections(os.path.join(ru_dir, (page or "glossary") + ".md")) if ru_dir else {}
        seen: Dict[str, int] = {}
        anchors: Dict[str, int] = {}
        site = site_anchors(website, page)
        for sec in sections(raw):
            body = "\n".join(sec["lines"]).strip()
            if site is None:                                  # no site page given: derived id, unchecked
                anchor = slug(sec["heading"], anchors) if sec["heading"] else ""
            else:                                             # the page's own id for this heading, or none
                ids = site.get(norm(sec["heading"])) if sec["heading"] else None
                anchor = ids.pop(0) if ids else ""
                if sec["heading"] and not anchor:
                    UNMATCHED.append(f"{doc_id}: {sec['heading']}")
            label = f"§{sec['number']}" if sec["number"] else (sec["heading"] or "title")
            for i, piece in enumerate(parts(body)):
                key = f"{label}" + (f" ({i + 1})" if i else "")
                seen[key] = seen.get(key, 0) + 1
                if seen[key] > 1:
                    key += f" [{seen[key]}]"
                frag = {"fid": f"{doc_id}#{key}", "cite": f"{cite_doc} {label}", "document_id": doc_id, "section": label,
                        "heading": sec["heading"], "source_type": kind, "status": "normative" if kind != "glossary" else "explanatory",
                        "revision": {"world_commit": manifest["commit"], "file": rel, "file_sha256": meta["sha256"]},
                        "url": (f"{SITE}/pages/protocols/{page}.html" + (f"#{anchor}" if anchor else ""))
                        if page else None,
                        "text": (f"{sec['heading']}\n\n" if sec["heading"] and i == 0 else "") + piece}
                if sec["number"] and sec["number"] in ru and i == 0:
                    frag["search_ru"] = ru[sec["number"]]
                frag["sha256"] = sha(frag["text"])
                frags.append(frag)
    return frags


def ru_sections(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    return {s["number"]: (s["heading"] + "\n" + "\n".join(s["lines"]))[:4000]
            for s in sections(open(path, encoding="utf-8").read()) if s["number"]}


def lab_fragments() -> List[Dict[str, Any]]:
    frags: List[Dict[str, Any]] = []
    commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def add(fid, cite, doc, section, heading, kind, status, text, url=None):
        frags.append({"fid": fid, "cite": cite, "document_id": doc, "section": section, "heading": heading,
                      "source_type": kind, "status": status, "revision": {"engine_commit": commit}, "url": url,
                      "text": text, "sha256": sha(text)})
    for doc in ("README", "MODEL_GAPS", "ARCHITECTURE_DEVIATION", "CALIBRATION_MAP", "LAB_ERRORS"):
        raw = open(os.path.join(LAB, doc + ".md"), encoding="utf-8").read()
        for j, sec in enumerate(sections(raw)):
            for i, piece in enumerate(parts("\n".join(sec["lines"]))):
                label = sec["heading"] or "intro"
                add(f"LAB-{doc}#{j}.{i}", f"LAB {doc} {j}" + (f".{i}" if i else ""), f"LAB-{doc}", label, sec["heading"],
                    "lab_doc", "lab documentation", (f"{sec['heading']}\n\n" if i == 0 and sec["heading"] else "") + piece)
    fdir = os.path.join(LAB, "findings")
    for name in sorted(os.listdir(fdir)):
        if not re.fullmatch(r"F-\d{3}\.md", name):
            continue
        raw = open(os.path.join(fdir, name), encoding="utf-8").read()
        title = raw.splitlines()[0].lstrip("# ").strip()
        cls = re.search(r"\*\*Classification:\*\*\s*([^\n]+)", raw)
        fid = name[:-3]
        for i, piece in enumerate(parts(raw)):
            add(f"{fid}#{i}", fid, fid, f"part {i + 1}", title, "finding",
                cls.group(1).strip()[:200] if cls else "unclassified", piece)
    qs = json.load(open(os.path.join(LAB, "registry", "open_questions.json"), encoding="utf-8"))
    for q in qs.get("questions", []):
        text = json.dumps({k: v for k, v in q.items() if k not in ("quotes",)}, ensure_ascii=False, indent=1)
        for i, piece in enumerate(parts(text)):
            add(f"{q['id']}#{i}", q["id"], q["id"], f"part {i + 1}", q.get("title") or q.get("question", "")[:120],
                "question", q.get("status", "open"), piece)
    sys.path.insert(0, ROOT)
    from lab.modules import MODULES
    for m in MODULES.values():
        man = m.manifest()
        text = json.dumps({k: man.get(k) for k in ("id", "version", "title", "summary", "protocols", "scenario")
                           if man.get(k) is not None}, ensure_ascii=False)
        inputs = {k: (v.get("label") or {}).get("en") for k, v in (man.get("inputs") or {}).items()} if isinstance(man.get("inputs"), dict) else {}
        add(f"MODULE-{m.id}", f"module {m.id}", f"MODULE-{m.id}", "manifest", man.get("title", {}).get("en", m.id), "module",
            "lab model (not a norm)", text + ("\ninputs: " + json.dumps(inputs, ensure_ascii=False) if inputs else ""))
    return frags


def compare_site(frags: List[Dict[str, Any]], website: str) -> Dict[str, Any]:
    """The pinned corpus against the site's protocol pages: pages missing, corpus headings without an id on the page,
    site pages without a corpus document.  Text differences inside sections are not compared here."""
    pages = os.path.join(website, "pages", "protocols")
    have = {f["url"].split("/pages/protocols/")[1].split("#")[0] for f in frags if f.get("url")}
    commit = subprocess.run(["git", "-C", website, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    return {"site_commit": commit, "pages_checked": len(have),
            "missing_pages": sorted(p for p in have if not os.path.exists(os.path.join(pages, p))),
            "headings_without_site_id": list(UNMATCHED),
            "site_pages_without_corpus_document": sorted(p for p in os.listdir(pages) if p.endswith(".html") and p not in have)}


def build(out_dir: str, ru_dir: Optional[str] = None, website: Optional[str] = None) -> Dict[str, Any]:
    cman = json.load(open(os.path.join(LAB, "corpus", "CORPUS.json"), encoding="utf-8"))
    snapshot = os.path.join(LAB, "corpus", f"world-{cman['commit'][:7]}")
    UNMATCHED.clear()
    frags = protocol_fragments(snapshot, cman, ru_dir, website) + lab_fragments()
    body = "".join(json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n" for f in frags)
    version = sha(body)[:12]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"corpus-{version}.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    counts: Dict[str, int] = {}
    for f in frags:
        counts[f["source_type"]] = counts.get(f["source_type"], 0) + 1
    manifest = {"schema": "dkp-keeper-corpus/1", "version": version, "fragments": len(frags), "by_type": counts,
                "jsonl_sha256": sha(body), "world_commit": cman["commit"],
                "engine_commit": frags[-1]["revision"]["engine_commit"],
                "ru_search_keys": sum(1 for f in frags if "search_ru" in f),
                "site_comparison": compare_site(frags, website) if website else None}
    with open(os.path.join(out_dir, f"corpus-{version}.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    return manifest


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] != "build" or len(a) < 2:
        sys.exit(__doc__)
    opt = {a[i]: a[i + 1] for i in range(2, len(a) - 1, 2)}
    man = build(a[1], opt.get("--ru"), opt.get("--site"))
    print(json.dumps({k: v for k, v in man.items() if k != "site_comparison"}, ensure_ascii=False))
    if man["site_comparison"]:
        sc = man["site_comparison"]
        print(json.dumps({k: (v if isinstance(v, int) else (len(v), v[:6])) for k, v in sc.items()}, ensure_ascii=False))
