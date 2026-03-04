"""
General reply handler — fallback for emails that don't match a specialized handler.

Drafts a contextually appropriate reply using Claude, based on the email thread.
No calendar or external integrations needed.
"""
import anthropic
import config
from prompts import EMAIL_VOICE


def _client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


async def run(subject: str, email_body: str, thread_context: str, participants: list, **kwargs) -> dict:
    """
    Handler entry point. Returns a ReplyResponse-compatible dict:
      { "text": str, "action_url": None, "label": str, "mode": str }
    """
    participants_str = ", ".join(participants) if participants else "(none detected)"

    prompt = f"""{EMAIL_VOICE}

---

You are drafting an email reply for Jason. Follow his voice and style exactly as described above.

Email subject: {subject or "(no subject)"}

Email thread:
{thread_context or "(no prior thread)"}

User's current draft (may be empty):
{email_body or "(empty — draft a reply from scratch)"}

Other participants: {participants_str}

Write the reply body only — no explanation, no markdown. Include a greeting (e.g. "Hi [Name],") and sign-off ("Thanks\\nJason") as Jason would. If the user already has a draft, improve and complete it rather than rewriting from scratch."""

    msg = _client().messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip() if msg.content else ""
    return {
        "mode": "general",
        "text": text,
        "action_url": None,
        "label": "✅ Drafted",
    }
