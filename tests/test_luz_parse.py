"""פענוח לוז מ-Markdown: שבוע הדוגמה, בלי כתיבה לבסיס."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from app.luz.parse import SHIFT_NOTE, filter_days, format_text_preview, parse_luz
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
    assert parsed["stats"]["events"] == 5
    assert parsed["stats"]["skipped_shift_lines"] == 2
    assert parsed["notes"] == [SHIFT_NOTE]


def test_date_header_is_not_an_event():
    parsed = _sample()
    for day in parsed["days"]:
        for event in day["events"]:
            assert not event["title"].startswith(day["source_label"])
        assert day["source_label"]
        assert " " in day["source_label"]


def test_bare_shift_lines_are_skipped_not_assigned():
    days = _by_date(_sample())
    assert days["2026-10-30"]["events"] == []
    assert days["2026-10-30"]["skipped_shift_lines"] == 1
    assert days["2026-11-03"]["events"] == []
    assert days["2026-11-03"]["skipped_shift_lines"] == 1
    for row in _sample()["records"]:
        assert row["is_shift"] == 0
        assert row["shift_person_id"] is None
        assert row.get("shift_hints") is None


def test_mixed_and_plain_lines_import_as_events():
    days = _by_date(_sample())
    pilates = days["2026-10-28"]["events"]
    assert len(pilates) == 1
    assert pilates[0]["is_shift"] == 0
    assert pilates[0]["time"] == "08:30"
    assert pilates[0]["title"] == "בוקר (עד 12) 8:30 פילאטיס מכשירים ערב"

    friday_prep = days["2026-10-29"]["events"]
    assert len(friday_prep) == 1
    assert friday_prep[0]["time"] == "15:30"
    assert "תור טלפוני לאופר" in friday_prep[0]["title"]

    families = days["2026-11-01"]["events"]
    assert len(families) == 1
    assert families[0]["time"] is None
    assert families[0]["title"] == "בוקר 21 משפחות חדשות"

    laufer = days["2026-11-02"]["events"]
    assert len(laufer) == 1
    assert laufer[0]["time"] is None
    assert laufer[0]["title"] == "בוקר לילה 9 לאופר לתיפי"


def test_parsha_saturday_is_a_normal_event():
    day = _by_date(_sample())["2026-10-31"]
    assert day["skipped_shift_lines"] == 0
    assert len(day["events"]) == 1
    assert day["events"][0]["title"] == "וירא בבית"
    assert day["events"][0]["is_shift"] == 0


def test_named_text_is_still_an_event_not_a_shift_owner():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| טז 27.10 בחירות (אביחי קולט) 11:30 | ח 16.10 אביחי בוקר שירה ערב |\n"
        "| ----: | ----: |\n"
    )
    assert parsed["notes"] == []
    for row in parsed["records"]:
        assert row["shift_person_id"] is None
        assert row["is_shift"] == 0
    by_date = _by_date(parsed)
    assert by_date["2026-10-27"]["events"][0]["time"] == "11:30"
    named = by_date["2026-10-16"]["events"][0]
    assert named["title"] == "אביחי בוקר שירה ערב"


def test_strikethrough_days_are_still_imported():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| ~~יד 25.10 דייט~~ | יז 28.10 פילאטיס |\n"
        "| ----: | ----: |\n"
    )
    days = _by_date(parsed)
    assert days["2026-10-25"]["events"][0]["title"] == "דייט"
    assert days["2026-10-28"]["events"][0]["title"] == "פילאטיס"
    assert parsed["notes"] == []


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
    assert parsed["notes"] == []


def test_bare_it_and_modifiers_are_parked_in_the_html_note():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| כד 2.11 אביחי IT | כה 3.11 בוקר מאוחר | כו 4.11 משמרת it |\n"
        "| ----: | ----: | ----: |\n"
    )
    days = _by_date(parsed)
    assert days["2026-11-02"]["events"][0]["title"] == "אביחי IT"
    assert days["2026-11-03"]["events"] == []
    assert days["2026-11-04"]["events"] == []
    assert parsed["stats"]["skipped_shift_lines"] == 2
    assert parsed["notes"] == [SHIFT_NOTE]


def test_records_match_existing_event_fields():
    parsed = _sample()
    assert parsed["records"]
    for row in parsed["records"]:
        payload = {
            key: row[key]
            for key in ("title", "gregorian_date", "hebrew_date", "time", "description", "end_date", "color")
        }
        cleaned = clean_event_write(payload)
        assert cleaned["title"] == row["title"]
        assert cleaned["gregorian_date"] == row["gregorian_date"]
        assert shift_columns_from_payload(row, missing="defaults") == (0, None, None)


def test_hebrew_dates_come_from_existing_formatter():
    from app.services.recurrence import hebrew_display

    days = _by_date(_sample())
    assert days["2026-10-28"]["hebrew_date"] == hebrew_display(date(2026, 10, 28))
    assert days["2026-11-01"]["hebrew_date"] == hebrew_display(date(2026, 11, 1))


def test_filter_days_keeps_sample_range():
    parsed = parse_luz(
        "## תשפ\"ז\n\n"
        "| יד 25 דייט | יז 28 פילאטיס | כא 1.11 משפחות | כד 4 בוקר |\n"
        "| ----: | ----: | ----: | ----: |\n"
    )
    sliced = filter_days(parsed, SAMPLE_START, SAMPLE_END)
    assert [day["gregorian_date"] for day in sliced["days"]] == ["2026-10-28", "2026-11-01"]
    assert sliced["stats"]["events"] == 2
    assert sliced["notes"] == []


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
    assert body["notes"] == [SHIFT_NOTE]
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
    assert SHIFT_NOTE in text_run.stdout
    assert format_text_preview(_sample()).startswith("ימים: 7")
    assert "calendar.db" not in json_run.stdout
