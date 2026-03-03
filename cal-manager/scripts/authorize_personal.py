"""
One-time OAuth 2.0 authorization for the personal Gmail calendar.

Run this once:
  python scripts/authorize_personal.py

It will open a browser, ask you to log in to jvdavis@gmail.com, and then
print the refresh token to paste into your .env file.

Prerequisites:
  1. In Google Cloud Console, create an OAuth 2.0 Client ID (Desktop app type)
  2. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env first
"""
from pathlib import Path
from dotenv import load_dotenv

_root = Path(__file__).parent.parent.parent
load_dotenv(_root / ".env")
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

if not client_id or not client_secret:
    raise SystemExit(
        "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env first."
    )

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
creds = flow.run_local_server(port=0)

print("\n✅ Authorization successful!\n")
print("Add this to your .env file:")
print(f"\nGOOGLE_PERSONAL_REFRESH_TOKEN={creds.refresh_token}\n")
