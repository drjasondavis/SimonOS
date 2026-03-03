from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, ForeignKey, create_engine
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()


def new_uuid():
    return str(uuid.uuid4())


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=False, unique=True)
    salesforce_account_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="customer")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id"), nullable=True)
    calendar_event_id = Column(String, unique=True, nullable=False)
    gong_call_id = Column(String, nullable=True)
    title = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    # pending | enriched | no_match
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="conversations")
    attendees = relationship("Attendee", back_populates="conversation")
    sales_decks = relationship("SalesDeck", back_populates="conversation")
    recording = relationship("Recording", back_populates="conversation", uselist=False)


class Attendee(Base):
    __tablename__ = "attendees"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=False)
    name = Column(String)
    email = Column(String, nullable=False)
    is_internal = Column(Boolean, default=False)

    conversation = relationship("Conversation", back_populates="attendees")


class SalesDeck(Base):
    __tablename__ = "sales_decks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=False)
    drive_file_id = Column(String, nullable=False)
    name = Column(String)
    url = Column(String)
    modified_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="sales_decks")


class Recording(Base):
    __tablename__ = "recordings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=new_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=False)
    gong_call_id = Column(String)
    recording_url = Column(String)
    transcript_url = Column(String)
    transcript_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="recording")


def get_engine(database_url: str):
    return create_engine(database_url)


def create_tables(engine):
    Base.metadata.create_all(engine)
