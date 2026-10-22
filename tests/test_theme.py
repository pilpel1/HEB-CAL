import pytest


@pytest.mark.parametrize("path", ["/", "/events_list", "/settings"])
def test_pages_include_theme_bootstrap_and_single_settings_toggle(client, path):
    html = client.get(path).get_data(as_text=True)

    head = html.split("</head>")[0]
    assert "data-bs-theme" in head
    assert "prefers-color-scheme: dark" in head
    # הסקריפט שקובע את הערכה חייב לרוץ לפני ה-CSS כדי למנוע הבהוב
    assert head.index("data-bs-theme") < head.index("bootstrap.rtl.min.css")

    assert "js/theme.js" in html
    assert "data-theme-toggle" not in html
    assert "theme_toggle.html" not in html
    if path == "/settings":
        assert html.count("data-theme-switch") == 1
        assert html.count('id="themeSwitch"') == 1
        assert "צבעים" in html
        assert 'id="settingsColors"' in html
        assert 'id="settingsColorHex"' in html
        assert 'type="color"' in html
    else:
        assert "data-theme-switch" not in html
        assert 'id="themeSwitch"' not in html


def test_theme_js_uses_single_shared_key(client):
    response = client.get("/static/js/theme.js")
    try:
        js = response.get_data(as_text=True)
    finally:
        response.close()
    assert "heb-cal-theme" in js
    assert "data-theme-toggle" not in js
    assert "data-theme-switch" in js
    assert js.count("localStorage.setItem") == 1
    assert "heb-cal-theme-events" not in js
    assert "heb-cal-theme-settings" not in js


def test_theme_assets_are_served(client):
    js = client.get("/static/js/theme.js")
    css = client.get("/static/css/components/dark-theme.css")
    try:
        assert js.status_code == 200
        assert css.status_code == 200
    finally:
        js.close()
        css.close()


def test_dark_theme_covers_infinite_calendar_chrome(client):
    """מצב כהה נכתב מול המרקאפ הישן; הלוח האינסופי חייב דריסות משלו."""
    response = client.get("/static/css/components/dark-theme.css")
    try:
        css = response.get_data(as_text=True)
    finally:
        response.close()
    for selector in (
        ".toolbar-month-label",
        ".weekday-header",
        ".calendar-boot-status",
        ".gregorian-date.month-start",
        ".hebrew-date.month-start",
    ):
        assert selector in css
