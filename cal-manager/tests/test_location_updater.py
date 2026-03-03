"""Tests for location_updater: seasonal base, home-base detection, travel inference."""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from jobs.location_updater import is_summer, base_location, is_home_base, infer_travel_location
from tests.conftest import make_event, MON_10AM


# ---------------------------------------------------------------------------
# is_summer
# ---------------------------------------------------------------------------

class TestIsSummer:
    def _today(self, month):
        return MagicMock(month=month)

    def test_july_is_summer(self):
        with patch("jobs.location_updater.date") as d:
            d.today.return_value = self._today(7)
            assert is_summer() is True

    def test_august_is_summer(self):
        with patch("jobs.location_updater.date") as d:
            d.today.return_value = self._today(8)
            assert is_summer() is True

    def test_june_not_summer(self):
        with patch("jobs.location_updater.date") as d:
            d.today.return_value = self._today(6)
            assert is_summer() is False

    def test_september_not_summer(self):
        with patch("jobs.location_updater.date") as d:
            d.today.return_value = self._today(9)
            assert is_summer() is False

    def test_january_not_summer(self):
        with patch("jobs.location_updater.date") as d:
            d.today.return_value = self._today(1)
            assert is_summer() is False


# ---------------------------------------------------------------------------
# base_location
# ---------------------------------------------------------------------------

class TestBaseLocation:
    def test_non_summer_returns_home(self):
        with patch("jobs.location_updater.is_summer", return_value=False), \
             patch("jobs.location_updater.config") as cfg:
            cfg.HOME_ADDRESS = "363 2nd St Brooklyn, NY 11215"
            cfg.SUMMER_ADDRESS = "18 East Landing Rd Hampton Bays, NY 11946"
            assert base_location() == "363 2nd St Brooklyn"

    def test_summer_returns_summer_address(self):
        with patch("jobs.location_updater.is_summer", return_value=True), \
             patch("jobs.location_updater.config") as cfg:
            cfg.HOME_ADDRESS = "363 2nd St Brooklyn, NY 11215"
            cfg.SUMMER_ADDRESS = "18 East Landing Rd Hampton Bays, NY 11946"
            assert base_location() == "18 East Landing Rd Hampton Bays"

    def test_summer_no_summer_address_falls_back_to_home(self):
        with patch("jobs.location_updater.is_summer", return_value=True), \
             patch("jobs.location_updater.config") as cfg:
            cfg.HOME_ADDRESS = "363 2nd St Brooklyn, NY 11215"
            cfg.SUMMER_ADDRESS = ""
            assert base_location() == "363 2nd St Brooklyn"


# ---------------------------------------------------------------------------
# is_home_base
# ---------------------------------------------------------------------------

class TestIsHomeBase:
    def test_matches_base(self):
        with patch("jobs.location_updater.base_location", return_value="Brooklyn"):
            assert is_home_base("Brooklyn") is True

    def test_case_insensitive(self):
        with patch("jobs.location_updater.base_location", return_value="Brooklyn"):
            assert is_home_base("brooklyn") is True

    def test_different_city(self):
        with patch("jobs.location_updater.base_location", return_value="Brooklyn"):
            assert is_home_base("Chicago") is False


# ---------------------------------------------------------------------------
# infer_travel_location
# ---------------------------------------------------------------------------

class TestInferTravelLocation:
    # Rule 1: all-day event title used as location
    def test_allday_non_nyc_event_is_location(self):
        e = make_event(title="Chicago", is_all_day=True)
        assert infer_travel_location([e]) == "Chicago"

    def test_allday_own_location_event_skipped(self):
        e = make_event(title="📍 Brooklyn", is_all_day=True)
        assert infer_travel_location([e]) == ""

    def test_allday_nyc_event_skipped(self):
        e = make_event(title="New York", is_all_day=True)
        assert infer_travel_location([e]) == ""

    def test_allday_too_long_skipped(self):
        e = make_event(title="This is a very long event title that is not a city name at all", is_all_day=True)
        assert infer_travel_location([e]) == ""

    # Rule 2: travel keyword in event title
    def test_flight_to_destination(self):
        e = make_event(title="Flight to Austin")
        assert infer_travel_location([e]) == "Austin"

    def test_traveling_to_destination(self):
        e = make_event(title="Traveling to Los Angeles")
        assert infer_travel_location([e]) == "Los Angeles"

    def test_trip_to_destination(self):
        e = make_event(title="Trip to Miami")
        assert infer_travel_location([e]) == "Miami"

    def test_travel_keyword_nyc_destination_skipped(self):
        e = make_event(title="Flight to New York")
        assert infer_travel_location([e]) == ""

    # Rule 3: in-person event with non-NYC address
    def test_in_person_non_nyc_address(self):
        e = make_event(has_location=True, has_zoom=False, location="200 S Wacker Dr, Chicago, IL")
        assert infer_travel_location([e]) == "200 S Wacker Dr"

    def test_in_person_nyc_address_skipped(self):
        e = make_event(has_location=True, has_zoom=False, location="350 5th Ave, Manhattan, NY")
        assert infer_travel_location([e]) == ""

    def test_zoom_event_not_a_location(self):
        e = make_event(has_location=False, has_zoom=True, location="https://zoom.us/j/123")
        assert infer_travel_location([e]) == ""

    # Rule priority
    def test_allday_takes_priority_over_keyword(self):
        allday = make_event(title="Austin", is_all_day=True)
        flight = make_event(title="Flight to Dallas")
        assert infer_travel_location([allday, flight]) == "Austin"

    def test_no_signals_returns_empty(self):
        e = make_event(title="Team Standup", has_zoom=True)
        assert infer_travel_location([e]) == ""
