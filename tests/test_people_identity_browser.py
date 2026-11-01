"""בדיקת דפדפן: רשימת אנשים מלאה, מיזוג לפי שם, אזהרת צ׳אט, חסימת מחיקה."""
from __future__ import annotations

import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _seed(client):
    worker = client.post(
        "/api/reminder-people",
        json={
            "name": "שירה",
            "telegram_chat_id": "99",
            "receives_reminders": False,
            "works_shifts": True,
        },
    )
    assert worker.status_code == 201
    danny = client.post(
        "/api/reminder-people",
        json={"name": "דני", "telegram_chat_id": None, "receives_reminders": True},
    )
    assert danny.status_code == 201
    return worker.get_json(), danny.get_json()


def test_settings_lists_all_people_and_reuses_name(live_server, client):
    _seed(client)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_server + "/settings#settings-reminders", wait_until="load")
        page.wait_for_selector("#reminderPeopleList .reminder-person-row")
        rows = page.locator("#reminderPeopleList .reminder-person-row")
        expect(rows).to_have_count(2)
        expect(page.locator("#reminderPeopleList")).to_contain_text("שירה")
        expect(page.locator("#reminderPeopleList")).to_contain_text("דני")
        expect(page.locator("#reminderPeopleList")).to_contain_text("מחובר לטלגרם")
        expect(page.locator("#reminderPeopleList")).to_contain_text("אין קישור לטלגרם")
        expect(page.locator("#reminderPeopleList .reminder-person-flag")).to_have_count(4)

        page.fill("#reminderPersonName", "שירה")
        expect(page.locator("#reminderPersonSuggest")).to_be_visible()
        expect(page.locator("#reminderPersonSuggest")).to_contain_text("כבר יש שירה")
        page.click("#reminderPersonSave")
        expect(rows).to_have_count(2)
        shira = page.locator("#reminderPeopleList .reminder-person-row").filter(has_text="שירה")
        expect(shira.locator('input[aria-label="תזכורות לשירה"]')).to_be_checked()
        expect(shira.locator('input[aria-label="משמרות לשירה"]')).to_be_checked()

        page.fill("#reminderPersonName", "שירה כהן")
        expect(page.locator("#reminderPersonSuggest")).to_contain_text("שם דומה")
        browser.close()


def test_recipient_picker_warns_without_telegram(live_server, client):
    _seed(client)
    client.post(
        "/api/reminder-people",
        json={"name": "שירה", "receives_reminders": True},
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(live_server + "/", wait_until="load")
        page.wait_for_function("() => typeof openQuickEventModal === 'function'")
        page.evaluate("() => openQuickEventModal()")
        page.wait_for_selector("#quickEventModal.show", timeout=10000)
        page.check("#quick_reminder_enabled")
        page.wait_for_selector("#quick_reminder_recipients label")
        expect(page.locator("#quick_reminder_recipients")).to_contain_text("דני")
        expect(page.locator("#quick_reminder_recipients")).to_contain_text("שירה")
        expect(page.locator("#quick_reminder_recipients")).to_contain_text("בלי טלגרם")
        page.locator("#quick_reminder_recipients label").filter(has_text="דני").locator("input").check()
        expect(page.locator("#quick_reminder_chat_warn")).to_be_visible()
        expect(page.locator("#quick_reminder_chat_warn")).to_contain_text("אין קישור לטלגרם")
        browser.close()


def test_delete_blocked_until_reassign(live_server, client):
    worker, danny = _seed(client)
    created = client.post(
        "/api/events",
        json={
            "title": "פגישה",
            "gregorian_date": "2026-06-01",
            "hebrew_date": "א",
            "reminders": [{"offset_minutes": 0, "recipient_ids": [danny["id"]]}],
        },
    )
    assert created.status_code == 200
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(live_server + "/settings#settings-reminders", wait_until="load")
        page.wait_for_selector("#reminderPeopleList .reminder-person-row")
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#reminderPeopleList .reminder-person-row").filter(has_text="דני").locator(
            "text=מחיקה"
        ).click()
        expect(page.locator("#reminderPersonError")).to_contain_text("תזכורות")
        expect(page.locator("#reminderPersonReassign")).to_be_visible()
        page.select_option("#reminderPersonReassignTo", str(worker["id"]))
        page.click("#reminderPersonReassignBtn")
        expect(page.locator("#reminderPeopleList")).not_to_contain_text("דני")
        expect(page.locator("#reminderPeopleList")).to_contain_text("שירה")
        browser.close()
    leftover = client.get("/api/reminder-people").get_json()
    assert [row["name"] for row in leftover] == ["שירה"]
