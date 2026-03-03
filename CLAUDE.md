# SimonOS

A monorepo where each top-level folder represents a self-contained business process automation.

## Structure

```
SimonOS/
  <process-name>/   # one folder per business process
    ...
```

## Projects

- **customer-convos** — Tracks customer calls. Polls Google Calendar for external meetings, enriches with Gong recordings/transcripts and Google Drive sales decks, matches customers via Salesforce.

## Conventions

- Each project is independently runnable with its own `requirements.txt`, `config.py`, and `.env.example`
- Secrets are always in `.env` (never committed); `.env.example` documents required vars
- Database per project (Postgres); models defined with SQLAlchemy in `db/models.py`
- Integrations live in `integrations/`, scheduled work in `jobs/`, entrypoint is `scheduler.py`
