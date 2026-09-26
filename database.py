import sqlite3
import bcrypt

DB_PATH = "hospital_booking.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('patient', 'staff'))
        );

        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            specialty TEXT NOT NULL,
            hospital_id INTEGER NOT NULL REFERENCES hospitals(id),
            work_start TEXT NOT NULL,
            work_end TEXT NOT NULL,
            work_days TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id),
            doctor_id INTEGER NOT NULL REFERENCES doctors(id),
            slot_datetime TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('scheduled', 'cancelled', 'completed')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(doctor_id, slot_datetime, status)
        );
    """)

    existing = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing == 0:
        seed_data(cur)

    conn.commit()
    conn.close()


def seed_data(cur):
    patients = [
        ("Arun Patel", "arun@example.com", "patient123"),
        ("Deepa Singh", "deepa@example.com", "patient123"),
        ("Vikram Rao", "vikram@example.com", "patient123"),
    ]
    for name, email, pw in patients:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'patient')",
            (name, email, hash_password(pw)),
        )

    cur.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'staff')",
        ("Staff Admin", "staff@hospital.com", hash_password("staff123")),
    )

    hospitals = [
        ("City General Hospital", "Downtown MG Road"),
        ("Sunrise Medical Center", "Koramangala 4th Block"),
    ]
    for name, loc in hospitals:
        cur.execute("INSERT INTO hospitals (name, location) VALUES (?, ?)", (name, loc))

    doctors = [
        ("Dr. Priya Sharma", "Cardiology", 1, "09:00", "17:00", "0,1,2,3,4"),
        ("Dr. Rahul Mehta", "Orthopedics", 1, "10:00", "18:00", "0,1,2,3,4"),
        ("Dr. Ananya Iyer", "Pediatrics", 2, "08:00", "14:00", "0,1,2,3,4"),
        ("Dr. Suresh Kumar", "General Medicine", 2, "09:00", "17:00", "0,2,4"),
    ]
    for name, spec, hosp_id, start, end, days in doctors:
        cur.execute(
            "INSERT INTO doctors (name, specialty, hospital_id, work_start, work_end, work_days) VALUES (?, ?, ?, ?, ?, ?)",
            (name, spec, hosp_id, start, end, days),
        )


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")