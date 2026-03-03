"""Google Calendar read/write integration.

Requires a service account with domain-wide delegation and the
https://www.googleapis.com/auth/calendar scope.
"""
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    # Impersonate the calendar owner so we can write on their behalf
    # Set GOOGLE_IMPERSONATE_EMAIL in .env if using domain-wide delegation
    import os
    impersonate = os.getenv("GOOGLE_IMPERSONATE_EMAIL")
    if impersonate:
        creds = creds.with_subject(impersonate)
    return build("calendar", "v3", credentials=creds)


def fetch_events(calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    service = get_service()
    results = []
    page_token = None

    while True:
        response = service.events().list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()

        results.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return results


def create_event(calendar_id: str, body: dict) -> dict:
    return get_service().events().insert(calendarId=calendar_id, body=body).execute()


def update_event(calendar_id: str, event_id: str, body: dict) -> dict:
    return get_service().events().update(
        calendarId=calendar_id, eventId=event_id, body=body
    ).execute()


def delete_event(calendar_id: str, event_id: str):
    get_service().events().delete(calendarId=calendar_id, eventId=event_id).execute()


def upsert_location_event(calendar_id: str, date: str, location: str,
                          existing_id: str = None) -> str:
    """Create or update an all-day event showing current location for a given date."""
    body = {
        "summary": f"📍 {location}",
        "start": {"date": date},
        "end": {"date": date},
        "visibility": "private",
        "transparency": "transparent",  # doesn't block time
    }
    if existing_id:
        ev = update_event(calendar_id, existing_id, body)
    else:
        ev = create_event(calendar_id, body)
    return ev["id"]


def create_travel_hold(calendar_id: str, title: str, start: datetime,
                       end: datetime, from_loc: str, to_loc: str) -> dict:
    body = {
        "summary": title,
        "description": f"Travel: {from_loc} → {to_loc}",
        "start": {"dateTime": start.isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": config.TIMEZONE},
        "visibility": "private",
        "colorId": "8",  # graphite
    }
    return create_event(calendar_id, body)


def create_wife_notification_event(title: str, start: datetime, end: datetime,
                                   description: str) -> dict:
    """Create a private event that invites wife so she sees it on her calendar."""
    body = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start.isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": config.TIMEZONE},
        "visibility": "private",
        "attendees": [{"email": config.WIFE_EMAIL}],
        "guestsCanSeeOtherGuests": False,
    }
    return create_event(config.WORK_CALENDAR_ID, body)
