"""
Job: For after-hours work events, create a private calendar event that invites
wife (kkutzke@gmail.com) with a rough description of what Jason is doing.

"After hours" = outside WORK_HOURS_START–WORK_HOURS_END on work days,
                OR any event on a weekend.

Only creates one wife event per source event (idempotent).
"""
from datetime import datetime, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, WifeNotification, get_engine
from integrations import google_calendar
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def is_after_hours(event: Event) -> bool:
    local = event.start.astimezone(tz)
    if local.weekday() not in config.WORK_DAYS:
        return True  # weekend
    return local.hour >= config.WORK_HOURS_END or local.hour < config.WORK_HOURS_START


def build_description(event: Event) -> str:
    if event.has_zoom:
        where = "on a video call"
    elif event.has_location:
        where = f"at {event.location.split(',')[0].strip()}"
    else:
        where = "at an event"
    return f"Jason has: {event.title} ({where})"


def run():
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        already_notified = {
            n.source_event_id
            for n in session.query(WifeNotification).all()
        }

        events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.WORK_CALENDAR_ID,
                Event.start >= now,
                Event.is_all_day == False,
            )
            .all()
        )

        for event in events:
            if event.id in already_notified:
                continue
            if not is_after_hours(event):
                continue

            wife_event = google_calendar.create_wife_notification_event(
                title=f"Jason: {event.title}",
                start=event.start,
                end=event.end,
                description=build_description(event),
            )

            session.add(WifeNotification(
                source_event_id=event.id,
                wife_event_id=wife_event.get("id"),
                created_at=datetime.now(timezone.utc),
            ))
            print(f"[wife_notifications] Notified for: {event.title} ({event.start.astimezone(tz).strftime('%a %b %d %I:%M%p')})")

        session.commit()

    print("[wife_notifications] Done.")


if __name__ == "__main__":
    run()
