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

```bash
pip install -r requirements-dev.txt
pytest -q
```

Manual checks:

- Start the app (above) and use the browser UI.
- **`scripts/verify_infinite_scroll.py`** — headless Playwright check of the infinite calendar (refresh lands on today, no jump-backs or empty cells while scrolling, jump-to-date, today button). Needs `pip install playwright && python -m playwright install chromium` and a running app; not part of `pytest`. Run against a temp DB (`DATABASE_PATH=/tmp/x.sqlite`) if you use `--seed-events`. `--smooth` uses full Chromium with Chrome's real scroll pipeline; `--fake-today YYYY-MM-DD` pins the browser date.
- **`test_calendar.py`** — standalone script that exercises pyluach/calendar logic (run with `python test_calendar.py` from the repo root when debugging Hebrew dates/holidays).

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
| `app/static/js/script.js` | Main calendar UI logic (large file); the infinite calendar section starts at `INFINITE_CONFIG` |
| `app/static/js/events.js` | Events list UI |
| `app/templates/` | Jinja2: `base.html`, `index.html`, `events_list.html`, partials |
| `app/static/css/` | Component CSS (calendar, forms, variables) |
| `init_db.py` | Optional DB init helper |

## Known issues / repo reality

1. **Schema lives in `app/database.py`.** Tables are created and evolved at startup (inline SQL). There is no Alembic/Flask-Migrate workflow in this repo.
2. **Telegram bot is planned, not started.** Optional `BOT_TOKEN` in `.env` is reserved for a future integration; there is no `bot/` package in the tree yet.
3. **`app/static/js/script.js`** is monolithic and hard to navigate; refactors should stay small and behavior-preserving.
4. **Branch `feature/infinite-scroll-calendar`** holds unmerged infinite-scroll calendar work — do not confuse with `main` when merging or reviewing.

## Infinite calendar — lessons (scroll stability)

The home page is a continuous stream of week rows scrolled inside `#calendar-stream` (not the window). Bugs that took several rounds to find:

- **Bootstrap 5 sets `:root { scroll-behavior: smooth }`.** Every `window.scrollTo`/`scrollBy`/`scrollTop =` on the document becomes an animation. This caused the visible scroll after the loading screen, landing on the wrong month, and the "spring-back" while scrolling. Scroll corrections must be instant: keep `scroll-behavior: auto` on the scroller, and use `behavior: 'smooth'` only explicitly (the today button).
- **Never mix native scroll anchoring with manual compensation.** The scroller has `overflow-anchor: none`. Every DOM change that can move content above the viewport (prepend, trim, event repaint) goes through `preserveScrollAnchor()`: measure a visible row, mutate synchronously, then correct `scrollTop` in the same task, before paint.
- **Async work must not mutate the DOM half-way.** Fetch month data first (`requestMonth`), then insert whole week rows synchronously. A week row is rendered only when all 7 days are loaded, so there are no placeholder/empty cells.
- **Prepend while the user is scrolling.** Waiting for scroll idle to add past weeks makes fast upward scrolling hit the top and then jump. With exact anchoring, prepending mid-scroll is safe. Only skip it during a programmatic smooth scroll, which a `scrollTop` change would cancel.
- **A stale anchor pulls the view back.** The ResizeObserver correction only applies when `scrollTop` hasn't changed since the anchor was captured.
- **Verify with what the user sees** (the date under a fixed screen point, the on-screen position of today's cell), not with `scrollTop`. `scrollTop` legitimately jumps when weeks are prepended.
- Playwright's `mouse.wheel` scrolls instantly. Use CDP `Input.synthesizeScrollGesture` (as the verify script does) to exercise animated scrolling. Synthetic touch gestures don't scroll in headless Chromium.

## Rules for agents and contributors

- **Never commit** `.env`, tokens, or local secrets. Use `.env.example` for documentation only.
- **Small PRs:** one logical change per PR when possible.
- **Hebrew UI copy** in templates and JS is intentional; do not “fix” to English unless explicitly requested.
- Prefer matching existing patterns (Flask blueprints, sqlite3 via `get_db()`, RTL Bootstrap classes).
- Do not vendor third-party doc trees in git (e.g. local pyluach HTML docs); use upstream documentation or `.gitignore` for local copies.

## Dependencies (high level)

See `requirements.txt`: `flask`, `pyluach`, `convertdate`, `python-hebrew-numbers`, `python-dotenv`.
