"""מודאל אירוע: נשאר במסך, הגוף נגלל, הפוטר דבוק.

מכסה חלון לפטופ (~700px), מסך מלא כשחוסם התזכורות נפתח, וטלפון.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FORMS = REPO / "app/static/css/components/forms.css"
CALENDAR_CSS = REPO / "app/static/css/components/calendar.css"

# (עמוד, רוחב, גובה, לפתוח תזכורת+חזרה)
VIEWPORTS = [
    ("calendar", 1280, 700, False),
    ("calendar", 1280, 700, True),
    ("calendar", 1366, 768, True),
    ("calendar", 1440, 900, True),
    ("calendar", 1920, 1080, True),
    ("calendar", 390, 844, True),
    ("calendar", 375, 812, True),
    ("list", 1280, 720, True),
]


@pytest.fixture(autouse=True)
def _quiet_app_logs():
    log = logging.getLogger("app")
    previous = log.level
    log.setLevel(logging.WARNING)
    yield
    log.setLevel(previous)


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def test_modal_scroll_css_applies_at_every_width():
    css = FORMS.read_text(encoding="utf-8")
    head, _, rest = css.partition("@media (max-width: 480px)")
    mobile, _, after_mobile = rest.partition("@media (min-width: 481px)")

    assert "#quickEventModal .modal-content > form" in head
    assert "overflow-y: auto" in head
    assert "min-height: 0" in head
    assert "100dvh" in head
    assert "position: sticky" in head
    assert "overscroll-behavior: contain" in head

    # יעדי מגע וסגירת תאריך הסיום נשארים רק בטלפון
    assert "font-size: 16px" in mobile
    assert "min-height: 40px" in mobile
    assert ".quick-end-wrap:not(.is-open) .quick-end-field" in mobile
    assert "overflow-y: auto" not in mobile

    assert "height: calc(100dvh - 1.5rem)" in after_mobile
    assert "#quickEventModal .modal-footer" in after_mobile

    calendar = CALENDAR_CSS.read_text(encoding="utf-8")
    assert "touch-action: pan-x pan-y pinch-zoom" in calendar
    assert "user-scalable=no" not in (REPO / "app/templates/base.html").read_text(encoding="utf-8")


def _seed_people(client, count=8):
    for index in range(count):
        created = client.post(
            "/api/reminder-people",
            json={"name": f"נמען {index + 1}", "telegram_chat_id": str(8000 + index)},
        )
        assert created.status_code == 201, created.get_data(as_text=True)


_METRICS_JS = """
(selector) => {
    const body = document.querySelector('#quickEventModal .modal-body');
    const target = document.querySelector(selector);
    const modal = document.querySelector('#quickEventModal');
    const footer = document.querySelector('#quickEventModal .modal-footer');
    const header = document.querySelector('#quickEventModal .modal-header');
    const content = document.querySelector('#quickEventModal .modal-content');
    const submit = document.querySelector('#quick_submit_btn');
    if (!body || !target || !modal || !footer || !header || !content || !submit) {
        return { missing: true, selector };
    }
    const nudge = () => {
        const b = body.getBoundingClientRect();
        const t = target.getBoundingClientRect();
        if (t.bottom > b.bottom - 1) {
            body.scrollTop += t.bottom - b.bottom + 8;
        }
        const b2 = body.getBoundingClientRect();
        const t2 = target.getBoundingClientRect();
        if (t2.top < b2.top + 1) {
            body.scrollTop -= b2.top + 1 - t2.top;
        }
    };
    nudge();
    nudge();
    const box = (el) => {
        const r = el.getBoundingClientRect();
        return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height, width: r.width };
    };
    const buttons = [...footer.querySelectorAll('.btn')].map((el) => ({
        text: (el.textContent || '').trim(),
        ...box(el),
    }));
    return {
        missing: false,
        target: box(target),
        body: box(body),
        footer: box(footer),
        header: box(header),
        content: box(content),
        submit: box(submit),
        buttons,
        overflow: body.scrollHeight - body.clientHeight,
        scrollTop: body.scrollTop,
        modalOverflow: modal.scrollHeight - modal.clientHeight,
        vh: window.innerHeight,
        vw: window.innerWidth,
        bodyOverflowY: getComputedStyle(body).overflowY,
        touchAction: getComputedStyle(body).touchAction,
        footerPosition: getComputedStyle(footer).position,
        footerBg: getComputedStyle(footer).backgroundColor,
    };
}
"""


def _assert_chrome(metrics, label):
    assert not metrics.get("missing"), (label, metrics)
    vh = metrics["vh"]
    vw = metrics["vw"]
    assert metrics["header"]["top"] >= -1, (label, metrics)
    assert metrics["footer"]["bottom"] <= vh + 1, (label, metrics)
    assert metrics["submit"]["bottom"] <= vh + 1, (label, metrics)
    assert metrics["submit"]["top"] >= metrics["footer"]["top"] - 1, (label, metrics)
    assert metrics["content"]["top"] >= -1, (label, metrics)
    assert metrics["content"]["bottom"] <= vh + 1, (label, metrics)
    assert metrics["content"]["left"] >= -1, (label, metrics)
    assert metrics["content"]["right"] <= vw + 1, (label, metrics)
    assert metrics["content"]["height"] <= vh - 8, (label, metrics)
    if vw >= 576:
        assert metrics["content"]["width"] >= 400, (label, metrics)
    else:
        assert metrics["content"]["width"] >= vw - 48, (label, metrics)
    assert metrics["header"]["bottom"] <= metrics["body"]["top"] + 1, (label, metrics)
    assert metrics["footer"]["top"] >= metrics["body"]["bottom"] - 1, (label, metrics)
    assert metrics["bodyOverflowY"] in ("auto", "scroll"), (label, metrics)
    assert metrics["footerPosition"] == "sticky", (label, metrics)
    assert metrics["modalOverflow"] <= 2, (label, metrics)
    assert metrics["touchAction"] != "none", (label, metrics)
    assert "rgba(0, 0, 0, 0)" not in metrics["footerBg"], (label, metrics)
    for button in metrics["buttons"]:
        assert button["top"] >= -1, (label, button, metrics)
        assert button["bottom"] <= vh + 1, (label, button, metrics)
    texts = [button["text"] for button in metrics["buttons"]]
    assert any(text in ("הוסף אירוע", "שמירה") for text in texts), (label, texts)
    assert "ביטול" in texts, (label, texts)


def _assert_target_in_body(metrics, label):
    target = metrics["target"]
    body = metrics["body"]
    assert target["height"] > 0, (label, metrics)
    assert target["top"] >= body["top"] - 1, (label, metrics)
    assert target["bottom"] <= body["bottom"] + 1, (label, metrics)
    assert target["bottom"] <= metrics["footer"]["top"] + 1, (label, metrics)


def _open_modal(page, kind):
    if kind == "calendar":
        page.goto(page.context._base + "/", wait_until="domcontentloaded")
        page.wait_for_function("() => window.bootstrap && typeof openQuickEventModal === 'function'")
        page.click("#addEventFromCalendarBtn")
    else:
        page.goto(page.context._base + "/events_list", wait_until="domcontentloaded")
        page.wait_for_function("() => window.bootstrap && typeof openQuickEventModal === 'function'")
        page.click("#addEventFromListBtn")
    dialog = page.locator("#quickEventModal .modal-dialog")
    expect(page.locator("#quickEventModal")).to_be_visible()
    page.wait_for_function(
        """() => {
            const dialog = document.querySelector('#quickEventModal .modal-dialog');
            if (!dialog) return false;
            const transform = getComputedStyle(dialog).transform;
            return !transform || transform === 'none';
        }"""
    )
    page.wait_for_selector(
        "#quick_reminder_recipients label, #quick_reminder_recipients .reminder-empty-people",
        state="attached",
    )
    return dialog


def _expand(page, width):
    page.select_option("#quick_recurrence_freq", "yearly")
    page.select_option("#quick_recurrence_end_mode", "until")
    expect(page.locator("#quick_recurrence_until")).to_be_visible()
    if width <= 480:
        page.click("#quick_end_toggle")
        expect(page.locator("#quick_end_date")).to_be_visible()
    page.click("#quick_reminder_enabled")
    expect(page.locator("#quick_reminder_panel")).to_be_visible()
    page.click("#quick_reminder_custom_toggle")
    expect(page.locator("#quick_reminder_custom_row")).to_be_visible()
    expect(page.locator(".reminder-recipients")).to_contain_text("למי להזכיר")


@pytest.mark.parametrize("kind,width,height,expand", VIEWPORTS)
def test_event_modal_footer_stays_and_sections_scroll(live_server, client, kind, width, height, expand):
    _seed_people(client)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": width, "height": height},
            reduced_motion="reduce",
        )
        context._base = live_server
        page = context.new_page()
        page.set_default_timeout(8000)
        _open_modal(page, kind)

        if not expand:
            metrics = page.evaluate(_METRICS_JS, "#quick_reminder_enabled")
            _assert_chrome(metrics, f"collapsed {width}x{height}")
            _assert_target_in_body(metrics, f"collapsed {width}x{height}")
            assert metrics["overflow"] <= 8, metrics
            assert metrics["scrollTop"] <= 1, metrics
        else:
            _expand(page, width)
            # לפני גלילה: הכפתורים כבר על המסך, גם אם הבורר עוד למטה
            closed = page.evaluate(_METRICS_JS, "#quick_submit_btn")
            _assert_chrome(closed, f"expanded-chrome {kind} {width}x{height}")
            page.locator("#quick_submit_btn").click(trial=True)
            page.locator('#quickEventModal .modal-footer .btn-outline-secondary').click(trial=True)
            page.locator("#quickEventModal .btn-close").click(trial=True)

            recipients = page.evaluate(_METRICS_JS, "#quick_reminder_recipients label:last-child")
            _assert_chrome(recipients, f"recipients {kind} {width}x{height}")
            _assert_target_in_body(recipients, f"recipients {kind} {width}x{height}")
            page.locator("#quick_reminder_recipients label:last-child input").click(trial=True)

            until = page.evaluate(_METRICS_JS, "#quick_recurrence_until")
            _assert_chrome(until, f"until {kind} {width}x{height}")
            _assert_target_in_body(until, f"until {kind} {width}x{height}")

            if width <= 480:
                end = page.evaluate(_METRICS_JS, "#quick_end_date")
                _assert_chrome(end, f"end {kind} {width}x{height}")
                _assert_target_in_body(end, f"end {kind} {width}x{height}")
                # בטלפון חייב להיות אפשר לפתוח את הפאנל בלי לאבד את הפוטר,
                # והגלילה הפנימית היא זו שמגלה את הנמען כשהוא לא נכנס
                if recipients["overflow"] > 8:
                    assert recipients["scrollTop"] > 0, recipients

            # במסך נמוך הפאנל חייב לגלוש לתוך הגוף, לא מחוץ לחלון
            if height <= 768 and recipients["overflow"] <= 8:
                raise AssertionError(f"expected internal overflow at {width}x{height}: {recipients}")

        context.close()
        browser.close()
