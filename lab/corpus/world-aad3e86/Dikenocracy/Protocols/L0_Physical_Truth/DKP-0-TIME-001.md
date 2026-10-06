---
id: "DKP-0-TIME-001"
slug: dkp-0-time-001
kind: protocol
last_updated: 2026-10-04
---

### Dikenocratic Time & Date Index Protocol (DTI)

------------------------------------------------------------------------

### 1. Purpose

DKP-0-TIME-001 defines a **non-religious, event-neutral, deterministic system for counting days and years** within the Dikenocracy framework.

The protocol establishes:

- a canonical **absolute civil day index**,
- a **fixed-length governance year** for accountability and reporting,
- precise and auditable **conversion rules** to and from the Gregorian calendar when external interoperability is required.

This protocol explicitly avoids:

- religious eras or holidays,
- historical or mythological reference events,
- variable or exception-based calendar logic.

------------------------------------------------------------------------

### 2. Design Principles

1.  **Neutrality**

    Time MUST NOT be anchored to religious, cultural, political, or personal events.

2.  **Determinism**

    Any date MUST be uniquely computable from its canonical representation.

3.  **Auditability**

    Any record MUST allow independent recomputation of its time index.

4.  **Governance Fitness**

    Time units MUST be simple, fixed-length, and suitable for legal, financial, and KPI logic.

5.  **Interoperability**

    Explicit conversion rules to and from civil calendars MUST be provided.

------------------------------------------------------------------------

### 3. Definitions

- **JDN (Julian Day Number)**

  An integer count of civil days (midnight-to-midnight) in the proleptic Gregorian calendar.

**DTI-Day**

The canonical absolute civil day index used by Dikenocracy.

**Definition:**

`DTI-Day = JDN`

- **DTI-Year (DY)**

  A governance year consisting of exactly **360 consecutive DTI-Days**.

- **Day-of-Year (DOY)**

  A 1-based index of a day within a DTI-Year, in the range **1…360**.

------------------------------------------------------------------------

### 4. Normative Time Units

#### 4.1 Base Unit

- The base temporal unit of DKP-TIME-001 MUST be the **civil day**.
- Sub-day units (hours, minutes, seconds) MUST NOT be required by this protocol.

#### 4.2 Governance Year

- A DTI-Year MUST contain exactly **360 DTI-Days**.
- Leap days, leap years, or corrective rules MUST NOT exist.
- Year boundaries MUST be defined purely arithmetically.

------------------------------------------------------------------------

### 5. Canonical Date Representation

#### 5.1 Numeric Form

Given a canonical `DTI-Day`:

`DY = floor(DTI-Day / 360)`

`DOY = (DTI-Day mod 360) + 1`

#### 5.2 String Form

`DY<dy>-<doy>`

Where:

- `<dy>` is a signed integer year index,
- `<doy>` is a zero-padded three-digit day index (001–360).

**Example:**

`DY6836-084`

------------------------------------------------------------------------

### 6. Conversion Rules (Normative)

#### 6.1 Gregorian → Dikenocratic

Given a Gregorian civil date `(year, month, day)`:

1.  Compute the **JDN** using a standard astronomical algorithm.
2.  Set `DTI-Day = JDN`.
3.  Compute `(DY, DOY)` using Section 5.

#### 6.2 Dikenocratic → Gregorian

Given `(DY, DOY)`:

1.  Validate `DOY ∈ [1, 360]`.

2.  Compute:

    `DTI-Day = DY × 360 + (DOY − 1)`

3.  Convert `DTI-Day (JDN)` to Gregorian `(year, month, day)`.

#### 6.3 Validation

- Invalid `DOY` values MUST be rejected.
- `DY` MAY be negative.
- Derived fields MUST NOT override `DTI-Day`.

------------------------------------------------------------------------

### 7. Interoperability

- Gregorian dates MAY be shown for human readability.

- Any authoritative record MUST include:

  - `DTI-Day`, or
  - canonical `(DY, DOY)`.

- In case of conflict, **DTI-Day is authoritative**.

------------------------------------------------------------------------

### 8. Storage, Signing, and Audit

- Signed records SHOULD store:

  - `DTI-Day` (authoritative),
  - optionally `(DY, DOY)` as derived fields.

- Audits and dispute resolution MUST reference `DTI-Day`.

------------------------------------------------------------------------

### 9. Normative Test Vectors

Implementations MUST reproduce these values exactly.

| Gregorian Date | JDN (DTI-Day) | DY   | DOY | Canonical  |
|----------------|---------------|------|-----|------------|
| 2026-01-01     | 2461042       | 6836 | 83  | DY6836-083 |
| 2026-01-02     | 2461043       | 6836 | 84  | DY6836-084 |
| 1970-01-01     | 2440588       | 6779 | 149 | DY6779-149 |
| 2000-01-01     | 2451545       | 6815 | 26  | DY6815-026 |

Failure to match these vectors constitutes a protocol violation.

------------------------------------------------------------------------

### 10. Reference Implementation (Canonical)

```python
from __future__ import annotations
from dataclasses import dataclass

# Gregorian <-> JDN (Fliegel–Van Flandern)

def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return (
        day
        + (153 * m + 2) // 5
        + 365 * y
        + y // 4
        - y // 100
        + y // 400
        - 32045
    )

def jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + (m // 10)
    return year, month, day

DTI_YEAR_LENGTH = 360

@dataclass(frozen=True)
class DikenocraticDate:
    dy: int
    doy: int
    def __post_init__(self):
        if not (1 <= self.doy <= DTI_YEAR_LENGTH):
            raise ValueError("DOY must be in 1..360")
    def canonical(self) -> str:
        return f"DY{self.dy}-{self.doy:03d}"

def jdn_to_dikenocratic(jdn: int) -> DikenocraticDate:
    return DikenocraticDate(jdn // 360, (jdn % 360) + 1)

def dikenocratic_to_jdn(dd: DikenocraticDate) -> int:
    return dd.dy * 360 + (dd.doy - 1)

def gregorian_to_dikenocratic(y: int, m: int, d: int) -> DikenocraticDate:
    return jdn_to_dikenocratic(gregorian_to_jdn(y, m, d))

def dikenocratic_to_gregorian(dy: int, doy: int) -> tuple[int, int, int]:
    return jdn_to_gregorian(dikenocratic_to_jdn(DikenocraticDate(dy, doy)))
```

------------------------------------------------------------------------

### 11. Rationale (Non-Normative)

Time in Dikenocracy is treated as an **operational index**, not as a cultural narrative. `DTI-Day` provides a continuous, neutral axis. `DTI-Year` provides a stable governance cycle.
