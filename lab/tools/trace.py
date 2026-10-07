#!/usr/bin/env python3
"""
Traceability: requirement -> implementation -> test -> gap -> open question, and the
execution matrix of the lab specification (stages A-G, scenarios S-LAB-01..10).

    python -m lab.tools.trace            write lab/registry/traceability.json and lab/TRACEABILITY.md
    python -m lab.tools.trace --check    exit 1 if the written files are not current

Observed statuses come from running every module's reference examples (inputs without
deliberate ``faults``).  A FAIL there means the example case violates the provision (for
example an understaffed roster), not that a protocol is wrong.  Examples with deliberate
faults are counterexamples: they show that a check detects a violation.

Coverage counts IMPLEMENTED and PARTIAL provisions; it measures whether a check exists, not
whether a protocol holds.  Every interpretation is a draft until reviewed
(``interpretation_status``); provisions needing a human or author decision are UNRESOLVED.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from typing import Any, Dict, List

from lab.core import verification
from lab.core.registry import catalog
from lab.tools.check_registry import REQ_DIR, check_file, check_open_questions, load_catalog

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(LAB, "registry")
OUT_JSON = os.path.join(REG, "traceability.json")
OUT_MD = os.path.join(LAB, "TRACEABILITY.md")
STATUSES = ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE", "UNCOVERED")
REGISTRABLE = ("protocol", "addendum", "appendix", "codex")


def _load(name: str) -> Any:
    with open(os.path.join(REG, name), encoding="utf-8") as f:
        return json.load(f)


def registry() -> Dict[str, Dict[str, Any]]:
    out = {}
    for name in sorted(os.listdir(REQ_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(REQ_DIR, name), encoding="utf-8") as f:
                reg = json.load(f)
            out[reg["doc_id"]] = reg
    return out


def observe() -> Dict[str, Any]:
    """Run every module example; collect statuses per requirement."""
    from lab.modules import MODULES
    evidence: Dict[str, Counter] = {}
    detected: Dict[str, List[str]] = {}
    alternative: Dict[str, Counter] = {}
    noncompliant: Dict[str, List[str]] = {}
    ref_fails: Dict[str, List[str]] = {}
    runs = []
    for m in MODULES.values():
        for name, inp in sorted(m.examples().items()):
            res = m.evaluate(m.validate(inp))
            kind = m.example_kind(name)
            runs.append({"module": m.id, "example": name, "kind": kind})
            for c in res.checks:
                if kind == "counterexample":
                    if c.status == "FAIL":
                        detected.setdefault(c.requirement_id, []).append(f"{m.id}:{name}")
                elif kind == "alternative":
                    alternative.setdefault(c.requirement_id, Counter())[c.status] += 1
                elif kind == "noncompliant":
                    if c.status == "FAIL":
                        noncompliant.setdefault(c.requirement_id, []).append(f"{m.id}:{name}")
                else:
                    evidence.setdefault(c.requirement_id, Counter())[c.status] += 1
                    if c.status == "FAIL":
                        ref_fails.setdefault(c.requirement_id, []).append(f"{m.id}:{name}")
    return {"evidence": evidence, "detected": detected, "alternative": alternative, "noncompliant": noncompliant,
            "reference_fails": ref_fails, "runs": runs}


def summary_status(counts: Counter) -> str:
    if not counts:
        return "UNCOVERED"
    for s in ("FAIL", "UNKNOWN", "PASS"):
        if counts.get(s):
            return s
    return "NOT_APPLICABLE"


def build() -> Dict[str, Any]:
    from lab.modules import MODULES
    cat = catalog()
    docs = {d["id"]: d for d in cat["documents"]}
    regs = registry()
    questions = _load("open_questions.json")["questions"]
    stages = _load("tz_stages.json")
    obs = observe()
    hyps = {m.id: [h["id"] for h in m.hypotheses] for m in MODULES.values()}
    ver = verification.load()
    read = verification.verified_provisions(ver, regs)

    rows = []
    for doc_id, reg in regs.items():
        for r in reg["requirements"]:
            impl = r["implementation"]
            counts = obs["evidence"].get(r["id"], Counter())
            rows.append({
                "id": r["id"], "document": doc_id, "section": r["section"], "kind": r["kind"],
                "checkable": r["checkable"], "coverage": r["coverage"],
                "module": impl["module"] if impl else None, "check": impl["check"] if impl else None,
                "tests": r["tests"], "gap": r["gap"],
                "also_checked_by": [f"{a['module']} · {a['check']}" for a in impl.get("also", [])] if impl else [],
                "hypotheses": sorted({h for mid in ([impl["module"]] + [a["module"] for a in impl.get("also", [])])
                                      for h in hyps.get(mid, [])}) if impl else [],
                "interpretation_status": r["interpretation_status"], "decision_status": r["decision_status"],
                "open_questions": r["open_questions"],
                "observed": {s: counts.get(s, 0) for s in STATUSES[:4]},
                "status": summary_status(counts),
                "counterexample_detected_by": sorted(set(obs["detected"].get(r["id"], []))),
                "under_alternative_readings": dict(obs["alternative"].get(r["id"], {})),
                "violated_by_noncompliant_case": sorted(set(obs["noncompliant"].get(r["id"], []))),
                "text_verification": read.get(r["id"], []),
                "open_point": r.get("open_point"),
            })
    by_doc: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_doc.setdefault(row["document"], []).append(row)

    def doc_stats(ids: List[str]) -> Dict[str, Any]:
        sel = [row for d in ids for row in by_doc.get(d, [])]
        covered = sum(1 for x in sel if x["coverage"] in ("IMPLEMENTED", "PARTIAL"))
        st = Counter(x["status"] for x in sel)
        resolvable = [x for x in sel if x["checkable"] != "no" and x["decision_status"] == "NONE_IDENTIFIED"]
        return {
            "documents": len(ids),
            "registered": sum(1 for d in ids if d in regs),
            "not_registered": [d for d in ids if d not in regs],
            "provisions": len(sel), "covered": covered,
            "covered_percent": round(100 * covered / len(sel), 1) if sel else 0.0,
            "statuses": {s: st.get(s, 0) for s in STATUSES},
            "resolvable": len(resolvable),
            "resolvable_uncovered": sum(1 for x in resolvable if x["coverage"] not in ("IMPLEMENTED", "PARTIAL")),
            "unresolved_decisions": sum(1 for x in sel if x["decision_status"] == "UNRESOLVED"),
        }

    registrable = [d for d, v in docs.items() if v["kind"] in REGISTRABLE]
    reg_problems: List[str] = []
    seen: Dict[str, str] = {}
    cat_docs = load_catalog()
    for name in sorted(os.listdir(REQ_DIR)):
        if name.endswith(".json"):
            reg_problems += check_file(os.path.join(REQ_DIR, name), cat_docs, seen)
    reg_problems += check_open_questions(seen)

    def criterion(check: str, stage_docs: List[str]) -> bool:
        if check.startswith("manual:"):
            return check == "manual:done"
        if check == "corpus_pinned":
            return True                                  # catalog() refuses an unpinned corpus
        if check == "catalog_35":
            return cat["counts"]["protocols"] == 35
        if check == "all_documents_registered":
            return all(d in regs for d in registrable)
        if check == "registry_valid":
            return not reg_problems
        if check == "references_checked":
            return "section_references" in cat
        if check == "interpretations_reviewed":           # a human review; TEXT_VERIFIED does not count
            return all(x["interpretation_status"] in ("REVIEWED", "CONFIRMED_BY_AUTHOR") for x in rows)
        if check == "stage_coverage":
            s = doc_stats(stage_docs)
            return s["registered"] == s["documents"] and s["resolvable_uncovered"] == 0
        if check == "all_resolvable_covered":
            s = doc_stats(registrable)
            return s["registered"] == s["documents"] and s["resolvable_uncovered"] == 0
        raise ValueError(check)

    stage_rows = []
    for st in stages["stages"]:
        st_docs = registrable if st["documents"] == "ALL_REGISTRABLE" else st["documents"]
        crit = [{**c, "met": criterion(c["check"], st_docs)} for c in st["criteria"]]
        stats = doc_stats(st_docs) if st_docs else None
        if all(c["met"] for c in crit):
            status = "DONE"
        elif any(c["met"] for c in crit) or (stats and stats["covered"]):
            status = "PARTIAL"
        else:
            status = "NOT STARTED"
        stage_rows.append({"id": st["id"], "title": st["title"], "status": status, "criteria": crit, "stats": stats})

    module_docs: Dict[str, set] = {}
    for row in rows:
        for mid in ([row["module"]] if row["module"] else []) + [a.split(" · ")[0] for a in row["also_checked_by"]]:
            module_docs.setdefault(mid, set()).add(row["document"])
    scen_rows = []
    for sc in stages["scenarios"]:
        m = sc["module"]
        if not m:
            status, missing = "NOT STARTED", sc["documents"]
        else:
            missing = [d for d in sc["documents"] if d not in module_docs.get(m, set())]
            status = "DONE" if not missing else "PARTIAL"
        scen_rows.append({**sc, "status": status, "documents_without_checks": missing})

    total = doc_stats(registrable)
    gate = semantic_gate(ver, obs, questions)
    return {
        "schema": "dkp-lab-traceability/1",
        "corpus": cat["corpus"]["commit"],
        "registry_problems": len(reg_problems),
        "modules": sorted(MODULES),
        "runs": obs["runs"],
        "totals": total,
        "stages": stage_rows,
        "scenarios": scen_rows,
        "open_questions": [{"id": q["id"], "title": q["title"], "status": q["status"], "category": q["category"]}
                           for q in questions],
        "semantic_gate": gate,
        "unresolved_decomposition": decomposition(rows),
        "requirements": sorted(rows, key=lambda x: (x["document"], x["id"])),
    }


def finding_title(fid: str) -> str:
    with open(os.path.join(verification.FINDINGS_DIR, f"{fid}.md"), encoding="utf-8") as f:
        first = f.readline().strip()
    return first.split("—", 1)[1].strip() if "—" in first else first.lstrip("# ")


def semantic_gate(ver: Dict[str, Any], obs: Dict[str, Any], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Findings by class, every FAIL of a reference or noncompliant example against its verification record."""
    cls = verification.classifications(ver)
    findings = [{"id": fid, "title": finding_title(fid), "classification": c} for fid, c in cls.items()]
    by_req = {r["requirement"]: r for r in ver["reference_fails"]}
    fails = []
    for rid, runs in sorted(obs["reference_fails"].items()):
        rec = by_req.get(rid)
        fails.append({"requirement": rid, "runs": sorted(set(runs)),
                      "origin": rec["origin"] if rec else "UNVERIFIED", "finding": rec.get("finding") if rec else None})
    nc_rec = {r["requirement"]: r for r in ver["noncompliant_cases"]}
    nc = [{"requirement": rid, "runs": sorted(set(runs)), "verified": rid in nc_rec}
          for rid, runs in sorted(obs["noncompliant"].items())]
    qc = Counter((q["status"], q["category"]) for q in questions)
    return {
        "verifier": ver["verifier"], "date": ver["date"],
        "findings": findings,
        "finding_counts": {c: sum(1 for f in findings if f["classification"] == c) for c in verification.FINDING_CLASSES},
        "reference_fails": fails,
        "unverified_reference_fails": [f["requirement"] for f in fails if f["origin"] == "UNVERIFIED"],
        "noncompliant_fails": nc,
        "unverified_noncompliant_fails": [x["requirement"] for x in nc if not x["verified"]],
        "questions": [{"status": s, "category": c, "count": n} for (s, c), n in sorted(qc.items())],
    }


def decomposition(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """UNRESOLVED provisions by the origin of the open point (text-verified or Codex draft)."""
    cls = verification.load_classification() or {"items": {}, "provenance": {}}
    unres = [r for r in rows if r["decision_status"] == "UNRESOLVED"]
    by = Counter()
    per_doc: Dict[str, Counter] = {}
    for r in unres:
        op = r["open_point"]
        key = (op["origin"], op["source"]) if op else ("pending", "none")
        by[key] += 1
        per_doc.setdefault(r["document"], Counter())[op["origin"] if op else "pending"] += 1
    draft_rows = {r["id"] for r in unres if (r["open_point"] or {}).get("source") == "codex_draft"}
    candidates = sorted(rid for rid, it in cls["items"].items() if it["author_question_candidate"] and rid in draft_rows)
    origins = list(verification.ORIGINS) + ["pending"]
    return {
        "unresolved": len(unres),
        "by_origin": [{"origin": o, "text_verified": by.get((o, "text_verified"), 0), "codex_draft": by.get((o, "codex_draft"), 0),
                       "total": by.get((o, "text_verified"), 0) + by.get((o, "codex_draft"), 0) + by.get((o, "none"), 0)}
                      for o in origins],
        "draft_author_question_candidates": len(candidates),
        "draft_provenance": cls.get("provenance", {}),
        "per_document": {d: {o: c.get(o, 0) for o in origins} for d, c in sorted(per_doc.items())},
    }


def markdown(t: Dict[str, Any]) -> str:
    L = ["# Traceability and execution matrix", "",
         "Generated by `python -m lab.tools.trace` — do not edit.  Corpus World "
         f"`{t['corpus'][:12]}`; modules: {', '.join(t['modules'])}.", "",
         "*Covered* = a lab check exists (IMPLEMENTED or PARTIAL); it does not mean that a protocol holds.",
         "Statuses aggregate the modules' reference examples (text in force, compliant case, no deliberate",
         "faults): FAIL if any run failed, else UNKNOWN, else PASS, else NOT_APPLICABLE; UNCOVERED = no check.",
         "Examples under alternative readings, examples that break a provision on purpose (noncompliant",
         "cases, e.g. an understaffed roster) and counterexamples with deliberate faults are reported apart.",
         "Every reference FAIL passes the semantic verification gate (`lab/registry/verifications.json`).",
         "Interpretations are machine drafts; TEXT_VERIFIED means the wording was read against the literal",
         "text by the lab (not a human review).  Author questions: `lab/registry/open_questions.json`.", "",
         "## Stages of the specification", "",
         "| Stage | Status | Documents registered | Provisions | Covered | PASS | FAIL | UNKNOWN | N/A | UNCOVERED | Resolvable, uncovered | Unresolved decisions |",
         "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in t["stages"]:
        x = s["stats"]
        if x:
            st = x["statuses"]
            L.append(f"| {s['id']}. {s['title']} | {s['status']} | {x['registered']}/{x['documents']} | {x['provisions']} | "
                     f"{x['covered']} ({x['covered_percent']} %) | {st['PASS']} | {st['FAIL']} | {st['UNKNOWN']} | "
                     f"{st['NOT_APPLICABLE']} | {st['UNCOVERED']} | {x['resolvable_uncovered']} | {x['unresolved_decisions']} |")
        else:
            L.append(f"| {s['id']}. {s['title']} | {s['status']} | — | | | | | | | | | |")
    x = t["totals"]
    st = x["statuses"]
    L += [f"| **All registrable documents** | | {x['registered']}/{x['documents']} | {x['provisions']} | "
          f"{x['covered']} ({x['covered_percent']} %) | {st['PASS']} | {st['FAIL']} | {st['UNKNOWN']} | "
          f"{st['NOT_APPLICABLE']} | {st['UNCOVERED']} | {x['resolvable_uncovered']} | {x['unresolved_decisions']} |", "",
          "### Stage criteria", ""]
    for s in t["stages"]:
        for c in s["criteria"]:
            note = f" — {c['note']}" if c.get("note") else ""
            L.append(f"- {s['id']} / {c['id']} {'met' if c['met'] else '**not met**'}: {c['text']}{note}")
        if s["stats"] and s["stats"]["not_registered"]:
            L.append(f"  - not registered: {', '.join(s['stats']['not_registered'])}")
    L += ["", "## Composite scenarios", "", "| Scenario | Status | Module | Documents without checks |", "|---|---|---|---|"]
    for sc in t["scenarios"]:
        L.append(f"| {sc['id']} {sc['title']} | {sc['status']} | {sc['module'] or '—'} | "
                 f"{', '.join(sc['documents_without_checks']) or '—'} |")
    g = t["semantic_gate"]
    L += ["", "## Semantic verification gate", "",
          f"Verifier: {g['verifier']} ({g['date']}).", "",
          "| Class | Findings |", "|---|---:|"]
    L += [f"| {c} | {n} |" for c, n in g["finding_counts"].items()]
    L += ["", "| Finding | Class | Title |", "|---|---|---|"]
    L += [f"| {f['id']} | {f['classification']} | {f['title']} |" for f in g["findings"]]
    L += ["", "FAILs of reference examples and their verified origin:", "",
          "| Requirement | Origin | Finding | Runs |", "|---|---|---|---|"]
    L += [f"| {x['requirement']} | {x['origin']} | {x['finding'] or '—'} | {', '.join(x['runs'])} |" for x in g["reference_fails"]]
    L += ["", "FAILs of noncompliant cases (the input breaks the provision on purpose):", "",
          "| Requirement | Verified | Runs |", "|---|---|---|"]
    L += [f"| {x['requirement']} | {'yes' if x['verified'] else '**no**'} | {', '.join(x['runs'])} |" for x in g["noncompliant_fails"]]
    L += ["", f"Unverified reference FAILs: {', '.join(g['unverified_reference_fails']) or 'none'}; "
              f"unverified noncompliant FAILs: {', '.join(g['unverified_noncompliant_fails']) or 'none'}."]
    d = t["unresolved_decomposition"]
    pv = d["draft_provenance"]
    L += ["", "## Origin of open points (UNRESOLVED provisions)", "",
          f"{d['unresolved']} provisions have an open point.  Origin: text-verified where an author question was "
          "verified against the literal text; otherwise a Codex draft "
          f"({pv.get('model', '—')}, {pv.get('date', '—')}; DRAFT_UNREVIEWED; not in the draft (opened later): "
          f"{', '.join(pv.get('unclassified_open_points', [])) or 'none'}).  Only normative_ambiguity and "
          "architecture_definition can become author questions, and only after verification.", "",
          "| Origin | Text-verified | Codex draft | Total |", "|---|---:|---:|---:|"]
    L += [f"| {x['origin']} | {x['text_verified']} | {x['codex_draft']} | {x['total']} |" for x in d["by_origin"]]
    L += ["", f"Draft author-question candidates (unverified, not questions): {d['draft_author_question_candidates']}."]
    L += ["", "## Open questions (author decisions)", ""]
    L += [f"- {q['id']} [{q['status']}, {q['category']}] {q['title']}" for q in t["open_questions"] if q["status"] != "WITHDRAWN"]
    L += ["", "Withdrawn after verification (not author decisions):", ""]
    L += [f"- {q['id']} [{q['category']}] {q['title']}" for q in t["open_questions"] if q["status"] == "WITHDRAWN"]
    L += ["", "## Documents", "", "| Document | Provisions | Covered | PASS | FAIL | UNKNOWN | N/A | UNCOVERED | Unresolved |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    by = {}
    for r in t["requirements"]:
        by.setdefault(r["document"], []).append(r)
    for d, rs in sorted(by.items()):
        c = Counter(r["status"] for r in rs)
        cov = sum(1 for r in rs if r["coverage"] in ("IMPLEMENTED", "PARTIAL"))
        unres = sum(1 for r in rs if r["decision_status"] == "UNRESOLVED")
        L.append(f"| {d} | {len(rs)} | {cov} | {c['PASS']} | {c['FAIL']} | {c['UNKNOWN']} | {c['NOT_APPLICABLE']} | "
                 f"{c['UNCOVERED']} | {unres} |")
    L += ["", "## Covered provisions", "",
          "| Requirement | Coverage | Module · check | Status | Counterexample detected | Open questions |",
          "|---|---|---|---|---|---|"]
    for r in t["requirements"]:
        if r["module"]:
            L.append(f"| {r['id']} | {r['coverage']} | {r['module']} · {r['check']} | {r['status']} | "
                     f"{'yes' if r['counterexample_detected_by'] else '—'} | {', '.join(r['open_questions']) or '—'} |")
    L += ["", "The full map (every provision, its gap and tests) is `lab/registry/traceability.json`.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    t = build()
    js = json.dumps(t, indent=1, ensure_ascii=False) + "\n"
    md = markdown(t)
    if check:
        cur = [open(p, encoding="utf-8").read() if os.path.exists(p) else "" for p in (OUT_JSON, OUT_MD)]
        ok = cur == [js, md]
        print("traceability current" if ok else "traceability out of date: run python -m lab.tools.trace")
        return 0 if ok else 1
    for p, text in ((OUT_JSON, js), (OUT_MD, md)):
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    x = t["totals"]
    print(f"{x['registered']}/{x['documents']} documents registered, {x['provisions']} provisions, "
          f"covered {x['covered']} ({x['covered_percent']} %), statuses {x['statuses']}")
    for s in t["stages"]:
        print(f"  {s['id']}: {s['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
