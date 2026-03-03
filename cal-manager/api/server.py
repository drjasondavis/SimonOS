"""
FastAPI server consumed by the Gmail Chrome extension.

Endpoints:
  POST /schedule                            — smart scheduling (suggest times or create event)
  GET  /available-slots?duration=60&days=7  — raw available slots
  GET  /health                              — liveness check

Run with:
  uvicorn api.server:app --port 5555 --reload
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, quote

import anthropic
import pytz
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.models import Event, get_engine
import config

app = FastAPI(title="Cal Manager")

# Log all Anthropic calls to a file next to the server
_LOG_PATH = Path(__file__).parent / "anthropic_calls.log"
logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("anthropic_calls")
_fh = logging.FileHandler(_LOG_PATH)
_fh.setFormatter(logging.Formatter("%(asctime)s\n%(message)s\n" + "-" * 80))
_log.addHandler(_fh)


def _log_call(label: str, prompt: str, response: str):
    _log.info(f"=== {label} ===\n\nPROMPT:\n{prompt}\n\nRESPONSE:\n{response}")
    print(f"\n[anthropic:{label}] prompt sent ({len(prompt)} chars) → response ({len(response)} chars)")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mail.google.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Api-Secret", "Content-Type"],
)

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def _check_auth(secret: Optional[str]):
    if config.API_SECRET and secret != config.API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _anthropic_client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Free slot finder
# ---------------------------------------------------------------------------

# Hours (local, 24h) to search within for each context type.
# Each entry is a list of (window_start_hour, window_end_hour) pairs.
CONTEXT_WINDOWS = {
    "lunch":      [(11, 14)],          # 11am–2pm
    "happy_hour": [(17, 19)],          # 5pm–7pm
    "dinner":     [(18, 21)],          # 6pm–9pm
    "regular":    [(config.WORK_HOURS_START, config.WORK_HOURS_END)],
}


def _find_free_slots(
    duration_minutes: int,
    lookahead_days: int,
    travel_buffer_minutes: int = 0,
    context_type: str = "regular",
    earliest_date: Optional[str] = None,
    latest_date: Optional[str] = None,
) -> list[dict]:
    """
    Return up to 5 free slots.

    travel_buffer_minutes — for in-person meetings, extend the conflict check
      this many minutes before and after the proposed slot so surrounding
      meetings have breathing room for travel.

    context_type — narrows which hours are searched:
      "lunch"      → 11am–2pm
      "happy_hour" → 5pm–7pm
      "dinner"     → 6pm–9pm
      "regular"    → normal working hours
    """
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=lookahead_days)

    with Session(engine) as session:
        busy = (
            session.query(Event)
            .filter(
                Event.start >= now,
                Event.end <= end,
                Event.is_all_day == False,
            )
            .order_by(Event.start)
            .all()
        )

    buffer = timedelta(minutes=travel_buffer_minutes)
    windows = CONTEXT_WINDOWS.get(context_type, CONTEXT_WINDOWS["regular"])
    slots = []
    today = datetime.now(tz).date()

    from datetime import date as date_type
    def _parse_date(s):
        try:
            return date_type.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    min_start = today + timedelta(days=2)  # always at least 48 hours out
    day = max(_parse_date(earliest_date) or min_start, min_start)
    end_day = _parse_date(latest_date) or (today + timedelta(days=lookahead_days))

    while day <= end_day:
        if day.weekday() not in config.WORK_DAYS:
            day += timedelta(days=1)
            continue

        day_busy = [e for e in busy if e.start.astimezone(tz).date() == day]

        for (win_start_h, win_end_h) in windows:
            window_start = tz.localize(datetime(day.year, day.month, day.day, win_start_h))
            window_end   = tz.localize(datetime(day.year, day.month, day.day, win_end_h))

            cursor = window_start
            while cursor + timedelta(minutes=duration_minutes) <= window_end:
                slot_end = cursor + timedelta(minutes=duration_minutes)

                # For in-person meetings, expand the conflict window by the
                # travel buffer on both sides so adjacent meetings have room.
                check_start = cursor - buffer
                check_end   = slot_end + buffer
                conflict = any(e.start < check_end and e.end > check_start for e in day_busy)

                if not conflict:
                    slots.append({
                        "start": cursor.isoformat(),
                        "end": slot_end.isoformat(),
                        "display": cursor.strftime("%A, %B %-d at %-I:%M %p %Z"),
                        "is_in_person": travel_buffer_minutes > 0,
                    })
                    cursor = slot_end
                    if len(slots) >= 5:
                        return slots
                    # For social contexts, one suggestion per day is enough
                    if context_type in ("dinner", "happy_hour", "lunch"):
                        break
                else:
                    cursor += timedelta(minutes=15)

        day += timedelta(days=1)

    return slots


# ---------------------------------------------------------------------------
# Claude helpers
# ---------------------------------------------------------------------------

def _analyze_thread(subject: str, email_body: str, thread_context: str, participants: list = []) -> dict:
    """
    Ask Claude to determine mode, meeting type, and context.

    All responses include:
      is_in_person: bool
      context_type: "lunch" | "happy_hour" | "dinner" | "regular"

    Plus either:
      {"mode": "create", "title", "start_iso", "end_iso", "timezone", "location", "attendees"}
    or:
      {"mode": "suggest", "constraints": "..."}
    """
    today = datetime.now(tz).strftime("%A, %B %d, %Y")
    participants_str = ", ".join(participants) if participants else "(none detected)"
    prompt = f"""Analyze this email thread to help schedule a meeting. Today is {today} ({config.TIMEZONE}). Respond with JSON only — no explanation, no markdown.

Email subject: {subject or "(no subject)"}

User's draft:
{email_body or "(empty)"}

Prior thread (quoted messages):
{thread_context or "(no prior thread)"}

All email addresses seen in this thread:
{participants_str}

Answer these questions:

1. is_in_person: Is this an in-person meeting (true) or virtual/Zoom/phone (false)? Default false if unclear.

2. context_type: What kind of meeting is this?
   - "lunch"      → mentions lunch, meal, grab a bite, eat, restaurant
   - "happy_hour" → mentions drinks, happy hour, beer, cocktails, bar
   - "dinner"     → mentions dinner, evening meal, supper
   - "regular"    → any other work meeting, call, or unclear

3. attendees: From the list of email addresses above, select only the people who should actually attend this meeting. Exclude scheduling assistants, admins, or anyone who was only CC'd for coordination. Include the other party's primary contact(s) and anyone else directly relevant to the meeting purpose.

4. title: Generate a friendly, concise invite title that works for both parties.
   - Dinner/lunch/drinks: "{config.USER_NAME} / [Other person's first name] [Meal type]" (e.g. "{config.USER_NAME} / Matt Dinner")
   - Intro or first meeting: "{config.COMPANY_NAME} / [Their company name] Intro" (e.g. "{config.COMPANY_NAME} / Acme Intro Call")
   - Regular meeting: short description of the purpose
   - Use first names where possible; infer company names from email domains if not mentioned

5. Does the thread contain a CLEAR AGREEMENT on a specific meeting time? This includes:
   - Explicit confirmations: "Tuesday at 2pm works", "confirmed for Thursday", "let's do 3pm"
   - Short acceptances referring back to a previously offered time: "Let's do Tuesday", "Thursday works", "that works" — resolve these by finding the specific time offered for that day earlier in the thread

If there IS an agreed time, respond with:
{{"mode": "create", "is_in_person": <bool>, "context_type": "<type>", "title": "<title>", "start_iso": "<YYYY-MM-DDTHH:MM:SS>", "end_iso": "<YYYY-MM-DDTHH:MM:SS>", "timezone": "{config.TIMEZONE}", "location": "<location or empty>", "attendees": ["<email>"], "reply_text": "<reply>"}}

For reply_text: write 1-2 friendly sentences to insert into the email confirming the plan (e.g. "Great, sounds like a plan! I've sent over a calendar invite for [day] at [time]."). If the meeting is in-person and no specific location has been agreed upon in the thread, add a natural follow-up sentence asking where to meet (e.g. "Do you have a spot in mind, or should I suggest a few places?"). Keep it warm and conversational — no greeting or sign-off needed.

If there is NO agreed time yet, respond with:
{{"mode": "suggest", "is_in_person": <bool>, "context_type": "<type>", "constraints": "<any time preferences or constraints mentioned, or empty string>", "earliest_date": "<YYYY-MM-DD or null>", "latest_date": "<YYYY-MM-DD or null>"}}

For earliest_date / latest_date: parse relative references ("next week" → start of next week, "this weekend" → upcoming Saturday). Use null if no date range is implied."""

    msg = _anthropic_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = msg.content[0].text if msg.content else ""
    _log_call("analyze_thread", prompt, response_text)
    try:
        # Strip markdown code fences if Claude wraps its response
        import re as _re
        clean = _re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        clean = _re.sub(r"\s*```$", "", clean)
        return json.loads(clean)
    except (json.JSONDecodeError, IndexError, ValueError):
        return {"mode": "suggest", "constraints": ""}


_CONTEXT_LABELS = {
    "lunch":      "a lunch",
    "happy_hour": "a drinks / happy hour",
    "dinner":     "a dinner",
    "regular":    "a meeting",
}


def _format_suggestion(
    subject: str,
    email_body: str,
    constraints: str,
    slots: list[dict],
    context_type: str = "regular",
    is_in_person: bool = False,
) -> str:
    """Ask Claude to write a contextual, friendly time-suggestion paragraph."""
    if not slots:
        no_avail = {
            "lunch":      "I don't have any free lunch slots in the next 7 days",
            "happy_hour": "I don't have any free evenings for drinks in the next 7 days",
            "dinner":     "I don't have any free dinner slots in the next 7 days",
            "regular":    "I don't have any open time in the next 7 days",
        }
        return no_avail.get(context_type, no_avail["regular"]) + " — let me know what works for you."

    def _fmt(s):
        dt = datetime.fromisoformat(s["start"])
        if s.get("is_in_person"):
            return dt.strftime("%A, %B %-d at %-I:%M %p")       # no timezone
        else:
            return dt.strftime("%A, %B %-d at %-I:%M %p %Z")    # include timezone

    slot_lines = "\n".join(f"- {_fmt(s)}" for s in slots)
    meeting_label = _CONTEXT_LABELS.get(context_type, "a meeting")
    in_person_note = (
        "This is an in-person meeting, so the suggested times already account for travel time."
        if is_in_person else ""
    )

    prompt = f"""Write a short, friendly paragraph (2-4 sentences) that follows from what was originally written in the user's draft, suggesting times for {meeting_label}. No greeting or sign-off — it will be inserted directly after the existing email text. {in_person_note}

Email subject: {subject or "(no subject)"}

Email context:
{email_body or "(no context)"}

Time preferences or constraints from the thread:
{constraints or "none mentioned"}

Available slots:
{slot_lines}

Write naturally, as if Jason is the one writing. Frame the suggestion appropriately for {meeting_label} (e.g. for lunch say "grab lunch", for drinks say "grab a drink", etc.). Include the times clearly. End with something like "let me know what works!"."""

    msg = _anthropic_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = msg.content[0].text.strip() if msg.content else ""
    _log_call("format_suggestion", prompt, response_text)
    return response_text


def _build_calendar_url(
    title: str,
    start_iso: str,
    end_iso: str,
    timezone: str,
    location: str,
    attendees: list[str],
) -> str:
    """Build a Google Calendar event-creation URL with pre-filled fields."""
    tz_obj = pytz.timezone(timezone)

    def to_gcal(iso_str: str) -> str:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = tz_obj.localize(dt)
        return dt.astimezone(pytz.utc).strftime("%Y%m%dT%H%M%SZ")

    params = {"text": title, "dates": f"{to_gcal(start_iso)}/{to_gcal(end_iso)}"}
    if location:
        params["location"] = location

    url = f"https://calendar.google.com/calendar/r/eventedit?{urlencode(params)}"
    for email in attendees:
        url += f"&add={quote(email)}"
    return url


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class SchedulePayload(BaseModel):
    subject: str = ""
    email_body: str = ""
    thread_context: str = ""
    participants: list = []
    duration_minutes: int = 60
    days: int = 14


@app.post("/schedule")
async def schedule(
    payload: SchedulePayload,
    x_api_secret: Optional[str] = Header(default=None),
):
    """
    Smart scheduling endpoint.

    - If the thread shows an agreed time → returns a pre-filled Google Calendar URL.
    - Otherwise → returns contextual slot-suggestion text to insert into the email.
    """
    _check_auth(x_api_secret)
    analysis = _analyze_thread(payload.subject, payload.email_body, payload.thread_context, payload.participants)

    if analysis.get("mode") == "create":
        url = _build_calendar_url(
            title=analysis.get("title", "Meeting"),
            start_iso=analysis.get("start_iso", ""),
            end_iso=analysis.get("end_iso", ""),
            timezone=analysis.get("timezone", config.TIMEZONE),
            location=analysis.get("location", ""),
            attendees=analysis.get("attendees", []),
        )
        return {
            "mode": "create",
            "calendar_url": url,
            "summary": analysis.get("title", "Meeting"),
            "reply_text": analysis.get("reply_text", "Great, sounds like a plan! I've sent over a calendar invite."),
        }

    is_in_person = analysis.get("is_in_person", False)
    context_type = analysis.get("context_type", "regular")
    travel_buffer = 45 if is_in_person else 0

    slots = _find_free_slots(
        payload.duration_minutes,
        payload.days,
        travel_buffer_minutes=travel_buffer,
        context_type=context_type,
        earliest_date=analysis.get("earliest_date"),
        latest_date=analysis.get("latest_date"),
    )
    text = _format_suggestion(
        payload.subject,
        payload.email_body,
        analysis.get("constraints", ""),
        slots,
        context_type=context_type,
        is_in_person=is_in_person,
    )
    return {"mode": "suggest", "text": text}


@app.get("/available-slots")
def available_slots(
    duration: int = 60,
    days: int = 7,
    x_api_secret: Optional[str] = Header(default=None),
):
    """Return up to 5 raw available time slots."""
    _check_auth(x_api_secret)
    return {"slots": _find_free_slots(duration_minutes=duration, lookahead_days=days)}


@app.get("/health")
def health():
    return {"status": "ok"}
