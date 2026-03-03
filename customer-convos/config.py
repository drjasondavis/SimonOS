import os

# Internal domains — attendees with these domains are considered internal
INTERNAL_DOMAINS = os.getenv("INTERNAL_DOMAINS", "").split(",")

# Google
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_CALENDAR_IDS = os.getenv("GOOGLE_CALENDAR_IDS", "").split(",")
GOOGLE_DRIVE_SALES_DECKS_FOLDER_ID = os.getenv("GOOGLE_DRIVE_SALES_DECKS_FOLDER_ID")

# Gong
GONG_API_KEY = os.getenv("GONG_API_KEY")
GONG_API_SECRET = os.getenv("GONG_API_SECRET")

# Salesforce
SALESFORCE_USERNAME = os.getenv("SALESFORCE_USERNAME")
SALESFORCE_PASSWORD = os.getenv("SALESFORCE_PASSWORD")
SALESFORCE_SECURITY_TOKEN = os.getenv("SALESFORCE_SECURITY_TOKEN")
SALESFORCE_DOMAIN = os.getenv("SALESFORCE_DOMAIN", "login")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/customer_convos")

# Job schedule
CALENDAR_POLL_INTERVAL_MINUTES = int(os.getenv("CALENDAR_POLL_INTERVAL_MINUTES", "60"))
CALENDAR_LOOKBACK_DAYS = int(os.getenv("CALENDAR_LOOKBACK_DAYS", "7"))
