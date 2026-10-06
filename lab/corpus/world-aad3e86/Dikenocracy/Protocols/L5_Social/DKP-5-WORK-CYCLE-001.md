---
id: "DKP-5-WORK-CYCLE-001"
slug: dkp-5-work-cycle-001
kind: protocol
last_updated: 2026-10-04
---

**Work Cycle & Recovery Rhythm Protocol**

------------------------------------------------------------------------

### 0. Preamble

DKP-5-WORK-CYCLE-001 defines the normative structure of work and recovery within Dikenocracy.

This protocol treats work cycles as a **physical, cognitive, and safety-critical infrastructure**, not as a cultural habit, moral expectation, or legacy industrial convention. Human fatigue, error accumulation, and burnout are considered **systemic risks**, not individual failures.

Accordingly, the protocol abandons the culturally inherited 7-day week as a core unit and replaces it with a **physically neutral, mathematically exact, and biologically sustainable cycle**, fully compatible with DTI timekeeping.

------------------------------------------------------------------------

### 1. Purpose

The purpose of DKP-5-WORK-CYCLE-001 is to:

- establish a deterministic, culture-neutral work/rest cycle,
- guarantee mandatory intra-day recovery,
- reduce systemic error, injury, and burnout risk,
- ensure compatibility with 24/7 critical infrastructure,
- decouple productivity from continuous human exhaustion,
- provide measurable constraints for workforce planning and simulation.

------------------------------------------------------------------------

### 2. Scope

This protocol applies to:

- all standard labor arrangements under DKP,
- public services and private enterprises,
- critical and non-critical sectors.

Sector-specific adaptations are permitted **only if** all invariants defined herein are preserved.

------------------------------------------------------------------------

### 3. Definitions

- **DTI-Day**

  A physical day indexed under DKP-0-TIME-001.

- **Cycle6**

  A 6-day overlay cycle defined as: `CycleDay = DTI-Day mod 6`

- **Workday (W)**

  A day containing a mandatory productive work obligation.

- **Restday (R)**

  A day containing no productive work obligation.

- **Presence Window**

  The total time a worker is scheduled to be available on a workday.

- **Productive Work Time**

  Time spent on direct labor tasks.

- **Recovery Block**

  Mandatory non-working time within a workday dedicated to recovery.

------------------------------------------------------------------------

### 4. Standard Work Cycle

#### 4.1 Cycle Structure

The normative default cycle is a **6-day cycle**:

`[W, W, R, W, W, R]`

Meaning:

- two consecutive workdays,
- one restday,
- two consecutive workdays,
- one restday.

#### 4.2 Properties

- Maximum consecutive workdays: **2**

- Rest frequency: every **≤ 3 days**

- Full compatibility with a 360-day DTI year:

  \* 360 / 6 = 60 exact cycles per year

The 7-day week is explicitly **non-normative** and may exist only as a local cultural overlay without legal or computational authority.

------------------------------------------------------------------------

### 5. Daily Workday Structure

#### 5.1 Normative Time Allocation (Workday)

Each workday SHALL be structured as follows:

- **Total Presence Window:** 10 hours
- **Productive Work Time:** 8 hours
- **Mandatory Recovery Block:** 2 hours

Formally:

Presence = 10h Work = 8h Recovery = 2h

#### 5.2 Recommended Default Layout

A recommended (but not mandatory) structure:

- 4 hours productive work
- 2 hours recovery
- 4 hours productive work

#### 5.3 Recovery Block Rules

- The recovery block:

  *is not counted as work time,* cannot be removed, reduced, or monetized, \* does not require justification.

- Permitted recovery activities include:

  *meals,* sleep or rest, *personal or family needs,* non-work mobility.

The recovery block is considered **system-required**, not discretionary.

------------------------------------------------------------------------

### 6. Cycle Accounting

Per 6-day cycle:

- Workdays: 4
- Restdays: 2
- Productive work: 32 hours
- Presence: 40 hours
- Recovery: 8 hours

Per DTI-Year (360 days):

- Workdays: 240
- Productive work: 1,920 hours
- Presence: 2,400 hours
- Mandatory recovery: 480 hours

------------------------------------------------------------------------

### 7. Recovery Invariant (Hard Constraint)

Under no circumstances may a system-approved schedule violate the following invariant:

- No worker may be assigned more than **2 consecutive workdays** without a restday

  **OR**

- An equivalent, demonstrably safe recovery compensation must be provided.

Violation of this invariant constitutes a **system planning failure**, not individual misconduct.

------------------------------------------------------------------------

### 8. 24/7 and High-Intensity Environments

#### 8.1 Shift-Based Continuity

Continuous operation (e.g., hospitals, emergency services, infrastructure control) SHALL be achieved through:

- multiple shifts,
- workforce scaling,
- shift overlap,
- capacity buffering.

Continuous service SHALL NOT be achieved through exhaustion of individual workers.

------------------------------------------------------------------------

#### 8.2 Shift Requirements

Each shift SHALL preserve:

- a 10-hour presence window,
- 8 hours productive work,
- **minimum 2 hours recovery** per shift.

For high-intensity environments:

- **3–4 hours recovery per shift is recommended**, potentially fragmented.

#### 8.3 Overlaps and Peak Load

- Overlapping shifts during peak hours are:

  *explicitly permitted,* treated as capacity design, not inefficiency.

- Simultaneous multi-shift presence during peaks is considered normal and encouraged.

------------------------------------------------------------------------

### 9. Monitoring & KPIs (Minimum Set)

Implementations SHALL monitor at least:

- error and incident rates,
- sick leave frequency,
- staff attrition,
- output per productive hour,
- recovery compliance rate.

Persistent degradation in these metrics SHALL trigger mandatory schedule review.

------------------------------------------------------------------------

### 10. Exceptions

Exceptions are permitted only:

- in clearly defined crisis scopes,
- for limited duration,
- with mandatory recovery compensation,
- and with full traceability under DKP crisis protocols.

No exception may establish precedent.

------------------------------------------------------------------------

### 11. Architectural Principle

This protocol establishes a three-layer human time model:

1.  **Productive Work**
2.  **Mandatory Recovery**
3.  **Full Rest**

Human recovery is treated as **infrastructure**, not as a personal optimization problem.

------------------------------------------------------------------------

### 12. Summary Statement

DKP-5-WORK-CYCLE-001 replaces legacy industrial work rhythms with a mathematically exact, biologically sustainable, and governance-compatible cycle.

It ensures that:

- time is counted deterministically,
- recovery is guaranteed by design,
- productivity is stabilized through prevention of systemic harm,
- and continuous services are achieved through planning, not sacrifice.

------------------------------------------------------------------------
