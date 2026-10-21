"""הסקריפטים של ה-UI הם קבצים קלאסיים עם scope גלובלי משותף (ראו app/static/js/script.js).

שני דברים שבורים את כל הדף בלי שום שגיאת שרת:
  - קובץ שחסר (404) — הפונקציות שלו פשוט לא קיימות.
  - אותו שם const/let בשני סקריפטים — SyntaxError שמפיל את כל הקובץ השני.
"""
import re

import pytest

SCRIPT_SRC = re.compile(r'<script src="(/static/[^"]+\.js)"')
INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
TOP_LEVEL_LEXICAL = re.compile(r"^(?:const|let|class)\s+(\w+)", re.M)


@pytest.mark.parametrize("page", ["/", "/events_list"])
def test_page_scripts_load_without_lexical_collisions(client, page):
    html = client.get(page).get_data(as_text=True)
    sources = SCRIPT_SRC.findall(html)
    assert "/static/js/script.js" in sources

    owners: dict[str, str] = {}
    bodies = []
    for src in sources:
        response = client.get(src)
        assert response.status_code == 200, src
        bodies.append((src, response.get_data(as_text=True)))
        response.close()
    bodies += [(f"{page} inline #{i}", body) for i, body in enumerate(INLINE_SCRIPT.findall(html))]

    for origin, body in bodies:
        for name in TOP_LEVEL_LEXICAL.findall(body):
            assert name not in owners, f"{name} declared in both {owners[name]} and {origin}"
            owners[name] = origin
