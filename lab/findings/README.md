# Findings

Problems the lab found in the protocols, in their interaction, or in its own readings.  Each finding
has a minimal reproduction (`F-nnn.request.json`, run with `python -m lab run`) where a computation
shows it, the provisions with verbatim quotes, and options for the author where a decision is needed.

**Semantic verification gate.**  A finding gets its class only after the provisions involved have
been read against the literal pinned text; the records, with quotes checked verbatim by
`tests/lab/test_semantic_gate.py`, are in `lab/registry/verifications.json`.  A Codex draft is never
a source.  Classes:

| Class | Meaning |
|---|---|
| CONFIRMED_FINDING | the literal texts produce the defect (contradiction, broken reference, wrong number, missing definition) without any lab reading |
| INTERPRETATION_GAP | the result depends on a reading or a definition the corpus does not give; no text is contradicted |
| IMPLEMENTATION_BUG | the lab's own reading or code produced the reported defect; fixed in the lab, kept as a regression |
| UNVERIFIED_FINDING | recorded but not yet verified (none at present; never reported as a protocol defect) |

The lab does not fix a finding by changing the meaning of a protocol.  Alternative readings appear
only as separately named inputs (`source: alternative`); defaults follow the text in force.  Author
decisions stay open (`lab/registry/open_questions.json`); `tests/lab/test_findings.py` keeps the
documented numbers as regressions.

| Id | Title | Class | Question |
|---|---|---|---|
| [F-001](F-001.md) | A synchronous change of physical state triggered no re-evaluation | IMPLEMENTATION_BUG (fixed) | Q-006 withdrawn |
| [F-002](F-002.md) | Asynchronous sampling turns a real change into a divergence | INTERPRETATION_GAP | Q-004 |
| [F-003](F-003.md) | A class slower than its TTL keeps dependent outputs suspended | INTERPRETATION_GAP | Q-003, Q-008 |
| [F-004](F-004.md) | FINANCE §11.2(b) points to a section of ERROR that does not exist | CONFIRMED_FINDING | Q-009 |
| [F-005](F-005.md) | IMPACT: the §13 example disagrees with §5; Bᵢ scale or level | CONFIRMED_FINDING (arithmetic) | Q-023 |
| [F-006](F-006.md) | The polarity of Rᵢ is not fixed by IMPACT | INTERPRETATION_GAP | Q-022 |
| [F-007](F-007.md) | N_eff and N_eff_min decide the null-output state but are defined nowhere | CONFIRMED_FINDING | Q-026 |
| [F-008](F-008.md) | CRISIS allows extending oracle TTLs; ORACLE forbids it | CONFIRMED_FINDING | Q-027 |
| [F-009](F-009.md) | CRISIS §12.3 cites "Section 8 (Non-Precedent Rule)"; the rule is in §6 | CONFIRMED_FINDING | Q-028 |
| [F-010](F-010.md) | DEFENSE escalates at D3; CRISIS enters on "sustained" D3 of undefined duration | INTERPRETATION_GAP (missing L8 parameter) | Q-029, Q-030 withdrawn |
| [F-011](F-011.md) | EXIT delays exit for stability; SCOPE forbids delaying exit for stability | CONFIRMED_FINDING | Q-031 |
| [F-012](F-012.md) | EXIT: exit is never suspended; SCOPE: it may be suspended within Crisis Scope | CONFIRMED_FINDING | Q-032 |
| [F-013](F-013.md) | A failing external oracle mirror: no conflict between INTEROP and CRISIS | IMPLEMENTATION_BUG (fixed) | Q-033 withdrawn |
| [F-014](F-014.md) | No Calibration Bundle exists; by SIMULATION §4 protocols lacking one are non-enforceable | CONFIRMED_FINDING (systemic blocker) | Q-034, Q-035 |
| [F-015](F-015.md) | TRANSPORT has PTL quantify "systemic insurance exposure"; ORACLE limits PTL to physical state | CONFIRMED_FINDING (narrowed) | Q-036 |
| [F-016](F-016.md) | PPDI "forced bodily contact between non-consenting passengers": measurement undefined | INTERPRETATION_GAP | Q-037 withdrawn |
| [F-017](F-017.md) | TIME §9: the test vector for 2000-01-01 contradicts §5 | CONFIRMED_FINDING | Q-002 |
| [F-018](F-018.md) | ORACLE §11: nothing says what happens when the 14-day arbitration window ends | CONFIRMED_FINDING | Q-005, Q-010 |
| [F-019](F-019.md) | An asset revocation has two dispute clocks: from execution (ASSETS) and from recording (ERROR) | INTERPRETATION_GAP | Q-038 |
| [F-020](F-020.md) | UPGRADE defers the post-crisis stabilization period to AUDIT, which does not define it | CONFIRMED_FINDING | Q-039 |

Changes made by the verification of 2026-10-07: F-001 and F-013 were the lab's errors (fixed,
counterexamples kept); F-006, F-010 and F-016 were reclassified from contradictions to
interpretation gaps; F-015 was narrowed to the part the texts confirm; F-017 (formerly only an open
question) and F-018 (a reference FAIL without a record) were added.
