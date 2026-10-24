"""המרת יומן iCal לאירועים בזמן ישראל.

חזרות של גוגל (שבועי, יומי, BYDAY) לא נכנסות למודל החזרה של HEB-CAL
(חודשי/שנתי בלבד). כל מופע בחלון נשמר כשורה, עם מזהה יציב:
לסדרה — חותמת ה-RECURRENCE-ID, לאירוע בודד — מחרוזת ריקה (אותו UID מתעדכן).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar
from recurring_ical_events import of

from app.gcal.errors import GcalUserError
from app.services.event_payload import DESCRIPTION_MAX, TITLE_MAX
from app.services.hebrew_dates import gregorian_to_hebrew

JERUSALEM = ZoneInfo("Asia/Jerusalem")
PARSE_ERROR = "הקובץ שהתקבל אינו יומן iCal תקין."


def parse_ical(payload: bytes | str, window_start: date, window_end: date) -> list[dict]:
    """מופעים שנוגעים בחלון, כולל יום שלם ורב-יומי. בלי כפילויות."""
    if window_end < window_start:
        return []
    calendar = _load_calendar(payload)
    series = _series_uids(calendar)
    start = datetime.combine(window_start, time.min, tzinfo=JERUSALEM)
    end = datetime.combine(window_end, time.max, tzinfo=JERUSALEM)
    try:
        expanded = of(calendar).between(start, end)
    except Exception as exc:
        raise GcalUserError(PARSE_ERROR) from exc

    by_key: dict[tuple[str, str], dict] = {}
    for component in expanded:
        status = str(component.get("STATUS") or "").upper()
        if status == "CANCELLED":
            continue
        uid = str(component.get("UID") or "").strip()
        if not uid:
            continue
        try:
            row = _occurrence(component, uid, series)
        except GcalUserError:
            raise
        except Exception as exc:
            raise GcalUserError(PARSE_ERROR) from exc
        if row is None:
            continue
        if not _overlaps(row["gregorian_date"], row["end_date"], window_start, window_end):
            continue
        by_key[(row["gcal_uid"], row["gcal_recurrence_id"])] = row
    return list(by_key.values())


def _load_calendar(payload: bytes | str) -> Calendar:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not raw or not raw.strip():
        raise GcalUserError(PARSE_ERROR)
    try:
        calendar = Calendar.from_ical(raw)
    except Exception as exc:
        raise GcalUserError(PARSE_ERROR) from exc
    if calendar is None:
        raise GcalUserError(PARSE_ERROR)
    return calendar


def _series_uids(calendar) -> set[str]:
    """UID שיש לו RRULE או RECURRENCE-ID בקובץ המקורי, לפני ההרחבה."""
    found: set[str] = set()
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("UID") or "").strip()
        if not uid:
            continue
        if component.get("RRULE") or component.get("RECURRENCE-ID"):
            found.add(uid)
    return found


def _occurrence(component, uid: str, series: set[str]) -> dict | None:
    start_raw = _decoded(component, "DTSTART")
    if start_raw is None:
        return None
    end_raw = _decoded(component, "DTEND")
    duration = _decoded(component, "DURATION")
    all_day = isinstance(start_raw, date) and not isinstance(start_raw, datetime)

    if all_day:
        start_day = start_raw
        end_exclusive = _all_day_end(start_day, end_raw, duration)
        last_day = end_exclusive - timedelta(days=1)
        if last_day < start_day:
            last_day = start_day
        gregorian = start_day
        time_value = None
        end_date = last_day.isoformat() if last_day > start_day else None
    else:
        start = _to_jerusalem(start_raw)
        end = _timed_end(start, end_raw, duration)
        gregorian = start.date()
        time_value = start.strftime("%H:%M")
        end_day = end.date()
        if end_day > gregorian and end.timetz().replace(tzinfo=None) == time.min:
            end_day -= timedelta(days=1)
        end_date = end_day.isoformat() if end_day > gregorian else None

    rid = ""
    if uid in series:
        rid_value = component.get("RECURRENCE-ID")
        stamp_source = rid_value.dt if rid_value is not None else start_raw
        rid = recurrence_stamp(stamp_source)

    return {
        "title": _clip(_plain(component.get("SUMMARY")) or "(ללא כותרת)", TITLE_MAX),
        "gregorian_date": gregorian.isoformat(),
        "hebrew_date": gregorian_to_hebrew(gregorian)["hebrew_date"],
        "time": time_value,
        "description": _description(component),
        "end_date": end_date,
        "gcal_uid": uid,
        "gcal_recurrence_id": rid,
    }


def recurrence_stamp(value) -> str:
    """חותמת יציבה: יום שלם כ-YYYY-MM-DD, שעה ב-UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=JERUSALEM)
        utc = value.astimezone(timezone.utc).replace(microsecond=0)
        return utc.strftime("%Y%m%dT%H%M%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return ""


def _decoded(component, name):
    if component.get(name) is None:
        return None
    return component.decoded(name)


def _to_jerusalem(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=JERUSALEM)
    return value.astimezone(JERUSALEM)


def _all_day_end(start_day: date, end_raw, duration) -> date:
    """DTEND של יום שלם הוא בלעדי (היום שאחרי היום האחרון)."""
    if isinstance(duration, timedelta):
        return start_day + duration
    if isinstance(end_raw, datetime):
        return _to_jerusalem(end_raw).date()
    if isinstance(end_raw, date):
        return end_raw
    return start_day + timedelta(days=1)


def _timed_end(start: datetime, end_raw, duration) -> datetime:
    if isinstance(duration, timedelta):
        return start + duration
    if isinstance(end_raw, datetime):
        return _to_jerusalem(end_raw)
    if isinstance(end_raw, date):
        return datetime.combine(end_raw, time.min, tzinfo=JERUSALEM)
    return start


def _plain(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return text.strip()


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _description(component) -> str:
    text = _plain(component.get("DESCRIPTION"))
    location = _plain(component.get("LOCATION"))
    if location:
        text = f"{text}\nמיקום: {location}" if text else f"מיקום: {location}"
    return _clip(text, DESCRIPTION_MAX)


def overlaps_window(gregorian_date: str, end_date: str | None, start: date, end: date) -> bool:
    return _overlaps(gregorian_date, end_date, start, end)


def _overlaps(gregorian_date: str, end_date: str | None, start: date, end: date) -> bool:
    try:
        first = date.fromisoformat(str(gregorian_date)[:10])
    except ValueError:
        return False
    last = first
    if end_date:
        try:
            last = date.fromisoformat(str(end_date)[:10])
        except ValueError:
            last = first
    if last < first:
        last = first
    return first <= end and last >= start
