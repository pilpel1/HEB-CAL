"""בורר הצבע של אדם מגיע מאותה פלטה כמו שאר המסכים, כולל צבע שנוסף עכשיו."""
from __future__ import annotations

import threading
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


@pytest.fixture(scope="module")
def live_server(app):
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _colors_path(url: str) -> str:
    return urlparse(url).path


def test_custom_color_shows_in_person_picker_and_survives_delete(live_server):
    errors = []
    held = []
    state = {"held": False}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.on("pageerror", lambda err: errors.append(str(err)))

        def hold_first_palette(route):
            is_palette = route.request.method == "GET" and _colors_path(route.request.url) == "/api/colors"
            if is_palette and not state["held"]:
                state["held"] = True
                held.append(route)
                return
            route.continue_()

        page.route("**/api/colors", hold_first_palette)
        page.goto(live_server + "/settings", wait_until="domcontentloaded")
        for _ in range(40):
            if held:
                break
            page.wait_for_timeout(50)
        assert held, "טעינת הפלטה הראשונה לא יצאה"

        page.locator("#settingsColorHex").evaluate("(el) => { el.value = '#ffcc88'; }")
        page.locator("#settingsColorName").fill("כתום בהיר")
        with page.expect_response(
            lambda response: (
                response.request.method == "GET"
                and _colors_path(response.url) == "/api/colors"
                and response.status == 200
            )
        ) as fresh:
            page.locator("#settingsColorSave").click()
        assert "no-store" in fresh.value.headers.get("cache-control", "")

        custom = page.locator('#personColorPicker [data-color="#ffcc88"]')
        expect(custom).to_have_count(1)
        expect(page.locator("#settingsColorsList")).to_contain_text("כתום בהיר")
        for code in ("cyan", "yellow", "orange", "green"):
            expect(page.locator(f'#personColorPicker [data-color="{code}"]')).to_have_count(1)

        held.pop().continue_()
        page.wait_for_timeout(400)
        expect(custom).to_have_count(1)
        expect(page.locator("#settingsColorsList")).to_contain_text("כתום בהיר")

        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#shiftsEnabled").click()
        expect(page.locator("#shiftPeoplePanel")).to_be_visible()
        swatch_box = custom.bounding_box()
        assert swatch_box is not None
        assert swatch_box["width"] >= 40
        assert swatch_box["height"] >= 40
        custom.click()
        expect(custom).to_have_class("quick-color-swatch is-selected")
        page.locator("#shiftPersonName").fill("נועה")
        page.locator("#shiftPersonSave").click()
        row = page.locator("#shiftPeopleList .reminder-person-row", has_text="נועה")
        expect(row).to_be_visible()
        dot = row.locator(".shift-color-dot")
        expect(dot).to_have_css("background-color", "rgb(255, 204, 136)")
        expect(dot).to_have_attribute("title", "כתום בהיר")

        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#settingsColorsList .settings-color-row", has_text="כתום בהיר").locator(
            "[data-color-delete]"
        ).click()
        expect(page.locator("#settingsColorError")).to_contain_text("שימוש")
        expect(dot).to_have_css("background-color", "rgb(255, 204, 136)")
        expect(page.locator("#settingsColorsList")).to_contain_text("כתום בהיר")

        orphan = page.evaluate(
            """() => {
                eventColorPalette = eventColorPalette.filter((color) => color.color_code !== '#ffcc88');
                const dot = document.createElement('span');
                applyShiftColorDot(dot, '#ffcc88');
                shiftUiState.personColor = '#ffcc88';
                shiftUiState.colorIsSuggested = false;
                shiftUiState.rulesDirty = true;
                paintPersonColorSwatches(currentEventColors());
                const swatch = document.querySelector('#personColorPicker [data-color="#ffcc88"]');
                return {
                    background: dot.style.backgroundColor,
                    hidden: dot.hidden,
                    selected: Boolean(swatch && swatch.classList.contains('is-selected')),
                };
            }"""
        )
        assert orphan["hidden"] is False
        assert orphan["background"].replace(" ", "") in ("#ffcc88", "rgb(255,204,136)")
        assert orphan["selected"] is True

        page.goto(live_server + "/", wait_until="domcontentloaded")
        expect(page.locator('#quickEventModal [data-color="#ffcc88"]')).to_have_count(1)
        page.goto(live_server + "/events_list", wait_until="domcontentloaded")
        option = page.locator('#colorSearch option[value="#ffcc88"]')
        expect(option).to_have_count(1)
        expect(option).to_have_text("כתום בהיר")

        context.close()
        browser.close()

    assert errors == []
