"""אימות שדות אירוע — משותף ל-API ולייבוא."""
from __future__ import annotations

from datetime import date

from app.reminders.schedule import _parse_hhmm

TITLE_MAX = 200
DESCRIPTION_MAX = 2000


class EventPayloadError(ValueError):
    """קלט אירוע לא תקין."""


def parse_real_date(value) -> date:
    """YYYY-MM-DD שקיים בלוח. 2026-02-31 נדחה."""
    raw = str(value or "").strip()
    try:
        parsed = date.fromisoformat(raw)
    except (TypeError, ValueError) as exc:
        raise EventPayloadError("Invalid date format. Expected YYYY-MM-DD") from exc
    if parsed.isoformat() != raw:
        raise EventPayloadError("Invalid date format. Expected YYYY-MM-DD")
    return parsed


def clean_event_time(value):
    """None / ריק = בלי שעה. אחרת חייב HH:MM אמיתי."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = _parse_hhmm(text)
    if parsed is None:
        raise EventPayloadError("שעה לא תקינה. צריך HH:MM")
    hour, minute = parsed
    return f"{hour:02d}:{minute:02d}"


def clean_event_write(data: dict) -> dict:
    """כותרת, תאריכים, שעה ותיאור מוכנים לכתיבה."""
    if not isinstance(data, dict):
        raise EventPayloadError("האירוע חייב להיות אובייקט")

    title = (data.get("title") or "").strip() if isinstance(data.get("title"), str) else ""
    if not isinstance(data.get("title"), str):
        title = str(data.get("title") or "").strip()
    if not title:
        raise EventPayloadError("חסרה כותרת")
    if len(title) > TITLE_MAX:
        raise EventPayloadError("הכותרת ארוכה מדי")

    raw_description = data.get("description", "")
    if raw_description is None:
        description = ""
    elif not isinstance(raw_description, str):
        description = str(raw_description)
    else:
        description = raw_description
    if len(description) > DESCRIPTION_MAX:
        raise EventPayloadError("התיאור ארוך מדי")

    gregorian = parse_real_date(data.get("gregorian_date"))
    hebrew = data.get("hebrew_date")
    hebrew = (hebrew or "").strip() if isinstance(hebrew, str) else str(hebrew or "").strip()
    if not hebrew:
        raise EventPayloadError("חסר תאריך עברי")

    time_value = clean_event_time(data.get("time"))
    end_raw = data.get("end_date") or None
    end_date = None
    if end_raw:
        end_date = parse_real_date(end_raw)
        if end_date < gregorian:
            raise EventPayloadError("תאריך הסיום לא יכול להיות לפני ההתחלה")

    return {
        "title": title,
        "gregorian_date": gregorian.isoformat(),
        "hebrew_date": hebrew,
        "time": time_value,
        "description": description,
        "end_date": end_date.isoformat() if end_date else None,
        "color": data.get("color"),
    }
