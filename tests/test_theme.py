import pytest


@pytest.mark.parametrize("path", ["/", "/events_list", "/settings"])
def test_pages_include_theme_bootstrap_and_toggle(client, path):
    html = client.get(path).get_data(as_text=True)

    head = html.split("</head>")[0]
    assert "data-bs-theme" in head
    assert "prefers-color-scheme: dark" in head
    # הסקריפט שקובע את הערכה חייב לרוץ לפני ה-CSS כדי למנוע הבהוב
    assert head.index("data-bs-theme") < head.index("bootstrap.rtl.min.css")

    assert "js/theme.js" in html
    if path == "/events_list":
        assert "data-theme-toggle" in html
    if path == "/settings":
        assert "data-theme-switch" in html


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
