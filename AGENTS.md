# Agent guide — HEB-CAL

## What this project is

**HEB-CAL** is a small Flask web app: a shared Hebrew–Gregorian calendar for a couple. Users browse months, see Jewish holidays and parshiyot (via **pyluach**), and manage personal events (CRUD). The UI is **Hebrew**, **RTL**, built with **vanilla JavaScript** and **Bootstrap RTL**; there is no React/Vue SPA.

- **Backend:** Flask, SQLite (`data/calendar.db` by default), REST API under `/api`.
- **Config:** `.env` (see `.env.example`) — `DATABASE_PATH`, `SECRET_KEY`, `FLASK_DEBUG`, optional `BOT_TOKEN`.
- **Scope:** Personal/couple use; not a multi-tenant SaaS.

## Setup

Requires **Python 3.12+**. Recommended dev path: Linux or WSL2.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and adjust values. **Never commit `.env` or secrets.**

## Run

```bash
source .venv/bin/activate
python -m flask --app app run
```

Alternative entry: `python app/main.py` (same app).

Open the URL Flask prints (default `http://127.0.0.1:5000`).

## Test

There is **no pytest suite** yet. Manual checks:

- Start the app (above) and use the browser UI.
- **`test_calendar.py`** — standalone script that exercises pyluach/calendar logic (run with `python test_calendar.py` from the repo root when debugging Hebrew dates/holidays).

Do not assume CI runs automated tests until pytest is added.

## File map (key modules)

| Path | Role |
|------|------|
| `app/__init__.py` | Flask app factory, routes for `/`, `/events_list`, API blueprint registration, `init_db()` on startup |
| `app/database.py` | SQLite connection, schema creation/migrations inline (not Alembic) |
| `app/api/__init__.py` | API blueprint wiring |
| `app/api/events.py` | Event CRUD endpoints |
| `app/services/jewish_calendar.py` | Jewish calendar / holiday helpers |
| `app/services/hebrew_format.py` | Hebrew date text normalization/formatting |
| `app/services/calendar_service.py`, `event_service.py` | Higher-level calendar/event logic |
| `app/static/js/script.js` | Main calendar UI logic (large file) |
| `app/static/js/events.js` | Events list UI |
| `app/templates/` | Jinja2: `base.html`, `index.html`, `events_list.html`, partials |
| `app/static/css/` | Component CSS (calendar, forms, variables) |
| `init_db.py` | Optional DB init helper |

## Known issues / repo reality

1. **Schema lives in `app/database.py`.** Tables are created and evolved at startup (inline SQL). There is no Alembic/Flask-Migrate workflow in this repo.
2. **Telegram bot is planned, not started.** Optional `BOT_TOKEN` in `.env` is reserved for a future integration; there is no `bot/` package in the tree yet.
3. **`app/static/js/script.js`** is monolithic and hard to navigate; refactors should stay small and behavior-preserving.
4. **Branch `feature/infinite-scroll-calendar`** holds unmerged infinite-scroll calendar work — do not confuse with `main` when merging or reviewing.

## Rules for agents and contributors

- **Never commit** `.env`, tokens, or local secrets. Use `.env.example` for documentation only.
- **Small PRs:** one logical change per PR when possible.
- **Hebrew UI copy** in templates and JS is intentional; do not “fix” to English unless explicitly requested.
- Prefer matching existing patterns (Flask blueprints, sqlite3 via `get_db()`, RTL Bootstrap classes).
- Do not vendor third-party doc trees in git (e.g. local pyluach HTML docs); use upstream documentation or `.gitignore` for local copies.

## Dependencies (high level)

See `requirements.txt`: `flask`, `pyluach`, `convertdate`, `python-hebrew-numbers`, `python-dotenv`.
