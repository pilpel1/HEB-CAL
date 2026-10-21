import os
import tempfile

import pytest

os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from app import app as flask_app  # noqa: E402


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/events_list"])
def test_pages_include_theme_bootstrap_and_toggle(client, path):
    html = client.get(path).get_data(as_text=True)

    head = html.split("</head>")[0]
    assert "data-bs-theme" in head
    assert "prefers-color-scheme: dark" in head
    # הסקריפט שקובע את הערכה חייב לרוץ לפני ה-CSS כדי למנוע הבהוב
    assert head.index("data-bs-theme") < head.index("bootstrap.rtl.min.css")

    assert "data-theme-toggle" in html
    assert "js/theme.js" in html


def test_theme_assets_are_served(client):
    assert client.get("/static/js/theme.js").status_code == 200
    assert client.get("/static/css/components/dark-theme.css").status_code == 200
