"""Google Maps travel time estimation."""
from datetime import datetime
import googlemaps
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = googlemaps.Client(key=config.GOOGLE_MAPS_API_KEY)
    return _client


def get_travel_minutes(origin: str, destination: str,
                       departure_time: datetime = None) -> int:
    """Return estimated driving time in minutes between two addresses."""
    if origin.strip().lower() == destination.strip().lower():
        return 0

    client = _get_client()
    result = client.distance_matrix(
        origins=[origin],
        destinations=[destination],
        mode="driving",
        departure_time=departure_time or "now",
    )
    try:
        element = result["rows"][0]["elements"][0]
        if element["status"] != "OK":
            return 30  # fallback
        # Prefer duration_in_traffic when available (requires departure_time)
        duration = element.get("duration_in_traffic") or element["duration"]
        return duration["value"] // 60
    except (KeyError, IndexError):
        return 30  # fallback: assume 30 minutes
