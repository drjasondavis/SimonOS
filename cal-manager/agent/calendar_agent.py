"""
Personal calendar agent powered by Claude.

Answers natural-language questions about Jason's upcoming schedule,
surfaces conflicts between work and personal calendars, and can be
called interactively or imported by other jobs.

Usage:
  python -m agent.calendar_agent "What conflicts do I have this week?"
  python -m agent.calendar_agent "When am I free for a 90-minute meeting next week?"
"""
import sys
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session
import anthropic

from db.models import Event, get_engine
from jobs.conflict_checker import run as get_conflicts
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def build_calendar_context(days: int = 14) -> str:
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)

    with Session(engine) as session:
        events = (
            session.query(Event)
            .filter(Event.start >= now, Event.end <= end, Event.is_all_day == False)
            .order_by(Event.start)
            .all()
        )

    if not events:
        return "No upcoming events found."

    lines = []
    for e in events:
        local = e.start.astimezone(tz)
        flags = []
        if e.has_zoom:
            flags.append("Zoom")
        elif e.has_location:
            flags.append(f"📍 {e.location.split(',')[0]}")
        else:
            flags.append("no location")
        if not e.is_working_hours:
            flags.append("after-hours")
        if e.visibility == "private":
            flags.append("private")
        cal = "work" if e.calendar_id == config.WORK_CALENDAR_ID else "personal"
        flag_str = ", ".join(flags)
        lines.append(
            f"- [{cal}] {local.strftime('%a %b %d %I:%M%p')}–"
            f"{e.end.astimezone(tz).strftime('%I:%M%p')}: {e.title} [{flag_str}]"
        )

    conflicts = get_conflicts()
    conflict_lines = []
    for c in conflicts:
        conflict_lines.append(
            f"- CONFLICT: '{c.work_event}' vs '{c.personal_event}' "
            f"at {c.start.astimezone(tz).strftime('%a %b %d %I:%M%p')}"
        )

    context = "## Upcoming events:\n" + "\n".join(lines)
    if conflict_lines:
        context += "\n\n## Known conflicts:\n" + "\n".join(conflict_lines)

    return context


def ask(question: str) -> str:
    """Ask the calendar agent a natural-language question."""
    client = anthropic.Anthropic()
    calendar_context = build_calendar_context(days=14)

    system = f"""You are Jason's personal calendar assistant.
You help identify scheduling conflicts, suggest meeting times, and answer questions about his schedule.

Working hours: {config.WORK_HOURS_START}:00–{config.WORK_HOURS_END}:00, Mon–Fri.
Timezone: {config.TIMEZONE}.
Wife's email: {config.WIFE_EMAIL}

{calendar_context}

Be concise and actionable. If you identify a conflict, suggest a resolution."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What does my week look like?"
    print(ask(question))
