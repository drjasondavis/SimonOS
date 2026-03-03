"""Tests for wife_notifications: after-hours detection, invite check, description."""
import json
from datetime import timedelta
from unittest.mock import patch

import pytest

from jobs.wife_notifications import is_after_hours, wife_already_invited, build_description
from tests.conftest import make_event, MON_10AM, MON_7PM, MON_7AM, SAT_11AM


# ---------------------------------------------------------------------------
# is_after_hours
# ---------------------------------------------------------------------------

class TestIsAfterHours:
    def test_weekday_within_hours_false(self):
        # Monday 10am — inside 9–18
        e = make_event(start=MON_10AM)
        assert is_after_hours(e) is False

    def test_weekday_after_end_hour(self):
        # Monday 7pm — after 18:00
        e = make_event(start=MON_7PM)
        assert is_after_hours(e) is True

    def test_weekday_before_start_hour(self):
        # Monday 7am — before 9:00
        e = make_event(start=MON_7AM)
        assert is_after_hours(e) is True

    def test_saturday_is_after_hours(self):
        e = make_event(start=SAT_11AM)
        assert is_after_hours(e) is True

    def test_exactly_at_work_start_is_not_after_hours(self):
        import pytz
        from datetime import datetime
        ny = pytz.timezone("America/New_York")
        start = ny.localize(datetime(2026, 3, 9, 9, 0))  # 9:00am exactly
        e = make_event(start=start)
        assert is_after_hours(e) is False

    def test_exactly_at_work_end_is_after_hours(self):
        import pytz
        from datetime import datetime
        ny = pytz.timezone("America/New_York")
        start = ny.localize(datetime(2026, 3, 9, 18, 0))  # 6:00pm exactly
        e = make_event(start=start)
        assert is_after_hours(e) is True


# ---------------------------------------------------------------------------
# wife_already_invited
# ---------------------------------------------------------------------------

class TestWifeAlreadyInvited:
    def test_wife_in_attendees(self):
        raw = json.dumps({"attendees": [{"email": "kkutzke@gmail.com"}]})
        e = make_event(raw_json=raw)
        assert wife_already_invited(e) is True

    def test_wife_not_in_attendees(self):
        raw = json.dumps({"attendees": [{"email": "someone@simondata.com"}]})
        e = make_event(raw_json=raw)
        assert wife_already_invited(e) is False

    def test_no_attendees(self):
        e = make_event(raw_json=json.dumps({}))
        assert wife_already_invited(e) is False

    def test_case_insensitive(self):
        raw = json.dumps({"attendees": [{"email": "KKUTZKE@GMAIL.COM"}]})
        e = make_event(raw_json=raw)
        assert wife_already_invited(e) is True

    def test_malformed_json_returns_false(self):
        e = make_event(raw_json="not-json")
        assert wife_already_invited(e) is False

    def test_empty_raw_json_returns_false(self):
        e = make_event(raw_json=None)
        assert wife_already_invited(e) is False


# ---------------------------------------------------------------------------
# build_description
# ---------------------------------------------------------------------------

class TestBuildDescription:
    def test_zoom_event(self):
        e = make_event(title="Board Call", has_zoom=True, has_location=False)
        assert build_description(e) == "Jason has: Board Call (on a video call)"

    def test_physical_location(self):
        e = make_event(title="Client Dinner", has_zoom=False, has_location=True,
                       location="Nobu Tribeca, New York, NY")
        assert build_description(e) == "Jason has: Client Dinner (at Nobu Tribeca)"

    def test_no_location(self):
        e = make_event(title="Team Offsite", has_zoom=False, has_location=False)
        assert build_description(e) == "Jason has: Team Offsite (at an event)"
