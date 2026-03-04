"""
Gong integration via REST API.
Docs: https://us-14321.app.gong.io/settings/api/documentation

Requires GONG_ACCESS_KEY and GONG_ACCESS_SECRET in config.
"""
from datetime import datetime, timedelta
import base64
import requests
import config

BASE_URL = "https://api.gong.io/v2"


def _auth_header() -> dict:
    token = base64.b64encode(
        f"{config.GONG_ACCESS_KEY}:{config.GONG_ACCESS_SECRET}".encode()
    ).decode()
    return {"Authorization": f"Basic {token}"}


def find_call(start_time: datetime, attendee_emails: list[str]) -> dict | None:
    """
    Search Gong for a call matching the given start time (± 30 min)
    and at least one attendee email.
    Returns the first matching call or None.
    """
    if not config.GONG_ACCESS_KEY:
        # Stub: return None until credentials are configured
        return None

    window_start = (start_time - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = (start_time + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = requests.post(
        f"{BASE_URL}/calls/extensive",
        headers=_auth_header(),
        json={
            "filter": {
                "fromDateTime": window_start,
                "toDateTime": window_end,
            }
        },
    )
    response.raise_for_status()
    calls = response.json().get("calls", [])

    attendee_set = {e.lower() for e in attendee_emails}
    for call in calls:
        parties = call.get("parties", [])
        call_emails = {p.get("emailAddress", "").lower() for p in parties}
        if attendee_set & call_emails:
            return call

    return None


def get_transcript(gong_call_id: str) -> str | None:
    """Fetch transcript text for a call by ID."""
    if not config.GONG_ACCESS_KEY:
        return None

    response = requests.post(
        f"{BASE_URL}/calls/transcript",
        headers=_auth_header(),
        json={"filter": {"callIds": [gong_call_id]}},
    )
    response.raise_for_status()
    transcripts = response.json().get("callTranscripts", [])
    if not transcripts:
        return None

    sentences = []
    for utterance in transcripts[0].get("transcript", []):
        for sentence in utterance.get("sentences", []):
            sentences.append(sentence.get("text", ""))
    return " ".join(sentences)
