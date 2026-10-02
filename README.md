# Hospital Appointment Booking Agent

A conversational AI agent for hospital appointment management. Patients find doctors, check availability, and manage appointments through natural language. Hospital staff manage doctor schedules — all through a browser-based chat interface.

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI
- **Frontend:** HTML + Vanilla JavaScript
- **Database:** MySQL / MariaDB (via SQLAlchemy + PyMySQL — not SQLite; `database/hospital.db` is an unused leftover file)
- **AI:** Gemini 2.0 Flash (Google) with function calling

## Setup

1. Get a Gemini API key from https://aistudio.google.com/app/apikey

2. Make sure a MySQL-compatible server (MySQL or MariaDB) is installed and running. `database/database.py` will create the `hospital_appointment_db` database automatically on first run, but the server itself and a working user/password must already exist. On Debian/Ubuntu:
   ```bash
   sudo apt-get install -y mariadb-server
   sudo mysqld_safe --datadir=/var/lib/mysql &   # or: sudo service mariadb start, if your init system supports it
   ```

3. Install dependencies from the repo root:
   ```bash
   pip install -r backend/requirements.txt
   ```
   Note: `requirements.txt` does not list `google-generativeai`, which `backend/agent.py` imports directly (`import google.generativeai as genai`). Install it separately:
   ```bash
   pip install google-generativeai
   ```

4. Create `backend/.env` (see `backend/.env.example`) with, at minimum:
   ```bash
   GEMINI_API_KEY=your_key_here
   JWT_SECRET_KEY=some_random_secret
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=hospital_appointment_db
   ```
   `DB_PORT` defaults to `3307` in code if unset, which does not match MySQL/MariaDB's default port of `3306` — set it explicitly.

5. Start the server from the **repo root** (not from inside `backend/`), since `backend/main.py` imports sibling packages as `backend.agent` / `database.database`:
   ```bash
   uvicorn backend.main:app --reload
   ```

6. Open http://localhost:8000

Everything except the AI chat screen (login, hospital/doctor listing, slot lookup, booking) works even without a valid `GEMINI_API_KEY` — the chat endpoint will just return a "not configured" message until a real key is set.

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
backend/main.py          - FastAPI app (API endpoints + static serving)
backend/agent.py         - Gemini 2.0 Flash integration with function calling
backend/tools.py         - Tool functions with business rule enforcement
backend/requirements.txt - Python dependencies
backend/.env.example     - Required environment variables
database/database.py     - MySQL/MariaDB (SQLAlchemy) schema creation and seed data
database/hospital.db     - Unused leftover SQLite file (not read by the app)
frontend/index.html      - Chat UI (login + chat screens), served at /
docs/CONTEXT.md          - Domain glossary
docs/adr/                - Architecture Decision Records
scratch/                 - Old/experimental versions of agent, tools, main (not used by the app)
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