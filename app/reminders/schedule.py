"""חישוב מועד תזכורת. בלי רשת ובלי בסיס נתונים — נוח לבדיקות.

אירוע בלי ``recurrence_freq`` מתנהג כמו קודם: המופע הוא התאריך הלועזי,
ו-``now`` לא מזיז אותו. באירוע חוזר ``occurrence_start`` מחזירה את המופע
הבא (אחרי חריגות) שזמן ההתחלה שלו לא עבר. שליחה per-occurrence נרשמת
ב-``reminder_sends``, לא ב-``sent_at``.

ההפרש של התזכורת מחושב ב-UTC (דקות אמיתיות), לא בשעון הקיר. במעבר שעון
של ישראל חיסור על datetime מודע סוטה בשעה. התצוגה נשארת בשעה מקומית.
``sent_at`` נשמר ב-UTC בנפרד (``repository.mark_reminder_sent``).
"""
from __future__ import annotations

import html
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MAX_OFFSET_MINUTES = 365 * 24 * 60

PRESET_OFFSETS = (
    (0, "בזמן"),
    (5, "5 דקות"),
    (10, "10 דקות"),
    (15, "15 דקות"),
    (30, "30 דקות"),
    (60, "שעה"),
    (120, "שעתיים"),
    (180, "3 שעות"),
    (360, "6 שעות"),
    (720, "12 שעות"),
    (1440, "יום"),
    (2880, "יומיים"),
    (4320, "3 ימים"),
    (10080, "שבוע"),
)

PRESET_LABELS = dict(PRESET_OFFSETS)

_UNIT_MINUTES = {
    "minutes": 1,
    "minute": 1,
    "דקות": 1,
    "דקה": 1,
    "hours": 60,
    "hour": 60,
    "שעות": 60,
    "שעה": 60,
    "days": 1440,
    "day": 1440,
    "ימים": 1440,
    "יום": 1440,
}

_HHMM = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")


class OffsetError(ValueError):
    """offset לא חוקי (יחידה, טווח, או ערך לא מספרי)."""


def reminder_timezone() -> ZoneInfo:
    name = (os.getenv("REMINDER_TIMEZONE") or "Asia/Jerusalem").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Jerusalem")


def reminder_default_time() -> str:
    """שעה מקומית לאירוע בלי שדה time. ברירת מחדל 09:00."""
    raw = (os.getenv("REMINDER_DEFAULT_TIME") or "09:00").strip()
    parsed = _parse_hhmm(raw)
    if parsed is None:
        return "09:00"
    hour, minute = parsed
    return f"{hour:02d}:{minute:02d}"


def _parse_hhmm(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    match = _HHMM.fullmatch(value.strip())
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _as_int(value) -> int:
    if isinstance(value, bool) or isinstance(value, float):
        raise OffsetError("ההפרש חייב להיות מספר שלם")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    raise OffsetError("ההפרש חייב להיות מספר שלם")


def custom_offset_minutes(amount, unit) -> int:
    """ממיר מספר + יחידה (דקות/שעות/ימים) לדקות. 0 ומטה נדחים.

    «בזמן האירוע» הוא offset 0 מהרשימה הקבועה, לא ערך מותאם.
    """
    count = _as_int(amount)
    if count <= 0:
        raise OffsetError("המספר חייב להיות חיובי")
    key = (unit or "").strip().lower()
    factor = _UNIT_MINUTES.get(key)
    if factor is None:
        factor = _UNIT_MINUTES.get((unit or "").strip())
    if factor is None:
        raise OffsetError("היחידה חייבת להיות דקות, שעות או ימים")
    minutes = count * factor
    if minutes > MAX_OFFSET_MINUTES:
        raise OffsetError("ההפרש גדול מדי (עד שנה)")
    return minutes


def coerce_offset_minutes(value) -> int:
    minutes = _as_int(value)
    if minutes < 0 or minutes > MAX_OFFSET_MINUTES:
        raise OffsetError("ההפרש חייב להיות בין 0 לדקות של שנה")
    return minutes


def normalize_reminder_item(item) -> dict:
    """מחזיר ``{offset_minutes, recipient_ids}``.

    מתקבל או ``offset_minutes`` (כולל 0), או ``amount`` + ``unit``.
    """
    if not isinstance(item, dict):
        raise OffsetError("כל תזכורת חייבת להיות אובייקט")

    has_offset = item.get("offset_minutes") is not None and item.get("offset_minutes") != ""
    has_custom = item.get("amount") is not None and item.get("amount") != ""
    if has_custom and not has_offset:
        minutes = custom_offset_minutes(item.get("amount"), item.get("unit"))
    elif has_offset:
        minutes = coerce_offset_minutes(item.get("offset_minutes"))
    else:
        raise OffsetError("חסר זמן לתזכורת")

    raw_ids = item.get("recipient_ids") or []
    if not isinstance(raw_ids, list):
        raise OffsetError("רשימת הנמענים חייבת להיות מערך")
    recipient_ids = []
    for raw in raw_ids:
        try:
            person_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise OffsetError("מזהה נמען חייב להיות מספר") from exc
        if person_id <= 0:
            raise OffsetError("מזהה נמען חייב להיות מספר")
        if person_id not in recipient_ids:
            recipient_ids.append(person_id)
    return {"offset_minutes": minutes, "recipient_ids": recipient_ids}


def parse_reminders_payload(raw, valid_people_ids: set[int] | None = None) -> list[dict]:
    """מאחד כפילויות של אותו offset ומאמת שנמענים קיימים."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise OffsetError("תזכורות חייבות להיות רשימה")

    merged: dict[int, list[int]] = {}
    order: list[int] = []
    allowed = valid_people_ids
    for item in raw:
        normal = normalize_reminder_item(item)
        offset = normal["offset_minutes"]
        if offset not in merged:
            merged[offset] = []
            order.append(offset)
        for person_id in normal["recipient_ids"]:
            if allowed is not None and person_id not in allowed:
                raise OffsetError(f"נמען לא קיים: {person_id}")
            if person_id not in merged[offset]:
                merged[offset].append(person_id)
    return [
        {"offset_minutes": offset, "recipient_ids": merged[offset]}
        for offset in order
    ]


def offset_label(minutes: int) -> str:
    if minutes in PRESET_LABELS:
        return PRESET_LABELS[minutes]
    if minutes % 1440 == 0:
        days = minutes // 1440
        if days == 1:
            return "יום"
        return f"{days} ימים"
    if minutes % 60 == 0:
        hours = minutes // 60
        if hours == 1:
            return "שעה"
        if hours == 2:
            return "שעתיים"
        return f"{hours} שעות"
    if minutes == 1:
        return "דקה"
    return f"{minutes} דקות"


def _aware(now: datetime, tz: ZoneInfo) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _to_utc(moment: datetime, tz: ZoneInfo) -> datetime:
    """רגע ב-UTC. ערך נאיבי נקרא כשעון מקומי, לא כ-UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    return moment.astimezone(timezone.utc)


def _localize(year: int, month: int, day: int, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """שעת קיר → רגע אמיתי באזור ``tz``.

    שעה כפולה (סתיו, 01:00–02:00): ``fold=0``, הפעם הראשונה שהשעון מראה אותה.
    שעה שלא קיימת (אביב, 02:00–03:00): ``fold=0`` ואז נרמול דרך UTC. הרגע
    נשאר, והשעון המוצג זז קדימה אל השעה שבאמת קיימת (02:30 → 03:30).
    """
    wall = datetime(year, month, day, hour, minute)
    attached = wall.replace(tzinfo=tz, fold=0)
    normalized = attached.astimezone(timezone.utc).astimezone(tz)
    same_clock = (
        normalized.fold == 0
        and normalized.year == wall.year
        and normalized.month == wall.month
        and normalized.day == wall.day
        and normalized.hour == wall.hour
        and normalized.minute == wall.minute
    )
    if same_clock:
        return attached
    return normalized


def apply_offset(start: datetime, offset_minutes: int) -> datetime:
    """מחסיר דקות בזמן מוחלט ומחזיר את הרגע באזור של ``start``.

    ``start - timedelta`` על datetime עם ZoneInfo הוא חשבון שעון-קיר:
    חלון שחוצה את החזרת השעון (25.10) או את הקדמתו (סוף מרץ) נדלק
    שעה מוקדם או מאוחר. כאן החיסור הוא על UTC.
    """
    zone = start.tzinfo or reminder_timezone()
    if start.tzinfo is None:
        start = start.replace(tzinfo=zone)
    fired = start.astimezone(timezone.utc) - timedelta(minutes=int(offset_minutes))
    return fired.astimezone(zone)


def event_start(event: dict, *, tz: ZoneInfo | None = None, default_time: str | None = None) -> datetime:
    """תחילת האירוע באזור הזמן המקומי.

    בלי שעה (או שעה לא תקינה) — ``default_time``, ברירת מחדל 09:00.
    שעה כפולה במעבר סתיו נלקחת בפעם הראשונה (``fold=0``). שעה בחור
    של האביב מוזזת קדימה לשעה המקומית שקיימת.
    """
    tz = tz or reminder_timezone()
    default_time = default_time if default_time is not None else reminder_default_time()
    date_raw = event.get("gregorian_date")
    if not date_raw:
        raise OffsetError("לאירוע אין תאריך")
    date_value = datetime.strptime(date_raw, "%Y-%m-%d").date()
    parsed = _parse_hhmm(event.get("time")) or _parse_hhmm(default_time) or (9, 0)
    hour, minute = parsed
    return _localize(date_value.year, date_value.month, date_value.day, hour, minute, tz)


def occurrence_start(
    event: dict,
    now: datetime | None = None,
    *,
    tz: ZoneInfo | None = None,
    default_time: str | None = None,
) -> datetime:
    """המופע שעליו חלה התזכורת.

    בלי חזרה — תאריך האירוע, בלי קשר ל-``now``.
    עם חזרה — המופע הבא שתחילתו >= ``now`` (ברירת מחדל: עכשיו).
    ההשוואה ב-UTC: בשעה כפולה ``==`` של אותו ZoneInfo מתעלם מ-``fold``.
    """
    tz = tz or reminder_timezone()
    anchor = event_start(event, tz=tz, default_time=default_time)
    if not event.get("recurrence_freq"):
        return anchor
    from app.services.recurrence import expand_event, is_recurring

    if not is_recurring(event):
        return anchor
    current = _aware(now or datetime.now(tz), tz)
    window_from = current.date()
    window_to = current.date() + timedelta(days=800)
    rows = expand_event(event, event.get("exceptions") or [], window_from, window_to)
    for row in rows:
        start = event_start(
            {**event, "gregorian_date": row["gregorian_date"], "time": row.get("time")},
            tz=tz,
            default_time=default_time,
        )
        if _to_utc(start, tz) >= _to_utc(current, tz):
            return start
    return anchor


def fire_at(
    event: dict,
    offset_minutes: int,
    *,
    now: datetime | None = None,
    tz: ZoneInfo | None = None,
    default_time: str | None = None,
) -> datetime:
    start = occurrence_start(event, now, tz=tz, default_time=default_time)
    return apply_offset(start, offset_minutes)


def is_due(fire: datetime, now: datetime, sent_at) -> bool:
    if sent_at:
        return False
    zone = fire.tzinfo or reminder_timezone()
    return _to_utc(fire, zone) <= _to_utc(now, zone)


def in_browser_window(
    fire: datetime,
    now: datetime,
    *,
    within_seconds: int,
    grace_seconds: int,
) -> bool:
    """חלון להתראת דפדפן: קצת לפני המועד, ועוד קצת אחריו.

    לא תלוי ב-``sent_at`` של הטלגרם. הטאב שומר אצלו מה כבר הוצג.
    הגבולות בדקות אמיתיות (UTC), לא בשעון הקיר.
    """
    zone = fire.tzinfo or reminder_timezone()
    current = _to_utc(now, zone)
    instant = _to_utc(fire, zone)
    return (
        current - timedelta(seconds=grace_seconds)
        <= instant
        <= current + timedelta(seconds=within_seconds)
    )


def reminder_message(event: dict, offset_minutes: int, start: datetime) -> str:
    """טקסט תזכורת. שדות משתמש בורחים ל-HTML (send_message שולח parse_mode=HTML)."""
    title = html.escape((event.get("title") or "אירוע").strip() or "אירוע", quote=False)
    lines = [
        f"תזכורת: {title}",
        f"{start.strftime('%Y-%m-%d %H:%M')} ({offset_label(offset_minutes)})",
    ]
    hebrew = html.escape((event.get("hebrew_date") or "").strip(), quote=False)
    if hebrew:
        lines.append(hebrew)
    description = html.escape((event.get("description") or "").strip(), quote=False)
    if description:
        lines.append(description)
    return "\n".join(lines)


def browser_body(event: dict, offset_minutes: int, start: datetime, fire: datetime, now: datetime) -> str:
    zone = fire.tzinfo or reminder_timezone()
    when = "עכשיו" if _to_utc(fire, zone) <= _to_utc(now, zone) else "בקרוב"
    clock = start.strftime("%H:%M")
    date_label = start.strftime("%Y-%m-%d")
    return f"{when} · {offset_label(offset_minutes)} · {date_label} {clock}"
