from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, create_engine
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Event(Base):
    """Cached calendar event with analysis metadata."""
    __tablename__ = "events"

    id = Column(String, primary_key=True)          # Google event ID
    calendar_id = Column(String, nullable=False)
    title = Column(String)
    start = Column(DateTime(timezone=True))
    end = Column(DateTime(timezone=True))
    location = Column(String)
    description = Column(Text)
    visibility = Column(String)                    # "public", "private", "default"
    is_all_day = Column(Boolean, default=False)
    has_zoom = Column(Boolean, default=False)
    has_location = Column(Boolean, default=False)  # physical in-person location
    is_working_hours = Column(Boolean, default=True)
    raw_json = Column(Text)
    last_synced = Column(DateTime(timezone=True))


class TravelHold(Base):
    """Travel buffer blocks we have created between in-person events."""
    __tablename__ = "travel_holds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hold_event_id = Column(String, nullable=False)  # Google event ID of the created hold
    from_event_id = Column(String)
    to_event_id = Column(String)
    from_location = Column(String)
    to_location = Column(String)
    travel_minutes = Column(Integer)
    created_at = Column(DateTime(timezone=True))


class WifeNotification(Base):
    """After-hours events for which we've created a wife calendar event."""
    __tablename__ = "wife_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_event_id = Column(String, nullable=False, unique=True)
    wife_event_id = Column(String)               # event ID created on wife's calendar
    created_at = Column(DateTime(timezone=True))


class LocationDay(Base):
    """All-day location events we manage on the work calendar."""
    __tablename__ = "location_days"

    date = Column(String, primary_key=True)      # YYYY-MM-DD
    location = Column(String)
    all_day_event_id = Column(String)
    updated_at = Column(DateTime(timezone=True))


def get_engine(database_url: str):
    return create_engine(database_url)


def create_tables(engine):
    Base.metadata.create_all(engine)
