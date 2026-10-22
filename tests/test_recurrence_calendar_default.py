"""ברירת המחדל של לוח החזרה לפי הבורר האחרון — בלי לדרוס בחירה מפורשת."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node") or "/exec-daemon/node"


def test_recurrence_calendar_default_follows_the_last_picker_until_locked():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('app/static/js/events/quick-event-modal.js', 'utf8');
const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const fn = sandbox.recurrenceCalendarForDateEntry;
if (typeof fn !== 'function') {
  throw new Error('recurrenceCalendarForDateEntry is not global');
}
const cases = [
  ['hebrew', false, 'hebrew'],
  ['gregorian', false, 'gregorian'],
  ['hebrew', true, null],
  ['gregorian', true, null],
  [null, false, null],
  ['', false, null],
];
for (const [source, touched, expected] of cases) {
  const got = fn(source, touched);
  if (got !== expected) {
    throw new Error(JSON.stringify({ source, touched, got, expected }));
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
