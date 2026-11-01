"""כפתור «מחיקה» במודל עריכת אירוע — מוסתר בהוספה, מוצג בעריכה, מוחק דרך ה-API הקיים."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MODAL_HTML = (REPO / "app/templates/partials/quick_event_modal.html").read_text(encoding="utf-8")
MODAL_JS = (REPO / "app/static/js/events/quick-event-modal.js").read_text(encoding="utf-8")
ACTIONS_JS = (REPO / "app/static/js/events/event-actions.js").read_text(encoding="utf-8")
FORMS_CSS = (REPO / "app/static/css/components/forms.css").read_text(encoding="utf-8")

ANCHOR = "2026-03-03"
LATER = "2026-04-03"


def test_delete_button_markup_is_danger_and_hidden_by_default():
    footer = MODAL_HTML.split("modal-footer", 1)[1].split("</div>", 1)[0]
    assert 'id="quick_delete_btn"' in footer
    assert "מחיקה" in footer
    assert "btn-outline-danger" in footer
    assert "btn-primary" not in footer.split("quick_delete_btn", 1)[1].split(">", 1)[0]
    attrs = footer.split("quick_delete_btn", 1)[1].split(">", 1)[0]
    assert "hidden" in attrs
    assert 'type="button"' in footer.split("quick_delete_btn", 1)[0][-80:]
    assert "ביטול" in footer
    assert "quick_submit_btn" in footer
    assert 'id="quick_delete_btn"' not in MODAL_HTML.split("modal-body", 1)[1].split("modal-footer", 1)[0]


def test_delete_button_on_calendar_and_list_pages(client):
    for page in ("/", "/events_list"):
        html = client.get(page).get_data(as_text=True)
        assert 'id="quick_delete_btn"' in html
        assert ">מחיקה<" in html
        assert "btn-outline-danger" in html
        assert "deleteFromQuickEventModal" in html or "/static/js/events/quick-event-modal.js" in html


def test_js_reuses_existing_delete_api_and_confirms_in_hebrew():
    assert "function syncQuickDeleteButton" in MODAL_JS
    assert "function deleteFromQuickEventModal" in MODAL_JS
    assert "deleteEventOccurrence" in MODAL_JS
    assert "deleteEvent(" in MODAL_JS
    assert "currentEditScope()" in MODAL_JS
    assert "bootstrap.Modal.getOrCreateInstance(modalElement).hide()" in MODAL_JS
    assert "deleteBtn.hidden = !editing || isReadonly" in MODAL_JS
    assert "quick_delete_btn" in MODAL_JS
    assert "למחוק את האירוע?" in ACTIONS_JS
    assert "למחוק את כל הסדרה?" in ACTIONS_JS
    assert "למחוק רק את המופע הזה?" in ACTIONS_JS
    assert "return true;" in ACTIONS_JS
    assert "return false;" in ACTIONS_JS
    assert "/api/events/${eventId}" in ACTIONS_JS
    assert "scope=occurrence" in ACTIONS_JS


def test_footer_css_keeps_three_buttons_on_one_row_on_phones():
    assert "flex-wrap: wrap" in FORMS_CSS
    mobile = FORMS_CSS.partition("@media (max-width: 480px)")[2]
    assert "#quickEventModal .modal-footer .btn" in mobile
    assert "min-height: 40px" in mobile
    assert "flex: 1 1 0" in mobile


@pytest.fixture(scope="module")
def live_server(app):
    pytest.importorskip("playwright.sync_api")
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _seed_event(client, **extra):
    payload = {
        "title": extra.pop("title", "למחיקה"),
        "gregorian_date": extra.pop("gregorian_date", ANCHOR),
        "hebrew_date": extra.pop("hebrew_date", "יד אדר"),
        **extra,
    }
    created = client.post("/api/events", json=payload)
    assert created.status_code == 200, created.get_data(as_text=True)
    return created.get_json()


def _open_calendar(page, live_server):
    from playwright.sync_api import expect

    page.goto(live_server + "/", wait_until="domcontentloaded")
    page.wait_for_function("() => window.bootstrap && typeof openEditEventModal === 'function'")
    expect(page.locator("#quick_delete_btn")).to_be_hidden()


def _wait_modal_reset(page):
    """Bootstrap מפעיל hidden.bs.modal אחרי שהמודל כבר לא .show — מחכים לאיפוס."""
    page.wait_for_function(
        """() => {
            const modal = document.getElementById('quickEventModal');
            const eventId = document.getElementById('quick_event_id');
            return Boolean(
                modal
                && !modal.classList.contains('show')
                && eventId
                && !eventId.value
            );
        }"""
    )


def _dialog(page, action, expected=None):
    def handle(dialog):
        if expected:
            assert expected in dialog.message, dialog.message
        if action == "accept":
            dialog.accept()
        else:
            dialog.dismiss()

    page.once("dialog", handle)


def test_new_event_hides_delete_edit_shows_deletes_and_closes(live_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    event = _seed_event(client, title="חד־פעמי")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, locale="he-IL")
        page.set_default_timeout(8000)
        _open_calendar(page, live_server)

        page.evaluate("async (id) => { await openEditEventModal(id); }", event["id"])
        expect(page.locator("#quickEventModal")).to_be_visible()
        expect(page.locator("#quick_delete_btn")).to_be_visible()
        expect(page.locator("#quick_delete_btn")).to_have_class("btn btn-outline-danger")
        expect(page.locator("#quick_delete_btn")).to_have_text("מחיקה")
        expect(page.locator("#quick_submit_btn")).to_have_text("שמירה")

        box = page.locator("#quick_delete_btn").bounding_box()
        footer = page.locator("#quickEventModal .modal-footer").bounding_box()
        assert box and footer
        assert box["y"] >= footer["y"] - 1
        assert box["y"] + box["height"] <= footer["y"] + footer["height"] + 1
        assert box["y"] + box["height"] <= 844 + 1

        _dialog(page, "dismiss", "למחוק את האירוע?")
        page.click("#quick_delete_btn")
        expect(page.locator("#quickEventModal")).to_be_visible()
        still = client.get(f"/api/events/{event['id']}")
        assert still.status_code == 200

        _dialog(page, "accept", "למחוק את האירוע?")
        page.click("#quick_delete_btn")
        expect(page.locator("#quickEventModal")).to_be_hidden()
        expect(page.locator("#success-message")).to_have_text("האירוע נמחק")
        gone = client.get(f"/api/events/{event['id']}")
        assert gone.status_code == 404
        _wait_modal_reset(page)

        page.evaluate("async (day) => { await openQuickEventModal(day); }", ANCHOR)
        expect(page.locator("#quickEventModal")).to_be_visible()
        expect(page.locator("#quick_delete_btn")).to_be_hidden()
        expect(page.locator("#quick_submit_btn")).to_have_text("הוסף אירוע")
        browser.close()


def test_recurring_delete_follows_occurrence_vs_series_scope(live_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    event = _seed_event(
        client,
        title="חוזר",
        recurrence_freq="monthly",
        recurrence_calendar="gregorian",
        recurrence_count=4,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, locale="he-IL")
        page.set_default_timeout(8000)
        _open_calendar(page, live_server)

        page.evaluate(
            """async ({ id, day }) => { await openEditEventModal(id, day); }""",
            {"id": event["id"], "day": LATER},
        )
        expect(page.locator("#quickEventModal")).to_be_visible()
        expect(page.locator("#quick_delete_btn")).to_be_visible()
        expect(page.locator("#quick_recurrence_scope")).to_be_visible()
        assert page.locator('#quick_recurrence_scope input[value="occurrence"]').is_checked()

        _dialog(page, "accept", "למחוק רק את המופע הזה?")
        page.click("#quick_delete_btn")
        expect(page.locator("#quickEventModal")).to_be_hidden()
        expect(page.locator("#success-message")).to_have_text("המופע נמחק")
        _wait_modal_reset(page)

        rows = client.get("/api/events?from=2026-03-01&to=2026-06-30").get_json()
        dates = [row["gregorian_date"] for row in rows if row["id"] == event["id"]]
        assert LATER not in dates
        assert ANCHOR in dates

        page.evaluate(
            """async ({ id, day }) => { await openEditEventModal(id, day); }""",
            {"id": event["id"], "day": ANCHOR},
        )
        expect(page.locator("#quickEventModal")).to_be_visible()
        expect(page.locator("#quick_recurrence_scope")).to_be_visible()
        page.locator("#quick_recurrence_scope").get_by_text("כל הסדרה").click()
        _dialog(page, "accept", "למחוק את כל הסדרה?")
        page.click("#quick_delete_btn")
        expect(page.locator("#quickEventModal")).to_be_hidden()
        gone = client.get(f"/api/events/{event['id']}")
        assert gone.status_code == 404
        browser.close()


def test_gcal_readonly_hides_delete_button(live_server, client):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    event = _seed_event(client, title="מקומי")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_default_timeout(8000)
        _open_calendar(page, live_server)
        page.evaluate("async (id) => { await openEditEventModal(id); }", event["id"])
        expect(page.locator("#quick_delete_btn")).to_be_visible()
        page.evaluate("() => setQuickEventReadonly(true)")
        expect(page.locator("#quick_delete_btn")).to_be_hidden()
        expect(page.locator("#quick_submit_btn")).to_be_hidden()
        browser.close()
