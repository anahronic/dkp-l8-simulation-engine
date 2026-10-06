---
id: "DKP-1-IMPACT-001"
slug: dkp-1-impact-001
kind: protocol
last_updated: 2026-10-04
---

### Impact Measurement Protocol

------------------------------------------------------------------------

### 1. Purpose

The Impact Measurement Protocol defines how changes in the **Physical State Vector S(t)** are transformed into **time-indexed, bounded, and auditable impact metrics**.

This protocol performs **measurement only**. It does **not** interpret value, intent, utility, justice, responsibility, or policy.

------------------------------------------------------------------------

### 2. System Position and Anchoring

This protocol operates:

- above DKP-0-ORACLE-001 (Physical Truth Layer),
- below DKP-1-IDENTITY-001 (Identity & Subject Protocol),
- below DKP-1-JUSTICE-001 (Justice Function Protocol),
- below all governance, economic, and enforcement protocols.

All inputs to this protocol MUST originate exclusively from **Physical Truth Layer outputs**.

All reference bounds **Bᵢ** MUST be explicitly imported from:

- DKP-1-AXIOMS-001, or

- normatively defined Physical Truth Layer indices

  (e.g., biosphere survival thresholds anchored in Genesis Block constants).

This protocol is bound to **Genesis Block \#0 (2025-12-10)**.

------------------------------------------------------------------------

### 3. Scope

This protocol governs:

- measurement of state change between two physical states,
- time-indexed impact evaluation over an externally supplied horizon Δt,
- detection of boundary approach and boundary crossing,
- classification of reversibility and externality,
- production of structured, channel-separated impact outputs.

This protocol explicitly excludes:

- optimization, scoring, or weighting,
- aggregation across channels,
- decision-making or enforcement,
- attribution of responsibility,
- compensation logic,
- any form of utility or justice calculation.

------------------------------------------------------------------------

### 4. Core Definitions

#### Physical State Vector S(t)

An immutable, time-indexed vector of measured physical variables produced by DKP-0-ORACLE-001.

------------------------------------------------------------------------

#### Baseline State S(t₀)

The reference physical state prior to an evaluated change.

------------------------------------------------------------------------

#### Observed State S(t₁)

The measured physical state after the evaluated change.

------------------------------------------------------------------------

#### Impact Horizon Δt

A time interval supplied as an external parameter defining the evaluation window.

------------------------------------------------------------------------

#### Impact Channel

A logically independent dimension of physical or informational impact.

Normatively declared impact channels include, but are not limited to:

- Biosphere Integrity
- Atmospheric Composition
- Human Health Proxies
- Resource Depletion
- Energy Balance
- Cognitive Integrity Proxies
- Cultural Continuity Indicators

------------------------------------------------------------------------

#### Impact Vector Iᵢ(t₀ → t₁, Δt)

A channel-specific, bounded impact metric defined as normalized physical change.

------------------------------------------------------------------------

#### Reference Bounds Bᵢ

Invariant physical limits imported from DKP-1-AXIOMS-001 or Physical Truth Layer indices.

------------------------------------------------------------------------

#### Reversibility Flag Rᵢ

A boolean indicator of physical or informational irreversibility.

------------------------------------------------------------------------

#### Externality Flag Xᵢ

A boolean indicator of boundary-crossing impact.

------------------------------------------------------------------------

#### Uncertainty Envelope Uᵢ

A bounded confidence interval propagated from Physical Truth Layer uncertainty.

------------------------------------------------------------------------

### 5. Measurement Principle

Impact is defined strictly as the **difference between two physical states**:

**S(t₀) → S(t₁)** over **Δt**

For each impact channel *i*, let *Sᵢ(t)* denote the projection of *S(t)* onto channel *i*.

The protocol computes:

**Iᵢ = ( Sᵢ(t₁) − Sᵢ(t₀) ) / Bᵢ**

The resulting value is:

- unaggregated,
- dimensionless,
- auditable.

If **\|Iᵢ\| ≥ 1**, a boundary crossing SHALL be flagged.

No aggregation across channels is permitted.

------------------------------------------------------------------------

### 6. Reference Bounds and Boundary Detection

Each impact channel SHALL declare its applicable reference bounds **Bᵢ**.

Bounds MUST be:

- physically or informationally defined,
- immutable within this protocol,
- traceable to DKP-1-AXIOMS-001 or Physical Truth Layer indices.

The protocol SHALL detect:

- boundary approach,
- boundary crossing.

Bounds SHALL NOT be modified, normalized, or reinterpreted.

------------------------------------------------------------------------

### 7. Reversibility Classification

For each impact channel, the protocol SHALL evaluate reversibility using formal criteria.

Criteria MUST be:

- explicit,
- physically or informationally grounded,
- binary in output.

Illustrative criteria MAY include:

- entropy increase beyond reversible regimes,

- irrecoverable loss of biospheric structures,

- irreversible phase transitions,

- permanent loss of cognitive or cultural capacity

  as verified via Physical Truth Layer data.

Subjective or intent-based assessments are forbidden.

------------------------------------------------------------------------

### 8. Externality Detection

The protocol SHALL distinguish between **internal** and **external** impact.

System boundary SHALL default to **planetary scale** unless explicitly narrowed by higher-layer protocols.

Any detected boundary crossing SHALL set **Xᵢ = True**.

Absence of an explicit boundary definition SHALL be treated as **full externality exposure**.

------------------------------------------------------------------------

### 9. Uncertainty Propagation

Measurement uncertainty from Physical Truth Layer inputs SHALL be propagated into each impact channel.

Propagation SHALL be deterministic.

Illustrative methods MAY include:

- Bayesian ensembles,
- posterior confidence bands (e.g., ±3σ).

Uncertainty SHALL NOT be used to suppress, downgrade, or invalidate detected impact.

------------------------------------------------------------------------

### 10. Outputs

For each impact channel *i*, the protocol outputs:

- **Iᵢ** — impact vector,
- **Bᵢ** — reference bound,
- **Rᵢ** — reversibility flag,
- **Xᵢ** — externality flag,
- **Uᵢ** — uncertainty envelope.

No aggregated impact score SHALL be produced.

------------------------------------------------------------------------

### 11. Cross-Layer Isolation Invariant

No higher-layer protocol may:

- alter reference bounds,
- suppress impact channels,
- override reversibility or externality flags,
- inject valuation, weighting, responsibility, or optimization logic.

Violation constitutes a **critical architectural breach**.

------------------------------------------------------------------------

### 12. Protocol Finality

This protocol is changed only through the controlled procedure of DKP-4-UPGRADE-001: proposal, simulation under DKP-8-SIMULATION-001, audit under DKP-8-AUDIT-001, acceptance conditions, activation window and rollback.

Any modification requires:

- a new protocol identifier,
- explicit declaration of incompatibility,
- full-system revalidation under DKP-8-SIMULATION.

Presentation-only corrections that do not change normative content are not Upgrades (DKP-4-UPGRADE-001 §3); they are recorded only by the "Last updated" date of this document.

Edition integrity: the SHA-256 digest of the canonical source of each published edition is listed in `SHA256SUMS.txt` of the canonical repository (github.com/anahronic/World).

------------------------------------------------------------------------

### 13. Illustrative Example (Non-Normative)

**Input**

- Channel: Atmospheric Composition
- S(t₀): CO₂ = 426.91 ppm
- S(t₁): CO₂ = 427.00 ppm
- Δt: 1 hour
- Bᵢ: 450 ppm

**Output**

- Iᵢ ≈ 0.004
- Rᵢ = False
- Xᵢ = False
- Uᵢ = ±0.01 ppm

This example is illustrative only and not normative.

------------------------------------------------------------------------

#### END OF PROTOCOL
