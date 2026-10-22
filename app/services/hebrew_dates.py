"""המרה דו-כיוונית לועזי ↔ עברי לבחירת תאריך במודל.

חודש 1 = ניסן, 12 = אדר (או אדר א׳ בשנה מעוברת), 13 = אדר ב׳.
בשנה לא מעוברת אין חודש 13. חשוון וכסלו הם 29 או 30 לפי השנה (pyluach).
"""
from __future__ import annotations

from datetime import date

from pyluach.dates import GregorianDate, HebrewDate
from pyluach.hebrewcal import Month, Year

from app.services.hebrew_format import format_hebrew_date, format_hebrew_year
from app.services.recurrence import HEBREW_DAYS, HEBREW_MONTHS

MAX_YEAR_SPAN = 500


class HebrewDateError(ValueError):
    """תאריך עברי או טווח שנים לא תקינים."""


def _picker_month_name(leap: bool, month: int) -> str:
    if leap and month == 12:
        return "אדר א׳"
    if leap and month == 13:
        return "אדר ב׳"
    return HEBREW_MONTHS.get(month, "")


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


def hebrew_to_gregorian(year: int, month: int, day: int) -> dict:
    """ממיר בחירה מהבורר. אדר ב׳ בשנה פשוטה הופך לאדר, ויום מעבר לאורך החודש נחתך."""
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
