"""שעת סיום אופציונלית: אימות, CRUD, חזרה, MCP, גיבוי, גוגל, תצוגה."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from app.services.event_payload import EventPayloadError, clean_event_write, format_event_time_range
from mcp_support import add_user, make_key, ok, tool_error

REPO = Path(__file__).resolve().parent.parent
DAY = "2026-12-02"


def test_clean_end_time_rules():
    same = clean_event_write({
        "title": "פגישה",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "07:30",
        "end_time": "09:30",
    })
    assert same["time"] == "07:30"
    assert same["end_time"] == "09:30"
    assert format_event_time_range(same) == "07:30-09:30"

    overnight = clean_event_write({
        "title": "לילה",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "22:00",
        "end_time": "01:00",
        "end_date": "2026-12-03",
    })
    assert overnight["end_time"] == "01:00"
    assert overnight["end_date"] == "2026-12-03"

    missing = clean_event_write({
        "title": "בלי שעה",
        "gregorian_date": DAY,
        "hebrew_date": "א",
    })
    assert missing["time"] is None
    assert missing["end_time"] is None
    assert format_event_time_range(missing) is None

    try:
        clean_event_write({
            "title": "רק סיום",
            "gregorian_date": DAY,
            "hebrew_date": "א",
            "end_time": "09:00",
        })
        raise AssertionError("expected error")
    except EventPayloadError as exc:
        assert "שעת התחלה" in str(exc)

    try:
        clean_event_write({
            "title": "הפוך",
            "gregorian_date": DAY,
            "hebrew_date": "א",
            "time": "10:00",
            "end_time": "09:00",
        })
        raise AssertionError("expected error")
    except EventPayloadError as exc:
        assert "לפני" in str(exc)

    try:
        clean_event_write({
            "title": "שבור",
            "gregorian_date": DAY,
            "hebrew_date": "א",
            "time": "10:00",
            "end_time": "25:00",
        })
        raise AssertionError("expected error")
    except EventPayloadError as exc:
        assert "HH:MM" in str(exc)


def test_api_create_update_clear_and_same_day_reject(client):
    created = client.post("/api/events", json={
        "title": "ישבצ פגיה",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "07:30",
        "end_time": "09:30",
    })
    assert created.status_code == 200, created.get_json()
    event_id = created.get_json()["id"]
    listed = client.get("/api/events").get_json()
    row = next(item for item in listed if item["id"] == event_id)
    assert row["time"] == "07:30"
    assert row["end_time"] == "09:30"

    got = client.get(f"/api/events/{event_id}").get_json()
    assert got["end_time"] == "09:30"

    bad = client.post("/api/events", json={
        "title": "הפוך",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "10:00",
        "end_time": "09:00",
    })
    assert bad.status_code == 400
    assert "לפני" in bad.get_json()["error"]

    no_start = client.post("/api/events", json={
        "title": "רק סיום",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "end_time": "09:00",
    })
    assert no_start.status_code == 400
    assert "שעת התחלה" in no_start.get_json()["error"]

    overnight = client.post("/api/events", json={
        "title": "לילה",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "22:00",
        "end_time": "01:00",
        "end_date": "2026-12-03",
    })
    assert overnight.status_code == 200, overnight.get_json()

    cleared = client.put(f"/api/events/{event_id}", json={
        "title": "ישבצ פגיה",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "07:30",
        "end_time": None,
    })
    assert cleared.status_code == 200, cleared.get_json()
    after = client.get(f"/api/events/{event_id}").get_json()
    assert after["time"] == "07:30"
    assert after["end_time"] is None


def test_existing_event_without_end_time_stays_null(client):
    created = client.post("/api/events", json={
        "title": "ישן",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "10:00",
    })
    assert created.status_code == 200
    row = next(item for item in client.get("/api/events").get_json() if item["title"] == "ישן")
    assert row["time"] == "10:00"
    assert row.get("end_time") is None


def test_recurrence_occurrences_inherit_end_time(client):
    created = client.post("/api/events", json={
        "title": "חוג",
        "gregorian_date": "2026-12-01",
        "hebrew_date": "א",
        "time": "18:00",
        "end_time": "19:00",
        "recurrence_freq": "weekly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 3,
    })
    assert created.status_code == 200, created.get_json()
    rows = client.get("/api/events?from=2026-12-01&to=2026-12-15").get_json()
    times = [(row["gregorian_date"][:10], row["time"], row.get("end_time")) for row in rows if row["title"] == "חוג"]
    assert times == [
        ("2026-12-01", "18:00", "19:00"),
        ("2026-12-08", "18:00", "19:00"),
        ("2026-12-15", "18:00", "19:00"),
    ]


def test_export_import_keeps_end_time_and_old_json_without_it(client):
    create = client.post("/api/events", json={
        "title": "עם סיום",
        "gregorian_date": DAY,
        "hebrew_date": "א",
        "time": "07:30",
        "end_time": "09:30",
    })
    assert create.status_code == 200
    exported = json.loads(client.get("/api/events/export").data.decode("utf-8"))
    row = next(item for item in exported["events"] if item["title"] == "עם סיום")
    assert row["end_time"] == "09:30"

    old = {
        "title": "גיבוי ישן",
        "gregorian_date": "2026-12-04",
        "hebrew_date": "א",
        "time": "11:00",
        "description": "",
    }
    imported = client.post(
        "/api/events/import?mode=replace",
        json={"events": [row, old], "colors": exported["colors"]},
    )
    assert imported.status_code == 200, imported.get_json()
    by_title = {item["title"]: item for item in client.get("/api/events").get_json()}
    assert by_title["עם סיום"]["end_time"] == "09:30"
    assert by_title["גיבוי ישן"]["time"] == "11:00"
    assert by_title["גיבוי ישן"]["end_time"] is None


def test_mcp_create_update_list_search_get_end_time(app, client):
    user = add_user(app)
    token = make_key(app, user, "write")
    created = ok(client, token, "create_event", {
        "title": "ישבצ פגיה",
        "date": DAY,
        "time": "07:30",
        "end_time": "09:30",
    })
    event = created["event"]
    event_id = event["id"]
    assert event["time"] == "07:30"
    assert event["end_time"] == "09:30"

    listed = ok(client, token, "list_events", {"from": DAY, "to": DAY})
    assert listed["events"][0]["end_time"] == "09:30"
    found = ok(client, token, "search_events", {"query": "פגיה"})
    assert found["events"][0]["end_time"] == "09:30"
    got = ok(client, token, "get_event", {"event_id": event_id})
    assert got["event"]["end_time"] == "09:30"

    cleared = ok(client, token, "update_event", {"event_id": event_id, "end_time": None})
    assert cleared["event"]["time"] == "07:30"
    assert cleared["event"]["end_time"] is None

    restored = ok(client, token, "update_event", {"event_id": event_id, "end_time": "08:15"})
    assert restored["event"]["end_time"] == "08:15"

    assert tool_error(client, token, "create_event", {
        "title": "רק סיום",
        "date": DAY,
        "end_time": "09:00",
    })["code"] == "invalid_input"
    assert "שעת התחלה" in tool_error(client, token, "create_event", {
        "title": "רק סיום",
        "date": DAY,
        "end_time": "09:00",
    })["message"]
    assert "לפני" in tool_error(client, token, "create_event", {
        "title": "הפוך",
        "date": DAY,
        "time": "10:00",
        "end_time": "09:00",
    })["message"]


def test_gcal_parse_carries_end_time():
    from app.gcal.parse import parse_ical

    body = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"
        "BEGIN:VEVENT\r\nUID:timed\r\nSUMMARY:פגישה\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260327T073000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260327T093000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:all-day\r\nSUMMARY:יום\r\n"
        "DTSTART;VALUE=DATE:20260328\r\nDTEND;VALUE=DATE:20260329\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:overnight\r\nSUMMARY:לילה\r\n"
        "DTSTART:20260601T213000\r\nDTEND:20260602T003000\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    rows = {row["gcal_uid"]: row for row in parse_ical(body, date(2026, 1, 1), date(2026, 12, 31))}
    assert rows["timed"]["time"] == "07:30"
    assert rows["timed"]["end_time"] == "09:30"
    assert rows["all-day"]["time"] is None
    assert rows["all-day"]["end_time"] is None
    assert rows["overnight"]["time"] == "21:30"
    assert rows["overnight"]["end_date"] == "2026-06-02"
    assert rows["overnight"]["end_time"] == "00:30"


def test_digest_shows_time_range(app):
    from app.database import create_event, get_event
    from app.reminders.digest import format_digest_event
    from app.services.recurrence import hebrew_display

    with app.app_context():
        from app.reminders.repository import create_person

        person = create_person("שירה", "1")
        day = date(2026, 10, 22)
        event_id = create_event(
            "ישבצ פגיה | שירה",
            day.isoformat(),
            hebrew_display(day),
            time="07:30",
            end_time="09:30",
        )
        line = format_digest_event(get_event(event_id), {person["id"]: person})
    assert line == "• 07:30-09:30 | ישבצ פגיה | שירה"
    assert "כל היום" not in line


def test_schema_v9_adds_nullable_end_time(tmp_path):
    from app.database import SCHEMA_VERSION, apply_pending_migrations

    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            gregorian_date TEXT NOT NULL,
            hebrew_date TEXT NOT NULL,
            time TEXT,
            description TEXT,
            end_date TEXT,
            color TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO events (title, gregorian_date, hebrew_date, time) VALUES ('ישן', '2020-01-02', 'ה טבת', '10:00')"
    )
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    apply_pending_migrations(conn)
    apply_pending_migrations(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
    assert "end_time" in cols
    ex_cols = {row[1] for row in conn.execute("PRAGMA table_info(event_exceptions)")}
    assert "end_time" in ex_cols
    row = conn.execute("SELECT title, time, end_time FROM events").fetchone()
    assert row["title"] == "ישן"
    assert row["time"] == "10:00"
    assert row["end_time"] is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 11
    conn.close()


def test_ui_has_end_time_next_to_start():
    html = (REPO / "app/templates/partials/quick_event_modal.html").read_text(encoding="utf-8")
    js = (REPO / "app/static/js/events/quick-event-modal.js").read_text(encoding="utf-8")
    render = (REPO / "app/static/js/calendar/event-render.js").read_text(encoding="utf-8")
    simple, _, _advanced = html.partition('id="quick_advanced"')
    assert 'id="quick_time"' in simple
    assert 'id="quick_end_time"' in simple
    assert "שעת סיום" in simple
    assert "function getQuickEndTimeValue" in js
    assert "function assertEndTimeValid" in js
    assert "function formatEventTimeRange" in render
    assert "${start}-${event.end_time}" in render
