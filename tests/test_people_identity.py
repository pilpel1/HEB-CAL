"""איחוד אנשים לפי שם, אינדקס ייחודי, וחסימת מחיקה בלי העברת תזכורות."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.database import SCHEMA_VERSION
from app.reminders.repository import _PEOPLE_NAME_INDEX


def _person(client, name="שירה", **extra):
    payload = {"name": name, "telegram_chat_id": extra.pop("telegram_chat_id", None)}
    payload.update(extra)
    response = client.post("/api/reminder-people", json=payload)
    assert response.status_code in (200, 201), response.get_json()
    return response


def test_create_reuses_same_name_and_turns_on_reminders(client):
    first = _person(
        client,
        name="שירה",
        telegram_chat_id="99",
        receives_reminders=False,
        works_shifts=True,
    )
    assert first.status_code == 201
    body = first.get_json()
    assert body["receives_reminders"] is False
    assert body["works_shifts"] is True

    again = _person(client, name="  שירה ", receives_reminders=True)
    assert again.status_code == 200
    reused = again.get_json()
    assert reused["id"] == body["id"]
    assert reused["telegram_chat_id"] == "99"
    assert reused["receives_reminders"] is True
    assert reused["works_shifts"] is True

    listed = client.get("/api/reminder-people").get_json()
    assert len(listed) == 1
    assert listed[0]["name"] == "שירה"


def test_create_reuses_case_insensitive_latin_name(client):
    first = _person(client, name="Shira", telegram_chat_id="7", works_shifts=True)
    again = _person(client, name="shira", receives_reminders=True)
    assert again.status_code == 200
    assert again.get_json()["id"] == first.get_json()["id"]
    assert len(client.get("/api/reminder-people").get_json()) == 1


def test_create_conflicts_when_chat_ids_differ(client):
    _person(client, name="שירה", telegram_chat_id="11")
    conflict = client.post(
        "/api/reminder-people",
        json={"name": "שירה", "telegram_chat_id": "22"},
    )
    assert conflict.status_code == 400
    assert "צ׳אט" in conflict.get_json()["error"]
    assert len(client.get("/api/reminder-people").get_json()) == 1


def test_rename_conflicts_with_existing_name(client):
    _person(client, name="שירה")
    other = _person(client, name="דני").get_json()
    renamed = client.put(
        f"/api/reminder-people/{other['id']}",
        json={"name": "שירה", "telegram_chat_id": None},
    )
    assert renamed.status_code == 400
    assert "כבר בשימוש" in renamed.get_json()["error"]


def test_list_returns_everyone_including_shift_only(client):
    _person(client, name="שירה", receives_reminders=False, works_shifts=True)
    _person(client, name="דני", receives_reminders=True, works_shifts=False)
    all_names = {row["name"] for row in client.get("/api/reminder-people").get_json()}
    assert all_names == {"שירה", "דני"}
    reminder_names = {
        row["name"] for row in client.get("/api/reminder-people?role=reminders").get_json()
    }
    assert reminder_names == {"דני"}


def test_delete_requires_reassign_when_referenced(client):
    person = _person(client, name="שירה", telegram_chat_id="1").get_json()
    other = _person(client, name="דני", telegram_chat_id="2").get_json()
    created = client.post(
        "/api/events",
        json={
            "title": "פגישה",
            "gregorian_date": "2026-06-01",
            "hebrew_date": "א",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    blocked = client.delete(f"/api/reminder-people/{person['id']}")
    assert blocked.status_code == 409
    assert "תזכורות" in blocked.get_json()["error"]
    assert event_id in blocked.get_json()["referenced_event_ids"]
    still = client.get(f"/api/events/{event_id}").get_json()
    assert still["reminders"][0]["recipient_ids"] == [person["id"]]

    moved = client.delete(f"/api/reminder-people/{person['id']}?reassign_to={other['id']}")
    assert moved.status_code == 200, moved.get_json()
    after = client.get(f"/api/events/{event_id}").get_json()
    assert after["reminders"][0]["recipient_ids"] == [other["id"]]
    names = {row["name"] for row in client.get("/api/reminder-people").get_json()}
    assert names == {"דני"}


def test_delete_without_refs_still_works(client):
    person = _person(client, name="שירה").get_json()
    assert client.delete(f"/api/reminder-people/{person['id']}").status_code == 200
    assert client.get("/api/reminder-people").get_json() == []


def test_unique_index_exists_on_fresh_db(client, app):
    with app.app_context():
        from app.database import get_db

        row = get_db().execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (_PEOPLE_NAME_INDEX,),
        ).fetchone()
    assert row


def test_version_seven_merges_compatible_duplicates(tmp_path):
    path = tmp_path / "v6-dup.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        from app.database import apply_pending_migrations

        assert SCHEMA_VERSION >= 7
        apply_pending_migrations(conn)
        conn.execute("PRAGMA user_version = 6")
        conn.execute(f"DROP INDEX IF EXISTS {_PEOPLE_NAME_INDEX}")
        conn.execute("DROP INDEX IF EXISTS idx_users_name_norm")
        conn.execute(
            """
            INSERT INTO users (name, telegram_chat_id, receives_reminders, works_shifts)
            VALUES ('שירה', '99', 0, 1)
            """
        )
        worker_id = conn.execute("SELECT id FROM users WHERE name = 'שירה'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO users (name, telegram_chat_id, receives_reminders, works_shifts)
            VALUES ('  שירה', NULL, 1, 0)
            """
        )
        extra_id = conn.execute(
            "SELECT id FROM users WHERE id != ? AND trim(name) = 'שירה'",
            (worker_id,),
        ).fetchone()["id"]
        event_id = conn.execute(
            "INSERT INTO events (title, gregorian_date, hebrew_date) VALUES ('פגישה', '2026-11-01', 'א')"
        ).lastrowid
        conn.execute(
            "INSERT INTO reminders (event_id, offset_minutes, recipient_ids) VALUES (?, 0, ?)",
            (event_id, json.dumps([extra_id])),
        )
        conn.execute(
            """
            INSERT INTO events (
                title, gregorian_date, hebrew_date, is_shift, shift_person_id, shift_label
            ) VALUES ('בוקר', '2026-11-02', 'ב', 1, ?, 'בוקר')
            """,
            (worker_id,),
        )
        conn.commit()

        apply_pending_migrations(conn)
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        assert len(rows) == 1
        person = rows[0]
        assert person["id"] == worker_id
        assert person["telegram_chat_id"] == "99"
        assert person["receives_reminders"] == 1
        assert person["works_shifts"] == 1
        reminder = conn.execute("SELECT recipient_ids FROM reminders WHERE event_id = ?", (event_id,)).fetchone()
        assert json.loads(reminder["recipient_ids"]) == [worker_id]
        shift = conn.execute(
            "SELECT shift_person_id FROM events WHERE is_shift = 1"
        ).fetchone()
        assert shift["shift_person_id"] == worker_id
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (_PEOPLE_NAME_INDEX,),
        ).fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()


def test_version_seven_leaves_conflicting_chat_duplicates(tmp_path):
    path = tmp_path / "v6-conflict.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        from app.database import apply_pending_migrations

        apply_pending_migrations(conn)
        conn.execute("PRAGMA user_version = 6")
        conn.execute(f"DROP INDEX IF EXISTS {_PEOPLE_NAME_INDEX}")
        conn.execute("DROP INDEX IF EXISTS idx_users_name_norm")
        conn.execute(
            "INSERT INTO users (name, telegram_chat_id) VALUES ('שירה', '11')"
        )
        conn.execute(
            "INSERT INTO users (name, telegram_chat_id) VALUES ('שירה', '22')"
        )
        conn.commit()
        apply_pending_migrations(conn)
        names = [row["telegram_chat_id"] for row in conn.execute("SELECT telegram_chat_id FROM users")]
        assert sorted(names) == ["11", "22"]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()


def test_people_ui_lists_everyone_and_warns_about_chat(client):
    settings = client.get("/settings").get_data(as_text=True)
    assert "כל האנשים במקום אחד" in settings
    assert 'id="reminderPersonSuggest"' in settings
    assert 'id="reminderPersonReassign"' in settings
    people_js = client.get("/static/js/events/reminder-people.js").get_data(as_text=True)
    assert "filter((person) => person.receives_reminders)" not in people_js
    assert "appendPersonRoleSwitch" in people_js
    assert "telegramUnlinkConfirm" in people_js
    assert "דורש חיבור לטלגרם" in people_js
    assert "בטוח שרוצים לנתק את הטלגרם של" in people_js
    assert "סיכום הבוקר ייכבה ותזכורות לא יגיעו בטלגרם (רק בדפדפן)." in people_js
    assert "ייכבו" not in people_js
    assert "telegramLinkStatus" in people_js
    assert "suggestSimilarReminderPerson" in people_js
    assert "reassign_to" in people_js
    form_js = client.get("/static/js/events/reminders-form.js").get_data(as_text=True)
    assert "role=reminders" in form_js
    assert "updateReminderChatWarning" in form_js
    assert "אין קישור לטלגרם" in form_js
    modal = (Path(__file__).resolve().parent.parent / "app/templates/partials/quick_event_modal.html").read_text(
        encoding="utf-8"
    )
    assert 'id="quick_reminder_chat_warn"' in modal
