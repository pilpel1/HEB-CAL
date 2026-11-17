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
    assert 'settings-section-label">גיבוי ושחזור</span>' in settings
    assert 'id="settingsBackup"' in settings
    assert 'data-settings-section="settingsAutoBackup"' not in settings
    assert 'id="settingsAutoBackup"' in settings
    assert "<details" in settings.split('id="settingsAutoBackup"', 1)[0][-80:]
    assert "גיבוי אוטומטי" in settings
    assert "רץ פעם ביום, רק כשהמחשב דולק והיומן פתוח בדפדפן" in settings
    assert 'id="exportEventsBtn">שמירה לקובץ</button>' in settings
    assert 'id="importEventsBtn">שחזור מקובץ</button>' in settings
    assert 'id="importReplaceWarning"' in settings
    assert '"להחליף הכל" מוחק את כל האירועים שיש עכשיו' in settings
    export_at = settings.index('id="exportEventsBtn"')
    import_at = settings.index('id="importEventsBtn"')
    auto_at = settings.index('id="settingsAutoBackup"')
    warn_at = settings.index('id="importReplaceWarning"')
    assert export_at < import_at < warn_at < auto_at
    assert 'id="autoBackupEnabled"' in settings
    assert 'id="autoBackupRetention"' in settings
    assert 'value="3"' in settings
    assert 'min="1"' in settings
    assert 'max="30"' in settings
    assert 'id="autoBackupPickFolder"' in settings
    assert 'id="autoBackupNow"' in settings
    assert 'id="autoBackupApiNote"' in settings
    assert "heb-cal-backup" in settings
    assert "בדפדפן הזה אי אפשר" in settings
    assert "גיבוי יומן" in settings
    assert "Safari" not in settings
    assert "ייצוא" not in settings
    assert "ייבוא" not in settings
    assert "מיזוג" not in settings
    assert "/static/js/events/auto-backup-logic.js" in settings
    assert "/static/js/events/auto-backup.js" in settings
    home = client.get("/").get_data(as_text=True)
    assert "/static/js/events/auto-backup-logic.js" in home
    assert "/static/js/events/auto-backup.js" in home
    events = client.get("/events_list").get_data(as_text=True)
    assert "/static/js/events/auto-backup.js" in events
