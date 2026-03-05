import os
from pathlib import Path
from dotenv import load_dotenv

# Load shared root .env first, then project-level .env (project values win)
# override=True ensures .env values beat anything inherited from the shell environment
_root = Path(__file__).parent.parent
_project = Path(__file__).parent / ".env"
print(f"[config] loading root: {_root / '.env'}")
print(f"[config] loading project: {_project} exists={_project.exists()}")
load_dotenv(_root / ".env", override=True)
load_dotenv(_project, override=True)

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Identity
USER_NAME = os.getenv("USER_NAME", "Jason")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Simon AI")

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "America/Chicago")

# Working hours (used by scheduling handler)
WORK_HOURS_START = float(os.getenv("WORK_HOURS_START", "9"))
WORK_HOURS_END = int(os.getenv("WORK_HOURS_END", "18"))
WORK_DAYS = [int(d) for d in os.getenv("WORK_DAYS", "0,1,2,3,4").split(",")]

# Database (used by scheduling handler to read calendar events)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/cal_manager")

# API server
API_PORT = int(os.getenv("API_PORT", "5556"))
API_SECRET = os.getenv("API_SECRET", "change-me")
