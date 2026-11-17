"""Builds the author's review workbook (A6): one static HTML page with every provision reading and open question,
current registry status, the latest author decision with its history, references, and client-side search/filters.

    python -m lab.tools.review_queue [out.html]      (default: simulation/outputs/review/index.html, not published)
Decisions are recorded with `python -m lab.tools.review_record` (append-only); this page only displays them.
"""
import html
import json
import pathlib
import sys
from collections import defaultdict

from lab.tools.review_record import LOG, digest, items

out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("simulation/outputs/review/index.html")
history = defaultdict(list)
if LOG.exists():
    for line in LOG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            e = json.loads(line)
            history[e["id"]].append(e)
rows, counts = [], defaultdict(int)
for iid, (kind, doc, item) in sorted(items().items()):
    h = history.get(iid, [])
    last = h[-1] if h else None
    stale = bool(last and last["item_sha256"] != digest(item))
    status = item.get("interpretation_status") or item.get("status")
    decision = (last["decision"] + (" (stale: item changed)" if stale else "")) if last else "not reviewed"
    counts[f"{kind}:{'reviewed' if last and not stale else 'pending'}"] += 1
    text = item.get("interpretation") or item.get("title") or ""
    refs = item.get("documents") or item.get("open_questions") or []
    hist = "<br>".join(html.escape(f"{e['time']} {e['decision']} by {e['reviewer']}: {e['note']}") for e in h) or "—"
    rows.append(f"<tr data-kind='{kind}' data-state='{'pending' if not last or stale else 'reviewed'}'>"
                f"<td><b>{html.escape(iid)}</b><br><small>{html.escape(doc or '')} §{html.escape(str(item.get('section', '')))}</small></td>"
                f"<td>{html.escape(item.get('title', ''))}<blockquote>{html.escape(item.get('quote', '') or '')}</blockquote></td>"
                f"<td>{html.escape(text)}</td><td>{html.escape(str(status))}<br><small>{html.escape(str(item.get('decision_status', '')))}</small></td>"
                f"<td>{html.escape(decision)}<br><small>{hist}</small></td><td><small>{html.escape(json.dumps(refs, ensure_ascii=False))}</small></td></tr>")
page = f"""<!doctype html><meta charset="utf-8"><title>Lab author review (A6)</title>
<style>body{{font:14px system-ui;margin:16px}}table{{border-collapse:collapse;width:100%}}td{{border:1px solid #ccc;padding:6px;vertical-align:top}}
blockquote{{margin:4px 0;color:#555;white-space:pre-wrap}}#q{{width:40ch}}</style>
<h1>Lab author review (A6)</h1><p>{html.escape(json.dumps(dict(counts)))} — record decisions with
<code>python -m lab.tools.review_record &lt;id&gt; &lt;decision&gt; --reviewer NAME --note TEXT</code>. Nothing here approves anything.</p>
<p><input id=q placeholder="Search id, text, document"> <select id=k><option value="">all</option><option>provision</option><option>question</option></select>
<select id=s><option value="">any state</option><option>pending</option><option>reviewed</option></select> <span id=n></span></p>
<table><thead><tr><td>Id</td><td>Provision / question</td><td>Draft reading</td><td>Registry status</td><td>Author decision / history</td><td>References</td></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<script>const f=()=>{{const q=document.getElementById('q').value.toLowerCase(),k=document.getElementById('k').value,s=document.getElementById('s').value;let n=0;
for(const r of document.querySelectorAll('tbody tr')){{const ok=(!q||r.textContent.toLowerCase().includes(q))&&(!k||r.dataset.kind===k)&&(!s||r.dataset.state===s);r.hidden=!ok;n+=ok}}
document.getElementById('n').textContent=n+' shown'}};for(const id of ['q','k','s'])document.getElementById(id).oninput=f;f();</script>"""
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(page, encoding="utf-8", newline="\n")
print(f"review workbook: {len(rows)} items -> {out} {dict(counts)}")
