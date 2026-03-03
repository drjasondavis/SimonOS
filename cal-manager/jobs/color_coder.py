"""
Job: Color-code calendar events based on origin.

Rule: external invites (events organized by someone else) that have no explicit
color set (showing as default calendar blue) get recolored to yellow (Banana).

Only events with colorId=None are changed — events with any explicitly set color
(even blue-ish ones like Peacock or Blueberry) are left alone, as those were
intentionally colored.

Google Calendar colorId reference:
  None=Calendar default (blue)
  1=Lavender  2=Sage      3=Grape     4=Flamingo
  5=Banana    6=Tangerine 7=Peacock   8=Graphite
  9=Blueberry 10=Basil    11=Tomato
"""
import json
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, get_engine
from integrations import google_calendar
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)

YELLOW = "5"
COLOR_NAMES = {
    None: "default (blue)", "1": "Lavender", "2": "Sage", "3": "Grape",
    "4": "Flamingo", "5": "Banana (yellow)", "6": "Tangerine", "7": "Peacock",
    "8": "Graphite", "9": "Blueberry", "10": "Basil", "11": "Tomato",
}


def dbg(msg):
    if config.TEST_MODE:
        print(f"  [debug] {msg}")


def is_external_organizer(organizer_email: str) -> bool:
    """True if the organizer's domain is not in INTERNAL_DOMAINS.

    Google Calendar system addresses (e.g. @group.calendar.google.com) are
    ignored — they are automated organizers, not real people.
    """
    organizer_domain = organizer_email.split("@")[-1].lower()
    if organizer_domain == "group.calendar.google.com":
        return False
    return organizer_domain not in config.INTERNAL_DOMAINS


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
            )
            .all()
        )

    dbg(f"Checking colors for {len(events)} upcoming work events")
    updated = 0

    for event in events:
        try:
            raw = json.loads(event.raw_json or "{}")
        except json.JSONDecodeError:
            continue

        organizer = raw.get("organizer", {})
        organizer_email = organizer.get("email", "unknown")
        is_self = organizer.get("self", False)
        is_external = is_external_organizer(organizer_email)
        color_id = raw.get("colorId") or None
        color_name = COLOR_NAMES.get(color_id, f"unknown ({color_id})")
        local_start = event.start.astimezone(tz).strftime("%a %b %d %I:%M%p")
        internal_label = f"internal ({', '.join(config.INTERNAL_DOMAINS)})"

        dbg(f"Event: '{event.title}' at {local_start}")
        dbg(f"  organizer: {organizer_email} {'(you)' if is_self else f'({internal_label})' if not is_external else '(external)'}")
        dbg(f"  color: {color_name}")

        if not is_external:
            dbg(f"  → Organized internally, skipping")
            continue

        if color_id == YELLOW:
            dbg(f"  → Already yellow, skipping")
            continue

        if color_id is not None:
            dbg(f"  → Explicitly set to {color_name}, leaving it alone")
            continue

        dbg(f"  → External invite with default color → will set to yellow")
        google_calendar.patch_event(
            config.WORK_CALENDAR_ID,
            event.id,
            {"colorId": YELLOW},
            label=f"[yellow] '{event.title}'",
        )
        updated += 1
        print(f"[color_coder] → yellow: '{event.title}' (was: {color_name}, organizer: {organizer_email})")

    print(f"[color_coder] Done. {updated} event(s) recolored.")


if __name__ == "__main__":
    run()
