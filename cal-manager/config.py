import os

# Calendars
WORK_CALENDAR_ID = os.getenv("WORK_CALENDAR_ID", "primary")
PERSONAL_CALENDAR_ID = os.getenv("PERSONAL_CALENDAR_ID", "")

WIFE_EMAIL = os.getenv("WIFE_EMAIL", "kkutzke@gmail.com")

# Working hours (24h format, local time)
WORK_HOURS_START = int(os.getenv("WORK_HOURS_START", "9"))   # 9am
WORK_HOURS_END = int(os.getenv("WORK_HOURS_END", "18"))      # 6pm
WORK_DAYS = [int(d) for d in os.getenv("WORK_DAYS", "0,1,2,3,4").split(",")]  # 0=Mon

# Locations
HOME_ADDRESS = os.getenv("HOME_ADDRESS", "")
WORK_ADDRESS = os.getenv("WORK_ADDRESS", "")
TIMEZONE = os.getenv("TIMEZONE", "America/Chicago")

# Google
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/cal_manager")

# Scheduling
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))
LOOKAHEAD_DAYS = int(os.getenv("LOOKAHEAD_DAYS", "14"))

# API server (used by Chrome extension)
API_PORT = int(os.getenv("API_PORT", "5555"))
API_SECRET = os.getenv("API_SECRET", "change-me")
