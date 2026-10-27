"""סבב QA שני: תזכורת למופע כל-היום, סדרה שנגמרה, ושמות אדר."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.reminders.schedule import fire_at, occurrence_start
from app.services.jewish_calendar import JewishCalendarService
from app.services.recurrence import hebrew_display

TZ = ZoneInfo("Asia/Jerusalem")


def test_finished_series_has_no_next_occurrence():
    ended = {
        "gregorian_date": "2026-01-01",
        "time": "10:00",
        "recurrence_freq": "monthly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 2,
    }
    after = datetime(2026, 3, 1, 12, 0, tzinfo=TZ)
    assert occurrence_start(ended, now=after, tz=TZ) is None
    assert fire_at(ended, 30, now=after, tz=TZ) is None
    # 1.2 10:00 כבר עבר — אין מופע שלישי
    passed = datetime(2026, 2, 1, 11, 0, tzinfo=TZ)
    assert occurrence_start(ended, now=passed, tz=TZ) is None
    still = datetime(2026, 2, 1, 9, 0, tzinfo=TZ)
    nxt = occurrence_start(ended, now=still, tz=TZ)
    assert nxt is not None
    assert nxt.date().isoformat() == "2026-02-01"
    assert nxt.hour == 10


def test_all_day_occurrence_reminder_ignores_series_clock(client, app):
    person = client.post(
        "/api/reminder-people",
        json={"name": "דני", "telegram_chat_id": "777"},
    )
    assert person.status_code == 201
    person_id = person.get_json()["id"]
    created = client.post(
        "/api/events",
        json={
            "title": "סדרה",
            "gregorian_date": "2026-05-01",
            "hebrew_date": "א",
            "time": "18:00",
            "recurrence_freq": "monthly",
            "recurrence_calendar": "gregorian",
            "recurrence_count": 3,
            "reminders": [{"offset_minutes": 0, "recipient_ids": [person_id]}],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]
    edited = client.put(
        f"/api/events/{event_id}",
        json={
            "scope": "occurrence",
            "occurrence_date": "2026-06-01",
            "title": "סדרה",
            "gregorian_date": "2026-06-01",
            "hebrew_date": "א",
            "time": None,
            "description": "",
        },
    )
    assert edited.status_code == 200

    from app.reminders.due import telegram_due

    morning = datetime(2026, 6, 1, 9, 0, tzinfo=TZ)
    early = datetime(2026, 6, 1, 8, 59, tzinfo=TZ)
    with app.app_context():
        assert telegram_due(now=early) == []
        due = telegram_due(now=morning)
    assert len(due) == 1
    assert due[0]["occurrence_date"] == "2026-06-01"
    assert "09:00" in due[0]["text"]
    assert "18:00" not in due[0]["text"]


def test_hebrew_service_month_names_follow_nisan():
    # א׳ באב תשפ״ו = 15.7.2026. המפה הישנה (תשרי=1) הציגה את אב כשבט.
    text = JewishCalendarService.get_hebrew_date(date(2026, 7, 15))
    assert "אב" in text
    assert "תשרי" not in text
    assert "שבט" not in text
    # י״א באדר א׳ תשפ״ד = 10.2.2024, וא׳ באדר ב׳ = 11.3.2024
    assert "אדר א׳" in hebrew_display(date(2024, 2, 10))
    assert "אדר ב׳" in hebrew_display(date(2024, 3, 11))
    assert "אדר א׳" not in hebrew_display(date(2025, 3, 1))
    assert hebrew_display(date(2025, 3, 1)).split()[1] == "אדר"
