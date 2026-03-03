"""
Job: Sync events from work and personal calendars, annotate each with:
  - has_zoom: contains a Zoom/Meet/Teams link
  - has_location: has a physical address (not virtual)
  - is_working_hours: falls within configured work hours
  - visibility: public / private / default
"""
import json
import re
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, get_engine
from integrations import google_calendar
import config

ZOOM_PATTERN = re.compile(
    r"zoom\.us/j/|meet\.google\.com/|teams\.microsoft\.com/l/meetup",
    re.IGNORECASE,
)

# Any bare URL in the location field means it's virtual, not a physical address
URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def dbg(msg):
    if config.TEST_MODE:
        print(f"  [debug] {msg}")


def is_virtual(event: dict) -> bool:
    for field in ("location", "description"):
        val = event.get(field) or ""
        if ZOOM_PATTERN.search(val):
            dbg(f"  → has_zoom=True (matched in {field})")
            return True
    if "conferenceData" in event:
        dbg(f"  → has_zoom=True (conferenceData present)")
        return True
    return False


def has_physical_location(event: dict) -> bool:
    loc = (event.get("location") or "").strip()
    if not loc:
        dbg(f"  → has_location=False (no location field)")
        return False
    if ZOOM_PATTERN.search(loc):
        dbg(f"  → has_location=False (recognized video conferencing link: {loc})")
        return False
    if URL_PATTERN.search(loc):
        dbg(f"  → has_location=False (location is a URL, not a physical address: {loc})")
        return False
    dbg(f"  → has_location=True ({loc})")
    return True


def is_in_working_hours(start: datetime) -> bool:
    local = start.astimezone(tz)
    day_ok = local.weekday() in config.WORK_DAYS
    hour_ok = config.WORK_HOURS_START <= local.hour < config.WORK_HOURS_END
    if not day_ok:
        dbg(f"  → is_working_hours=False (weekend: {local.strftime('%A')})")
    elif not hour_ok:
        dbg(f"  → is_working_hours=False ({local.strftime('%I:%M%p')} outside {config.WORK_HOURS_START}:00–{config.WORK_HOURS_END}:00)")
    else:
        dbg(f"  → is_working_hours=True")
    return day_ok and hour_ok


def parse_start_end(event: dict):
    start_str = event["start"].get("dateTime")
    end_str = event["end"].get("dateTime")
    if not start_str or not end_str:
        return None, None  # skip all-day events
    return datetime.fromisoformat(start_str), datetime.fromisoformat(end_str)


def run():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=config.LOOKAHEAD_DAYS)

    calendar_ids = [config.WORK_CALENDAR_ID]
    if config.PERSONAL_CALENDAR_ID:
        calendar_ids.append(config.PERSONAL_CALENDAR_ID)

    with Session(engine) as session:
        for cal_id in calendar_ids:
            raw_events = google_calendar.fetch_events(cal_id, now, end)
            dbg(f"Fetched {len(raw_events)} events from {cal_id}")
            for raw in raw_events:
                start, end_dt = parse_start_end(raw)
                if not start:
                    dbg(f"Skipping all-day event: {raw.get('summary', '(no title)')}")
                    continue

                title = raw.get("summary", "(no title)")
                local_start = start.astimezone(tz).strftime("%a %b %d %I:%M%p")
                dbg(f"Event: '{title}' at {local_start} [{cal_id}]")

                obj = session.get(Event, raw["id"]) or Event(id=raw["id"])
                obj.calendar_id = cal_id
                obj.title = title
                obj.start = start
                obj.end = end_dt
                obj.location = raw.get("location")
                obj.description = raw.get("description")
                obj.visibility = raw.get("visibility", "default")
                obj.is_all_day = False
                obj.has_zoom = is_virtual(raw)
                obj.has_location = has_physical_location(raw)
                obj.is_working_hours = is_in_working_hours(start)
                obj.raw_json = json.dumps(raw)
                obj.last_synced = now
                session.merge(obj)

        session.commit()

    print(f"[poll_events] Synced {len(calendar_ids)} calendar(s) through {end.date()}.")


if __name__ == "__main__":
    run()
