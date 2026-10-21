"""חזרות: קצוות עבריים/לועזיים, חריגות, מיגרציה, ותזכורת per-occurrence."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pyluach.dates import GregorianDate, HebrewDate, Rounding
from pyluach.hebrewcal import Month, Year

from app.services.recurrence import (
    RecurrenceError,
    clean_recurrence,
    expand_event,
    nth_start,
)

TZ = ZoneInfo("Asia/Jerusalem")
REPO = Path(__file__).resolve().parent.parent


def _iso(day: date) -> str:
    return day.isoformat()


def _dates(event, **kwargs):
    rows = expand_event(event, kwargs.get("exceptions"), kwargs["start"], kwargs["end"])
    return [row["gregorian_date"] for row in rows]


def _event(anchor: date, freq, calendar_name, **extra):
    heb = GregorianDate(anchor.year, anchor.month, anchor.day).to_heb()
    return {
        "id": extra.pop("id", 1),
        "title": extra.pop("title", "חוזר"),
        "gregorian_date": anchor.isoformat(),
        "hebrew_date": f"{heb.day} {heb.month}",
        "time": extra.pop("time", None),
        "description": "",
        "end_date": extra.pop("end_date", None),
        "color": None,
        "recurrence_freq": freq,
        "recurrence_calendar": calendar_name,
        "recurrence_until": extra.pop("recurrence_until", None),
        "recurrence_count": extra.pop("recurrence_count", None),
        "reminders": [],
        **extra,
    }


def test_gregorian_feb29_and_monthly_31():
    leap = date(2024, 2, 29)
    assert nth_start(leap, "yearly", "gregorian", 1) == date(2025, 2, 28)
    assert nth_start(leap, "yearly", "gregorian", 4) == date(2028, 2, 29)

    anchor = date(2026, 1, 31)
    assert nth_start(anchor, "monthly", "gregorian", 1) == date(2026, 2, 28)
    assert nth_start(anchor, "monthly", "gregorian", 2) == date(2026, 3, 31)
    assert nth_start(anchor, "monthly", "gregorian", 3) == date(2026, 4, 30)

    rows = _dates(
        _event(anchor, "monthly", "gregorian", recurrence_count=4),
        start=date(2026, 1, 1),
        end=date(2026, 12, 31),
    )
    assert rows == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_hebrew_30_cheshvan_and_kislev_use_last_day_of_month():
    """ל׳ חשוון/כסלו בשנה קצרה → כ״ט באותו חודש, לא א׳ בחודש הבא."""
    assert len(Month(5780, 8)) == 30 and len(Month(5780, 9)) == 30
    assert len(Month(5784, 8)) == 29 and len(Month(5784, 9)) == 29

    cheshvan = HebrewDate(5780, 8, 30).to_greg()
    anchor = date(cheshvan.year, cheshvan.month, cheshvan.day)
    landed = nth_start(anchor, "yearly", "hebrew", 4)
    heb = GregorianDate(landed.year, landed.month, landed.day).to_heb()
    assert (heb.year, heb.month, heb.day) == (5784, 8, 29)
    # לא א׳ כסלו
    assert heb.month != 9

    kislev = HebrewDate(5780, 9, 30).to_greg()
    k_anchor = date(kislev.year, kislev.month, kislev.day)
    k_landed = nth_start(k_anchor, "yearly", "hebrew", 4)
    k_heb = GregorianDate(k_landed.year, k_landed.month, k_landed.day).to_heb()
    assert (k_heb.year, k_heb.month, k_heb.day) == (5784, 9, 29)

    # pyluach ברירת המחדל היא היום הבא; אנחנו במפורש PREVIOUS_DAY
    default_round = HebrewDate(5780, 8, 30).add(years=4)
    assert default_round.month == 9 and default_round.day == 1
    previous = HebrewDate(5780, 8, 30).add(years=4, rounding=Rounding.PREVIOUS_DAY)
    assert (previous.month, previous.day) == (8, 29)


def test_adar_yahrzeit_rules():
    """אדר פשוט → אדר ב׳ במעוברת. אדר א׳/ב׳ נשארים, ובשנה פשוטה שניהם באדר."""
    assert Year(5785).leap is False
    assert Year(5787).leap is True
    assert Year(5788).leap is False
    assert Year(5790).leap is True

    plain = HebrewDate(5785, 12, 14).to_greg()
    plain_anchor = date(plain.year, plain.month, plain.day)
    in_leap = nth_start(plain_anchor, "yearly", "hebrew", 2)  # 5787
    in_plain = nth_start(plain_anchor, "yearly", "hebrew", 3)  # 5788
    leap_heb = GregorianDate(in_leap.year, in_leap.month, in_leap.day).to_heb()
    plain_heb = GregorianDate(in_plain.year, in_plain.month, in_plain.day).to_heb()
    assert (leap_heb.year, leap_heb.month, leap_heb.day) == (5787, 13, 14)
    assert (plain_heb.year, plain_heb.month, plain_heb.day) == (5788, 12, 14)

    adar1 = HebrewDate(5787, 12, 14).to_greg()
    adar1_anchor = date(adar1.year, adar1.month, adar1.day)
    adar1_plain = GregorianDate(*nth_start(adar1_anchor, "yearly", "hebrew", 1).timetuple()[:3]).to_heb()
    adar1_leap = GregorianDate(*nth_start(adar1_anchor, "yearly", "hebrew", 3).timetuple()[:3]).to_heb()
    assert (adar1_plain.year, adar1_plain.month, adar1_plain.day) == (5788, 12, 14)
    assert (adar1_leap.year, adar1_leap.month, adar1_leap.day) == (5790, 12, 14)

    adar2 = HebrewDate(5787, 13, 14).to_greg()
    adar2_anchor = date(adar2.year, adar2.month, adar2.day)
    adar2_plain = GregorianDate(*nth_start(adar2_anchor, "yearly", "hebrew", 1).timetuple()[:3]).to_heb()
    adar2_leap = GregorianDate(*nth_start(adar2_anchor, "yearly", "hebrew", 3).timetuple()[:3]).to_heb()
    assert (adar2_plain.year, adar2_plain.month, adar2_plain.day) == (5788, 12, 14)
    assert (adar2_leap.year, adar2_leap.month, adar2_leap.day) == (5790, 13, 14)


def test_until_count_and_plain_event_unchanged():
    anchor = date(2026, 5, 10)
    counted = _dates(
        _event(anchor, "monthly", "gregorian", recurrence_count=3),
        start=date(2026, 1, 1),
        end=date(2027, 1, 1),
    )
    assert counted == ["2026-05-10", "2026-06-10", "2026-07-10"]

    until = _dates(
        _event(anchor, "monthly", "gregorian", recurrence_until="2026-07-10"),
        start=date(2026, 1, 1),
        end=date(2027, 1, 1),
    )
    assert until == ["2026-05-10", "2026-06-10", "2026-07-10"]
    assert "2026-08-10" not in until

    once = {
        "id": 7,
        "title": "חד פעמי",
        "gregorian_date": "2026-05-10",
        "hebrew_date": "שמור",
        "time": None,
        "description": "",
        "end_date": None,
        "color": None,
        "recurrence_freq": None,
        "recurrence_calendar": None,
        "recurrence_until": None,
        "recurrence_count": None,
    }
    rows = expand_event(once, [], date(2026, 5, 1), date(2026, 5, 31))
    assert len(rows) == 1
    assert rows[0]["gregorian_date"] == "2026-05-10"
    assert rows[0]["hebrew_date"] == "שמור"
    assert rows[0]["recurring"] is False
    assert expand_event(once, [], date(2026, 6, 1), date(2026, 6, 30)) == []

    with pytest.raises(RecurrenceError):
        clean_recurrence("weekly", "gregorian", None, None, anchor)
    with pytest.raises(RecurrenceError):
        clean_recurrence("yearly", "gregorian", "2026-05-01", None, anchor)
    with pytest.raises(RecurrenceError):
        clean_recurrence("yearly", "gregorian", None, 0, anchor)


def test_exceptions_delete_and_move_one_occurrence():
    event = _event(date(2026, 1, 10), "monthly", "gregorian", recurrence_count=4)
    deleted = _dates(
        event,
        exceptions=[{"original_date": "2026-02-10", "kind": "deleted"}],
        start=date(2026, 1, 1),
        end=date(2026, 6, 1),
    )
    assert deleted == ["2026-01-10", "2026-03-10", "2026-04-10"]

    moved = expand_event(
        event,
        [{
            "original_date": "2026-03-10",
            "kind": "edited",
            "title": "הוזז",
            "gregorian_date": "2026-03-12",
            "hebrew_date": "אחר",
            "time": "18:00",
            "description": "רק הפעם",
            "end_date": None,
            "color": "green",
        }],
        date(2026, 3, 1),
        date(2026, 3, 31),
    )
    assert [row["gregorian_date"] for row in moved] == ["2026-03-12"]
    assert moved[0]["title"] == "הוזז"
    assert moved[0]["time"] == "18:00"
    assert moved[0]["occurrence_date"] == "2026-03-10"
    assert moved[0]["is_exception"] is True
    # המופע המקורי לא מופיע בנוסף
    assert "2026-03-10" not in [row["gregorian_date"] for row in moved]


def test_schema_migration_is_idempotent_and_keeps_rows(tmp_path):
    from app.database import ensure_recurrence_schema
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
        "INSERT INTO events (title, gregorian_date, hebrew_date) VALUES ('ישן', '2020-01-02', 'ה טבת')"
    )
    conn.commit()

    ensure_reminder_schema(conn)
    ensure_recurrence_schema(conn)
    ensure_recurrence_schema(conn)
    conn.commit()

    row = conn.execute("SELECT * FROM events").fetchone()
    assert row["title"] == "ישן"
    assert row["gregorian_date"] == "2020-01-02"
    assert row["recurrence_freq"] is None
    assert row["recurrence_calendar"] is None
    assert row["recurrence_until"] is None
    assert row["recurrence_count"] is None
    assert conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 1
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='event_exceptions'"
    ).fetchone()
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reminder_sends'"
    ).fetchone()
    conn.close()

    env = dict(os.environ)
    env["DATABASE_PATH"] = str(path)
    script = REPO / "scripts" / "migrate_recurrence.py"
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, str(script), "--database", str(path)],
            cwd=REPO,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "recurrence schema ok" in completed.stdout

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    assert conn.execute("SELECT title FROM events").fetchone()["title"] == "ישן"
    assert conn.execute("SELECT recurrence_freq FROM events").fetchone()[0] is None
    conn.close()


def test_api_expands_range_and_scopes_edit_delete(client):
    created = client.post(
        "/api/events",
        json={
            "title": "יום הולדת",
            "gregorian_date": "2026-01-31",
            "hebrew_date": "אדר",
            "time": "09:00",
            "recurrence_freq": "monthly",
            "recurrence_calendar": "gregorian",
            "recurrence_count": 3,
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    masters = client.get("/api/events").get_json()
    assert len(masters) == 1
    assert masters[0]["recurrence_freq"] == "monthly"
    assert masters[0]["recurrence_count"] == 3
    assert masters[0]["exceptions"] == []

    expanded = client.get("/api/events?from=2026-01-01&to=2026-12-31").get_json()
    assert [row["gregorian_date"] for row in expanded] == [
        "2026-01-31",
        "2026-02-28",
        "2026-03-31",
    ]
    assert all(row["id"] == event_id for row in expanded)
    assert all(row["recurring"] is True for row in expanded)

    # אירוע בלי חזרה נשאר שורה אחת גם בטווח
    plain = client.post(
        "/api/events",
        json={"title": "חד", "gregorian_date": "2026-02-02", "hebrew_date": "א"},
    )
    assert plain.status_code == 200
    both = client.get("/api/events?from=2026-02-01&to=2026-02-28").get_json()
    assert {row["title"] for row in both} == {"יום הולדת", "חד"}

    moved = client.put(
        f"/api/events/{event_id}",
        json={
            "title": "יום הולדת מוזז",
            "gregorian_date": "2026-02-27",
            "hebrew_date": "אחר",
            "time": "11:00",
            "scope": "occurrence",
            "occurrence_date": "2026-02-28",
        },
    )
    assert moved.status_code == 200
    feb = client.get("/api/events?from=2026-02-01&to=2026-03-31").get_json()
    by_date = {row["gregorian_date"]: row for row in feb if row["title"].startswith("יום")}
    assert "2026-02-28" not in by_date
    assert by_date["2026-02-27"]["title"] == "יום הולדת מוזז"
    assert by_date["2026-02-27"]["occurrence_date"] == "2026-02-28"
    assert by_date["2026-03-31"]["title"] == "יום הולדת"

    master = client.get(f"/api/events/{event_id}").get_json()
    assert master["title"] == "יום הולדת"
    assert master["gregorian_date"] == "2026-01-31"
    occurrence = client.get(f"/api/events/{event_id}?occurrence_date=2026-02-28").get_json()
    assert occurrence["gregorian_date"] == "2026-02-27"
    assert occurrence["series"]["gregorian_date"] == "2026-01-31"

    removed = client.delete(
        f"/api/events/{event_id}?scope=occurrence&occurrence_date=2026-03-31"
    )
    assert removed.status_code == 200
    march = client.get("/api/events?from=2026-03-01&to=2026-03-31").get_json()
    assert all(row["id"] != event_id for row in march)

    still = client.get(f"/api/events/{event_id}").get_json()
    assert still["title"] == "יום הולדת"

    deleted = client.delete(f"/api/events/{event_id}")
    assert deleted.status_code == 200
    left = client.get("/api/events").get_json()
    assert [row["title"] for row in left] == ["חד"]


def test_reminders_fire_per_occurrence(client, app):
    from app.reminders.due import telegram_due
    from app.reminders.repository import mark_reminder_sent
    from app.reminders.worker import process_due_reminders

    person = client.post(
        "/api/reminder-people",
        json={"name": "דני", "telegram_chat_id": "777"},
    ).get_json()
    created = client.post(
        "/api/events",
        json={
            "title": "טסט חודשי",
            "gregorian_date": "2026-01-31",
            "hebrew_date": "א",
            "time": "10:00",
            "recurrence_freq": "monthly",
            "recurrence_calendar": "gregorian",
            "recurrence_count": 3,
            "reminders": [{"offset_minutes": 0, "recipient_ids": [person["id"]]}],
        },
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]

    jan = datetime(2026, 1, 31, 10, 0, tzinfo=TZ)
    feb = datetime(2026, 2, 28, 10, 0, tzinfo=TZ)
    with app.app_context():
        due = telegram_due(now=jan)
        assert len(due) == 1
        assert due[0]["event_id"] == event_id
        assert due[0]["occurrence_date"] == "2026-01-31"
        assert "2026-01-31" in due[0]["text"]

        sent = []

        def fake_send(token, chat_id, text):
            sent.append(text)
            return True

        assert process_due_reminders(now=jan, send=fake_send, token="t") == 1
        assert telegram_due(now=jan) == []
        assert "2026-01-31" in sent[0]

        nxt = telegram_due(now=feb)
        assert len(nxt) == 1
        assert nxt[0]["occurrence_date"] == "2026-02-28"
        assert "2026-02-28" in nxt[0]["text"]
        mark_reminder_sent(nxt[0]["id"], occurrence_date=nxt[0]["occurrence_date"])
        assert telegram_due(now=feb) == []
        # ינואר לא נשלח שוב
        assert telegram_due(now=jan) == []


def test_export_round_trip_keeps_rule_and_exception(client):
    import json

    created = client.post(
        "/api/events",
        json={
            "title": "יארצייט",
            "gregorian_date": "2025-03-14",
            "hebrew_date": "יד אדר",
            "recurrence_freq": "yearly",
            "recurrence_calendar": "hebrew",
        },
    )
    event_id = created.get_json()["id"]
    client.delete(f"/api/events/{event_id}?scope=occurrence&occurrence_date=2026-03-03")

    exported = json.loads(client.get("/api/events/export").data.decode("utf-8"))
    match = next(row for row in exported["events"] if row["id"] == event_id)
    assert match["recurrence_freq"] == "yearly"
    assert match["recurrence_calendar"] == "hebrew"
    assert any(ex["kind"] == "deleted" for ex in match["exceptions"])

    imported = client.post("/api/events/import?mode=replace", json=exported)
    assert imported.status_code == 200
    restored = client.get("/api/events").get_json()
    assert len(restored) == 1
    assert restored[0]["recurrence_calendar"] == "hebrew"
    assert restored[0]["exceptions"][0]["kind"] == "deleted"
