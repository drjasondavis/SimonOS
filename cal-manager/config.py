import os
from pathlib import Path
from dotenv import load_dotenv

# Load shared root .env first, then project-level .env (project values win)
_root = Path(__file__).parent.parent
load_dotenv(_root / ".env")
load_dotenv(Path(__file__).parent / ".env", override=True)

# Calendars
WORK_CALENDAR_ID = os.getenv("WORK_CALENDAR_ID", "primary")
PERSONAL_CALENDAR_ID = os.getenv("PERSONAL_CALENDAR_ID", "")

# Internal domains — organizers from these domains are treated as colleagues, not external
INTERNAL_DOMAINS = [
    d.strip().lower()
    for d in os.getenv("INTERNAL_DOMAINS", "simondata.com,simon.ai").split(",")
    if d.strip()
]

WIFE_EMAIL = os.getenv("WIFE_EMAIL", "kkutzke@gmail.com")

# Working hours (24h format, local time)
WORK_HOURS_START = int(os.getenv("WORK_HOURS_START", "9"))   # 9am
WORK_HOURS_END = int(os.getenv("WORK_HOURS_END", "18"))      # 6pm
WORK_DAYS = [int(d) for d in os.getenv("WORK_DAYS", "0,1,2,3,4").split(",")]  # 0=Mon

# Locations
HOME_ADDRESS = os.getenv("HOME_ADDRESS", "")
SUMMER_ADDRESS = os.getenv("SUMMER_ADDRESS", "")
TIMEZONE = os.getenv("TIMEZONE", "America/Chicago")

# Google — Workspace (service account with optional impersonation)
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_IMPERSONATE_EMAIL = os.getenv("GOOGLE_IMPERSONATE_EMAIL", "")

# Google — Personal Gmail (OAuth 2.0, read-only)
# Run scripts/authorize_personal.py once to populate the refresh token
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_PERSONAL_REFRESH_TOKEN = os.getenv("GOOGLE_PERSONAL_REFRESH_TOKEN", "")

# Google Maps
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/cal_manager")

# Scheduling
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "14"))

# Identity (used for invite title generation)
USER_NAME = os.getenv("USER_NAME", "Jason")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Simon AI")

# API server (used by Chrome extension)
API_PORT = int(os.getenv("API_PORT", "5555"))
API_SECRET = os.getenv("API_SECRET", "change-me")

# Test mode — print every write action and ask for confirmation before executing
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
