from datetime import datetime, timedelta
from database.database import get_db

BOOKING_WINDOW_DAYS = 7


def _now():
    return datetime.now()


def _today_str():
    return _now().strftime("%Y-%m-%d")


def _weekday_name(n):
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][n]


def search_doctors(specialty: str = None, hospital_name: str = None, **_):
    db = get_db()
    query = """
        SELECT d.id, d.name, d.specialty, h.name as hospital, h.location,
               d.work_start, d.work_end, d.work_days
        FROM doctors d JOIN hospitals h ON d.hospital_id = h.id
        WHERE 1=1
    """
    params = []
    if specialty:
        query += " AND LOWER(d.specialty) LIKE ?"
        params.append(f"%{specialty.lower()}%")
    if hospital_name:
        query += " AND LOWER(h.name) LIKE ?"
        params.append(f"%{hospital_name.lower()}%")

    rows = db.execute(query, params).fetchall()
    db.close()

    if not rows:
        return {"doctors": [], "message": "No doctors found matching your criteria."}

    doctors = []
    for r in rows:
        days = [int(d) for d in r["work_days"].split(",") if d]
        day_names = [_weekday_name(d) for d in days]
        doctors.append({
            "id": r["id"],
            "name": r["name"],
            "specialty": r["specialty"],
            "hospital": r["hospital"],
            "location": r["location"],
            "work_start": r["work_start"],
            "work_end": r["work_end"],
            "work_days": ", ".join(day_names),
        })
    return {"doctors": doctors}


def check_slots(doctor_id: int, date: str, **_):
    db = get_db()

    doctor = db.execute(
        "SELECT d.*, h.name as hospital FROM doctors d JOIN hospitals h ON d.hospital_id=h.id WHERE d.id=?",
        (doctor_id,)
    ).fetchone()
    if not doctor:
        db.close()
        return {"error": "Doctor not found."}

    try:
        req_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        db.close()
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    today = _now().date()
    max_date = today + timedelta(days=BOOKING_WINDOW_DAYS)
    if req_date < today:
        db.close()
        return {"error": "Cannot check slots for a past date."}
    if req_date > max_date:
        db.close()
        return {"error": f"Slots are only available within {BOOKING_WINDOW_DAYS} days from today."}

    weekday = req_date.weekday()
    work_days = [int(d) for d in doctor["work_days"].split(",") if d]
    if weekday not in work_days:
        db.close()
        return {"error": f"Dr. {doctor['name']} does not work on {_weekday_name(weekday)}s."}

    work_start = datetime.strptime(doctor["work_start"], "%H:%M")
    work_end = datetime.strptime(doctor["work_end"], "%H:%M")

    all_slots = []
    current = work_start
    while current + timedelta(minutes=30) <= work_end:
        slot_str = current.strftime("%H:%M")
        # Hardcode lunch break
        if not ("11:30" <= slot_str < "13:00"):
            all_slots.append(slot_str)
        current += timedelta(minutes=30)

    booked = db.execute(
        "SELECT slot_datetime FROM appointments WHERE doctor_id=? AND slot_datetime LIKE ? AND status='scheduled'",
        (doctor_id, f"{date}%")
    ).fetchall()
    booked_times = set()
    for b in booked:
        booked_times.add(b["slot_datetime"].split(" ")[1])

    now = _now()
    free_slots = []
    for slot in all_slots:
        if slot in booked_times:
            continue
        if req_date == today:
            slot_time = datetime.strptime(f"{date} {slot}", "%Y-%m-%d %H:%M")
            if slot_time <= now:
                continue
        free_slots.append(f"{date} {slot}")

    db.close()
    return {"doctor": doctor["name"], "date": date, "free_slots": free_slots}


def book_appointment(doctor_id: int, slot_datetime: str, caller_id: int, **_):
    db = get_db()

    doctor = db.execute(
        "SELECT d.*, h.name as hospital FROM doctors d JOIN hospitals h ON d.hospital_id=h.id WHERE d.id=?",
        (doctor_id,)
    ).fetchone()
    if not doctor:
        db.close()
        return {"error": "Doctor not found."}

    try:
        slot_dt = datetime.strptime(slot_datetime, "%Y-%m-%d %H:%M")
    except ValueError:
        db.close()
        return {"error": "Invalid datetime format. Use YYYY-MM-DD HH:MM."}

    now = _now()
    if slot_dt <= now:
        db.close()
        return {"error": "Cannot book a slot in the past."}

    today = now.date()
    max_date = today + timedelta(days=BOOKING_WINDOW_DAYS)
    if slot_dt.date() > max_date:
        db.close()
        return {"error": f"Booking window is {BOOKING_WINDOW_DAYS} days from today."}

    weekday = slot_dt.weekday()
    work_days = [int(d) for d in doctor["work_days"].split(",") if d]
    if weekday not in work_days:
        db.close()
        return {"error": f"Dr. {doctor['name']} does not work on {_weekday_name(weekday)}s."}

    work_start = datetime.strptime(doctor["work_start"], "%H:%M").time()
    work_end = datetime.strptime(doctor["work_end"], "%H:%M").time()
    
    slot_time = slot_dt.time()
    if slot_time < work_start or slot_time >= work_end:
        db.close()
        return {"error": f"Slot is outside working hours ({doctor['work_start']}-{doctor['work_end']})."}

    lunch_start = datetime.strptime("11:30", "%H:%M").time()
    lunch_end = datetime.strptime("13:00", "%H:%M").time()
    if lunch_start <= slot_time < lunch_end:
        db.close()
        return {"error": "Slot falls within the lunch break (11:30-13:00)."}

    if slot_time.minute % 30 != 0:
        db.close()
        return {"error": "Slots must align to 30-minute intervals."}

    existing = db.execute(
        "SELECT id FROM appointments WHERE doctor_id=? AND slot_datetime=? AND status='scheduled'",
        (doctor_id, slot_datetime)
    ).fetchone()
    if existing:
        db.close()
        return {"error": "This slot is already booked."}

    cur = db.execute(
        "INSERT INTO appointments (patient_id, doctor_id, slot_datetime, status) VALUES (?, ?, ?, 'scheduled')",
        (caller_id, doctor_id, slot_datetime)
    )
    db.commit()
    appt_id = cur.lastrowid
    db.close()

    return {
        "appointment_id": appt_id,
        "doctor": doctor["name"],
        "hospital": doctor["hospital"],
        "slot_datetime": slot_datetime,
        "status": "scheduled",
        "message": f"Appointment confirmed with {doctor['name']} at {slot_datetime}.",
    }


def get_my_appointments(caller_id: int, **_):
    db = get_db()
    rows = db.execute("""
        SELECT a.id, a.slot_datetime, a.status, d.name as doctor, d.specialty,
               h.name as hospital
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN hospitals h ON d.hospital_id = h.id
        WHERE a.patient_id = ?
        ORDER BY a.slot_datetime ASC
    """, (caller_id,)).fetchall()
    db.close()

    appointments = [{
        "appointment_id": r["id"],
        "slot_datetime": r["slot_datetime"],
        "status": r["status"],
        "doctor": r["doctor"],
        "specialty": r["specialty"],
        "hospital": r["hospital"],
    } for r in rows]

    return {"appointments": appointments}


def cancel_appointment(appointment_id: int, caller_id: int, **_):
    db = get_db()

    appt = db.execute(
        "SELECT * FROM appointments WHERE id=?", (appointment_id,)
    ).fetchone()
    if not appt:
        db.close()
        return {"error": "Appointment not found."}

    if appt["patient_id"] != caller_id:
        db.close()
        return {"error": "You can only cancel your own appointments."}

    if appt["status"] != "scheduled":
        db.close()
        return {"error": f"Cannot cancel appointment with status '{appt['status']}'."}

    db.execute(
        "UPDATE appointments SET status='cancelled' WHERE id=?",
        (appointment_id,)
    )
    db.commit()
    db.close()

    return {"message": f"Appointment {appointment_id} has been cancelled."}


def reschedule_appointment(appointment_id: int, new_slot_datetime: str, caller_id: int, **_):
    db = get_db()

    appt = db.execute(
        "SELECT * FROM appointments WHERE id=?", (appointment_id,)
    ).fetchone()
    if not appt:
        db.close()
        return {"error": "Appointment not found."}

    if appt["patient_id"] != caller_id:
        db.close()
        return {"error": "You can only reschedule your own appointments."}

    if appt["status"] != "scheduled":
        db.close()
        return {"error": f"Cannot reschedule appointment with status '{appt['status']}'."}

    doctor_id = appt["doctor_id"]
    old_slot = appt["slot_datetime"]

    db.execute(
        "UPDATE appointments SET status='cancelled' WHERE id=?",
        (appointment_id,)
    )
    db.commit()
    db.close()

    result = book_appointment(doctor_id=doctor_id, slot_datetime=new_slot_datetime, caller_id=caller_id)

    if "error" in result:
        db = get_db()
        db.execute(
            "UPDATE appointments SET status='scheduled' WHERE id=?",
            (appointment_id,)
        )
        db.commit()
        db.close()
        return {"error": f"Reschedule failed: {result['error']}. Original appointment restored."}

    return {
        "message": f"Appointment rescheduled from {old_slot} to {new_slot_datetime}.",
        "new_appointment_id": result["appointment_id"],
        "doctor": result["doctor"],
    }


def get_doctor_schedule(doctor_id: int, date: str, caller_role: str, auth_doctor_id: int = None, **_):
    if caller_role == "doctor":
        if str(doctor_id) != str(auth_doctor_id) and doctor_id != auth_doctor_id:
            return {"error": "Doctors can only view their own schedules."}
    elif caller_role != "staff":
        return {"error": "Only staff or the doctor themselves can view doctor schedules."}

    db = get_db()

    doctor = db.execute(
        "SELECT d.*, h.name as hospital FROM doctors d JOIN hospitals h ON d.hospital_id=h.id WHERE d.id=?",
        (doctor_id,)
    ).fetchone()
    if not doctor:
        db.close()
        return {"error": "Doctor not found."}

    rows = db.execute("""
        SELECT a.slot_datetime, a.status, u.name as patient_name, u.email as patient_email
        FROM appointments a JOIN users u ON a.patient_id = u.id
        WHERE a.doctor_id=? AND a.slot_datetime LIKE ?
        ORDER BY a.slot_datetime ASC
    """, (doctor_id, f"{date}%")).fetchall()
    db.close()

    schedule = [{
        "slot": r["slot_datetime"].split(" ")[1] if " " in r["slot_datetime"] else r["slot_datetime"],
        "patient_name": r["patient_name"],
        "patient_email": r["patient_email"],
        "status": r["status"],
    } for r in rows]

    return {
        "doctor": doctor["name"],
        "date": date,
        "appointments": schedule,
    }


def list_all_doctors(caller_role: str, **_):
    if caller_role != "staff":
        return {"error": "Only staff can list all doctors."}

    db = get_db()
    rows = db.execute("""
        SELECT d.id, d.name, d.specialty, h.name as hospital,
               d.work_start, d.work_end, d.work_days
        FROM doctors d JOIN hospitals h ON d.hospital_id = h.id
    """).fetchall()
    db.close()

    doctors = []
    for r in rows:
        days = [int(d) for d in r["work_days"].split(",") if d]
        day_names = [_weekday_name(d) for d in days]
        doctors.append({
            "id": r["id"],
            "name": r["name"],
            "specialty": r["specialty"],
            "hospital": r["hospital"],
            "work_start": r["work_start"],
            "work_end": r["work_end"],
            "work_days": ", ".join(day_names),
        })

    return {"doctors": doctors}


def update_doctor_hours(doctor_id: int, work_start: str, work_end: str, work_days: str, caller_role: str, auth_doctor_id: int = None, **_):
    if caller_role == "doctor":
        if str(doctor_id) != str(auth_doctor_id) and doctor_id != auth_doctor_id:
            return {"error": "Doctors can only update their own hours."}
    elif caller_role != "staff":
        return {"error": "Only staff or the doctor themselves can update doctor hours."}

    db = get_db()

    doctor = db.execute("SELECT * FROM doctors WHERE id=?", (doctor_id,)).fetchone()
    if not doctor:
        db.close()
        return {"error": "Doctor not found."}

    try:
        datetime.strptime(work_start, "%H:%M")
        datetime.strptime(work_end, "%H:%M")
    except ValueError:
        db.close()
        return {"error": "Invalid time format. Use HH:MM."}

    day_list = [d.strip() for d in work_days.split(",")]
    for d in day_list:
        if not d.isdigit() or int(d) < 0 or int(d) > 6:
            db.close()
            return {"error": "work_days must be comma-separated numbers 0-6 (0=Mon, 6=Sun)."}

    db.execute(
        "UPDATE doctors SET work_start=?, work_end=?, work_days=? WHERE id=?",
        (work_start, work_end, work_days, doctor_id)
    )
    db.commit()
    db.close()

    day_names = [_weekday_name(int(d)) for d in day_list]
    return {
        "message": f"Dr. {doctor['name']} updated to {work_start}-{work_end}, {', '.join(day_names)}.",
    }


import math

def haversine(lat1, lon1, lat2, lon2):
    if not lat1 or not lon1 or not lat2 or not lon2:
        return float('inf')
    R = 6371.0
    try:
        lat1_rad = math.radians(float(lat1))
        lon1_rad = math.radians(float(lon1))
        lat2_rad = math.radians(float(lat2))
        lon2_rad = math.radians(float(lon2))
    except (ValueError, TypeError):
        return float('inf')

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def find_nearby_hospitals(latitude: float, longitude: float, radius_km: float = 10, **_):
    db = get_db()
    rows = db.execute("SELECT * FROM hospitals").fetchall()
    db.close()
    
    nearby = []
    for r in rows:
        if r["latitude"] and r["longitude"]:
            dist = haversine(latitude, longitude, r["latitude"], r["longitude"])
            if dist <= radius_km:
                nearby.append({
                    "id": r["id"],
                    "name": r["name"],
                    "location": r["location"],
                    "address": r["address"],
                    "distance_km": round(dist, 2)
                })
    
    nearby.sort(key=lambda x: x["distance_km"])
    return {"hospitals": nearby}

def find_nearby_doctors(latitude: float, longitude: float, specialty: str = None, radius_km: float = 10, **_):
    db = get_db()
    query = """
        SELECT d.id, d.name, d.specialty, h.name as hospital, h.location, h.address, h.latitude, h.longitude,
               d.work_start, d.work_end, d.work_days
        FROM doctors d JOIN hospitals h ON d.hospital_id = h.id
        WHERE h.latitude IS NOT NULL AND h.longitude IS NOT NULL
    """
    params = []
    if specialty:
        query += " AND LOWER(d.specialty) LIKE ?"
        params.append(f"%{specialty.lower()}%")
        
    rows = db.execute(query, params).fetchall()
    db.close()
    
    nearby = []
    for r in rows:
        dist = haversine(latitude, longitude, r["latitude"], r["longitude"])
        if dist <= radius_km:
            days = [int(d) for d in r["work_days"].split(",") if d] if r["work_days"] else []
            day_names = [_weekday_name(d) for d in days] if days else []
            nearby.append({
                "id": r["id"],
                "name": r["name"],
                "specialty": r["specialty"],
                "hospital": r["hospital"],
                "location": r["location"],
                "address": r["address"],
                "distance_km": round(dist, 2),
                "work_start": r["work_start"],
                "work_end": r["work_end"],
                "work_days": ", ".join(day_names) if day_names else ""
            })
            
    nearby.sort(key=lambda x: x["distance_km"])
    return {"doctors": nearby}

TOOLS_MAP = {
    "search_doctors": search_doctors,
    "check_slots": check_slots,
    "book_appointment": book_appointment,
    "get_my_appointments": get_my_appointments,
    "cancel_appointment": cancel_appointment,
    "reschedule_appointment": reschedule_appointment,
    "get_doctor_schedule": get_doctor_schedule,
    "list_all_doctors": list_all_doctors,
    "update_doctor_hours": update_doctor_hours,
    "find_nearby_hospitals": find_nearby_hospitals,
    "find_nearby_doctors": find_nearby_doctors,
}