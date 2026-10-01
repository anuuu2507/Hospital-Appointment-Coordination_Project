import os
import bcrypt
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import declarative_base
import pymysql.cursors

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env")
load_dotenv(env_path)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3307")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "hospital_appointment_db")

# Create database if it doesn't exist
try:
    setup_engine = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/")
    with setup_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}"))
except Exception as e:
    print(f"Error creating database: {e}")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_recycle=3600)
Base = declarative_base()

class Hospital(Base):
    __tablename__ = 'hospitals'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    latitude = Column(String(50), nullable=True)
    longitude = Column(String(50), nullable=True)

class Doctor(Base):
    __tablename__ = 'doctors'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    specialty = Column(String(255), nullable=False)
    hospital_id = Column(Integer, ForeignKey('hospitals.id'), nullable=True)
    work_start = Column(String(50), nullable=True)
    work_end = Column(String(50), nullable=True)
    work_days = Column(String(50), nullable=True)
    professional_id = Column(String(100), nullable=True)

class DoctorAvailabilityException(Base):
    __tablename__ = 'doctor_availability_exceptions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False)
    date = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, default="unavailable")
    reason = Column(String(255), nullable=True)
    created_at = Column(String(50), nullable=False, default="now()")
    
    __table_args__ = (
        UniqueConstraint('doctor_id', 'date', name='_doctor_date_uc'),
    )

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=True)

class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    doctor_id = Column(Integer, ForeignKey('doctors.id'), nullable=False)
    slot_datetime = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(String(50), nullable=False, default="now()")
    
    __table_args__ = (
        UniqueConstraint('doctor_id', 'slot_datetime', 'status', name='_doctor_slot_status_uc'),
    )

class ChatSession(Base):
    __tablename__ = 'chat_sessions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    title = Column(String(255), nullable=True)
    created_at = Column(String(50), nullable=False, default="now()")
    updated_at = Column(String(50), nullable=False, default="now()")

class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey('chat_sessions.id'), nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(String(5000), nullable=False)
    created_at = Column(String(50), nullable=False, default="now()")

class Patient(Base):
    __tablename__ = 'patients'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    address = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    latitude = Column(String(50), nullable=True)
    longitude = Column(String(50), nullable=True)

class DBMock:
    def __init__(self):
        try:
            self.conn = engine.raw_connection()
            self.cursor = self.conn.cursor(pymysql.cursors.DictCursor)
        except Exception as e:
            raise Exception(f"Database connection failed: {e}")

    def execute(self, query, params=()):
        q = query.replace("?", "%s")
        self.cursor.execute(q, params)
        return self.cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.cursor.close()
        self.conn.close()

def get_db():
    return DBMock()

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def init_db():
    try:
        Base.metadata.create_all(engine)
        
        db = get_db()
        try:
            db.execute("ALTER TABLE doctors MODIFY hospital_id INT NULL")
        except: pass
        try:
            db.execute("ALTER TABLE doctors ADD COLUMN professional_id VARCHAR(100) NULL")
        except: pass
        try:
            db.execute("ALTER TABLE doctors MODIFY work_start VARCHAR(50) NULL")
            db.execute("ALTER TABLE doctors MODIFY work_end VARCHAR(50) NULL")
        except: pass
        
        for col, col_def in [
            ("address", "VARCHAR(255) NULL"),
            ("city", "VARCHAR(100) NULL"),
            ("state", "VARCHAR(100) NULL"),
            ("pincode", "VARCHAR(20) NULL"),
            ("latitude", "VARCHAR(50) NULL"),
            ("longitude", "VARCHAR(50) NULL")
        ]:
            try:
                db.execute(f"ALTER TABLE hospitals ADD COLUMN {col} {col_def}")
            except:
                pass
                
        db.commit()
        
        seed_data(db)
        db.commit()
        db.close()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def seed_data(cur):
    hospitals = [
        ("City General Hospital", "Downtown MG Road", None, None, None, None, None, None),
        ("Sunrise Medical Center", "Koramangala 4th Block", None, None, None, None, None, None),
        ("Apollo Hospitals, Bannerghatta Road", "Bannerghatta Road, Bengaluru", "IIM, 154/11, Bannerghatta Road, opposite Krishnaraju Layout, Panduranga Nagar", "Bengaluru", "Karnataka", "560076", "12.8961", "77.5985"),
        ("Apollo Speciality Hospital, Jayanagar", "Jayanagar, Bengaluru", "14th Cross Road, 212, Dr Parvathamma Rajkumar Road, near Madhavan Park Circle, 3rd Block, Jayanagar", "Bengaluru", "Karnataka", "560011", "12.9328", "77.5815"),
        ("Apollo Hospitals, Seshadripuram", "Seshadripuram, Bengaluru", "Old No. 28, 1, Platform Road, near Mantri Square Mall, Seshadripuram", "Bengaluru", "Karnataka", "560020", "12.9880", "77.5750"),
        ("Apollo Hospitals, Sarjapur Road", "Sarjapur Road, Bengaluru", "Opposite Decathlon, Sarjapur Road, Mulluru Hobli", "Bengaluru", "Karnataka", "560035", "12.8950", "77.7125"),
    ]
    hosp_map = {}
    for name, loc, addr, city, state, pin, lat, lon in hospitals:
        existing = cur.execute("SELECT id FROM hospitals WHERE name=?", (name,)).fetchone()
        if not existing:
            cur.execute("INSERT INTO hospitals (name, location, address, city, state, pincode, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (name, loc, addr, city, state, pin, lat, lon))
            hosp_id = cur.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
        else:
            hosp_id = existing["id"]
            cur.execute("UPDATE hospitals SET location=?, address=?, city=?, state=?, pincode=?, latitude=?, longitude=? WHERE id=?", (loc, addr, city, state, pin, lat, lon, hosp_id))
        hosp_map[name] = hosp_id

    doctors = [
        ("Dr. Priya Sharma", "Cardiology", "City General Hospital", "09:00", "17:00", "0,1,2,3,4"),
        ("Dr. Rahul Mehta", "Orthopedics", "City General Hospital", "09:00", "17:00", "0,1,2,3,4"),
        ("Dr. Ananya Iyer", "Pediatrics", "Sunrise Medical Center", "09:00", "17:00", "0,1,2,3,4"),
        ("Dr. Suresh Kumar", "General Medicine", "Sunrise Medical Center", "09:00", "17:00", "0,1,2,3,4"),
    ]
    for name, spec, hosp_name, start, end, days in doctors:
        existing = cur.execute("SELECT id FROM doctors WHERE name=? AND specialty=?", (name, spec)).fetchone()
        if not existing:
            cur.execute(
                "INSERT INTO doctors (name, specialty, hospital_id, work_start, work_end, work_days) VALUES (?, ?, ?, ?, ?, ?)",
                (name, spec, hosp_map[hosp_name], start, end, days),
            )
        else:
            cur.execute(
                "UPDATE doctors SET work_start=?, work_end=?, work_days=? WHERE id=?",
                (start, end, days, existing["id"])
            )

    new_doctors = [
        ("Dr. Revathi", "Neurology", "Apollo Speciality Hospital, Jayanagar", "revathimurala@gmail.com"),
        ("Dr. Suzanne", "Cardiology", "Apollo Hospitals, Bannerghatta Road", "skathyrene@gmail.com"),
        ("Dr. Charitha", "Eye Specialist", "Apollo Hospitals, Seshadripuram", "charithapolavarapu@gmail.com"),
        ("Dr. Hansika", "Gynecologist", "Apollo Hospitals, Sarjapur Road", "hansikakommina@gmail.com"),
    ]
    
    for name, spec, hosp_name, email in new_doctors:
        hosp_id = hosp_map.get(hosp_name)
        existing = cur.execute("SELECT id FROM doctors WHERE name=?", (name,)).fetchone()
        if not existing:
            cur.execute("INSERT INTO doctors (name, specialty, hospital_id, work_start, work_end, work_days) VALUES (?, ?, ?, '09:00', '17:00', '0,1,2,3,4')", (name, spec, hosp_id))
            doc_id = cur.execute("SELECT LAST_INSERT_ID() as id").fetchone()["id"]
        else:
            doc_id = existing["id"]
            cur.execute("UPDATE doctors SET specialty=?, hospital_id=?, work_start='09:00', work_end='17:00', work_days='0,1,2,3,4' WHERE id=?", (spec, hosp_id, doc_id))
            
        existing_user = cur.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not existing_user:
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role, doctor_id) VALUES (?, ?, ?, 'doctor', ?)",
                (name, email, hash_password("default123"), doc_id)
            )

    patients = [
        ("Arun Patel", "arun@example.com", "patient123"),
        ("Deepa Singh", "deepa@example.com", "patient123"),
        ("Vikram Rao", "vikram@example.com", "patient123"),
    ]
    for name, email, pw in patients:
        existing = cur.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if not existing:
            cur.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'patient')",
                (name, email, hash_password(pw)),
            )

if __name__ == "__main__":
    init_db()