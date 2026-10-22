"""הזנת משמרות: מיגרציה, מתג בית, רשת שבוע אידמפוטנטית, וחיים ליד חזרות ותזכורות."""
import json
import sqlite3
from datetime import date

import pytest

from app.services.shifts import default_week_start, shift_title


def _allowed(labels_days):
    base = {"בוקר": [], "ערב": [], "לילה": []}
    base.update(labels_days)
    return base


@pytest.fixture(autouse=True)
def _enable_shifts(client, request):
    """הכתיבה לרשת דורשת מתג דלוק. בדיקת ברירת המחדל נשארת כבויה."""
    if request.node.name == "test_household_toggle_defaults_off":
        yield
        return
    client.put("/api/shifts/settings", json={"enabled": True})
    yield


def _person(client, name="אביחי", **extra):
    payload = {"name": name, "telegram_chat_id": None}
    payload.update(extra)
    response = client.post("/api/reminder-people", json=payload)
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def _week_cells(start, pairs):
    """pairs: list of (offset 0=Sunday, label)."""
    from datetime import timedelta

    cells = []
    for offset, label in pairs:
        cells.append({
            "date": (start + timedelta(days=offset)).isoformat(),
            "label": label,
        })
    return cells


def test_default_week_is_the_week_after_today():
    assert default_week_start(date(2026, 10, 18)) == date(2026, 10, 25)  # Sunday
    assert default_week_start(date(2026, 10, 21)) == date(2026, 10, 25)  # Wednesday
    assert default_week_start(date(2026, 10, 22)) == date(2026, 10, 25)  # Thursday
    assert default_week_start(date(2026, 10, 23)) == date(2026, 10, 25)  # Friday
    assert default_week_start(date(2026, 10, 24)) == date(2026, 10, 25)  # Saturday
    assert default_week_start(date(2026, 10, 25)) == date(2026, 11, 1)  # next Sunday


def test_shift_migration_is_idempotent_and_keeps_rows(tmp_path):
    path = tmp_path / "old.sqlite"
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
        "INSERT INTO events (title, gregorian_date, hebrew_date) VALUES ('ישן', '2024-01-02', 'א')"
    )
    conn.execute(
        """
        CREATE TABLE reminder_people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_chat_id TEXT
        )
        """
    )
    conn.execute("INSERT INTO reminder_people (name, telegram_chat_id) VALUES ('דני', '5')")
    conn.commit()

    from app.services.shifts import ensure_shift_schema

    ensure_shift_schema(conn)
    ensure_shift_schema(conn)
    conn.commit()

    event = conn.execute("SELECT * FROM events").fetchone()
    assert event["title"] == "ישן"
    assert event["is_shift"] == 0
    assert event["shift_person_id"] is None
    assert event["shift_label"] is None
    person = conn.execute("SELECT * FROM reminder_people").fetchone()
    assert person["name"] == "דני"
    assert person["telegram_chat_id"] == "5"
    assert person["color"] is None
    assert person["shift_allowed"] is None
    assert conn.execute("SELECT COUNT(*) FROM household_settings").fetchone()[0] == 1
    assert conn.execute("SELECT shifts_enabled FROM household_settings").fetchone()[0] == 0
    conn.close()


def test_household_toggle_defaults_off(client):
    assert client.get("/api/shifts/settings").get_json() == {"enabled": False}
    turned = client.put("/api/shifts/settings", json={"enabled": True})
    assert turned.status_code == 200
    assert turned.get_json()["enabled"] is True
    assert client.get("/api/shifts/settings").get_json()["enabled"] is True
    off = client.put("/api/shifts/settings", json={"enabled": False})
    assert off.get_json()["enabled"] is False
    bad = client.put("/api/shifts/settings", json={"enabled": "yes"})
    assert bad.status_code == 400


def test_person_color_and_rules_round_trip_without_clobber(client):
    person = _person(
        client,
        color="orange",
        shift_allowed=_allowed({
            "בוקר": [0, 1, 2, 3, 4],
            "ערב": [0, 1, 2, 3, 4],
            "לילה": [],
        }),
    )
    assert person["color"] == "orange"
    assert person["shift_allowed"]["בוקר"] == [0, 1, 2, 3, 4]
    assert person["shift_allowed"]["לילה"] == []
    assert person["works_shifts"] is True
    assert person["receives_reminders"] is True

    with client.application.app_context():
        from app.database import get_db

        stored = get_db().execute(
            "SELECT shift_allowed, works_shifts, receives_reminders FROM reminder_people WHERE id = ?",
            (person["id"],),
        ).fetchone()
    assert stored["shift_allowed"]
    assert "לילה" in stored["shift_allowed"]
    assert stored["works_shifts"] == 1
    assert stored["receives_reminders"] == 1

    renamed = client.put(
        f"/api/reminder-people/{person['id']}",
        json={"name": "אביחי כהן", "telegram_chat_id": "12"},
    )
    assert renamed.status_code == 200
    body = renamed.get_json()
    assert body["name"] == "אביחי כהן"
    assert body["color"] == "orange"
    assert body["shift_allowed"]["לילה"] == []

    bad_color = client.put(
        f"/api/reminder-people/{person['id']}",
        json={"name": "אביחי כהן", "color": "purple"},
    )
    assert bad_color.status_code == 400


def test_person_custom_color_stays_visible_when_delete_is_blocked(client):
    created = client.post("/api/colors", json={"name": "כתום בהיר", "color_code": "#ffcc88"})
    assert created.status_code == 201
    color = created.get_json()
    person = _person(client, name="נועה", color="#FFCC88", receives_reminders=False)
    assert person["color"] == "#ffcc88"
    assert person["works_shifts"] is True

    unknown = client.post(
        "/api/reminder-people",
        json={"name": "זר", "color": "#010203"},
    )
    assert unknown.status_code == 400
    assert "צבע" in unknown.get_json()["error"]

    renamed = client.put(
        f"/api/reminder-people/{person['id']}",
        json={"name": "נועה לוי", "telegram_chat_id": None},
    )
    assert renamed.status_code == 200
    assert renamed.get_json()["color"] == "#ffcc88"

    rejected = client.put(
        f"/api/reminder-people/{person['id']}",
        json={"name": "נועה לוי", "color": "#123456"},
    )
    assert rejected.status_code == 400

    blocked = client.delete(f"/api/colors/{color['id']}")
    assert blocked.status_code == 400
    assert "שימוש" in blocked.get_json()["error"]

    week = date(2026, 10, 18)
    saved = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": week.isoformat(),
        "cells": [{"date": week.isoformat(), "label": "בוקר"}],
    })
    assert saved.status_code == 200, saved.get_json()

    def shown_color():
        events = client.get("/api/events").get_json()
        row = next(
            item for item in events
            if item.get("is_shift") and item.get("shift_person_id") == person["id"]
        )
        return row["color"]

    assert shown_color() == "#ffcc88"
    still_blocked = client.delete(f"/api/colors/{color['id']}")
    assert still_blocked.status_code == 400
    assert shown_color() == "#ffcc88"
    people = client.get("/api/reminder-people").get_json()
    stored = next(row for row in people if row["id"] == person["id"])
    assert stored["color"] == "#ffcc88"

    moved = client.put(
        f"/api/colors/{color['id']}",
        json={"name": "כתום בהיר", "color_code": "#ffaa55"},
    )
    assert moved.status_code == 200
    people = client.get("/api/reminder-people").get_json()
    stored = next(row for row in people if row["id"] == person["id"])
    assert stored["color"] == "#ffaa55"
    assert shown_color() == "#ffaa55"

    exported = json.loads(client.get("/api/events/export").data.decode("utf-8"))
    assert any(row["color_code"] == "#ffaa55" for row in exported["colors"])
    imported = client.post("/api/events/import?mode=replace", json=exported)
    assert imported.status_code == 200, imported.get_json()
    restored = client.get("/api/reminder-people").get_json()
    assert restored[0]["color"] == "#ffaa55"
    assert shown_color() == "#ffaa55"


def test_week_save_is_idempotent_and_only_removes_shifts(client):
    client.put("/api/shifts/settings", json={"enabled": True})
    avihai = _person(
        client,
        name="אביחי",
        color="cyan",
        shift_allowed=_allowed({
            "בוקר": [0, 1, 2, 3, 4],
            "ערב": [0, 1, 2, 3, 4, 5, 6],
            "לילה": [],
        }),
    )
    noa = _person(
        client,
        name="נועה",
        color="yellow",
        shift_allowed=_allowed({
            "בוקר": [],
            "ערב": [5, 6],
            "לילה": [5, 6],
        }),
    )
    week = date(2026, 10, 18)  # Sunday
    cells = _week_cells(week, [(0, "בוקר"), (3, "ערב"), (4, "בוקר")])

    first = client.put("/api/shifts/week", json={
        "person_id": avihai["id"],
        "week_start": week.isoformat(),
        "cells": cells,
    })
    assert first.status_code == 200, first.get_json()
    created_ids = first.get_json()["created"]
    assert len(created_ids) == 3

    events = client.get("/api/events").get_json()
    shifts = [row for row in events if row["is_shift"]]
    assert len(shifts) == 3
    sunday = next(row for row in shifts if row["gregorian_date"] == "2026-10-18")
    assert sunday["title"] == shift_title("אביחי", "בוקר")
    assert sunday["color"] == "cyan"
    assert sunday["time"] is None
    assert sunday["end_date"] is None
    assert sunday["shift_label"] == "בוקר"
    assert sunday["shift_person_id"] == avihai["id"]
    assert sunday["hebrew_date"]
    assert sunday["recurrence_freq"] is None

    second = client.put("/api/shifts/week", json={
        "person_id": avihai["id"],
        "week_start": week.isoformat(),
        "cells": cells,
    })
    assert second.status_code == 200
    body = second.get_json()
    assert body["created"] == []
    assert body["deleted"] == []
    assert sorted(body["kept"]) == sorted(created_ids)
    assert len(client.get("/api/events").get_json()) == 3

    # עריכת הכותרת לא מורידה את הסימון. הסוג נשאר «בוקר», והכותרת נשמרת.
    edited = client.put(f"/api/events/{sunday['id']}", json={
        "title": "אביחי בבוקר מוקדם",
        "gregorian_date": sunday["gregorian_date"],
        "hebrew_date": sunday["hebrew_date"],
        "color": "cyan",
    })
    assert edited.status_code == 200
    shown = client.get(f"/api/events/{sunday['id']}").get_json()
    assert shown["title"] == "אביחי בבוקר מוקדם"
    assert shown["shift_label"] == "בוקר"
    assert shown["is_shift"] == 1
    again = client.put("/api/shifts/week", json={
        "person_id": avihai["id"],
        "week_start": week.isoformat(),
        "cells": cells,
    })
    assert again.get_json()["created"] == []
    kept_title = client.get(f"/api/events/{sunday['id']}").get_json()
    assert kept_title["title"] == "אביחי בבוקר מוקדם"
    assert kept_title["shift_label"] == "בוקר"
    assert kept_title["is_shift"] == 1

    manual = client.post("/api/events", json={
        "title": shift_title("אביחי", "בוקר"),
        "gregorian_date": "2026-10-19",
        "hebrew_date": "יד",
        "color": "green",
    })
    assert manual.status_code == 200
    manual_id = manual.get_json()["id"]

    # כיבוי יום ראשון מוחק רק את המשמרת, לא את האירוע הרגיל עם אותה כותרת
    trimmed = client.put("/api/shifts/week", json={
        "person_id": avihai["id"],
        "week_start": week.isoformat(),
        "cells": _week_cells(week, [(3, "ערב"), (4, "בוקר")]),
    })
    assert sunday["id"] in trimmed.get_json()["deleted"]
    left = {row["id"]: row for row in client.get("/api/events").get_json()}
    assert sunday["id"] not in left
    assert left[manual_id]["is_shift"] == 0
    assert left[manual_id]["title"] == shift_title("אביחי", "בוקר")

    # נועה לא רואה ולא מוחקת את המשמרות של אביחי
    noa_view = client.get(
        f"/api/shifts/week?person_id={noa['id']}&week_start={week.isoformat()}"
    ).get_json()
    assert all(day["checked"] == [] for day in noa_view["days"])
    assert "לילה" in noa_view["days"][5]["allowed"]
    assert noa_view["days"][0]["allowed"] == []

    noa_save = client.put("/api/shifts/week", json={
        "person_id": noa["id"],
        "week_start": week.isoformat(),
        "cells": _week_cells(week, [(5, "לילה"), (6, "ערב")]),
    })
    assert noa_save.status_code == 200
    titles = {row["title"] for row in client.get("/api/events").get_json()}
    assert shift_title("נועה", "לילה") in titles
    assert shift_title("אביחי", "ערב") in titles

    # לילה באמצע השבוע אסור לנועה, וגם בוקר ביום ראשון אסור לאביחי
    blocked = client.put("/api/shifts/week", json={
        "person_id": noa["id"],
        "week_start": week.isoformat(),
        "cells": _week_cells(week, [(3, "לילה")]),
    })
    assert blocked.status_code == 400
    weekend_morning = client.put("/api/shifts/week", json={
        "person_id": avihai["id"],
        "week_start": "2026-10-21",
        "cells": [],
    })
    assert weekend_morning.status_code == 400

    view = client.get(
        f"/api/shifts/week?person_id={avihai['id']}&week_start={week.isoformat()}"
    ).get_json()
    by_date = {day["date"]: day for day in view["days"]}
    assert by_date["2026-10-18"]["checked"] == []
    assert "בוקר" not in by_date["2026-10-23"]["allowed"]  # Friday
    assert by_date["2026-10-21"]["checked"] == ["ערב"]


def test_disallowed_existing_shift_is_kept_when_still_checked(client):
    person = _person(client, name="אביחי", color="green", shift_allowed=_allowed({
        "בוקר": list(range(7)),
        "ערב": [],
        "לילה": [],
    }))
    week = "2026-10-18"
    saved = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": week,
        "cells": [{"date": "2026-10-24", "label": "בוקר"}],
    })
    assert saved.status_code == 200
    shift_id = saved.get_json()["created"][0]

    client.put(f"/api/reminder-people/{person['id']}", json={
        "name": "אביחי",
        "shift_allowed": _allowed({"בוקר": [0, 1, 2, 3, 4], "ערב": [], "לילה": []}),
    })
    view = client.get(f"/api/shifts/week?person_id={person['id']}&week_start={week}").get_json()
    saturday = next(day for day in view["days"] if day["date"] == "2026-10-24")
    assert saturday["checked"] == ["בוקר"]
    assert "בוקר" not in saturday["allowed"]

    kept = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": week,
        "cells": [{"date": "2026-10-24", "label": "בוקר"}],
    })
    assert kept.status_code == 200
    assert kept.get_json()["kept"] == [shift_id]
    assert client.get(f"/api/events/{shift_id}").status_code == 200


def test_shifts_merge_with_recurrence_and_keep_reminders(client):
    person = _person(client, name="אביחי", color="orange")
    week = "2026-10-18"
    saved = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": week,
        "cells": [{"date": "2026-10-20", "label": "ערב"}],
    })
    shift_id = saved.get_json()["created"][0]
    shift = client.get(f"/api/events/{shift_id}").get_json()

    reminded = client.put(f"/api/events/{shift_id}", json={
        **{key: shift[key] for key in ("title", "gregorian_date", "hebrew_date", "color")},
        "reminders": [{"offset_minutes": 60, "recipient_ids": [person["id"]]}],
    })
    assert reminded.status_code == 200
    after = client.get(f"/api/events/{shift_id}").get_json()
    assert after["is_shift"] == 1
    assert after["shift_label"] == "ערב"
    assert after["reminders"][0]["offset_minutes"] == 60
    assert after["reminders"][0]["recipient_ids"] == [person["id"]]

    series = client.post("/api/events", json={
        "title": "יום הולדת",
        "gregorian_date": "2026-10-20",
        "hebrew_date": "א",
        "recurrence_freq": "yearly",
        "recurrence_calendar": "gregorian",
        "recurrence_count": 2,
    })
    assert series.status_code == 200

    merged = client.get("/api/events?from=2026-10-18&to=2026-10-24").get_json()
    same_day = [row for row in merged if row["gregorian_date"] == "2026-10-20"]
    assert len(same_day) == 2
    assert any(
        row["title"] == shift_title("אביחי", "ערב") and row.get("is_shift") == 1 and not row.get("recurrence_freq")
        for row in same_day
    )
    assert any(row["title"] == "יום הולדת" and row["recurrence_freq"] == "yearly" for row in same_day)

    client.delete(f"/api/reminder-people/{person['id']}")
    still = client.get(f"/api/events/{shift_id}").get_json()
    assert still["title"] == shift_title("אביחי", "ערב")
    assert still["is_shift"] == 1


def test_export_import_round_trip_keeps_shift_flag_and_toggle(client):
    client.put("/api/shifts/settings", json={"enabled": True})
    person = _person(client, name="אביחי", color="cyan", shift_allowed=_allowed({
        "בוקר": [1, 2, 3],
        "ערב": [],
        "לילה": [0],
    }))
    client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-19", "label": "בוקר"}],
    })
    exported = json.loads(client.get("/api/events/export").data.decode("utf-8"))
    assert exported["shifts_enabled"] is True
    assert exported["reminder_people"][0]["color"] == "cyan"
    assert exported["reminder_people"][0]["shift_allowed"]["בוקר"] == [1, 2, 3]
    shift = next(row for row in exported["events"] if row["is_shift"])
    assert shift["shift_label"] == "בוקר"
    assert shift["shift_person_id"] == person["id"]

    client.put("/api/shifts/settings", json={"enabled": False})
    client.post("/api/events", json={
        "title": "רעש",
        "gregorian_date": "2026-01-01",
        "hebrew_date": "א",
    })
    imported = client.post("/api/events/import?mode=replace", json=exported)
    assert imported.status_code == 200, imported.get_json()
    assert client.get("/api/shifts/settings").get_json()["enabled"] is True
    restored = client.get("/api/events").get_json()
    assert len(restored) == 1
    assert restored[0]["is_shift"] == 1
    assert restored[0]["shift_label"] == "בוקר"
    people = client.get("/api/reminder-people").get_json()
    assert people[0]["color"] == "cyan"
    assert people[0]["shift_allowed"]["לילה"] == [0]

    # ייבוא ישן בלי המפתח לא מכבה מתג שכבר דלוק
    client.post("/api/events/import?mode=merge", json={
        "events": [{
            "title": "ישן",
            "gregorian_date": "2020-02-02",
            "hebrew_date": "ב",
        }],
        "colors": [],
    })
    assert client.get("/api/shifts/settings").get_json()["enabled"] is True
    old_event = next(row for row in client.get("/api/events").get_json() if row["title"] == "ישן")
    assert old_event["is_shift"] == 0


def test_new_disallowed_cell_is_rejected_in_hebrew(client):
    person = _person(client, name="אביחי", color="cyan", shift_allowed=_allowed({
        "בוקר": [0, 1, 2, 3, 4],
        "ערב": [0, 1, 2, 3, 4],
        "לילה": [],
    }))
    blocked = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-23", "label": "בוקר"}],
    })
    assert blocked.status_code == 400
    error = blocked.get_json()["error"]
    assert "בוקר" in error
    assert "שישי" in error
    assert "אביחי" in error
    assert client.get("/api/events").get_json() == []

    night = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-20", "label": "לילה"}],
    })
    assert night.status_code == 400
    assert "לילה" in night.get_json()["error"]
    assert "שלישי" in night.get_json()["error"]

    ok = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-21", "label": "בוקר"}],
    })
    assert ok.status_code == 200, ok.get_json()
    event = client.get(f"/api/events/{ok.get_json()['created'][0]}").get_json()
    assert event["title"] == "בוקר"
    assert event["color"] == "cyan"


def test_week_header_has_hebrew_range_and_parasha(client):
    from app.services.shifts import hebrew_day_month, week_parasha

    person = _person(client, name="אביחי", shift_allowed=_allowed({
        "בוקר": [0, 1, 2, 3, 4],
        "ערב": [0, 1, 2, 3, 4],
        "לילה": [],
    }))
    view = client.get(
        f"/api/shifts/week?person_id={person['id']}&week_start=2026-10-18"
    ).get_json()
    assert view["hebrew_range"] == f"{hebrew_day_month(date(2026, 10, 18))} – {hebrew_day_month(date(2026, 10, 24))}"
    parasha = week_parasha(date(2026, 10, 24))
    assert parasha
    assert view["parasha"] == parasha
    assert view["week_title"] == f"{view['hebrew_range']} · פרשת {parasha}"
    sunday = view["days"][0]
    assert sunday["hebrew"]
    assert sunday["hebrew_day"]
    assert sunday["hebrew_month"]
    assert sunday["hebrew"] == f"{sunday['hebrew_day']} {sunday['hebrew_month']}"
    friday = next(day for day in view["days"] if day["date"] == "2026-10-23")
    assert friday["allowed"] == []
    wednesday = next(day for day in view["days"] if day["date"] == "2026-10-21")
    assert wednesday["allowed"] == ["בוקר", "ערב"]


def test_shift_color_follows_person_even_when_the_row_has_none(client):
    person = _person(client, name="אביחי", shift_allowed=_allowed({"בוקר": [0, 1, 2, 3, 4]}))
    saved = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-21", "label": "בוקר"}],
    })
    shift_id = saved.get_json()["created"][0]
    bare = client.get(f"/api/events/{shift_id}").get_json()
    assert bare["title"] == "בוקר"
    assert bare["color"] in (None, "")

    client.put(f"/api/reminder-people/{person['id']}", json={"name": "אביחי", "color": "orange"})
    painted = client.get(f"/api/events/{shift_id}").get_json()
    assert painted["color"] == "orange"
    assert painted["title"] == "בוקר"
    ranged = client.get("/api/events?from=2026-10-18&to=2026-10-24").get_json()
    chip = next(row for row in ranged if row["id"] == shift_id)
    assert chip["title"] == "בוקר"
    assert chip["color"] == "orange"


def test_normalize_rewrites_old_shift_title_and_copies_color(client):
    person = _person(client, name="אביחי", color="cyan", shift_allowed=_allowed({"בוקר": [0]}))
    saved = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-18", "label": "בוקר"}],
    })
    shift_id = saved.get_json()["created"][0]
    with client.application.app_context():
        from app.database import get_db
        from app.services.shifts import normalize_shift_events

        db = get_db()
        db.execute(
            "UPDATE events SET title = ?, color = NULL WHERE id = ?",
            ("אביחי — בוקר", shift_id),
        )
        db.execute(
            "INSERT INTO events (title, gregorian_date, hebrew_date, is_shift) VALUES ('יום הולדת', '2026-01-01', 'א', 0)"
        )
        db.execute(
            """
            INSERT INTO events (
                title, gregorian_date, hebrew_date, is_shift, shift_person_id, shift_label
            ) VALUES ('בוקר מוקדם', '2026-10-19', 'ב', 1, ?, 'בוקר')
            """,
            (person["id"],),
        )
        db.commit()
        normalize_shift_events(db)
        normalize_shift_events(db)
        db.commit()
        row = db.execute("SELECT title, color FROM events WHERE id = ?", (shift_id,)).fetchone()
        assert row["title"] == "בוקר"
        assert row["color"] == "cyan"
        plain = db.execute("SELECT title FROM events WHERE title = 'יום הולדת'").fetchone()
        assert plain["title"] == "יום הולדת"
        custom = db.execute(
            "SELECT title, shift_label FROM events WHERE gregorian_date = '2026-10-19'"
        ).fetchone()
        assert custom["title"] == "בוקר מוקדם"
        assert custom["shift_label"] == "בוקר"
    shown = client.get(f"/api/events/{shift_id}").get_json()
    assert shown["title"] == "בוקר"
    assert shown["color"] == "cyan"


def test_manual_shift_is_allowed_outside_the_rules(client):
    person = _person(client, name="אביחי", color="cyan", shift_allowed=_allowed({
        "בוקר": [0, 1, 2, 3, 4],
        "ערב": [0, 1, 2, 3, 4],
        "לילה": [],
    }))
    created = client.post("/api/events", json={
        "title": "חריג",
        "gregorian_date": "2026-10-23",
        "hebrew_date": "ב",
        "time": "23:00",
        "end_date": "2026-10-24",
        "color": "green",
        "recurrence_freq": "yearly",
        "recurrence_calendar": "gregorian",
        "is_shift": True,
        "shift_person_id": person["id"],
        "shift_label": "לילה",
    })
    assert created.status_code == 200, created.get_json()
    event = client.get(f"/api/events/{created.get_json()['id']}").get_json()
    assert event["is_shift"] == 1
    assert event["shift_person_id"] == person["id"]
    assert event["shift_label"] == "לילה"
    assert event["title"] == "חריג"
    assert event["color"] == "cyan"
    assert event["time"] is None
    assert event["end_date"] is None
    assert event["recurrence_freq"] is None

    blocked = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-23", "label": "בוקר"}],
    })
    assert blocked.status_code == 400
    assert "שישי" in blocked.get_json()["error"]

    view = client.get(
        f"/api/shifts/week?person_id={person['id']}&week_start=2026-10-18"
    ).get_json()
    friday = next(day for day in view["days"] if day["date"] == "2026-10-23")
    assert "לילה" in friday["checked"]
    assert "לילה" not in friday["allowed"]
    kept = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-23", "label": "לילה"}],
    })
    assert kept.status_code == 200, kept.get_json()
    assert event["id"] in kept.get_json()["kept"]

    missing = client.post("/api/events", json={
        "title": "בוקר",
        "gregorian_date": "2026-10-20",
        "hebrew_date": "א",
        "is_shift": True,
        "shift_label": "בוקר",
    })
    assert missing.status_code == 400
    assert "בחרו" in missing.get_json()["error"]

    cleared = client.put(f"/api/events/{event['id']}", json={
        "title": "כבר לא משמרת",
        "gregorian_date": "2026-10-23",
        "hebrew_date": event["hebrew_date"],
        "is_shift": False,
    })
    assert cleared.status_code == 200
    plain = client.get(f"/api/events/{event['id']}").get_json()
    assert plain["is_shift"] == 0
    assert plain["shift_label"] is None
    assert plain["title"] == "כבר לא משמרת"


def test_free_text_shift_survives_grid_resave(client):
    person = _person(client, name="אביחי", color="orange", shift_allowed=_allowed({
        "בוקר": [0, 1, 2, 3, 4],
        "ערב": [],
        "לילה": [],
    }))
    created = client.post("/api/events", json={
        "title": "משהו אחר",
        "gregorian_date": "2026-10-21",
        "hebrew_date": "א",
        "color": "green",
        "is_shift": True,
        "shift_person_id": person["id"],
        "shift_label": "יום מחלה",
    })
    assert created.status_code == 200, created.get_json()
    shift_id = created.get_json()["id"]
    event = client.get(f"/api/events/{shift_id}").get_json()
    assert event["title"] == "משהו אחר"
    assert event["shift_label"] == "יום מחלה"
    assert event["color"] == "orange"
    assert event["is_shift"] == 1

    morning = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-21", "label": "בוקר"}],
    })
    assert morning.status_code == 200, morning.get_json()
    morning_id = morning.get_json()["created"][0]

    wiped = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [],
    })
    assert wiped.status_code == 200, wiped.get_json()
    assert morning_id in wiped.get_json()["deleted"]
    left = {row["id"]: row for row in client.get("/api/events").get_json()}
    assert morning_id not in left
    assert left[shift_id]["title"] == "משהו אחר"
    assert left[shift_id]["shift_label"] == "יום מחלה"
    assert left[shift_id]["color"] == "orange"
    assert left[shift_id]["is_shift"] == 1

    view = client.get(
        f"/api/shifts/week?person_id={person['id']}&week_start=2026-10-18"
    ).get_json()
    wednesday = next(day for day in view["days"] if day["date"] == "2026-10-21")
    assert wednesday["checked"] == []

    empty = client.post("/api/events", json={
        "title": "ריק",
        "gregorian_date": "2026-10-22",
        "hebrew_date": "ב",
        "is_shift": True,
        "shift_person_id": person["id"],
        "shift_label": "   ",
    })
    assert empty.status_code == 400
    assert "כתבו" in empty.get_json()["error"]

    grid_label = client.put("/api/shifts/week", json={
        "person_id": person["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-21", "label": "יום מחלה"}],
    })
    assert grid_label.status_code == 400


def test_calendar_and_settings_markup(client):
    calendar = client.get("/").get_data(as_text=True)
    assert 'id="enterShiftsBtn"' in calendar
    assert "הזן משמרות" not in calendar
    assert 'class="shift-grid-icon"' in calendar
    assert "fa-user-clock" not in calendar
    plus = calendar.index('id="addEventFromCalendarBtn"')
    shifts = calendar.index('id="enterShiftsBtn"')
    listing = calendar.index('id="calendarEventsLink"')
    assert plus < shifts < listing
    assert 'class="btn btn-outline-secondary settings-gear-btn"' in calendar
    assert 'aria-label="הגדרות"' in calendar
    assert 'href="/settings"' in calendar
    assert 'id="quick-settings"' not in calendar
    assert 'aria-label="היום"' in calendar
    assert 'aria-label="דלג לתאריך"' in calendar
    assert 'aria-label="הוסף אירוע"' in calendar
    assert 'aria-label="רשימת אירועים"' in calendar
    assert 'aria-label="משמרות"' in calendar
    assert 'id="header-collapse"' in calendar
    assert 'header-collapse-chevron' in calendar
    assert 'header-collapse-grip' not in calendar
    assert 'heb-cal-header-collapsed' in calendar
    assert 'id="current-month"' in calendar
    assert 'id="shiftEntryModal"' in calendar
    assert 'id="quick_shift_enabled"' in calendar
    assert "הכותרת היא מה שכתוב כאן" not in calendar
    assert 'type="hidden" id="quick_shift_label"' in calendar
    assert 'placeholder="יום מחלה, יום חופש…"' not in calendar
    assert 'id="quick_hebrew_day"' in calendar
    assert 'id="quick_hebrew_month"' in calendar
    assert 'id="quick_hebrew_year"' in calendar
    assert '>תאריך עברי</label>' not in calendar
    assert 'aria-label="תאריך עברי"' in calendar
    assert 'aria-label="הגדרות תזכורות"' in calendar
    assert 'href="/settings#settings-reminders"' in calendar
    assert 'class="reminder-people-link"' not in calendar
    settings = client.get("/settings").get_data(as_text=True)
    assert 'id="shiftsEnabled"' in settings
    assert 'id="settings-shifts-title">משמרות</h2>' in settings
    assert settings.count(">משמרות</h2>") == 1
    assert "הפעלת משמרות בבית הזה" not in settings
    assert "אנשים למשמרות" not in settings
    assert 'id="personShiftMatrix"' in settings
    assert 'id="shiftPeoplePanel"' in settings
    assert 'id="shiftPersonSave"' in settings
    assert 'id="shiftPersonForm"' in settings
    assert 'id="shiftPersonContext"' in settings
    reminder_form = settings.split('id="reminderPersonForm"')[1].split('id="shiftSettings"')[0]
    assert 'id="personShiftMatrix"' not in reminder_form
    assert 'id="reminderPersonName"' in reminder_form
    assert 'id="reminderPersonChat"' in reminder_form
    assert ">שמור<" in settings.split('id="shiftPersonSave"')[1][:80]
    assert 'data-theme-switch' in settings
    assert 'data-density-switch' in settings
    assert "מצב כהה" in settings
    assert "תצוגה צפופה" in settings
    assert "גיבוי וייבוא" in settings
    assert 'id="exportEventsBtn"' in settings
    assert 'id="importEventsBtn"' in settings
    assert "צבעים" in settings
    assert 'id="settingsColors"' in settings
    assert settings.count("data-theme-switch") == 1
    events_list = client.get("/events_list").get_data(as_text=True)
    assert 'id="searchInput"' in events_list
    assert 'id="addEventFromListBtn"' in events_list
    assert '>תזכורות</a>' not in events_list
    assert 'aria-label="הגדרות תזכורות"' in events_list
    assert 'href="/settings#settings-reminders"' in events_list
    assert "חזרה ללוח" in events_list
    assert 'id="eventsToolsBtn"' not in events_list
    assert "data-theme-toggle" not in events_list
    assert 'id="exportEventsBtn"' not in events_list
    assert 'id="pageSizeSelect"' in events_list
    assert 'id="sortOrderSelect"' in events_list
    assert '<h2 class="h5">תזכורות</h2>' in settings
    assert 'id="settings-reminders"' in settings
    assert "אנשים לתזכורות" not in settings
    assert 'id="chatIdHelpBtn"' in settings
    assert 'aria-label="איך מקבלים מזהה צ׳אט"' in settings
    label = settings.index('<label for="reminderPersonChat" class="form-label">מזהה צ׳אט</label>')
    help_btn = settings.index('id="chatIdHelpBtn"')
    help_pop = settings.index('id="chatIdHelp"')
    assert label < help_btn < help_pop
    assert "TELEGRAM_BOT_TOKEN" in settings[help_pop:help_pop + 1200]
    assert '<h2 class="h5">איך מקבלים מזהה צ׳אט</h2>' not in settings
    shifts_js = client.get("/static/js/events/shifts.js").get_data(as_text=True)
    assert "function persistEditedShiftRules" not in shifts_js
    assert "function saveShiftPerson" in shifts_js
    assert "beforeunload" in shifts_js
    people_js = client.get("/static/js/events/reminder-people.js").get_data(as_text=True)
    assert "personShiftPayload" not in people_js
    assert "receives_reminders" in people_js


def test_people_role_filters_and_api_validation(client):
    reminder = _person(client, name="דני", telegram_chat_id="11")
    shifter = client.post(
        "/api/reminder-people",
        json={
            "name": "אביחי",
            "color": "cyan",
            "shift_allowed": _allowed({"בוקר": [0]}),
            "receives_reminders": False,
            "works_shifts": True,
        },
    ).get_json()
    both = _person(
        client,
        name="נועה",
        telegram_chat_id="22",
        color="yellow",
        shift_allowed=_allowed({"ערב": [1]}),
    )

    reminder_names = {
        row["name"] for row in client.get("/api/reminder-people?role=reminders").get_json()
    }
    assert reminder_names == {"דני", "נועה"}
    shift_names = {
        row["name"] for row in client.get("/api/reminder-people?role=shifts").get_json()
    }
    assert shift_names == {"אביחי", "נועה"}
    assert client.get("/api/reminder-people?role=nope").status_code == 400

    blocked_recipient = client.post(
        "/api/events",
        json={
            "title": "פגישה",
            "gregorian_date": "2026-10-18",
            "hebrew_date": "א",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [shifter["id"]]}],
        },
    )
    assert blocked_recipient.status_code == 400

    ok_event = client.post(
        "/api/events",
        json={
            "title": "פגישה",
            "gregorian_date": "2026-10-18",
            "hebrew_date": "א",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [reminder["id"]]}],
        },
    )
    assert ok_event.status_code == 200, ok_event.get_json()

    blocked_week = client.put("/api/shifts/week", json={
        "person_id": reminder["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-18", "label": "בוקר"}],
    })
    assert blocked_week.status_code == 400
    assert "רשימת המשמרות" in blocked_week.get_json()["error"]

    ok_week = client.put("/api/shifts/week", json={
        "person_id": shifter["id"],
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-18", "label": "בוקר"}],
    })
    assert ok_week.status_code == 200, ok_week.get_json()
    assert both["id"]


def test_put_shift_allowed_persists_and_round_trips(client):
    person = _person(client, name="אביחי", telegram_chat_id="5")
    assert person["works_shifts"] is False
    allowed = _allowed({"בוקר": [0, 1, 2, 3, 4], "ערב": [], "לילה": []})
    updated = client.put(
        f"/api/reminder-people/{person['id']}",
        json={
            "name": "אביחי",
            "telegram_chat_id": "5",
            "color": "green",
            "shift_allowed": allowed,
            "works_shifts": True,
            "receives_reminders": True,
        },
    )
    assert updated.status_code == 200, updated.get_json()
    body = updated.get_json()
    assert body["works_shifts"] is True
    assert body["shift_allowed"]["בוקר"] == [0, 1, 2, 3, 4]
    assert body["shift_allowed"]["לילה"] == []

    listed = client.get("/api/reminder-people?role=shifts").get_json()
    match = next(row for row in listed if row["id"] == person["id"])
    assert match["shift_allowed"]["בוקר"] == [0, 1, 2, 3, 4]
    assert match["color"] == "green"

    with client.application.app_context():
        from app.database import get_db

        row = get_db().execute(
            "SELECT shift_allowed, works_shifts FROM reminder_people WHERE id = ?",
            (person["id"],),
        ).fetchone()
    assert row["works_shifts"] == 1
    stored = json.loads(row["shift_allowed"])
    assert stored["בוקר"] == [0, 1, 2, 3, 4]
    assert stored["לילה"] == []
