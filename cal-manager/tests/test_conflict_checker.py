"""Tests for conflict_checker: duration, anchor selection, grouping logic."""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from jobs.conflict_checker import duration_minutes, Conflict
from tests.conftest import make_event, MON_10AM


# ---------------------------------------------------------------------------
# duration_minutes
# ---------------------------------------------------------------------------

class TestDurationMinutes:
    def test_one_hour(self):
        e = make_event(start=MON_10AM, end=MON_10AM + timedelta(hours=1))
        assert duration_minutes(e) == 60.0

    def test_thirty_minutes(self):
        e = make_event(start=MON_10AM, end=MON_10AM + timedelta(minutes=30))
        assert duration_minutes(e) == 30.0

    def test_ninety_minutes(self):
        e = make_event(start=MON_10AM, end=MON_10AM + timedelta(minutes=90))
        assert duration_minutes(e) == 90.0


# ---------------------------------------------------------------------------
# Anchor selection and grouping (tested via run() with mocked DB)
# ---------------------------------------------------------------------------

def _make_overlapping_pair(work_duration_hrs=2, personal_duration_hrs=1):
    """Return (work_event, personal_event) that overlap."""
    we = make_event(id="work-1", title="Work Event",
                    start=MON_10AM,
                    end=MON_10AM + timedelta(hours=work_duration_hrs))
    pe = make_event(id="personal-1", title="Personal Event",
                    start=MON_10AM + timedelta(minutes=30),
                    end=MON_10AM + timedelta(minutes=30) + timedelta(hours=personal_duration_hrs))
    return we, pe


class TestConflictGrouping:
    def _run_with_events(self, work_events, personal_events):
        """Call conflict_checker.run() with mocked DB queries."""
        from jobs import conflict_checker
        with patch("jobs.conflict_checker.config") as cfg, \
             patch("jobs.conflict_checker.Session") as mock_session_cls:
            cfg.PERSONAL_CALENDAR_ID = "jvdavis@gmail.com"
            cfg.WORK_CALENDAR_ID = "jason@simondata.com"
            cfg.LOOKAHEAD_DAYS = 14
            cfg.TEST_MODE = False

            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__.return_value = mock_session
            mock_query = mock_session.query.return_value.filter.return_value
            # First call returns work_events, second returns personal_events
            mock_query.all.side_effect = [work_events, personal_events]

            return conflict_checker.run()

    def test_longer_event_is_anchor(self):
        we, pe = _make_overlapping_pair(work_duration_hrs=2, personal_duration_hrs=1)
        conflicts = self._run_with_events([we], [pe])
        assert len(conflicts) == 1
        assert conflicts[0].anchor.title == "Work Event"
        assert conflicts[0].conflicting[0].title == "Personal Event"

    def test_personal_longer_becomes_anchor(self):
        we, pe = _make_overlapping_pair(work_duration_hrs=1, personal_duration_hrs=2)
        conflicts = self._run_with_events([we], [pe])
        assert len(conflicts) == 1
        assert conflicts[0].anchor.title == "Personal Event"
        assert conflicts[0].conflicting[0].title == "Work Event"

    def test_multiple_short_events_grouped_under_anchor(self):
        long_event = make_event(
            id="long", title="All-Day Meeting",
            start=MON_10AM, end=MON_10AM + timedelta(hours=3)
        )
        short1 = make_event(
            id="s1", title="Quick Call",
            start=MON_10AM + timedelta(minutes=30),
            end=MON_10AM + timedelta(minutes=60)
        )
        short2 = make_event(
            id="s2", title="Dentist",
            start=MON_10AM + timedelta(hours=1),
            end=MON_10AM + timedelta(hours=2)
        )
        conflicts = self._run_with_events([long_event], [short1, short2])
        assert len(conflicts) == 1
        assert conflicts[0].anchor.title == "All-Day Meeting"
        assert len(conflicts[0].conflicting) == 2

    def test_no_overlap_returns_empty(self):
        we = make_event(id="w1", start=MON_10AM, end=MON_10AM + timedelta(hours=1))
        pe = make_event(id="p1", start=MON_10AM + timedelta(hours=2),
                        end=MON_10AM + timedelta(hours=3))
        conflicts = self._run_with_events([we], [pe])
        assert conflicts == []

    def test_no_personal_calendar_returns_empty(self):
        from jobs import conflict_checker
        with patch("jobs.conflict_checker.config") as cfg:
            cfg.PERSONAL_CALENDAR_ID = ""
            result = conflict_checker.run()
        assert result == []
