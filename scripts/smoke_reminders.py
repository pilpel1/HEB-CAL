#!/usr/bin/env python3
"""Smoke של טופס התזכורת ברוחב טלפון (390px).

לא חלק מ-pytest. מול שרת רץ ו-DB זמני:

    DATABASE_PATH=/tmp/reminders.sqlite python -m flask --app app run --port 5000
    python scripts/smoke_reminders.py --base-url http://127.0.0.1:5000
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

from playwright.sync_api import expect, sync_playwright


def api(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or b"null")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--width", type=int, default=390)
    parser.add_argument("--height", type=int, default=844)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    person = api(base, "POST", "/api/reminder-people", {"name": "דני סמוק", "telegram_chat_id": "9001"})
    problems: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            permissions=["notifications"],
        )
        page = context.new_page()
        page.set_default_timeout(8000)
        page.on("pageerror", lambda exc: problems.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda msg: problems.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None,
        )
        page.on(
            "response",
            lambda response: problems.append(f"HTTP {response.status}: {response.url}")
            if response.status >= 400 and not response.url.endswith("favicon.ico")
            else None,
        )

        page.goto(base + "/")
        page.wait_for_selector(".infinite-calendar:not(.is-booting)")

        page.click("#addEventFromCalendarBtn")
        modal = page.locator("#quickEventModal")
        expect(modal).to_be_visible()
        expect(page.locator("#quick_reminder_panel")).to_be_hidden()

        page.click("#quick_reminder_enabled")
        panel = page.locator("#quick_reminder_panel")
        expect(panel).to_be_visible()
        page.click('#quick_reminder_offsets .reminder-offset-chip[data-offset="15"]')
        page.click('#quick_reminder_offsets .reminder-offset-chip[data-offset="10080"]')
        page.click("#quick_reminder_custom_toggle")
        page.fill("#quick_reminder_custom_amount", "4")
        page.select_option("#quick_reminder_custom_unit", "hours")
        page.click("#quick_reminder_custom_add")
        expect(page.locator("#quick_reminder_custom_list")).to_contain_text("4 שעות")
        expect(page.locator(".reminder-people-link")).to_be_visible()
        expect(page.locator("#quick_hebrew_date")).not_to_have_value("")
        recipient = page.locator(f'#quick_reminder_recipients input[value="{person["id"]}"]')
        expect(recipient).to_be_visible()
        recipient.check()

        footer = page.locator("#quickEventModal .modal-footer")
        expect(footer).to_be_visible()
        box = footer.bounding_box()
        assert box and box["y"] + box["height"] <= args.height + 1, box
        modal_box = modal.locator(".modal-content").bounding_box()
        assert modal_box and modal_box["x"] >= -1
        assert modal_box["x"] + modal_box["width"] <= args.width + 1

        page.evaluate("""() => {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            try { localStorage.setItem('heb-cal-theme', 'dark'); } catch (e) {}
        }""")
        theme = page.evaluate("() => document.documentElement.getAttribute('data-bs-theme')")
        assert theme == "dark", theme
        expect(panel).to_be_visible()

        page.fill("#quick_title", "סמוק תזכורת")
        page.click("#quick_submit_btn")
        expect(modal).to_be_hidden()

        events = api(base, "GET", "/api/events")
        match = next(row for row in events if row["title"] == "סמוק תזכורת")
        offsets = sorted(item["offset_minutes"] for item in match["reminders"])
        assert offsets == [15, 240, 10080], offsets
        assert match["reminders"][0]["recipient_ids"] == [person["id"]]

        page.goto(base + "/events_list")
        page.locator(f'#eventsTable button[onclick="editEvent({match["id"]})"]').click()
        expect(modal).to_be_visible()
        expect(page.locator("#quick_reminder_enabled")).to_be_checked()
        expect(page.locator('#quick_reminder_offsets .reminder-offset-chip[data-offset="15"]')).to_have_class(
            re.compile(r"\bis-selected\b")
        )
        expect(page.locator("#quick_reminder_custom_list")).to_contain_text("4 שעות")
        page.click("#quick_reminder_enabled")
        page.click("#quick_submit_btn")
        expect(modal).to_be_hidden()
        cleared = api(base, "GET", f"/api/events/{match['id']}")
        assert cleared["reminders"] == []

        page.goto(base + "/settings")
        expect(page.get_by_role("heading", name="אנשים לתזכורות")).to_be_visible()
        expect(page.locator("#reminderPeopleList")).to_contain_text("דני סמוק")
        expect(page.locator("body")).to_contain_text("/start")
        page.fill("#reminderPersonName", "נועה סמוק")
        page.fill("#reminderPersonChat", "9002")
        page.click("#reminderPersonSave")
        expect(page.locator("#reminderPeopleList")).to_contain_text("נועה סמוק")

        api(base, "DELETE", f"/api/events/{match['id']}")
        browser.close()

    if problems:
        print("\nCONSOLE/JS PROBLEMS:")
        for line in problems:
            print("  " + line)
        return 1
    print("reminder form smoke passed at", args.width)
    return 0


if __name__ == "__main__":
    sys.exit(main())
