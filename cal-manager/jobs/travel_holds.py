"""
Job: For consecutive in-person events, calculate driving time via Google Maps
and insert a travel block between them. Warns if there isn't enough gap.

Only creates a hold if one doesn't already exist for that event pair.
"""
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, TravelHold, get_engine
from integrations import google_calendar, google_maps
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def run():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=config.LOOKAHEAD_DAYS)

    with Session(engine) as session:
        events = (
            session.query(Event)
            .filter(
                Event.calendar_id == config.WORK_CALENDAR_ID,
                Event.has_location == True,
                Event.has_zoom == False,
                Event.start >= now,
                Event.start <= end,
            )
            .order_by(Event.start)
            .all()
        )

        for i in range(len(events) - 1):
            a, b = events[i], events[i + 1]

            # Skip if same location
            if (a.location or "").strip().lower() == (b.location or "").strip().lower():
                continue

            gap_minutes = (b.start - a.end).total_seconds() / 60
            if gap_minutes < 0:
                continue  # overlapping events — not our job to fix

            # Skip if hold already exists for this pair
            existing = session.query(TravelHold).filter_by(
                from_event_id=a.id, to_event_id=b.id
            ).first()
            if existing:
                continue

            travel_mins = google_maps.get_travel_minutes(
                a.location, b.location, departure_time=a.end
            )

            if gap_minutes < travel_mins:
                print(
                    f"[travel_holds] ⚠️  Not enough time between '{a.title}' "
                    f"and '{b.title}' (need {travel_mins}min, have {int(gap_minutes)}min)"
                )
                hold_start = a.end
                hold_end = b.start  # fill the whole gap
            else:
                hold_start = a.end
                hold_end = a.end + timedelta(minutes=travel_mins)

            from_short = a.location.split(",")[0]
            to_short = b.location.split(",")[0]

            ev = google_calendar.create_travel_hold(
                config.WORK_CALENDAR_ID,
                f"🚗 Travel → {to_short}",
                hold_start,
                hold_end,
                a.location,
                b.location,
            )

            session.add(TravelHold(
                hold_event_id=ev["id"],
                from_event_id=a.id,
                to_event_id=b.id,
                from_location=a.location,
                to_location=b.location,
                travel_minutes=travel_mins,
                created_at=datetime.now(timezone.utc),
            ))
            print(f"[travel_holds] Created hold: {from_short} → {to_short} ({travel_mins}min)")

        session.commit()

    print("[travel_holds] Done.")


if __name__ == "__main__":
    run()
