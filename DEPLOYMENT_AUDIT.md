# DEPLOYMENT READINESS AUDIT

This is a complete deployment-readiness report based on the actual current state of the HealthConnect / Hospital Appointment Coordination project.

## 1. Current Architecture

**Frontend:**
- **Technology:** Vanilla HTML, CSS, JavaScript in a single file (`index.html`).
- **Framework/Library:** None (pure DOM manipulation).
- **Static/Bundled:** Static, not bundled.
- **Serving:** Served directly by FastAPI using `StaticFiles` mounted at `/static` and a `/` route serving `index.html`.

**Backend:**
- **Python Version:** 3.11+ (based on local virtual environment markers).
- **FastAPI Version:** Mentioned in `requirements.txt` (latest available).
- **Uvicorn:** Yes, used as the ASGI server.
- **Entry Point:** `backend.main:app`.
- **Application Object:** `app` in `backend/main.py`.
- **Startup Command (Current):** Handled via `if __name__ == "__main__": uvicorn.run(app, host="0.0.0.0", port=8000)`.
- **Port/Host Binding:** Hardcoded to `0.0.0.0:8000` when run directly via Python.

**AI:**
- **SDK:** `google-generativeai`.
- **Model:** `gemini-1.5-flash` (for both patient and doctor agents).
- **API Key Loading:** Loaded via `os.environ.get("GEMINI_API_KEY")` from `.env`.
- **Server-Side Secrets:** Yes, the Gemini API key MUST remain on the server and is never sent to the frontend.
- **Request Flow:** Frontend sends a message to `/api/chat`. Backend retrieves chat history from the DB, constructs a context-aware prompt, uses the Gemini API with tools (function calling) to retrieve data from the DB if needed, and returns a formatted JSON or text response to the frontend.

**Database:**
- **Technology:** MySQL.
- **Library:** `pymysql` with `sqlalchemy` (SQLAlchemy is mostly used for schema definitions and DB creation, while a custom `DBMock` wrapper uses raw SQL with `pymysql` for queries).
- **Database Name:** `hospital_appointment_db` (default).
- **Initialization:** `database.py` includes `init_db()` which attempts to create the DB and schema using `Base.metadata.create_all`. It also inserts seed data (hospitals and doctors).
- **Current Dependency:** It currently relies on a MySQL server (like XAMPP on localhost:3307).
- **Production Replacement:** Yes, the database MUST be replaced with a hosted MySQL service in production. XAMPP cannot be used for a deployed app.

**Authentication:**
- **Method:** JWT (JSON Web Tokens).
- **Storage:** Stored in `HttpOnly` cookies (`access_token` and `refresh_token`).
- **Expiration:** Configurable via `.env` (defaults: 30 mins access, 30 days refresh).
- **Required Secrets:** `JWT_SECRET_KEY` in `.env`.
- **CORS:** Since the frontend and backend are served from the same origin, CORS is not currently configured or required.

**Voice:**
- **Voice Implementation:** After inspecting the frontend code (`index.html`), there is currently **no voice/speech functionality** implemented (no Web Speech API, `webkitSpeechRecognition`, etc.). Heali interaction is entirely text-based.

---

## 2. Runtime Requirements

| Component | Requirement | Production Notes |
| :--- | :--- | :--- |
| **Python Version** | 3.11+ | Make sure the platform supports modern Python. |
| **Node Requirement** | None | Pure Python/Static file deployment. |
| **Package Install Command**| `pip install -r backend/requirements.txt` | Requirements file is located in the `backend/` directory. |
| **Backend Start Command** | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`| Use standard Uvicorn CLI, as `python main.py` hardcodes port 8000. |
| **Build Command** | None | No frontend bundling required. |
| **Environment Variables** | Required | See section below. |
| **Database** | Managed MySQL 8.0+ | Persistent database required. SQLite cannot be used. |
| **Persistent Storage** | Not required | No user file uploads. |
| **External APIs** | Gemini API | Outbound HTTPS required. |
| **HTTPS Requirement** | Strongly Recommended | Needed for Geolocation API and secure cookies in production. |

---

## 3. Environment Variables

Here is the SAFE list of required environment variables for production. Configure these in the deployment platform's dashboard.

| Variable Name | Purpose | Example Format | Required in Prod? | Where to Configure |
| :--- | :--- | :--- | :--- | :--- |
| `GEMINI_API_KEY` | Authenticates backend with Google Gemini AI. | `AIzaSy...` | YES | Platform Env Vars |
| `JWT_SECRET_KEY` | Signs auth tokens. Keep this secure and random. | `<strong-random-secret>` | YES | Platform Env Vars |
| `DB_HOST` | Hostname of the managed MySQL database. | `db.platform.com` | YES | Platform Env Vars |
| `DB_PORT` | Port of the MySQL database. | `3306` | YES | Platform Env Vars |
| `DB_USER` | Database username. | `admin_user` | YES | Platform Env Vars |
| `DB_PASSWORD` | Database password. | `<strong-password>` | YES | Platform Env Vars |
| `DB_NAME` | Name of the database to use. | `healthconnect_db` | YES | Platform Env Vars |

*(Optional variables like `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` can be omitted to use defaults).*

---

## 4. Database Requirements

The application connects to MySQL via a connection string constructed in `database/database.py` using `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME`.

- **Hosted MySQL Required?** YES. You cannot use a local XAMPP database for a deployed application. If the developer's PC is turned off, the application will crash because it cannot reach the local database.
- **SQLite Remnants?** There are two SQLite `.db` files (`database/hospital.db` and `database/hospital_booking.db`) in the repository, but the application code strictly uses MySQL (`mysql+pymysql://...`). The SQLite files are orphaned remnants and are not used by the current code.
- **Schema Auto-creation:** Yes, `init_db()` in `database/database.py` automatically runs `CREATE DATABASE IF NOT EXISTS` and uses SQLAlchemy's `create_all` to build tables.
- **Seed Data:** Yes, `init_db()` inserts seed hospitals, doctors, and patients.
- **Production Safety:** `init_db()` is currently called unconditionally when `backend/main.py` starts (`init_db()` on line 17). This will attempt to create the database and insert seed data every time the server restarts. While `seed_data` checks if entries already exist before inserting, it does run `UPDATE` statements on existing seed doctors, which might override changes made in production. This is somewhat safe but not ideal for production. Existing user-created appointments are preserved.

---

## 5. Database Schema

The required production tables are:

- **users:** `id`, `name`, `email`, `password_hash`, `role`, `doctor_id` (FK to doctors). Core authentication table.
- **patients:** `id`, `user_id` (FK to users), `address`, `city`, `state`, `pincode`, `latitude`, `longitude`. Patient profile data.
- **doctors:** `id`, `name`, `specialty`, `hospital_id` (FK to hospitals), `work_start`, `work_end`, `work_days`, `professional_id`. Doctor profile and schedule configuration.
- **hospitals:** `id`, `name`, `location`, `address`, `city`, `state`, `pincode`, `latitude`, `longitude`. Hospital details for location-based searching.
- **appointments:** `id`, `patient_id` (FK to users), `doctor_id` (FK to doctors), `slot_datetime`, `status`, `created_at`. Stores bookings.
- **chat_sessions:** `id`, `user_id` (FK to users), `title`, `created_at`. Chat history organization.
- **chat_messages:** `id`, `session_id` (FK to chat_sessions), `role`, `content`, `created_at`. Actual Heali conversation logs.

---

## 6. External Services

The application relies entirely on:
1. **Google Gemini API** for the Heali assistant.
2. **OpenStreetMap Nominatim API** (`https://nominatim.openstreetmap.org/reverse`) for reverse geocoding patient coordinates into addresses.

---

## 7. Production Start Command

The exact command that should be configured in the deployment platform is:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```
*(Note: Some platforms use a specific port environment variable. Ensure the command respects the platform's dynamic `$PORT`).*

Do not use `python backend/main.py` as it hardcodes port `8000` and `0.0.0.0`, which may conflict with the platform's routing.

---

## 8. Static File Configuration

FastAPI correctly mounts the `frontend` directory using `StaticFiles`:
```python
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
```
It serves `index.html` at the root `/`.

- **Hardcoded URLs:** A scan of the frontend shows NO hardcoded `localhost`, `127.0.0.1`, `8000`, or `8001` URLs in the JS `fetch` calls. All API calls use relative paths (e.g., `/api/login`, `/api/me`), which is excellent for deployment.
- **Assets:** SVGs in `frontend/assets` are referenced correctly.

---

## 9. CORS

Because the frontend is served by FastAPI on the exact same domain and port, **CORS is completely avoided**. The current codebase does not include `CORSMiddleware`, and it does not need it for this architecture.

---

## 10. Authentication / Cookies

JWT is used, and tokens are set as HTTP-only cookies in `backend/main.py`.

**Production Change Needed:**
Currently, the cookies are set like this:
```python
response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
```
For production (HTTPS), it is highly recommended (and required by some browsers for cross-site or secure contexts) to include `secure=True` and `samesite="lax"`. However, because it's a same-origin request, the current configuration will function, though it is slightly less secure over HTTPS without the `Secure` flag.

---

## 11. Gemini Configuration

- **SDK:** `google.generativeai`
- **Model:** `gemini-1.5-flash`
- **Configuration:** API key loaded securely from `.env`. The deployment platform will need outbound HTTPS access to reach Google's APIs.
- The model `gemini-1.5-flash` is active and correct.

---

## 12. Location & Voice Requirements

**Location Features:**
- Uses the browser's `navigator.geolocation` API.
- **HTTPS Requirement:** Modern browsers **require HTTPS** to allow access to the geolocation API. If you deploy this on standard HTTP, the "Use my current location" button will silently fail or be blocked.
- Uses OpenStreetMap for reverse geocoding via backend proxy (`/api/geocode/reverse`), which works well and avoids CORS issues.

**Voice Features:**
- There is currently **no voice integration** in the codebase. Interaction with Heali is entirely text-based.

---

## 13. Security Findings

| Finding | Severity | Description |
| :--- | :--- | :--- |
| **Missing Secure Cookie Flag** | MEDIUM | Cookies do not have the `Secure` flag, making them susceptible to interception if accidentally sent over HTTP. |
| **DB Initialization in Production** | MEDIUM | `init_db()` runs on every startup. It executes raw `ALTER TABLE` and `UPDATE` statements that might cause brief locks or overwrite manual changes to seed doctors in production. |
| **Hardcoded Defaults** | LOW | Fallback JWT secret `fallback_secret` is present if `.env` fails to load. |
| **SQL Injection Risks** | INFO | The custom `DBMock.execute` method safely replaces `?` with `%s` and uses parameter binding. It appears safe from basic SQL injection. |

---

## 14. Platform Comparison

Given the architecture (FastAPI serving static files + MySQL), here is a comparison:

| Platform | FastAPI Support | Managed MySQL | Deployment Complexity | Free/Low Cost Tier | HTTPS/SSL |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Render** | Excellent | Yes (Render Postgres is common, but MySQL requires external provider or paid tier) | Very Low (Connect GitHub) | Yes (Web service is free, but free DB disappears after 90 days) | Automatic |
| **Railway** | Excellent | Yes (Built-in Managed MySQL plugin) | Very Low (Connect GitHub) | Low cost (approx $5/mo, no permanent free tier) | Automatic |
| **Fly.io** | Good (Docker) | Needs external/Docker | Medium | Yes (Generous free tier) | Automatic |
| **Vercel** | Poor for FastAPI | No | High (Serverless only) | Yes | Automatic |

**Conclusion:** The codebase naturally supports a single unified service (Option A: Backend + Frontend together). **Railway** or **Render** are the best choices for a college/demo project. Railway is highly recommended because it offers an easy, one-click managed MySQL database plugin in the same environment.

---

## 15. Recommended Deployment Architecture

**Architecture (Single Service + Managed DB):**

[User Browser]
      │ (HTTPS)
      ▼
[FastAPI Web Service] ──(Serves Static Files)──► [Frontend (index.html)]
      │
      ├── (TCP/3306) ──► [Managed MySQL Database]
      │
      └── (HTTPS) ────► [Google Gemini API]

Everything runs on one URL (e.g., `https://healthconnect.up.railway.app`). This completely avoids CORS issues and simplifies cookie management.

---

## 16. Deployment Checklist

**BEFORE DEPLOYMENT**
- [ ] Connect GitHub repository to deployment platform.
- [ ] Provision a managed MySQL database on the platform.
- [ ] Configure Environment Variables on the platform (`GEMINI_API_KEY`, `JWT_SECRET_KEY`, `DB_*`).
- [ ] Set Start Command to `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
- [ ] Deploy the web service.

**VERIFICATION**
- [ ] Verify homepage loads over HTTPS.
- [ ] Verify Patient registration (and test Geolocation).
- [ ] Verify Doctor registration.
- [ ] Verify Heali chat works (confirms Gemini API connection).
- [ ] Verify manual booking persists.
- [ ] Verify login/logout clears cookies.

---

## 17. Post-Deployment Testing Plan

Follow these exact steps in a browser once deployed:

**PATIENT TEST:**
1. Register → enter home address or use Geolocation.
2. Login → check Patient Portal loads.
3. Talk to Heali → ask "Find doctors near me".
4. Book manually → select hospital, doctor, check slots, confirm.
5. Verify appointment appears in Upcoming Appointments.
6. Logout.

**DOCTOR TEST:**
1. Register → enter hospital details.
2. Login → check Doctor Portal.
3. Manage Schedule → adjust working hours and save.
4. Talk to Heali → ask "Show my appointments for today".
5. Verify the patient's booked appointment appears in Upcoming Appointments.
6. Logout.

---

## 18. Known Limitations

- **Geolocation requires HTTPS.** If deployed on a platform without SSL, registration location will fail.
- **Database Seed Data:** Restarting the server will execute `seed_data`, which might reset some doctor specialties or hospital addresses back to default values.
- **Voice Features:** Not implemented.

---

## 19. Exact Things My Friend Must Configure

1. Provide an active `GEMINI_API_KEY`.
2. Generate a random string for `JWT_SECRET_KEY`.
3. Create a managed MySQL instance and obtain the Host, Port, User, Password, and Database Name.
4. Set the startup command to use Uvicorn with `$PORT`.

---

## 20. Things That Must NOT Be Committed to GitHub

Ensure `.env` is inside `.gitignore`. The repository must NEVER contain:
- `GEMINI_API_KEY`
- Database passwords
- `JWT_SECRET_KEY`

*(The `backend/.env.example` file is safe to commit).*
