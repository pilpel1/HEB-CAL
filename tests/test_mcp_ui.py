"""כרטיס «חיבור לעוזר AI (MCP)» בהגדרות: יצירה חד-פעמית וביטול."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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
    assert html.count(GUIDE_URL) == 1
    assert "כל אירועי הבית" in html
    assert "כל בקשת פרוטוקול שהשרת קיבל" in html
    assert "גם אם הכלי החזיר שגיאה" in html
    assert "HEB_CAL_MCP_KEY" in html
    assert "נשמר בקובץ ההגדרות יחד עם המפתח" in html
    platforms = html.split('id="mcpPlatforms"', 1)[1].split("</div>", 1)[0]
    assert "אילו עוזרים מתחברים" in platforms
    assert "מהמחשב, גם דרך Tailscale" in platforms
    for name in (
        "Cursor", "Claude Desktop", "mcp-remote", "Claude Code", "GitHub Copilot",
        "Gemini CLI", "Cline", "Windsurf", "LM Studio",
    ):
        assert name in platforms
    assert "Grok" in platforms and "grok.com" in platforms and "Copilot Studio" in platforms
    assert "בטא" in platforms and "Bypass" in platforms
    assert "לא נתמך:" in platforms and "OAuth 2.1" in platforms
    assert "ChatGPT" in platforms and "בלי אימות" in platforms
    assert GUIDE_URL not in platforms
    assert html.index('id="mcpPlatforms"') < html.index('id="mcpKeyForm"')
    readme = README.read_text(encoding="utf-8")
    mcp_docs = readme.split('<a id="mcp"></a>', 1)[1].split("### התראות", 1)[0]
    for url in (
        "https://cursor.com/docs/mcp",
        "https://www.npmjs.com/package/mcp-remote",
        "https://code.claude.com/docs/en/mcp",
        "https://code.visualstudio.com/docs/copilot/chat/mcp-servers",
        "https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md",
        "https://github.com/cline/cline/blob/main/docs/mcp/mcp-overview.mdx",
        "https://docs.devin.ai/windsurf/plugins/cascade/mcp",
        "https://lmstudio.ai/docs/app/mcp",
        "https://docs.x.ai/grok/connectors",
        "https://docs.x.ai/developers/tools/remote-mcp",
        "https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent",
        "https://claude.com/docs/connectors/custom/remote-mcp",
        "https://support.google.com/gemini/answer/17209137",
        "https://developers.google.com/connected-apps/mcp/oauth",
        "https://developers.openai.com/api/docs/guides/custom-mcp-server",
        "https://dash.cloudflare.com/?to=/:account/one/access-controls/apps",
        "https://cursor.com/docs/mcp/install-links",
        "https://code.visualstudio.com/api/extension-guides/ai/mcp",
    ):
        assert url in mcp_docs
    assert "one.dash.cloudflare.com" in mcp_docs
    assert 'id="mcpCursorInstall"' in html
    assert 'id="mcpVsCodeInstall"' in html
    assert "cursor://" not in html
    assert "vscode:mcp" not in html
    assert "הוספה ל-Cursor" in html
    assert "התקנה ב-VS Code" in html
    assert "בלי אימות" in mcp_docs
    assert "כל אירועי הבית" in mcp_docs
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
        expect(platforms).to_contain_text("לא נתמך")
        expect(platforms).to_contain_text("OAuth 2.1")
        expect(platforms).to_contain_text("ChatGPT")
        expect(platforms).to_contain_text("Copilot Studio")
        expect(page.locator("#settings-mcp")).to_contain_text("כל אירועי הבית")
        place = page.evaluate(
            """() => {
                const box = document.getElementById('mcpPlatforms').getBoundingClientRect();
                const form = document.getElementById('mcpKeyForm').getBoundingClientRect();
                return { boxTop: box.top, formTop: form.top };
            }"""
        )
        assert place["boxTop"] < place["formTop"]
        guide = page.locator(f'#settings-mcp a[href="{GUIDE_URL}"]')
        expect(guide).to_have_count(1)
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
        expect(page.locator("#mcpPlatforms")).to_contain_text("לא נתמך")
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
        requested = []
        page.on("request", lambda request: requested.append(request.url))
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
        cursor = page.locator("#mcpCursorConfig").text_content()
        assert "${env:HEB_CAL_MCP_KEY}" in cursor
        assert live_server + "/mcp" in cursor
        assert token not in cursor
        claude = page.locator("#mcpClaudeConfig").text_content()
        assert "mcp-remote@0.16.0" in claude
        assert "Authorization:${HEB_CAL_AUTH}" in claude
        assert token in claude
        cursor_href = page.locator("#mcpCursorInstall").get_attribute("href")
        cursor_query = parse_qs(urlparse(cursor_href).query)
        assert cursor_href.startswith("cursor://anysphere.cursor-deeplink/mcp/install?")
        assert cursor_query["name"] == ["heb-cal"]
        cursor_config = json.loads(base64.b64decode(cursor_query["config"][0]))
        assert cursor_config == {
            "url": live_server + "/mcp",
            "headers": {"Authorization": f"Bearer {token}"},
        }
        expect(page.locator("#mcpCursorInstall")).to_be_visible()
        fits = page.evaluate(
            """() => {
                const box = document.querySelector('#mcpKeyModal .modal-content').getBoundingClientRect();
                return box.left >= -1 && box.right <= window.innerWidth + 1;
            }"""
        )
        assert fits is True
        page.locator("#mcpTabVsCode").click()
        expect(page.locator("#mcpVsCodeInstall")).to_be_visible()
        vscode_href = page.locator("#mcpVsCodeInstall").get_attribute("href")
        assert vscode_href.startswith("vscode:mcp/install?")
        vscode_config = json.loads(unquote(vscode_href.split("?", 1)[1]))
        assert vscode_config == {
            "name": "heb-cal",
            "type": "http",
            "url": live_server + "/mcp",
            "headers": {"Authorization": f"Bearer {token}"},
        }
        assert token not in page.url
        assert all(token not in url for url in requested)
        page.locator("#mcpKeyModal .btn-close").click()
        expect(dialog).to_be_hidden()
        page.wait_for_function(
            "() => !document.getElementById('mcpCursorInstall').getAttribute('href')"
        )
        assert token not in (page.locator("#mcpKeyModal").text_content() or "")
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
