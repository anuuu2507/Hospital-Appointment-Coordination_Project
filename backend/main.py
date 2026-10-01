import os
import sys
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import jwt
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from database.database import init_db, get_db, check_password, hash_password
from backend.agent import GeminiAgent

app = FastAPI(title="Hospital Appointment Booking Agent")
init_db()

agent = None

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback_secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def get_agent():
    global agent
    if agent is None:
        agent = GeminiAgent()
    return agent


class LoginRequest(BaseModel):
    email: str
    password: str

class PatientRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    address: str = None
    city: str = None
    state: str = None
    pincode: str = None
    latitude: str = None
    longitude: str = None

class DoctorRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    specialization: str
    doctor_id: str
    hospital_name: str
    hospital_address: str = None
    hospital_city: str = None
    hospital_state: str = None
    hospital_pincode: str = None

class ChatRequest(BaseModel):
    message: str


def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    
    if not token or token == "null":
        raise HTTPException(status_code=401, detail="Missing authentication token")
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Expired access token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.post("/api/register/patient")
def register_patient(req: PatientRegisterRequest):
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    db.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'patient')",
        (req.name, req.email, hash_password(req.password))
    )
    user_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
    
    db.execute(
        "INSERT INTO patients (user_id, address, city, state, pincode, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, req.address, req.city, req.state, req.pincode, req.latitude, req.longitude)
    )
    
    db.commit()
    db.close()
    return {"message": "Patient registered successfully"}

@app.post("/api/register/doctor")
def register_doctor(req: DoctorRegisterRequest):
    db = get_db()
    
    # Check if user already exists
    existing_user = db.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
    if existing_user:
        db.close()
        raise HTTPException(status_code=400, detail="Email already registered.")
        
    # Check if doctor with this professional ID already exists
    existing_doc = db.execute("SELECT id FROM doctors WHERE professional_id=?", (req.doctor_id,)).fetchone()
    if existing_doc:
        db.close()
        raise HTTPException(status_code=400, detail="Doctor ID already registered.")
        
    # Match hospital by name (robustly)
    hospital = db.execute("SELECT id FROM hospitals WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (req.hospital_name,)).fetchone()
    if not hospital:
        # Create hospital
        db.execute(
            "INSERT INTO hospitals (name, location, address, city, state, pincode) VALUES (?, ?, ?, ?, ?, ?)", 
            (req.hospital_name, req.hospital_city or '', req.hospital_address, req.hospital_city, req.hospital_state, req.hospital_pincode)
        )
        hospital_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
    else:
        hospital_id = hospital["id"]
        
    # Insert doctor
    db.execute(
        "INSERT INTO doctors (name, specialty, hospital_id, work_start, work_end, work_days, professional_id) VALUES (?, ?, ?, '09:00,13:00', '11:30,17:00', '0,1,2,3,4', ?)",
        (req.name, req.specialization, hospital_id, req.doctor_id)
    )
    new_doc_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
        
    db.execute(
        "INSERT INTO users (name, email, password_hash, role, doctor_id) VALUES (?, ?, ?, 'doctor', ?)",
        (req.name, req.email, hash_password(req.password), new_doc_id)
    )
    db.commit()
    db.close()
    return {"message": "Doctor registered successfully"}


import urllib.request
import json

@app.get("/api/geocode/reverse")
def reverse_geocode(latitude: str, longitude: str):
    try:
        lat = float(latitude)
        lon = float(longitude)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid latitude or longitude")
    
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
    req = urllib.request.Request(url, headers={"User-Agent": "HealthConnectApp/1.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        raise HTTPException(status_code=503, detail="Reverse geocoding service unavailable")

    address = data.get("address", {})
    return {
        "display_name": data.get("display_name", ""),
        "road": address.get("road", ""),
        "suburb": address.get("suburb", address.get("locality", address.get("neighbourhood", ""))),
        "city": address.get("city", address.get("town", address.get("village", address.get("county", "")))),
        "state": address.get("state", ""),
        "postcode": address.get("postcode", ""),
        "house_number": address.get("house_number", "")
    }


@app.post("/api/login")
def login(req: LoginRequest, response: Response):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (req.email,)).fetchone()
    db.close()

    if not user or not check_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    payload = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "doctor_id": user["doctor_id"] if "doctor_id" in user.keys() else None
    }
    
    access_token = create_access_token(payload)
    refresh_token = create_refresh_token(payload)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, max_age=REFRESH_TOKEN_EXPIRE_DAYS*86400)

    return {"token": access_token, "name": user["name"], "role": user["role"]}

@app.get("/api/me")
def get_me(user=Depends(get_current_user)):
    return {"token": "cookie", "name": user["name"], "role": user["role"]}

@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"ok": True}

@app.get("/api/chat/sessions")
def get_sessions(user=Depends(get_current_user)):
    db = get_db()
    rows = db.execute("SELECT * FROM chat_sessions WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
    db.close()
    return [{"id": r["id"], "title": r["title"], "created_at": r["created_at"]} for r in rows]

@app.get("/api/chat/sessions/{session_id}")
def get_session_messages(session_id: int, user=Depends(get_current_user)):
    db = get_db()
    session = db.execute("SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user["id"])).fetchone()
    if not session:
        db.close()
        raise HTTPException(status_code=403, detail="Unauthorized access to chat session.")
    
    messages = db.execute("SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall()
    db.close()
    return {"session_id": session_id, "messages": [{"role": r["role"], "content": r["content"]} for r in messages]}

@app.post("/api/chat/sessions")
def create_session(user=Depends(get_current_user)):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)", (user["id"], "New Chat", now, now))
    db.commit()
    session_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
    db.close()
    return {"id": session_id, "title": "New Chat"}

@app.delete("/api/chat/sessions/{session_id}")
def delete_session(session_id: int, user=Depends(get_current_user)):
    db = get_db()
    session = db.execute("SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user["id"])).fetchone()
    if not session:
        db.close()
        raise HTTPException(status_code=403, detail="Unauthorized")
    db.execute("DELETE FROM chat_messages WHERE session_id=?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
    db.commit()
    db.close()
    return {"ok": True}

@app.post("/api/chat/sessions/{session_id}/messages")
def add_session_message(session_id: int, req: ChatRequest, user=Depends(get_current_user)):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session = db.execute("SELECT id FROM chat_sessions WHERE id=? AND user_id=?", (session_id, user["id"])).fetchone()
    if not session:
        db.close()
        raise HTTPException(status_code=403, detail="Unauthorized")
    db.execute("INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)", (session_id, "user", req.message, now))
    db.commit()
    db.close()
    return {"ok": True}

@app.post("/api/chat")
def chat(req: ChatRequest, user=Depends(get_current_user)):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session = db.execute("SELECT id FROM chat_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (user["id"],)).fetchone()
    
    if not session:
        db.execute("INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)", (user["id"], "Chat", now, now))
        db.commit()
        session_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
    else:
        session_id = session["id"]
        
    db.execute("INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)", (session_id, "user", req.message, now))
    db.commit()
    user_msg_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
    
    history_rows = db.execute("SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall()
    
    history = []
    for r in history_rows:
        history.append({"role": "user" if r["role"] == "user" else "model", "parts": [r["content"]]})
        
    history = history[:-1][-10:]

    a = get_agent()
    reply = a.chat(
        history=history,
        message=req.message,
        caller_id=user["id"],
        caller_role=user["role"],
        caller_name=user["name"],
        doctor_id=user.get("doctor_id")
    )
    
    if isinstance(reply, list):
        reply = " ".join([str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in reply])
    elif isinstance(reply, dict):
        reply = str(reply.get("text", reply))
    else:
        reply = str(reply)
        
    error_messages = [
        "Heali is having trouble connecting right now 😅",
        "Heali is not configured correctly right now. Please contact the administrator.",
        "Something went wrong while Heali was processing that request. Please try again."
    ]
    
    if reply in error_messages:
        db.execute("DELETE FROM chat_messages WHERE id=?", (user_msg_id,))
        db.commit()
    else:
        db.execute("INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)", (session_id, "agent", reply, now))
        db.commit()
        
    db.close()

    return {"reply": reply}

@app.post("/api/clear")
def clear_history(user=Depends(get_current_user)):
    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO chat_sessions (user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)", (user["id"], "New Chat", now, now))
    db.commit()
    db.close()
    return {"ok": True}

@app.get("/api/appointments/upcoming")
def get_upcoming_appointments(user=Depends(get_current_user)):
    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    if user["role"] == "patient":
        rows = db.execute('''
            SELECT a.*, d.name as doctor_name, d.specialty, h.name as hospital_name, h.address as hospital_address
            FROM appointments a 
            LEFT JOIN doctors d ON a.doctor_id = d.id
            LEFT JOIN hospitals h ON d.hospital_id = h.id
            WHERE a.patient_id=? AND a.status='scheduled' AND a.slot_datetime >= ?
            ORDER BY a.slot_datetime ASC
        ''', (user["id"], now_str)).fetchall()
    else:
        rows = db.execute('''
            SELECT a.*, u.name as patient_name 
            FROM appointments a 
            LEFT JOIN users u ON a.patient_id = u.id
            WHERE a.doctor_id=? AND a.status='scheduled' AND a.slot_datetime >= ?
            ORDER BY a.slot_datetime ASC
        ''', (user.get("doctor_id"), now_str)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/api/appointments/previous")
def get_previous_appointments(user=Depends(get_current_user)):
    db = get_db()
    if user["role"] == "patient":
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = db.execute('''
            SELECT a.*, d.name as doctor_name, d.specialty, h.name as hospital_name, h.address as hospital_address
            FROM appointments a 
            LEFT JOIN doctors d ON a.doctor_id = d.id
            LEFT JOIN hospitals h ON d.hospital_id = h.id
            WHERE a.patient_id=? AND (a.status IN ('completed', 'cancelled') OR (a.status='scheduled' AND a.slot_datetime < ?))
            ORDER BY a.slot_datetime DESC
        ''', (user["id"], now_str)).fetchall()
        db.close()
        return [dict(r) for r in rows]
    else:
        db.close()
        raise HTTPException(status_code=403, detail="Only patients can view previous appointments")

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_ui():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# ----------------- NEW ENDPOINTS ----------------- #


class AvailabilityUpdate(BaseModel):
    days: str # comma separated string "0,1,2,3,4"
    morning_start: str
    morning_end: str
    afternoon_start: str
    afternoon_end: str

class ProfileUpdate(BaseModel):
    name: str
    email: str
    specialty: str
    hospital_name: str
    hospital_address: str
    hospital_city: str
    hospital_state: str
    hospital_pincode: str

@app.get("/api/hospitals")
def get_hospitals():
    db = get_db()
    hospitals = db.execute("SELECT * FROM hospitals").fetchall()
    db.close()
    return [dict(h) for h in hospitals]

def require_role(role: str):
    def role_checker(user=Depends(get_current_user)):
        if user["role"] != role:
            raise HTTPException(status_code=403, detail=f"Requires {role} role.")
        return user
    return role_checker

@app.get("/api/doctor/profile")
def get_doctor_profile(user=Depends(require_role("doctor"))):
    db = get_db()
    doctor = db.execute("SELECT * FROM doctors WHERE id=?", (user.get("doctor_id"),)).fetchone()
    if not doctor:
        db.close()
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    hospital = None
    if doctor["hospital_id"]:
        hospital = db.execute("SELECT * FROM hospitals WHERE id=?", (doctor["hospital_id"],)).fetchone()
        
    db.close()
    return {
        "id": doctor["id"],
        "name": doctor["name"],
        "specialty": doctor["specialty"],
        "professional_id": doctor.get("professional_id", ""),
        "email": user["email"],
        "work_days": doctor["work_days"],
        "work_start": doctor["work_start"],
        "work_end": doctor["work_end"],
        "hospital": dict(hospital) if hospital else None
    }

@app.put("/api/doctor/profile")
def update_doctor_profile(req: ProfileUpdate, user=Depends(require_role("doctor"))):
    db = get_db()
    # Update user email
    db.execute("UPDATE users SET email=?, name=? WHERE id=?", (req.email, req.name, user["id"]))
    
    # Check hospital
    hospital = db.execute("SELECT id FROM hospitals WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))", (req.hospital_name,)).fetchone()
    if not hospital:
        db.execute(
            "INSERT INTO hospitals (name, location, address, city, state, pincode) VALUES (?, ?, ?, ?, ?, ?)", 
            (req.hospital_name, req.hospital_city or '', req.hospital_address, req.hospital_city, req.hospital_state, req.hospital_pincode)
        )
        hospital_id = db.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
    else:
        hospital_id = hospital["id"]
        # Update hospital details
        db.execute("UPDATE hospitals SET address=?, city=?, state=?, pincode=? WHERE id=?", (req.hospital_address, req.hospital_city, req.hospital_state, req.hospital_pincode, hospital_id))
        
    # Update doctor
    db.execute("UPDATE doctors SET name=?, specialty=?, hospital_id=? WHERE id=?", (req.name, req.specialty, hospital_id, user.get("doctor_id")))
    
    db.commit()
    db.close()
    return {"message": "Profile updated"}

@app.get("/api/doctor/appointments/today")
def get_today_appointments(user=Depends(require_role("doctor"))):
    db = get_db()
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows = db.execute(
        "SELECT a.*, u.name as patient_name FROM appointments a JOIN users u ON a.patient_id = u.id WHERE a.doctor_id=? AND a.slot_datetime LIKE ? ORDER BY a.slot_datetime ASC", 
        (user.get("doctor_id"), f"{today_str}%")
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/api/doctor/appointments/upcoming")
def get_doc_upcoming_appointments(user=Depends(require_role("doctor"))):
    db = get_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = db.execute(
        "SELECT a.*, u.name as patient_name FROM appointments a JOIN users u ON a.patient_id = u.id WHERE a.doctor_id=? AND a.slot_datetime >= ? ORDER BY a.slot_datetime ASC", 
        (user.get("doctor_id"), now_str)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.put("/api/doctor/availability")
def update_availability(req: AvailabilityUpdate, user=Depends(require_role("doctor"))):
    db = get_db()
    # Storing morning_start, morning_end, afternoon_start, afternoon_end in work_start and work_end as JSON or comma separated?
    # Wait, the schema has work_start, work_end (String(10)). 
    # If the user wants 09:00-11:30 and 13:00-17:00, we can store it as "09:00,13:00" and "11:30,17:00"
    db.execute(
        "UPDATE doctors SET work_days=?, work_start=?, work_end=? WHERE id=?",
        (req.days, f"{req.morning_start},{req.afternoon_start}", f"{req.morning_end},{req.afternoon_end}", user.get("doctor_id"))
    )
    db.commit()
    db.close()
    return {"message": "Availability updated"}

@app.put("/api/appointments/{appt_id}/status")
def update_appointment_status(appt_id: int, status_update: dict, user=Depends(require_role("doctor"))):
    db = get_db()
    # Verify doctor owns this appointment
    appt = db.execute("SELECT * FROM appointments WHERE id=? AND doctor_id=?", (appt_id, user.get("doctor_id"))).fetchone()
    if not appt:
        db.close()
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    db.execute("UPDATE appointments SET status=? WHERE id=?", (status_update.get("status"), appt_id))
    db.commit()
    db.close()
    return {"message": "Status updated"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)



@app.get("/api/doctors")
def get_all_doctors():
    db = get_db()
    rows = db.execute('''
        SELECT d.id as doctor_id, d.name, d.specialty, d.work_days,
               h.name as hospital_name, h.address as hospital_address, h.city as hospital_city
        FROM doctors d
        LEFT JOIN hospitals h ON d.hospital_id = h.id
    ''').fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/api/doctors/{doctor_id}/slots")
def get_doctor_slots(doctor_id: int, date: str):
    from backend.tools import check_slots
    result = check_slots(doctor_id, date)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

class BookAppointmentRequest(BaseModel):
    doctor_id: int
    date: str
    time: str

@app.post("/api/appointments/book")
def book_appointment_api(req: BookAppointmentRequest, user=Depends(get_current_user)):
    if user["role"] != "patient":
        raise HTTPException(status_code=403, detail="Only patients can book appointments")
    
    from backend.tools import book_appointment
    slot_datetime = req.time if " " in req.time else f"{req.date} {req.time}"
    result = book_appointment(doctor_id=req.doctor_id, slot_datetime=slot_datetime, caller_id=user["id"])
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
