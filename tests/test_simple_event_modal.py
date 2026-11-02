"""מצב פשוט במודל אירוע: שורה אחת, «מתקדם», והגדרה לכל מכשיר ב-localStorage."""
from __future__ import annotations

import json
import logging
import subprocess
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
    assert 'id="quick_end_toggle"' in MODAL_HTML
    assert "+ תאריך סיום" in MODAL_HTML
    assert 'id="quick_end_wrap"' in MODAL_HTML
    assert 'id="quick_end_clear"' in MODAL_HTML
    assert "hidden" in MODAL_HTML.split('id="quick_end_wrap"', 1)[1].split(">", 1)[0]
    assert "הסר" in MODAL_HTML.split("quick_end_clear", 1)[1].split("</button>", 1)[0]
    assert 'id="quick_advanced_toggle"' in MODAL_HTML
    assert ">מתקדם<" in MODAL_HTML
    assert 'aria-controls="quick_advanced"' in MODAL_HTML
    assert 'id="quick_advanced"' in MODAL_HTML
    assert "hidden" in MODAL_HTML.split("id=\"quick_advanced\"", 1)[1].split(">", 1)[0]
    body, _, footer = MODAL_HTML.partition("modal-footer")
    simple, _, advanced = body.partition("id=\"quick_advanced\"")
    assert "quick-simple-row" in simple
    assert 'id="quick_title"' in simple
    assert 'id="quick_time"' in simple
    assert "quick-color-picker" in simple
    assert 'id="quick_gregorian_date"' not in simple
    assert 'id="quick_hebrew_day"' not in simple
    assert 'id="quick_end_date"' not in simple
    assert 'id="quick_end_toggle"' not in simple
    assert "quick_advanced" in body
    assert 'id="quick_gregorian_date"' in advanced
    assert 'id="quick_hebrew_day"' in advanced
    assert 'id="quick_end_hebrew_day"' in advanced
    assert 'id="quick_end_hebrew_month"' in advanced
    assert 'id="quick_end_hebrew_year"' in advanced
    assert "quick_end_date" in advanced
    assert "quick-when-caption" in advanced
    assert ">מתאריך<" in advanced
    assert ">עד תאריך<" in advanced
    assert 'id="quick_end_toggle"' in advanced
    assert 'id="quick_end_wrap"' in advanced
    assert 'id="quick_end_clear"' in advanced
    assert "quick_recurrence" in advanced
    assert "quick_description" in advanced
    assert "quick_reminder_enabled" in advanced
    assert "quickShiftBlock" in advanced
    assert "quick_delete_btn" in footer
    assert "quick_live_notice" in simple
    assert "function setEndDateOpen" in MODAL_JS
    assert "function clearQuickEndDate" in MODAL_JS
    assert "function openQuickEndDate" in MODAL_JS


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
    assert ".quick-simple-row" in FORMS
    assert "minmax(5.5rem" in FORMS
    assert "display: contents" in FORMS
    assert "minmax(2.9rem" in FORMS
    assert ".quick-advanced-toggle" in FORMS
    assert ".quick-when-caption" in FORMS
    assert ".quick-end-toggle" in FORMS
    assert ".quick-end-wrap[hidden]" in FORMS
    assert "quick-end-when" in FORMS or "quick-end-when" in MODAL_HTML
    mobile = FORMS.partition("@media (max-width: 480px)")[2].partition("@media (min-width: 481px)")[0]
    assert ".quick-simple-row .form-label" in mobile
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


def _simple_row_metrics(page):
    return page.evaluate(
        """() => {
            const box = (id) => {
                const el = document.getElementById(id);
                const r = el.getBoundingClientRect();
                return { id, top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height };
            };
            const title = box('quick_title');
            const time = box('quick_time');
            const color = document.querySelector('#quickEventModal .quick-color-picker').getBoundingClientRect();
            const content = document.querySelector('#quickEventModal .modal-content').getBoundingClientRect();
            const footer = document.querySelector('#quickEventModal .modal-footer').getBoundingClientRect();
            const submit = document.getElementById('quick_submit_btn').getBoundingClientRect();
            const boxes = [title, time];
            return {
                title,
                time,
                color: { top: color.top, bottom: color.bottom, left: color.left, right: color.right },
                topSpread: Math.abs(title.top - time.top),
                timeOnLeft: time.left < title.left - 4,
                colorBelow: color.top >= Math.max(title.bottom, time.bottom) - 2,
                overflowRight: Math.max(0, Math.max(...boxes.map((b) => b.right)) - content.right),
                overflowLeft: Math.max(0, content.left - Math.min(...boxes.map((b) => b.left))),
                footerBottom: footer.bottom,
                submitBottom: submit.bottom,
                vh: window.innerHeight,
                vw: window.innerWidth,
            };
        }"""
    )


def _date_row_metrics(page, prefix):
    ids = (
        [f"{prefix}hebrew_day", f"{prefix}hebrew_month", f"{prefix}hebrew_year", f"{prefix}gregorian_date"]
        if prefix == "quick_"
        else [
            "quick_end_hebrew_day",
            "quick_end_hebrew_month",
            "quick_end_hebrew_year",
            "quick_end_date",
        ]
    )
    return page.evaluate(
        """(ids) => {
            const boxes = ids.map((id) => {
                const el = document.getElementById(id);
                const r = el.getBoundingClientRect();
                return { id, top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height };
            });
            return {
                boxes,
                topSpread: Math.max(...boxes.map((b) => b.top)) - Math.min(...boxes.map((b) => b.top)),
            };
        }""",
        ids,
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
        expect(page.locator("#quick_time")).to_be_visible()
        expect(page.locator("#quick_hebrew_day")).to_be_hidden()
        expect(page.locator("#quick_gregorian_date")).to_be_hidden()
        expect(page.locator("#quick_end_hebrew_day")).to_be_hidden()
        expect(page.locator("#quick_hebrew_date")).to_be_hidden()
        expect(page.locator("#quick_hebrew_date")).not_to_have_value("")
        expect(page.locator("#quick_gregorian_date")).to_have_value(ANCHOR)
        expect(page.locator("#quick_advanced")).to_be_hidden()
        expect(page.locator("#quick_end_date")).to_be_hidden()
        expect(page.locator("#quick_description")).to_be_hidden()
        expect(page.locator("#quick_recurrence")).to_be_hidden()
        expect(page.locator("#quick_reminder_enabled")).to_be_hidden()
        expect(page.locator("#quick_advanced_toggle")).to_have_text("מתקדם")
        expect(page.locator("#quick_advanced_toggle")).to_have_attribute("aria-expanded", "false")
        expect(page.locator("#quick_delete_btn")).to_be_hidden()
        expect(page.locator("#quick_live_notice")).to_be_hidden()
        expect(page.locator("#quickEventModalLabel")).to_contain_text("אירוע חדש")

        row = _simple_row_metrics(page)
        assert row["topSpread"] <= 8, row
        assert row["timeOnLeft"] is True, row
        assert row["colorBelow"] is True, row
        assert row["overflowRight"] <= 2, row
        assert row["overflowLeft"] <= 2, row
        assert row["footerBottom"] <= row["vh"] + 1, row
        assert row["submitBottom"] <= row["vh"] + 1, row

        page.fill("#quick_title", "2110 בדיקה")
        page.wait_for_function("() => document.getElementById('quick_time').value === '21:10'")
        expect(page.locator("#quick_title")).to_have_value("בדיקה")
        expect(page.locator("#quick_gregorian_date")).to_have_value(ANCHOR)

        page.click("#quick_advanced_toggle")
        expect(page.locator("#quick_advanced")).to_be_visible()
        expect(page.locator("#quick_hebrew_day")).to_be_visible()
        expect(page.locator("#quick_gregorian_date")).to_be_visible()
        expect(page.locator("#quick_start_block .quick-when-caption")).to_have_text("מתאריך")
        expect(page.locator("#quick_end_toggle")).to_be_visible()
        expect(page.locator("#quick_end_toggle")).to_have_text("+ תאריך סיום")
        expect(page.locator("#quick_end_wrap")).to_be_hidden()
        expect(page.locator("#quick_end_date")).to_be_hidden()
        expect(page.locator("#quick_end_hebrew_day")).to_be_hidden()
        expect(page.locator("#quick_description")).to_be_visible()
        expect(page.locator("#quick_recurrence_freq")).to_be_visible()
        expect(page.locator("#quick_reminder_enabled")).to_be_visible()
        expect(page.locator("#quick_advanced_toggle")).to_have_attribute("aria-expanded", "true")
        start_row = _date_row_metrics(page, "quick_")
        assert start_row["topSpread"] <= 8, start_row

        page.click("#quick_end_toggle")
        expect(page.locator("#quick_end_wrap")).to_be_visible()
        expect(page.locator("#quick_end_toggle")).to_be_hidden()
        expect(page.locator("#quick_end_date")).to_be_visible()
        expect(page.locator("#quick_end_hebrew_day")).to_be_visible()
        expect(page.locator("#quick_end_wrap .quick-when-caption")).to_contain_text("עד תאריך")
        expect(page.locator("#quick_end_clear")).to_be_visible()
        end_row = _date_row_metrics(page, "end")
        assert end_row["topSpread"] <= 8, end_row
        day_label = page.locator("#quick_hebrew_day").evaluate(
            "el => el.selectedOptions[0] && el.selectedOptions[0].textContent"
        )
        assert day_label and not day_label.strip().isdigit(), day_label

        page.click("#quick_end_clear")
        expect(page.locator("#quick_end_wrap")).to_be_hidden()
        expect(page.locator("#quick_end_toggle")).to_be_visible()
        expect(page.locator("#quick_end_date")).to_have_value("")

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
        expect(page.locator("#quick_end_toggle")).to_be_visible()
        expect(page.locator("#quick_end_wrap")).to_be_hidden()
        page.click('#quickEventModal button:has-text("ביטול")')
        expect(page.locator("#quickEventModal")).to_be_hidden()
        _wait_modal_reset(page)

        page.evaluate("async (id) => { await openEditEventModal(id); }", dated["id"])
        expect(page.locator("#quick_advanced")).to_be_visible()
        expect(page.locator("#quick_end_wrap")).to_be_visible()
        expect(page.locator("#quick_end_date")).to_have_value("2026-11-03")
        expect(page.locator("#quick_end_toggle")).to_be_hidden()
        expect(page.locator("#quick_end_clear")).to_be_visible()
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


def test_clear_end_date_removes_it_on_save(live_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    dated = _seed_event(client, title="רב יומי למחיקה", end_date="2026-11-03")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, locale="he-IL")
        _open_calendar(page, live_server)
        page.evaluate("async (id) => { await openEditEventModal(id); }", dated["id"])
        expect(page.locator("#quick_end_wrap")).to_be_visible()
        expect(page.locator("#quick_end_date")).to_have_value("2026-11-03")
        page.click("#quick_end_clear")
        expect(page.locator("#quick_end_wrap")).to_be_hidden()
        expect(page.locator("#quick_end_date")).to_have_value("")
        page.click("#quick_submit_btn")
        expect(page.locator("#quickEventModal")).to_be_hidden()
        browser.close()

    rows = client.get("/api/events").get_json()
    match = next(row for row in rows if row["id"] == dated["id"])
    assert match["end_date"] in (None, "")


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


def test_four_digit_time_in_title_is_parsed():
    start = MODAL_JS.index("function extractTimeFromTitle")
    end = MODAL_JS.index("function applyTimeFromTitlePrefix")
    script = (
        MODAL_JS[start:end]
        + """
const cases = ['2110 בדיקה', 'בדיקה 2110', '21:10 בדיקה', '0600 פגישה'];
const out = cases.map((text) => extractTimeFromTitle(text));
process.stdout.write(JSON.stringify(out));
"""
    )
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    parsed = json.loads(result.stdout)
    assert parsed[0]["time"] == "21:10"
    assert parsed[0]["cleanedTitle"] == "בדיקה"
    assert parsed[1]["time"] == "21:10"
    assert parsed[1]["cleanedTitle"] == "בדיקה"
    assert parsed[2]["time"] == "21:10"
    assert parsed[3]["time"] == "06:00"
    assert parsed[3]["cleanedTitle"] == "פגישה"


def test_end_date_row_stays_in_sync_with_hebrew(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, locale="he-IL")
        _open_calendar(page, live_server, 1280, 800)
        page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        page.click("#quick_advanced_toggle")
        expect(page.locator("#quick_end_wrap")).to_be_hidden()
        page.click("#quick_end_toggle")
        expect(page.locator("#quick_end_when")).to_be_visible()
        expect(page.locator("#quick_end_hebrew_day")).to_be_visible()
        expect(page.locator("#quick_end_date")).to_be_visible()
        page.wait_for_function(
            """() => {
                const day = document.getElementById('quick_hebrew_day');
                return day && day.value && day.options.length > 20;
            }"""
        )

        page.fill("#quick_end_date", "2026-11-03")
        page.locator("#quick_end_date").dispatch_event("change")
        page.wait_for_function(
            """() => {
                const greg = document.getElementById('quick_end_date');
                const startDay = document.getElementById('quick_hebrew_day');
                const endDay = document.getElementById('quick_end_hebrew_day');
                return greg && greg.value === '2026-11-03'
                    && startDay && endDay && endDay.value
                    && endDay.options.length > 0
                    && endDay.value !== startDay.value;
            }"""
        )
        start_day = page.locator("#quick_hebrew_day").input_value()
        end_day = page.locator("#quick_end_hebrew_day").input_value()
        assert end_day
        assert start_day != end_day or page.locator("#quick_end_hebrew_month").input_value() != page.locator(
            "#quick_hebrew_month"
        ).input_value()

        end_month = page.locator("#quick_end_hebrew_month").input_value()
        end_year = page.locator("#quick_end_hebrew_year").input_value()
        page.select_option("#quick_end_hebrew_day", start_day)
        page.wait_for_function(
            """(expected) => document.getElementById('quick_end_date').value === expected""",
            arg=ANCHOR,
        )
        expect(page.locator("#quick_end_hebrew_month")).to_have_value(end_month)
        expect(page.locator("#quick_end_hebrew_year")).to_have_value(end_year)
        expect(page.locator("#quick_gregorian_date")).to_have_value(ANCHOR)
        browser.close()
