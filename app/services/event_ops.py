"""קריאה וכתיבה של אירועים — המסלול הקנוני של ה-REST ושל שרת ה-MCP.

הפונקציות זורקות ``EventOpError`` עם ההודעה והסטטוס שה-API מחזיר.
ה-route ב-``app/api/events.py`` רק עוטף את זה ב-``jsonify``.
"""
from __future__ import annotations

from datetime import date, datetime

from app.database import (
    create_event,
    delete_event,
    get_all_events,
    get_event,
    update_event,
    upsert_exception,
)
from app.gcal.repository import READONLY_MESSAGE, is_gcal_event
from app.reminders.repository import clear_reminder_delivery, people_ids, replace_event_reminders
from app.reminders.schedule import OffsetError, parse_reminders_payload
from app.services.event_payload import EventPayloadError, clean_event_write
from app.services.recurrence import (
    RecurrenceError,
    clean_recurrence,
    expand_event,
    is_recurring,
    is_series_date,
    recurrence_fields,
)
from app.services.shifts import ShiftError, resolve_manual_shift, shifts_enabled

REQUIRED_EVENT_FIELDS = ("title", "gregorian_date", "hebrew_date")


class EventOpError(Exception):
    """שגיאה שמוצגת למשתמש כמו שהיא, עם סטטוס ה-HTTP של ה-API."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def validate_event_payload(data: dict) -> None:
    missing_fields = [field for field in REQUIRED_EVENT_FIELDS if not data.get(field)]
    if missing_fields:
        raise EventOpError(f"Missing required fields: {missing_fields}")
    try:
        cleaned = clean_event_write(data)
    except EventPayloadError as exc:
        raise EventOpError(str(exc)) from exc
    data.update(cleaned)


def recurrence_from_payload(data: dict, gregorian_date: str):
    """'keep' אם המפתח לא נשלח, None אם אין חזרה, dict אם יש."""
    if "recurrence_freq" not in data and not isinstance(data.get("recurrence"), dict):
        return "keep"
    anchor = datetime.strptime(gregorian_date, "%Y-%m-%d").date()
    source = data["recurrence"] if isinstance(data.get("recurrence"), dict) and "recurrence_freq" not in data else data
    if "recurrence_freq" in data:
        freq = data.get("recurrence_freq")
        calendar_name = data.get("recurrence_calendar")
        until = data.get("recurrence_until")
        count = data.get("recurrence_count")
    else:
        freq = source.get("freq")
        calendar_name = source.get("calendar")
        until = source.get("until")
        count = source.get("count")
    try:
        return clean_recurrence(freq, calendar_name, until, count, anchor)
    except RecurrenceError as exc:
        raise EventOpError(str(exc)) from exc


def identity_changed(old: dict, gregorian_date: str, rule) -> bool:
    if (old.get("gregorian_date") or "") != gregorian_date:
        return True
    old_rule = recurrence_fields(old)
    new_freq = None if rule is None or rule == "keep" else rule.get("recurrence_freq")
    new_cal = None if rule is None or rule == "keep" else rule.get("recurrence_calendar")
    if rule == "keep":
        return False
    return old_rule["recurrence_freq"] != new_freq or old_rule["recurrence_calendar"] != new_cal


def manual_shift(data: dict):
    """('keep' | tuple, data).

    משמרת ידנית לא נבדקת מול הימים המותרים. בלי המפתחות — לא נוגעים בדגל.
    """
    try:
        resolved = resolve_manual_shift(data)
    except ShiftError as exc:
        raise EventOpError(str(exc)) from exc
    if resolved is None:
        return "keep", data
    if not resolved["is_shift"]:
        return (0, None, None), data
    adjusted = dict(data)
    # הכותרת נשארת מהטופס. סוג המשמרת נשמר לחוד ב-shift_label.
    adjusted["color"] = resolved["color"]
    adjusted["time"] = None
    adjusted["end_date"] = None
    adjusted["recurrence_freq"] = None
    return (1, resolved["shift_person_id"], resolved["shift_label"]), adjusted


def parsed_reminders(data: dict):
    """None = המפתח לא נשלח (בעדכון משאירים את הקיים)."""
    if "reminders" not in data:
        return None
    try:
        return parse_reminders_payload(data.get("reminders"), people_ids(role="reminders"))
    except OffsetError as exc:
        raise EventOpError(str(exc)) from exc


def list_range(start: date, end: date) -> list[dict]:
    """מופעים שנוגעים בטווח, כולל חריגות. כמו ``GET /api/events?from=&to=``."""
    rows = []
    for event in get_all_events():
        try:
            rows.extend(expand_event(event, event.get("exceptions") or [], start, end))
        except RecurrenceError:
            continue
    return rows


def occurrence_payload(event: dict, occurrence_date: str):
    """מופע אחד לעריכה, בתוספת ``series`` (השורת אב) כדי שאפשר לעבור ל"כל הסדרה"."""
    if not is_recurring(event):
        return event
    try:
        original = date.fromisoformat(occurrence_date)
    except ValueError:
        return None
    if not is_series_date(event, original):
        return None
    # המופע יכול היה לזוז לפני או אחרי תאריך המקור
    window_start = original
    window_end = original
    for ex in event.get("exceptions") or []:
        if (ex.get("original_date") or "")[:10] != occurrence_date:
            continue
        for key in ("gregorian_date", "end_date"):
            raw = ex.get(key)
            if not raw:
                continue
            try:
                moved = date.fromisoformat(raw[:10])
            except ValueError:
                continue
            window_start = min(window_start, moved)
            window_end = max(window_end, moved)
    matches = [
        row for row in expand_event(event, event.get("exceptions") or [], window_start, window_end)
        if row.get("occurrence_date") == occurrence_date
    ]
    if not matches:
        # נמחק
        return None
    payload = matches[0]
    payload["series"] = {
        key: event.get(key)
        for key in (
            "id", "title", "gregorian_date", "hebrew_date", "time", "description",
            "end_date", "color", "recurrence_freq", "recurrence_calendar",
            "recurrence_until", "recurrence_count", "reminders",
        )
    }
    return payload


def create(data: dict) -> int:
    validate_event_payload(data)
    reminders = parsed_reminders(data)
    shift, data = manual_shift(data)
    rule = recurrence_from_payload(data, data["gregorian_date"])
    if rule == "keep" or (shift != "keep" and shift[0]):
        rule = None
    if shift != "keep" and shift[0] and not shifts_enabled():
        raise EventOpError("המשמרות כבויות")

    event_id = create_event(
        title=data['title'],
        gregorian_date=data['gregorian_date'],
        hebrew_date=data['hebrew_date'],
        time=data.get('time') or None,
        description=data.get('description', ''),
        end_date=data.get('end_date'),
        color=data.get('color'),
        recurrence=rule,
        shift=None if shift == "keep" else shift,
    )
    if not event_id:
        raise EventOpError("Failed to create event")
    replace_event_reminders(event_id, reminders or [])
    return event_id


def update(event_id: int, data: dict) -> dict:
    """``{"scope": "all" | "occurrence", "exceptions_cleared": bool}``.

    ``exceptions_cleared``: שינוי תאריך או חזרה על כל הסדרה מחק חריגות קיימות.
    """
    validate_event_payload(data)
    reminders = parsed_reminders(data)

    existing = get_event(event_id)
    if existing is None:
        raise EventOpError("Event not found", 404)
    if is_gcal_event(existing):
        raise EventOpError(READONLY_MESSAGE, 403)

    scope = (data.get("scope") or "all").strip()
    if scope == "occurrence" and "reminders" in data:
        raise EventOpError("תזכורות נשמרות על כל הסדרה")
    if scope == "occurrence" and data.get("is_shift"):
        raise EventOpError("משמרת נשמרת על האירוע כולו")
    if scope == "occurrence":
        if not is_recurring(existing):
            raise EventOpError("לאירוע אין חזרה")
        occurrence_date = (data.get("occurrence_date") or "").strip()
        try:
            original = date.fromisoformat(occurrence_date)
        except ValueError as exc:
            raise EventOpError("חסר תאריך מופע") from exc
        if not is_series_date(existing, original):
            raise EventOpError("התאריך לא מופיע בסדרה")
        end_date = data.get("end_date") or None
        if end_date:
            try:
                if date.fromisoformat(end_date) < date.fromisoformat(data["gregorian_date"]):
                    raise EventOpError("תאריך הסיום לא יכול להיות לפני ההתחלה")
            except ValueError as exc:
                raise EventOpError("Invalid date format. Expected YYYY-MM-DD") from exc
        upsert_exception(
            event_id,
            occurrence_date,
            "edited",
            {
                "title": data["title"],
                "gregorian_date": data["gregorian_date"],
                "hebrew_date": data["hebrew_date"],
                "time": data.get("time") or None,
                "description": data.get("description", ""),
                "end_date": end_date,
                "color": data.get("color"),
            },
        )
        return {"scope": "occurrence", "exceptions_cleared": False}

    if scope != "all":
        raise EventOpError("scope חייב להיות all או occurrence")

    shift, data = manual_shift(data)
    marking_shift = shift != "keep" and shift[0]

    rule = recurrence_from_payload(data, data["gregorian_date"])
    if marking_shift:
        rule = None
    if marking_shift and not shifts_enabled():
        raise EventOpError("המשמרות כבויות")

    if (
        (existing.get("gregorian_date") or "") != data["gregorian_date"]
        or (existing.get("time") or None) != (data.get("time") or None)
    ):
        clear_reminder_delivery(event_id)

    clear_exceptions = identity_changed(existing, data["gregorian_date"], rule) or marking_shift
    success = update_event(
        event_id,
        data['title'],
        data['gregorian_date'],
        data['hebrew_date'],
        data.get('time') or None,
        data.get('description', ''),
        data.get('end_date'),
        data.get('color'),
        recurrence=rule,
        clear_exceptions=clear_exceptions,
        shift=shift,
    )
    if not success:
        raise EventOpError("Failed to update event")
    if reminders is not None:
        replace_event_reminders(event_id, reminders)
    return {"scope": "all", "exceptions_cleared": bool(clear_exceptions and existing.get("exceptions"))}


def delete(event_id: int, scope: str, occurrence_date: str) -> str:
    """מחזיר את ה-scope שבוצע: ``all`` או ``occurrence``."""
    scope = (scope or "all").strip()
    existing = get_event(event_id)
    if is_gcal_event(existing):
        raise EventOpError(READONLY_MESSAGE, 403)
    if scope == "occurrence":
        if existing is None:
            raise EventOpError("Event not found", 404)
        if not is_recurring(existing):
            raise EventOpError("לאירוע אין חזרה")
        occurrence_date = (occurrence_date or "").strip()
        try:
            original = date.fromisoformat(occurrence_date)
        except ValueError as exc:
            raise EventOpError("חסר תאריך מופע") from exc
        if not is_series_date(existing, original):
            raise EventOpError("התאריך לא מופיע בסדרה")
        upsert_exception(event_id, occurrence_date, "deleted", {"gregorian_date": occurrence_date})
        return "occurrence"
    if scope != "all":
        raise EventOpError("scope חייב להיות all או occurrence")
    if delete_event(event_id):
        return "all"
    raise EventOpError("Failed to delete event", 404)
