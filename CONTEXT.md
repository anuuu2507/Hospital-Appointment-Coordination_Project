# Domain Glossary — Hospital Appointment Booking Agent

| Term | Definition |
|------|------------|
| Patient | A registered user who books appointments with doctors. |
| Staff | A hospital employee who manages doctor schedules. |
| Doctor | A medical professional with defined working hours attached to a hospital. |
| Hospital | A medical facility that employs one or more doctors. |
| Slot | A 30-minute availability window derived from a doctor's working hours. Computed dynamically; not stored. |
| Appointment | A confirmed reservation of a Slot by a Patient. Status: scheduled, cancelled, completed. |
| Booking Window | Today through the next 7 days — the only period for which slots are shown or bookable. |
| Session | An in-memory server-side object (token to user) for the duration of a browser tab's login. |
| Tool | A Python function exposed to Gemini via function calling. The authoritative enforcement point for all business rules. |
| Working Hours | A doctor's work_start, work_end, and work_days — the source of truth for slot generation. |