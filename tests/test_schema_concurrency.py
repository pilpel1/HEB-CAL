"""init_db מקבילי: כמה תהליכים וחוטים על DB טרי ועל סכמה ישנה.

הבאג: האפליקציה ו-scripts/reminder_worker.py מייבאים את app ביחד, שניהם
רצים init_db, והשני מת על ALTER TABLE ... recurrence_freq.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from app.database import SCHEMA_VERSION, _schema_execute

REPO = Path(__file__).resolve().parent.parent
WORKERS = 6

_CHILD_SCRIPT = r"""
import os
import sys
import time

os.environ["DATABASE_PATH"] = sys.argv[1]
flag = sys.argv[2]
ready = sys.argv[3]
with open(ready, "w", encoding="utf-8") as handle:
    handle.write("ready")
deadline = time.monotonic() + 30
while not os.path.exists(flag):
    if time.monotonic() > deadline:
        raise SystemExit("start flag was not created")
    time.sleep(0.01)

from app import app
from app.database import init_db

with app.app_context():
    init_db()
print("schema-ok", flush=True)
"""


def _make_fresh(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.close()


def _make_legacy(path: Path) -> None:
    """סכמה של לפני חזרות/משמרות, עם שורה קיימת ותזכורת חלקית."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            gregorian_date TEXT NOT NULL,
            hebrew_date TEXT NOT NULL,
            time TEXT,
            description TEXT,
            end_date TEXT,
            color TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO events (title, gregorian_date, hebrew_date) VALUES ('ישן', '2020-01-02', 'ה טבת')"
    )
    conn.execute(
        "CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER)"
    )
    conn.execute("INSERT INTO reminders (event_id) VALUES (1)")
    conn.commit()
    conn.close()


def _prepare(tmp_path: Path, kind: str) -> Path:
    path = tmp_path / f"{kind}.sqlite"
    if kind == "fresh":
        _make_fresh(path)
    elif kind == "legacy":
        _make_legacy(path)
    else:
        raise AssertionError(kind)
    return path


def _assert_migrated(path: Path, *, legacy: bool) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        assert {
            "recurrence_freq",
            "recurrence_calendar",
            "recurrence_until",
            "recurrence_count",
            "is_shift",
            "shift_person_id",
            "shift_label",
        } <= cols
        people = {row[1] for row in conn.execute("PRAGMA table_info(reminder_people)")}
        assert {"name", "telegram_chat_id", "color", "shift_allowed"} <= people
        reminders = {row[1] for row in conn.execute("PRAGMA table_info(reminders)")}
        assert {"event_id", "offset_minutes", "recipient_ids", "sent_at"} <= reminders
        for table in (
            "events",
            "event_colors",
            "event_exceptions",
            "reminder_sends",
            "reminder_people",
            "reminders",
            "household_settings",
        ):
            found = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            assert found, table
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_events_shift'"
        ).fetchone()
        colors = [row["name"] for row in conn.execute("SELECT name FROM event_colors ORDER BY id")]
        assert colors == ["ציאן", "צהוב", "כתום", "ירוק"]
        settings = conn.execute("SELECT id, shifts_enabled FROM household_settings").fetchall()
        assert [(row["id"], row["shifts_enabled"]) for row in settings] == [(1, 0)]
        if legacy:
            rows = conn.execute("SELECT * FROM events").fetchall()
            assert len(rows) == 1
            row = rows[0]
            assert row["title"] == "ישן"
            assert row["gregorian_date"] == "2020-01-02"
            assert row["hebrew_date"] == "ה טבת"
            assert row["recurrence_freq"] is None
            assert row["recurrence_count"] is None
            assert row["is_shift"] == 0
            assert row["shift_person_id"] is None
            assert row["shift_label"] is None
            reminder = conn.execute(
                "SELECT event_id, offset_minutes, recipient_ids, sent_at FROM reminders"
            ).fetchone()
            assert reminder["event_id"] == 1
            assert reminder["offset_minutes"] == 0
            assert reminder["recipient_ids"] == "[]"
            assert reminder["sent_at"] is None
        else:
            assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    finally:
        conn.close()


def _run_processes(path: Path) -> None:
    flag = path.parent / f"{path.stem}-go.flag"
    env = os.environ.copy()
    env["DATABASE_PATH"] = str(path)
    env["PYTHONPATH"] = str(REPO)
    procs = []
    for index in range(WORKERS):
        ready = path.parent / f"{path.stem}-ready-{index}"
        procs.append(
            subprocess.Popen(
                [sys.executable, "-c", _CHILD_SCRIPT, str(path), str(flag), str(ready)],
                cwd=REPO,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    deadline = time.monotonic() + 30
    ready_paths = [path.parent / f"{path.stem}-ready-{index}" for index in range(WORKERS)]
    while time.monotonic() < deadline:
        if all(item.exists() for item in ready_paths):
            break
        if any(proc.poll() is not None for proc in procs):
            break
        time.sleep(0.02)
    flag.write_text("go", encoding="utf-8")
    failures = []
    for proc in procs:
        stdout, stderr = proc.communicate(timeout=60)
        if proc.returncode != 0 or "schema-ok" not in stdout:
            failures.append(
                f"exit {proc.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
    assert not failures, "\n---\n".join(failures)


def _run_threads(path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(path))
    from app import app
    from app.database import init_db

    errors: list[BaseException] = []
    barrier = threading.Barrier(WORKERS)

    def worker() -> None:
        try:
            barrier.wait(timeout=30)
            with app.app_context():
                init_db()
                init_db()
        except BaseException as exc:  # noqa: BLE001 — נאסף ומוצג בטענה
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()
    assert errors == [], errors


@pytest.mark.parametrize("kind", ["fresh", "legacy"])
def test_concurrent_processes_init_db(tmp_path, kind):
    path = _prepare(tmp_path, kind)
    _run_processes(path)
    _assert_migrated(path, legacy=(kind == "legacy"))


@pytest.mark.parametrize("kind", ["fresh", "legacy"])
def test_concurrent_threads_init_db(tmp_path, monkeypatch, kind):
    path = _prepare(tmp_path, kind)
    _run_threads(path, monkeypatch)
    _assert_migrated(path, legacy=(kind == "legacy"))


def test_concurrent_ensure_functions_on_legacy(tmp_path):
    """ensure_* עצמן, בלי init_db, לא מפילות אחת את השנייה על עמודה כפולה."""
    path = _prepare(tmp_path, "legacy")
    errors: list[BaseException] = []
    barrier = threading.Barrier(WORKERS)

    def worker() -> None:
        try:
            barrier.wait(timeout=30)
            conn = sqlite3.connect(path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                from app.database import ensure_recurrence_schema
                from app.reminders.repository import ensure_reminder_schema
                from app.services.shifts import ensure_shift_schema

                ensure_reminder_schema(conn)
                ensure_recurrence_schema(conn)
                ensure_shift_schema(conn)
            finally:
                conn.close()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()
    assert errors == [], errors

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        assert "recurrence_freq" in cols
        assert "is_shift" in cols
        row = conn.execute("SELECT title, recurrence_freq, is_shift FROM events").fetchone()
        assert row["title"] == "ישן"
        assert row["recurrence_freq"] is None
        assert row["is_shift"] == 0
        assert conn.execute("SELECT COUNT(*) FROM household_settings").fetchone()[0] == 1
    finally:
        conn.close()


def test_failed_migration_rolls_back_and_retries(tmp_path, monkeypatch):
    """שגיאה באמצע המיגרציה לא משאירה user_version גבוה וסכמה חצי-כתובה."""
    path = _prepare(tmp_path, "legacy")
    import app.services.shifts as shifts

    def boom(_db):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(shifts, "ensure_shift_schema", boom)
    conn = sqlite3.connect(path)
    try:
        from app.database import apply_pending_migrations

        with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
            apply_pending_migrations(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        assert "recurrence_freq" not in cols
        assert "is_shift" not in cols
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "event_colors" not in tables
        assert "event_exceptions" not in tables

        monkeypatch.undo()
        apply_pending_migrations(conn)
    finally:
        conn.close()
    _assert_migrated(path, legacy=True)


def test_duplicate_column_and_already_exists_are_success(tmp_path):
    path = tmp_path / "dup.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                gregorian_date TEXT,
                recurrence_freq TEXT
            )
            """
        )
        conn.commit()
        assert _schema_execute(
            conn, "ALTER TABLE events ADD COLUMN recurrence_freq TEXT"
        ) is None
        assert _schema_execute(
            conn, "CREATE TABLE events (id INTEGER PRIMARY KEY)"
        ) is None
        conn.execute("CREATE TABLE reminder_people (id INTEGER PRIMARY KEY, name TEXT)")
        from app.database import ensure_recurrence_schema
        from app.reminders.repository import ensure_reminder_schema
        from app.services.shifts import ensure_shift_schema

        ensure_reminder_schema(conn)
        ensure_recurrence_schema(conn)
        ensure_shift_schema(conn)
        ensure_reminder_schema(conn)
        ensure_recurrence_schema(conn)
        ensure_shift_schema(conn)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(events)")}
        assert "recurrence_freq" in cols
        assert "is_shift" in cols
    finally:
        conn.close()
