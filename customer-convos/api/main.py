from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from db.models import Customer, Conversation, Attendee, SalesDeck, Recording, get_engine
import config

app = FastAPI(title="Customer Convos API")
engine = get_engine(config.DATABASE_URL)


# --- Conversations ---

@app.get("/conversations")
def list_conversations(status: str = None, customer_id: str = None, limit: int = 50):
    with Session(engine) as session:
        q = session.query(Conversation)
        if status:
            q = q.filter(Conversation.status == status)
        if customer_id:
            q = q.filter(Conversation.customer_id == customer_id)
        convos = q.order_by(Conversation.start_time.desc()).limit(limit).all()
        return [_serialize_convo(c) for c in convos]


@app.get("/conversations/{convo_id}")
def get_conversation(convo_id: str):
    with Session(engine) as session:
        convo = session.query(Conversation).filter_by(id=convo_id).first()
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return _serialize_convo(convo, full=True)


# --- Customers ---

@app.get("/customers")
def list_customers():
    with Session(engine) as session:
        customers = session.query(Customer).order_by(Customer.name).all()
        return [_serialize_customer(c) for c in customers]


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str):
    with Session(engine) as session:
        customer = session.query(Customer).filter_by(id=customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        convos = session.query(Conversation).filter_by(customer_id=customer_id).order_by(Conversation.start_time.desc()).all()
        result = _serialize_customer(customer)
        result["conversations"] = [_serialize_convo(c) for c in convos]
        return result


# --- Serializers ---

def _serialize_customer(c: Customer) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "domain": c.domain,
        "salesforce_account_id": c.salesforce_account_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_convo(c: Conversation, full: bool = False) -> dict:
    result = {
        "id": c.id,
        "title": c.title,
        "status": c.status,
        "start_time": c.start_time.isoformat() if c.start_time else None,
        "end_time": c.end_time.isoformat() if c.end_time else None,
        "customer_id": c.customer_id,
        "gong_call_id": c.gong_call_id,
    }
    if full:
        result["attendees"] = [
            {"name": a.name, "email": a.email, "is_internal": a.is_internal}
            for a in c.attendees
        ]
        result["sales_decks"] = [
            {"name": d.name, "url": d.url, "modified_at": d.modified_at.isoformat() if d.modified_at else None}
            for d in c.sales_decks
        ]
        result["recording"] = {
            "recording_url": c.recording.recording_url,
            "transcript_url": c.recording.transcript_url,
            "has_transcript": bool(c.recording.transcript_text),
        } if c.recording else None
    return result
