"""תאריך ושעה שהמשתמש מקליד. התאריך הסופי עובר גם ב-clean_event_write."""
from __future__ import annotations

import re
from datetime import date

from app.services.event_payload import EventPayloadError, clean_event_time, parse_real_date

_DMY = re.compile(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$")
_COMPACT_TIME = re.compile(r"^\d{3,4}$")


class InputError(ValueError):
    """טקסט שאפשר להראות כמו שהוא במסך."""


def parse_user_date(text: str, today: date) -> date:
    raw = " ".join((text or "").strip().split())
    if raw == "היום":
        return today
    if raw == "מחר":
        return today.fromordinal(today.toordinal() + 1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return parse_real_date(raw)
        except EventPayloadError as exc:
            raise InputError("התאריך לא קיים. למשל 22.10.2026.") from exc
    match = _DMY.fullmatch(raw)
    if not match:
        raise InputError("התאריך לא ברור. למשל 22.10.2026.")
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise InputError("התאריך לא קיים. למשל 22.10.2026.") from exc
    return parsed


def parse_user_time(text: str) -> str | None:
    """``None`` = כל היום. אחרת HH:MM אחרי אותה בדיקה של האירועים."""
    raw = " ".join((text or "").strip().split())
    if raw in {"כל היום", "יום שלם", "בלי שעה", "-"}:
        return None
    compact = raw.replace(".", ":").replace(" ", "")
    if _COMPACT_TIME.fullmatch(compact):
        compact = compact.zfill(4)
        compact = f"{compact[:2]}:{compact[2:]}"
    try:
        cleaned = clean_event_time(compact)
    except EventPayloadError as exc:
        raise InputError("השעה לא תקינה. למשל 18:30.") from exc
    if cleaned is None:
        raise InputError("השעה לא תקינה. למשל 18:30.")
    return cleaned


def explain_payload_error(exc: EventPayloadError) -> str:
    message = str(exc)
    if "לפני" in message:
        return "תאריך הסיום לפני ההתחלה."
    if "שעה" in message or "HH:MM" in message:
        return "השעה לא תקינה. למשל 18:30."
    if "כותרת" in message or "תיאור" in message or "חסר" in message:
        return message
    if "date" in message.lower() or "תאריך" in message:
        return "התאריך לא תקין. למשל 22.10.2026."
    return message
