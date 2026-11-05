"""כרטיס «חיבור לעוזר AI (MCP)» בהגדרות: יצירה חד-פעמית וביטול."""
from __future__ import annotations

import re

import pytest

from mcp_support import add_user


@pytest.fixture(scope="module")
def live_server(app):
    import threading

    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


def test_settings_mcp_card_is_present(client):
    html = client.get("/settings").get_data(as_text=True)
    assert 'data-settings-section="settings-mcp"' in html
    assert "חיבור לעוזר AI (MCP)" in html
    assert 'id="mcpKeyPermission"' in html
    assert '<option value="read" selected>קריאה בלבד</option>' in html
    assert "/static/js/events/mcp-settings.js" in html
    assert "mcp-remote@0.16.0" in client.get("/static/js/events/mcp-settings.js").get_data(as_text=True)


def test_create_shows_the_key_once_and_revoke_confirms(live_server, app):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    add_user(app, "אביחי")
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(live_server + "/settings", wait_until="load")
        page.locator("#settings-mcp .settings-section-toggle").click()
        expect(page.locator("#mcpKeyUser")).to_be_visible()
        expect(page.locator("#mcpKeyUser option")).to_have_text("אביחי")
        expect(page.locator("#mcpKeyPermission")).to_have_value("read")
        page.locator("#mcpKeyLabel").fill("Cursor בטלפון")
        page.locator("#mcpKeyPermission").select_option("write")
        page.locator("#mcpKeyCreate").click()
        dialog = page.locator("#mcpKeyModal")
        expect(dialog).to_be_visible()
        token = page.locator("#mcpKeyToken").inner_text()
        assert re.fullmatch(r"hcal_[0-9a-f]{8}_[A-Za-z0-9_-]{43}", token)
        cursor = page.locator("#mcpCursorConfig").inner_text()
        assert "${env:HEB_CAL_MCP_KEY}" in cursor
        assert live_server + "/mcp" in cursor
        assert token not in cursor
        claude = page.locator("#mcpClaudeConfig").inner_text()
        assert "mcp-remote@0.16.0" in claude
        assert "Authorization:${HEB_CAL_AUTH}" in claude
        assert token in claude
        page.locator("#mcpKeyModal .btn-close").click()
        expect(dialog).to_be_hidden()
        prefix = "hcal_" + token.split("_")[1]
        expect(page.locator("#mcpKeyList")).to_contain_text(prefix)
        expect(page.locator("#mcpKeyList")).to_contain_text("קריאה וכתיבה")
        assert token not in page.locator("#mcpKeyList").inner_text()
        page.once("dialog", lambda popup: popup.accept())
        page.locator("[data-mcp-revoke]").click()
        expect(page.locator("#mcpKeyList")).to_contain_text("מבוטל")
        page.reload(wait_until="load")
        assert token not in page.content()
        browser.close()
    assert errors == []
