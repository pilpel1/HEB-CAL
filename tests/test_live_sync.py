"""סנכרון חי: מונה SQLite, SSE, origin, ושרת threaded שלא נחסם."""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from app.live_sync import CLIENT_HEADER, bump_events_revision, generate_live_sync_sse, live_sync_response, read_live_sync_snapshot

REPO = Path(__file__).resolve().parent.parent
SAMPLE = {
    "title": "סנכרון",
    "gregorian_date": "2026-03-14",
    "hebrew_date": "י״ד אדר",
}


def _revision(client) -> int:
    with client.application.app_context():
        return read_live_sync_snapshot()["revision"]


def _parse_sse(raw: str) -> dict:
    event = None
    data = None
    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = json.loads(line.split(":", 1)[1].strip())
    return {"event": event, "data": data}


def test_crud_bumps_revision_and_stores_origin(client):
    assert _revision(client) == 0
    created = client.post(
        "/api/events",
        json=SAMPLE,
        headers={CLIENT_HEADER: "phone-1"},
    )
    assert created.status_code == 200
    event_id = created.get_json()["id"]
    snap = read_live_sync_snapshot()
    assert snap["revision"] == 1
    assert snap["origin"] == "phone-1"
    assert snap["ids"] == [event_id]
    assert snap["action"] == "created"

    updated = client.put(
        f"/api/events/{event_id}",
        json={**SAMPLE, "title": "עודכן"},
        headers={CLIENT_HEADER: "desktop-2"},
    )
    assert updated.status_code == 200
    snap = read_live_sync_snapshot()
    assert snap["revision"] == 2
    assert snap["origin"] == "desktop-2"
    assert snap["action"] == "updated"

    deleted = client.delete(
        f"/api/events/{event_id}",
        headers={CLIENT_HEADER: "phone-1"},
    )
    assert deleted.status_code == 200
    snap = read_live_sync_snapshot()
    assert snap["revision"] == 3
    assert snap["action"] == "deleted"
    assert snap["ids"] == [event_id]


def test_occurrence_edit_and_bot_create_bump(client, app):
    created = client.post(
        "/api/events",
        json={
            **SAMPLE,
            "recurrence_freq": "yearly",
            "recurrence_calendar": "gregorian",
        },
    )
    event_id = created.get_json()["id"]
    before = _revision(client)
    occurrence = client.put(
        f"/api/events/{event_id}",
        json={
            **SAMPLE,
            "title": "רק הפעם",
            "scope": "occurrence",
            "occurrence_date": SAMPLE["gregorian_date"],
        },
    )
    assert occurrence.status_code == 200
    assert _revision(client) == before + 1

    with app.app_context():
        from app.database import create_event

        before = read_live_sync_snapshot()["revision"]
        new_id = create_event("מהבוט", "2026-04-01", "י״ג ניסן")
        assert new_id
        snap = read_live_sync_snapshot()
        assert snap["revision"] == before + 1
        assert snap["origin"] is None
        assert snap["ids"] == [new_id]


def test_import_bumps_once(client):
    before = _revision(client)
    payload = {
        "events": [
            {**SAMPLE, "title": "ייבוא א"},
            {**SAMPLE, "title": "ייבוא ב", "gregorian_date": "2026-03-15"},
        ],
        "colors": [],
    }
    imported = client.post("/api/events/import?mode=merge", json=payload)
    assert imported.status_code == 200
    assert imported.get_json()["success"] is True
    assert _revision(client) == before + 1


def test_invalid_client_id_is_ignored(client):
    created = client.post(
        "/api/events",
        json=SAMPLE,
        headers={CLIENT_HEADER: "not a valid id!!!"},
    )
    assert created.status_code == 200
    snap = read_live_sync_snapshot()
    assert snap["origin"] is None
    assert snap["revision"] == 1


def test_sse_hello_then_changed(app, monkeypatch):
    monkeypatch.setenv("HEB_CAL_LIVE_SYNC_POLL", "0.05")
    monkeypatch.setenv("HEB_CAL_LIVE_SYNC_KEEPALIVE", "5")
    with app.app_context():
        gen = generate_live_sync_sse()
        retry = next(gen)
        hello = next(gen)
        assert "retry:" in retry
        parsed = _parse_sse(hello)
        assert parsed["event"] == "hello"
        assert parsed["data"]["type"] == "hello"
        assert parsed["data"]["revision"] == 0
        bump_events_revision(origin="other-tab", event_ids=[42], action="created")
        changed = next(gen)
        parsed = _parse_sse(changed)
        assert parsed["event"] == "changed"
        assert parsed["data"]["type"] == "changed"
        assert parsed["data"]["origin"] == "other-tab"
        assert parsed["data"]["ids"] == [42]
        assert parsed["data"]["action"] == "created"
        gen.close()


def test_sse_last_event_id_replays_missed_change(app):
    with app.app_context():
        bump_events_revision(origin="gcal", action="changed")
        gen = generate_live_sync_sse(last_event_id="0")
        next(gen)
        hello = next(gen)
        changed = next(gen)
        assert _parse_sse(hello)["data"]["revision"] == 1
        parsed = _parse_sse(changed)
        assert parsed["event"] == "changed"
        assert parsed["data"]["origin"] == "gcal"
        gen.close()


def test_stream_response_headers(app):
    with app.test_request_context("/api/events/stream"):
        response = live_sync_response()
        assert response.mimetype == "text/event-stream"
        assert "no-store" in response.headers["Cache-Control"]
        assert response.headers.get("X-Accel-Buffering") == "no"
        assert response.headers.get("Connection") == "keep-alive"
        gen = response.response
        next(gen)
        hello = next(gen)
        assert "event: hello" in hello
        gen.close()


@pytest.fixture
def threaded_server(app, monkeypatch):
    monkeypatch.setenv("HEB_CAL_LIVE_SYNC_POLL", "0.05")
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()


def test_open_sse_does_not_block_other_requests(threaded_server, client):
    host, port = "127.0.0.1", threaded_server.server_port
    stream = http.client.HTTPConnection(host, port, timeout=5)
    stream.request(
        "GET",
        "/api/events/stream",
        headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
    )
    stream_resp = stream.getresponse()
    assert stream_resp.status == 200
    assert "text/event-stream" in stream_resp.getheader("Content-Type")
    buf = stream_resp.read(64)
    assert buf
    other = http.client.HTTPConnection(host, port, timeout=2)
    other.request("GET", "/api/events")
    other_resp = other.getresponse()
    assert other_resp.status == 200
    body = json.loads(other_resp.read().decode("utf-8"))
    assert isinstance(body, list)
    other.close()
    stream.close()


def test_frontend_connects_without_reload():
    js = (REPO / "app/static/js/core/live-sync.js").read_text(encoding="utf-8")
    assert "EventSource" in js
    assert "/api/events/stream" in js
    assert "X-Heb-Cal-Client" in js
    assert "LIVE_SYNC_DEBOUNCE_MS" in js
    assert "visibilitychange" in js
    assert "refreshEventsViews" in js
    assert "location.reload" not in js
    assert "האירוע עודכן במכשיר אחר" in js
    assert "האירוע נמחק במכשיר אחר" in js
    modal = (REPO / "app/templates/partials/quick_event_modal.html").read_text(encoding="utf-8")
    assert 'id="quick_live_notice"' in modal
    actions = (REPO / "app/static/js/events/event-actions.js").read_text(encoding="utf-8")
    assert "restorePage: true" in actions
    sw = (REPO / "app/static/sw.js").read_text(encoding="utf-8")
    assert "/api/events/stream" in sw
    assert "text/event-stream" in sw
    assert "initLiveSync" in (REPO / "app/static/js/script.js").read_text(encoding="utf-8")
    modalJs = (REPO / "app/static/js/events/quick-event-modal.js").read_text(encoding="utf-8")
    assert "isQuickEventFormDirty" in modalJs
    assert "isQuickEventModalOpen" in modalJs
    assert "getOpenQuickEventId" in modalJs
    base = (REPO / "app/templates/base.html").read_text(encoding="utf-8")
    assert "core/live-sync.js" in base


def test_server_runner_is_explicitly_threaded():
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "--with-threads" in dockerfile
    restart = (REPO / "scripts/restart.sh").read_text(encoding="utf-8")
    assert "--with-threads" in restart
    main = (REPO / "app/main.py").read_text(encoding="utf-8")
    assert "threaded=True" in main
    for path in (REPO / "tests").glob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        if "make_server(" in text:
            assert "threaded=True" in text, path.name


def test_other_tab_repaints_calendar_without_reload(threaded_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    url = f"http://127.0.0.1:{threaded_server.server_port}/"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1400, "height": 900}, locale="he-IL").new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            page.wait_for_function("() => typeof EventSource !== 'undefined' && typeof refreshEventsViews === 'function'")
            page.evaluate("window.__hebCalStay = 1")
            day = page.evaluate("() => getTodayDateStr()")
            created = client.post(
                "/api/events",
                json={"title": "מהמכשיר האחר", "gregorian_date": day, "hebrew_date": "א"},
                headers={CLIENT_HEADER: "other-device"},
            )
            assert created.status_code == 200
            page.wait_for_selector(".event-item:has-text('מהמכשיר האחר')", timeout=8000)
            assert page.evaluate("window.__hebCalStay") == 1
            page.evaluate("() => openQuickEventModal(getTodayDateStr())")
            page.wait_for_selector("#quickEventModal.show")
            page.fill("#quick_title", "טיוטה שלי")
            client.post(
                "/api/events",
                json={
                    "title": "עוד אחד",
                    "gregorian_date": day,
                    "hebrew_date": "א",
                },
                headers={CLIENT_HEADER: "other-device"},
            )
            page.wait_for_selector(".event-item:has-text('עוד אחד')", timeout=8000)
            assert page.locator("#quick_title").input_value() == "טיוטה שלי"
            assert page.locator("#quickEventModal").evaluate("el => el.classList.contains('show')")
            assert page.evaluate("window.__hebCalStay") == 1
        finally:
            browser.close()


def test_events_list_refreshes_in_place(threaded_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    url = f"http://127.0.0.1:{threaded_server.server_port}/events_list"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_context(locale="he-IL").new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function("() => typeof loadAllEvents === 'function'")
            page.evaluate("window.__hebCalStay = 1")
            created = client.post(
                "/api/events",
                json={
                    "title": "ברשימה מרחוק",
                    "gregorian_date": "2026-11-01",
                    "hebrew_date": "א",
                },
                headers={CLIENT_HEADER: "phone-x"},
            )
            assert created.status_code == 200
            page.wait_for_selector("text=ברשימה מרחוק", timeout=8000)
            assert page.evaluate("window.__hebCalStay") == 1
        finally:
            browser.close()
