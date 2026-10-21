"""CRUD לאירועים + ייבוא/ייצוא JSON דרך ה-API."""
import json

SAMPLE_EVENT = {
    "title": "אירוע בדיקה",
    "gregorian_date": "2025-03-14",
    "hebrew_date": "י״ד אדר 5785",
    "time": "10:30",
    "description": "תיאור לבדיקה",
    "color": "cyan",
}


def _find_event_id(client, title: str) -> int:
    response = client.get("/api/events")
    assert response.status_code == 200
    for row in response.get_json():
        if row["title"] == title:
            return row["id"]
    raise AssertionError(f"event with title {title!r} not found")


def test_events_crud_round_trip(client):
    create = client.post("/api/events", json=SAMPLE_EVENT)
    assert create.status_code == 200
    assert create.get_json()["success"] is True

    event_id = _find_event_id(client, SAMPLE_EVENT["title"])

    got = client.get(f"/api/events/{event_id}")
    assert got.status_code == 200
    body = got.get_json()
    assert body["title"] == SAMPLE_EVENT["title"]
    assert body["gregorian_date"] == SAMPLE_EVENT["gregorian_date"]
    assert body["hebrew_date"] == "י״ד אדר תשפ״ה"
    assert body["time"] == SAMPLE_EVENT["time"]
    assert body["description"] == SAMPLE_EVENT["description"]
    assert body["color"] == SAMPLE_EVENT["color"]

    updated = {
        **SAMPLE_EVENT,
        "title": "אירוע מעודכן",
        "description": "תיאור חדש",
    }
    put = client.put(f"/api/events/{event_id}", json=updated)
    assert put.status_code == 200

    after_update = client.get(f"/api/events/{event_id}").get_json()
    assert after_update["title"] == "אירוע מעודכן"
    assert after_update["description"] == "תיאור חדש"

    delete = client.delete(f"/api/events/{event_id}")
    assert delete.status_code == 200
    assert delete.get_json()["success"] is True

    missing = client.get(f"/api/events/{event_id}")
    assert missing.status_code == 404


def test_export_import_json_round_trip(client):
    create = client.post("/api/events", json=SAMPLE_EVENT)
    assert create.status_code == 200
    event_id = _find_event_id(client, SAMPLE_EVENT["title"])

    export_resp = client.get("/api/events/export")
    assert export_resp.status_code == 200
    exported = json.loads(export_resp.data.decode("utf-8"))
    assert exported["version"] == 1
    assert any(e["id"] == event_id and e["title"] == SAMPLE_EVENT["title"] for e in exported["events"])
    assert any(c["color_code"] == "cyan" for c in exported["colors"])

    noise = client.post(
        "/api/events",
        json={
            **SAMPLE_EVENT,
            "title": "אירוע זמני",
            "gregorian_date": "2025-03-15",
        },
    )
    assert noise.status_code == 200

    import_resp = client.post(
        "/api/events/import?mode=replace",
        json={"events": exported["events"], "colors": exported["colors"]},
    )
    assert import_resp.status_code == 200
    result = import_resp.get_json()
    assert result["success"] is True
    assert result["mode"] == "replace"
    assert result["imported_events"] == len(exported["events"])

    all_events = client.get("/api/events").get_json()
    titles = {e["title"] for e in all_events}
    assert titles == {SAMPLE_EVENT["title"]}

    restored_id = _find_event_id(client, SAMPLE_EVENT["title"])
    restored = client.get(f"/api/events/{restored_id}").get_json()
    assert restored["gregorian_date"] == SAMPLE_EVENT["gregorian_date"]
    assert restored["hebrew_date"] == "י״ד אדר תשפ״ה"
