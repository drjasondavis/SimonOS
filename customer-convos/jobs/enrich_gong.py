"""
Job: Match pending conversations to Gong calls and pull recordings/transcripts.
"""
from sqlalchemy.orm import Session
from db.models import Conversation, Recording, get_engine
from integrations import gong
import config

engine = get_engine(config.DATABASE_URL)


def run():
    with Session(engine) as session:
        pending = session.query(Conversation).filter_by(status="pending").all()

        for convo in pending:
            attendee_emails = [a.email for a in convo.attendees]
            call = gong.find_call(convo.start_time, attendee_emails)

            if not call:
                print(f"No Gong match for: {convo.title}")
                continue

            gong_call_id = call["metaData"]["id"]
            transcript = gong.get_transcript(gong_call_id)

            session.add(Recording(
                conversation_id=convo.id,
                gong_call_id=gong_call_id,
                recording_url=call["metaData"].get("url"),
                transcript_text=transcript,
            ))

            convo.gong_call_id = gong_call_id
            print(f"Enriched with Gong: {convo.title}")

        session.commit()


if __name__ == "__main__":
    run()
