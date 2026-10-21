"""בדיקות לעיצוב שנה עברית באותיות."""
from app.services.hebrew_format import (
    format_hebrew_date,
    format_hebrew_year,
    normalize_hebrew_date_text,
)


def test_format_hebrew_year_5786():
    assert format_hebrew_year(5786) == "תשפ״ו"


def test_format_hebrew_year_with_heh_prefix():
    assert format_hebrew_year(5786, with_heh_prefix=True) == "ה'תשפ״ו"


def test_format_hebrew_date_full_string():
    assert format_hebrew_date("ח", "אב", 5786) == "ח אב תשפ״ו"


def test_normalize_numeric_year_suffix():
    assert normalize_hebrew_date_text("ח אב 5786") == "ח אב תשפ״ו"


def test_normalize_leaves_letter_year_unchanged():
    original = "ח אב תשפ״ו"
    assert normalize_hebrew_date_text(original) == original


def test_normalize_empty():
    assert normalize_hebrew_date_text(None) == ""
    assert normalize_hebrew_date_text("") == ""
