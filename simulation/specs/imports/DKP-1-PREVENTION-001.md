---
id: "DKP-1-PREVENTION-001"
slug: dkp-1-prevention-001
kind: protocol
last_updated: 2026-10-04
meta: "Layer: L1–L2 Boundary · Depends on: DKP-0-ORACLE-001, DKP-1-IMPACT-001, DKP-1-IDENTITY-001 · Compatibility: Confirmed · Override: Not permitted"
---

### Preventive Impact Attribution Protocol

------------------------------------------------------------------------

### 1. Purpose

This protocol defines how preventive actions are transformed into measurable, attributable, and non-manipulable impact contributions.

Preventive contribution is recognized only through measurable suppression of activated risk processes, not through absence of realized harm and not through hypothetical projections.

------------------------------------------------------------------------

### 2. System Position

PTL → Impact → Prevention Attribution → Identity → Labor / Compensation

------------------------------------------------------------------------

### 3. Core Definitions

#### 3.1 Protected Zone Z

Physically bounded domain of evaluation.

------------------------------------------------------------------------

#### 3.2 Risk Channel Rcᵢ

PTL-derived measurable risk exposure channel.

------------------------------------------------------------------------

#### 3.3 Threat Activation Signal (TAₖ)

TAₖ valid ⇔ confirmations ≥ 2 independent oracle classes

Let:

Δ_oracle = max(intensity) − min(intensity)

Two regimes:

#### 3.3.1 Consistent regime

Δ_oracle ≤ ε_consistency

Then:

TAₖ_intensity = min(valid oracle intensities)

#### 3.3.2 Inconsistent regime

Δ_oracle \> ε_consistency

Then:

SPDₖ = informational

------------------------------------------------------------------------

#### 3.4 Subject-linked Intervention (SIₖ)

Measured Subject action within valid space-time window.

------------------------------------------------------------------------

#### 3.5 Suppression Event (SEₖ)

Measured reduction/interruption of active risk.

------------------------------------------------------------------------

#### 3.6 Suppression Completeness (Sₖ)

Signals must be temporally aligned:

TAₖ @ t₀\
SEₖ @ t₁, where 0 \< (t₁ − t₀) ≤ Δt_int

Sₖ = clamp(0,1, (TAₖ_intensity − SEₖ_intensity) / TAₖ_intensity )

If:

SEₖ_intensity ≥ TAₖ_intensity

then:

Sₖ = 0\
SPDₖ = 0

------------------------------------------------------------------------

#### 3.7 Threat Severity Weight (Wₖ)

Non-negative scalar.

------------------------------------------------------------------------

#### 3.8 Attribution Factor (Aₖ)

Aₖ ∈ \[0,1\]

------------------------------------------------------------------------

#### 3.9 Confidence Factor (Cₖ)

Derived from PTL coverage.

------------------------------------------------------------------------

#### 3.10 Tamper Resistance Factor (Tₖ)

Derived from manipulation detection.

------------------------------------------------------------------------

#### 3.11 Contextual Baseline Field (CBFᵢ)

Audit-only reference, non-reward.

------------------------------------------------------------------------

### 4. Core Recognition Rule

TAₖ(valid, consistent) ∧ SIₖ ∧ SEₖ ⇒ SPDₖ \> 0

Else:

SPDₖ = 0 or informational

------------------------------------------------------------------------

### 5. Preventive Contribution Calculation

SPDₖ = Wₖ × Sₖ × Aₖ × Cₖ × Tₖ

PS_subject = Σ SPDₖ

------------------------------------------------------------------------

### 6. Attribution Rules

Aₖ \> 0 ⇔ causal linkage traceable

Σ Aₖ ≤ 1

Residual remains unallocated.

------------------------------------------------------------------------

### 7. Justice Non-Leakage Invariant

Preventive attribution shall not create:

- obligation
- liability
- duty presumption

------------------------------------------------------------------------

### 8. Privacy Constraint

Subject-linked intervention must be provable via:

ZKP(SIₖ, linkage) without exposing raw behavioral logs

Raw logs:

- encrypted
- access-restricted
- audit-gated

------------------------------------------------------------------------

### 9. Anti-Manipulation Constraints

#### 9.1 Self-Induced Risk

if linkage(subject, TAₖ) \> θ → Tₖ = 0

------------------------------------------------------------------------

#### 9.2 Baseline Isolation

CBFᵢ non-reward.

------------------------------------------------------------------------

#### 9.3 Pattern Recurrence

repeat(TAₖ pattern) → Tₖ ↓

------------------------------------------------------------------------

#### 9.4 Coverage Integrity

low coverage → Cₖ ↓\
no data → SPDₖ = 0

------------------------------------------------------------------------

#### 9.5 Multi-Oracle Requirement

Single-source invalid.

------------------------------------------------------------------------

### 10. Coordinated Drift Protection

Peer signals non-reward.

Global floors enforced.

------------------------------------------------------------------------

### 11. Output Specification

- SPDₖ
- PS_subject
- attribution
- confidence
- tamper flags

Deterministic and auditable.

------------------------------------------------------------------------

### 12. Failure Modes

- oracle inconsistency (Δ_oracle \> ε_consistency) → informational
- attribution ambiguity → SPDₖ = 0
- sensor degradation → Cₖ ↓

------------------------------------------------------------------------

### 13. Invariants

1.  TAₖ, SIₖ, SEₖ required
2.  No reward from absence
3.  No hypothetical states
4.  Oracle consistency required
5.  Causal attribution mandatory
6.  Anti-gaming enforced
7.  No justice leakage

------------------------------------------------------------------------

### 14. Simulation Layer (L8)

Defines:

- ε_consistency
- Δt_int
- θ thresholds
- Wₖ weights

------------------------------------------------------------------------

### 15. Finality

This protocol is changed only through the controlled procedure of DKP-4-UPGRADE-001: proposal, simulation under DKP-8-SIMULATION-001, audit under DKP-8-AUDIT-001, acceptance conditions, activation window and rollback.

Changes require:

- version increment
- compatibility audit
- migration path

Presentation-only corrections that do not change normative content are not Upgrades (DKP-4-UPGRADE-001 §3); they are recorded only by the "Last updated" date of this document.
