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

- **cal-manager** — Manages Google Calendar: conflict detection, travel holds, location updates, wife notifications, color coding. The `api/server.py` scheduling logic has been superseded by `email-responder`. The `extension/` folder is kept for reference but the active extension is in `email-responder/extension/`. Background jobs still run via `scheduler.py`.
- **customer-convos** — Tracks customer calls. Polls Google Calendar for external meetings, enriches with Gong recordings/transcripts and Google Drive sales decks, matches customers via Salesforce.
- **email-responder** — Generalized AI reply assistant. Chrome extension injects an "✨ Reply" button into Gmail compose windows. API server (port 5556) classifies email intent and dispatches to pluggable handlers: `scheduling` (suggest times / create calendar events, reads cal-manager DB) and `general` (draft any reply). Run with: `uvicorn api.server:app --port 5556 --reload`.
- **cap-table** — Cap table management and investor request handling. Syncs investors, rounds, and holdings from Carta. Polls Gmail for investor emails, classifies request type, and uses Claude to draft responses. Query API on port 5557. Run scheduler with `python scheduler.py`; API with `uvicorn api.server:app --port 5557 --reload`.

## Conventions

- Each project is independently runnable with its own `requirements.txt`, `config.py`, and `.env.example`
- **Shared credentials** (Google service account, OAuth, Maps API key) live in root `.env` and `credentials/`
- **Project-specific config** (DB URL, calendar IDs, Salesforce, etc.) lives in each project's `.env`
- `config.py` in each project loads root `.env` first, then project `.env` — project values override shared ones
- Database per project (Postgres); models defined with SQLAlchemy in `db/models.py`
- Integrations live in `integrations/`, scheduled work in `jobs/`, entrypoint is `scheduler.py`
