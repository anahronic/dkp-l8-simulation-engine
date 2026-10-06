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
| [F-005](F-005.md) | IMPACT: Bᵢ used as a scale, a limit crossed without a flag, §13 example disagrees with §5 | protocol defect / missing definition | UNRESOLVED |
| [F-006](F-006.md) | Rᵢ means "irreversible" in IMPACT and "reversible" in JUSTICE | cross-protocol defect | UNRESOLVED |
| [F-007](F-007.md) | N_eff and N_eff_min decide the null-output state but are defined nowhere | missing definition | UNRESOLVED |
| [F-008](F-008.md) | CRISIS allows extending oracle TTLs; ORACLE forbids it | contradiction between protocols | UNRESOLVED |
| [F-009](F-009.md) | CRISIS §12.3 cites "Section 8 (Non-Precedent Rule)"; the rule is in §6 | corpus defect | UNRESOLVED |
| [F-011](F-011.md) | EXIT delays exit for stability; SCOPE forbids delaying exit for stability | contradiction between protocols | UNRESOLVED |
| [F-012](F-012.md) | EXIT: exit is never suspended; SCOPE: it may be suspended within Crisis Scope | contradiction between protocols | UNRESOLVED |
| [F-013](F-013.md) | A failing external oracle mirror: INTEROP forbids a crisis, CRISIS requires one | contradiction between protocols | UNRESOLVED |
| [F-014](F-014.md) | No Calibration Bundle exists; by SIMULATION §4 every protocol that needs one is non-enforceable | systemic precondition | UNRESOLVED |
| [F-010](F-010.md) | DEFENSE escalates at D3; CRISIS enters only on "sustained" D3 of undefined duration | rule interaction / missing parameter | UNRESOLVED |
