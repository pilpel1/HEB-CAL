"""מצב פשוט במודל אירוע: שורה אחת, «מתקדם», והגדרה לכל מכשיר ב-localStorage."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODAL_HTML = (REPO / "app/templates/partials/quick_event_modal.html").read_text(encoding="utf-8")
MODAL_JS = (REPO / "app/static/js/events/quick-event-modal.js").read_text(encoding="utf-8")
SETTINGS = (REPO / "app/templates/settings.html").read_text(encoding="utf-8")
FORMS = (REPO / "app/static/css/components/forms.css").read_text(encoding="utf-8")
DATABASE = (REPO / "app/database.py").read_text(encoding="utf-8")

ANCHOR = "2026-11-01"


def test_simple_mode_markup_hides_caption_and_end_toggle():
    assert 'id="quick_hebrew_date"' in MODAL_HTML
    assert 'type="hidden"' in MODAL_HTML.split("quick_hebrew_date", 1)[0][-80:]
    assert 'readonly' not in MODAL_HTML.split("quick_hebrew_date", 1)[1].split(">", 1)[0]
    assert "כא חשון" not in MODAL_HTML
    assert "quick_end_toggle" not in MODAL_HTML
    assert "+ תאריך סיום" not in MODAL_HTML
    assert 'id="quick_advanced_toggle"' in MODAL_HTML
    assert ">מתקדם<" in MODAL_HTML
    assert 'aria-controls="quick_advanced"' in MODAL_HTML
    assert 'id="quick_advanced"' in MODAL_HTML
    assert "hidden" in MODAL_HTML.split("id=\"quick_advanced\"", 1)[1].split(">", 1)[0]
    body, _, footer = MODAL_HTML.partition("modal-footer")
    assert "quick_advanced" in body
    assert "quick_end_date" in body
    assert "quick_recurrence" in body
    assert "quick_description" in body
    assert "quick_reminder_enabled" in body
    assert "quickShiftBlock" in body
    assert "quick_delete_btn" in footer
    assert "quick_live_notice" in body.split("quick_advanced", 1)[0]


def test_full_form_setting_is_local_to_the_device():
    assert "תמיד להציג טופס מלא במכשיר זה" in SETTINGS
    assert "במכשיר זה" in SETTINGS
    assert "heb-cal-full-event-form" in SETTINGS
    assert "data-full-form-switch" in SETTINGS
    assert "heb-cal-full-event-form" in MODAL_JS
    assert "localStorage.getItem(FULL_EVENT_FORM_KEY)" in MODAL_JS
    assert "localStorage.setItem(FULL_EVENT_FORM_KEY, '1')" in MODAL_JS
    assert "localStorage.removeItem(FULL_EVENT_FORM_KEY)" in MODAL_JS
    assert "/api/" not in MODAL_JS.split("FULL_EVENT_FORM_KEY", 1)[1].split("function loadHebrewYearLabels", 1)[0]
    assert "household_settings" not in MODAL_JS
    assert "full_event_form" not in DATABASE
    assert "heb-cal-full-event-form" not in DATABASE
    assert "visualViewport" in MODAL_JS
    assert "function syncQuickModalToVisualViewport" in MODAL_JS
    assert "function applyQuickAdvancedDefault" in MODAL_JS
    assert "prefersFullEventForm() || eventUsesAdvancedFields" in MODAL_JS


def test_simple_when_row_is_one_grid_on_narrow_phones():
    assert "display: contents" in FORMS
    assert "minmax(2.9rem" in FORMS
    assert ".quick-advanced-toggle" in FORMS
    mobile = FORMS.partition("@media (max-width: 480px)")[2].partition("@media (min-width: 481px)")[0]
    assert ".quick-when .form-label" in mobile
    assert "display: none" in mobile
    assert "align-items: flex-start" in mobile


@pytest.fixture(autouse=True)
def _quiet_app_logs():
    log = logging.getLogger("app")
    previous = log.level
    log.setLevel(logging.WARNING)
    yield
    log.setLevel(previous)


@pytest.fixture(scope="module")
def live_server(app):
    pytest.importorskip("playwright.sync_api")
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _seed_event(client, **extra):
    payload = {
        "title": extra.pop("title", "פשוט"),
        "gregorian_date": extra.pop("gregorian_date", ANCHOR),
        "hebrew_date": extra.pop("hebrew_date", "כ חשון"),
        **extra,
    }
    created = client.post("/api/events", json=payload)
    assert created.status_code == 200, created.get_data(as_text=True)
    return created.get_json()


def _open_calendar(page, live_server, width=390, height=844, storage=None):
    from playwright.sync_api import expect

    context_kwargs = {"viewport": {"width": width, "height": height}, "locale": "he-IL"}
    page.set_default_timeout(8000)
    if storage:
        page.add_init_script(
            f"try {{ localStorage.setItem({json.dumps(storage[0])}, {json.dumps(storage[1])}); }} catch (e) {{}}"
        )
    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => window.bootstrap && typeof openQuickEventModal === 'function'")
    expect(page.locator("#quickEventModal")).to_be_hidden()


def _wait_modal_reset(page):
    page.wait_for_function(
        """() => {
            const modal = document.getElementById('quickEventModal');
            const eventId = document.getElementById('quick_event_id');
            return Boolean(modal && !modal.classList.contains('show') && eventId && !eventId.value);
        }"""
    )


def _row_metrics(page):
    return page.evaluate(
        """() => {
            const ids = [
                'quick_hebrew_day', 'quick_hebrew_month', 'quick_hebrew_year',
                'quick_gregorian_date', 'quick_time',
            ];
            const boxes = ids.map((id) => {
                const el = document.getElementById(id);
                const r = el.getBoundingClientRect();
                return { id, top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height };
            });
            const content = document.querySelector('#quickEventModal .modal-content').getBoundingClientRect();
            const footer = document.querySelector('#quickEventModal .modal-footer').getBoundingClientRect();
            const submit = document.getElementById('quick_submit_btn').getBoundingClientRect();
            return {
                boxes,
                topSpread: Math.max(...boxes.map((b) => b.top)) - Math.min(...boxes.map((b) => b.top)),
                overflowRight: Math.max(0, Math.max(...boxes.map((b) => b.right)) - content.right),
                overflowLeft: Math.max(0, content.left - Math.min(...boxes.map((b) => b.left))),
                footerBottom: footer.bottom,
                submitBottom: submit.bottom,
                vh: window.innerHeight,
                vw: window.innerWidth,
            };
        }"""
    )


def test_new_event_opens_simple_and_expander_reveals_advanced(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 640}, locale="he-IL")
        _open_calendar(page, live_server, 360, 640)
        page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        expect(page.locator("#quickEventModal")).to_be_visible()
        expect(page.locator("#quick_title")).to_be_visible()
        expect(page.locator(".quick-color-picker")).to_be_visible()
        expect(page.locator("#quick_hebrew_day")).to_be_visible()
        expect(page.locator("#quick_gregorian_date")).to_be_visible()
        expect(page.locator("#quick_time")).to_be_visible()
        expect(page.locator("#quick_hebrew_date")).to_be_hidden()
        expect(page.locator("#quick_hebrew_date")).not_to_have_value("")
        expect(page.locator("#quick_advanced")).to_be_hidden()
        expect(page.locator("#quick_end_date")).to_be_hidden()
        expect(page.locator("#quick_description")).to_be_hidden()
        expect(page.locator("#quick_recurrence")).to_be_hidden()
        expect(page.locator("#quick_reminder_enabled")).to_be_hidden()
        expect(page.locator("#quick_advanced_toggle")).to_have_text("מתקדם")
        expect(page.locator("#quick_advanced_toggle")).to_have_attribute("aria-expanded", "false")
        expect(page.locator("#quick_delete_btn")).to_be_hidden()
        expect(page.locator("#quick_live_notice")).to_be_hidden()

        row = _row_metrics(page)
        assert row["topSpread"] <= 8, row
        assert row["overflowRight"] <= 2, row
        assert row["overflowLeft"] <= 2, row
        assert row["footerBottom"] <= row["vh"] + 1, row
        assert row["submitBottom"] <= row["vh"] + 1, row
        day_box = next(box for box in row["boxes"] if box["id"] == "quick_hebrew_day")
        assert day_box["right"] - (page.evaluate(
            "() => document.getElementById('quick_hebrew_day').getBoundingClientRect().left"
        )) >= 36
        day_label = page.locator("#quick_hebrew_day").evaluate(
            "el => el.selectedOptions[0] && el.selectedOptions[0].textContent"
        )
        assert day_label and not day_label.strip().isdigit(), day_label

        page.click("#quick_advanced_toggle")
        expect(page.locator("#quick_advanced")).to_be_visible()
        expect(page.locator("#quick_end_date")).to_be_visible()
        expect(page.locator("#quick_description")).to_be_visible()
        expect(page.locator("#quick_recurrence_freq")).to_be_visible()
        expect(page.locator("#quick_reminder_enabled")).to_be_visible()
        expect(page.locator("#quick_advanced_toggle")).to_have_attribute("aria-expanded", "true")
        page.click("#quick_advanced_toggle")
        expect(page.locator("#quick_advanced")).to_be_hidden()
        browser.close()


def test_edit_with_advanced_fields_opens_expanded(live_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    described = _seed_event(client, title="עם תיאור", description="פירוט")
    dated = _seed_event(client, title="רב יומי", end_date="2026-11-03")
    repeating = _seed_event(
        client,
        title="חוזר",
        recurrence_freq="yearly",
        recurrence_calendar="hebrew",
    )
    plain = _seed_event(client, title="רק כותרת")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, locale="he-IL")
        _open_calendar(page, live_server)

        page.evaluate("async (id) => { await openEditEventModal(id); }", described["id"])
        expect(page.locator("#quick_advanced")).to_be_visible()
        expect(page.locator("#quick_description")).to_have_value("פירוט")
        expect(page.locator("#quick_delete_btn")).to_be_visible()
        page.click('#quickEventModal button:has-text("ביטול")')
        expect(page.locator("#quickEventModal")).to_be_hidden()
        _wait_modal_reset(page)

        page.evaluate("async (id) => { await openEditEventModal(id); }", dated["id"])
        expect(page.locator("#quick_advanced")).to_be_visible()
        expect(page.locator("#quick_end_date")).to_have_value("2026-11-03")
        page.click('#quickEventModal button:has-text("ביטול")')
        _wait_modal_reset(page)

        page.evaluate("async (id) => { await openEditEventModal(id); }", repeating["id"])
        expect(page.locator("#quick_advanced")).to_be_visible()
        expect(page.locator("#quick_recurrence_freq")).to_have_value("yearly")
        page.click('#quickEventModal button:has-text("ביטול")')
        _wait_modal_reset(page)

        page.evaluate("async (id) => { await openEditEventModal(id); }", plain["id"])
        expect(page.locator("#quick_advanced")).to_be_hidden()
        expect(page.locator("#quick_title")).to_have_value("רק כותרת")
        expect(page.locator("#quick_delete_btn")).to_be_visible()
        page.click('#quickEventModal button:has-text("ביטול")')
        _wait_modal_reset(page)

        page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        expect(page.locator("#quick_advanced")).to_be_hidden()
        browser.close()


def test_full_form_setting_stays_on_this_device_only(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        desktop = browser.new_context(viewport={"width": 1280, "height": 800}, locale="he-IL")
        phone = browser.new_context(viewport={"width": 360, "height": 640}, locale="he-IL")
        desk_page = desktop.new_page()
        phone_page = phone.new_page()
        desk_page.set_default_timeout(8000)
        phone_page.set_default_timeout(8000)

        desk_page.goto(live_server + "/settings", wait_until="domcontentloaded")
        expect(desk_page.locator("label[for=fullEventFormSwitch]")).to_contain_text("במכשיר זה")
        switch = desk_page.locator("#fullEventFormSwitch")
        expect(switch).not_to_be_checked()
        switch.check()
        assert desk_page.evaluate("() => localStorage.getItem('heb-cal-full-event-form')") == "1"

        desk_page.goto(live_server + "/", wait_until="domcontentloaded")
        desk_page.wait_for_function("() => typeof openQuickEventModal === 'function'")
        desk_page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        expect(desk_page.locator("#quick_advanced")).to_be_visible()
        expect(desk_page.locator("#quick_description")).to_be_visible()

        phone_page.goto(live_server + "/", wait_until="domcontentloaded")
        phone_page.wait_for_function("() => typeof openQuickEventModal === 'function'")
        assert phone_page.evaluate("() => localStorage.getItem('heb-cal-full-event-form')") in (None, "")
        phone_page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        expect(phone_page.locator("#quick_advanced")).to_be_hidden()
        expect(phone_page.locator("#quick_description")).to_be_hidden()

        desktop.close()
        phone.close()
        browser.close()


def test_simple_modal_footer_stays_when_viewport_shrinks(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 640}, locale="he-IL")
        _open_calendar(page, live_server, 360, 640)
        page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        expect(page.locator("#quickEventModal")).to_be_visible()
        page.set_viewport_size({"width": 360, "height": 360})
        page.wait_for_timeout(80)
        page.evaluate("() => { if (typeof syncQuickModalToVisualViewport === 'function') syncQuickModalToVisualViewport(); }")
        box = page.locator("#quickEventModal .modal-footer").bounding_box()
        submit = page.locator("#quick_submit_btn").bounding_box()
        assert box and submit
        assert box["y"] + box["height"] <= 360 + 1, box
        assert submit["y"] + submit["height"] <= 360 + 1, submit
        expect(page.locator("#quick_submit_btn")).to_be_visible()
        expect(page.locator('#quickEventModal button:has-text("ביטול")')).to_be_visible()
        browser.close()


def test_simple_save_does_not_need_advanced_fields(live_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 360, "height": 640}, locale="he-IL")
        _open_calendar(page, live_server, 360, 640)
        page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        page.fill("#quick_title", "בלי מתקדם")
        page.click("#quick_submit_btn")
        expect(page.locator("#quickEventModal")).to_be_hidden()
        rows = client.get("/api/events").get_json()
        match = next(row for row in rows if row["title"] == "בלי מתקדם")
        assert match["gregorian_date"] == ANCHOR
        assert match["end_date"] in (None, "")
        assert not match.get("recurrence_freq")
        browser.close()
