"""Builds the author's review workbook (A6): one static HTML page with every provision reading and open question,
current registry status, the latest author decision with its history, references, and client-side search/filters.

    python -m lab.tools.review_queue [out.html]      (default: simulation/outputs/review/index.html, not published)
Decisions are recorded with `python -m lab.tools.review_record` (append-only); this page only displays them.

Filters: text, kind, review state, protocol, "depends on" (items of documents that normatively depend on the chosen
document, plus items that reference it) and an ordering by criticality.  Criticality is an ordering aid only, never a
judgement of content:
  provision = 2 x open questions it references + 2 if its decision is UNRESOLVED + 1 if it is not fully checkable
              + (documents that depend on its document) / 5, rounded down
  question  = 2 x provisions it blocks (listed in either direction) + documents it names
"""
import html
import json
import pathlib
import sys
from collections import defaultdict

from lab.tools.review_record import LOG, digest, items

CRITERIA = ("provision: 2 x referenced open questions + 2 if UNRESOLVED + 1 if not fully checkable + dependent "
            "documents / 5; question: 2 x provisions it blocks + documents it names")


def dependency_maps():
    from dkp8.enforcement import dependents, documents, graph
    g = graph()
    return g, {d: len(dependents(d)) for d in documents()}


def criticality(kind, item, iid, blocked_by_q, dependents_count, doc):
    if kind == "question":
        blocked = set(item.get("requirements") or []) | blocked_by_q.get(iid, set())
        return 2 * len(blocked) + len(item.get("documents") or [])
    return (2 * len(item.get("open_questions") or []) + (2 if item.get("decision_status") == "UNRESOLVED" else 0)
            + (1 if item.get("checkable") != "yes" else 0) + dependents_count.get(doc, 0) // 5)


def build(out):
    history = defaultdict(list)
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                history[e["id"]].append(e)
    all_items = items()
    graph, dependents_count = dependency_maps()
    blocked_by_q = defaultdict(set)
    for iid, (kind, doc, item) in all_items.items():
        if kind == "provision":
            for q in item.get("open_questions") or []:
                blocked_by_q[q].add(iid)
    rows, counts, docs = [], defaultdict(int), set()
    for iid, (kind, doc, item) in sorted(all_items.items()):
        h = history.get(iid, [])
        last = h[-1] if h else None
        stale = bool(last and last["item_sha256"] != digest(item))
        status = item.get("interpretation_status") or item.get("status")
        decision = (last["decision"] + (" (stale: item changed)" if stale else "")) if last else "not reviewed"
        counts[f"{kind}:{'reviewed' if last and not stale else 'pending'}"] += 1
        text = item.get("interpretation") or item.get("title") or ""
        refs = item.get("documents") or item.get("open_questions") or []
        own_docs = [doc] if doc else list(item.get("documents") or [])
        docs.update(d for d in own_docs if d)
        depends = sorted({t for d in own_docs for t in graph.get(d, [])}
                         | {r for r in refs if isinstance(r, str) and r.startswith(("DKP-", "CODE-"))})
        crit = criticality(kind, item, iid, blocked_by_q, dependents_count, doc)
        hist = "<br>".join(html.escape(f"{e['time']} {e['decision']} by {e['reviewer']}: {e['note']}") for e in h) or "—"
        rows.append(f"<tr data-kind='{kind}' data-state='{'pending' if not last or stale else 'reviewed'}' "
                    f"data-docs='{html.escape(' '.join(own_docs))}' data-deps='{html.escape(' '.join(depends))}' "
                    f"data-crit='{crit}' data-order='{len(rows)}'>"
                    f"<td><b>{html.escape(iid)}</b><br><small>{html.escape(doc or '')} §{html.escape(str(item.get('section', '')))}</small>"
                    f"<br><small>criticality {crit}</small></td>"
                    f"<td>{html.escape(item.get('title', ''))}<blockquote>{html.escape(item.get('quote', '') or '')}</blockquote></td>"
                    f"<td>{html.escape(text)}</td><td>{html.escape(str(status))}<br><small>{html.escape(str(item.get('decision_status', '')))}</small></td>"
                    f"<td>{html.escape(decision)}<br><small>{hist}</small></td><td><small>{html.escape(json.dumps(refs, ensure_ascii=False))}</small></td></tr>")
    options = "".join(f"<option>{html.escape(d)}</option>" for d in sorted(docs))
    page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lab author review (A6)</title>
<style>body{{font:14px system-ui;margin:16px}}table{{border-collapse:collapse;width:100%}}td{{border:1px solid #ccc;padding:6px;vertical-align:top;overflow-wrap:anywhere}}
blockquote{{margin:4px 0;color:#555;white-space:pre-wrap}}#q{{width:min(40ch,100%)}}.bar{{display:flex;flex-wrap:wrap;gap:6px;align-items:center}}
select,input{{max-width:100%}}@media(max-width:700px){{td{{display:block}}thead{{display:none}}tr{{display:block;border-bottom:2px solid #999;margin-bottom:8px}}}}</style>
<h1>Lab author review (A6)</h1><p>{html.escape(json.dumps(dict(counts)))} — record decisions with
<code>python -m lab.tools.review_record &lt;id&gt; &lt;decision&gt; --reviewer NAME --note TEXT</code>. Nothing here approves anything.</p>
<p class=bar><input id=q placeholder="Search id, text, document"> <select id=k><option value="">all kinds</option><option>provision</option><option>question</option></select>
<select id=s><option value="">any state</option><option>pending</option><option>reviewed</option></select>
<select id=d><option value="">any protocol</option>{options}</select>
<select id=p><option value="">depends on: any</option>{options}</select>
<select id=o><option value="">registry order</option><option value="crit">criticality, high first</option></select> <span id=n></span></p>
<p><small>Criticality orders the work only ({html.escape(CRITERIA)}).</small></p>
<table><thead><tr><td>Id</td><td>Provision / question</td><td>Draft reading</td><td>Registry status</td><td>Author decision / history</td><td>References</td></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<script>const $=id=>document.getElementById(id),body=document.querySelector('tbody'),all=[...body.rows];
const f=()=>{{const q=$('q').value.toLowerCase(),k=$('k').value,s=$('s').value,d=$('d').value,p=$('p').value,o=$('o').value;let n=0;
const sorted=o==='crit'?[...all].sort((a,b)=>b.dataset.crit-a.dataset.crit||a.dataset.order-b.dataset.order):all;
for(const r of sorted){{body.append(r);const ok=(!q||r.textContent.toLowerCase().includes(q))&&(!k||r.dataset.kind===k)&&(!s||r.dataset.state===s)
&&(!d||r.dataset.docs.split(' ').includes(d))&&(!p||r.dataset.deps.split(' ').includes(p));r.hidden=!ok;n+=ok}}
$('n').textContent=n+' shown'}};for(const id of ['q','k','s','d','p','o'])$(id).oninput=f;f();</script>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    return len(rows), dict(counts)


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("simulation/outputs/review/index.html")
    n, counts = build(target)
    print(f"review workbook: {n} items -> {target} {counts}")
