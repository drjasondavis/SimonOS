"""Shared fixtures and helpers for cal-manager tests."""
import json
from datetime import datetime, timedelta

import pytz
import pytest

NY_TZ = pytz.timezone("America/New_York")

# Canonical reference times (all timezone-aware)
MON_10AM = NY_TZ.localize(datetime(2026, 3, 9, 10, 0))   # Monday 10am — work hours
MON_7PM  = NY_TZ.localize(datetime(2026, 3, 9, 19, 0))   # Monday 7pm  — after hours
MON_7AM  = NY_TZ.localize(datetime(2026, 3, 9, 7, 0))    # Monday 7am  — before hours
SAT_11AM = NY_TZ.localize(datetime(2026, 3, 14, 11, 0))  # Saturday    — weekend


def make_event(**kwargs):
    """Create a minimal Event for testing without a DB session."""
    from db.models import Event
    e = Event()
    e.id            = kwargs.get("id", "test-id")
    e.title         = kwargs.get("title", "Test Event")
    e.calendar_id   = kwargs.get("calendar_id", "jason@simondata.com")
    e.start         = kwargs.get("start", MON_10AM)
    e.end           = kwargs.get("end", kwargs.get("start", MON_10AM) + timedelta(hours=1))
    e.location      = kwargs.get("location", None)
    e.is_all_day    = kwargs.get("is_all_day", False)
    e.has_zoom      = kwargs.get("has_zoom", False)
    e.has_location  = kwargs.get("has_location", False)
    e.is_working_hours = kwargs.get("is_working_hours", True)
    e.raw_json      = kwargs.get("raw_json", "{}")
    return e


def raw_event(**kwargs):
    """Build a dict resembling a raw Google Calendar API event."""
    return {
        "id": kwargs.get("id", "gcal-id"),
        "summary": kwargs.get("summary", "Test Event"),
        "start": {"dateTime": kwargs.get("start", "2026-03-09T10:00:00-05:00")},
        "end":   {"dateTime": kwargs.get("end",   "2026-03-09T11:00:00-05:00")},
        "location": kwargs.get("location", None),
        "description": kwargs.get("description", None),
        "visibility": kwargs.get("visibility", "default"),
        "colorId": kwargs.get("colorId", None),
        "organizer": kwargs.get("organizer", {"email": "jason@simondata.com", "self": True}),
        "attendees": kwargs.get("attendees", []),
        **{k: v for k, v in kwargs.items()
           if k not in ("id", "summary", "start", "end", "location",
                        "description", "visibility", "colorId", "organizer", "attendees")},
    }
