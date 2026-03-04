from pathlib import Path

_DIR = Path(__file__).parent

def load(name: str) -> str:
    """Load a prompt file by name (without .md extension)."""
    return (_DIR / f"{name}.md").read_text()

EMAIL_VOICE = load("email_voice_context")
