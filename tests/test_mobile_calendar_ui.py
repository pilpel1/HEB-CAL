"""הדגשת שורת אירוע ביום, זום-פאן, וחץ כותרת — בלי דפדפן."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVENT_RENDER = REPO / "app/static/js/calendar/event-render.js"
DAY_AGENDA = REPO / "app/static/js/calendar/day-agenda.js"
CONTEXT_MENU = REPO / "app/static/js/events/context-menu.js"
CALENDAR_CSS = REPO / "app/static/css/components/calendar.css"


def _color_helpers_js() -> str:
    src = EVENT_RENDER.read_text(encoding="utf-8")
    start = src.index("const EVENT_COLOR_RGB")
    end = src.index("function getMultiDaySegmentRole")
    return src[start:end]


def _eval_color_cases(cases: list[dict]) -> list:
    script = (
        _color_helpers_js()
        + "const cases = "
        + json.dumps(cases)
        + """;
const out = cases.map((item) => ({
    color: resolveEventColor(item.event, item.people),
    fill: eventChipFill(item.event, item.alpha, item.people),
    rgba: getColorRGBA(item.event && item.event.color, item.alpha),
}));
process.stdout.write(JSON.stringify(out));
"""
    )
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_resolve_event_color_matches_chip_and_person_shift():
    out = _eval_color_cases([
        {"event": {"color": "green"}, "alpha": 0.4},
        {"event": {"color": "yellow"}, "alpha": 1},
        {
            "event": {"is_shift": 1, "shift_person_id": 7},
            "people": [{"id": 7, "color": "orange"}],
            "alpha": 1,
        },
        {"event": {"title": "בלי צבע"}, "alpha": 1},
        {"event": {"color": "#00ffff"}, "alpha": 1},
    ])
    assert out[0]["color"] == "green"
    assert out[0]["fill"] == "rgba(0, 128, 0, 0.4)"
    assert out[1]["color"] == "yellow"
    assert out[1]["fill"] == "rgba(255, 255, 0, 1)"
    assert out[2]["color"] == "orange"
    assert out[2]["fill"] == "rgba(255, 165, 0, 1)"
    assert out[3]["color"] == ""
    assert out[3]["fill"] == ""
    assert out[4]["color"] == "#00ffff"
    assert out[4]["fill"] == "rgba(0, 255, 255, 1)"


def test_agenda_row_reuses_event_chip_color_helpers():
    agenda = DAY_AGENDA.read_text(encoding="utf-8")
    render = EVENT_RENDER.read_text(encoding="utf-8")
    assert "function resolveEventColor" in render
    assert "function eventChipFill" in render
    assert "eventChipFill(ev)" in agenda
    assert "agenda-highlight" in agenda
    # העיגול נשאר כמו קודם — רק לפי event.color
    assert "getColorRGBA(ev.color)" in agenda
    assert "eventChipFill(ev, 1)" not in agenda


def test_agenda_description_is_inline_after_title():
    agenda = DAY_AGENDA.read_text(encoding="utf-8")
    render = EVENT_RENDER.read_text(encoding="utf-8")
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    start = render.index("function escapeHtml")
    end = render.index("const REPEAT_ICON_SVG")
    script = (
        render[start:end]
        + agenda[agenda.index("function agendaDescriptionHtml"):agenda.index("function renderDayAgenda")]
        + """
const cases = [
  { description: '' },
  { description: '   \\n  ' },
  { description: 'פגישה קצרה' },
  { description: 'שורה\\nשנייה  <b>x</b>' },
];
const out = cases.map((ev) => agendaDescriptionHtml(ev));
process.stdout.write(JSON.stringify(out));
"""
    )
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    empty, spaces, short, multiline = json.loads(result.stdout)
    assert empty == ""
    assert spaces == ""
    assert short == '<span class="agenda-desc"> • פגישה קצרה</span>'
    assert multiline == '<span class="agenda-desc"> • שורה שנייה &lt;b&gt;x&lt;/b&gt;</span>'
    assert "agenda-text has-desc" in agenda
    assert "agendaDescriptionHtml(ev)" in agenda
    assert ".agenda-text.has-desc" in css
    assert "text-overflow: ellipsis" in css
    assert ".agenda-desc" in css
    assert "font-weight: 300" in css


def test_page_zoom_skips_custom_gestures_and_allows_pan(client):
    agenda = DAY_AGENDA.read_text(encoding="utf-8")
    menu = CONTEXT_MENU.read_text(encoding="utf-8")
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    html = client.get("/").get_data(as_text=True)

    assert "function isPageZoomed" in agenda
    assert "visualViewport" in agenda
    assert "vv.scale > 1.01" in agenda
    assert "if (isPageZoomed())" in agenda
    assert "is-page-zoomed" in agenda
    assert "isPageZoomed()" in menu
    assert "touch-action: pan-x pan-y pinch-zoom" in css
    assert "html.is-page-zoomed .agenda-resize" in css
    # PR #21 השאיר overscroll-behavior:contain על הסטרים, וזה בלע את הפאן האופקי
    assert "overscroll-behavior: auto" in css
    assert "overflow: clip" not in css
    assert "html.is-page-zoomed:has(.infinite-calendar)" in css
    assert "html.is-page-zoomed body:has(.infinite-calendar)" in css
    assert 'name="viewport" content="width=device-width, initial-scale=1.0"' in html
    assert "user-scalable=no" not in html
    assert "maximum-scale" not in html
    assert "header-collapse-chevron" in html
    assert "header-collapse-grip" not in html
    assert "header-collapse-arrow" not in html
    # המפריד התחתון נשאר בר גרירה
    assert "agenda-resize-grip" in html
    assert 'id="agenda-resize"' in html
