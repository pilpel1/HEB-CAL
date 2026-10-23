"""פס הניווט בהגדרות נשאר למעלה ולא מכסה עוגנים."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FORMS = REPO / "app/static/css/components/forms.css"


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def test_settings_nav_css_matches_theme_and_offsets_anchors():
    css = FORMS.read_text(encoding="utf-8")
    top = css.split(".settings-top {", 1)[1].split("}", 1)[0]
    assert "position: sticky" in top
    assert "top: 0" in top
    assert "var(--background-color)" in top
    assert "scroll-margin-top: var(--settings-sticky-offset)" in css
    page = (REPO / "app/templates/settings.html").read_text(encoding="utf-8")
    assert 'class="settings-nav"' in page
    assert 'href="/"' in page
    assert 'href="/events_list"' in page
    assert 'id="settings-reminders"' in page


def _layout(page):
    return page.evaluate(
        """() => {
            const nav = document.querySelector('.settings-top');
            const anchor = document.getElementById('settings-reminders');
            const bodyBg = getComputedStyle(document.body).backgroundColor;
            const navBg = getComputedStyle(nav).backgroundColor;
            const box = (el) => {
                const r = el.getBoundingClientRect();
                return { top: r.top, bottom: r.bottom, height: r.height, left: r.left, right: r.right };
            };
            return {
                nav: box(nav),
                anchor: box(anchor),
                bodyBg,
                navBg,
                vh: window.innerHeight,
                vw: window.innerWidth,
                sticky: getComputedStyle(nav).position,
            };
        }"""
    )


@pytest.mark.parametrize("width,height", [(1280, 700), (390, 844)])
def test_settings_nav_sticks_and_anchor_stays_clear(live_server, width, height):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(live_server + "/settings#settings-reminders", wait_until="networkidle")
        page.evaluate("() => document.documentElement.setAttribute('data-bs-theme', 'light')")
        page.evaluate(
            "() => document.getElementById('settings-reminders').scrollIntoView({block: 'start'})"
        )
        # Bootstrap שם scroll-behavior:smooth על :root, אז scrollIntoView הוא אנימציה.
        # העמוד ארוך יותר אחרי בלוק יומן גוגל; מחכים שהעוגן ינחת מתחת לפס.
        page.wait_for_function(
            """() => {
                const nav = document.querySelector('.settings-top');
                const anchor = document.getElementById('settings-reminders');
                if (!nav || !anchor) return false;
                const gap = anchor.getBoundingClientRect().top - nav.getBoundingClientRect().bottom;
                return gap >= -1 && gap <= 20;
            }""",
            timeout=4000,
        )
        landed = _layout(page)
        assert landed["sticky"] == "sticky"
        assert landed["nav"]["top"] <= 1, landed
        assert landed["anchor"]["top"] >= landed["nav"]["bottom"] - 1, landed
        assert landed["anchor"]["top"] <= landed["nav"]["bottom"] + 20, landed
        assert landed["navBg"] == landed["bodyBg"], landed
        if width <= 480:
            assert landed["nav"]["height"] <= 48, landed

        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        stuck = _layout(page)
        assert stuck["nav"]["top"] <= 1, stuck
        assert stuck["nav"]["bottom"] > 24, stuck
        assert stuck["nav"]["right"] <= width + 1, stuck
        assert stuck["nav"]["left"] >= -1, stuck

        page.evaluate("() => document.documentElement.setAttribute('data-bs-theme', 'dark')")
        dark = _layout(page)
        assert dark["navBg"] == dark["bodyBg"], dark
        assert dark["navBg"] != landed["navBg"]
        browser.close()
