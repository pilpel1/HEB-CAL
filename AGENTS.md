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

`requirements-dev.txt` pulls in `requirements.txt` plus `pytest` and `playwright`. Pytest does not need a browser. The two scripts under `scripts/` do: after the pip install, run `python -m playwright install chromium` once (the browser binary is not a pip package).

Manual checks:

- Start the app (above) and use the browser UI.
- **`scripts/verify_infinite_scroll.py`** — headless Playwright check of the infinite calendar (refresh lands on today, no jump-backs or empty cells while scrolling, jump-to-date, today button). Not part of `pytest`. Run against a temp DB (`DATABASE_PATH=/tmp/x.sqlite`) if you use `--seed-events`. `--smooth` uses full Chromium with Chrome's real scroll pipeline; `--fake-today YYYY-MM-DD` pins the browser date.
- **`scripts/smoke_ui.py`** — Playwright smoke of add/edit/delete (calendar + events list), search, JSON export, today button, jump-to-date, and zero console errors. Same browser setup. It writes and deletes events, so point the app at a temp DB. `--snapshot PATH` dumps UI state (globals, rendered calendar HTML, modal titles, context-menu markup) for a before/after diff.
- **`test_calendar.py`** — standalone script at the repo root (not under `tests/`, so pytest does not collect it) that exercises pyluach/calendar logic. Run with `python test_calendar.py` from the repo root when debugging Hebrew dates/holidays.

## File map (key modules)

| Path | Role |
|------|------|
| `app/__init__.py` | Flask app factory, routes for `/`, `/events_list`, API blueprint registration, `init_db()` on startup |
| `app/database.py` | SQLite connection, schema creation/migrations inline (not Alembic) |
| `app/api/__init__.py` | API blueprint wiring |
| `app/api/events.py` | Event CRUD endpoints. Optional `reminders` on create/update |
| `app/api/reminders.py` | Reminder people CRUD + `GET /api/reminders/due` (browser poll). People also carry shift color and allowed shifts |
| `app/api/shifts.py` | Household shifts toggle + idempotent week grid save |
| `app/reminders/` | Offset math, due query, Telegram worker. Recurring events fire per occurrence (`reminder_sends`); `occurrence_start` is the next start |
| `app/bot/` | Telegram menu bot (no LLM): lists, search, guided add/edit/delete, settings. State in `bot_sessions`. Reuses `clean_event_write` and `reminder_people.telegram_chat_id` |
| `scripts/reminder_worker.py` | Due reminders plus the bot menu (callbacks and `/start` `/add` `/today` `/week` `/find` `/settings`). Token: `TELEGRAM_BOT_TOKEN` only |
| `app/services/recurrence.py` | Expand yearly/monthly occurrences (Hebrew or Gregorian) plus exception overrides. Range results also carry `is_shift` so shifts merge into the same list |
| `app/services/shifts.py` | Shift labels (בוקר/ערב/לילה, no hours), per-weekday rules, week save. One household toggle in `household_settings` |
| `app/services/jewish_calendar.py` | Jewish calendar / holiday helpers |
| `app/services/hebrew_format.py` | Hebrew date text normalization/formatting |
| `app/services/calendar_service.py`, `event_service.py` | Not imported anywhere. Live paths are `app/api/` (calendar + Jewish events) and `app/database.py` (event CRUD) |
| `app/static/js/script.js` | UI entry only: the `DOMContentLoaded` bootstrap. Comment at the top explains the global scope |
| `app/static/js/theme.js` | Light/dark toggle. `localStorage` key `heb-cal-theme`. Loaded from `base.html` before `script.js`. The inline script in `<head>` sets `data-bs-theme` before CSS so the page does not flash. Button markup: `partials/theme_toggle.html` |
| `app/static/js/core/dates.js` | `YYYY-MM-DD` helpers, week/month math, date-range checks |
| `app/static/js/core/hebrew-format.js` | Hebrew day letters, month names, toolbar label, short dates in the modal title |
| `app/static/js/core/api.js` | `fetch` GET helpers: month calendar, Jewish events, `/api/events` |
| `app/static/js/calendar/infinite-state.js` | `INFINITE_CONFIG`, the `infiniteCalendar` state object, page detection |
| `app/static/js/calendar/month-data.js` | Month fetch + cache, "is this week fully loaded" |
| `app/static/js/calendar/event-render.js` | Paint a cell: holidays, multi-day rail, single-day events, color map |
| `app/static/js/calendar/week-rows.js` | Build week rows and day cells |
| `app/static/js/calendar/scroll-anchor.js` | Scroll geometry and `preserveScrollAnchor()` |
| `app/static/js/calendar/infinite-calendar.js` | Infinite-scroll core: maintain/trim, `renderAround`, `scrollToDate`, today button |
| `app/static/js/events/end-date-validation.js` | End date must not precede the start date (shared with the events-list page) |
| `app/static/js/events/event-actions.js` | Create / update / delete, success toast, refresh both views |
| `app/static/js/events/quick-event-modal.js` | Quick-event modal: fields, time parsed out of the title, color, submit. Reminder block is filled from `reminders-form.js` |
| `app/static/js/events/reminders-form.js` | Reminder checkbox, offset chips, custom amount, recipients |
| `app/static/js/events/reminder-notify.js` | Notification API poll of `/api/reminders/due` while the tab is open |
| `app/static/js/events/reminder-people.js` | Settings page (`/settings`) people CRUD |
| `app/static/js/events/shifts.js` | Settings toggle, person color/allowed shifts, and the calendar «הזן משמרות» popup |
| `app/static/js/events/context-menu.js` | Context menu: right-click, and long-press on touch |
| `app/templates/events_list.html` (inline `<script>`) | Events-list page: search, advanced search, import/export, pagination. Not a separate file |
| `app/templates/` | Jinja2: `base.html`, `index.html`, `events_list.html`, `settings.html`, partials (`quick_event_modal.html`, `shift_entry_modal.html`, `theme_toggle.html`) |
| `app/static/css/` | `style.css` imports `components/`: variables, calendar, events-table, forms, dark-theme |
| `tests/` | Pytest (`pytest.ini` sets `testpaths = tests`). `conftest.py` points the app at a temp SQLite file, never `data/calendar.db`. Modules: `test_events_api.py` (CRUD, search, import/export), `test_calendar_month_api.py`, `test_hebrew_format.py`, `test_jewish_calendar.py`, `test_static_scripts.py` (404s and duplicate top-level `const`/`let`), `test_theme.py` |
| `scripts/migrate_recurrence.py` | Idempotent additive migration for existing SQLite files (also applied by `init_db`) |
| `scripts/migrate_shifts.py` | Idempotent additive migration for shift columns, people color/rules, and the household toggle (also applied by `init_db`) |
| `scripts/verify_infinite_scroll.py`, `scripts/smoke_ui.py` | Playwright checks. Not collected by pytest. See Test |
| `test_calendar.py` | Manual pyluach script at the repo root. Not part of pytest |
| `init_db.py` | Optional DB init helper |

## Known issues / repo reality

1. **Schema lives in `app/database.py`.** Tables are created and evolved at startup (inline SQL). There is no Alembic/Flask-Migrate workflow in this repo.
2. **Telegram is one worker, not a model.** `scripts/reminder_worker.py` reads `TELEGRAM_BOT_TOKEN` only (`BOT_TOKEN` stays unused). It sends due reminders and runs `app/bot/` (inline buttons and slash commands, plain DB CRUD). Updates are a separate `getUpdates` long poll (25s) so a button tap is not waiting out the reminder interval; `answerCallbackQuery` («פותח…») is sent before the screen is built. Unlinked `/start` shows only the chat id in `<code>` (paste it in web settings, or use the link button). Linked `/start` is only the menu. The id stays on the bot settings screen. A shift line in the bot uses `shift_label` when that field is set. The shifts screen is this Sun–Sat week plus the next, one line per day (same person grouped, בוקר then ערב then לילה). Button `style` is only delete (danger), the save commit (success), and open-edit (primary). `bot_sessions` is created without raising `user_version`. Browser notifications poll `/api/reminders/due` while a tab is open; background Web Push needs HTTPS/PWA and is not built. `sent_at` is the Telegram stamp for a one-off event. A repeating event stamps each occurrence in `reminder_sends` (keyed by the original series date) and does not reuse `sent_at`. Events with no time fire at `REMINDER_DEFAULT_TIME` (default 09:00, `Asia/Jerusalem`). Recurrence lives on the event (`recurrence_freq`, `recurrence_calendar`, `recurrence_until`, `recurrence_count`); a single skipped or moved day is a row in `event_exceptions`. Rules: 30 Cheshvan/Kislev in a short year lands on the 29th of that month; plain Adar in a leap year is Adar II, and Adar I or Adar II in a non-leap year is Adar; Gregorian Feb 29 is Feb 28; a monthly 31st is the last day of the month. `GET /api/events` without a range returns the series master. `?from=&to=` expands occurrences.
3. **Frontend JS is classic scripts, one shared global scope** (see the lessons below). `base.html` loads `theme.js`, then `script.js`, then the `core/` / `calendar/` / `events/` files. Search, import, and export live in the inline script of `events_list.html`, not in those files. Shifts reuse `reminder_people` (color + `shift_allowed` JSON). A shift is a normal all-day event (`is_shift`, `shift_person_id`, `shift_label`) titled `שם — בוקר|ערב|לילה`. The week grid adds and removes only those rows. `household_settings.shifts_enabled` (default off) shows the «הזן משמרות» button. Recurring events stay expanded in the same `GET /api/events?from=&to=` list.
4. **`origin/feature/infinite-scroll-calendar` is a stale snapshot, not the current UI.** The infinite calendar is on `main`: it landed as the scroll-stability work, then `script.js` was split into `app/static/js/core/` and `app/static/js/calendar/`. That remote branch is still the older monolithic `script.js`. Do not merge it back and do not treat it as the source of truth.

## Infinite calendar — lessons (scroll stability)

The home page is a continuous stream of week rows scrolled inside `#calendar-stream` (not the window). Bugs that took several rounds to find:

- **Bootstrap 5 sets `:root { scroll-behavior: smooth }`.** Every `window.scrollTo`/`scrollBy`/`scrollTop =` on the document becomes an animation. This caused the visible scroll after the loading screen, landing on the wrong month, and the "spring-back" while scrolling. Scroll corrections must be instant: keep `scroll-behavior: auto` on the scroller, and use `behavior: 'smooth'` only explicitly (the today button).
- **Never mix native scroll anchoring with manual compensation.** The scroller has `overflow-anchor: none`. Every DOM change that can move content above the viewport (prepend, trim, event repaint) goes through `preserveScrollAnchor()`: measure a visible row, mutate synchronously, then correct `scrollTop` in the same task, before paint.
- **Async work must not mutate the DOM half-way.** Fetch month data first (`requestMonth`), then insert whole week rows synchronously. A week row is rendered only when all 7 days are loaded, so there are no placeholder/empty cells.
- **Prepend while the user is scrolling.** Waiting for scroll idle to add past weeks makes fast upward scrolling hit the top and then jump. With exact anchoring, prepending mid-scroll is safe. Only skip it during a programmatic smooth scroll, which a `scrollTop` change would cancel.
- **A stale anchor pulls the view back.** The ResizeObserver correction only applies when `scrollTop` hasn't changed since the anchor was captured.
- **Verify with what the user sees** (the date under a fixed screen point, the on-screen position of today's cell), not with `scrollTop`. `scrollTop` legitimately jumps when weeks are prepended.
- Playwright's `mouse.wheel` scrolls instantly. Use CDP `Input.synthesizeScrollGesture` (as the verify script does) to exercise animated scrolling. Synthetic touch gestures don't scroll in headless Chromium.

## Frontend scripts — lessons (splitting `script.js`)

`script.js` was split into the files in the map above. The move is verbatim; `script.js` keeps only the `DOMContentLoaded` handler.

- **Classic scripts, not `type="module"`.** The templates call functions from `onclick` (`goToToday`, `jumpToDate` → `jumpToMonth`, `editEvent`, `deleteEvent`), and those only see globals. A module would hide every function unless each one was also assigned to `window`. One global scope also means `let`/`const` (`infiniteCalendar`, `INFINITE_CONFIG`, …) are visible across files without `window.` — and **the same `const`/`let` name in two files is a `SyntaxError` that kills the whole second file**, with no server error. `tests/test_static_scripts.py` fails the build if any loaded script 404s, if a top-level name is declared twice, or if a `*.js` under `app/static/js/` is not referenced by `/` or `/events_list`.
- **Nothing runs at load time except declarations** (and the `history.scrollRestoration` assignment). Every call happens from `DOMContentLoaded` or later, and the scripts are parser-blocking, so they have all run before that event. File order does not affect correctness; keep new files in `base.html` anyway so a reader sees the dependency direction.
- **`events_list.html` has its own inline script, and it runs first** (it sits in the content block, above the script tags). It defines `deleteEvent`, `editEvent`, and `getTodayDateStr`, and the later files overwrite those three — that override is intentional and covered by `scripts/smoke_ui.py`. Its `loadAllEvents` is a different name on purpose: `core/api.js` already has `loadEvents`, and a second `function loadEvents` would silently replace it. `refreshEventsViews()` calls `loadAllEvents` only when it exists.
- **Any scroll closes the context menu** (`window` scroll listener, capture phase). The infinite calendar corrects `scrollTop` while repainting, so a real Playwright `click()` on a menu item — which scrolls the target into view — makes the menu detach. Dispatch the click, or the menu is gone.
- **Dead code removed with the split** (no template renders it, and nothing calls it): the legacy single-month view `updateCalendar` / `previousMonth` / `nextMonth` / `loadAndDisplayEvents` (it targeted `#calendar-body`, which no template has), the `updateEventsList` fallback (the only `#eventsTable` page defines `loadAllEvents`), the `currentDate` global, and `app/static/js/events.js`, which no template loaded. The per-day Jewish-events endpoint those functions used (`/api/jewish-events/<date>`) is still served; the infinite calendar uses `/api/jewish-events/month/...` instead.

## Mobile layout — lessons

The calendar is used mostly on a phone (375×812 and 390×844). What broke, and what to keep:

- **Long titles were breaking one letter per line.** A day column is ~45px wide. Bootstrap's `.table > :not(caption) > * > * { padding }` beats `.calendar-table td { padding: 0 }`, so the cell kept ~8px of padding on each side and `.day-content` added more. The text box was ~12px. `overflow-wrap: break-word` then wrapped every letter. The fix is `padding: 0` on `.table.calendar-table > :not(caption) > * > *`, plus `nowrap` / `text-overflow: ellipsis` / `min-width: 0` on `.event-item` (a flex item will not ellipsis without `min-width: 0`). The full string stays in the element (`title`) and in the edit modal. A tap opens that modal; the click is delayed ~280ms so a double-click (and `scripts/smoke_ui.py`) still edits once.
- **Right-click is not a phone gesture.** Delete, and "add on this day", lived only in the context menu. A long-press (~500ms, cancelled if the finger moves) opens the same menu. Open it on `pointerup`, not from `contextmenu` while the finger is down: on Android `contextmenu` fires first, and showing the menu then makes the release hit the first item (or the following click closes it). The release's click is swallowed in the capture phase so it does not also open the editor. Any scroll still closes the menu.
- **The quick-event modal is taller than the phone.** `modal-dialog-centered` shoves the title above the viewport. `modal-dialog-scrollable` is not enough on its own: the `<form>` wraps both `.modal-body` and `.modal-footer`, so that form is the flex item that has to shrink (`min-height: 0`, column flex). Otherwise the footer sits past the bottom edge. Swatches and the close button are 24px unless you set a 40px box.
- **Weekday names do not fit seven equal columns.** `repeat(7, 1fr)` sizes each track by its word, so the header drifts off the table. Use `minmax(0, 1fr)`, and one-letter labels (א׳–ש׳) under 480px.
- **The events list was scrolling sideways inside `.table-responsive`, and the edit/delete buttons sat off-screen.** Under 576px the table becomes a two-column card (text, then the action buttons). Hiding columns instead leaves the actions at 5% width, which is smaller than a 40px target.

## Rules for agents and contributors

- **Never commit** `.env`, tokens, or local secrets. Use `.env.example` for documentation only.
- **Small PRs:** one logical change per PR when possible.
- **Hebrew UI copy** in templates and JS is intentional; do not “fix” to English unless explicitly requested.
- Prefer matching existing patterns (Flask blueprints, sqlite3 via `get_db()`, RTL Bootstrap classes).
- Do not vendor third-party doc trees in git (e.g. local pyluach HTML docs); use upstream documentation or `.gitignore` for local copies.

## Dependencies (high level)

Runtime (`requirements.txt`): `flask`, `pyluach`, `python-hebrew-numbers`, `python-dotenv`.

Hebrew dates in the API go through pyluach (`GregorianDate.to_heb()`), same month numbering as the old `convertdate.hebrew.from_gregorian` (Nisan = 1, Adar II = 13). `convertdate` is not a dependency: its latest release still calls the deprecated `month_days` wrapper from inside `to_jd`.

Dev (`requirements-dev.txt`): the runtime file, plus `pytest` and `playwright`. Chromium for the scripts: `python -m playwright install chromium`.
