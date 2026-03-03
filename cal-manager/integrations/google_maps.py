"""Google Maps travel time estimation using the Routes API.

Travel mode preference:
  - Walk if ≤ 20 minutes
  - Public transit otherwise
"""
from datetime import datetime, timezone
import requests
import config

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
WALK_THRESHOLD_MINUTES = 20


def _query(origin: str, destination: str, mode: str,
           departure_time: datetime = None) -> int:
    """Call the Routes API for a specific travel mode. Returns minutes or None on failure."""
    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": mode,
    }

    if departure_time:
        utc_time = departure_time.astimezone(timezone.utc)
        body["departureTime"] = utc_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        if mode == "DRIVE":
            body["routingPreference"] = "TRAFFIC_AWARE"

    response = requests.post(
        ROUTES_URL,
        json=body,
        headers={
            "X-Goog-Api-Key": config.GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "routes.duration",
        },
        timeout=10,
    )

    if not response.ok:
        print(f"[google_maps] {mode} query error {response.status_code}: {response.text}")
        return None

    try:
        duration_str = response.json()["routes"][0]["duration"]  # e.g. "1823s"
        return int(duration_str.rstrip("s")) // 60
    except (KeyError, IndexError, ValueError):
        print(f"[google_maps] {mode} unexpected response: {response.text}")
        return None


def get_travel_minutes(origin: str, destination: str,
                       departure_time: datetime = None) -> tuple:
    """
    Returns (minutes, mode) using preferred travel mode:
      - Walk if ≤ 20 min
      - Transit otherwise
    Falls back to 30 min / TRANSIT if both queries fail.
    """
    if origin.strip().lower() == destination.strip().lower():
        return 0, "WALK"

    walk_mins = _query(origin, destination, "WALK", departure_time)
    if walk_mins is not None and walk_mins <= WALK_THRESHOLD_MINUTES:
        return walk_mins, "WALK"

    transit_mins = _query(origin, destination, "TRANSIT", departure_time)
    if transit_mins is not None:
        return transit_mins, "TRANSIT"

    return 30, "TRANSIT"  # fallback
