"""
Job: Cross-reference work and personal calendars to identify overlapping events
during work hours. Returns a list of conflicts and prints warnings.
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

from sqlalchemy.orm import Session

from db.models import Event, get_engine
import config

engine = get_engine(config.DATABASE_URL)


@dataclass
class Conflict:
    work_event: str
    personal_event: str
    start: datetime
    end: datetime


def run() -> list[Conflict]:
    if not config.PERSONAL_CALENDAR_ID:
        print("[conflict_checker] No PERSONAL_CALENDAR_ID configured, skipping.")
        return []

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=config.LOOKAHEAD_DAYS)

    with Session(engine) as session:
        work_events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.WORK_CALENDAR_ID,
                Event.start >= now,
                Event.end <= end,
                Event.is_working_hours == True,
                Event.is_all_day == False,
            )
            .all()
        )

        personal_events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.PERSONAL_CALENDAR_ID,
                Event.start >= now,
                Event.end <= end,
                Event.is_working_hours == True,
                Event.is_all_day == False,
            )
            .all()
        )

    conflicts = []
    for we in work_events:
        for pe in personal_events:
            if we.start < pe.end and pe.start < we.end:
                c = Conflict(
                    work_event=we.title,
                    personal_event=pe.title,
                    start=max(we.start, pe.start),
                    end=min(we.end, pe.end),
                )
                conflicts.append(c)
                print(
                    f"[conflict_checker] ⚠️  '{we.title}' conflicts with "
                    f"'{pe.title}' at {we.start.astimezone().strftime('%a %b %d %I:%M%p')}"
                )

    if not conflicts:
        print("[conflict_checker] No conflicts found.")

    return conflicts


if __name__ == "__main__":
    run()
