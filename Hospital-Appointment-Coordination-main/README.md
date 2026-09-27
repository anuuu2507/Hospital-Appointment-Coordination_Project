# Hospital Appointment Booking Agent

A conversational AI agent for hospital appointment management. Patients find doctors, check availability, and manage appointments through natural language. Hospital staff manage doctor schedules — all through a browser-based chat interface.

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI
- **Frontend:** HTML + Vanilla JavaScript
- **Database:** SQLite
- **AI:** Gemini 2.0 Flash (Google) with function calling

## Setup

1. Get a Gemini API key from https://aistudio.google.com/app/apikey
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set the API key:
   ```bash
   export GEMINI_API_KEY=your_key_here
   ```
4. Start the server:
   ```bash
   uvicorn main:app --reload
   ```
5. Open http://localhost:8000

## Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Patient | arun@example.com | patient123 |
| Patient | deepa@example.com | patient123 |
| Patient | vikram@example.com | patient123 |
| Staff | staff@hospital.com | staff123 |

## Features

### Patient
- Search doctors by specialty/hospital
- Check available 30-minute slots
- Book, reschedule, cancel appointments
- View appointment history

### Staff
- List all doctors with working hours
- View any doctor's schedule by date
- Update doctor working hours

## Project Structure

```
main.py          - FastAPI app (API endpoints + static serving)
agent.py         - Gemini 2.0 Flash integration with function calling
tools.py         - 9 tool functions with business rule enforcement
database.py      - SQLite schema creation and seed data
static/index.html - Chat UI (login + chat screens)
requirements.txt - Python dependencies
CONTEXT.md       - Domain glossary
docs/adr/        - Architecture Decision Records
```

## Business Rules

All rules enforced in the tool layer (Python), not in LLM prompts:
- No past-slot booking
- No double-booking (DB constraint + code check)
- 7-day booking window
- Valid 30-minute slot alignment
- Doctor must work on requested day
- Patient can only modify own appointments
- Role-based tool access

## Author

**Bhavana Kolli** — [@bhavana2007](https://github.com/bhavana2007)