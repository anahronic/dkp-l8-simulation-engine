# Findings

Problems the lab found in the protocols or in their interaction.  Each finding has a
minimal reproduction (`F-nnn.request.json`, run with `python -m lab run`), the exact chain
of provisions with registry ids and verbatim quotes, and options for the author.

The lab does not fix a finding by changing the meaning of a protocol.  Alternative readings
appear only as separately named hypotheses (`source: alternative`) for comparison; the
default inputs keep the lab's declared reading.  Every finding stays `UNRESOLVED` until the
author decides; `tests/lab/test_findings.py` keeps the documented numbers as regressions.

| Id | Title | Kind | Status |
|---|---|---|---|
| [F-001](F-001.md) | A synchronous change of physical state triggers no re-evaluation | protocol/model gap | UNRESOLVED |
| [F-002](F-002.md) | Asynchronous sampling turns a real change into a divergence | protocol/model gap | UNRESOLVED |
| [F-003](F-003.md) | A class slower than its TTL keeps dependent outputs suspended | protocol/model gap | UNRESOLVED |
| [F-004](F-004.md) | FINANCE §11.2(b) points to a section of ERROR that does not exist | corpus defect | UNRESOLVED |
