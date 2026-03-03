"""Google Calendar read/write integration.

Two auth paths:
  - Work calendar (Google Workspace): service account with domain-wide delegation
  - Personal calendar (Gmail): OAuth 2.0 with a stored refresh token

Run `python scripts/authorize_personal.py` once to generate the refresh token.
"""
from datetime import datetime

from google.oauth2 import service_account, credentials as oauth2_credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import config

WORK_SCOPES = ["https://www.googleapis.com/auth/calendar"]
PERSONAL_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _work_service():
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=WORK_SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def _personal_service():
    creds = oauth2_credentials.Credentials(
        token=None,
        refresh_token=config.GOOGLE_PERSONAL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=config.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=PERSONAL_SCOPES,
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


def _service_for(calendar_id: str):
    """Return the right service based on which calendar we're accessing."""
    if calendar_id == config.PERSONAL_CALENDAR_ID:
        return _personal_service()
    return _work_service()


def fetch_events(calendar_id: str, start: datetime, end: datetime) -> list[dict]:
    service = _service_for(calendar_id)
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
    return _work_service().events().insert(calendarId=calendar_id, body=body).execute()


def update_event(calendar_id: str, event_id: str, body: dict) -> dict:
    return _work_service().events().update(
        calendarId=calendar_id, eventId=event_id, body=body
    ).execute()


def delete_event(calendar_id: str, event_id: str):
    _work_service().events().delete(calendarId=calendar_id, eventId=event_id).execute()


def upsert_location_event(calendar_id: str, date: str, location: str,
                          existing_id: str = None) -> str:
    body = {
        "summary": f"📍 {location}",
        "start": {"date": date},
        "end": {"date": date},
        "visibility": "private",
        "transparency": "transparent",
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
