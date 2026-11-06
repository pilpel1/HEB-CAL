"""כלי האירועים של MCP מול אותו מסלול של ה-REST: חזרות, עברית, גוגל ומשמרות."""
from __future__ import annotations

from mcp_support import add_user, db_snapshot, make_key, ok, tool_error

DAY = "2026-12-02"


def _setup(app):
    user = add_user(app)
    return make_key(app, user, "write")


def _rest(client, event_id, occurrence=None):
    path = f"/api/events/{event_id}"
    if occurrence:
        path += f"?occurrence_date={occurrence}"
    response = client.get(path)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _range(client, start, end):
    response = client.get(f"/api/events?from={start}&to={end}")
    assert response.status_code == 200
    return response.get_json()


def test_one_off_create_matches_rest_and_partial_update(app, client):
    token = _setup(app)
    created = ok(client, token, "create_event", {
        "title": "רופא",
        "date": "02.12.2026",
        "time": "09:30",
        "description": "בדיקה",
        "end_date": "2026-12-03",
    })
    event_id = created["event"]["id"]
    stored = _rest(client, event_id)
    assert stored["title"] == "רופא"
    assert stored["gregorian_date"] == DAY
    assert stored["time"] == "09:30"
    assert stored["end_date"] == "2026-12-03"
    assert stored["hebrew_date"]
    assert created["event"]["hebrew_date"] == stored["hebrew_date"]

    updated = ok(client, token, "update_event", {"event_id": event_id, "title": "רופא שיניים"})
    assert updated["event"]["title"] == "רופא שיניים"
    assert updated["event"]["time"] == "09:30"
    assert updated["event"]["gregorian_date"] == DAY
    assert updated["exceptions_cleared"] is False
    assert _rest(client, event_id)["description"] == "בדיקה"

    listed = ok(client, token, "list_events", {"from": DAY, "to": "2026-12-03"})
    rest_rows = _range(client, DAY, "2026-12-03")
    assert [row["title"] for row in listed["events"]] == ["רופא שיניים"]
    assert [row["gregorian_date"][:10] for row in rest_rows] == [row["gregorian_date"] for row in listed["events"]]
    assert listed["events"][0]["end_date"] == rest_rows[0]["end_date"][:10]


def test_hebrew_date_input_and_convert_date(app, client):
    token = _setup(app)
    created = ok(client, token, "create_event", {"title": "יום הולדת", "date": "י״ג חשון תשפ״ז"})
    event = created["event"]
    assert "חשון" in event["hebrew_date"]
    assert event["gregorian_date"] == "2026-10-24"
    converted = ok(client, token, "convert_date", {"date": event["gregorian_date"]})
    assert converted["hebrew_date"] == event["hebrew_date"]
    assert converted["gregorian_date"] == "2026-10-24"
    assert "יום" in converted["weekday"]
    again = ok(client, token, "convert_date", {"date": "י״ג חשון תשפ״ז"})
    assert again["gregorian_date"] == "2026-10-24"


def test_weekly_series_occurrence_edit_and_delete_match_rest(app, client):
    token = _setup(app)
    created = ok(client, token, "create_event", {
        "title": "ספורט",
        "date": "2026-12-01",
        "time": "18:00",
        "recurrence": {"freq": "weekly", "calendar": "gregorian", "count": 4},
    })
    event_id = created["event"]["id"]
    assert created["event"]["recurrence"]["freq"] == "weekly"

    missing = tool_error(client, token, "update_event", {"event_id": event_id, "title": "בלי scope"})
    assert missing["code"] == "scope_required"
    assert _rest(client, event_id)["title"] == "ספורט"

    moved = ok(client, token, "update_event", {
        "event_id": event_id,
        "scope": "occurrence",
        "occurrence_date": "2026-12-08",
        "title": "ספורט — רק היום",
        "date": "2026-12-09",
    })
    assert moved["scope"] == "occurrence"
    assert moved["exceptions_cleared"] is False
    via_rest = _rest(client, event_id, "2026-12-08")
    via_mcp = ok(client, token, "get_event", {"event_id": event_id, "occurrence_date": "2026-12-08"})["event"]
    assert via_mcp["title"] == via_rest["title"] == "ספורט — רק היום"
    assert via_mcp["gregorian_date"] == via_rest["gregorian_date"][:10] == "2026-12-09"
    assert _rest(client, event_id)["title"] == "ספורט"

    deleted = ok(client, token, "delete_event", {
        "event_id": event_id,
        "scope": "occurrence",
        "occurrence_date": "2026-12-15",
    })
    assert deleted == {"deleted": True, "scope": "occurrence", "event_id": event_id, "occurrence_date": "2026-12-15"}
    assert tool_error(client, token, "get_event", {"event_id": event_id, "occurrence_date": "2026-12-15"})["code"] == "not_found"
    listed = ok(client, token, "list_events", {"from": "2026-12-01", "to": "2026-12-22"})
    dates = [row["occurrence_date"] for row in listed["events"]]
    assert dates == ["2026-12-01", "2026-12-08", "2026-12-22"]
    assert [row["gregorian_date"] for row in _range(client, "2026-12-01", "2026-12-22")] == [
        "2026-12-01", "2026-12-09", "2026-12-22",
    ]


def test_series_date_change_clears_exceptions(app, client):
    token = _setup(app)
    event_id = ok(client, token, "create_event", {
        "title": "חודשי",
        "date": "2026-12-01",
        "recurrence": {"freq": "monthly", "calendar": "hebrew"},
    })["event"]["id"]
    ok(client, token, "update_event", {
        "event_id": event_id,
        "scope": "occurrence",
        "occurrence_date": "2026-12-01",
        "title": "חריג",
    })
    changed = ok(client, token, "update_event", {
        "event_id": event_id,
        "scope": "all",
        "date": "2026-12-02",
    })
    assert changed["exceptions_cleared"] is True
    assert changed["event"]["gregorian_date"] == "2026-12-02"
    assert _rest(client, event_id)["exceptions"] == []
    assert "חשון" in changed["event"]["hebrew_date"] or "כסלו" in changed["event"]["hebrew_date"]


def test_search_without_range_returns_the_series(app, client):
    token = _setup(app)
    ok(client, token, "create_event", {
        "title": "חוג",
        "date": "2026-12-01",
        "description": "שחייה",
        "recurrence": {"freq": "weekly"},
    })
    found = ok(client, token, "search_events", {"query": "שחייה"})
    assert found["count"] == 1
    assert found["events"][0]["recurring"] is True
    ranged = ok(client, token, "search_events", {"query": "חוג", "from": "2026-12-01", "to": "2026-12-21"})
    assert ranged["count"] == 3


def test_google_event_is_read_only(app, client):
    token = _setup(app)
    with app.app_context():
        from app.database import get_db

        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO events (
                title, gregorian_date, hebrew_date, gcal_source_id, gcal_uid, gcal_recurrence_id
            ) VALUES ('מהגוגל', '2026-12-04', 'יום', 1, 'uid-1', '')
            """
        )
        db.commit()
        event_id = cursor.lastrowid
    before = db_snapshot(app)
    shown = ok(client, token, "get_event", {"event_id": event_id})["event"]
    assert shown["read_only"] is True
    assert shown["source"] == "google"
    for name, arguments in (
        ("update_event", {"event_id": event_id, "title": "שינוי"}),
        ("delete_event", {"event_id": event_id}),
    ):
        error = tool_error(client, token, name, arguments)
        assert error["code"] == "read_only"
        assert "גוגל" in error["message"]
    assert db_snapshot(app) == before


def test_shift_is_read_only(app, client):
    token = _setup(app)
    person = client.post("/api/reminder-people", json={"name": "אביחי", "works_shifts": True}).get_json()
    assert client.put("/api/shifts/settings", json={"enabled": True}).status_code == 200
    created = client.post("/api/events", json={
        "title": "משמרת",
        "gregorian_date": "2026-12-06",
        "hebrew_date": "יום",
        "is_shift": True,
        "shift_person_id": person["id"],
        "shift_label": "בוקר",
    })
    assert created.status_code == 200, created.get_json()
    event_id = created.get_json()["id"]
    shown = ok(client, token, "list_events", {"from": "2026-12-06", "to": "2026-12-06"})["events"][0]
    assert shown["is_shift"] is True
    assert shown["read_only_reason"] == "shift"
    before = db_snapshot(app)
    error = tool_error(client, token, "delete_event", {"event_id": event_id})
    assert error["code"] == "read_only"
    assert "משמרות" in error["message"]
    assert db_snapshot(app) == before


def test_delete_series_and_validation_errors(app, client):
    token = _setup(app)
    event_id = ok(client, token, "create_event", {"title": "חד פעמי", "date": "2026-12-01"})["event"]["id"]
    assert ok(client, token, "delete_event", {"event_id": event_id})["scope"] == "all"
    assert tool_error(client, token, "get_event", {"event_id": event_id})["code"] == "not_found"
    assert tool_error(client, token, "create_event", {"title": " ", "date": "2026-12-01"})["code"] == "invalid_input"
    assert tool_error(client, token, "list_events", {"from": "2026-12-02", "to": "2026-12-01"})["code"] == "invalid_input"
    assert tool_error(client, token, "create_event", {"title": "רחוק", "date": "לא תאריך"})["code"] == "invalid_input"
