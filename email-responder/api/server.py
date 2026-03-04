"""
Email Responder API — consumed by the Gmail Chrome extension.

Endpoints:
  POST /reply    — classify intent + dispatch to the right handler
  GET  /health   — liveness check

Run with:
  uvicorn api.server:app --port 5556 --reload

Handlers:
  scheduling  — suggest meeting times or create calendar events
  general     — draft a contextually appropriate reply (fallback)

Adding a new handler:
  1. Create api/handlers/my_handler.py with: async def run(...) -> dict
  2. Add an entry to HANDLERS below
  3. Update _classify_intent() to detect when it applies
"""
import json
import logging
import re
from pathlib import Path
from typing import Optional

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.handlers import scheduling, general
import config
print(f"[server] config loaded from: {config.__file__}")

app = FastAPI(title="Email Responder")

_LOG_PATH = Path(__file__).parent / "anthropic_calls.log"
logging.basicConfig(level=logging.INFO)
_log = logging.getLogger("anthropic_calls")
_fh = logging.FileHandler(_LOG_PATH)
_fh.setFormatter(logging.Formatter("%(asctime)s\n%(message)s\n" + "-" * 80))
_log.addHandler(_fh)


def _log_call(label: str, prompt: str, response: str):
    _log.info(f"=== {label} ===\n\nPROMPT:\n{prompt}\n\nRESPONSE:\n{response}")
    print(f"\n[anthropic:{label}] prompt sent ({len(prompt)} chars) → response ({len(response)} chars)")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mail.google.com"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Api-Secret", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

HANDLERS = {
    "scheduling": scheduling,
    "general":    general,
}

# ---------------------------------------------------------------------------
# Intent classifier
# ---------------------------------------------------------------------------

async def _classify_intent(subject: str, email_body: str, thread_context: str) -> str:
    """
    Ask Claude to classify the email into one of the registered handler intents.
    Returns a handler key from HANDLERS.
    """
    handler_list = "\n".join(f'- "{k}"' for k in HANDLERS)
    prompt = f"""Classify the primary intent of this email thread. Respond with a single JSON object — no explanation, no markdown.

Available intents:
{handler_list}

Intent definitions:
- "scheduling" — the thread is about arranging a meeting, call, lunch, dinner, drinks, or any kind of calendar event. This includes both proposing times AND confirming agreed times.
- "general" — any other email: questions, updates, requests, introductions, follow-ups, etc.

Email subject: {subject or "(no subject)"}

User's draft:
{email_body or "(empty)"}

Prior thread:
{thread_context or "(no prior thread)"}

Respond with: {{"intent": "<key>"}}"""

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=64,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = msg.content[0].text if msg.content else ""
    _log_call("classify_intent", prompt, response_text)

    try:
        clean = re.sub(r"^```(?:json)?\s*", "", response_text.strip())
        clean = re.sub(r"\s*```$", "", clean)
        result = json.loads(clean)
        intent = result.get("intent", "general")
        return intent if intent in HANDLERS else "general"
    except (json.JSONDecodeError, KeyError):
        return "general"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _check_auth(secret: Optional[str]):
    print(f"[auth] received={repr(secret)} expected={repr(config.API_SECRET)}")
    if config.API_SECRET and secret != config.API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class ReplyPayload(BaseModel):
    subject: str = ""
    email_body: str = ""
    thread_context: str = ""
    participants: list = []
    # Optional overrides — if set, skip intent classification
    force_handler: str = ""
    # Scheduling-specific
    duration_minutes: int = 60
    days: int = 14


@app.post("/reply")
async def reply(
    payload: ReplyPayload,
    x_api_secret: Optional[str] = Header(default=None),
):
    """
    Main endpoint. Classifies the email intent and dispatches to the
    appropriate handler. Each handler returns:
      { "text": str, "action_url": str | None, "label": str, "mode": str }
    """
    _check_auth(x_api_secret)

    intent = payload.force_handler if payload.force_handler in HANDLERS else await _classify_intent(
        payload.subject, payload.email_body, payload.thread_context
    )

    handler = HANDLERS[intent]
    result = await handler.run(
        subject=payload.subject,
        email_body=payload.email_body,
        thread_context=payload.thread_context,
        participants=payload.participants,
        duration_minutes=payload.duration_minutes,
        days=payload.days,
    )
    result["handler"] = intent
    return result


@app.get("/health")
def health():
    return {"status": "ok"}
