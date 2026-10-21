"""בדיקות JewishCalendarService על תאריכים ידועים."""
from datetime import date

from app.services.jewish_calendar import JewishCalendarService


def test_purim_2025_major_holiday():
    events = JewishCalendarService.get_holidays(date(2025, 3, 14))
    holiday_names = [e["name"] for e in events if e["type"] == "holiday"]
    assert holiday_names == ["פורים"]


def test_shabbat_vayikra_parasha_2025():
    events = JewishCalendarService.get_holidays(date(2025, 4, 5))
    parasha_events = [e for e in events if e["type"] == "parasha"]
    assert len(parasha_events) == 1
    assert parasha_events[0]["name"] == "פרשת ויקרא"
    assert parasha_events[0]["color"] == "#4A90E2"


def test_get_parasha_only_on_shabbat():
    parasha = JewishCalendarService.get_parasha(date(2025, 4, 5))
    assert parasha is not None
    assert parasha["name"] == "ויקרא"
    assert parasha["type"] == "parasha"

    assert JewishCalendarService.get_parasha(date(2025, 4, 4)) is None
