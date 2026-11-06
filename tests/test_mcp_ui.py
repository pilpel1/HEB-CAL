"""כרטיס «חיבור לעוזר AI (MCP)» בהגדרות: יצירה חד-פעמית וביטול."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mcp_support import add_user

README = Path(__file__).resolve().parents[1] / "README.md"
GUIDE_URL = "https://github.com/pilpel1/HEB-CAL/blob/main/README.md#mcp"


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
    assert "בחרו את האדם ושם למכשיר" in html
    assert GUIDE_URL in html
    platforms = html.split('id="mcpPlatforms"', 1)[1].split('id="mcpKeyForm"', 1)[0]
    assert "אילו עוזרים מתחברים" in platforms
    assert "עובד:" in platforms and "Cursor" in platforms
    assert "mcp-remote" in platforms and "Node" in platforms and "Tailscale" in platforms
    assert "Bearer" in platforms and "Grok" in platforms and "Bypass" in platforms
    assert "עדיין לא נתמך:" in platforms and "Gemini" in platforms and "ChatGPT" in platforms
    assert "OAuth" in platforms
    assert GUIDE_URL in platforms
    assert html.index('id="mcpPlatforms"') < html.index('id="mcpKeyForm"')
    assert 'id="mcpKeyNoUsers"' in html
    assert 'href="#settings-reminders"' in html
    assert "ב-README" not in html
    assert '<a id="mcp"></a>' in README.read_text(encoding="utf-8")
    assert "/static/js/events/mcp-settings.js" in html
    script = client.get("/static/js/events/mcp-settings.js").get_data(as_text=True)
    assert "mcp-remote@0.16.0" in script
    assert "paintMcpUsers" in script
    assert "data-mcp-mounted" in script or "mcpMounted" in script


def test_mobile_user_select_lists_household_users(live_server, app):
    """הכרטיס נפתח סגור. הרשימה מתמלאת כשהוא מוצג, עם ערך שנבחר באמת."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    add_user(app, "אביחי")
    add_user(app, "שירה")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_server + "/settings", wait_until="load")
        section = page.locator("#settings-mcp")
        expect(section).not_to_have_class(re.compile(r"\bis-open\b"))
        page.locator("#settings-mcp .settings-section-toggle").click()
        select = page.locator("#mcpKeyUser")
        expect(select).to_be_visible()
        expect(select).to_have_attribute("data-mcp-mounted", "visible")
        expect(page.locator("#mcpKeyNoUsers")).to_be_hidden()
        expect(page.locator("#mcpKeyForm")).to_be_visible()
        names = [text.strip() for text in select.locator("option").all_inner_texts()]
        assert set(names) == {"אביחי", "שירה"}
        state = page.evaluate(
            """() => {
                const select = document.getElementById('mcpKeyUser');
                const body = document.getElementById('settings-mcp-body');
                return {
                    index: select.selectedIndex,
                    value: select.value,
                    valid: select.checkValidity(),
                    message: select.validationMessage,
                    shown: getComputedStyle(body).display !== 'none',
                };
            }"""
        )
        assert state["shown"] is True
        assert state["index"] >= 0
        assert state["value"]
        assert state["valid"] is True
        assert state["message"] == ""
        page.locator("#mcpKeyUser").select_option(label="שירה")
        expect(page.locator("#mcpKeyUser option:checked")).to_have_text("שירה")
        page.locator("#mcpKeyUser").select_option(label="אביחי")
        expect(page.locator("#mcpKeyUser option:checked")).to_have_text("אביחי")
        platforms = page.locator("#mcpPlatforms")
        expect(platforms).to_be_visible()
        expect(platforms).to_contain_text("עדיין לא נתמך")
        expect(platforms).to_contain_text("Gemini")
        expect(platforms).to_contain_text("ChatGPT")
        place = page.evaluate(
            """() => {
                const box = document.getElementById('mcpPlatforms').getBoundingClientRect();
                const form = document.getElementById('mcpKeyForm').getBoundingClientRect();
                return { boxTop: box.top, formTop: form.top };
            }"""
        )
        assert place["boxTop"] < place["formTop"]
        guide = page.locator(f'#mcpPlatforms a[href="{GUIDE_URL}"]')
        expect(guide).to_be_visible()
        browser.close()


def test_mobile_without_users_links_to_the_users_section(live_server):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(live_server + "/settings", wait_until="load")
        page.locator("#settings-mcp .settings-section-toggle").click()
        expect(page.locator("#mcpPlatforms")).to_be_visible()
        expect(page.locator("#mcpPlatforms")).to_contain_text("עדיין לא נתמך")
        note = page.locator("#mcpKeyNoUsers")
        expect(note).to_be_visible()
        expect(note).to_contain_text("עדיין אין משתמשים")
        expect(page.locator("#mcpKeyForm")).to_be_hidden()
        expect(page.locator("#mcpKeyUser option")).to_have_count(0)
        page.locator('#mcpKeyNoUsers a[href="#settings-reminders"]').click()
        expect(page.locator("#settings-reminders")).to_have_class(re.compile(r"\bis-open\b"))
        expect(page.locator("#reminderPersonName")).to_be_visible()
        browser.close()


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
        page.locator("#mcpKeyAbsolute").fill("2026-11-20")
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
        expiry = page.evaluate(
            """() => fetch('/api/mcp-keys').then((response) => response.json()).then((data) => {
                const key = data.keys[0];
                const cell = document.querySelector('#mcpKeyList [data-label="תפוגה"]');
                return {
                    effective: key.effective_expires_at,
                    sliding: key.expires_at,
                    cell: cell ? cell.textContent : '',
                    effectiveLabel: formatMcpStamp(key.effective_expires_at),
                    slidingLabel: formatMcpStamp(key.expires_at),
                };
            })"""
        )
        assert expiry["effective"] < expiry["sliding"]
        assert expiry["effectiveLabel"] in expiry["cell"]
        assert expiry["slidingLabel"] not in expiry["cell"]
        page.once("dialog", lambda popup: popup.accept())
        page.locator("[data-mcp-revoke]").click()
        expect(page.locator("#mcpKeyList")).to_contain_text("מבוטל")
        page.reload(wait_until="load")
        assert token not in page.content()
        browser.close()
    assert errors == []
