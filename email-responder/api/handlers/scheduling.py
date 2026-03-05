"""
Scheduling handler — ported from cal-manager/api/server.py.

Given an email thread, either:
  - Detects an agreed meeting time → returns a pre-filled Google Calendar URL + reply text
  - No agreement yet → finds free slots from cal-manager's DB → returns suggestion text
"""
import json
import re
from datetime import datetime, timedelta, timezone, date as date_type
from typing import Optional
from urllib.parse import urlencode, quote

import anthropic
import pytz
from sqlalchemy.orm import Session

import config

import sys
from pathlib import Path
# Import cal-manager's Event model — scheduling handler reads its DB
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "cal-manager"))
from db.models import Event, get_engine
from prompts import EMAIL_VOICE

_tz = pytz.timezone(config.TIMEZONE)
_engine = get_engine(config.DATABASE_URL)

def _to_time(decimal_hour: float):
    """Convert a decimal hour (e.g. 9.5) to (hour, minute) tuple."""
    h = int(decimal_hour)
    m = int(round((decimal_hour - h) * 60))
    return h, m

CONTEXT_WINDOWS = {
    "lunch":      [(11, 14)],
    "happy_hour": [(17, 19)],
    "dinner":     [(18, 21)],
    "regular":    [(config.WORK_HOURS_START, config.WORK_HOURS_END)],
}

_CONTEXT_LABELS = {
    "lunch":      "a lunch",
    "happy_hour": "a drinks / happy hour",
    "dinner":     "a dinner",
    "regular":    "a meeting",
}


def _client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _parse_date(s):
    try:
        return date_type.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def find_free_slots(
    duration_minutes: int,
    lookahead_days: int,
    travel_buffer_minutes: int = 0,
    context_type: str = "regular",
    earliest_date: Optional[str] = None,
    latest_date: Optional[str] = None,
) -> list[dict]:
    """Return up to 5 free calendar slots from the cal-manager DB."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=lookahead_days)

    with Session(_engine) as session:
        busy = (
            session.query(Event)
            .filter(Event.start >= now, Event.end <= end, Event.is_all_day == False)
            .order_by(Event.start)
            .all()
        )

    buffer = timedelta(minutes=travel_buffer_minutes)
    windows = CONTEXT_WINDOWS.get(context_type, CONTEXT_WINDOWS["regular"])
    slots = []
    today = datetime.now(_tz).date()

    min_start = today + timedelta(days=2)
    day = max(_parse_date(earliest_date) or min_start, min_start)
    end_day = _parse_date(latest_date) or (today + timedelta(days=lookahead_days))

    while day <= end_day:
        if day.weekday() not in config.WORK_DAYS:
            day += timedelta(days=1)
            continue

        day_busy = [e for e in busy if e.start.astimezone(_tz).date() == day]

        for (win_start_h, win_end_h) in windows:
            sh, sm = _to_time(win_start_h)
            eh, em = _to_time(win_end_h)
            window_start = _tz.localize(datetime(day.year, day.month, day.day, sh, sm))
            window_end   = _tz.localize(datetime(day.year, day.month, day.day, eh, em))
            cursor = window_start

            while cursor + timedelta(minutes=duration_minutes) <= window_end:
                slot_end = cursor + timedelta(minutes=duration_minutes)
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
                    if context_type in ("dinner", "happy_hour", "lunch"):
                        break
                else:
                    cursor += timedelta(minutes=15)

        day += timedelta(days=1)

    return slots


def analyze_thread(subject: str, email_body: str, thread_context: str, participants: list) -> dict:
    today = datetime.now(_tz).strftime("%A, %B %d, %Y")
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

3. attendees: From the list of email addresses above, select only the people who should actually attend this meeting. Exclude scheduling assistants, admins, or anyone who was only CC'd for coordination.

4. title: Generate a friendly, concise invite title.
   - Dinner/lunch/drinks: "{config.USER_NAME} / [Other person's first name] [Meal type]"
   - Intro or first meeting: "{config.COMPANY_NAME} / [Their company name] Intro"
   - Regular meeting: short description of the purpose

5. Does the thread contain a CLEAR AGREEMENT on a specific meeting time?
   - Explicit confirmations: "Tuesday at 2pm works", "confirmed for Thursday"
   - Short acceptances: "Let's do Tuesday", "Thursday works" — resolve to the specific time offered earlier

If there IS an agreed time:
{{"mode": "create", "is_in_person": <bool>, "context_type": "<type>", "title": "<title>", "start_iso": "<YYYY-MM-DDTHH:MM:SS>", "end_iso": "<YYYY-MM-DDTHH:MM:SS>", "timezone": "{config.TIMEZONE}", "location": "<location or empty>", "attendees": ["<email>"], "reply_text": "<1-2 sentences in Jason's voice confirming the plan — concise, no filler, ends with next step. E.g. 'Perfect — sent over an invite for [day] at [time].' If in-person with no location agreed, add a short ask like 'Do you have a spot in mind?'>"}}

If there is NO agreed time:
{{"mode": "suggest", "is_in_person": <bool>, "context_type": "<type>", "constraints": "<any time preferences or constraints, or empty>", "earliest_date": "<YYYY-MM-DD or null>", "latest_date": "<YYYY-MM-DD or null>"}}"""

    msg = _client().messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = msg.content[0].text if msg.content else ""
    try:
        clean = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        clean = re.sub(r"\s*```$", "", clean)
        return json.loads(clean)
    except (json.JSONDecodeError, IndexError, ValueError):
        return {"mode": "suggest", "constraints": ""}


def format_suggestion(
    subject: str,
    email_body: str,
    constraints: str,
    slots: list[dict],
    context_type: str = "regular",
    is_in_person: bool = False,
) -> str:
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
        return dt.strftime("%A, %B %-d at %-I:%M %p") if s.get("is_in_person") else dt.strftime("%A, %B %-d at %-I:%M %p %Z")

    slot_lines = "\n".join(f"- {_fmt(s)}" for s in slots)
    meeting_label = _CONTEXT_LABELS.get(context_type, "a meeting")
    in_person_note = (
        "This is an in-person meeting, so the suggested times already account for travel time."
        if is_in_person else ""
    )

    prompt = f"""{EMAIL_VOICE}

---

Write a short time-suggestion to insert directly after the user's existing draft. Follow Jason's voice exactly — concise, no filler, action-forward. {in_person_note}

This is for {meeting_label}. No greeting or sign-off — this text will be appended inline.

Email subject: {subject or "(no subject)"}

User's draft so far:
{email_body or "(no context)"}

Time preferences or constraints from the thread:
{constraints or "none mentioned"}

Available slots:
{slot_lines}

Write 1-3 sentences max. Include the times clearly. End with a soft next-step ("lmk what works" style)."""

    msg = _client().messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip() if msg.content else ""


def build_calendar_url(title: str, start_iso: str, end_iso: str, timezone: str, location: str, attendees: list) -> str:
    tz_obj = pytz.timezone(timezone)

    def to_gcal(iso_str):
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


async def run(subject: str, email_body: str, thread_context: str, participants: list, duration_minutes: int = 60, days: int = 14) -> dict:
    """
    Handler entry point. Returns a ReplyResponse-compatible dict:
      { "text": str, "action_url": str | None, "label": str, "mode": str }
    """
    analysis = analyze_thread(subject, email_body, thread_context, participants)

    if analysis.get("mode") == "create":
        url = build_calendar_url(
            title=analysis.get("title", "Meeting"),
            start_iso=analysis.get("start_iso", ""),
            end_iso=analysis.get("end_iso", ""),
            timezone=analysis.get("timezone", config.TIMEZONE),
            location=analysis.get("location", ""),
            attendees=analysis.get("attendees", []),
        )
        return {
            "mode": "create",
            "text": analysis.get("reply_text", "Great, sounds like a plan! I've sent over a calendar invite."),
            "action_url": url,
            "label": "✅ Invite sent",
        }

    is_in_person = analysis.get("is_in_person", False)
    context_type = analysis.get("context_type", "regular")
    slots = find_free_slots(
        duration_minutes,
        days,
        travel_buffer_minutes=45 if is_in_person else 0,
        context_type=context_type,
        earliest_date=analysis.get("earliest_date"),
        latest_date=analysis.get("latest_date"),
    )
    text = format_suggestion(subject, email_body, analysis.get("constraints", ""), slots, context_type, is_in_person)
    return {
        "mode": "suggest",
        "text": text,
        "action_url": None,
        "label": "✅ Inserted",
    }
