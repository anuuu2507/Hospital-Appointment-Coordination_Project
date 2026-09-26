# ADR 0002: Slots Computed Dynamically, Not Stored

## Status
Accepted

## Context
We need to show available 30-minute appointment slots for each doctor. One approach is to pre-generate and store all slots in a table. Another is to compute them on the fly from doctor working hours.

## Decision
Compute slots dynamically from `doctors.work_start`, `doctors.work_end`, and `doctors.work_days`. A slot is free if no row exists in `appointments` for that `(doctor_id, slot_datetime)` with status `scheduled`.

## Consequences
**Positive:**
- No slot table to maintain or synchronize.
- Changing doctor hours immediately affects future slot queries.
- Simpler schema with fewer tables.

**Negative:**
- Slot queries require a DB lookup per doctor per date.
- Slightly more computation per request (acceptable for MVP scale).