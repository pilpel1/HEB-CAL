"""תזכורות: offsets, due, אנשים, וסכמה על DB קיים."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.reminders.schedule import (
    OffsetError,
    custom_offset_minutes,
    fire_at,
    is_due,
    occurrence_start,
    offset_label,
    parse_reminders_payload,
)
from app.reminders.telegram import chat_id_reply, consume_updates, start_chat_id

TZ = ZoneInfo("Asia/Jerusalem")

SAMPLE = {
    "title": "תזכורת בדיקה",
    "gregorian_date": "2026-06-01",
    "hebrew_date": "טו סיון",
    "time": "10:00",
}


def test_custom_offsets_and_presets():
    assert custom_offset_minutes(15, "minutes") == 15
    assert custom_offset_minutes(2, "hours") == 120
    assert custom_offset_minutes(3, "days") == 4320
    assert custom_offset_minutes(1, "שעות") == 60
    assert custom_offset_minutes("4", "days") == 4 * 1440
    with pytest.raises(OffsetError):
        custom_offset_minutes(0, "minutes")
    with pytest.raises(OffsetError):
        custom_offset_minutes(-2, "hours")
    with pytest.raises(OffsetError):
        custom_offset_minutes(1, "weeks")
    with pytest.raises(OffsetError):
        custom_offset_minutes(1.5, "hours")
    with pytest.raises(OffsetError):
        custom_offset_minutes(400, "days")

    parsed = parse_reminders_payload(
        [
            {"offset_minutes": 0, "recipient_ids": [1]},
            {"amount": 2, "unit": "hours", "recipient_ids": [2, 2]},
            {"offset_minutes": 120, "recipient_ids": [1]},
        ],
        {1, 2},
    )
    assert parsed == [
        {"offset_minutes": 0, "recipient_ids": [1]},
        {"offset_minutes": 120, "recipient_ids": [2, 1]},
    ]
    with pytest.raises(OffsetError, match="נמען לא קיים"):
        parse_reminders_payload([{"offset_minutes": 5, "recipient_ids": [9]}], {1})


def test_fire_time_default_jerusalem_and_no_recurrence():
    all_day = {"gregorian_date": "2026-01-15", "time": None}
    winter = fire_at(all_day, 0, tz=TZ, default_time="09:00")
    assert winter.hour == 9 and winter.minute == 0
    assert winter.utcoffset() == timedelta(hours=2)

    summer = fire_at({"gregorian_date": "2026-07-15", "time": ""}, 0, tz=TZ, default_time="09:00")
    assert summer.hour == 9
    assert summer.utcoffset() == timedelta(hours=3)

    timed = {"gregorian_date": "2026-04-02", "time": "18:40", "hebrew_date": "טו ניסן"}
    start = occurrence_start(
        timed,
        now=datetime(2030, 1, 1, tzinfo=TZ),
        tz=TZ,
        default_time="09:00",
    )
    assert start == datetime(2026, 4, 2, 18, 40, tzinfo=TZ)
    fire = fire_at(timed, 30, tz=TZ, default_time="09:00")
    assert fire == datetime(2026, 4, 2, 18, 10, tzinfo=TZ)
    assert is_due(fire, datetime(2026, 4, 2, 18, 10, tzinfo=TZ), None)
    assert not is_due(fire, datetime(2026, 4, 2, 18, 9, tzinfo=TZ), None)
    assert not is_due(fire, datetime(2026, 4, 2, 18, 30, tzinfo=TZ), "2026-04-02T15:10:00Z")
    assert offset_label(0) == "בזמן"
    assert offset_label(90) == "90 דקות"


def test_schema_migration_keeps_existing_events(tmp_path):
    from app.reminders.repository import ensure_reminder_schema

    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            gregorian_date TEXT NOT NULL,
            hebrew_date TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO events (title, gregorian_date, hebrew_date) VALUES ('ישן', '2020-01-01', 'א')"
    )
    conn.execute("CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER)")
    conn.commit()

    ensure_reminder_schema(conn)
    ensure_reminder_schema(conn)
    conn.commit()

    assert conn.execute("SELECT title FROM events").fetchone()["title"] == "ישן"
    reminder_cols = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
    assert {"offset_minutes", "recipient_ids", "sent_at"} <= reminder_cols
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reminder_people'"
    ).fetchone()


def _person(client, name="דני", chat_id="4242"):
    response = client.post(
        "/api/reminder-people",
        json={"name": name, "telegram_chat_id": chat_id},
    )
    assert response.status_code == 201
    return response.get_json()


def test_event_reminders_api_round_trip(client):
    person = _person(client)
    other = _person(client, name="נועה", chat_id="")

    created = client.post(
        "/api/events",
        json={
            **SAMPLE,
            "reminders": [
                {"offset_minutes": 15, "recipient_ids": [person["id"]]},
                {"amount": 2, "unit": "hours", "recipient_ids": [person["id"], other["id"]]},
            ],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    body = client.get(f"/api/events/{event_id}").get_json()
    assert [(item["offset_minutes"], item["recipient_ids"]) for item in body["reminders"]] == [
        (15, [person["id"]]),
        (120, [person["id"], other["id"]]),
    ]

    kept = client.put(
        f"/api/events/{event_id}",
        json={**SAMPLE, "title": "בלי לגעת בתזכורות"},
    )
    assert kept.status_code == 200
    still = client.get(f"/api/events/{event_id}").get_json()
    assert len(still["reminders"]) == 2
    assert still["title"] == "בלי לגעת בתזכורות"

    cleared = client.put(f"/api/events/{event_id}", json={**SAMPLE, "reminders": []})
    assert cleared.status_code == 200
    assert client.get(f"/api/events/{event_id}").get_json()["reminders"] == []

    rejected = client.post(
        "/api/events",
        json={**SAMPLE, "title": "לא נוצר", "reminders": [{"offset_minutes": -5}]},
    )
    assert rejected.status_code == 400
    titles = {row["title"] for row in client.get("/api/events").get_json()}
    assert "לא נוצר" not in titles

    unknown = client.post(
        "/api/events",
        json={**SAMPLE, "title": "נמען זר", "reminders": [{"offset_minutes": 5, "recipient_ids": [999]}]},
    )
    assert unknown.status_code == 400
    assert "נמען לא קיים" in unknown.get_json()["error"]


def test_due_query_respects_sent_default_time_and_browser_window(client, app, monkeypatch):
    from app.reminders.due import browser_due, telegram_due
    from app.reminders.repository import mark_reminder_sent
    from app.reminders.worker import process_due_reminders

    person = _person(client, chat_id="555")
    monkeypatch.setenv("REMINDER_DEFAULT_TIME", "08:15")
    monkeypatch.setenv("REMINDER_TIMEZONE", "Asia/Jerusalem")

    created = client.post(
        "/api/events",
        json={
            "title": "בלי שעה",
            "gregorian_date": "2026-03-01",
            "hebrew_date": "א",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    before = datetime(2026, 3, 1, 8, 14, tzinfo=TZ)
    at_default = datetime(2026, 3, 1, 8, 15, tzinfo=TZ)
    with app.app_context():
        assert telegram_due(now=before) == []
        due = telegram_due(now=at_default)
        assert len(due) == 1
        assert due[0]["event_id"] == event_id
        assert "555" in due[0]["chat_ids"]
        assert "בלי שעה" in due[0]["text"]

        sent_calls = []

        def fake_send(token, chat_id, text):
            sent_calls.append((token, chat_id, text))
            return True

        assert process_due_reminders(now=at_default, send=fake_send, token="test-token") == 1
        assert sent_calls[0][0] == "test-token"
        assert sent_calls[0][1] == "555"
        assert telegram_due(now=at_default) == []

        visible = browser_due(now=at_default + timedelta(minutes=5), grace_seconds=900)
        assert len(visible) == 1
        assert visible[0]["title"] == "בלי שעה"
        assert visible[0]["tag"].startswith("heb-cal-reminder-")

        failed = client.post(
            "/api/events",
            json={
                "title": "כישלון שליחה",
                "gregorian_date": "2026-03-01",
                "hebrew_date": "א",
                "time": "08:15",
                "reminders": [{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
            },
        )
        assert failed.status_code == 200

        def explode(token, chat_id, text):
            raise RuntimeError("network")

        assert process_due_reminders(now=at_default, send=explode, token="test-token") == 0
        still_due = telegram_due(now=at_default)
        assert len(still_due) == 1
        mark_reminder_sent(still_due[0]["id"], datetime(2026, 3, 1, tzinfo=timezone.utc))
        assert telegram_due(now=at_default) == []

    no_token = client.post(
        "/api/events",
        json={
            **SAMPLE,
            "title": "בלי טוקן",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
        },
    )
    assert no_token.status_code == 200
    with app.app_context():
        assert process_due_reminders(
            now=datetime(2026, 6, 1, 10, 0, tzinfo=TZ),
            token="",
        ) == 0
        assert len(telegram_due(now=datetime(2026, 6, 1, 10, 0, tzinfo=TZ))) == 1


def test_browser_due_endpoint_and_people_crud(client):
    person = _person(client, name="רינה", chat_id="-100")
    edited = client.put(
        f"/api/reminder-people/{person['id']}",
        json={"name": "רינה כהן", "telegram_chat_id": "100"},
    )
    assert edited.status_code == 200
    assert edited.get_json()["telegram_chat_id"] == "100"

    bad_chat = client.post(
        "/api/reminder-people",
        json={"name": "טעות", "telegram_chat_id": "abc"},
    )
    assert bad_chat.status_code == 400

    now = datetime.now(TZ).replace(second=0, microsecond=0)
    start = now + timedelta(minutes=5)
    created = client.post(
        "/api/events",
        json={
            "title": "עוד מעט",
            "gregorian_date": start.date().isoformat(),
            "hebrew_date": "היום",
            "time": start.strftime("%H:%M"),
            "reminders": [{"offset_minutes": 10, "recipient_ids": [person["id"]]}],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    due = client.get("/api/reminders/due?within_seconds=90&grace_seconds=900")
    assert due.status_code == 200
    payload = due.get_json()
    assert payload["push"]["supported"] is False
    matches = [item for item in payload["reminders"] if item["event_id"] == event_id]
    assert len(matches) == 1
    assert matches[0]["title"] == "עוד מעט"

    deleted = client.delete(f"/api/events/{event_id}")
    assert deleted.status_code == 200
    with client.application.app_context():
        from app.database import get_db

        left = get_db().execute(
            "SELECT COUNT(*) AS n FROM reminders WHERE event_id = ?",
            (event_id,),
        ).fetchone()["n"]
        assert left == 0

    assert client.delete(f"/api/reminder-people/{person['id']}").status_code == 200
    assert client.get("/api/reminder-people").get_json() == []


def test_settings_page_and_start_command(client):
    page = client.get("/settings")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert '<h2 class="h5">תזכורות</h2>' in html
    assert "/start" in html
    assert "התראות בדפדפן" in html
    assert "Web Push" not in html

    assert start_chat_id({"message": {"text": "/start", "chat": {"id": 42}}}) == 42
    assert start_chat_id({"message": {"text": "/start@HebCalBot now", "chat": {"id": -7}}}) == -7
    assert start_chat_id({"message": {"text": "/started", "chat": {"id": 1}}}) is None
    assert chat_id_reply(42) == (
        "מזהה הצ'אט שלך: <code>42</code>\n"
        "מעתיקים את המספר להגדרות, תחת תזכורות."
    )
    assert "<code>-100</code>" in chat_id_reply(-100)
    assert "<code>&lt;id&gt;</code>" in chat_id_reply("<id>")

    calls = []

    def api(token, method, payload=None, timeout=30):
        calls.append((method, payload))
        if method == "getUpdates":
            return [{"update_id": 7, "message": {"text": "/start", "chat": {"id": 42}}}]
        return {"ok": True}

    assert consume_updates("token", None, api=api) == 8
    assert calls[1][0] == "sendMessage"
    assert calls[1][1]["chat_id"] == 42
    assert calls[1][1]["parse_mode"] == "HTML"
    assert "<code>42</code>" in calls[1][1]["text"]


def test_delete_person_missing_and_empty_name(client):
    assert client.delete("/api/reminder-people/5").status_code == 404
    missing = client.post("/api/reminder-people", json={"name": "  "})
    assert missing.status_code == 400
