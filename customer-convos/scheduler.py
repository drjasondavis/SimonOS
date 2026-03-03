"""
Runs all enrichment jobs in sequence.
Can be triggered manually or via cron.

Example cron (every hour):
  0 * * * * cd /path/to/customer-convos && python scheduler.py
"""
from jobs import poll_calendar, enrich_gong, enrich_drive

if __name__ == "__main__":
    print("--- Polling calendar ---")
    poll_calendar.run()

    print("--- Enriching with Gong ---")
    enrich_gong.run()

    print("--- Enriching with Drive ---")
    enrich_drive.run()

    print("--- Done ---")
