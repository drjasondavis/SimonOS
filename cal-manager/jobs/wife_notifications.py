"""
Job: For after-hours work events, create a private calendar event that invites
wife (kkutzke@gmail.com) with a rough description of what Jason is doing.

"After hours" = outside WORK_HOURS_START–WORK_HOURS_END on work days,
                OR any event on a weekend.

Only creates one wife event per source event (idempotent).
"""
import json
from datetime import datetime, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, TravelHold, WifeNotification, get_engine
from integrations import google_calendar
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def dbg(msg):
    if config.TEST_MODE:
        print(f"  [debug] {msg}")


def is_after_hours(event: Event) -> bool:
    local = event.start.astimezone(tz)
    if local.weekday() not in config.WORK_DAYS:
        dbg(f"  → after-hours: weekend ({local.strftime('%A')})")
        return True
    if local.hour >= config.WORK_HOURS_END:
        dbg(f"  → after-hours: {local.strftime('%I:%M%p')} is after {config.WORK_HOURS_END}:00")
        return True
    if local.hour < config.WORK_HOURS_START:
        dbg(f"  → after-hours: {local.strftime('%I:%M%p')} is before {config.WORK_HOURS_START}:00")
        return True
    dbg(f"  → within work hours ({local.strftime('%I:%M%p')}), skipping")
    return False


def wife_already_invited(event: Event) -> bool:
    try:
        raw = json.loads(event.raw_json or "{}")
        attendees = [a.get("email", "").lower() for a in raw.get("attendees", [])]
        return config.WIFE_EMAIL.lower() in attendees
    except (json.JSONDecodeError, AttributeError):
        return False


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
        travel_hold_ids = {
            h.hold_event_id
            for h in session.query(TravelHold).all()
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

        dbg(f"Checking {len(events)} upcoming work events for after-hours notifications")

        for event in events:
            local_time = event.start.astimezone(tz).strftime("%a %b %d %I:%M%p")
            dbg(f"Event: '{event.title}' at {local_time}")

            if event.id in already_notified:
                dbg(f"  → Already notified wife, skipping")
                continue

            if event.id in travel_hold_ids:
                dbg(f"  → This is a travel hold we created, skipping")
                continue

            if wife_already_invited(event):
                dbg(f"  → Wife already on the invite, skipping")
                continue

            if not is_after_hours(event):
                continue

            description = build_description(event)
            dbg(f"  → Will notify wife: \"{description}\"")

            wife_event = google_calendar.create_wife_notification_event(
                title=f"Jason: {event.title}",
                start=event.start,
                end=event.end,
                description=description,
            )

            session.add(WifeNotification(
                source_event_id=event.id,
                wife_event_id=wife_event.get("id"),
                created_at=datetime.now(timezone.utc),
            ))
            print(f"[wife_notifications] Notified for: {event.title} ({local_time})")

        session.commit()

    print("[wife_notifications] Done.")


if __name__ == "__main__":
    run()
