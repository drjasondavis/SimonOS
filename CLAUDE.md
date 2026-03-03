# SimonOS

A monorepo where each top-level folder represents a self-contained business process automation.

## Structure

```
SimonOS/
  .env                  # shared credentials (Google, Maps, OAuth) — never committed
  .env.example          # template for shared credentials
  credentials/          # credential files (service account JSON, etc.) — never committed
  <process-name>/       # one folder per business process
    .env                # project-specific config — never committed
    .env.example        # template for project config
    config.py           # loads root .env then project .env (project values win)
    ...
```

## Projects

- **cal-manager** — Manages Google Calendar: conflict detection, travel holds, location updates, wife notifications, color coding. Includes a Gmail Chrome extension (`extension/`) with a "📅 Scheduler" button that uses Claude Opus to suggest meeting times or create calendar events from email threads. API server runs on port 5555 (`uvicorn api.server:app --port 5555 --reload`).
- **customer-convos** — Tracks customer calls. Polls Google Calendar for external meetings, enriches with Gong recordings/transcripts and Google Drive sales decks, matches customers via Salesforce.

## Conventions

- Each project is independently runnable with its own `requirements.txt`, `config.py`, and `.env.example`
- **Shared credentials** (Google service account, OAuth, Maps API key) live in root `.env` and `credentials/`
- **Project-specific config** (DB URL, calendar IDs, Salesforce, etc.) lives in each project's `.env`
- `config.py` in each project loads root `.env` first, then project `.env` — project values override shared ones
- Database per project (Postgres); models defined with SQLAlchemy in `db/models.py`
- Integrations live in `integrations/`, scheduled work in `jobs/`, entrypoint is `scheduler.py`
