"""תזכורות לפי אדם: מיגרציה, API, ו-UI."""
from __future__ import annotations

import json
from pathlib import Path

from app.database import SCHEMA_VERSION, get_db


REPO = Path(__file__).resolve().parent.parent


def test_expand_shared_recipients_preserves_sends(client, app):
    avi = client.post(
        "/api/reminder-people",
        json={"name": "אביחי", "telegram_chat_id": "111"},
    ).get_json()
    shira = client.post(
        "/api/reminder-people",
        json={"name": "שירה", "telegram_chat_id": "222"},
    ).get_json()
    created = client.post(
        "/api/events",
        json={
            "title": "לפני פיצול",
            "gregorian_date": "2026-06-01",
            "hebrew_date": "א",
            "reminders": [
                {"offset_minutes": 30, "recipient_ids": [avi["id"], shira["id"]]},
            ],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    with app.app_context():
        db = get_db()
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        # מדמים שורה ישנה משותפת: מאחדים חזרה ל-recipient_ids כפול ומאפסים person_id
        rows = db.execute(
            "SELECT id FROM reminders WHERE event_id = ? ORDER BY id",
            (event_id,),
        ).fetchall()
        assert len(rows) == 2
        keep_id = rows[0]["id"]
        drop_id = rows[1]["id"]
        db.execute("DELETE FROM reminder_sends WHERE reminder_id = ?", (drop_id,))
        db.execute("DELETE FROM reminders WHERE id = ?", (drop_id,))
        db.execute(
            """
            UPDATE reminders
            SET person_id = NULL,
                recipient_ids = ?,
                sent_at = '2026-01-01T00:00:00Z'
            WHERE id = ?
            """,
            (json.dumps([avi["id"], shira["id"]]), keep_id),
        )
        db.execute(
            """
            INSERT INTO reminder_sends (reminder_id, occurrence_date, chat_id, sent_at)
            VALUES (?, '2026-06-01', '111', '2026-01-01T00:00:00Z'),
                   (?, '2026-06-01', '222', '2026-01-01T00:00:00Z')
            """,
            (keep_id, keep_id),
        )
        db.commit()

        from app.reminders.repository import expand_reminders_to_per_person

        created_rows = expand_reminders_to_per_person(db)
        db.commit()
        assert created_rows == 1

        expanded = db.execute(
            """
            SELECT id, person_id, offset_minutes, recipient_ids, sent_at
            FROM reminders WHERE event_id = ?
            ORDER BY person_id
            """,
            (event_id,),
        ).fetchall()
        assert len(expanded) == 2
        assert [row["person_id"] for row in expanded] == [avi["id"], shira["id"]]
        assert all(row["offset_minutes"] == 30 for row in expanded)
        assert all(row["sent_at"] for row in expanded)
        by_person = {row["person_id"]: row["id"] for row in expanded}
        chats = {
            (row["reminder_id"], row["chat_id"])
            for row in db.execute("SELECT reminder_id, chat_id FROM reminder_sends")
        }
        assert (by_person[avi["id"]], "111") in chats
        assert (by_person[shira["id"]], "222") in chats


def test_per_person_offsets_round_trip(client):
    avi = client.post(
        "/api/reminder-people",
        json={"name": "אביחי", "telegram_chat_id": "11"},
    ).get_json()
    shira = client.post(
        "/api/reminder-people",
        json={"name": "שירה", "telegram_chat_id": "22"},
    ).get_json()

    created = client.post(
        "/api/events",
        json={
            "title": "שונים",
            "gregorian_date": "2026-07-01",
            "hebrew_date": "א",
            "time": "18:00",
            "reminders": [
                {"person_id": avi["id"], "offset_minutes": 15},
                {"person_id": shira["id"], "offset_minutes": 60},
                {"person_id": avi["id"], "offset_minutes": 1440},
            ],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]
    body = client.get(f"/api/events/{event_id}").get_json()
    pairs = sorted(
        (item["person_id"], item["offset_minutes"]) for item in body["reminders"]
    )
    assert pairs == [
        (avi["id"], 15),
        (avi["id"], 1440),
        (shira["id"], 60),
    ]

    legacy = client.post(
        "/api/events",
        json={
            "title": "ישן",
            "gregorian_date": "2026-07-02",
            "hebrew_date": "ב",
            "reminders": [
                {"offset_minutes": 5, "recipient_ids": [avi["id"], shira["id"]]},
            ],
        },
    )
    assert legacy.status_code == 200
    legacy_id = legacy.get_json()["id"]
    legacy_body = client.get(f"/api/events/{legacy_id}").get_json()
    assert sorted(
        (item["person_id"], item["offset_minutes"]) for item in legacy_body["reminders"]
    ) == [(avi["id"], 5), (shira["id"], 5)]


def test_due_honors_different_offsets_per_person(client, app):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.reminders.due import telegram_due

    tz = ZoneInfo("Asia/Jerusalem")
    avi = client.post(
        "/api/reminder-people",
        json={"name": "אביחי", "telegram_chat_id": "501"},
    ).get_json()
    shira = client.post(
        "/api/reminder-people",
        json={"name": "שירה", "telegram_chat_id": "502"},
    ).get_json()
    created = client.post(
        "/api/events",
        json={
            "title": "פגישה",
            "gregorian_date": "2026-08-10",
            "hebrew_date": "א",
            "time": "12:00",
            "reminders": [
                {"person_id": avi["id"], "offset_minutes": 60},
                {"person_id": shira["id"], "offset_minutes": 15},
            ],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    with app.app_context():
        at_avi = datetime(2026, 8, 10, 11, 0, tzinfo=tz)
        due_avi = [item for item in telegram_due(now=at_avi) if item["event_id"] == event_id]
        assert len(due_avi) == 1
        assert due_avi[0]["chat_ids"] == ["501"]
        assert due_avi[0]["offset_minutes"] == 60

        at_shira = datetime(2026, 8, 10, 11, 45, tzinfo=tz)
        due_shira = [
            item for item in telegram_due(now=at_shira) if item["event_id"] == event_id
        ]
        # אביחי עדיין לא סומן כנשלח — שתי התזכורות due, כל אחת לצ'אט שלה
        by_offset = {item["offset_minutes"]: item for item in due_shira}
        assert set(by_offset) == {15, 60}
        assert by_offset[15]["chat_ids"] == ["502"]
        assert by_offset[60]["chat_ids"] == ["501"]


def test_modal_and_list_markup_for_per_person_and_chunks():
    modal = (REPO / "app/templates/partials/quick_event_modal.html").read_text(encoding="utf-8")
    form_js = (REPO / "app/static/js/events/reminders-form.js").read_text(encoding="utf-8")
    listing = (REPO / "app/templates/events_list.html").read_text(encoding="utf-8")

    assert 'id="quick_reminder_person_tabs"' in modal
    assert "reminder-recipients" not in modal
    assert "byPerson" in form_js
    assert "person_id" in form_js
    assert "הצג עוד" in listing
    assert "sectionOpen" in listing
    assert "sectionVisible" in listing
    assert "events-section-details" in listing
