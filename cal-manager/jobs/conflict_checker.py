"""
Job: Cross-reference work and personal calendars to identify overlapping events
during work hours.

For each set of overlapping events, the longest event is the anchor and all
shorter events are grouped under it.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from db.models import Event, get_engine
import config

engine = get_engine(config.DATABASE_URL)


def dbg(msg):
    if config.TEST_MODE:
        print(f"  [debug] {msg}")


def duration_minutes(event: Event) -> float:
    return (event.end - event.start).total_seconds() / 60


def fmt(event: Event) -> str:
    local = event.start.astimezone()
    return f"'{event.title}' {local.strftime('%a %b %d %I:%M%p')}–{event.end.astimezone().strftime('%I:%M%p')}"


@dataclass
class Conflict:
    anchor: Event
    conflicting: list = field(default_factory=list)  # events that overlap the anchor


def run() -> list:
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

    dbg(f"Checking {len(work_events)} work events against {len(personal_events)} personal events")
    if config.TEST_MODE:
        for e in work_events:
            dbg(f"  Work:     {fmt(e)} ({int(duration_minutes(e))}min)")
        for e in personal_events:
            dbg(f"  Personal: {fmt(e)} ({int(duration_minutes(e))}min)")

    # Find all overlapping pairs, group by the longer event as anchor
    anchor_conflicts: dict[str, Conflict] = {}

    for we in work_events:
        for pe in personal_events:
            if not (we.start < pe.end and pe.start < we.end):
                continue

            overlap_mins = int(
                (min(we.end, pe.end) - max(we.start, pe.start)).total_seconds() / 60
            )
            anchor, other = (we, pe) if duration_minutes(we) >= duration_minutes(pe) else (pe, we)
            dbg(f"  → Overlap: {fmt(we)} vs {fmt(pe)} ({overlap_mins}min) — anchor: '{anchor.title}'")

            if anchor.id not in anchor_conflicts:
                anchor_conflicts[anchor.id] = Conflict(anchor=anchor)
            if other not in anchor_conflicts[anchor.id].conflicting:
                anchor_conflicts[anchor.id].conflicting.append(other)

    conflicts = list(anchor_conflicts.values())

    if not conflicts:
        print("[conflict_checker] No conflicts found.")
    else:
        for c in conflicts:
            others = ", ".join(f"'{e.title}'" for e in c.conflicting)
            print(
                f"[conflict_checker] ⚠️  '{c.anchor.title}' "
                f"({int(duration_minutes(c.anchor))}min) conflicts with: {others}"
            )

    return conflicts


if __name__ == "__main__":
    run()
