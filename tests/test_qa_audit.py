"""אודיט QA — מקרי קצה שאושרו בקוד.

הטענות כאן מתארות התנהגות סבירה. באג מאושר מסומן
``pytest.mark.xfail`` עם סיבה, כדי ש-CI יישאר ירוק עד התיקון.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.reminders.due import telegram_due
from app.reminders.schedule import fire_at, reminder_message
from app.reminders.worker import process_due_reminders

TZ = ZoneInfo("Asia/Jerusalem")
REPO = Path(__file__).resolve().parent.parent

SAMPLE = {
    "title": "אודיט",
    "gregorian_date": "2026-06-15",
    "hebrew_date": "כ סיון",
}


def _person(client, name="דני", chat_id="1001", **extra):
    payload = {"name": name, "telegram_chat_id": chat_id, **extra}
    response = client.post("/api/reminder-people", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _event(client, **extra):
    payload = {**SAMPLE, **extra}
    response = client.post("/api/events", json=payload)
    return response


# --- התנהגות מאושרת כתקינה -----------------------------------------------


def test_all_day_reminder_fires_at_default_0900(client, app):
    """אירוע בלי שעה: בסיס 09:00 שעון ירושלים (REMINDER_DEFAULT_TIME)."""
    person = _person(client)
    created = _event(
        client,
        title="כל היום",
        gregorian_date="2026-01-20",
        time=None,
        reminders=[{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    winter = fire_at(
        {"gregorian_date": "2026-01-20", "time": None},
        0,
        tz=TZ,
        default_time="09:00",
    )
    assert winter == datetime(2026, 1, 20, 9, 0, tzinfo=TZ)
    assert winter.utcoffset() == timedelta(hours=2)

    evening = fire_at(
        {"gregorian_date": "2026-01-20", "time": None},
        720,
        tz=TZ,
        default_time="09:00",
    )
    assert evening == datetime(2026, 1, 19, 21, 0, tzinfo=TZ)

    with app.app_context():
        assert telegram_due(now=datetime(2026, 1, 20, 8, 59, tzinfo=TZ)) == []
        due = telegram_due(now=datetime(2026, 1, 20, 9, 0, tzinfo=TZ))
        assert len(due) == 1
        assert due[0]["event_id"] == event_id


def test_dst_all_day_stays_local_0900():
    summer = fire_at(
        {"gregorian_date": "2026-07-20", "time": ""},
        0,
        tz=TZ,
        default_time="09:00",
    )
    assert summer.hour == 9
    assert summer.utcoffset() == timedelta(hours=3)


def test_multi_day_reminder_uses_start_not_end(client, app):
    person = _person(client)
    created = _event(
        client,
        title="טיול",
        gregorian_date="2026-08-01",
        end_date="2026-08-05",
        time="18:00",
        reminders=[{"offset_minutes": 60, "recipient_ids": [person["id"]]}],
    )
    assert created.status_code == 200
    with app.app_context():
        assert telegram_due(now=datetime(2026, 8, 1, 16, 59, tzinfo=TZ)) == []
        due = telegram_due(now=datetime(2026, 8, 1, 17, 0, tzinfo=TZ))
        assert len(due) == 1
        assert "2026-08-01 18:00" in due[0]["text"]
        later = telegram_due(now=datetime(2026, 8, 5, 17, 0, tzinfo=TZ))
        assert later[0]["event_id"] == created.get_json()["id"]


def test_end_before_start_rejected(client):
    response = _event(
        client,
        gregorian_date="2026-05-10",
        end_date="2026-05-09",
    )
    assert response.status_code == 400
    assert "סיום" in response.get_json()["error"]


def test_chat_id_and_person_name_validation(client):
    assert client.post(
        "/api/reminder-people",
        json={"name": "א", "telegram_chat_id": "12ab"},
    ).status_code == 400
    assert client.post(
        "/api/reminder-people",
        json={"name": "א", "telegram_chat_id": "+123"},
    ).status_code == 400
    ok = client.post(
        "/api/reminder-people",
        json={"name": "קבוצה", "telegram_chat_id": "-1001234567890"},
    )
    assert ok.status_code == 201
    long_name = client.post(
        "/api/reminder-people",
        json={"name": "א" * 81},
    )
    assert long_name.status_code == 400


def test_telegram_reminder_is_plain_text_not_html():
    text = reminder_message(
        {"title": "<b>xss</b>", "hebrew_date": "א", "description": "<img>"},
        0,
        datetime(2026, 1, 1, 9, 0, tzinfo=TZ),
    )
    assert "<b>xss</b>" in text
    source = (REPO / "app" / "reminders" / "telegram.py").read_text(encoding="utf-8")
    send_fn = source.split("def send_message", 1)[1].split("def ", 1)[0]
    assert "parse_mode" not in send_fn


def test_calendar_chips_escape_user_title():
    render = (REPO / "app" / "static" / "js" / "calendar" / "event-render.js").read_text(
        encoding="utf-8"
    )
    assert "escapeHtml(event.title" in render
    agenda = (REPO / "app" / "static" / "js" / "calendar" / "day-agenda.js").read_text(
        encoding="utf-8"
    )
    assert "escapeHtml(ev.title" in agenda


def test_deleted_occurrence_does_not_fire_reminder(client, app):
    person = _person(client, chat_id="88")
    created = _event(
        client,
        gregorian_date="2026-01-31",
        time="10:00",
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
        reminders=[{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
    )
    event_id = created.get_json()["id"]
    removed = client.delete(
        f"/api/events/{event_id}?scope=occurrence&occurrence_date=2026-02-28"
    )
    assert removed.status_code == 200
    with app.app_context():
        assert telegram_due(now=datetime(2026, 2, 28, 10, 0, tzinfo=TZ)) == []
        jan = telegram_due(now=datetime(2026, 1, 31, 10, 0, tzinfo=TZ))
        assert len(jan) == 1


def test_range_requires_both_bounds_and_order(client):
    _event(client)
    assert client.get("/api/events?from=2026-01-01").status_code == 400
    assert client.get("/api/events?from=2026-12-31&to=2026-01-01").status_code == 400


def test_recurring_monthly_31_and_multi_day_span(client):
    created = _event(
        client,
        title="משכורת",
        gregorian_date="2026-01-31",
        end_date="2026-02-02",
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
    )
    assert created.status_code == 200
    rows = client.get("/api/events?from=2026-01-01&to=2026-04-30").get_json()
    mine = [row for row in rows if row["title"] == "משכורת"]
    assert [row["gregorian_date"] for row in mine] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
    ]
    assert mine[0]["end_date"] == "2026-02-02"
    assert mine[1]["end_date"] == "2026-03-02"


def test_update_without_reminders_key_keeps_rows(client):
    person = _person(client)
    created = _event(
        client,
        reminders=[{"offset_minutes": 15, "recipient_ids": [person["id"]]}],
    )
    event_id = created.get_json()["id"]
    client.put(
        f"/api/events/{event_id}",
        json={**SAMPLE, "title": "עודכן"},
    )
    body = client.get(f"/api/events/{event_id}").get_json()
    assert body["title"] == "עודכן"
    assert body["reminders"][0]["offset_minutes"] == 15


def test_browser_due_works_without_chat_id(client, app):
    from app.reminders.due import browser_due

    person = _person(client, chat_id="")
    created = _event(
        client,
        gregorian_date="2026-04-01",
        time="09:00",
        reminders=[{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
    )
    event_id = created.get_json()["id"]
    now = datetime(2026, 4, 1, 9, 0, tzinfo=TZ)
    with app.app_context():
        assert telegram_due(now=now) == []
        visible = browser_due(now=now, within_seconds=90, grace_seconds=900)
        assert [row["event_id"] for row in visible] == [event_id]


# --- באגים מאושרים --------------------------------------------------------


@pytest.mark.xfail(reason="POST מקבל תאריך לועזי לא תקין בלי end_date — אין אימות YYYY-MM-DD")
def test_invalid_gregorian_date_is_rejected(client):
    response = _event(client, gregorian_date="2026-02-31", hebrew_date="א")
    assert response.status_code == 400
    garbage = _event(client, gregorian_date="not-a-date", hebrew_date="א")
    assert garbage.status_code == 400


@pytest.mark.xfail(reason="תאריך פסול שנשמר מפיל GET /api/events?from=&to= ב-500 (RecurrenceError)")
def test_invalid_stored_date_does_not_break_range_query(client, app):
    created = _event(client, gregorian_date="2026-02-31", hebrew_date="א")
    if created.status_code != 200:
        pytest.skip("היצירה כבר נדחית — הטווח בטוח")
    ranged = client.get("/api/events?from=2026-02-01&to=2026-02-28")
    assert ranged.status_code == 200
    assert isinstance(ranged.get_json(), list)


@pytest.mark.xfail(reason="כותרת של רווחים בלבד עוברת את בדיקת השדות החובה")
def test_whitespace_title_is_rejected(client):
    response = _event(client, title="   ")
    assert response.status_code == 400


@pytest.mark.xfail(reason="שעה לא תקינה נשמרת, ותזכורת נופלת בשקט ל-09:00")
def test_invalid_time_is_rejected(client):
    response = _event(client, time="25:99")
    assert response.status_code == 400
    bad = _event(client, time="noon")
    assert bad.status_code == 400


@pytest.mark.xfail(reason="DELETE לאירוע שלא קיים מחזיר 200 — delete_event לא בודק rowcount")
def test_delete_missing_event_is_404(client):
    response = client.delete("/api/events/999999")
    assert response.status_code == 404


@pytest.mark.xfail(reason="כישלון בצ'אט השני לא מסמן sent, והסבב הבא שולח שוב לראשון")
def test_partial_telegram_failure_does_not_duplicate_first_chat(client, app):
    first = _person(client, name="א", chat_id="111")
    second = _person(client, name="ב", chat_id="222")
    created = _event(
        client,
        gregorian_date="2026-03-01",
        time="09:00",
        reminders=[{
            "offset_minutes": 0,
            "recipient_ids": [first["id"], second["id"]],
        }],
    )
    assert created.status_code == 200
    sent = []

    def flaky(token, chat_id, text):
        sent.append(chat_id)
        if chat_id == "222":
            raise RuntimeError("telegram down")
        return True

    now = datetime(2026, 3, 1, 9, 0, tzinfo=TZ)
    with app.app_context():
        assert process_due_reminders(now=now, send=flaky, token="t") == 0
        assert process_due_reminders(now=now, send=flaky, token="t") == 0
    assert sent.count("111") == 1
    assert sent.count("222") >= 1


@pytest.mark.xfail(reason="שינוי שעת אירוע אחרי שליחה לא מאפס sent_at — התזכורת לא נשלחת מחדש")
def test_reschedule_after_send_refires(client, app):
    from app.reminders.repository import mark_reminder_sent

    person = _person(client, chat_id="333")
    created = _event(
        client,
        gregorian_date="2026-06-01",
        time="10:00",
        reminders=[{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
    )
    event_id = created.get_json()["id"]
    with app.app_context():
        due = telegram_due(now=datetime(2026, 6, 1, 10, 0, tzinfo=TZ))
        assert due
        mark_reminder_sent(due[0]["id"])
    moved = client.put(
        f"/api/events/{event_id}",
        json={**SAMPLE, "time": "18:00"},
    )
    assert moved.status_code == 200
    with app.app_context():
        again = telegram_due(now=datetime(2026, 6, 1, 18, 0, tzinfo=TZ))
        assert len(again) == 1
        assert again[0]["event_id"] == event_id


@pytest.mark.xfail(reason="החלפת נמענים באירוע חוזר לא מוחקת reminder_sends — נמען חדש מפספס מופע שכבר נשלח")
def test_recipient_change_on_recurring_notifies_new_person(client, app):
    from app.reminders.repository import mark_reminder_sent

    old = _person(client, name="ישן", chat_id="444")
    created = _event(
        client,
        gregorian_date="2026-01-31",
        time="10:00",
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
        reminders=[{"offset_minutes": 0, "recipient_ids": [old["id"]]}],
    )
    event_id = created.get_json()["id"]
    with app.app_context():
        due = telegram_due(now=datetime(2026, 1, 31, 10, 0, tzinfo=TZ))
        mark_reminder_sent(due[0]["id"], occurrence_date=due[0]["occurrence_date"])

    new = _person(client, name="חדש", chat_id="555")
    updated = client.put(
        f"/api/events/{event_id}",
        json={
            **SAMPLE,
            "gregorian_date": "2026-01-31",
            "time": "10:00",
            "recurrence_freq": "monthly",
            "recurrence_calendar": "gregorian",
            "recurrence_count": 3,
            "reminders": [{"offset_minutes": 0, "recipient_ids": [old["id"], new["id"]]}],
        },
    )
    assert updated.status_code == 200
    with app.app_context():
        due = telegram_due(now=datetime(2026, 1, 31, 10, 0, tzinfo=TZ))
        chats = {chat for row in due for chat in row["chat_ids"]}
        assert "555" in chats


@pytest.mark.xfail(reason="תזכורת על אירוע חד-פעמי מלפני שנים נשלחת מיד כשה-worker חוזר")
def test_stale_one_off_reminder_is_not_due_years_later(client, app):
    person = _person(client, chat_id="666")
    created = _event(
        client,
        title="ישן מאוד",
        gregorian_date="2020-01-01",
        time="09:00",
        reminders=[{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
    )
    assert created.status_code == 200
    with app.app_context():
        due = telegram_due(now=datetime(2026, 6, 1, 12, 0, tzinfo=TZ))
        assert due == []


@pytest.mark.xfail(reason="שמירת רשת משמרות ומשמרת ידנית לא בודקות household_settings.shifts_enabled")
def test_shift_writes_rejected_when_feature_disabled(client):
    assert client.get("/api/shifts/settings").get_json()["enabled"] is False
    person = _person(client, name="אביחי", color="cyan")
    week = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-18", "label": "בוקר"}],
    })
    assert week.status_code == 400
    manual = _event(
        client,
        is_shift=True,
        shift_person_id=person["id"],
        shift_label="בוקר",
    )
    assert manual.status_code == 400


@pytest.mark.xfail(reason="/api/calendar/<year>/<month> לא מאמת חודש — 13 מחזיר 500")
def test_calendar_month_rejects_invalid_month(client):
    response = client.get("/api/calendar/2026/13")
    assert response.status_code == 400


@pytest.mark.xfail(reason="חיפוש לפי טווח תאריכים לא מרחיב מופעים — 28.2 של סדרת 31.1 לא נמצא")
def test_search_finds_future_occurrence_date(client):
    created = _event(
        client,
        title="יום הולדת אודיט",
        gregorian_date="2026-01-31",
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
    )
    assert created.status_code == 200
    by_date = client.get("/api/events/advanced-search", query_string={
        "advanced_search": '{"startDate":"2026-02-28","endDate":"2026-02-28"}',
    }).get_json()
    titles = {row.get("title") for row in by_date}
    assert "יום הולדת אודיט" in titles


@pytest.mark.xfail(reason="מחיקת אדם משאירה recipient_ids ומשמרות יתומות בלי FK")
def test_delete_person_strips_recipient_ids(client):
    person = _person(client, chat_id="777")
    created = _event(
        client,
        reminders=[{"offset_minutes": 5, "recipient_ids": [person["id"]]}],
    )
    event_id = created.get_json()["id"]
    assert client.delete(f"/api/reminder-people/{person['id']}").status_code == 200
    body = client.get(f"/api/events/{event_id}").get_json()
    leftover = [rid for item in body["reminders"] for rid in item["recipient_ids"]]
    assert person["id"] not in leftover


@pytest.mark.xfail(reason="רשימת האירועים מזריקה title/description ל-innerHTML בלי escapeHtml")
def test_events_list_escapes_user_text():
    html = (REPO / "app" / "templates" / "events_list.html").read_text(encoding="utf-8")
    assert "escapeHtml(event.title)" in html
    assert "escapeHtml(event.description)" in html


@pytest.mark.xfail(reason="צ'יפי חיפוש מתקדם מזריקים title/description ל-innerHTML")
def test_filter_chips_escape_search_text():
    html = (REPO / "app" / "templates" / "events_list.html").read_text(encoding="utf-8")
    assert "escapeHtml(searchParams.title)" in html


@pytest.mark.xfail(reason="ייבוא לא מאמת פורמט תאריך — אותה פרצה כמו POST")
def test_import_rejects_invalid_gregorian_date(client):
    response = client.post(
        "/api/events/import?mode=merge",
        json={
            "events": [{
                "title": "יבוא שבור",
                "gregorian_date": "2026-02-31",
                "hebrew_date": "א",
            }],
            "colors": [],
        },
    )
    assert response.status_code == 400
    titles = {row["title"] for row in client.get("/api/events").get_json()}
    assert "יבוא שבור" not in titles


@pytest.mark.xfail(reason="אין מגבלת אורך לכותרת/תיאור אירוע (לאדם יש מגבלה 80)")
def test_overlong_title_is_rejected(client):
    response = _event(client, title="א" * 2001)
    assert response.status_code == 400


@pytest.mark.xfail(reason="PUT scope=occurrence בולע reminders בלי שגיאה ובלי לשמור")
def test_occurrence_update_rejects_or_applies_reminders(client):
    person = _person(client)
    created = _event(
        client,
        gregorian_date="2026-01-10",
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=3,
        reminders=[{"offset_minutes": 10, "recipient_ids": [person["id"]]}],
    )
    event_id = created.get_json()["id"]
    response = client.put(
        f"/api/events/{event_id}",
        json={
            "title": "רק הפעם",
            "gregorian_date": "2026-02-10",
            "hebrew_date": "א",
            "scope": "occurrence",
            "occurrence_date": "2026-02-10",
            "reminders": [{"offset_minutes": 60, "recipient_ids": [person["id"]]}],
        },
    )
    assert response.status_code == 400


@pytest.mark.xfail(reason="חיפוש מתקדם משתמש ב-datetime.now() נאיבי, לא ב-Asia/Jerusalem")
def test_advanced_search_uses_jerusalem_today():
    source = (REPO / "app" / "api" / "events.py").read_text(encoding="utf-8")
    assert "reminder_timezone" in source
