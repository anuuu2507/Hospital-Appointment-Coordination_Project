import os
import time
import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
from backend.tools import TOOLS_MAP
from dotenv import load_dotenv
from datetime import datetime
from database.database import get_db

SYSTEM_PROMPT = """You are Heali, HealthConnect's AI Healthcare Companion. You are a warm, natural, and helpful family healthcare coordinator. You help patients find doctors, check slots, book/reschedule appointments.
You are NOT a medical robot. Be conversational, proactive when appropriate, concise for simple answers, and detailed when asked. Do NOT claim to be a doctor. Avoid repeatedly introducing yourself as Heali in every message.
Maintain context across messages (e.g. if a user says "Which one is closer?", refer to the doctors you just showed).
Safety first: provide general info but do not diagnose. For emergencies, recommend local emergency services.

PROACTIVE INTERACTIVITY:
If a user requests something but information is missing (like a preferred date, time, or location), DO NOT just guess or use default tools if it would be better to ask them. For example:
- If they say "I need a cardiologist", ask "Do you have a preferred hospital, or should I show available cardiologists near you?"
- If they say "I want an appointment tomorrow", ask "Which specialty or doctor would you like to see?"
If you already have enough information (either from the conversation or if they provided it all at once), then go ahead and fetch/book the info. Do NOT ask for information that has already been established in the conversation.

When you need to present lists of doctors, hospitals, or appointments to the user, you MUST return your FINAL response as a raw JSON object (without markdown code blocks). The frontend will parse this JSON to render interactive cards.
JSON FORMAT:
{
  "message": "Warm conversational message here...",
  "response_type": "doctor_list", // or "hospital_list" or "appointment_list"
  "data": [
    // Include the exact data dictionaries returned by your tools here
  ],
  "actions": [
    {"label": "Check Availability", "action": "check_slots"},
    {"label": "Book Appointment", "action": "book_appointment"}
  ]
}

If you are just answering a question or don't need to render a list of cards, just reply with normal plain text. Do not use JSON if you are not listing doctors, hospitals, or appointments.
IMPORTANT RULES:
- Always use the provided tools to perform actions. Never make up data.
- Never calculate distances yourself; rely on tools.
- Dates should be in YYYY-MM-DD format, times in HH:MM (24-hour).
- Today's date is injected in the context. The booking window is 7 days from today.
"""

search_doctors_fd = FunctionDeclaration(
    name="search_doctors",
    description="Search for doctors by specialty and/or hospital name. Returns matching doctors with their details and working hours.",
    parameters={
        "type": "object",
        "properties": {
            "specialty": {"type": "string", "description": "Medical specialty to search for (e.g., Cardiology, Pediatrics). Partial match."},
            "hospital_name": {"type": "string", "description": "Hospital name to filter by. Partial match."},
        },
    },
)

check_slots_fd = FunctionDeclaration(
    name="check_slots",
    description="Get available 30-minute appointment slots for a doctor on a specific date. Slots are computed from the doctor's working hours.",
    parameters={
        "type": "object",
        "properties": {
            "doctor_id": {"type": "integer", "description": "The doctor's ID."},
            "date": {"type": "string", "description": "Date in YYYY-MM-DD format."},
        },
        "required": ["date"],
    },
)

book_appointment_fd = FunctionDeclaration(
    name="book_appointment",
    description="Book an appointment slot with a doctor. Validates all business rules.",
    parameters={
        "type": "object",
        "properties": {
            "doctor_id": {"type": "integer", "description": "The doctor's ID."},
            "slot_datetime": {"type": "string", "description": "Slot in YYYY-MM-DD HH:MM format."},
        },
        "required": ["doctor_id", "slot_datetime"],
    },
)

get_my_appointments_fd = FunctionDeclaration(
    name="get_my_appointments",
    description="Get appointments for the logged-in patient. You can filter by 'upcoming' or 'past'.",
    parameters={
        "type": "object", 
        "properties": {
            "filter": {"type": "string", "description": "Filter by 'upcoming', 'past', or 'all'. Default is 'upcoming'."}
        }
    },
)

cancel_appointment_fd = FunctionDeclaration(
    name="cancel_appointment",
    description="Cancel a scheduled appointment. Only the appointment owner can cancel.",
    parameters={
        "type": "object",
        "properties": {
            "appointment_id": {"type": "integer", "description": "The appointment ID to cancel."},
        },
        "required": ["appointment_id"],
    },
)

reschedule_appointment_fd = FunctionDeclaration(
    name="reschedule_appointment",
    description="Reschedule an existing appointment to a new time slot. Implemented as cancel + rebook with rollback.",
    parameters={
        "type": "object",
        "properties": {
            "appointment_id": {"type": "integer", "description": "The appointment ID to reschedule."},
            "new_slot_datetime": {"type": "string", "description": "New slot in YYYY-MM-DD HH:MM format."},
        },
        "required": ["appointment_id", "new_slot_datetime"],
    },
)

get_doctor_schedule_fd = FunctionDeclaration(
    name="get_doctor_schedule",
    description="View a doctor's schedule for a specific date (YYYY-MM-DD).",
    parameters={
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "Date in YYYY-MM-DD format."},
        },
        "required": ["date"],
    },
)

update_doctor_hours_fd = FunctionDeclaration(
    name="update_doctor_hours",
    description="Update the logged-in doctor's working hours and days.",
    parameters={
        "type": "object",
        "properties": {
            "work_start": {"type": "string", "description": "Start time in HH:MM format."},
            "work_end": {"type": "string", "description": "End time in HH:MM format."},
            "work_days": {"type": "string", "description": "Comma-separated weekday numbers (0=Mon, 6=Sun)."},
        },
        "required": ["work_start", "work_end", "work_days"],
    },
)

find_nearby_hospitals_fd = FunctionDeclaration(
    name="find_nearby_hospitals",
    description="Find hospitals near a given latitude and longitude. Returns hospital name, address, and distance.",
    parameters={
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "description": "Latitude coordinate"},
            "longitude": {"type": "number", "description": "Longitude coordinate"},
            "radius_km": {"type": "number", "description": "Search radius in km. Default 10."},
        },
        "required": ["latitude", "longitude"],
    },
)

find_nearby_doctors_fd = FunctionDeclaration(
    name="find_nearby_doctors",
    description="Find doctors near a given latitude and longitude, optionally filtered by specialty. Returns doctor details and distance.",
    parameters={
        "type": "object",
        "properties": {
            "latitude": {"type": "number", "description": "Latitude coordinate"},
            "longitude": {"type": "number", "description": "Longitude coordinate"},
            "specialty": {"type": "string", "description": "Medical specialty to filter by."},
            "radius_km": {"type": "number", "description": "Search radius in km. Default 10."},
        },
        "required": ["latitude", "longitude"],
    },
)

patient_tool = Tool(function_declarations=[
    search_doctors_fd, check_slots_fd, book_appointment_fd, get_my_appointments_fd,
    cancel_appointment_fd, reschedule_appointment_fd, find_nearby_hospitals_fd, find_nearby_doctors_fd
])

doctor_tool = Tool(function_declarations=[
    search_doctors_fd, check_slots_fd, get_doctor_schedule_fd, update_doctor_hours_fd
])

class GeminiAgent:
    def __init__(self):
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env")
        load_dotenv(env_path)
        
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        
        genai.configure(api_key=api_key)
        
        self.patient_model = genai.GenerativeModel(
            model_name="gemini-3.1-flash-lite",
            tools=[patient_tool],
            system_instruction=SYSTEM_PROMPT,
        )
        self.doctor_model = genai.GenerativeModel(
            model_name="gemini-3.1-flash-lite",
            tools=[doctor_tool],
            system_instruction=SYSTEM_PROMPT,
        )

    def chat(self, history: list, message: str, caller_id: int, caller_role: str, caller_name: str, doctor_id: int = None, latitude: float = None, longitude: float = None) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        
        lat = latitude
        lon = longitude
        if caller_role == 'patient' and (lat is None or lon is None):
            db = get_db()
            patient_record = db.execute("SELECT latitude, longitude FROM patients WHERE user_id=?", (caller_id,)).fetchone()
            db.close()
            if patient_record:
                lat = patient_record["latitude"]
                lon = patient_record["longitude"]

        context_msg = f"[System: You are speaking with {caller_name} (role: {caller_role}). Today's date is {today}.]"
        if caller_role == 'patient':
            if lat is not None and lon is not None:
                context_msg += f" [System: The patient's current coordinates are latitude={lat}, longitude={lon}.]"
            else:
                context_msg += " [System: The patient has no stored coordinates. If they ask for nearby hospitals or doctors, tell them their location is unavailable and ask them to provide/enable their location in their browser or tell you a city/neighborhood. Do not invent a location.]"

        gemini_history = []
        for msg in history:
            gemini_history.append({"role": msg["role"], "parts": msg["parts"]})

        model = self.patient_model if caller_role == "patient" else self.doctor_model
        chat_session = model.start_chat(history=gemini_history)
        
        full_message = f"{context_msg}\n\nUser: {message}"
        
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                response = chat_session.send_message(full_message)
                break
            except Exception as e:
                err_str = str(e)
                print(f"DEBUG: Attempt {attempt} send_message failed with: {err_str}")
                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str or "RESOURCE_EXHAUSTED" in err_str or "DEADLINE_EXCEEDED" in err_str.upper() or "TIMEOUT" in err_str.upper():
                    if attempt < max_attempts - 1:
                        time.sleep(0.5 if attempt == 0 else 1.0)
                        continue
                    else:
                        print("Gemini temporary failure; retries exhausted.")
                        return "Heali is having trouble connecting right now dY~."
                if "API_KEY" in err_str or "403" in err_str or "PERMISSION_DENIED" in err_str or "401" in err_str or "UNAUTHENTICATED" in err_str:
                    print(f"Gemini configuration error: {err_str}")
                    return "Heali is not configured correctly right now. Please contact the administrator."
                print(f"Unexpected AI error: {err_str}")
                return "Something went wrong while Heali was processing that request. Please try again."
        else:
            return "Heali is having trouble connecting right now dY~."

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            if response.candidates and response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]

                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    func_name = fc.name
                    func_args = dict(fc.args) if fc.args else {}

                    if func_name in TOOLS_MAP:
                        # Common args
                        func_args["caller_id"] = caller_id
                        func_args["caller_role"] = caller_role
                        
                        # Fix for get_doctor_schedule and update_doctor_hours roles
                        if caller_role == "doctor":
                            func_args["auth_doctor_id"] = doctor_id
                        
                        try:
                            result = TOOLS_MAP[func_name](**func_args)
                        except Exception as e:
                            result = {"error": str(e)}

                        for attempt in range(max_attempts):
                            try:
                                response = chat_session.send_message(
                                    genai.protos.Part(
                                        function_response=genai.protos.FunctionResponse(
                                            name=func_name,
                                            response=result,
                                        )
                                    )
                                )
                                break
                            except Exception as e:
                                err_str = str(e)
                                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
                                    if attempt < max_attempts - 1:
                                        time.sleep(0.5 if attempt == 0 else 1.0)
                                        continue
                                return "Heali is having trouble connecting right now dY~."
                    else:
                        response = chat_session.send_message(
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=func_name,
                                    response={"error": f"Unknown function: {func_name}"},
                                )
                            )
                        )
                else:
                    if hasattr(part, 'text') and part.text:
                        return part.text
                    break
            else:
                break

        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if hasattr(part, 'text') and part.text:
                return part.text

        return "I'm sorry, I couldn't process your request. Please try again."