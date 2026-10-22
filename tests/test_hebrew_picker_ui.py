"""בורר עברי במודל: אדר לפי השנה, וברירת מחדל של לוח החזרה לפי הבורר האחרון."""
from __future__ import annotations

import json
import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

# י״ד אדר תשפ״ו (שנה פשוטה) — 2026-03-03
PLAIN_ADAR = "2026-03-03"
# י״ד אדר ב׳ תשפ״ז
ADAR_II = "2027-03-23"


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _month_names(page):
    return page.evaluate(
        """() => [...document.getElementById('quick_hebrew_month').options].map((option) => option.textContent)"""
    )


def test_picker_adar_and_recurrence_calendar_follow_the_user(live_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(live_server + "/events_list", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof openQuickEventModal === 'function'")
        page.evaluate(
            """async (day) => { await openQuickEventModal(day); }""",
            PLAIN_ADAR,
        )
        page.wait_for_function(
            """() => {
                const month = document.getElementById('quick_hebrew_month');
                const year = document.getElementById('quick_hebrew_year');
                return month && year && year.value === '5786' && month.options.length === 12;
            }"""
        )
        names = _month_names(page)
        assert names.count("אדר") == 1
        assert "אדר א׳" not in names
        assert "אדר ב׳" not in names
        assert page.locator("#quick_hebrew_month").input_value() == "12"

        page.select_option("#quick_hebrew_year", "5787")
        page.wait_for_function(
            """() => {
                const month = document.getElementById('quick_hebrew_month');
                return month && month.value === '13' && month.options.length === 13;
            }"""
        )
        names = _month_names(page)
        assert "אדר א׳" in names
        assert "אדר ב׳" in names
        assert "אדר" not in names
        expect(page.locator("#quick_gregorian_date")).to_have_value(ADAR_II)

        page.select_option("#quick_hebrew_month", "12")
        page.wait_for_function(
            """() => document.getElementById('quick_hebrew_month').value === '12'
                && document.getElementById('quick_hebrew_year').value === '5787'"""
        )
        page.select_option("#quick_hebrew_year", "5786")
        page.wait_for_function(
            """() => {
                const month = document.getElementById('quick_hebrew_month');
                const names = [...month.options].map((option) => option.textContent);
                return month.value === '12' && names.includes('אדר') && !names.includes('אדר ב׳');
            }"""
        )

        page.select_option("#quick_hebrew_year", "5787")
        page.wait_for_function(
            "() => document.getElementById('quick_hebrew_month').value === '13'"
        )
        page.select_option("#quick_recurrence_freq", "yearly")
        expect(page.locator("#quick_recurrence_calendar")).to_have_value("hebrew")

        page.locator("#quick_gregorian_date").fill("2026-06-01")
        page.locator("#quick_gregorian_date").dispatch_event("change")
        expect(page.locator("#quick_recurrence_calendar")).to_have_value("gregorian")

        page.select_option("#quick_recurrence_calendar", "hebrew")
        page.locator("#quick_gregorian_date").fill("2026-07-01")
        page.locator("#quick_gregorian_date").dispatch_event("change")
        expect(page.locator("#quick_recurrence_calendar")).to_have_value("hebrew")
        page.wait_for_function(
            """() => document.getElementById('quick_hebrew_year').value === '5786'"""
        )
        expect(page.locator("#quick_recurrence_calendar")).to_have_value("hebrew")

        created = page.request.post(
            live_server + "/api/events",
            data=json.dumps({
                "title": "יום הולדת לועזי",
                "gregorian_date": PLAIN_ADAR,
                "hebrew_date": "יד אדר",
                "recurrence_freq": "yearly",
                "recurrence_calendar": "gregorian",
            }),
            headers={"Content-Type": "application/json"},
        )
        assert created.ok
        event_id = created.json()["id"]
        page.evaluate(
            """async (id) => { await openEditEventModal(id); }""",
            event_id,
        )
        page.wait_for_function(
            """() => document.getElementById('quick_recurrence_calendar').value === 'gregorian'
                && document.getElementById('quick_event_id').value"""
        )
        page.select_option("#quick_hebrew_day", "2")
        expect(page.locator("#quick_recurrence_calendar")).to_have_value("gregorian")
        page.locator("#quick_gregorian_date").fill("2026-08-01")
        page.locator("#quick_gregorian_date").dispatch_event("change")
        expect(page.locator("#quick_recurrence_calendar")).to_have_value("gregorian")

        assert errors == [], errors
        browser.close()
