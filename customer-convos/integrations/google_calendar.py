from datetime import datetime, timedelta, timezone
from google.oauth2 import service_account
from googleapiclient.discovery import build
import config

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def is_external(email: str) -> bool:
    domain = email.split("@")[-1].lower()
    return domain not in [d.lower() for d in config.INTERNAL_DOMAINS]


def fetch_recent_events(calendar_id: str, lookback_days: int = None) -> list[dict]:
    """Fetch calendar events from the past N days that have at least one external attendee."""
    lookback_days = lookback_days or config.CALENDAR_LOOKBACK_DAYS
    service = get_service()

    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=lookback_days)).isoformat()
    time_max = now.isoformat()

    results = []
    page_token = None

    while True:
        response = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()

        for event in response.get("items", []):
            attendees = event.get("attendees", [])
            external = [a for a in attendees if is_external(a.get("email", ""))]
            if external:
                results.append(event)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def parse_event(event: dict) -> dict:
    """Normalize a Google Calendar event into a flat dict."""
    attendees = event.get("attendees", [])
    start = event["start"].get("dateTime") or event["start"].get("date")
    end = event["end"].get("dateTime") or event["end"].get("date")

    return {
        "calendar_event_id": event["id"],
        "title": event.get("summary", "(no title)"),
        "start_time": datetime.fromisoformat(start),
        "end_time": datetime.fromisoformat(end),
        "attendees": [
            {
                "name": a.get("displayName", ""),
                "email": a.get("email", ""),
                "is_internal": not is_external(a.get("email", "")),
            }
            for a in attendees
        ],
    }
