---
id: "DKP-1-JUSTICE-001"
slug: dkp-1-justice-001
kind: protocol
last_updated: 2026-10-04
---

### Justice Function Protocol (δίκη)

------------------------------------------------------------------------

### 1. Purpose

The Justice Function Protocol defines how measured impact and attributed responsibility are transformed into deterministic justice outcomes within the Dikenocracy system.

Justice is defined here as a function, not an institution, authority, ideology, or moral judgment.

This protocol computes consequences, not punishment. It produces binding justice outputs, not discretionary decisions.

------------------------------------------------------------------------

### 2. System Position

This protocol operates:

- above DKP-1-IMPACT-001 (Impact Measurement Protocol),
- above DKP-1-IDENTITY-001 (Identity & Subject Protocol),
- below all economic, governance, security, and enforcement protocols.

This protocol SHALL NOT access raw Physical Truth Layer data directly.

All inputs MUST be imported exclusively from:

- DKP-1-IMPACT-001 outputs, and
- DKP-1-IDENTITY-001 attribution bindings.

------------------------------------------------------------------------

### 3. Core Inputs

For each evaluated action instance A, the protocol receives:

#### 3.1 Impact Set

A channel-separated, unaggregated set of impact outputs produced by DKP-1-IMPACT-001:

- Iᵢ — impact magnitude per channel,
- Bᵢ — reference bounds,
- Rᵢ — reversibility flags,
- Xᵢ — externality flags,
- Uᵢ — uncertainty envelopes.

------------------------------------------------------------------------

#### 3.2 Responsibility Binding

From DKP-1-IDENTITY-001:

- identified Subject(s),
- responsibility weights per Subject,
- temporal persistence indicators,
- cascading and higher-order attribution flags.

------------------------------------------------------------------------

#### 3.3 Normative Constraints

From DKP-1-AXIOMS-001:

- priority ordering of protected domains,
- absolute prohibitions,
- minimum survival and stability thresholds,
- non-negotiable axiom-defined bounds.

------------------------------------------------------------------------

### 4. Justice Definition

Justice (δίκη) is defined as a deterministic mapping:

`δίκη : (Impact, Responsibility, Axioms) → Consequence Vector C`

The output vector C SHALL contain no:

- moral language,
- intent interpretation,
- discretionary adjustment,
- subjective weighting.

Justice outcomes are computed, not interpreted.

------------------------------------------------------------------------

### 5. Justice Evaluation Domains

Justice SHALL be evaluated independently across the following domains:

1.  Restitution Domain
2.  Restriction Domain
3.  Isolation Domain
4.  Exclusion Domain

No domain SHALL be skipped if its triggering conditions are met.

------------------------------------------------------------------------

### 6. Restitution Domain

Restitution applies when:

- impact is reversible (Rᵢ = True), and
- mitigation or repair is physically possible.

The protocol SHALL compute:

- required mitigation scope,
- proportional restitution obligations per Subject,
- time constraints for restitution completion.

Restitution SHALL NOT exceed the measurable impact.

------------------------------------------------------------------------

### 7. Restriction Domain

Restriction applies when:

- impact exceeds axiom-defined safe margins, or
- repeated harmful behavior is detected, or
- mitigation capacity is insufficient.

Restrictions MAY include:

- limitation of action scope,
- throttling of resource access,
- enforced participation constraints.

Restrictions MUST be:

- proportional,
- reversible where physically possible,
- continuously re-evaluated.

Restrictions SHALL NOT be used as punitive measures and SHALL exist solely to prevent further harm.

------------------------------------------------------------------------

### 8. Isolation Domain

Isolation applies when:

- impact is irreversible (Rᵢ = False), or
- externality exposure is critical (Xᵢ = True), or
- Subject behavior presents systemic risk.

Isolation SHALL be:

- functional, not punitive,
- targeted strictly at harm prevention,
- minimal in scope.

Physical isolation SHALL be treated as a last-resort measure.

Isolation SHALL prioritize functional separation over physical confinement whenever technically feasible.

------------------------------------------------------------------------

### 9. Exclusion Domain

Exclusion applies when:

- a Subject persistently violates non-negotiable axioms, or
- mitigation and isolation fail to contain harm, or
- the Subject refuses or is incapable of compliance.

Exclusion SHALL result in:

- removal from system participation,
- loss of system-provided privileges,
- persistence of historical attribution.

Exclusion SHALL NOT entail physical harm, lethal deprivation, or conditions leading to loss of life.

All exclusion outcomes MUST remain consistent with Axiom A1 (Preservation of Life) as defined in DKP-1-AXIOMS-001.

Exclusion terminates system participation and access to system-provided privileges only. It SHALL NOT authorize annihilation, abandonment, or indirect lethal exposure.

Exclusion is not annihilation and does not imply moral condemnation.

------------------------------------------------------------------------

### 10. Proportionality and Distribution

Where multiple Subjects are responsible:

- consequences SHALL be distributed proportionally to responsibility weights,
- no Subject SHALL absorb consequences exceeding its attributable contribution.

Collective responsibility SHALL NOT nullify individual accountability.

------------------------------------------------------------------------

### 11. Temporal Re-evaluation

Justice outputs SHALL be re-evaluated when:

- impact metrics change,
- mitigation occurs,
- new data reduces uncertainty,
- system boundary conditions shift.

Justice is adaptive but not discretionary.

Re-evaluation frequency SHALL be bounded by Physical Truth Layer temporal guarantees.

Justice outputs MAY NOT be re-evaluated more frequently than the minimum TTL (Time-To-Live) of the underlying Physical Truth Layer data that produced the original impact measurements.

Any attempt to trigger re-evaluation using incomplete, stale, or selectively withheld data SHALL be treated as continued exposure to prior justice outcomes.

Adaptive justice SHALL NOT permit oscillatory relief, temporary concealment, or strategic delay of mitigation.

#### Dispute Exception Clause

The TTL-based re-evaluation constraint applies to scheduled periodic re-evaluation cycles only.

Dispute events triggered by new admissible data under Section 7.1 of DKP-1-EPISTEMIC-BOUNDARIES-001 SHALL NOT be rejected solely on TTL grounds.

A valid Dispute Event SHALL initiate re-evaluation regardless of elapsed time since last evaluation, provided:

a\) the dispute introduces new admissible data not present in prior evaluation,

b\) the dispute alleges oracle inconsistency, scope violation, or measurement integrity challenge,

c\) the dispute is submitted through DKP-4-ERROR-001 appeal mechanism.

This exception preserves Core Invariant \#3: No DKP output is final; all outputs remain subject to re-evaluation.

------------------------------------------------------------------------

### 12. No-Exemption Invariant

No Subject SHALL be exempt from justice outcomes based on:

- status,
- authority,
- jurisdiction,
- ideology,
- cultural justification.

Justice follows causality, not hierarchy.

------------------------------------------------------------------------

### 13. Cross-Layer Isolation

This protocol SHALL NOT:

- reinterpret impact metrics,
- alter identity attribution,
- override axiom-defined bounds,
- inject policy, governance, or moral reasoning.

Violation constitutes a critical architectural breach.

------------------------------------------------------------------------

### 14. Transparency and Auditability

All justice computations MUST be:

- deterministic,
- reproducible,
- fully auditable,
- traceable to protocol inputs.

Opaque, discretionary, or non-reproducible justice mechanisms are forbidden.

------------------------------------------------------------------------

### 15. Protocol Finality

This protocol is changed only through the controlled procedure of DKP-4-UPGRADE-001: proposal, simulation under DKP-8-SIMULATION-001, audit under DKP-8-AUDIT-001, acceptance conditions, activation window and rollback.

Any modification requires:

- a new protocol identifier,
- explicit incompatibility declaration,
- full-system simulation under DKP-8-SIMULATION.

Presentation-only corrections that do not change normative content are not Upgrades (DKP-4-UPGRADE-001 §3); they are recorded only by the "Last updated" date of this document.

Edition integrity: the SHA-256 digest of the canonical source of each published edition is listed in `SHA256SUMS.txt` of the canonical repository (github.com/anahronic/World).

------------------------------------------------------------------------

END OF PROTOCOL
