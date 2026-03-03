"""
Job: For each in-person event, create travel holds departing from home (outbound)
and returning home (inbound). Each direction is checked and created independently.
"""
from datetime import datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from db.models import Event, TravelHold, get_engine
from integrations import google_calendar, google_maps
import config

tz = pytz.timezone(config.TIMEZONE)
engine = get_engine(config.DATABASE_URL)


def dbg(msg):
    if config.TEST_MODE:
        print(f"  [debug] {msg}")


def create_hold(session, title, hold_start, hold_end, from_loc, to_loc,
                from_event_id, to_event_id, travel_mins):
    ev = google_calendar.create_travel_hold(
        config.WORK_CALENDAR_ID, title, hold_start, hold_end, from_loc, to_loc
    )
    session.add(TravelHold(
        hold_event_id=ev["id"],
        from_event_id=from_event_id,
        to_event_id=to_event_id,
        from_location=from_loc,
        to_location=to_loc,
        travel_minutes=travel_mins,
        created_at=datetime.now(timezone.utc),
    ))


def run():
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=config.LOOKAHEAD_DAYS)
    home = config.HOME_ADDRESS
    home_short = home.split(",")[0]

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

        dbg(f"Found {len(events)} in-person events, checking travel holds for each")

        for event in events:
            local_start = event.start.astimezone(tz).strftime("%a %b %d %I:%M%p")
            dest_short = event.location.split(",")[0]
            dbg(f"Event: '{event.title}' at {dest_short} ({local_start})")

            # --- Outbound: home → event ---
            outbound_exists = session.query(TravelHold).filter_by(
                to_event_id=event.id
            ).first()

            if outbound_exists:
                dbg(f"  → Outbound hold already exists, skipping")
            else:
                dbg(f"  → Querying outbound: home → {dest_short}")
                travel_mins, mode = google_maps.get_travel_minutes(
                    home, event.location, departure_time=event.start
                )
                emoji = "🚶" if mode == "WALK" else "🚇"
                dbg(f"  → Outbound: {travel_mins}min ({mode})")

                hold_start = event.start - timedelta(minutes=travel_mins)
                if hold_start < now:
                    dbg(f"  → ⚠️  Outbound hold would start in the past, skipping")
                else:
                    create_hold(
                        session,
                        title=f"{emoji} Travel → {dest_short}",
                        hold_start=hold_start,
                        hold_end=event.start,
                        from_loc=home,
                        to_loc=event.location,
                        from_event_id=None,
                        to_event_id=event.id,
                        travel_mins=travel_mins,
                    )
                    print(f"[travel_holds] {home_short} → {dest_short} ({travel_mins}min {mode} before '{event.title}')")

            # --- Return: event → home ---
            return_exists = session.query(TravelHold).filter(
                TravelHold.from_event_id == event.id,
                TravelHold.to_event_id == None,
            ).first()

            if return_exists:
                dbg(f"  → Return hold already exists, skipping")
            else:
                dbg(f"  → Querying return: {dest_short} → home")
                return_mins, return_mode = google_maps.get_travel_minutes(
                    event.location, home, departure_time=event.end
                )
                return_emoji = "🚶" if return_mode == "WALK" else "🚇"
                dbg(f"  → Return: {return_mins}min ({return_mode})")

                create_hold(
                    session,
                    title=f"{return_emoji} Travel → home",
                    hold_start=event.end,
                    hold_end=event.end + timedelta(minutes=return_mins),
                    from_loc=event.location,
                    to_loc=home,
                    from_event_id=event.id,
                    to_event_id=None,
                    travel_mins=return_mins,
                )
                print(f"[travel_holds] {dest_short} → home ({return_mins}min {return_mode} after '{event.title}')")

        session.commit()

    print("[travel_holds] Done.")


if __name__ == "__main__":
    run()
