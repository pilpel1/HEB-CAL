"""המרה דו-כיוונית לועזי ↔ עברי לבחירת תאריך במודל.

חודש 1 = ניסן, 12 = אדר (או אדר א׳ בשנה מעוברת), 13 = אדר ב׳.
בשנה לא מעוברת אין חודש 13. חשוון וכסלו הם 29 או 30 לפי השנה (pyluach).

רשימת החודשים בבורר תלויה בשנה: שנה פשוטה — «אדר» אחד; שנה מעוברת —
«אדר א׳» ו«אדר ב׳». כשמחליפים שנה (``from_year``), אדר פשוט עובר לאדר ב׳,
ואדר א׳ או אדר ב׳ עוברים לאדר. יום שלא קיים בחודש היעד נחתך
(ל׳ אדר א׳ בבורר → כ״ט אדר). כלל החזרה השנתית (א׳ ניסן) חי ב-recurrence.py.
"""
from __future__ import annotations

import re
from datetime import date

from pyluach.dates import GregorianDate, HebrewDate
from pyluach.hebrewcal import Month, Year

from app.services.hebrew_format import format_hebrew_date, format_hebrew_year
from app.services.recurrence import HEBREW_DAYS, hebrew_month_name

MAX_YEAR_SPAN = 500


class HebrewDateError(ValueError):
    """תאריך עברי או טווח שנים לא תקינים."""


def _picker_month_name(leap: bool, month: int) -> str:
    return hebrew_month_name(month, leap=leap)


def _months(year: int, leap: bool) -> list[dict]:
    last = 13 if leap else 12
    return [
        {"value": month, "name": _picker_month_name(leap, month)}
        for month in range(1, last + 1)
    ]


def _describe(year: int, month: int, day: int, gregorian: date, adjusted: bool) -> dict:
    leap = Year(year).leap
    return {
        "hebrew_date": format_hebrew_date(
            HEBREW_DAYS.get(day, str(day)),
            _picker_month_name(leap, month),
            year,
        ),
        "gregorian_date": gregorian.isoformat(),
        "year": year,
        "month": month,
        "day": day,
        "year_label": format_hebrew_year(year),
        "leap": leap,
        "days_in_month": len(Month(year, month)),
        "months": _months(year, leap),
        "adjusted": adjusted,
    }


def gregorian_to_hebrew(day: date) -> dict:
    hebrew = GregorianDate(day.year, day.month, day.day).to_heb()
    return _describe(hebrew.year, hebrew.month, hebrew.day, day, False)


def _leap_year(year: int) -> bool:
    try:
        return Year(year).leap
    except Exception as exc:
        raise HebrewDateError("שנה עברית לא תקינה") from exc


def hebrew_to_gregorian(year: int, month: int, day: int, from_year=None) -> dict:
    """ממיר בחירה מהבורר. אדר ב׳ בשנה פשוטה הופך לאדר, ויום מעבר לאורך החודש נחתך.

    ``from_year`` הוא השנה שאליה שייכת רשימת החודשים שעל המסך. בלי זה אי אפשר
    להבדיל בין אדר פשוט לאדר א׳ — שניהם חודש 12.
    """
    if isinstance(year, bool) or isinstance(month, bool) or isinstance(day, bool):
        raise HebrewDateError("תאריך עברי לא תקין")
    try:
        year = int(year)
        month = int(month)
        day = int(day)
    except (TypeError, ValueError) as exc:
        raise HebrewDateError("תאריך עברי לא תקין") from exc
    if year < 1:
        raise HebrewDateError("שנה עברית לא תקינה")
    try:
        heb_year = Year(year)
    except Exception as exc:
        raise HebrewDateError("שנה עברית לא תקינה") from exc

    adjusted = False
    if from_year not in (None, ""):
        if isinstance(from_year, bool):
            raise HebrewDateError("שנה עברית לא תקינה")
        try:
            src_year = int(from_year)
        except (TypeError, ValueError) as exc:
            raise HebrewDateError("שנה עברית לא תקינה") from exc
        if src_year < 1:
            raise HebrewDateError("שנה עברית לא תקינה")
        # אדר פשוט (12 בשנה לא מעוברת) → אדר ב׳ כשהיעד מעוברת.
        # אדר א׳ נשאר 12, ובשנה פשוטה זה כבר «אדר».
        if (not _leap_year(src_year)) and heb_year.leap and month == 12:
            month = 13
            adjusted = True
    if month == 13 and not heb_year.leap:
        month = 12
        adjusted = True
    last_month = 13 if heb_year.leap else 12
    if month < 1 or month > last_month:
        raise HebrewDateError("חודש עברי לא תקין")
    if day < 1:
        raise HebrewDateError("יום עברי לא תקין")
    length = len(Month(year, month))
    if day > length:
        day = length
        adjusted = True
    try:
        hebrew = HebrewDate(year, month, day)
    except Exception as exc:
        raise HebrewDateError("תאריך עברי לא תקין") from exc
    greg = hebrew.to_greg()
    return _describe(year, month, day, date(greg.year, greg.month, greg.day), adjusted)


_MONTH_ALIASES = {
    "ניסן": 1,
    "אייר": 2,
    "סיון": 3,
    "סיוון": 3,
    "תמוז": 4,
    "אב": 5,
    "מנחם אב": 5,
    "אלול": 6,
    "תשרי": 7,
    "חשון": 8,
    "חשוון": 8,
    "מרחשון": 8,
    "מרחשוון": 8,
    "כסלו": 9,
    "כסליו": 9,
    "טבת": 10,
    "שבט": 11,
    "אדר": 12,
    "אדר א": "adar1",
    "אדר ב": "adar2",
    "אדר ראשון": "adar1",
    "אדר שני": "adar2",
    "אדר הראשון": "adar1",
    "אדר השני": "adar2",
}

_MARKS = str.maketrans("", "", "\"'`״׳\u05f3\u05f4")


def _bare_hebrew(text: str) -> str:
    cleaned = text.translate(_MARKS)
    cleaned = re.sub(r"[\u0591-\u05c7]", "", cleaned)
    cleaned = cleaned.replace("־", " ")
    return " ".join(cleaned.split())


def _gematria(token: str) -> int | None:
    from hebrew_numbers import gematria_to_int

    if not token or any(ch.isdigit() for ch in token):
        return None
    if not all("א" <= ch <= "ת" for ch in token):
        return None
    return gematria_to_int(token)


def _day_number(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    value = _gematria(token)
    if value is None or not 1 <= value <= 30:
        return None
    return value


def _year_number(token: str) -> int | None:
    if token.isdigit():
        value = int(token)
    else:
        letters = token[1:] if token.startswith("ה") and len(token) > 1 else token
        value = _gematria(letters)
        if value is None:
            return None
    if 700 <= value <= 999:
        return 5000 + value
    if 5000 <= value <= 5999:
        return value
    return None


def _resolve_month(key, year: int) -> int:
    leap = Year(year).leap
    if key == "adar1":
        return 12
    if key == "adar2":
        return 13 if leap else 12
    if key == 12:
        return 13 if leap else 12
    return int(key)


def _gregorian_from_hebrew(year: int, month: int, day: int) -> date:
    length = len(Month(year, month))
    if day < 1 or day > length:
        raise HebrewDateError("התאריך לא קיים בחודש הזה.")
    hebrew = HebrewDate(year, month, day)
    greg = hebrew.to_greg()
    return date(greg.year, greg.month, greg.day)


def parse_hebrew_date_text(text: str, today: date) -> date:
    """יום וחודש עבריים. בלי שנה — המופע הקרוב מהיום והלאה.

    גרשיים לא חובה. חשון/חשוון/מרחשוון, ואדר א׳/ב׳, מתקבלים.
    אדר סתם בשנה מעוברת הוא אדר ב׳. אדר א׳ או ב׳ בשנה פשוטה הוא אדר.
    """
    bare = _bare_hebrew(text or "")
    tokens = [token for token in bare.split() if token not in {"חודש", "בחודש"}]
    if len(tokens) < 2:
        raise HebrewDateError("התאריך לא ברור. למשל י״ג חשון.")
    day = _day_number(tokens[0])
    if day is None:
        raise HebrewDateError("היום לא ברור. למשל י״ג חשון.")
    rest = tokens[1:]
    year = None
    if len(rest) >= 2:
        parsed_year = _year_number(rest[-1])
        if parsed_year is not None:
            year = parsed_year
            rest = rest[:-1]
    if rest and rest[0] == "ב":
        rest = rest[1:]
    elif rest and rest[0].startswith("ב") and len(rest[0]) > 1:
        rest = [rest[0][1:], *rest[1:]]
    month_name = " ".join(rest).strip()
    month_name = month_name.replace("אדר 1", "אדר א").replace("אדר 2", "אדר ב")
    key = _MONTH_ALIASES.get(month_name)
    if key is None:
        raise HebrewDateError("החודש לא מוכר. למשל חשון, חשוון או אדר.")
    if year is not None:
        try:
            return _gregorian_from_hebrew(year, _resolve_month(key, year), day)
        except HebrewDateError:
            raise
        except Exception as exc:
            raise HebrewDateError("התאריך לא קיים. למשל י״ג חשון.") from exc
    hebrew_today = GregorianDate(today.year, today.month, today.day).to_heb()
    for candidate in range(hebrew_today.year, hebrew_today.year + 8):
        try:
            found = _gregorian_from_hebrew(candidate, _resolve_month(key, candidate), day)
        except HebrewDateError:
            continue
        except Exception:
            continue
        if found >= today:
            return found
    raise HebrewDateError("התאריך לא קיים. למשל י״ג חשון.")


def hebrew_year_options(start: int, end: int) -> list[dict]:
    try:
        start = int(start)
        end = int(end)
    except (TypeError, ValueError) as exc:
        raise HebrewDateError("טווח שנים לא תקין") from exc
    if end < start or end - start > MAX_YEAR_SPAN:
        raise HebrewDateError("טווח שנים לא תקין")
    options = []
    for year in range(start, end + 1):
        try:
            leap = Year(year).leap
        except Exception as exc:
            raise HebrewDateError("שנה עברית לא תקינה") from exc
        options.append({
            "year": year,
            "label": format_hebrew_year(year),
            "leap": leap,
        })
    return options
