"""
FastAPI server consumed by the Gmail Chrome extension.

Endpoints:
  GET /available-slots?duration=60&days=7   — returns N open time slots
  GET /health                               — liveness check

Run with:
  uvicorn api.server:app --port 5555 --reload
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from fastapi import FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from db.models import Event, get_engine
import config

app = FastAPI(title="Cal Manager")
tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def _check_auth(secret: Optional[str]):
    if config.API_SECRET and secret != config.API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _find_free_slots(duration_minutes: int, lookahead_days: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=lookahead_days)

    with Session(engine) as session:
        busy = (
            session.query(Event)
            .filter(
                Event.start >= now,
                Event.end <= end,
                Event.is_all_day == False,
            )
            .order_by(Event.start)
            .all()
        )

    slots = []
    day = datetime.now(tz).date() + timedelta(days=1)  # start tomorrow

    while day <= (datetime.now(tz).date() + timedelta(days=lookahead_days)):
        if day.weekday() not in config.WORK_DAYS:
            day += timedelta(days=1)
            continue

        day_start = tz.localize(datetime(day.year, day.month, day.day, config.WORK_HOURS_START))
        day_end = tz.localize(datetime(day.year, day.month, day.day, config.WORK_HOURS_END))
        day_busy = [e for e in busy if e.start.date() == day]

        cursor = day_start
        while cursor + timedelta(minutes=duration_minutes) <= day_end:
            slot_end = cursor + timedelta(minutes=duration_minutes)
            conflict = any(e.start < slot_end and e.end > cursor for e in day_busy)
            if not conflict:
                slots.append({
                    "start": cursor.isoformat(),
                    "end": slot_end.isoformat(),
                    "display": cursor.strftime("%A, %B %-d at %-I:%M %p %Z"),
                })
                cursor = slot_end  # skip past this slot to avoid adjacent overlaps
                if len(slots) >= 5:
                    return slots
            else:
                cursor += timedelta(minutes=15)

        day += timedelta(days=1)

    return slots


@app.get("/available-slots")
def available_slots(
    duration: int = 60,
    days: int = 7,
    x_api_secret: Optional[str] = Header(default=None),
):
    """Return up to 5 available time slots of `duration` minutes within `days`."""
    _check_auth(x_api_secret)
    return {"slots": _find_free_slots(duration_minutes=duration, lookahead_days=days)}


@app.get("/health")
def health():
    return {"status": "ok"}
