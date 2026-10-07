#!/usr/bin/env python3
"""
Calibration map — the decomposition of the systemic blocker F-014.

    python -m lab.tools.calibration_map           write lab/CALIBRATION_MAP.md
    python -m lab.tools.calibration_map --check   exit 1 if it is not current or a quote is not verbatim

Sources: lab/registry/calibration_map.json (hand-made, every quote verbatim) and the registry.  The
numeric constants written into normative texts are found by pattern in the registry's verbatim quotes.
The lab invents no Calibration Bundle and no value.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List

from lab.core.registry import catalog
from lab.tools.check_registry import REQ_DIR, doc_text, load_catalog, normalize

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(LAB, "registry", "calibration_map.json")
OUT_MD = os.path.join(LAB, "CALIBRATION_MAP.md")
UNIT = (r"%|percent|DTI-Days?|days?|hours?|h\b|minutes?|years?|ppm|°C|seconds?|times|x\b")
NUMBER = re.compile(r"(?<![\w.§-])(\d+(?:[.,]\d+)?)\s*(?:" + UNIT + r")|\((\d+)\)\s*(?:" + UNIT + r")", re.I)


def load() -> Dict[str, Any]:
    with open(SRC, encoding="utf-8") as f:
        return json.load(f)


def quotes(m: Dict[str, Any]):
    for sec in ("bundle_required", "deferred_to_l8", "missing_values", "external_dependencies"):
        for rec in m[sec]:
            yield sec, rec
    yield "simulation_position", m["simulation_position"]["quote"]


def quote_problems(m: Dict[str, Any]) -> List[str]:
    cat = load_catalog()
    texts: Dict[str, str] = {}
    out = []
    for sec, q in quotes(m):
        t = texts.setdefault(q["doc"], normalize(doc_text(cat[q["doc"]])))
        if normalize(q["text"]) not in t:
            out.append(f"{sec}: quote not found in {q['doc']}: {q['text'][:80]!r}")
    return out


def input_problems(m: Dict[str, Any]) -> List[str]:
    """Every 'module.input' named as a lab stand-in exists."""
    from lab.modules import MODULES
    out = []
    for sec in ("deferred_to_l8", "missing_values"):
        for rec in m[sec]:
            for ref in re.findall(r"\b([a-z_]+)\.([a-z_0-9]+)", rec.get("lab_input") or ""):
                mod = ref[0]
                if mod in MODULES and ref[1] != "bundle" and ref[1] not in MODULES[mod].inputs:
                    out.append(f"{sec}: {mod}.{ref[1]} is not an input")
                if mod not in MODULES:
                    out.append(f"{sec}: unknown module {mod}")
    return out


def constants() -> List[Dict[str, Any]]:
    """Numbers with a unit written into the verbatim quotes of registered provisions."""
    out = []
    for name in sorted(os.listdir(REQ_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(REQ_DIR, name), encoding="utf-8") as f:
            reg = json.load(f)
        for r in reg["requirements"]:
            q = normalize(r["quote"])
            hits = [mm.group(0) for mm in NUMBER.finditer(q)]
            if hits:
                out.append({"id": r["id"], "document": reg["doc_id"], "values": hits, "quote": q})
    return out


def protocol_table(m: Dict[str, Any], consts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cat = catalog()
    pos = m["simulation_position"]
    ncon = Counter(c["document"] for c in consts)
    ndef = Counter(r["doc"] for r in m["deferred_to_l8"])
    nmis = Counter(r["doc"] for r in m["missing_values"])
    rows = []
    for d in cat["documents"]:
        if d["kind"] not in ("protocol", "addendum", "appendix", "codex"):
            continue
        did = d["id"]
        if did == "DKP-8-SIMULATION-001":
            cat_, status = "calibration_protocol", "the calibration protocol itself"
        elif d["kind"] == "codex":
            cat_, status = "not_a_protocol", ("not a protocol (§4 speaks of protocols); Main Equation parameters change "
                                              "only via UPGRADE + SIMULATION")
        elif did in pos["upstream"]:
            cat_, status = "undetermined", ("§4 read literally: NON-ENFORCEABLE, but §2 places SIMULATION downstream of "
                                            "it — undetermined (Q-035)")
        else:
            cat_, status = "non_enforceable", "NON-ENFORCEABLE as written (SIMULATION §4): no bundle exists"
        rows.append({"document": did, "kind": d["kind"],
                     "position": "upstream of SIMULATION" if did in pos["upstream"] else
                                 "listed downstream" if did in pos["listed_downstream"] else "not listed",
                     "own_clause": m["own_clause"].get(did, "—"),
                     "constants_in_text": ncon.get(did, 0), "deferred_to_l8": ndef.get(did, 0),
                     "missing_values": nmis.get(did, 0), "category": cat_, "literal_status": status})
    return rows


def markdown(m: Dict[str, Any]) -> str:
    consts = constants()
    rows = protocol_table(m, consts)
    L = ["# Calibration map (decomposition of F-014)", "",
         "Generated by `python -m lab.tools.calibration_map` from `lab/registry/calibration_map.json` and the registry — "
         "do not edit.  " + m["rule"], "",
         f"Verifier: {m['verifier']}", "",
         "## 1. Provisions that literally require a Calibration Bundle or L8 calibration", "",
         "| Document | § | Applies to | Text |", "|---|---|---|---|"]
    L += [f"| {r['doc']} | {r['at']} | {r['scope']} | \"{r['text']}\" |" for r in m["bundle_required"]]
    L += ["", "No Calibration Bundle exists in the pinned corpus.", "",
          "## 2. Numeric values already written into the texts", "",
          f"{len(consts)} registered provisions state a number with a unit (found by pattern in their verbatim quotes; "
          "the Code of Planetary Synergy is included).  Whether such constants bind without a bundle is open "
          "question Q-035.", "",
          "| Requirement | Values | Quote |", "|---|---|---|"]
    for c in consts:
        q = c["quote"] if len(c["quote"]) <= 160 else c["quote"][:157] + "…"
        L.append(f"| {c['id']} | {', '.join(c['values'])} | {q.replace('|', '¦')} |")
    L += ["", "## 3. Parameters the texts assign to L8", "",
          "| Parameter | Document | § | Text | Lab stand-in (declared, source `missing`) |", "|---|---|---|---|---|"]
    L += [f"| {r['parameter']} | {r['doc']} | {r['at']} | \"{r['text']}\"{' — ' + r['note'] if r.get('note') else ''} | "
          f"{r['lab_input'] or '—'} |" for r in m["deferred_to_l8"]]
    L += ["", "## 4. Values needed but neither written nor assigned to L8", "",
          "| Value | Document | § | Text | Origin | Lab stand-in |", "|---|---|---|---|---|---|"]
    L += [f"| {r['value']} | {r['doc']} | {r['at']} | \"{r['text']}\" | {r['origin']}"
          f"{' (' + r['finding'] + ')' if r.get('finding') else ''} | {r['lab_input'] or '—'} |" for r in m["missing_values"]]
    L += ["", "External documents referenced but absent: " +
          "; ".join(f"{r['document']} (cited by {r['doc']})" for r in m["external_dependencies"]) + ".", "",
          "## 5. Which documents are non-enforceable without a bundle", "",
          "SIMULATION §2 lists the protocols downstream of it and the three it is downstream of; §4 speaks of every "
          "protocol.  Four L5 protocols and ORACLE's B(t) also say so in their own text.", "",
          "| Document | SIMULATION §2 position | Own clause | Constants in text | Deferred to L8 | Missing values | Status as written |",
          "|---|---|---|---:|---:|---:|---|"]
    L += [f"| {r['document']} | {r['position']} | {r['own_clause']} | {r['constants_in_text']} | {r['deferred_to_l8']} | "
          f"{r['missing_values']} | {r['literal_status']} |" for r in rows]
    st = Counter(r["category"] for r in rows)
    label = {"non_enforceable": "non-enforceable as written", "undetermined": "upstream of SIMULATION, undetermined (Q-035)",
             "not_a_protocol": "not a protocol", "calibration_protocol": "the calibration protocol itself"}
    L += ["", "Summary: " + "; ".join(f"{st[k]} {label[k]}" for k in label if st.get(k)) + ".  Of the non-enforceable ones, "
          "HABITAT, INFO, EDU and CULTURE say so in their own text as well.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    m = load()
    problems = quote_problems(m) + input_problems(m)
    for p in problems:
        print(p)
    md = markdown(m)
    if check:
        cur = open(OUT_MD, encoding="utf-8").read() if os.path.exists(OUT_MD) else ""
        ok = cur == md and not problems
        print("calibration map current" if ok else "calibration map out of date or invalid")
        return 0 if ok else 1
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write(md)
    print(f"written {OUT_MD}; {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
