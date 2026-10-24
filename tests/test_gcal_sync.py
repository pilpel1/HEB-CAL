"""סנכרון חד-כיווני מיומן גוגל: פענוח, עדכון, מחיקה, חזרות, שעון קיץ.

בלי רשת. הכתובת הסודית לא אמורה להופיע בתשובה, בשגיאה, או בלוג.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.gcal.errors import GcalUserError
from app.gcal.parse import parse_ical
from app.gcal.urls import mask_ical_url, require_google_ical_url

JERUSALEM = ZoneInfo("Asia/Jerusalem")
SECRET = (
    "https://calendar.google.com/calendar/ical/"
    "family%40group.calendar.google.com/private-SECRETVALUE/basic.ics"
)
TODAY = date(2026, 6, 15)


def _ics(events: str) -> bytes:
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//heb-cal-test//\r\n"
        f"{events}"
        "END:VCALENDAR\r\n"
    ).encode()


def _sync(app, body: bytes, *, source_id: int, today=TODAY):
    from app.gcal.sync import sync_source

    def fetch(_url):
        assert _url == SECRET
        return body

    with app.app_context():
        return sync_source(source_id, fetch=fetch, today=today)


def _rows(app):
    with app.app_context():
        from app.database import get_db

        db = get_db()
        return [
            dict(row)
            for row in db.execute(
                """
                SELECT id, title, gregorian_date, hebrew_date, time, description, end_date,
                       color, gcal_source_id, gcal_uid, gcal_recurrence_id
                FROM events
                WHERE gcal_source_id IS NOT NULL
                ORDER BY gregorian_date, time, id
                """
            ).fetchall()
        ]


def _make_source(client, url=SECRET, **extra):
    payload = {"ical_url": url, "label": "עבודה", "color": "#4285f4", "enabled": False}
    payload.update(extra)
    return client.post("/api/gcal/sources", json=payload)


def test_rejects_non_google_and_masks_without_the_secret():
    with pytest.raises(GcalUserError) as exc:
        require_google_ical_url("http://calendar.google.com/calendar/ical/a/basic.ics")
    assert "http://" not in str(exc.value)
    with pytest.raises(GcalUserError):
        require_google_ical_url("https://evil.example/calendar/ical/a/basic.ics")
    with pytest.raises(GcalUserError):
        require_google_ical_url("https://calendar.google.com.evil/calendar/ical/a/basic.ics")
    with pytest.raises(GcalUserError):
        require_google_ical_url(mask_ical_url())
    assert require_google_ical_url(SECRET) == SECRET
    masked = mask_ical_url(SECRET)
    assert "SECRETVALUE" not in masked
    assert "family" not in masked


def test_parse_all_day_timed_and_dst():
    body = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:all-one\r\n"
        "SUMMARY:יום אחד\r\n"
        "DTSTART;VALUE=DATE:20260401\r\n"
        "DTEND;VALUE=DATE:20260402\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:all-span\r\n"
        "SUMMARY:טיול\r\n"
        "DTSTART;VALUE=DATE:20260401\r\n"
        "DTEND;VALUE=DATE:20260404\r\n"
        "LOCATION:ים\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:utc-winter\r\n"
        "SUMMARY:חורף\r\n"
        "DTSTART:20260115T080000Z\r\n"
        "DTEND:20260115T090000Z\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:utc-summer\r\n"
        "SUMMARY:קיץ\r\n"
        "DTSTART:20260701T070000Z\r\n"
        "DTEND:20260701T080000Z\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:local-spring\r\n"
        "SUMMARY:אביב\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260327T100000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260327T110000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:local-fall\r\n"
        "SUMMARY:סתיו\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20261025T100000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20261025T110000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:float-one\r\n"
        "SUMMARY:צף\r\n"
        "DTSTART:20260601T213000\r\n"
        "DTEND:20260602T003000\r\n"
        "END:VEVENT\r\n"
    )
    rows = {row["gcal_uid"]: row for row in parse_ical(body, date(2026, 1, 1), date(2026, 12, 31))}
    assert rows["all-one"]["time"] is None
    assert rows["all-one"]["gregorian_date"] == "2026-04-01"
    assert rows["all-one"]["end_date"] is None
    assert rows["all-one"]["gcal_recurrence_id"] == ""
    assert rows["all-span"]["end_date"] == "2026-04-03"
    assert "מיקום: ים" in rows["all-span"]["description"]
    assert rows["all-span"]["hebrew_date"]
    # חורף UTC+2, קיץ UTC+3. 10:00 מקומי נשאר 10:00 גם במעבר.
    assert (rows["utc-winter"]["gregorian_date"], rows["utc-winter"]["time"]) == ("2026-01-15", "10:00")
    assert (rows["utc-summer"]["gregorian_date"], rows["utc-summer"]["time"]) == ("2026-07-01", "10:00")
    assert rows["local-spring"]["time"] == "10:00"
    assert rows["local-spring"]["gregorian_date"] == "2026-03-27"
    assert rows["local-fall"]["time"] == "10:00"
    assert rows["local-fall"]["gregorian_date"] == "2026-10-25"
    # שעה צפה נחשבת ירושלים, וחצי שעה אחרי חצות נשפכת ליום הבא.
    assert (rows["float-one"]["gregorian_date"], rows["float-one"]["time"]) == ("2026-06-01", "21:30")
    assert rows["float-one"]["end_date"] == "2026-06-02"


def test_parse_recurrence_exdate_and_cancelled():
    body = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:weekly-1\r\n"
        "SUMMARY:שיעור\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260601T090000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260601T100000\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=4\r\n"
        "EXDATE;TZID=Asia/Jerusalem:20260608T090000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:weekly-1\r\n"
        "SUMMARY:בוטל\r\n"
        "STATUS:CANCELLED\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260622T090000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260622T100000\r\n"
        "RECURRENCE-ID;TZID=Asia/Jerusalem:20260622T090000\r\n"
        "END:VEVENT\r\n"
    )
    rows = parse_ical(body, date(2026, 6, 1), date(2026, 6, 30))
    days = [row["gregorian_date"] for row in rows]
    assert days == ["2026-06-01", "2026-06-15"]
    assert len({row["gcal_recurrence_id"] for row in rows}) == 2
    assert all(row["gcal_uid"] == "weekly-1" for row in rows)
    assert all(row["time"] == "09:00" for row in rows)


def test_parse_moved_instance_keeps_original_recurrence_id():
    body = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:moved-1\r\n"
        "SUMMARY:פגישה\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260302T100000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260302T110000\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=2\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:moved-1\r\n"
        "SUMMARY:פגישה הוזזה\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260310T150000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260310T160000\r\n"
        "RECURRENCE-ID;TZID=Asia/Jerusalem:20260309T100000\r\n"
        "END:VEVENT\r\n"
    )
    rows = parse_ical(body, date(2026, 3, 1), date(2026, 3, 31))
    moved = [row for row in rows if row["title"] == "פגישה הוזזה"]
    assert len(moved) == 1
    assert moved[0]["gregorian_date"] == "2026-03-10"
    assert moved[0]["time"] == "15:00"
    original = datetime(2026, 3, 9, 10, 0, tzinfo=JERUSALEM).astimezone(ZoneInfo("UTC"))
    assert moved[0]["gcal_recurrence_id"] == original.strftime("%Y%m%dT%H%M%SZ")


def test_upsert_updates_and_delete_drops_only_in_window(client, app):
    created = _make_source(client)
    assert created.status_code == 201, created.get_json()
    body = created.get_json()
    assert "SECRETVALUE" not in created.get_data(as_text=True)
    assert "ical_url" not in body
    source_id = body["id"]

    first = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:keep\r\n"
        "SUMMARY:נשאר\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260620T180000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260620T190000\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:gone\r\n"
        "SUMMARY:יימחק\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260621T180000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260621T190000\r\n"
        "END:VEVENT\r\n"
    )
    _sync(app, first, source_id=source_id)
    stored = _rows(app)
    assert {row["gcal_uid"] for row in stored} == {"keep", "gone"}
    keep_id = next(row["id"] for row in stored if row["gcal_uid"] == "keep")
    assert all(row["color"] == "#4285f4" for row in stored)
    assert all(row["hebrew_date"] for row in stored)

    with app.app_context():
        from app.database import get_db

        db = get_db()
        db.execute(
            """
            INSERT INTO events (
                title, gregorian_date, hebrew_date, gcal_source_id, gcal_uid, gcal_recurrence_id
            ) VALUES ('ארכיון', '2020-01-01', 'א', ?, 'archive', '')
            """,
            (source_id,),
        )
        db.commit()

    second = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:keep\r\n"
        "SUMMARY:עודכן\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260620T183000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260620T193000\r\n"
        "END:VEVENT\r\n"
    )
    _sync(app, second, source_id=source_id)
    stored = _rows(app)
    uids = {row["gcal_uid"]: row for row in stored}
    assert "gone" not in uids
    assert uids["archive"]["title"] == "ארכיון"
    assert uids["keep"]["id"] == keep_id
    assert uids["keep"]["title"] == "עודכן"
    assert uids["keep"]["time"] == "18:30"


def test_recurring_resync_moves_instance_without_duplicating(client, app):
    source_id = _make_source(client).get_json()["id"]
    first = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:series\r\n"
        "SUMMARY:סדרה\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260601T090000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260601T100000\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=3\r\n"
        "END:VEVENT\r\n"
    )
    _sync(app, first, source_id=source_id)
    before = _rows(app)
    assert len(before) == 3
    assert len({row["id"] for row in before}) == 3

    moved = _ics(
        "BEGIN:VEVENT\r\n"
        "UID:series\r\n"
        "SUMMARY:סדרה\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260601T090000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260601T100000\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=3\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:series\r\n"
        "SUMMARY:הוזז\r\n"
        "DTSTART;TZID=Asia/Jerusalem:20260609T150000\r\n"
        "DTEND;TZID=Asia/Jerusalem:20260609T160000\r\n"
        "RECURRENCE-ID;TZID=Asia/Jerusalem:20260608T090000\r\n"
        "END:VEVENT\r\n"
    )
    _sync(app, moved, source_id=source_id)
    after = _rows(app)
    assert len(after) == 3
    titles = {row["gregorian_date"]: row["title"] for row in after}
    assert titles["2026-06-09"] == "הוזז"
    assert "2026-06-08" not in titles
    assert {row["id"] for row in before} == {row["id"] for row in after}


def test_sync_error_does_not_leak_the_url(client, app, capsys):
    source_id = _make_source(client).get_json()["id"]

    def fetch(url):
        raise GcalUserError(f"נכשל {url}")

    with app.app_context():
        from app.gcal.sync import sync_source

        result = sync_source(source_id, fetch=fetch, today=TODAY)
    assert "SECRETVALUE" not in result["last_error"]
    assert "SECRETVALUE" not in capsys.readouterr().err
    listed = client.get("/api/gcal/sources")
    assert "SECRETVALUE" not in listed.get_data(as_text=True)
    assert "לא" in result["last_error"] or "כתובת הוסרה" in result["last_error"]


def test_api_readonly_search_and_import_keep_google_rows(client, app):
    source_id = _make_source(client).get_json()["id"]
    _sync(
        app,
        _ics(
            "BEGIN:VEVENT\r\n"
            "UID:ro-1\r\n"
            "SUMMARY:מגוגל\r\n"
            "DESCRIPTION:פרטים\r\n"
            "DTSTART;TZID=Asia/Jerusalem:20260618T120000\r\n"
            "DTEND;TZID=Asia/Jerusalem:20260618T130000\r\n"
            "END:VEVENT\r\n"
        ),
        source_id=source_id,
    )
    event_id = _rows(app)[0]["id"]
    forbidden = client.put(
        f"/api/events/{event_id}",
        json={
            "title": "שינוי",
            "gregorian_date": "2026-06-18",
            "hebrew_date": "א",
        },
    )
    assert forbidden.status_code == 403
    assert "לעריכה ביומן גוגל" in forbidden.get_json()["error"]
    assert client.delete(f"/api/events/{event_id}").status_code == 403

    found = client.get("/api/events/search?query=מגוגל").get_json()
    assert len(found) == 1
    assert found[0]["gcal_readonly"] is True
    ranged = client.get("/api/events?from=2026-06-01&to=2026-06-30").get_json()
    assert any(row["id"] == event_id and row["gcal_readonly"] for row in ranged)

    exported = client.get("/api/events/export").get_json()
    assert "SECRETVALUE" not in client.get("/api/events/export").get_data(as_text=True)
    assert "ical_url" not in exported
    local = client.post(
        "/api/events",
        json={"title": "מקומי", "gregorian_date": "2026-06-19", "hebrew_date": "ב"},
    )
    assert local.status_code == 200
    # החלפה מוחקת אירועים מקומיים. אירועי גוגל והפלטה נשארים.
    replaced = client.post(
        "/api/events/import?mode=replace",
        json={"events": [], "colors": exported["colors"]},
    )
    assert replaced.status_code == 200
    titles = {row["title"] for row in client.get("/api/events").get_json()}
    assert "מגוגל" in titles
    assert "מקומי" not in titles

    assert client.delete(f"/api/gcal/sources/{source_id}").status_code == 200
    assert _rows(app) == []


def test_disabled_source_is_skipped_by_the_worker(client, app):
    created = _make_source(client)
    source_id = created.get_json()["id"]
    called = []

    def fetch(url):
        called.append(url)
        return _ics("")

    with app.app_context():
        from app.gcal.sync import sync_enabled

        assert sync_enabled(fetch=fetch, today=TODAY) == []
    assert called == []
    with app.app_context():
        from app.gcal.sync import sync_source

        sync_source(source_id, fetch=fetch, today=TODAY)
    assert called == [SECRET]


def test_create_enabled_syncs_and_response_hides_the_url(client, monkeypatch):
    monkeypatch.setattr(
        "app.gcal.sync.fetch_ical",
        lambda url: _ics(
            "BEGIN:VEVENT\r\n"
            "UID:on-create\r\n"
            "SUMMARY:מיד\r\n"
            "DTSTART;TZID=Asia/Jerusalem:20260618T080000\r\n"
            "DTEND;TZID=Asia/Jerusalem:20260618T090000\r\n"
            "END:VEVENT\r\n"
        ),
    )
    response = _make_source(client, enabled=True)
    assert response.status_code == 201
    body = response.get_json()
    text = response.get_data(as_text=True)
    assert "SECRETVALUE" not in text
    assert "ical_url" not in body
    assert body["event_count"] == 1
    assert body["last_error"] == ""
    assert body["sync"]["inserted"] == 1


def test_fetch_404_is_hebrew_and_hides_the_url(monkeypatch):
    import urllib.error

    secret = SECRET

    class Opener:
        def open(self, request, timeout=0):
            raise urllib.error.HTTPError(request.full_url, 404, "missing", hdrs=None, fp=None)

    monkeypatch.setattr("app.gcal.sync.urllib.request.build_opener", lambda *args, **kwargs: Opener())
    from app.gcal.sync import fetch_ical

    with pytest.raises(GcalUserError) as exc:
        fetch_ical(secret)
    assert "SECRETVALUE" not in str(exc.value)
    assert "לא נמצא" in str(exc.value)


def test_migration_adds_gcal_columns_without_deleting_rows(tmp_path):
    path = tmp_path / "v4.sqlite"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        from app.database import SCHEMA_VERSION, apply_pending_migrations

        apply_pending_migrations(conn)
        conn.execute("PRAGMA user_version = 4")
        conn.execute(
            "INSERT INTO events (title, gregorian_date, hebrew_date) VALUES ('ישן', '2020-01-01', 'א')"
        )
        conn.commit()
        apply_pending_migrations(conn)
        row = conn.execute("SELECT title FROM events").fetchone()
        assert row["title"] == "ישן"
        cols = {info[1] for info in conn.execute("PRAGMA table_info(events)")}
        assert {"gcal_source_id", "gcal_uid", "gcal_recurrence_id"} <= cols
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'gcal_sources'"
        ).fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        apply_pending_migrations(conn)
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    finally:
        conn.close()


def test_bot_lists_google_event_as_readonly(app, client):
    source_id = _make_source(client).get_json()["id"]
    _sync(
        app,
        _ics(
            "BEGIN:VEVENT\r\n"
            "UID:bot-1\r\n"
            "SUMMARY:שיחת גוגל\r\n"
            "DTSTART;TZID=Asia/Jerusalem:20260618T160000\r\n"
            "DTEND;TZID=Asia/Jerusalem:20260618T170000\r\n"
            "END:VEVENT\r\n"
        ),
        source_id=source_id,
    )
    event_id = _rows(app)[0]["id"]
    with app.app_context():
        from app.bot.store import update_user_event
        from app.bot.ui import event_screen
        from app.database import get_event

        event = get_event(event_id)
        text, markup = event_screen(event, {})
        assert "לעריכה ביומן גוגל" in text
        callbacks = [
            button["callback_data"]
            for row in markup["inline_keyboard"]
            for button in row
        ]
        assert not any(item.startswith("ed:") or item.startswith("rm") for item in callbacks)
        status, _saved = update_user_event({"event_id": event_id, "title": "לא", "force": True})
        assert status == "readonly"
        assert get_event(event_id)["title"] == "שיחת גוגל"
