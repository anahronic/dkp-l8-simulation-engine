---
id: "DKP-4-CRISIS-001 (PATCH)"
slug: dkp-4-crisis-001-patch
kind: addendum
last_updated: 2026-10-04
meta: "Addendum to DKP-4-CRISIS-001 (not a separate protocol) · Patch: extends v1.0 · Layer: L4 · Affects: DKP-6-RESILIENCE-001 (8.4) · Override: Not permitted"
---

### Null-Output State Handling Extension

------------------------------------------------------------------------

### 1. Purpose

Define system behavior when DKP enters:

- null-output state

as specified in DKP-6-RESILIENCE-001.

------------------------------------------------------------------------

### 2. Trigger Condition

```
N_eff < N_eff_min
OR
oracle consistency invalid
```

Reference: DKP-0-ORACLE-001

------------------------------------------------------------------------

### 3. System State Definition

```
state = NO_ENFORCEMENT
```

Clarification:

- no penalties
- no rewards
- no attribution
- no enforcement outputs

Only:

- measurement continues

------------------------------------------------------------------------

### 4. Hard Constraints

#### 4.1 No Fallback Authority

No human, institution, or algorithm may replace DKP enforcement

Violation leads to:

- system exit from DKP domain
- treated as external system

------------------------------------------------------------------------

#### 4.2 No Degraded Enforcement

Partial enforcement is forbidden

Reason:

- creates manipulable regime
- breaks A3 (reality supremacy)

------------------------------------------------------------------------

#### 4.3 No Priority Routing

System must not selectively restore enforcement for subsets

No:

- “critical actors”
- “essential sectors”

------------------------------------------------------------------------

### 5. Allowed Behavior

#### 5.1 Passive Operation

- system continues collecting PTL data
- no transformation into decisions

------------------------------------------------------------------------

#### 5.2 Autonomous Recovery

```
If N_eff ≥ N_eff_min
AND consistency restored
→ enforcement resumes automatically
```

No:

- approval
- restart command
- manual validation

------------------------------------------------------------------------

### 6. Forbidden Recovery Patterns

6.1 Manual Restart

6.2 External Certification

6.3 Emergency Governance Layer

All violate DKP-7-SCOPE-001

------------------------------------------------------------------------

### 7. Crisis Interaction Constraint

Null-output state does not grant additional authority

Critical:

- crisis mechanisms must operate without DKP enforcement layer
- no precedent is created

------------------------------------------------------------------------

### 8. Failure Mode

#### 8.1 Forced Override Attempt

External system attempts to inject decisions during null-output

Result:

- DKP remains inactive
- external system operates outside DKP

------------------------------------------------------------------------

### 9. Validation Criteria

System is compliant if:

- enforcement fully stops at threshold breach
- no partial outputs exist
- recovery is automatic and deterministic
- no authority emerges during downtime

------------------------------------------------------------------------

### 10. Key Invariant

No enforcement is strictly safer than invalid enforcement

------------------------------------------------------------------------

### 11. Final Statement

DKP does not degrade

It either:

- operates correctly
- or does not operate
