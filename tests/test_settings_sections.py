"""קיפול עצמאי של כרטיסי ההגדרות, כולל משתמשים."""
from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
JS = REPO / "app/static/js/events/settings-sections.js"
SETTINGS = REPO / "app/templates/settings.html"
FORMS = REPO / "app/static/css/components/forms.css"


@pytest.fixture(scope="module")
def live_server(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def _eval(cases: list[dict]) -> list:
    src = JS.read_text(encoding="utf-8")
    start = src.index("function settingsSectionHashId")
    end = src.index("function readSettingsSectionStore")
    script = (
        src[start:end]
        + "const cases = "
        + json.dumps(cases)
        + ";process.stdout.write(JSON.stringify(cases.map((item) => {"
        + "if (item.op === 'hash') return settingsSectionHashId(item.hash);"
        + "return settingsSectionOpenMap(item.stored, item.ids, item.first, item.hashId);"
        + "})));"
    )
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_settings_section_open_map_defaults_and_hash():
    ids = ["settingsUpdate", "settings-display", "settings-reminders", "shiftSettings"]
    out = _eval([
        {"op": "hash", "hash": "#settings-users"},
        {
            "stored": None,
            "ids": ids,
            "first": "settingsUpdate",
            "hashId": "",
        },
        {
            "stored": {"settingsUpdate": False, "settings-reminders": True},
            "ids": ids,
            "first": "settingsUpdate",
            "hashId": "",
        },
        {
            "stored": None,
            "ids": ids,
            "first": "settingsUpdate",
            "hashId": "settings-reminders",
        },
        {
            "stored": {"settingsUpdate": False},
            "ids": ids,
            "first": "settingsUpdate",
            "hashId": "settings-reminders",
        },
    ])
    assert out[0] == "settings-reminders"
    assert out[1] == {
        "settingsUpdate": True,
        "settings-display": False,
        "settings-reminders": False,
        "shiftSettings": False,
    }
    assert out[2]["settingsUpdate"] is False
    assert out[2]["settings-reminders"] is True
    assert out[2]["settings-display"] is False
    assert out[3]["settingsUpdate"] is False
    assert out[3]["settings-reminders"] is True
    assert out[3]["settings-display"] is False
    assert out[4]["settingsUpdate"] is False
    assert out[4]["settings-reminders"] is True


def test_settings_markup_has_independent_sections(client):
    html = client.get("/settings").get_data(as_text=True)
    assert html.count("data-settings-section=") == 10
    assert 'data-settings-section="settings-reminders"' in html
    assert 'settings-section-label">משתמשים</span>' in html
    assert 'data-settings-section="settingsUpdate"' in html
    assert "settings-section is-open" in html
    assert html.count("settings-section is-open") == 1
    css = FORMS.read_text(encoding="utf-8")
    assert ".settings-section:not(.is-open) > .settings-section-body" in css
    js = client.get("/static/js/events/settings-sections.js").get_data(as_text=True)
    assert "heb-cal-settings-sections" in js
    assert "toggleSettingsSection" in js
    page = SETTINGS.read_text(encoding="utf-8")
    assert page.count("class=\"settings-section-toggle\"") == 10


def test_settings_page_loads_section_script(client):
    html = client.get("/settings").get_data(as_text=True)
    assert "/static/js/events/settings-sections.js" in html
    assert "initSettingsSections" in html


def test_settings_sections_toggle_independently_and_persist(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_server + "/settings", wait_until="load")
        update = page.locator("#settingsUpdate")
        users = page.locator("#settings-reminders")
        expect(update).to_have_class(re.compile(r"\bis-open\b"))
        expect(users).not_to_have_class(re.compile(r"\bis-open\b"))
        page.locator("#settings-reminders .settings-section-toggle").click()
        expect(users).to_have_class(re.compile(r"\bis-open\b"))
        expect(update).to_have_class(re.compile(r"\bis-open\b"))
        expect(page.locator("#reminderPersonName")).to_be_visible()
        page.reload(wait_until="load")
        expect(page.locator("#settings-reminders")).to_have_class(re.compile(r"\bis-open\b"))
        expect(page.locator("#settingsUpdate")).to_have_class(re.compile(r"\bis-open\b"))
        browser.close()
