---
id: "DKP-0-ORACLE-001"
slug: dkp-0-oracle-001
kind: protocol
last_updated: 2026-10-04
---

### Physical Truth Layer Protocol (PTL)

------------------------------------------------------------------------

### 1. Purpose

The Physical Truth Layer (PTL) defines the **sole admissible interface between physical reality and the Dikenocracy governance system**.

Its function is to produce a **bounded, physically grounded, cryptographically verifiable representation of observable reality**, independent of political, economic, or human discretion.

The PTL produces **physical state only**.

The PTL does not:

- interpret meaning,
- infer intent,
- assign value,
- perform policy reasoning,
- infer subjective or semantic states.

------------------------------------------------------------------------

### 2. System Position and Anchoring

This protocol is an integral extension of Appendix A.2 of the Code of Planetary Synergy and is anchored to **Genesis Block \#0 (2025-12-10)**.

Compatibility with Genesis Block physical anchors and parameters is a **mandatory validity condition** for any PTL implementation.

PTL outputs are **non-normative** and may only be consumed by higher layers under explicitly defined activation and scope rules.

------------------------------------------------------------------------

### 3. Scope

This protocol governs:

- oracle admissibility,
- data ingestion constraints,
- oracle weighting and ownership caps,
- temporal validity of data (TTL),
- data aggregation methodology,
- divergence detection and arbitration,
- production of raw physical indices required by higher layers.

This protocol explicitly excludes:

- human testimony or manual input,
- semantic interpretation,
- intent inference,
- subjective state attribution,
- policy reasoning,
- cross-layer feedback or parameter adjustment.

------------------------------------------------------------------------

### 4. Core Definitions

#### 4.1 Physical State Vector S(t)

A time-indexed vector of **physically measurable variables**, derived exclusively from admissible oracle inputs.

------------------------------------------------------------------------

#### 4.2 Oracle Source

A hardware-bound system producing **cryptographically signed physical measurements**, traceable to a registered oracle identity.

------------------------------------------------------------------------

#### 4.3 Oracle Owner

A natural or legal person controlling one or more oracle sources.

------------------------------------------------------------------------

#### 4.4 Confidence Weight wᵢ

A normalized reliability contribution of an oracle source, bounded and capped by protocol constraints.

------------------------------------------------------------------------

#### 4.5 Coverage

The fraction of the target physical domain that is actively observed by valid oracle sources with non-zero confidence.

------------------------------------------------------------------------

#### 4.6 Data Staleness (TTL)

The maximum admissible age of a datum before its confidence weight is **forced to zero**.

------------------------------------------------------------------------

#### 4.7 Independent Oracle Classes

Distinct measurement modalities defined by **physical separation of sensing mechanisms**.

------------------------------------------------------------------------

#### 4.8 Divergence Event

A statistically significant disagreement between posterior distributions produced by **independent oracle classes**.

------------------------------------------------------------------------

### 5. Measurement Classification (Mandatory)

All PTL outputs MUST be explicitly classified as one of the following:

#### 5.1 Direct Physical Measurements

Directly observable quantities requiring no semantic interpretation.

Examples include: position, speed, acceleration, mass, temperature, radiation, pressure, noise level, duration, exposure.

------------------------------------------------------------------------

#### 5.2 Proxy-Based Measurements

Derived indicators correlating with physical processes but **not equivalent to subjective, semantic, or normative states**.

Examples include: load indices, stress proxies, fatigue indicators, environmental risk proxies.

Proxy-based outputs MUST:

- explicitly declare the proxy model used,
- include propagated uncertainty,
- explicitly state that the result is not a subjective state.

------------------------------------------------------------------------

#### 5.3 Non-Measurable Domains (Explicitly Excluded)

The PTL SHALL NOT emit outputs concerning:

- intent,
- dignity,
- belief,
- responsibility,
- consent,
- moral, cultural, or social harm.

------------------------------------------------------------------------

### 6. Independent Oracle Classes

The PTL defines the following independent oracle classes:

- Orbital (satellite-based remote sensing),
- Ground (fixed terrestrial or marine sensors),
- Autonomous (mobile or robotic sensing platforms).

Divergence detection applies **exclusively across classes**, not within a single class.

------------------------------------------------------------------------

### 7. Data Ingestion Rules

All data MUST:

- be cryptographically signed at the source,
- be time-stamped with a verifiable clock,
- be traceable to a registered oracle identity,
- be delivered in an open, publicly decodable schema.

Proprietary or non-decodable data formats SHALL be rejected regardless of signature validity.

Zero-knowledge proofs MAY be used to verify authenticity without revealing proprietary sensor internals.

No data may be modified, normalized, aggregated, or interpreted at ingestion time.

------------------------------------------------------------------------

### 8. Oracle Weighting and Anti-Collusion Constraints

- Maximum confidence weight per oracle source: **4%**
- Maximum combined confidence weight per oracle owner: **4%**

Ownership caps apply regardless of the number or distribution of devices.

Exceeding caps results in:

- automatic zeroing of excess weight,
- slashing of the violating owner’s remaining stake, where applicable.

------------------------------------------------------------------------

### 9. Temporal Validity and Data Staleness

All data types SHALL have an explicit TTL.

Data exceeding its TTL SHALL have its confidence weight set to zero.

Stale data MUST NOT be:

- extrapolated,
- interpolated,
- substituted,
- averaged into current state.

Oracle silence, loss of signal, or zero-weight conditions:

- SHALL NOT be interpreted as neutral or zero-impact physical states,
- MUST propagate upward as **explicit uncertainty, degradation, or halt signals**.

------------------------------------------------------------------------

### 10. Data Aggregation Method

The PTL aggregates admissible data using a **deterministic Bayesian ensemble**.

- Oracle inputs act as likelihood updates, not votes.
- Prior weights reflect long-term reliability.
- Posterior distributions define S(t).

Given identical inputs, aggregation MUST be reproducible.

All aggregation pipelines MUST be auditable and explainable.

------------------------------------------------------------------------

### 11. Divergence Detection and Arbitration

A Divergence Event is triggered when posterior distributions across independent oracle classes differ by more than **7%**.

Upon a Divergence Event:

- a divergence flag is emitted,
- all dependent state-based transactions SHALL be frozen.

Maximum arbitration window: **14 days**.

Resolution requires:

- convergence within the threshold, or
- exclusion of faulty or compromised sources.

------------------------------------------------------------------------

### 12. Outputs

The PTL produces the following immutable outputs:

- Signed Physical State Vector S(t)
- Oracle confidence weights
- Coverage metrics
- Divergence flags
- Confidence envelope for each output ∈ \[0,1\]
- Raw Biosphere Integrity Index B(t)

B(t) is a **composite physical index**, constructed exclusively from PTL-admissible measurements.

The **model, aggregation logic, weighting, and calibration of B(t)** are **not defined in PTL** and MUST be explicitly specified in **DKP-8-SIMULATION-001**.

PTL SHALL NOT modify, tune, normalize, or reinterpret B(t) beyond emitting its raw, model-declared output.

Until an attached and valid L8 calibration bundle exists, B(t) SHALL be treated as **informational only** and SHALL NOT trigger enforcement.

------------------------------------------------------------------------

### 13. Systemic Halt Conditions

All dependent governance execution layers MUST halt if any of the following conditions occur:

- aggregate confidence falls below **60%**,
- global coverage falls below the minimum operational threshold,
- systemic oracle integrity is compromised.

Systemic Halt:

- blocks execution of L2 and higher layers,
- SHALL NOT erase, reset, reinterpret, or invalidate L1 state,
- preserves identity attribution, impact records, and subject continuity.

------------------------------------------------------------------------

### 14. Crisis Mercy Exception

If a Crisis Mercy status is formally activated under Appendix A.4 of the Code of Planetary Synergy, and the PTL confirms that oracle degradation is caused by **non-anthropogenic global physical events**, enforcement of Systemic Halt MAY be temporarily deferred.

For avoidance of doubt:

Events resulting from **human action, negligence, sabotage, coordinated sensor manipulation, or deliberate oracle interference** SHALL NOT be classified as non-anthropogenic.

Such deferral:

- DOES NOT modify TTL values,
- DOES NOT restore stale data weights,
- DOES NOT alter aggregation logic,
- IS strictly time-limited in accordance with Appendix A.4,
- DOES NOT create normative or precedential authority (see DKP-7-SCOPE-001).

------------------------------------------------------------------------

### 15. Cross-Layer Isolation Invariant

No higher-layer protocol may:

- influence oracle weights,
- modify TTL values,
- alter aggregation logic,
- suppress divergence flags,
- reinterpret confidence envelopes.

Violation constitutes a **critical system integrity breach**.

------------------------------------------------------------------------

### 16. Table of Constants

| Parameter                | Value   |
|--------------------------|---------|
| Max oracle source weight | 4%      |
| Max oracle owner weight  | 4%      |
| Divergence threshold     | 7%      |
| Arbitration window       | 14 days |
| Systemic confidence halt | \< 60%  |
| Minimum global coverage  | 80%     |

------------------------------------------------------------------------

### 17. TTL Registry (Normative)

| Data Type                      | Maximum TTL |
|--------------------------------|-------------|
| Atmospheric CO₂ concentration  | 1 hour      |
| Surface temperature (land/sea) | 24 hours    |
| Active fire detection          | 10 minutes  |
| Biodiversity indices           | 30 days     |
| Land-use change                | 7 days      |

------------------------------------------------------------------------

### 18. Non-Override and Finality

This protocol is immutable once deployed.

Any modification requires:

- a new protocol identifier,
- an explicit incompatibility declaration,
- re-anchoring assessment against Genesis Block \#0.

#### Epistemic Interpretation Note

PTL outputs are measurement records of physical states at specific times.

Their "finality" and "non-override" properties reflect:

a\) The impossibility of changing past physical states

b\) The prohibition on higher layers overriding measured reality

This does NOT constitute:

a\) A claim that PTL measurements represent absolute truth

b\) Immunity from measurement error correction under DKP-4-ERROR-001

c\) Permanent validity beyond defined TTL windows

PTL outputs remain bounded evaluations per DKP-1-EPISTEMIC-BOUNDARIES-001.

------------------------------------------------------------------------
