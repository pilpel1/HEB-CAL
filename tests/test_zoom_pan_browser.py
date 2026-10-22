"""פאן אחרי פינץ', וגלילת חודשים בלי זום — אמולציית מגע.

הדפדפן לא חלק מכל סביבת pytest. אם Chromium לא מותקן הבדיקה נכשלת
(אחרי `python -m playwright install chromium`), לא מדלגת בשקט.
"""
from __future__ import annotations

import datetime as dt
import threading

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

PAN_OK = {"manipulation", "pan-x pan-y pinch-zoom"}


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _drag(cdp, x0, y0, x1, y1, steps=8):
    cdp.send("Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{"x": x0, "y": y0, "id": 1}],
    })
    for i in range(1, steps + 1):
        cdp.send("Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{
                "x": x0 + (x1 - x0) * i / steps,
                "y": y0 + (y1 - y0) * i / steps,
                "id": 1,
            }],
        })
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def _install_prevent_default_spy(page):
    page.evaluate("""() => {
        window.__pd = [];
        const orig = Event.prototype.preventDefault;
        Event.prototype.preventDefault = function () {
            const t = this.type;
            if (t === 'touchstart' || t === 'touchmove' || t === 'pointerdown' || t === 'pointermove') {
                const el = this.target;
                window.__pd.push(t + '@' + (el && el.className));
            }
            return orig.apply(this, arguments);
        };
    }""")


def test_zoomed_pan_and_agenda_description(live_server, client):
    today = dt.date.today().isoformat()
    long_desc = "פגישה עם הרופא " + ("ואז עוד פרטים " * 12) + "<img src=x>"
    created = client.post("/api/events", json={
        "title": "בוקר",
        "gregorian_date": today,
        "hebrew_date": "היום",
        "description": long_desc,
        "color": "cyan",
    })
    assert created.status_code == 200
    plain = client.post("/api/events", json={
        "title": "בלי תיאור",
        "gregorian_date": today,
        "hebrew_date": "היום",
        "description": "   \n  ",
        "color": "yellow",
    })
    assert plain.status_code == 200

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            has_touch=True,
            is_mobile=True,
            device_scale_factor=2,
        )
        page = context.new_page()
        page.goto(live_server + "/", wait_until="domcontentloaded")
        page.wait_for_selector(".infinite-calendar:not(.is-booting)", timeout=20000)
        page.wait_for_selector(".agenda-text.has-desc", timeout=10000)

        desc = page.evaluate("""() => {
            const text = document.querySelector('.agenda-text.has-desc');
            const descEl = text.querySelector('.agenda-desc');
            const highlight = text.closest('.agenda-highlight');
            const list = document.querySelector('.day-agenda-list');
            const plain = [...document.querySelectorAll('.agenda-event .agenda-text')]
                .find((el) => el.textContent.trim() === 'בלי תיאור');
            const cs = getComputedStyle(descEl);
            const textCs = getComputedStyle(text);
            return {
                text: text.textContent,
                html: descEl.innerHTML,
                img: descEl.querySelector('img'),
                weight: cs.fontWeight,
                color: cs.color,
                nowrap: textCs.whiteSpace,
                ellipsis: textCs.textOverflow,
                overflowX: textCs.overflowX,
                truncated: text.scrollWidth > text.clientWidth + 1,
                highlightW: highlight.getBoundingClientRect().width,
                listW: list.getBoundingClientRect().width,
                plainClass: plain && plain.className,
                plainWhite: plain && getComputedStyle(plain).whiteSpace,
            };
        }""")
        assert desc["text"].startswith("בוקר")
        assert " • " in desc["text"]
        assert "פגישה עם הרופא" in desc["text"]
        assert desc["img"] is None
        assert "&lt;img" in desc["html"] or "<img" not in desc["html"]
        assert desc["html"].find("<img") == -1
        assert desc["weight"] in {"300", "300.0"} or str(desc["weight"]).startswith("300")
        assert desc["nowrap"] == "nowrap"
        assert desc["ellipsis"] == "ellipsis"
        assert desc["overflowX"] == "hidden"
        assert desc["truncated"] is True
        # ההדגשה תופסת כמעט את כל רוחב הפאנל (נשאר מקום לעיגול)
        assert desc["highlightW"] > desc["listW"] * 0.75
        assert desc["plainClass"] == "agenda-text"
        assert "has-desc" not in (desc["plainClass"] or "")
        assert desc["plainWhite"] != "nowrap"

        # צבע התיאור כהה מספיק על הציאן (לא שקוף עד כדי היעלמות)
        r, g, b = [int(x) for x in desc["color"].replace("rgba", "rgb").strip("rgba() ").split(",")[:3]]
        # #4b5563 = 75, 85, 99
        assert r < 140 and g < 150 and b < 160

        cdp = context.new_cdp_session(page)
        cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})

        # בקנה מידה 1 גלילת החודשים (הסטרים) עדיין עובדת, והמפריד נשאר touch-action: none
        scale1 = page.evaluate("""() => {
            const stream = document.querySelector('.calendar-stream');
            const handle = document.querySelector('.agenda-resize');
            const cell = document.querySelector('td[data-date]');
            return {
                zoomed: document.documentElement.classList.contains('is-page-zoomed'),
                streamY: getComputedStyle(stream).overflowY,
                streamOverscroll: getComputedStyle(stream).overscrollBehavior,
                handle: getComputedStyle(handle).touchAction,
                cell: getComputedStyle(cell).touchAction,
                top: stream.scrollTop,
            };
        }""")
        assert scale1["zoomed"] is False
        assert scale1["streamY"] == "auto"
        assert scale1["streamOverscroll"] == "contain"
        assert scale1["handle"] == "none"
        assert scale1["cell"] in PAN_OK or "pan-y" in scale1["cell"]

        cell = page.evaluate("""() => {
            const vv = { w: window.innerWidth, h: window.innerHeight };
            for (const el of document.querySelectorAll('#calendar-weeks td[data-date]')) {
                const r = el.getBoundingClientRect();
                if (r.top > 80 && r.bottom < vv.h * 0.55 && r.left >= 0 && r.right <= vv.w) {
                    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                }
            }
            return null;
        }""")
        assert cell, "no visible day cell"
        before_top = page.evaluate("() => document.querySelector('.calendar-stream').scrollTop")
        _drag(cdp, cell["x"], cell["y"], cell["x"], cell["y"] - 140)
        page.wait_for_timeout(200)
        after_top = page.evaluate("() => document.querySelector('.calendar-stream').scrollTop")
        # מגע אנכי מזיז את לוח החודשים. אם headless לא מגלגל מגע, גלגלת העכבר היא הגיבוי.
        if abs(after_top - before_top) < 20:
            page.mouse.move(cell["x"], cell["y"])
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(200)
            after_top = page.evaluate("() => document.querySelector('.calendar-stream').scrollTop")
        assert abs(after_top - before_top) > 20

        anchor = page.evaluate("""() => {
            const stream = document.querySelector('.calendar-stream');
            const y = stream.getBoundingClientRect().top + stream.clientHeight / 2;
            let date = null;
            for (const el of document.querySelectorAll('#calendar-weeks td[data-date]')) {
                const r = el.getBoundingClientRect();
                if (r.top <= y && r.bottom >= y && r.width > 4) {
                    date = el.dataset.date;
                    break;
                }
            }
            return { date, top: stream.scrollTop };
        }""")
        assert anchor["date"]

        cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2.5})
        page.wait_for_function(
            "() => document.documentElement.classList.contains('is-page-zoomed') && window.visualViewport.scale > 1.01",
            timeout=5000,
        )
        styles = page.evaluate("""() => {
            const pick = (sel) => {
                const el = document.querySelector(sel);
                const cs = getComputedStyle(el);
                return {
                    touch: cs.touchAction,
                    overflowX: cs.overflowX,
                    overflowY: cs.overflowY,
                    overscroll: cs.overscrollBehavior,
                };
            };
            return {
                html: pick('html'),
                body: pick('body'),
                stream: pick('.calendar-stream'),
                frame: pick('.calendar-stream-frame'),
                cell: pick('td[data-date]'),
                handle: pick('.agenda-resize'),
                agenda: pick('.day-agenda'),
                list: pick('.day-agenda-list'),
            };
        }""")
        for name in ("html", "body", "stream", "frame", "cell", "handle", "agenda", "list"):
            assert styles[name]["touch"] in PAN_OK, name
        for name in ("stream", "frame", "agenda", "list"):
            # hidden + overscroll auto: הפאן משרשר, וה-scrollTop של החודש נשמר
            assert styles[name]["overflowX"] == "hidden", name
            assert styles[name]["overflowY"] == "hidden", name
            assert styles[name]["overscroll"] == "auto", name
        still = page.evaluate(
            """(date) => {
                const el = document.querySelector(`#calendar-weeks td[data-date="${date}"]`);
                return {
                    top: document.querySelector('.calendar-stream').scrollTop,
                    present: Boolean(el),
                };
            }""",
            anchor["date"],
        )
        assert still["present"]
        assert abs(still["top"] - anchor["top"]) < 2
        assert styles["html"]["overflowX"] == "visible"
        assert styles["body"]["overflowX"] == "visible"
        # המפריד בזום לא נשאר none
        assert styles["handle"]["touch"] != "none"

        _install_prevent_default_spy(page)
        point = page.evaluate("""() => {
            const vv = window.visualViewport;
            for (const el of document.querySelectorAll('#calendar-weeks td[data-date]')) {
                const r = el.getBoundingClientRect();
                if (r.width > 8 && r.left >= 2 && r.top >= 30 && r.bottom <= vv.height - 4 && r.right <= vv.width - 2) {
                    return { x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 24) };
                }
            }
            return { x: vv.width / 2, y: Math.min(180, vv.height / 2) };
        }""")
        before = page.evaluate("() => visualViewport.offsetLeft")
        _drag(cdp, point["x"], point["y"], max(4, point["x"] - 100), point["y"])
        page.wait_for_timeout(200)
        after = page.evaluate("""() => ({
            l: visualViewport.offsetLeft,
            t: visualViewport.offsetTop,
            pd: window.__pd,
            share: document.querySelector('.infinite-calendar').dataset.agendaShare || '',
        })""")
        assert after["l"] > before + 15, after
        assert after["pd"] == []
        # גרירה אנכית מפנה את ה-viewport ולא את גלילת החודש
        up = page.evaluate("() => ({t: visualViewport.offsetTop, top: document.querySelector('.calendar-stream').scrollTop})")
        _drag(cdp, point["x"], min(point["y"], 200), point["x"], 30)
        page.wait_for_timeout(150)
        up_after = page.evaluate("() => ({t: visualViewport.offsetTop, top: document.querySelector('.calendar-stream').scrollTop})")
        assert up_after["t"] > up["t"] + 10
        assert abs(up_after["top"] - anchor["top"]) < 2

        # חזרה לקנה מידה 1 — גלילת החודשים חוזרת
        cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('is-page-zoomed')",
            timeout=5000,
        )
        back = page.evaluate(
            """(date) => {
                const el = document.querySelector(`#calendar-weeks td[data-date="${date}"]`);
                if (!el) return { present: false, top: null, inView: false };
                const r = el.getBoundingClientRect();
                const stream = document.querySelector('.calendar-stream');
                const box = stream.getBoundingClientRect();
                return {
                    present: true,
                    top: stream.scrollTop,
                    inView: r.bottom > box.top && r.top < box.bottom,
                };
            }""",
            anchor["date"],
        )
        assert back["present"]
        assert back["inView"]
        assert abs(back["top"] - anchor["top"]) < 2
        restored = page.evaluate("""() => {
            const stream = document.querySelector('.calendar-stream');
            return {
                y: getComputedStyle(stream).overflowY,
                overscroll: getComputedStyle(stream).overscrollBehavior,
                handle: getComputedStyle(document.querySelector('.agenda-resize')).touchAction,
            };
        }""")
        assert restored["y"] == "auto"
        assert restored["overscroll"] == "contain"
        assert restored["handle"] == "none"
        box = page.locator(".calendar-stream").bounding_box()
        assert box and box["height"] > 40
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        top_back = page.evaluate("() => document.querySelector('.calendar-stream').scrollTop")
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(250)
        top_back_2 = page.evaluate("() => document.querySelector('.calendar-stream').scrollTop")
        assert abs(top_back_2 - top_back) > 20

        browser.close()
