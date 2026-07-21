"""עזרי תצוגה לתאריך עברי — שנה באותיות (גימטריה) במקום מספרים."""
from __future__ import annotations

import re

from hebrew_numbers import int_to_gematria

# "ח אב 5786" / "ח אב תשפ\"ו"
_NUMERIC_YEAR_SUFFIX = re.compile(r"^(?P<head>.*\S)\s+(?P<year>\d{3,4})$")


def format_hebrew_year(year: int, *, with_heh_prefix: bool = False) -> str:
    """5786 -> תשפ\"ו  |  עם קידומת: ה'תשפ\"ו (לכותרת חודש)."""
    year_letters = int_to_gematria(int(year) % 5000, gershayim=True)
    if with_heh_prefix:
        return f"ה'{year_letters}"
    return year_letters


def format_hebrew_date(day_label: str, month_name: str, year: int) -> str:
    """בונה מחרוזת תאריך מלאה עם שנה באותיות."""
    return f"{day_label} {month_name} {format_hebrew_year(year)}".strip()


def normalize_hebrew_date_text(hebrew_date: str | None) -> str:
    """ממיר שנה מספרית בסוף המחרוזת לאותיות. אם כבר אותיות — מחזיר כמו שזה."""
    if not hebrew_date:
        return ""
    text = str(hebrew_date).strip()
    match = _NUMERIC_YEAR_SUFFIX.match(text)
    if not match:
        return text
    return f"{match.group('head')} {format_hebrew_year(int(match.group('year')))}"
