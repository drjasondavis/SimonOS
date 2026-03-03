"""Tests for color_coder: external organizer detection and color rules."""
import json
from unittest.mock import patch, MagicMock

import pytest

from jobs.color_coder import is_external_organizer
from tests.conftest import make_event, raw_event, MON_10AM


# ---------------------------------------------------------------------------
# is_external_organizer
# ---------------------------------------------------------------------------

class TestIsExternalOrganizer:
    def _with_domains(self, domains):
        """Patch INTERNAL_DOMAINS for a test."""
        return patch("jobs.color_coder.config") if False else \
               patch("jobs.color_coder.config", **{"INTERNAL_DOMAINS": domains})

    def test_simondata_is_internal(self):
        with patch("jobs.color_coder.config") as cfg:
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            assert is_external_organizer("galina@simondata.com") is False

    def test_simon_ai_is_internal(self):
        with patch("jobs.color_coder.config") as cfg:
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            assert is_external_organizer("someone@simon.ai") is False

    def test_gmail_is_external(self):
        with patch("jobs.color_coder.config") as cfg:
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            assert is_external_organizer("client@gmail.com") is True

    def test_other_company_is_external(self):
        with patch("jobs.color_coder.config") as cfg:
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            assert is_external_organizer("vendor@acmecorp.com") is True

    def test_case_insensitive(self):
        with patch("jobs.color_coder.config") as cfg:
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            assert is_external_organizer("Jason@SimonData.COM") is False

    def test_google_calendar_system_address_not_external(self):
        with patch("jobs.color_coder.config") as cfg:
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            assert is_external_organizer("c_269f707ce9d86851526af8f4e2a52de84207a2dcb3732783e74d200e886bd945@group.calendar.google.com") is False


# ---------------------------------------------------------------------------
# Color rules (via run() with mocked DB and API)
# ---------------------------------------------------------------------------

class TestColorRules:
    def _run_with_events(self, events):
        from jobs import color_coder
        with patch("jobs.color_coder.config") as cfg, \
             patch("jobs.color_coder.Session") as mock_session_cls, \
             patch("jobs.color_coder.google_calendar") as mock_gc:
            cfg.WORK_CALENDAR_ID = "jason@simondata.com"
            cfg.INTERNAL_DOMAINS = ["simondata.com", "simon.ai"]
            cfg.LOOKAHEAD_DAYS = 14
            cfg.TEST_MODE = False

            mock_session = MagicMock()
            mock_session_cls.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.all.return_value = events

            color_coder.run()
            return mock_gc.patch_event

    def test_external_default_color_gets_yellow(self):
        raw = json.dumps({"organizer": {"email": "client@acme.com", "self": False}})
        e = make_event(raw_json=raw)
        patch_event = self._run_with_events([e])
        patch_event.assert_called_once()
        assert patch_event.call_args[0][2] == {"colorId": "5"}

    def test_internal_organizer_not_recolored(self):
        raw = json.dumps({"organizer": {"email": "galina@simondata.com", "self": False}})
        e = make_event(raw_json=raw)
        patch_event = self._run_with_events([e])
        patch_event.assert_not_called()

    def test_self_organized_not_recolored(self):
        raw = json.dumps({"organizer": {"email": "jason@simondata.com", "self": True}})
        e = make_event(raw_json=raw)
        patch_event = self._run_with_events([e])
        patch_event.assert_not_called()

    def test_already_yellow_not_recolored(self):
        raw = json.dumps({"organizer": {"email": "client@acme.com"}, "colorId": "5"})
        e = make_event(raw_json=raw)
        patch_event = self._run_with_events([e])
        patch_event.assert_not_called()

    def test_custom_non_blue_color_not_overridden(self):
        # External but has Tomato (11) — intentionally colored, leave it alone
        raw = json.dumps({"organizer": {"email": "client@acme.com"}, "colorId": "11"})
        e = make_event(raw_json=raw)
        patch_event = self._run_with_events([e])
        patch_event.assert_not_called()
