import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from tools import TOOLS_MAP
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = """You are a helpful hospital appointment booking assistant. You help patients find doctors, check available slots, book/reschedule/cancel appointments. You also help doctors manage their schedules.

IMPORTANT RULES:
- Always use the provided tools to perform actions. Never make up data.
- For patients: you can search_doctors, check_slots, book_appointment, get_my_appointments, cancel_appointment, reschedule_appointment.
- For doctors: you can get_doctor_schedule, update_doctor_hours, search_doctors, check_slots.
- Never reveal other patients' information.
- Dates should be in YYYY-MM-DD format, times in HH:MM (24-hour).
- Today's date is injected in the context. The booking window is 7 days from today.
"""

class GeminiAgent:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")
        
        self.llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0, google_api_key=api_key)

    def chat(self, history: list, message: str, caller_id: int, caller_role: str, caller_name: str, doctor_id: int = None) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        context_msg = f"You are speaking with {caller_name} (role: {caller_role}). Today's date is {today}."

        def search_doctors(specialty: str = None, hospital_name: str = None):
            """Search for doctors by specialty and/or hospital name. Returns matching doctors with their details and working hours."""
            return TOOLS_MAP["search_doctors"](specialty=specialty, hospital_name=hospital_name)

        def check_slots(doc_id: int, date: str):
            """Get available 30-minute appointment slots for a doctor on a specific date (YYYY-MM-DD)."""
            return TOOLS_MAP["check_slots"](doctor_id=doc_id, date=date)

        def book_appointment(doc_id: int, slot_datetime: str):
            """Book an appointment slot with a doctor. Slot in YYYY-MM-DD HH:MM."""
            return TOOLS_MAP["book_appointment"](doctor_id=doc_id, slot_datetime=slot_datetime, caller_id=caller_id)

        def get_my_appointments():
            """Get all appointments for the logged-in patient."""
            return TOOLS_MAP["get_my_appointments"](caller_id=caller_id)

        def cancel_appointment(appointment_id: int):
            """Cancel a scheduled appointment."""
            return TOOLS_MAP["cancel_appointment"](appointment_id=appointment_id, caller_id=caller_id)

        def reschedule_appointment(appointment_id: int, new_slot_datetime: str):
            """Reschedule an existing appointment to a new time slot."""
            return TOOLS_MAP["reschedule_appointment"](appointment_id=appointment_id, new_slot_datetime=new_slot_datetime, caller_id=caller_id)

        def get_doctor_schedule(date: str):
            """View the logged-in doctor's schedule for a specific date (YYYY-MM-DD)."""
            return TOOLS_MAP["get_doctor_schedule"](doctor_id=doctor_id, date=date, caller_role=caller_role)

        def update_doctor_hours(work_start: str, work_end: str, work_days: str):
            """Update the logged-in doctor's working hours and days. work_days is comma-separated numbers (0=Mon, 6=Sun)"""
            return TOOLS_MAP["update_doctor_hours"](doctor_id=doctor_id, work_start=work_start, work_end=work_end, work_days=work_days, caller_role=caller_role)

        tools = [
            StructuredTool.from_function(search_doctors),
            StructuredTool.from_function(check_slots),
        ]
        
        if caller_role == "patient":
            tools.extend([
                StructuredTool.from_function(book_appointment),
                StructuredTool.from_function(get_my_appointments),
                StructuredTool.from_function(cancel_appointment),
                StructuredTool.from_function(reschedule_appointment),
            ])
        elif caller_role == "doctor":
            tools.extend([
                StructuredTool.from_function(get_doctor_schedule),
                StructuredTool.from_function(update_doctor_hours),
            ])

        agent = create_react_agent(self.llm, tools=tools, state_modifier=SYSTEM_PROMPT + "\n" + context_msg)
        
        lc_history = []
        for msg in history:
            if msg["role"] == "user":
                lc_history.append(HumanMessage(content=msg["parts"][0]))
            else:
                lc_history.append(AIMessage(content=msg["parts"][0]))
        lc_history.append(HumanMessage(content=message))
                
        try:
            result = agent.invoke({"messages": lc_history})
            return result["messages"][-1].content
        except Exception as e:
            return f"I'm sorry, I encountered an error: {str(e)}"