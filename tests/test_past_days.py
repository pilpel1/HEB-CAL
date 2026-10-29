"""ימים שעברו בלוח: שעון ירושלים, מחלקת past-day, וגוון בלי להחליש אירועים."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATES_JS = REPO / "app/static/js/core/dates.js"
WEEK_ROWS = REPO / "app/static/js/calendar/week-rows.js"
CALENDAR_CSS = REPO / "app/static/css/components/calendar.css"
DARK_CSS = REPO / "app/static/css/components/dark-theme.css"


def _eval_today(cases: list[str]) -> list[str]:
    script = (
        DATES_JS.read_text(encoding="utf-8")
        + "\nconst cases = "
        + json.dumps(cases)
        + """;
const out = cases.map((iso) => getTodayDateStr(new Date(iso)));
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


def test_get_today_date_str_uses_asia_jerusalem():
    winter_before, winter_after, summer_before, summer_after = _eval_today([
        "2026-01-15T21:30:00.000Z",
        "2026-01-15T22:30:00.000Z",
        "2026-07-15T20:30:00.000Z",
        "2026-07-15T21:30:00.000Z",
    ])
    assert winter_before == "2026-01-15"
    assert winter_after == "2026-01-16"
    assert summer_before == "2026-07-15"
    assert summer_after == "2026-07-16"


def test_week_rows_mark_past_days_from_jerusalem_today():
    js = WEEK_ROWS.read_text(encoding="utf-8")
    assert "getTodayDateStr()" in js
    assert "past-day" in js
    assert "current-day" in js
    assert "today.getFullYear()" not in js


def test_past_day_css_is_subtle_and_skips_today():
    css = CALENDAR_CSS.read_text(encoding="utf-8")
    dark = DARK_CSS.read_text(encoding="utf-8")
    assert "td.past-day:not(.current-day)" in css
    assert "td.current-day" in css
    assert "opacity" not in css.split("td.past-day")[1].split("/*")[0]
    assert ".event-item" not in css.split("td.past-day")[1][:400]
    assert "td.past-day:not(.current-day)" in dark
    assert "rgba(148, 163, 184" in dark
