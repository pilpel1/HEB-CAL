"""גוון ימים שעברו בלוח, כולל מצב כהה. צריך Chromium."""
from __future__ import annotations

import datetime as dt
import threading
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

JERUSALEM = ZoneInfo("Asia/Jerusalem")


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _jerusalem_today() -> dt.date:
    return dt.datetime.now(JERUSALEM).date()


def test_past_days_tinted_today_untouched(live_server, client):
    today = _jerusalem_today()
    yesterday = today - dt.timedelta(days=1)
    created = client.post("/api/events", json={
        "title": "אתמול צבעוני",
        "gregorian_date": yesterday.isoformat(),
        "hebrew_date": "אתמול",
        "color": "green",
    })
    assert created.status_code == 200

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1400, "height": 900}, locale="he-IL").new_page()
        try:
            page.goto(live_server + "/", wait_until="domcontentloaded")
            page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
            page.wait_for_selector("td.current-day", timeout=10000)
            page.wait_for_selector("td.past-day .event-item", timeout=10000)

            light = page.evaluate("""() => {
                const today = getTodayDateStr();
                const cells = [...document.querySelectorAll('td[data-date]')];
                const current = document.querySelector('td.current-day');
                const rgb = (el) => getComputedStyle(el).backgroundColor;
                const past = cells.filter((c) => c.dataset.date < today);
                const future = cells.filter((c) => c.dataset.date > today);
                const event = document.querySelector('td.past-day .event-item');
                return {
                    jsToday: today,
                    currentDate: current && current.dataset.date,
                    currentIsPast: current && current.classList.contains('past-day'),
                    pastMarked: past.length > 0 && past.every((c) => c.classList.contains('past-day')),
                    futureClean: future.every((c) => !c.classList.contains('past-day') && !c.classList.contains('current-day')),
                    pastBg: rgb(document.querySelector('td.past-day')),
                    todayBg: rgb(current),
                    futureBg: future[0] ? rgb(future[0]) : null,
                    eventOpacity: event ? getComputedStyle(event).opacity : null,
                    eventBg: event ? rgb(event) : null,
                };
            }""")
            assert light["jsToday"] == today.isoformat()
            assert light["currentDate"] == today.isoformat()
            assert light["currentIsPast"] is False
            assert light["pastMarked"] is True
            assert light["futureClean"] is True
            assert light["pastBg"] != light["todayBg"]
            assert light["pastBg"] != light["futureBg"]
            assert light["eventOpacity"] == "1"
            assert "0, 128, 0" in light["eventBg"]

            dark = page.evaluate("""() => {
                document.documentElement.setAttribute('data-bs-theme', 'dark');
                const rgb = (el) => getComputedStyle(el).backgroundColor;
                const current = document.querySelector('td.current-day');
                const event = document.querySelector('td.past-day .event-item');
                return {
                    pastBg: rgb(document.querySelector('td.past-day')),
                    todayBg: rgb(current),
                    eventOpacity: event ? getComputedStyle(event).opacity : null,
                    eventBg: event ? rgb(event) : null,
                };
            }""")
            assert dark["pastBg"] != dark["todayBg"]
            assert dark["eventOpacity"] == "1"
            assert "0, 128, 0" in dark["eventBg"]
        finally:
            browser.close()
