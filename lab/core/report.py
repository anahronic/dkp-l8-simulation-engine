"""
Human-readable reports (Markdown and HTML) of a lab result document.

All user-provided or computed text is escaped in HTML; nothing from the input
is interpreted as markup.
"""

from __future__ import annotations

import html
import json
from typing import Any, Dict, List

STATUS_RU = {"PASS": "выполнено", "FAIL": "нарушено", "UNKNOWN": "не определено", "NOT_APPLICABLE": "неприменимо"}


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


def markdown(doc: Dict[str, Any], lang: str = "en") -> str:
    m = doc["module"]
    L: List[str] = [f"# {m['title'][lang]}", ""]
    L.append(f"- module: `{m['id']}` {m['version']}; documents: {', '.join(m['protocols'])}")
    L.append(f"- input_id: `{doc['input_id']}`")
    L.append(f"- result_id: `{doc['result_id']}`")
    L.append(f"- lab {doc['identity']['lab_version']}, engine {doc['identity']['engine_version']}, "
             f"corpus World `{doc['identity']['corpus']['commit'][:12]}`")
    L.append("- operational_use: **false** — research output, not an admission under DKP-8-SIMULATION-001 §8–§9")
    if doc.get("causal_note"):
        L += ["", f"> {doc['causal_note'][lang]}"]
    comp = doc["comparison"]
    if comp["metrics"]:
        L += ["", "## Variants" if lang == "en" else "## Варианты", "",
              "| variant | " + " | ".join(comp["metrics"]) + " | PASS | FAIL | UNKNOWN |",
              "|---|" + "---:|" * (len(comp["metrics"]) + 3)]
        for row in comp["rows"]:
            L.append(f"| {row['variant']} | " + " | ".join(_fmt(row["metrics"].get(k)) for k in comp["metrics"])
                     + f" | {row['checks']['PASS']} | {row['checks']['FAIL']} | {row['checks']['UNKNOWN']} |")
        L += ["", comp["note"][lang]]
    for name, v in doc["variants"].items():
        L += ["", f"## {name}", "", v["summary"]["sentence"][lang], ""]
        for e in v["explain"]:
            L.append(f"- {e[lang]}")
        L += ["", "| requirement | status | explanation |", "|---|---|---|"]
        for c in v["checks"]:
            st = c["status"] if lang == "en" else f"{c['status']} ({STATUS_RU[c['status']]})"
            expl = c["explanation"] + (f" — {c['applicability']}" if c.get("applicability") else "")
            L.append(f"| {c['requirement_id']} | {st} | {expl.replace('|', '/')} |")
        if v["summary"]["uncovered"]:
            L += ["", ("Not covered by this experiment: " if lang == "en" else "Вне охвата эксперимента: ")
                  + ", ".join(v["summary"]["uncovered"])]
        L += ["", "Resolved input:" if lang == "en" else "Разрешённый вход:", "", "```json",
              json.dumps(v["resolved_input"], indent=1, sort_keys=True, ensure_ascii=False), "```"]
    if doc.get("hypotheses"):
        L += ["", "## Hypotheses" if lang == "en" else "## Гипотезы", ""]
        for h in doc["hypotheses"]:
            L.append(f"- **{h['id']}** ({h['source']}): {h['text'][lang]}")
    return "\n".join(L) + "\n"


def html_page(doc: Dict[str, Any], lang: str = "en") -> str:
    """Self-contained HTML rendering of the Markdown report (escaped, pre-wrapped)."""
    body = html.escape(markdown(doc, lang))
    title = html.escape(doc["module"]["title"][lang])
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{title}</title>"
            "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:60rem;margin:1rem auto;padding:0 1rem;"
            "background:#fff;color:#111}pre{white-space:pre-wrap}@media(prefers-color-scheme:dark){body{"
            "background:#111;color:#eee}}</style></head><body><pre>" + body + "</pre></body></html>\n")
