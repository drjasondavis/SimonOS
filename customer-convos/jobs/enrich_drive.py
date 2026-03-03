"""
Job: Search Google Drive sales decks folder for materials related to each conversation.
"""
from sqlalchemy.orm import Session
from db.models import Conversation, SalesDeck, get_engine
from integrations import google_drive
import config

engine = get_engine(config.DATABASE_URL)


def run():
    with Session(engine) as session:
        # Enrich all conversations that don't yet have decks
        convos = (
            session.query(Conversation)
            .filter(~Conversation.sales_decks.any())
            .all()
        )

        for convo in convos:
            decks = google_drive.find_decks_for_call(convo.start_time)

            for deck in decks:
                session.add(SalesDeck(
                    conversation_id=convo.id,
                    **deck,
                ))

            if decks:
                print(f"Linked {len(decks)} deck(s) to: {convo.title}")
            else:
                print(f"No decks found for: {convo.title}")

        session.commit()


if __name__ == "__main__":
    run()
