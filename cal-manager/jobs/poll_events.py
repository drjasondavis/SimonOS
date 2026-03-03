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

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def is_virtual(event: dict) -> bool:
    for field in ("location", "description"):
        if ZOOM_PATTERN.search(event.get(field) or ""):
            return True
    if "conferenceData" in event:
        return True
    return False


def has_physical_location(event: dict) -> bool:
    loc = (event.get("location") or "").strip()
    return bool(loc) and not ZOOM_PATTERN.search(loc)


def is_in_working_hours(start: datetime) -> bool:
    local = start.astimezone(tz)
    return (
        local.weekday() in config.WORK_DAYS
        and config.WORK_HOURS_START <= local.hour < config.WORK_HOURS_END
    )


def parse_start_end(event: dict) -> tuple[datetime | None, datetime | None]:
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
            for raw in raw_events:
                start, end_dt = parse_start_end(raw)
                if not start:
                    continue

                obj = session.get(Event, raw["id"]) or Event(id=raw["id"])
                obj.calendar_id = cal_id
                obj.title = raw.get("summary", "(no title)")
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
