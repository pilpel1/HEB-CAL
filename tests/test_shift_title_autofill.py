"""כפתור משמרת לא דורס כותרת שהמשתמש כתב."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node") or "/exec-daemon/node"


def test_shift_button_fills_only_empty_or_autofilled_title():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('app/static/js/events/shifts.js', 'utf8');
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const fn = sandbox.shiftTitleAfterPick;
if (typeof fn !== 'function') {
  throw new Error('shiftTitleAfterPick is not global');
}
const cases = [
  ['', '', 'בוקר', 'בוקר', true, 'בוקר'],
  ['   ', 'בוקר', 'ערב', 'ערב', true, 'ערב'],
  ['בוקר', 'בוקר', 'ערב', 'ערב', true, 'ערב'],
  ['בוקר מוקדם', 'בוקר', 'ערב', 'בוקר מוקדם', false, 'בוקר'],
  ['בוקר', '', 'ערב', 'בוקר', false, ''],
  ['יום מחלה', 'לילה', 'בוקר', 'יום מחלה', false, 'לילה'],
];
for (const [current, auto, next, title, filled, keptAuto] of cases) {
  const result = fn(current, auto, next);
  if (result.title !== title || result.filled !== filled || result.auto !== keptAuto) {
    throw new Error(JSON.stringify({ current, auto, next, result, title, filled, keptAuto }));
  }
}
"""
    completed = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_custom_shift_title_stays_when_the_type_changes(client):
    person = client.post("/api/reminder-people", json={
        "name": "אביחי",
        "color": "cyan",
    })
    assert person.status_code == 201, person.get_json()
    person_id = person.get_json()["id"]
    client.put("/api/shifts/settings", json={"enabled": True})

    created = client.post("/api/events", json={
        "title": "בוקר מוקדם",
        "gregorian_date": "2026-10-21",
        "hebrew_date": "א",
        "is_shift": True,
        "shift_person_id": person_id,
        "shift_label": "בוקר",
    })
    assert created.status_code == 200, created.get_json()
    event_id = created.get_json()["id"]
    event = client.get(f"/api/events/{event_id}").get_json()
    assert event["title"] == "בוקר מוקדם"
    assert event["shift_label"] == "בוקר"
    assert event["color"] == "cyan"

    switched = client.put(f"/api/events/{event_id}", json={
        "title": "בוקר מוקדם",
        "gregorian_date": "2026-10-21",
        "hebrew_date": event["hebrew_date"],
        "is_shift": True,
        "shift_person_id": person_id,
        "shift_label": "ערב",
    })
    assert switched.status_code == 200, switched.get_json()
    again = client.get(f"/api/events/{event_id}").get_json()
    assert again["title"] == "בוקר מוקדם"
    assert again["shift_label"] == "ערב"
    assert again["color"] == "cyan"

    week = client.put("/api/shifts/week", json={
        "person_id": person_id,
        "week_start": "2026-10-18",
        "cells": [{"date": "2026-10-21", "label": "ערב"}],
    })
    assert week.status_code == 200, week.get_json()
    assert event_id in week.get_json()["kept"]
    kept = client.get(f"/api/events/{event_id}").get_json()
    assert kept["title"] == "בוקר מוקדם"
    assert kept["shift_label"] == "ערב"
