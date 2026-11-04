"""טבלת users (גרסה 8): מיגרציה, אימייל, API, ו-Cf-Access."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import SCHEMA_VERSION
from app.users.identity import ACCESS_EMAIL_HEADER, current_access_user, user_for_access_headers
from app.users.table import USERS_BACKUP_TABLE, USERS_TABLE


def _person(client, name="שירה", **extra):
    payload = {"name": name, "telegram_chat_id": extra.pop("telegram_chat_id", None)}
    payload.update(extra)
    response = client.post("/api/users", json=payload)
    assert response.status_code in (200, 201), response.get_json()
    return response


def test_fresh_db_uses_users_table(app):
    with app.app_context():
        from app.database import get_db

        db = get_db()
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert USERS_TABLE in tables
        assert "reminder_people" not in tables
        assert USERS_BACKUP_TABLE in tables
        cols = {row[1] for row in db.execute(f"PRAGMA table_info({USERS_TABLE})")}
        assert "google_email" in cols
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_users_api_aliases_reminder_people(client):
    created = _person(client, name="שירה", google_email="shira@gmail.com").get_json()
    listed = client.get("/api/users").get_json()
    via_old = client.get("/api/reminder-people").get_json()
    assert listed == via_old
    assert listed[0]["google_email"] == "shira@gmail.com"
    assert listed[0]["id"] == created["id"]
    assert "flags" in listed[0]
    assert listed[0]["flags"]["receives_reminders"] is True

    updated = client.put(
        f"/api/users/{created['id']}",
        json={"name": "שירה", "telegram_chat_id": None, "google_email": "SHIRA@Gmail.com"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["google_email"] == "shira@gmail.com"


def test_google_email_must_be_unique_and_valid(client):
    _person(client, name="שירה", google_email="a@gmail.com")
    taken = client.post(
        "/api/users",
        json={"name": "דני", "google_email": "A@Gmail.com"},
    )
    assert taken.status_code == 400
    assert "אימייל" in taken.get_json()["error"]

    bad = client.post("/api/users", json={"name": "נועה", "google_email": "not-an-email"})
    assert bad.status_code == 400


def test_access_header_maps_when_present_and_ignored_otherwise(client, app):
    person = _person(client, name="שירה", google_email="shira@gmail.com").get_json()
    with app.test_request_context("/", headers={ACCESS_EMAIL_HEADER: "Shira@Gmail.com"}):
        found = current_access_user()
        assert found is not None
        assert found["id"] == person["id"]
    with app.test_request_context("/"):
        assert current_access_user() is None
    with app.app_context():
        assert user_for_access_headers({}) is None
        assert user_for_access_headers({ACCESS_EMAIL_HEADER: "nobody@gmail.com"}) is None
        assert user_for_access_headers({ACCESS_EMAIL_HEADER: "not-email"}) is None


def test_version_eight_renames_legacy_table_and_keeps_backup(tmp_path):
    path = tmp_path / "v7.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        from app.database import apply_pending_migrations
        from app.reminders.repository import ensure_reminder_schema

        ensure_reminder_schema(conn)
        conn.execute(
            "INSERT INTO reminder_people (name, telegram_chat_id) VALUES ('שירה', '99')"
        )
        conn.commit()
        apply_pending_migrations(conn)
        apply_pending_migrations(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert USERS_TABLE in tables
        assert "reminder_people" not in tables
        assert USERS_BACKUP_TABLE in tables
        row = conn.execute("SELECT name, telegram_chat_id FROM users").fetchone()
        assert row["name"] == "שירה"
        assert row["telegram_chat_id"] == "99"
        backup = conn.execute(
            f"SELECT name FROM {USERS_BACKUP_TABLE}"
        ).fetchone()
        assert backup["name"] == "שירה"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()


def test_export_includes_users_and_legacy_key(client):
    _person(client, name="שירה", google_email="shira@gmail.com")
    exported = json.loads(client.get("/api/events/export").data.decode("utf-8"))
    assert "users" in exported
    assert exported["users"] == exported["reminder_people"]
    assert exported["users"][0]["google_email"] == "shira@gmail.com"


def test_delete_blocked_by_shift_events(client):
    person = _person(client, name="שירה", works_shifts=True, color="cyan").get_json()
    other = _person(client, name="דני").get_json()
    client.put("/api/shifts/settings", json={"enabled": True})
    saved = client.put(
        "/api/shifts/week",
        json={
            "person_id": person["id"],
            "week_start": "2026-10-18",
            "cells": [{"date": "2026-10-18", "label": "בוקר"}],
        },
    )
    assert saved.status_code == 200, saved.get_json()
    blocked = client.delete(f"/api/users/{person['id']}")
    assert blocked.status_code == 409
    assert "משמרות" in blocked.get_json()["error"]
    assert blocked.get_json()["shift_event_count"] >= 1
    moved = client.delete(f"/api/users/{person['id']}?reassign_to={other['id']}")
    assert moved.status_code == 200, moved.get_json()


def test_telegram_due_skips_people_with_reminders_off(client, app):
    person = _person(
        client,
        name="שירה",
        telegram_chat_id="99",
        receives_reminders=True,
    ).get_json()
    created = client.post(
        "/api/events",
        json={
            "title": "פגישה",
            "gregorian_date": "2026-06-01",
            "hebrew_date": "א",
            "time": "08:00",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
        },
    )
    assert created.status_code == 200, created.get_json()
    client.put(
        f"/api/users/{person['id']}",
        json={"name": "שירה", "telegram_chat_id": "99", "receives_reminders": False},
    )
    with app.app_context():
        from app.reminders.due import telegram_due

        now = datetime(2026, 6, 1, 9, 0, tzinfo=ZoneInfo("Asia/Jerusalem"))
        assert telegram_due(now) == []
        client.put(
            f"/api/users/{person['id']}",
            json={"name": "שירה", "telegram_chat_id": "99", "receives_reminders": True},
        )
        assert telegram_due(now)


def test_digest_requires_telegram_chat_on_create_update_and_toggle(client):
    created = client.post(
        "/api/users",
        json={"name": "נועה", "telegram_chat_id": None, "daily_digest_enabled": True},
    )
    assert created.status_code == 400
    assert "טלגרם" in created.get_json()["error"]

    person = _person(client, name="נועה").get_json()
    assert person["daily_digest_enabled"] is False
    assert person["receives_reminders"] is True

    reminders_on = client.put(
        f"/api/users/{person['id']}",
        json={
            "name": "נועה",
            "telegram_chat_id": None,
            "receives_reminders": True,
        },
    )
    assert reminders_on.status_code == 200, reminders_on.get_json()
    assert reminders_on.get_json()["receives_reminders"] is True
    assert reminders_on.get_json()["daily_digest_enabled"] is False

    rejected = client.put(
        f"/api/users/{person['id']}",
        json={
            "name": "נועה",
            "telegram_chat_id": None,
            "daily_digest_enabled": True,
        },
    )
    assert rejected.status_code == 400
    assert "טלגרם" in rejected.get_json()["error"]

    linked = client.put(
        f"/api/users/{person['id']}",
        json={
            "name": "נועה",
            "telegram_chat_id": "42",
            "daily_digest_enabled": True,
            "receives_reminders": True,
        },
    )
    assert linked.status_code == 200, linked.get_json()
    assert linked.get_json()["daily_digest_enabled"] is True

    unlinked = client.put(
        f"/api/users/{person['id']}",
        json={"name": "נועה", "telegram_chat_id": None},
    )
    assert unlinked.status_code == 200, unlinked.get_json()
    body = unlinked.get_json()
    assert body["telegram_chat_id"] in (None, "")
    assert body["daily_digest_enabled"] is False
    assert body["receives_reminders"] is True


def test_digest_without_chat_is_turned_off_on_existing_rows(tmp_path, capsys):
    path = tmp_path / "digest-orphan.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        from app.database import apply_pending_migrations
        from app.reminders.repository import disable_digest_without_telegram

        apply_pending_migrations(conn)
        conn.execute(
            """
            INSERT INTO users (name, telegram_chat_id, daily_digest_enabled, receives_reminders)
            VALUES ('נועה', NULL, 1, 1), ('דני', '99', 1, 1)
            """
        )
        conn.commit()
        apply_pending_migrations(conn)
        rows = {
            row["name"]: row
            for row in conn.execute(
                "SELECT name, daily_digest_enabled, telegram_chat_id FROM users"
            )
        }
        assert rows["נועה"]["daily_digest_enabled"] == 0
        assert rows["דני"]["daily_digest_enabled"] == 1
        assert disable_digest_without_telegram(conn) == 0
        err = capsys.readouterr().err
        assert "נועה" in err
        assert "no telegram chat" in err
        assert "דני" not in err
    finally:
        conn.close()


def test_import_digest_without_chat_is_coerced_off(client, app):
    payload = {
        "events": [],
        "users": [
            {
                "name": "נועה",
                "telegram_chat_id": None,
                "daily_digest_enabled": True,
                "receives_reminders": True,
            }
        ],
    }
    imported = client.post("/api/events/import?mode=merge", json=payload)
    assert imported.status_code == 200, imported.get_json()
    with app.app_context():
        from app.reminders.repository import list_people

        people = list_people()
    assert len(people) == 1
    assert people[0]["daily_digest_enabled"] is False
    assert people[0]["receives_reminders"] is True


def test_unlink_confirm_copy_keeps_browser_reminders():
    from app.users.telegram import UNLINK_CONFIRM_CONSEQUENCES, unlink_telegram_confirm

    text = unlink_telegram_confirm("נועה")
    assert text == (
        "בטוח שרוצים לנתק את הטלגרם של נועה? "
        "סיכום הבוקר ייכבה ותזכורות לא יגיעו בטלגרם (רק בדפדפן)."
    )
    assert text.endswith(UNLINK_CONFIRM_CONSEQUENCES)
    assert "ייכבו" not in text
