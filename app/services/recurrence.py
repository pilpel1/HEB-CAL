"""הרחבת מופעים של אירוע חוזר.

הכלל נשמר על שורת האירוע. המופעים לא נשמרים — הם מחושבים לטווח שנשאל.
אירוע בלי ``recurrence_freq`` הוא חד-פעמי, כמו כל האירועים שנשמרו לפני המיגרציה.

החלטות תאריך (נבדקות ב-tests/test_recurrence.py):

חשוון / כסלו בן 30 יום בשנה שבה החודש קצר (29):
    היום האחרון של אותו חודש (כ״ט), לא א׳ בחודש הבא.
    זה נוהג נפוץ ליום-השנה כשאין ל׳ בחודש.

אדר (יום-הולדת / בר-מצווה / פורים — hebcal birthday, לא יארצייט):
    - עוגן באדר של שנה פשוטה (חודש 12, השנה לא מעוברת) → בשנה מעוברת: אדר ב׳.
    - עוגן באדר א׳ (חודש 12 בשנה מעוברת) → בשנה פשוטה: אדר; במעוברת נשאר אדר א׳.
    - עוגן באדר ב׳ (חודש 13) → בשנה פשוטה: אדר; במעוברת נשאר אדר ב׳.
    - ל׳ אדר א׳ בשנה פשוטה → א׳ ניסן.
      זה כלל יום-ההולדת של hebcal (Calendrical Calculations, Reingold & Dershowitz):
      כשהיום לא קיים, דוחים לא׳ בחודש הבא. pyluach עם ``NEXT_DAY`` נותן אותו יום.
      לא ל׳ שבט — זה כלל היארצייט של hebcal (היום האחרון בשבט).
      לא כ״ט אדר — זה מה ש-``PREVIOUS_DAY`` עושה, ולא בחרנו בו לל׳ אדר א׳.
    ל׳ חשוון/כסלו נשארים כ״ט באותו חודש (הכלל למעלה), ולא א׳ בחודש הבא.
    יארצייט של hebcal היה שם אדר פשוט על אדר א׳; כאן המנהג הוא אדר ב׳.
    חודשי (לא שנתי) פשוט מתקדם חודש-חודש, בלי הכללים האלה.

לועזי:
    - 29 בפברואר → 28 בפברואר בשנה לא מעוברת, וחוזר ל-29 במעוברת.
    - חודשי ביום 31 → היום האחרון של החודש (פברואר 28/29, חודש בן 30 → 30).
      היום נמדד מהעוגן, לא מהמופע הקודם, כדי שמרץ אחרי פברואר יישאר 31.

סיום הסדרה (מה שמגיע קודם):
    - ``until``: תאריך לועזי כולל של תחילת המופע.
    - ``count``: N מופעים כולל הראשון.
    - בלי שניהם: בלי סוף (ההרחבה נעצרת בטווח המבוקש).

חריגות (טבלת event_exceptions), לפי תאריך המקורי של המופע:
    - ``deleted``: המופע לא מוחזר.
    - ``edited``: הכותרת / התאריך / השעה וכו׳ של המופע הזה בלבד.
      עריכת "כל הסדרה" לא מוחקת חריגות, חוץ משינוי העוגן או סוג החזרה
      (אז תאריכי המקור כבר לא שייכים לסדרה).
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from pyluach.dates import GregorianDate, HebrewDate, Rounding
from pyluach.hebrewcal import Year

from app.services.hebrew_format import format_hebrew_date

MAX_OCCURRENCES = 2400
MAX_YEAR = 2200

HEBREW_MONTHS = {
    1: "ניסן",
    2: "אייר",
    3: "סיון",
    4: "תמוז",
    5: "אב",
    6: "אלול",
    7: "תשרי",
    8: "חשון",
    9: "כסלו",
    10: "טבת",
    11: "שבט",
    12: "אדר",
    13: "אדר ב",
}

HEBREW_DAYS = {
    1: "א", 2: "ב", 3: "ג", 4: "ד", 5: "ה", 6: "ו", 7: "ז", 8: "ח", 9: "ט", 10: "י",
    11: "יא", 12: "יב", 13: "יג", 14: "יד", 15: "טו", 16: "טז", 17: "יז", 18: "יח",
    19: "יט", 20: "כ", 21: "כא", 22: "כב", 23: "כג", 24: "כד", 25: "כה", 26: "כו",
    27: "כז", 28: "כח", 29: "כט", 30: "ל",
}

FREQS = ("monthly", "yearly")
CALENDARS = ("gregorian", "hebrew")


class RecurrenceError(ValueError):
    """כלל חזרה לא חוקי."""


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise RecurrenceError("תאריך לא תקין. צריך YYYY-MM-DD") from exc


def clean_recurrence(freq, calendar_name, until, count, anchor: date) -> dict | None:
    """מאמת כלל חזרה. ``None`` = אין חזרה.

    ``freq`` ריק / none / null נחשב "בלי חזרה".
    """
    if freq is None or freq is False:
        return None
    text = str(freq).strip().lower()
    if text in ("", "none", "null"):
        return None
    if text not in FREQS:
        raise RecurrenceError("חזרה יכולה להיות חודשית, שנתית, או בלי חזרה")

    calendar_text = (str(calendar_name).strip().lower() if calendar_name else "") or "gregorian"
    if calendar_text not in CALENDARS:
        raise RecurrenceError("הלוח של החזרה הוא עברי או לועזי")

    until_date = _parse_iso(until) if until else None
    if until_date and until_date < anchor:
        raise RecurrenceError("תאריך סיום החזרה חייב להיות בתאריך האירוע או אחריו")

    count_value = None
    if count is not None and count != "":
        if isinstance(count, bool) or isinstance(count, float):
            raise RecurrenceError("מספר הפעמים חייב להיות מספר שלם")
        try:
            count_value = int(count)
        except (TypeError, ValueError) as exc:
            raise RecurrenceError("מספר הפעמים חייב להיות מספר שלם") from exc
        if count_value < 1 or count_value > MAX_OCCURRENCES:
            raise RecurrenceError(f"מספר הפעמים חייב להיות בין 1 ל-{MAX_OCCURRENCES}")

    return {
        "recurrence_freq": text,
        "recurrence_calendar": calendar_text,
        "recurrence_until": until_date.isoformat() if until_date else None,
        "recurrence_count": count_value,
    }


def recurrence_fields(event: dict) -> dict:
    freq = event.get("recurrence_freq") or None
    if freq not in FREQS:
        freq = None
    calendar_name = event.get("recurrence_calendar") if freq else None
    if calendar_name not in CALENDARS:
        calendar_name = "gregorian" if freq else None
    until = event.get("recurrence_until") or None
    count = event.get("recurrence_count")
    if count is not None and count != "":
        try:
            count = int(count)
        except (TypeError, ValueError):
            count = None
    else:
        count = None
    return {
        "recurrence_freq": freq,
        "recurrence_calendar": calendar_name,
        "recurrence_until": until,
        "recurrence_count": count,
    }


def is_recurring(event: dict) -> bool:
    return recurrence_fields(event)["recurrence_freq"] in FREQS


def hebrew_display(day: date) -> str:
    heb = GregorianDate(day.year, day.month, day.day).to_heb()
    return format_hebrew_date(
        HEBREW_DAYS.get(heb.day, str(heb.day)),
        HEBREW_MONTHS.get(heb.month, ""),
        heb.year,
    )


def _greg_add_months(anchor: date, steps: int) -> date:
    month_index = anchor.month - 1 + steps
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last))


def _greg_add_years(anchor: date, steps: int) -> date:
    year = anchor.year + steps
    last = calendar.monthrange(year, anchor.month)[1]
    return date(year, anchor.month, min(anchor.day, last))


def _hebrew_anchor(anchor: date) -> HebrewDate:
    return GregorianDate(anchor.year, anchor.month, anchor.day).to_heb()


def _heb_to_date(heb: HebrewDate) -> date:
    greg = heb.to_greg()
    return date(greg.year, greg.month, greg.day)


def _hebrew_add_years(anchor: HebrewDate, years: int) -> HebrewDate:
    """שנתי עברי. ל׳ אדר א׳ בשנה פשוטה → א׳ ניסן. פירוט בראש הקובץ."""
    moved = anchor.add(years=years, rounding=Rounding.PREVIOUS_DAY, adar1=False)
    if (
        years
        and anchor.month == 12
        and anchor.day == 30
        and Year(anchor.year).leap
        and not Year(moved.year).leap
    ):
        return HebrewDate(moved.year, 1, 1)
    return moved


def nth_start(anchor: date, freq: str, calendar_name: str, index: int) -> date:
    """המופע ה-index (0 = העוגן עצמו)."""
    if index < 0:
        raise RecurrenceError("אינדקס מופע שלילי")
    if index == 0:
        return anchor
    if calendar_name == "hebrew":
        heb = _hebrew_anchor(anchor)
        if freq == "yearly":
            moved = _hebrew_add_years(heb, index)
        else:
            moved = heb.add(months=index, rounding=Rounding.PREVIOUS_DAY)
        return _heb_to_date(moved)
    if freq == "yearly":
        return _greg_add_years(anchor, index)
    return _greg_add_months(anchor, index)


def iter_starts(event: dict):
    """מניב (date, index) מהעוגן, כולל חיתוך until/count."""
    try:
        anchor = _parse_iso(event.get("gregorian_date"))
    except RecurrenceError:
        return
    if anchor is None:
        return
    rule = recurrence_fields(event)
    freq = rule["recurrence_freq"]
    if not freq:
        yield anchor, 0
        return

    until = _parse_iso(rule["recurrence_until"]) if rule["recurrence_until"] else None
    count = rule["recurrence_count"]
    calendar_name = rule["recurrence_calendar"] or "gregorian"
    for index in range(MAX_OCCURRENCES):
        if count is not None and index >= count:
            return
        start = nth_start(anchor, freq, calendar_name, index)
        if start.year > MAX_YEAR:
            return
        if until and start > until:
            return
        yield start, index


def duration_days(event: dict) -> int:
    try:
        start = _parse_iso(event.get("gregorian_date"))
        end = _parse_iso(event.get("end_date"))
    except RecurrenceError:
        return 0
    if not start or not end or end <= start:
        return 0
    return (end - start).days


def _overlaps(start: date, end: date, range_from: date, range_to: date) -> bool:
    return start <= range_to and end >= range_from


def is_series_date(event: dict, original: date) -> bool:
    """האם ``original`` הוא תאריך מקור של מופע (לפני חריגה)."""
    for start, _index in iter_starts(event):
        if start == original:
            return True
        if start > original:
            return False
    return False


def _generation_limit(range_to: date, exceptions: list[dict]) -> date:
    """עד איזה תאריך מקור חייבים לייצר כדי לתפוס גם מופע שהוזז לתוך הטווח."""
    limit = range_to
    for ex in exceptions:
        if ex.get("kind") != "edited" or not ex.get("gregorian_date") or not ex.get("original_date"):
            continue
        try:
            edited = date.fromisoformat(ex["gregorian_date"][:10])
            original = date.fromisoformat(ex["original_date"][:10])
        except ValueError:
            continue
        edited_end = _parse_iso(ex.get("end_date")) or edited
        if edited_end < edited:
            edited_end = edited
        if _overlaps(edited, edited_end, date.min, range_to) and original > limit:
            # נבדוק חפיפה אמיתית מול הטווח אחר כך; כאן רק מרחיבים את הייצור
            if edited <= range_to:
                limit = original
    return limit


def expand_event(event: dict, exceptions: list[dict] | None, range_from: date, range_to: date) -> list[dict]:
    """מופעים של אירוע אחד שנוגעים בטווח ``[range_from, range_to]`` (כולל)."""
    if range_to < range_from:
        return []
    exceptions = exceptions or []
    by_original = {}
    for ex in exceptions:
        original = ex.get("original_date")
        if original:
            by_original[original[:10]] = ex

    span = duration_days(event)
    rule = recurrence_fields(event)
    limit = _generation_limit(range_to, exceptions) if rule["recurrence_freq"] else range_to
    found = []

    for start, index in iter_starts(event):
        original = start.isoformat()
        ex = by_original.get(original)
        if ex and ex.get("kind") == "deleted":
            if start > limit:
                break
            continue

        if ex and ex.get("kind") == "edited" and ex.get("gregorian_date"):
            occ_start = _parse_iso(ex.get("gregorian_date")) or start
            occ_end = _parse_iso(ex.get("end_date")) or occ_start
            if occ_end < occ_start:
                occ_end = occ_start
            display = {
                "title": ex.get("title") if ex.get("title") is not None else event.get("title"),
                "gregorian_date": occ_start.isoformat(),
                "hebrew_date": ex.get("hebrew_date") or hebrew_display(occ_start),
                "time": ex.get("time"),
                "description": ex.get("description") if ex.get("description") is not None else event.get("description"),
                "end_date": occ_end.isoformat() if occ_end > occ_start else None,
                "color": ex.get("color"),
                "is_exception": True,
            }
        else:
            occ_start = start
            occ_end = start + timedelta(days=span) if span else start
            display = {
                "title": event.get("title"),
                "gregorian_date": occ_start.isoformat(),
                "hebrew_date": event.get("hebrew_date") if index == 0 else hebrew_display(occ_start),
                "time": event.get("time"),
                "description": event.get("description") or "",
                "end_date": occ_end.isoformat() if span else None,
                "color": event.get("color"),
                "is_exception": False,
            }

        if _overlaps(occ_start, occ_end, range_from, range_to):
            found.append({
                "id": event.get("id"),
                "series_id": event.get("id"),
                "occurrence_date": original,
                "occurrence_index": index,
                "recurring": bool(rule["recurrence_freq"]),
                **rule,
                **display,
                "reminders": event.get("reminders") or [],
                "is_shift": 1 if event.get("is_shift") else 0,
                "shift_person_id": event.get("shift_person_id"),
                "shift_label": event.get("shift_label") or None,
            })

        if start > limit:
            break

    return found


def expand_events(events: list[dict], exceptions_by_event: dict, range_from: date, range_to: date) -> list[dict]:
    rows = []
    for event in events:
        rows.extend(
            expand_event(
                event,
                exceptions_by_event.get(event.get("id")) or [],
                range_from,
                range_to,
            )
        )
    rows.sort(key=lambda item: (item.get("gregorian_date") or "", item.get("time") or "", item.get("id") or 0))
    return rows


def next_start_on_or_after(event: dict, day: date) -> date | None:
    """תאריך המקור הבא (אחרי חריגת מחיקה) שתחילתו >= day. None אם הסדרה נגמרה."""
    for start, _index in iter_starts(event):
        if start >= day:
            return start
    return None
