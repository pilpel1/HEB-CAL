"""כתיבה ליומן. האימות הוא ``clean_event_write`` / ``resolve_manual_shift``."""
from __future__ import annotations

from datetime import date

from app.database import create_event, delete_event, get_event, update_event
from app.services.event_payload import clean_event_write
from app.services.recurrence import hebrew_display, is_recurring
from app.services.shifts import ShiftError, resolve_manual_shift
from app.bot.parse import InputError


def fingerprint(event: dict) -> str:
    end = event.get("end_date") or ""
    parts = [
        event.get("title") or "",
        (event.get("gregorian_date") or "")[:10],
        event.get("time") or "",
        event.get("description") or "",
        end[:10] if end else "",
    ]
    if event.get("is_shift"):
        parts.append(str(event.get("shift_person_id") or ""))
        parts.append(event.get("shift_label") or "")
    return "\n".join(parts)


def snapshot(event: dict) -> dict:
    end = event.get("end_date") or ""
    return {
        "event_id": event["id"],
        "title": event.get("title") or "",
        "gregorian_date": (event.get("gregorian_date") or "")[:10],
        "time": event.get("time"),
        "description": event.get("description") or "",
        "end_date": end[:10] if end else None,
        "is_shift": 1 if event.get("is_shift") else 0,
        "shift_person_id": event.get("shift_person_id"),
        "shift_label": event.get("shift_label") or "",
        "recurring": is_recurring(event),
        "base": fingerprint(event),
        "force": False,
    }


def _day(value: str) -> date:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError as exc:
        raise InputError("התאריך לא תקין. למשל 22.10.2026.") from exc


def _blank_end(start: str, end: str | None) -> str | None:
    if not end or end[:10] == start:
        return None
    return end[:10]


def _insert(cleaned: dict, shift=None) -> dict:
    event_id = create_event(
        cleaned["title"],
        cleaned["gregorian_date"],
        cleaned["hebrew_date"],
        time=cleaned["time"],
        description=cleaned["description"],
        end_date=cleaned["end_date"],
        color=cleaned["color"],
        shift=shift,
    )
    if not event_id:
        raise InputError("לא הצלחתי לשמור. נסו שוב.")
    saved = get_event(event_id)
    if saved is None:
        raise InputError("לא הצלחתי לשמור. נסו שוב.")
    return saved


def create_user_event(draft: dict) -> dict:
    day = _day(draft.get("gregorian_date") or "")
    cleaned = clean_event_write(
        {
            "title": draft.get("title") or "",
            "gregorian_date": day.isoformat(),
            "hebrew_date": hebrew_display(day),
            "time": draft.get("time"),
            "description": draft.get("description") or "",
            "end_date": _blank_end(day.isoformat(), draft.get("end_date")),
            "color": None,
        }
    )
    reminders = draft.get("reminders") or []
    parsed = []
    if reminders:
        from app.reminders.repository import people_ids, replace_event_reminders
        from app.reminders.schedule import OffsetError, parse_reminders_payload

        try:
            parsed = parse_reminders_payload(reminders, people_ids(role="reminders"))
        except OffsetError as exc:
            raise InputError(str(exc)) from exc
    saved = _insert(cleaned)
    if parsed:
        from app.reminders.repository import replace_event_reminders

        replace_event_reminders(saved["id"], parsed)
        saved = get_event(saved["id"]) or saved
    return saved


def create_shift(person_id: int, label: str, gregorian_date: str) -> dict:
    day = _day(gregorian_date)
    try:
        resolved = resolve_manual_shift(
            {
                "is_shift": True,
                "shift_person_id": person_id,
                "shift_label": label,
            }
        )
    except ShiftError:
        raise
    if not resolved or not resolved.get("is_shift"):
        raise InputError("לא הצלחתי לשמור את המשמרת.")
    cleaned = clean_event_write(
        {
            "title": resolved["shift_label"],
            "gregorian_date": day.isoformat(),
            "hebrew_date": hebrew_display(day),
            "time": None,
            "description": "",
            "end_date": None,
            "color": resolved.get("color"),
        }
    )
    return _insert(
        cleaned,
        shift=(1, resolved["shift_person_id"], resolved["shift_label"]),
    )


def _same_id(left, right) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return False


def _shift_write(draft: dict, current: dict, color):
    """עמודות משמרת לשמירה. בלי שינוי אדם/סוג לא בודקים מחדש את הרשימה."""
    person_id = draft.get("shift_person_id")
    if person_id in (None, ""):
        person_id = current.get("shift_person_id")
    label = (draft.get("shift_label") or "").strip() or (current.get("shift_label") or "")
    if _same_id(person_id, current.get("shift_person_id")) and label == (current.get("shift_label") or ""):
        return "keep", color
    try:
        resolved = resolve_manual_shift(
            {
                "is_shift": True,
                "shift_person_id": person_id,
                "shift_label": label,
            }
        )
    except ShiftError as exc:
        raise InputError(str(exc)) from exc
    if not resolved or not resolved.get("is_shift"):
        raise InputError("לא הצלחתי לשמור את המשמרת.")
    if resolved.get("color"):
        color = resolved["color"]
    return (1, resolved["shift_person_id"], resolved["shift_label"]), color


def update_user_event(draft: dict) -> tuple[str, dict | None]:
    """``ok`` / ``deleted`` / ``conflict`` / ``readonly`` והאירוע הרלוונטי."""
    event_id = draft.get("event_id")
    current = get_event(event_id)
    if current is None:
        return "deleted", None
    if current.get("gcal_source_id"):
        return "readonly", current
    if not draft.get("force") and fingerprint(current) != draft.get("base"):
        return "conflict", current
    day = _day(draft.get("gregorian_date") or "")
    color = current.get("color")
    shift_arg = "keep"
    if current.get("is_shift"):
        title = (draft.get("title") or "").strip() or (current.get("title") or "")
        time_value = None
        if "description" in draft:
            description = draft.get("description") or ""
        else:
            description = current.get("description") or ""
        end = None
        shift_arg, color = _shift_write(draft, current, color)
    else:
        title = draft.get("title") or ""
        time_value = draft.get("time")
        description = draft.get("description") or ""
        end = _blank_end(day.isoformat(), draft.get("end_date"))
    cleaned = clean_event_write(
        {
            "title": title,
            "gregorian_date": day.isoformat(),
            "hebrew_date": hebrew_display(day),
            "time": time_value,
            "description": description,
            "end_date": end,
            "color": color,
        }
    )
    update_event(
        event_id,
        cleaned["title"],
        cleaned["gregorian_date"],
        cleaned["hebrew_date"],
        time=cleaned["time"],
        description=cleaned["description"],
        end_date=cleaned["end_date"],
        color=color,
        recurrence="keep",
        shift=shift_arg,
    )
    saved = get_event(event_id)
    if saved is None:
        return "deleted", None
    return "ok", saved


def remove_event(event_id: int) -> bool:
    event = get_event(event_id)
    if event is None or event.get("gcal_source_id"):
        return False
    return bool(delete_event(event_id))
