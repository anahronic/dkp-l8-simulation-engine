---
id: "DKP-2-FINANCE-001"
slug: dkp-2-finance-001
kind: protocol
last_updated: 2026-10-04
---

### Financial System Protocol

------------------------------------------------------------------------

### 1. Purpose

The Financial System Protocol defines how financial activity — including savings, lending, credit issuance, investment, capital allocation, and pricing of capital — operates within the Dikenocracy system.

The protocol embeds **δίκη (justice as a function)** directly into financial mechanics, ensuring that:

- cost of capital reflects measured impact and responsibility,
- externalities are internalized deterministically,
- financial incentives align with long-term physical and social stability.

This protocol governs **economic mechanics**, not policy discretion.

It does **not**:

- create or manage fiat monetary regimes,
- override justice outcomes,
- perform subjective valuation or preference aggregation,
- substitute for governance or social support layers.

------------------------------------------------------------------------

### 2. System Position

This protocol operates:

- above all L1 protocols

  (DKP-1-AXIOMS-001, DKP-1-IMPACT-001, DKP-1-IDENTITY-001, DKP-1-JUSTICE-001),

- below social, infrastructural, and intersystem protocols (L5–L6),

- alongside security and fail-safe mechanisms (L3–L4).

All financial computations MUST be traceable to:

- measured impact outputs (DKP-1-IMPACT-001),
- responsibility bindings (DKP-1-IDENTITY-001),
- justice outcomes (DKP-1-JUSTICE-001),
- axiomatic constraints (DKP-1-AXIOMS-001).

------------------------------------------------------------------------

### 3. Core Economic Units

#### 3.1 Capital Units (CU)

**Capital Units (CU)** are unitless, fungible representations of deployable economic capacity within the system.

CU represent **productive capability net of justice-weighted externalities**, not nominal wealth.

All CU flows are recorded on a deterministic, auditable ledger.

------------------------------------------------------------------------

#### 3.2 Justice-Weighted Cost of Capital (JWCoC)

The cost of capital is determined as a deterministic function of:

- historical justice outcomes associated with a Subject,
- projected impact risks across relevant channels,
- axiomatic reference bounds and safety margins.

Positive justice contribution reduces cost of capital. Negative or risky impact exposure increases cost of capital.

There is no discretionary pricing of risk.

------------------------------------------------------------------------

### 4. Time, Risk, and Capital Pricing

#### 4.1 Justice-Anchored Interest

Interest rates are computed as a function of:

- justice burden carried by the borrower,
- impact volatility and externality exposure,
- reversibility and mitigation capacity.

Interest is **not compensation for impatience**, but a pricing of **measured risk and justice imbalance**.

------------------------------------------------------------------------

#### 4.2 Time Value of Capital (Strict Constraint)

The system explicitly **rejects subjective time preference**.

#### Explicit Time Preference Prohibition

Subjective time preference, impatience discounting, or utility-based devaluation of future outcomes SHALL NOT be used in any financial computation within this protocol.

Temporal discounting is permitted **exclusively** as a consequence of measurable changes in projected impact channels over time, as defined by DKP-1-IMPACT-001.

For avoidance of doubt, the absence of subjective discounting does not imply zero time sensitivity.

Time remains a structurally relevant dimension through impact evolution, risk accumulation, reversibility decay, and exposure duration, all of which are evaluated via physically measurable impact channels rather than subjective preference functions.

This constraint is mandatory and reflects **Axiom A2** **(Intergenerational Responsibility)** as defined in DKP-1-AXIOMS-001.

------------------------------------------------------------------------

### 5. Credit and Lending

#### 5.1 Credit Issuance

Credit MAY be issued only if:

a\) projected justice-weighted productive output is sufficient for repayment, b) expected impact does not violate axiomatic bounds, c) aggregate exposure remains within systemic safety margins.

Credit is a **temporary imbalance**, not a right.

------------------------------------------------------------------------

#### 5.2 Credit Limits

Credit limits are dynamically computed based on:

- justice history of the Subject,
- projected impact correlation,
- systemic stress indicators.

No Subject may increase leverage if doing so raises the probability of axiom-bound violation.

------------------------------------------------------------------------

### 6. Savings and Reserves

#### 6.1 Savings

Savings are CU held in reserve and may generate returns derived from:

- duration of deployment,
- justice-weighted performance of deployed capital,
- measured systemic risk.

Savings returns are deterministic and fully auditable.

------------------------------------------------------------------------

#### 6.2 Systemic Reserve Pools (SRP)

Systemic Reserve Pools exist to:

- absorb defaults,
- fund restitution obligations,
- prevent cascading systemic failure.

Reserve sizing is impact-based, not percentage-based.

------------------------------------------------------------------------

### 7. Investment and Capital Allocation

Capital allocation decisions SHALL be driven by:

- expected net justice output,
- impact risk envelopes,
- alignment with axiomatic priorities.

Speculative or purely price-driven allocation is forbidden.

------------------------------------------------------------------------

### 8. Default and Financial Restitution

#### 8.1 Default Conditions

A default occurs when:

- repayment cannot be achieved within a justice-defined horizon, and
- continued exposure threatens axiomatic bounds.

Defaults trigger **justice-defined outcomes**, not punishment.

------------------------------------------------------------------------

#### 8.2 Restitution Handling

Restitution MAY include:

- reserve deployment,
- obligation restructuring,
- proportional loss allocation.

Restitution is bounded by measurable damage and justice outcomes.

------------------------------------------------------------------------

### 9. Leverage and Systemic Risk

Leverage SHALL be constrained such that:

- amplification of negative impact remains below safety thresholds,
- correlated failures cannot cascade beyond reserve capacity.

Leverage limits are impact-based, not volatility-based.

------------------------------------------------------------------------

### 10. Interoperability with External Financial Systems

When interfacing with external systems:

- all values MUST be translated into justice-weighted internal equivalents,
- external risk MUST be fully internalized before deployment.

No external financial structure may bypass justice constraints.

------------------------------------------------------------------------

### 11. Justice-Driven Financial Access Constraint

#### 11.1 Automatic Suspension under Exclusion

If a Subject is assigned to the **Exclusion Domain** under DKP-1-JUSTICE-001, all financial access governed by this protocol SHALL be automatically suspended.

This suspension is **causal**, not discretionary, and requires no independent financial evaluation.

The Financial System Protocol SHALL NOT:

- override exclusion outcomes,
- re-enable access under alternative criteria,
- provide compensatory financial pathways.

Financial access MAY be restored **only** upon formal exit from the Exclusion Domain as determined by DKP-1-JUSTICE-001.

#### 11.2 Justice Domain Synchronization Clause

Financial access suspension state SHALL be continuously synchronized with Justice Domain status as follows:

a\) Upon successful dispute resolution under DKP-4-ERROR-001 that results in exit from Exclusion Domain, financial access SHALL be automatically restored within one (1) DTI-Day.

b\) Pending dispute proceedings SHALL NOT automatically restore access, but SHALL suspend accumulation of any interest, penalties, or additional restrictions during the Status Quo Suspension period defined in DKP-4-ERROR-001 Section 4.1.

c\) The Financial System Protocol SHALL poll Justice Domain status at intervals not exceeding the minimum PTL TTL for Identity-related measurements, and SHALL auto-adjust suspension state upon Domain change.

This clause ensures financial execution tracks justice re-evaluation as required by DKP-1-EPISTEMIC-BOUNDARIES-001 Section 6 (Non-Finality Rule).

------------------------------------------------------------------------

### 12. Transparency and Auditability

All financial mechanisms MUST be:

- deterministic,
- reproducible,
- fully auditable,
- traceable to L1 protocol outputs.

Opaque, discretionary, or proprietary financial logic is forbidden.

------------------------------------------------------------------------

### 13. Cross-Layer Isolation

This protocol SHALL NOT:

- reinterpret impact measurements,
- override identity attribution,
- override justice outcomes,
- inject policy, ideology, or moral judgment.

Violation constitutes a critical architectural breach.

------------------------------------------------------------------------

### 14. Protocol Finality

This protocol is changed only through the controlled procedure of DKP-4-UPGRADE-001: proposal, simulation under DKP-8-SIMULATION-001, audit under DKP-8-AUDIT-001, acceptance conditions, activation window and rollback.

Any modification requires:

- a new protocol identifier,
- explicit declaration of incompatibility,
- full-system simulation under DKP-8-SIMULATION.

Presentation-only corrections that do not change normative content are not Upgrades (DKP-4-UPGRADE-001 §3); they are recorded only by the "Last updated" date of this document.

Edition integrity: the SHA-256 digest of the canonical source of each published edition is listed in `SHA256SUMS.txt` of the canonical repository (github.com/anahronic/World).

------------------------------------------------------------------------

#### END OF PROTOCOL
