import os
import secrets
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from database import init_db, get_db, check_password, hash_password
from agent import GeminiAgent

app = FastAPI(title="Hospital Appointment Booking Agent")
init_db()

agent = None

SESSIONS: dict = {}
HISTORIES: dict = {}


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

class DoctorRegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    specialization: str
    hospital_name: str
    doctor_id: int

class ChatRequest(BaseModel):
    message: str


def get_current_user(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    token = auth[7:]
    if token not in SESSIONS:
        raise HTTPException(status_code=401, detail="Session expired or invalid token.")
    return SESSIONS[token]


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
    db.commit()
    db.close()
    return {"message": "Patient registered successfully"}

@app.post("/api/register/doctor")
def register_doctor(req: DoctorRegisterRequest):
    db = get_db()
    doctor = db.execute("""
        SELECT d.id FROM doctors d 
        JOIN hospitals h ON d.hospital_id = h.id 
        WHERE d.id=? AND d.name=? AND d.specialty=? AND h.name=?
    """, (req.doctor_id, req.name, req.specialization, req.hospital_name)).fetchone()
    
    if not doctor:
        db.close()
        raise HTTPException(status_code=400, detail="Doctor verification failed. Check hospital name, doctor ID, name, and specialization.")
        
    existing = db.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
    if existing:
        db.close()
        raise HTTPException(status_code=400, detail="Email already registered.")
        
    db.execute(
        "INSERT INTO users (name, email, password_hash, role, doctor_id) VALUES (?, ?, ?, 'doctor', ?)",
        (req.name, req.email, hash_password(req.password), req.doctor_id)
    )
    db.commit()
    db.close()
    return {"message": "Doctor registered successfully"}


@app.post("/api/login")
def login(req: LoginRequest):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email=?", (req.email,)).fetchone()
    db.close()

    if not user or not check_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = secrets.token_hex(32)
    SESSIONS[token] = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "doctor_id": user["doctor_id"] if "doctor_id" in user.keys() else None
    }
    HISTORIES[token] = []

    return {"token": token, "name": user["name"], "role": user["role"]}


@app.post("/api/logout")
def logout(user=Depends(get_current_user)):
    auth = None
    for token, u in SESSIONS.items():
        if u["id"] == user["id"]:
            auth = token
            break
    if auth:
        SESSIONS.pop(auth, None)
        HISTORIES.pop(auth, None)
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request, user=Depends(get_current_user)):
    auth = request.headers.get("Authorization", "")
    token = auth[7:]

    a = get_agent()
    history = HISTORIES.get(token, [])

    reply = a.chat(
        history=history,
        message=req.message,
        caller_id=user["id"],
        caller_role=user["role"],
        caller_name=user["name"],
        doctor_id=user.get("doctor_id")
    )

    history.append({"role": "user", "parts": [req.message]})
    history.append({"role": "model", "parts": [reply]})
    HISTORIES[token] = history

    return {"reply": reply}


@app.post("/api/clear")
def clear_history(request: Request, user=Depends(get_current_user)):
    auth = request.headers.get("Authorization", "")
    token = auth[7:]
    HISTORIES[token] = []
    return {"ok": True}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def serve_ui():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)