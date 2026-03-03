"""
Job: Poll Google Calendar for new external meetings and create conversation records.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from db.models import Customer, Conversation, Attendee, get_engine
from integrations import google_calendar, salesforce
import config

engine = get_engine(config.DATABASE_URL)


def get_or_create_customer(session: Session, domain: str) -> Customer:
    customer = session.query(Customer).filter_by(domain=domain).first()
    if customer:
        return customer

    # Try to enrich from Salesforce
    sf_account = salesforce.find_account_by_domain(domain)
    customer = Customer(
        domain=domain,
        name=sf_account["Name"] if sf_account else domain,
        salesforce_account_id=sf_account["Id"] if sf_account else None,
    )
    session.add(customer)
    session.flush()
    return customer


def run():
    with Session(engine) as session:
        for calendar_id in config.GOOGLE_CALENDAR_IDS:
            events = google_calendar.fetch_recent_events(calendar_id)

            for event in events:
                parsed = google_calendar.parse_event(event)
                event_id = parsed["calendar_event_id"]

                # Skip if already tracked
                if session.query(Conversation).filter_by(calendar_event_id=event_id).first():
                    continue

                # Determine customer from first external attendee domain
                external_attendees = [
                    a for a in parsed["attendees"] if not a["is_internal"]
                ]
                customer = None
                if external_attendees:
                    domain = external_attendees[0]["email"].split("@")[-1]
                    customer = get_or_create_customer(session, domain)

                convo = Conversation(
                    calendar_event_id=event_id,
                    customer_id=customer.id if customer else None,
                    title=parsed["title"],
                    start_time=parsed["start_time"],
                    end_time=parsed["end_time"],
                    status="pending",
                )
                session.add(convo)
                session.flush()

                for a in parsed["attendees"]:
                    session.add(Attendee(
                        conversation_id=convo.id,
                        name=a["name"],
                        email=a["email"],
                        is_internal=a["is_internal"],
                    ))

                print(f"Created conversation: {parsed['title']} ({event_id})")

        session.commit()


if __name__ == "__main__":
    run()
