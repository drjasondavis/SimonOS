"""Tests for poll_events: virtual meeting detection and physical location detection."""
import pytest
from jobs.poll_events import is_virtual, has_physical_location
from tests.conftest import raw_event


# ---------------------------------------------------------------------------
# is_virtual
# ---------------------------------------------------------------------------

class TestIsVirtual:
    def test_zoom_link_in_location(self):
        assert is_virtual(raw_event(location="https://zoom.us/j/123456"))

    def test_zoom_link_in_description(self):
        assert is_virtual(raw_event(description="Join: https://zoom.us/j/99999"))

    def test_google_meet_in_location(self):
        assert is_virtual(raw_event(location="https://meet.google.com/abc-defg-hij"))

    def test_teams_link_in_description(self):
        assert is_virtual(raw_event(description="https://teams.microsoft.com/l/meetup-join/..."))

    def test_conference_data_field(self):
        ev = raw_event()
        ev["conferenceData"] = {"entryPoints": []}
        assert is_virtual(ev)

    def test_physical_address_not_virtual(self):
        assert not is_virtual(raw_event(location="123 Main St, New York, NY"))

    def test_no_location_not_virtual(self):
        assert not is_virtual(raw_event())

    def test_case_insensitive(self):
        assert is_virtual(raw_event(location="HTTPS://ZOOM.US/J/123"))


# ---------------------------------------------------------------------------
# has_physical_location
# ---------------------------------------------------------------------------

class TestHasPhysicalLocation:
    def test_empty_location(self):
        assert not has_physical_location(raw_event(location=None))

    def test_blank_location(self):
        assert not has_physical_location(raw_event(location="   "))

    def test_zoom_url_not_physical(self):
        assert not has_physical_location(raw_event(location="https://zoom.us/j/123"))

    def test_generic_https_url_not_physical(self):
        # Roam, Whereby, or any link-in-location-field
        assert not has_physical_location(raw_event(location="https://ro.am/room/abc"))

    def test_www_url_not_physical(self):
        assert not has_physical_location(raw_event(location="www.example.com/meeting"))

    def test_real_address_is_physical(self):
        assert has_physical_location(raw_event(location="350 5th Ave, New York, NY 10118"))

    def test_short_venue_name_is_physical(self):
        assert has_physical_location(raw_event(location="Nobu Tribeca, New York"))
