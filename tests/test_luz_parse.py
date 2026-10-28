"""פענוח לוז מ-Markdown: שבוע הדוגמה, בלי כתיבה לבסיס."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from app.luz.parse import filter_days, format_text_preview, parse_luz
from app.services.event_payload import clean_event_write
from app.services.shifts import shift_columns_from_payload

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "luz_sample_week.md"
SAMPLE_START = date(2026, 10, 28)
SAMPLE_END = date(2026, 11, 3)


def _sample():
    return parse_luz(FIXTURE.read_text(encoding="utf-8"))


def _by_date(parsed):
    return {day["gregorian_date"]: day for day in parsed["days"]}


def test_sample_week_preview_snapshot():
    import json

    gold = json.loads(
        (FIXTURE.parent / "luz_sample_week.preview.json").read_text(encoding="utf-8")
    )
    assert _sample() == gold


def test_sample_week_has_seven_consecutive_days():
    parsed = _sample()
    dates = [day["gregorian_date"] for day in parsed["days"]]
    assert dates == [
        "2026-10-28",
        "2026-10-29",
        "2026-10-30",
        "2026-10-31",
        "2026-11-01",
        "2026-11-02",
        "2026-11-03",
    ]
    assert parsed["stats"]["days"] == 7


def test_date_header_is_not_an_event():
    parsed = _sample()
    for day in parsed["days"]:
        for event in day["events"]:
            assert not event["title"].startswith(day["source_label"])
        assert day["source_label"]
        assert " " in day["source_label"]


def test_pure_shift_lines_are_unassigned_candidates():
    days = _by_date(_sample())
    morning = days["2026-10-30"]
    assert morning["events"] == []
    assert [row["shift_label"] for row in morning["shift_candidates"]] == ["בוקר"]
    evening = days["2026-11-03"]
    assert evening["events"] == []
    assert [row["shift_label"] for row in evening["shift_candidates"]] == ["ערב"]
    for row in morning["shift_candidates"] + evening["shift_candidates"]:
        assert row["is_shift"] == 1
        assert row["shift_person_id"] is None
        assert row["shift_person_name"] is None
        assert row["color"] is None
        assert row["time"] is None


def test_mixed_lines_stay_events_with_shift_hints_not_ownership():
    days = _by_date(_sample())
    pilates = days["2026-10-28"]["events"]
    assert len(pilates) == 1
    assert pilates[0]["is_shift"] == 0
    assert pilates[0]["time"] == "08:30"
    assert "פילאטיס מכשירים" in pilates[0]["title"]
    assert pilates[0]["shift_hints"] == ["בוקר", "ערב"]
    assert days["2026-10-28"]["shift_candidates"] == []

    friday_prep = days["2026-10-29"]["events"]
    assert len(friday_prep) == 1
    assert friday_prep[0]["time"] == "15:30"
    assert friday_prep[0]["shift_hints"] == ["ערב"]

    families = days["2026-11-01"]["events"]
    assert len(families) == 1
    assert families[0]["time"] is None
    assert "21 משפחות חדשות" in families[0]["title"]
    assert families[0]["shift_hints"] == ["בוקר"]

    laufer = days["2026-11-02"]["events"]
    assert len(laufer) == 1
    assert laufer[0]["time"] is None
    assert "9 לאופר לתיפי" in laufer[0]["title"]
    assert laufer[0]["shift_hints"] == ["בוקר", "לילה"]


def test_parsha_saturday_is_a_normal_event():
    day = _by_date(_sample())["2026-10-31"]
    assert day["shift_candidates"] == []
    assert len(day["events"]) == 1
    assert day["events"][0]["title"] == "וירא בבית"
    assert day["events"][0]["is_shift"] == 0
    assert day["events"][0].get("shift_hints") is None


def test_no_name_heuristic_assigns_avichay_or_shira():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| טז 27.10 בחירות (אביחי קולט) 11:30 | ח 16.10 אביחי בוקר שירה ערב |\n"
        "| ----: | ----: |\n"
    )
    for row in parsed["records"]:
        assert row["shift_person_id"] is None
        assert row["shift_person_name"] is None
        assert row["color"] is None
        assert row["is_shift"] == 0
    by_date = _by_date(parsed)
    assert by_date["2026-10-27"]["events"][0]["time"] == "11:30"
    named = by_date["2026-10-16"]["events"][0]
    assert "אביחי" in named["title"] and "שירה" in named["title"]
    assert named["shift_hints"] == ["בוקר", "ערב"]


def test_strikethrough_days_are_still_imported():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| ~~יד 25.10 בוקר~~ | יז 28.10 בוקר |\n"
        "| ----: | ----: |\n"
    )
    days = _by_date(parsed)
    assert "2026-10-25" in days
    assert days["2026-10-25"]["shift_candidates"][0]["shift_label"] == "בוקר"
    assert days["2026-10-28"]["shift_candidates"][0]["shift_label"] == "בוקר"


def test_soft_break_splits_separate_events():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| כז 7.11 חיי שרה ערב\x0bקורקוס (יומולדת) |\n"
        "| ----: |\n"
    )
    day = parsed["days"][0]
    assert day["gregorian_date"] == "2026-11-07"
    titles = [event["title"] for event in day["events"]]
    assert titles == ["חיי שרה ערב", "קורקוס (יומולדת)"]
    assert day["events"][0]["shift_hints"] == ["ערב"]
    assert day["shift_candidates"] == []


def test_it_and_modifiers_are_unassigned_shift_candidates():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| כד 2.11 אביחי IT | כה 3.11 בוקר מאוחר | כו 4.11 משמרת it |\n"
        "| ----: | ----: | ----: |\n"
    )
    days = _by_date(parsed)
    named_it = days["2026-11-02"]
    assert named_it["shift_candidates"] == []
    assert named_it["events"][0]["shift_hints"] == ["IT"]
    late = days["2026-11-03"]["shift_candidates"]
    assert [row["shift_label"] for row in late] == ["בוקר"]
    assert late[0]["shift_person_name"] is None
    it_only = days["2026-11-04"]["shift_candidates"]
    assert [row["shift_label"] for row in it_only] == ["IT"]


def test_records_match_existing_event_and_shift_fields():
    parsed = _sample()
    for row in parsed["records"]:
        payload = {key: row[key] for key in ("title", "gregorian_date", "hebrew_date", "time", "description", "end_date", "color")}
        cleaned = clean_event_write(payload)
        assert cleaned["title"] == row["title"]
        assert cleaned["gregorian_date"] == row["gregorian_date"]
        shift = shift_columns_from_payload(row, missing="defaults")
        if row["is_shift"]:
            assert shift == (1, None, row["shift_label"])
        else:
            assert shift == (0, None, None)


def test_hebrew_dates_come_from_existing_formatter():
    from app.services.recurrence import hebrew_display

    days = _by_date(_sample())
    assert days["2026-10-28"]["hebrew_date"] == hebrew_display(date(2026, 10, 28))
    assert days["2026-11-01"]["hebrew_date"] == hebrew_display(date(2026, 11, 1))


def test_filter_days_keeps_sample_range():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| יד 25 בוקר | יז 28 בוקר | כא 1.11 ערב | כד 4 בוקר |\n"
        "| ----: | ----: | ----: | ----: |\n"
    )
    sliced = filter_days(parsed, SAMPLE_START, SAMPLE_END)
    assert [day["gregorian_date"] for day in sliced["days"]] == ["2026-10-28", "2026-11-01"]


def test_cli_preview_prints_json_without_touching_db(tmp_path):
    import json
    import os
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["DATABASE_PATH"] = str(tmp_path / "cli.sqlite")
    script = root / "scripts" / "luz_preview.py"
    json_run = subprocess.run(
        [sys.executable, str(script), str(FIXTURE)],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert json_run.returncode == 0, json_run.stderr
    body = json.loads(json_run.stdout)
    assert body["stats"]["days"] == 7
    text_run = subprocess.run(
        [sys.executable, str(script), str(FIXTURE), "--text"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert text_run.returncode == 0, text_run.stderr
    assert "2026-10-28" in text_run.stdout
    assert "בלי שיוך" in text_run.stdout
    assert format_text_preview(_sample()).startswith("ימים: 7")
    assert "calendar.db" not in json_run.stdout
