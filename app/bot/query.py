"""רשימות לבוט. אותה הרחבת מופעים כמו ``GET /api/events?from=&to=``."""
from __future__ import annotations

from datetime import date, timedelta

from app.database import get_all_events
from app.services.recurrence import RecurrenceError, expand_event, is_recurring
from app.services.shifts import weekday_index

PAGE_SIZE = 5
PEOPLE_PAGE = 6
SOON_DAYS = 30
PERSON_DAYS = 60
FIND_BACK = 30
FIND_AHEAD = 365
FIND_PER_SERIES = 3


def week_bounds(today: date) -> tuple[date, date]:
    """ראשון עד שבת, כמו רשת המשמרות."""
    start = today - timedelta(days=weekday_index(today))
    return start, start + timedelta(days=6)


def shift_anchor(value, today: date) -> date:
    """ראשון של השבוע הראשון בלוח המשמרות. ערך ריק או שבור → השבוע של היום."""
    day = today
    if value:
        try:
            day = date.fromisoformat(str(value)[:10])
        except ValueError:
            day = today
    start, _end = week_bounds(day)
    return start


def _sort_key(row: dict):
    return (
        row.get("gregorian_date") or "",
        row.get("time") or "",
        row.get("id") or 0,
        row.get("occurrence_date") or "",
    )


def _expand(event: dict, start: date, end: date) -> list[dict]:
    try:
        return expand_event(event, event.get("exceptions") or [], start, end)
    except RecurrenceError:
        return []


def _blob(row: dict) -> str:
    return (
        f"{row.get('title') or ''} {row.get('shift_label') or ''} {row.get('description') or ''}"
    ).casefold()


def _master_row(event: dict) -> dict:
    rule_freq = event.get("recurrence_freq")
    return {
        "id": event.get("id"),
        "title": event.get("title"),
        "gregorian_date": (event.get("gregorian_date") or "")[:10],
        "hebrew_date": event.get("hebrew_date") or "",
        "time": event.get("time"),
        "description": event.get("description") or "",
        "end_date": event.get("end_date"),
        "occurrence_date": (event.get("gregorian_date") or "")[:10],
        "recurring": bool(rule_freq),
        "recurrence_freq": rule_freq,
        "is_shift": 1 if event.get("is_shift") else 0,
        "shift_person_id": event.get("shift_person_id"),
        "shift_label": event.get("shift_label"),
        "reminders": event.get("reminders") or [],
    }


def matches_person(row: dict, person_id: int) -> bool:
    try:
        if int(row.get("shift_person_id") or 0) == int(person_id):
            return True
    except (TypeError, ValueError):
        pass
    for reminder in row.get("reminders") or []:
        for item in reminder.get("recipient_ids") or []:
            try:
                if int(item) == int(person_id):
                    return True
            except (TypeError, ValueError):
                continue
    return False


def apply_filter(rows: list[dict], mode: str) -> list[dict]:
    if mode == "ev":
        return [row for row in rows if not row.get("is_shift")]
    if mode == "sh":
        return [row for row in rows if row.get("is_shift")]
    return list(rows)


def clamp_page(count: int, page: int, size: int = PAGE_SIZE) -> tuple[int, int]:
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 0
    if count <= 0:
        return 0, 1
    pages = (count + size - 1) // size
    return max(0, min(page, pages - 1)), pages


def range_for(kind: str, today: date) -> tuple[date, date] | None:
    if kind == "today":
        return today, today
    if kind == "week":
        return week_bounds(today)
    if kind == "soon":
        return today, today + timedelta(days=SOON_DAYS)
    if kind == "shifts":
        # שבוע אחד (ראשון–שבת). הדפדוף זז דרך sw:.
        return week_bounds(today)
    if kind == "person":
        return today, today + timedelta(days=PERSON_DAYS)
    return None


def events_between(start: date, end: date) -> list[dict]:
    rows: list[dict] = []
    for event in get_all_events():
        rows.extend(_expand(event, start, end))
    rows.sort(key=_sort_key)
    return rows


def search_events(query: str, today: date) -> list[dict]:
    needle = query.casefold()
    window_from = today - timedelta(days=FIND_BACK)
    window_to = today + timedelta(days=FIND_AHEAD)
    found: list[dict] = []
    seen: set[tuple] = set()
    for event in get_all_events():
        occs = _expand(event, window_from, window_to)
        hits = [row for row in occs if needle in _blob(row)]
        if not hits and needle in _blob(event):
            hits = occs[:1] if occs else [_master_row(event)]
        if is_recurring(event) and len(hits) > FIND_PER_SERIES:
            hits = hits[:FIND_PER_SERIES]
        for row in hits:
            key = (row.get("id"), row.get("gregorian_date"), row.get("occurrence_date"))
            if key in seen:
                continue
            seen.add(key)
            found.append(row)
    found.sort(key=_sort_key)
    return found


def collect_list(
    kind: str,
    today: date,
    *,
    mode: str = "all",
    person_id: int | None = None,
    query: str | None = None,
) -> list[dict]:
    if kind == "find":
        rows = search_events(query or "", today)
    else:
        bounds = range_for(kind, today)
        if bounds is None:
            return []
        rows = events_between(*bounds)
    if kind == "shifts":
        rows = apply_filter(rows, "sh")
    else:
        rows = apply_filter(rows, mode)
    if kind == "person" and person_id is not None:
        rows = [row for row in rows if matches_person(row, person_id)]
    return rows
