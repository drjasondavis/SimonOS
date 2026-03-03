"""
Job: Determine today's primary location and maintain an all-day location event
on the work calendar so attendees/integrations always know where Jason is.

Location inference priority:
  1. First in-person event of the day (physical address, no Zoom)
  2. WORK_ADDRESS if it's a work day with no in-person events
  3. HOME_ADDRESS as default fallback
"""
from datetime import datetime, date, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, LocationDay, get_engine
from integrations import google_calendar
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def infer_location(events: list[Event]) -> str:
    in_person = [e for e in events if e.has_location and not e.has_zoom]
    if in_person:
        return in_person[0].location.split(",")[0].strip()

    today = datetime.now(tz)
    if today.weekday() in config.WORK_DAYS and config.WORK_ADDRESS:
        return config.WORK_ADDRESS.split(",")[0].strip()

    return config.HOME_ADDRESS.split(",")[0].strip() or "Home"


def run():
    today = date.today()
    today_str = today.isoformat()
    tomorrow_str = (today + timedelta(days=1)).isoformat()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.WORK_CALENDAR_ID,
                Event.start >= datetime.fromisoformat(f"{today_str}T00:00:00+00:00"),
                Event.start < datetime.fromisoformat(f"{tomorrow_str}T00:00:00+00:00"),
                Event.is_all_day == False,
            )
            .order_by(Event.start)
            .all()
        )

        location = infer_location(events)

        loc_day = session.get(LocationDay, today_str)
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

    print(f"[location_updater] {today_str}: {location}")


if __name__ == "__main__":
    run()
