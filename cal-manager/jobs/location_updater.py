"""
Job: Determine today's location and create a private all-day location event
ONLY when away from home base (Brooklyn). No event = you're in Brooklyn.

Location inference priority:
  1. All-day travel event in calendar (e.g. "Chicago", "London trip") — manually set
  2. Travel-keyword event with a destination (e.g. "Flight to Austin")
  3. In-person event with a non-NYC address
  4. Default: Brooklyn (or Hampton Bays in July/August)
     — if defaulting to home base, delete any existing location event and skip
"""
import re
from datetime import datetime, date, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, LocationDay, get_engine
from integrations import google_calendar
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)

NYC_PATTERN = re.compile(
    r"\b(brooklyn|new york|nyc|manhattan|queens|bronx|staten island|new york city)\b",
    re.IGNORECASE,
)

DESTINATION_PATTERN = re.compile(
    r"(?:flight|flying|fly|travel(?:ing)?|arriving?|trip|headed|going)\s+to\s+([A-Z][a-zA-Z\s]+)",
    re.IGNORECASE,
)


def dbg(msg):
    if config.TEST_MODE:
        print(f"  [debug] {msg}")


def is_summer() -> bool:
    return date.today().month in (7, 8)


def base_location() -> str:
    if is_summer() and config.SUMMER_ADDRESS:
        return config.SUMMER_ADDRESS.split(",")[0].strip()
    return config.HOME_ADDRESS.split(",")[0].strip()


def is_home_base(location: str) -> bool:
    return location.strip().lower() == base_location().strip().lower()


def infer_travel_location(events: list) -> str:
    # Rule 1: all-day event that looks like a location
    for e in events:
        if not e.is_all_day:
            continue
        title = (e.title or "").strip()
        if title.startswith("📍"):
            dbg(f"Rule 1: skipping our own location event '{title}'")
            continue
        if title and not NYC_PATTERN.search(title) and len(title) < 60:
            dbg(f"Rule 1 matched: all-day event '{title}' → treating as travel location")
            return title
        elif NYC_PATTERN.search(title):
            dbg(f"Rule 1: all-day event '{title}' looks like NYC, skipping")

    # Rule 2: timed event title contains travel keyword + destination
    for e in events:
        if e.is_all_day:
            continue
        title = e.title or ""
        match = DESTINATION_PATTERN.search(title)
        if match:
            destination = match.group(1).strip()
            if not NYC_PATTERN.search(destination):
                dbg(f"Rule 2 matched: '{title}' → destination '{destination}'")
                return destination
            else:
                dbg(f"Rule 2: '{title}' matched but destination is NYC, skipping")

    # Rule 3: in-person event with a non-NYC address
    for e in events:
        if e.has_location and not e.has_zoom:
            loc = e.location or ""
            if not NYC_PATTERN.search(loc):
                city = loc.split(",")[0].strip()
                dbg(f"Rule 3 matched: event '{e.title}' has non-NYC location '{city}'")
                return city
            else:
                dbg(f"Rule 3: event '{e.title}' location '{loc}' is NYC, skipping")

    dbg("No travel signals found in today's events")
    return ""


def run():
    today = date.today()
    today_str = today.isoformat()
    tomorrow_str = (today + timedelta(days=1)).isoformat()
    now = datetime.now(timezone.utc)

    if config.TEST_MODE:
        month_label = "July/August (summer)" if is_summer() else "non-summer"
        print(f"  [debug] Today is {today_str} ({month_label}), base location: {base_location()}")

    with Session(engine) as session:
        events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.WORK_CALENDAR_ID,
                Event.start >= datetime.fromisoformat(f"{today_str}T00:00:00+00:00"),
                Event.start < datetime.fromisoformat(f"{tomorrow_str}T00:00:00+00:00"),
            )
            .order_by(Event.start)
            .all()
        )

        dbg(f"Scanning {len(events)} events for today")
        travel_location = infer_travel_location(events)
        location = travel_location if travel_location else base_location()
        loc_day = session.get(LocationDay, today_str)

        if is_home_base(location):
            dbg(f"Location '{location}' is home base — no calendar event needed")
            if loc_day and loc_day.all_day_event_id:
                dbg(f"Deleting stale location event from a previous away day")
                google_calendar.delete_event(config.WORK_CALENDAR_ID, loc_day.all_day_event_id)
                loc_day.all_day_event_id = None
                loc_day.location = location
                loc_day.updated_at = now
            print(f"[location_updater] {today_str}: at home base ({location}), no event needed")
            session.commit()
            return

        dbg(f"Away from home base → will create/update 📍 {location}")
        existing_id = loc_day.all_day_event_id if loc_day else None
        event_id = google_calendar.upsert_location_event(
            config.WORK_CALENDAR_ID, today_str, location, existing_id
        )

        if loc_day:
            loc_day.location = location
            loc_day.all_day_event_id = event_id
            loc_day.updated_at = now
        else:
            session.add(LocationDay(
                date=today_str,
                location=location,
                all_day_event_id=event_id,
                updated_at=now,
            ))

        session.commit()

    print(f"[location_updater] {today_str}: away at {location}")


if __name__ == "__main__":
    run()
