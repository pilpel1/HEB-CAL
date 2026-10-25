"""גיבוי אוטומטי: כללים טהורים (Node) + הסימון במסך ההגדרות."""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_auto_backup_logic_node():
    script = REPO / "tests" / "auto_backup_logic_check.js"
    result = subprocess.run(
        ["node", str(script)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_settings_auto_backup_markup(client):
    settings = client.get("/settings").get_data(as_text=True)
    assert 'id="settingsAutoBackup"' in settings
    assert "גיבוי אוטומטי" in settings
    assert "הגיבוי רץ רק כשהמחשב הזה דולק, מחובר לאינטרנט, והיומן פתוח בדפדפן" in settings
    assert 'id="autoBackupEnabled"' in settings
    assert 'id="autoBackupRetention"' in settings
    assert 'value="3"' in settings
    assert 'min="1"' in settings
    assert 'max="30"' in settings
    assert 'id="autoBackupPickFolder"' in settings
    assert 'id="autoBackupNow"' in settings
    assert 'id="autoBackupApiNote"' in settings
    assert "heb-cal-backup" in settings
    assert "Safari" in settings
    assert "/static/js/events/auto-backup-logic.js" in settings
    assert "/static/js/events/auto-backup.js" in settings
    assert 'id="exportEventsBtn"' in settings
    home = client.get("/").get_data(as_text=True)
    assert "/static/js/events/auto-backup-logic.js" in home
    assert "/static/js/events/auto-backup.js" in home
    events = client.get("/events_list").get_data(as_text=True)
    assert "/static/js/events/auto-backup.js" in events
