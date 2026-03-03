"""
Runs all calendar management jobs in sequence.
Can be triggered manually or via cron.

Example cron (every 30 minutes):
  */30 * * * * cd /path/to/cal-manager && python scheduler.py >> logs/scheduler.log 2>&1

Or run the API server separately:
  uvicorn api.server:app --port 5555 --reload
"""
from dotenv import load_dotenv
load_dotenv()

from db.models import get_engine, create_tables
from jobs import poll_events, location_updater, travel_holds, wife_notifications, conflict_checker
import config

if __name__ == "__main__":
    print("--- Initializing DB ---")
    engine = get_engine(config.DATABASE_URL)
    create_tables(engine)

    print("--- Polling events ---")
    poll_events.run()

    print("--- Updating today's location ---")
    location_updater.run()

    print("--- Creating travel holds ---")
    travel_holds.run()

    print("--- Notifying wife of after-hours events ---")
    wife_notifications.run()

    print("--- Checking work/personal conflicts ---")
    conflicts = conflict_checker.run()
    if conflicts:
        print(f"  ⚠️  {len(conflicts)} conflict(s) detected — check output above")

    print("--- Done ---")
