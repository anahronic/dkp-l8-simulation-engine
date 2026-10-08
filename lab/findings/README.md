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
| [F-011](F-011.md) | EXIT §6 delays exit 'to prevent cascading instability'; SCOPE §9 forbids it; SCOPE §2 resolves | CONFIRMED_FINDING (resolved by priority) | Q-031 |
| [F-012](F-012.md) | Exit in a crisis: SCOPE permits a temporary suspension that EXIT forbids | INTERPRETATION_GAP (authority difference) | Q-032 |
| [F-013](F-013.md) | A failing external oracle mirror: no conflict between INTEROP and CRISIS | IMPLEMENTATION_BUG (fixed) | Q-033 withdrawn |
| [F-014](F-014.md) | No Calibration Bundle exists; by SIMULATION §4 protocols lacking one are non-enforceable | CONFIRMED_FINDING (systemic blocker) | Q-034, Q-035 |
| [F-015](F-015.md) | TRANSPORT has PTL quantify "systemic insurance exposure"; ORACLE limits PTL to physical state | CONFIRMED_FINDING (narrowed) | Q-036 |
| [F-016](F-016.md) | PPDI "forced bodily contact between non-consenting passengers": measurement undefined | INTERPRETATION_GAP | Q-037 withdrawn |
| [F-017](F-017.md) | TIME §9: the test vector for 2000-01-01 contradicts §5 | CONFIRMED_FINDING | Q-002 |
| [F-018](F-018.md) | ORACLE §11: nothing says what happens when the 14-day arbitration window ends | CONFIRMED_FINDING | Q-005, Q-010 |
| [F-019](F-019.md) | An asset revocation has two dispute clocks: from execution (ASSETS) and from recording (ERROR) | INTERPRETATION_GAP | Q-038 |
| [F-020](F-020.md) | UPGRADE defers the post-crisis stabilization period to AUDIT, which does not define it | CONFIRMED_FINDING | Q-039 |
| [F-021](F-021.md) | INTERNAL-SEC: re-entry after a state expires to S0 is not defined | INTERPRETATION_GAP | Q-040 |
| [F-022](F-022.md) | AXIOMS §8 ratifies by '67% of active validating nodes, as defined in Appendix A.5' — A.5 defines none | CONFIRMED_FINDING | Q-041 |
| [F-023](F-023.md) | Axiom A1 'minimum required conditions': the authority is named, the admissibility test is not | CONFIRMED_FINDING | Q-042 |
| [F-024](F-024.md) | AXIOMS §5: rules 2 and 4 differ when every action violates an axiom | INTERPRETATION_GAP | Q-043 |
| [F-025](F-025.md) | Axiom A4 says SHOULD while every axiom is a constraint | INTERPRETATION_GAP | Q-044 |
| [F-026](F-026.md) | PRIVACY §6: aggregate statistics of the absolute privacy domains — allowed or not | INTERPRETATION_GAP | Q-045 |
| [F-027](F-027.md) | Mercy: 'suspended for 180 days' against 'SHALL NOT persist beyond explicitly declared Crisis Scope' | INTERPRETATION_GAP | Q-046 |
| [F-028](F-028.md) | Human validators: in the Code's oracle stack (A.2), excluded by ORACLE | INTERPRETATION_GAP | Q-047 |
| [F-029](F-029.md) | B(t) < B_min activates 'all Kill Switches': no target, no release | CONFIRMED_FINDING | Q-048 |
| [F-030](F-030.md) | A.1a System Failure: which violation counts; the manual control has no bounds | CONFIRMED_FINDING | Q-049 |
| [F-031](F-031.md) | 'Connect' under Code A.5 and the phases of INTEGRATION | INTERPRETATION_GAP (authority difference) | Q-050 |
| [F-032](F-032.md) | Council of Crisis Mercy and the SCOPE S3 ban on discretionary emergency authorities | INTERPRETATION_GAP | Q-051 |
| [F-033](F-033.md) | Code §18.1 passivity rating against LABOR §9.1 (no compulsion) and PRIVACY §10 (no social credit scoring) | INTERPRETATION_GAP | Q-052 |
| [F-034](F-034.md) | Code §14.2 'grows exponentially (Cost = Votes²)' | CONFIRMED_FINDING (wording) | Q-053 |
| [F-035](F-035.md) | SCOPE §8: the Scope Audit has a trigger but no procedure, end or object of confirmation | CONFIRMED_FINDING | Q-054 |
| [F-036](F-036.md) | Code A.1 activates the Kill Switches on B(t); ORACLE §12 forbids B(t) to trigger enforcement without an L8 bundle | CONFIRMED_FINDING (contradiction) | Q-055 |
| [F-037](F-037.md) | Cognitive and cultural impact channels must come from the PTL, which excludes cultural harm | INTERPRETATION_GAP | Q-056 |
| [F-038](F-038.md) | AUDIT §4 names D2 'Consistency or Integrity Anomaly'; §7 names D2 'Constraint Violation' | CONFIRMED_FINDING (wording) | Q-057 |

Changes made by the verification of 2026-10-07: F-001 and F-013 were the lab's errors (fixed,
counterexamples kept); F-006, F-010 and F-016 were reclassified from contradictions to
interpretation gaps; F-015 was narrowed to the part the texts confirm; F-017 (formerly only an open
question) and F-018 (a reference FAIL without a record) were added.

Changes made after the review of 2026-10-08: F-012 reclassified as an authority difference (the
requirements are compatible); F-011 and F-018 no longer produce reference FAILs (F-011: the SCOPE §2
resolution is applied; F-018: the arbitration window is measured, the state after it is UNKNOWN); F-006
checks JUSTICE literally on the received flag, with separate checks for the hand-over (IMPACT §11) and the
flag contract; F-023 narrowed (CRISIS §12.2 names the authority).  Every finding now has a kind;
contradictions carry a structured analysis and missing definitions the searches made
(`lab/registry/verifications.json`).
