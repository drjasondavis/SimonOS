"""
Job: Find in-person events that have no location set.

For each such event, asks Claude:
  1. Can a specific location be inferred from the title / description?
     → If yes: prints the suggestion (and optionally patches the event).
  2. If not: prints a pre-filled Gmail compose URL so you can click to send
     a quick "where should we meet?" email to all attendees.

Run via scheduler.py or directly:
  python -m jobs.location_finder
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import anthropic
import pytz
from sqlalchemy.orm import Session

from db.models import Event, TravelHold, get_engine
from integrations import google_calendar
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)
_client = None


def _anthropic():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _get_attendees(raw_json: str) -> list[dict]:
    """Return list of {email, name} dicts from raw event JSON."""
    try:
        raw = json.loads(raw_json or "{}")
    except json.JSONDecodeError:
        return []
    attendees = []
    for a in raw.get("attendees", []):
        email = a.get("email", "")
        name = a.get("displayName", "")
        if email and not a.get("self"):
            attendees.append({"email": email, "name": name})
    return attendees




def _analyze_event(event: Event, attendees: list[dict]) -> dict:
    """Ask Claude to infer a location or draft a 'where should we meet?' email."""
    local_start = event.start.astimezone(tz).strftime("%A, %B %-d at %-I:%M %p")
    try:
        raw = json.loads(event.raw_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    description = raw.get("description", "")
    attendees_str = ", ".join(
        f"{a['name']} <{a['email']}>" if a["name"] else a["email"]
        for a in attendees
    ) or "(no attendees)"

    prompt = f"""You are managing a calendar. An upcoming in-person event has no location set.

Event title: {event.title}
Date/time: {local_start}
Attendees: {attendees_str}
Description: {description or "(none)"}

Question 1 — Can you infer a SPECIFIC location from the context?
Only say yes if the title or description names a real venue, restaurant, address, or building.
Do NOT say yes for vague inferences like "probably a restaurant" or "likely downtown".
Examples that qualify: "Nobu Tribeca", "115 Broadway 5th Floor", "The Smith on 3rd Ave".

Question 2 — Write a short, friendly email asking attendees where to meet.
2-3 sentences, casual tone, written as Jason. Reference the event title and date.

Respond with JSON only — no markdown, no explanation:
{{"can_infer": <bool>, "location": "<specific venue/address or null>", "email_subject": "<subject>", "email_body": "<body>"}}"""

    msg = _anthropic().messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip() if msg.content else ""
    # Strip markdown fences if present
    import re
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"can_infer": False, "location": None, "email_subject": "", "email_body": text}


def _gmail_compose_url(to_emails: list[str], subject: str, body: str) -> str:
    """Return a Gmail compose URL with pre-filled To, Subject, and Body."""
    to = ",".join(to_emails)
    return (
        "https://mail.google.com/mail/?view=cm"
        f"&to={quote(to)}"
        f"&su={quote(subject)}"
        f"&body={quote(body)}"
    )


def run():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=config.LOOKAHEAD_DAYS)

    with Session(engine) as session:
        events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.WORK_CALENDAR_ID,
                Event.start >= now,
                Event.end <= end,
                Event.is_all_day == False,
                Event.has_zoom == False,
                Event.has_location == False,
            )
            .order_by(Event.start)
            .all()
        )

        # Exclude travel holds — they intentionally have no location
        travel_hold_ids = {
            row.hold_event_id
            for row in session.query(TravelHold).all()
        }

    events = [e for e in events if e.id not in travel_hold_ids]

    if not events:
        print("[location_finder] No in-person events without a location. All good.")
        return

    print(f"[location_finder] {len(events)} in-person event(s) without a location:\n")

    for event in events:
        local_start = event.start.astimezone(tz).strftime("%A, %B %-d at %-I:%M %p")
        attendees = _get_attendees(event.raw_json)
        print(f"  • '{event.title}' — {local_start}")

        result = _analyze_event(event, attendees)

        if result.get("can_infer") and result.get("location"):
            location = result["location"]
            print(f"    ✅ Inferred location: {location}")
            if not config.TEST_MODE:
                google_calendar.patch_event(
                    config.WORK_CALENDAR_ID,
                    event.id,
                    {"location": location},
                    label=f"[location] '{event.title}' → {location}",
                )
                print(f"    → Updated event location to: {location}")
            else:
                print(f"    [TEST MODE] Would set location to: {location}")
        else:
            subject = result.get("email_subject") or f"Where should we meet for {event.title}?"
            body = result.get("email_body") or (
                f"Hey, just wanted to nail down where we're meeting for {event.title} "
                f"on {local_start}. Do you have a spot in mind?"
            )
            to_emails = [a["email"] for a in attendees]
            if to_emails:
                url = _gmail_compose_url(to_emails, subject, body)
                print(f"    📧 No location inferred — compose email to ask:")
                print(f"    {url}\n")
            else:
                print(f"    ⚠️  No attendees found — can't generate email.\n")

    print("[location_finder] Done.")


if __name__ == "__main__":
    run()
