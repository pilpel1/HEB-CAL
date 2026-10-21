"""מיגרציה אידמפוטנטית להזנת משמרות.

מוסיפה על ``events`` את ``is_shift`` (ברירת מחדל 0), ``shift_person_id``
ו-``shift_label``. על ``reminder_people`` צבע וכללי משמרת. טבלת
``household_settings`` עם מתג אחד לבית (כבוי). לא משנה שורות קיימות.
בטוח להריץ שוב ושוב.

    python scripts/migrate_shifts.py
    python scripts/migrate_shifts.py --database /path/to/calendar.db

לא נוגע ב-.env. הנתיב הוא ``--database``, או ``DATABASE_PATH``, או ``data/calendar.db``.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def database_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    import os

    configured = os.getenv("DATABASE_PATH")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path.resolve()
    return (REPO_ROOT / "data" / "calendar.db").resolve()


def migrate(path: Path) -> None:
    from app.database import ensure_recurrence_schema
    from app.reminders.repository import ensure_reminder_schema
    from app.services.shifts import ensure_shift_schema

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
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
        ensure_reminder_schema(conn)
        ensure_recurrence_schema(conn)
        ensure_shift_schema(conn)
        conn.commit()
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="מיגרציית סכמה למשמרות (אידמפוטנטית)")
    parser.add_argument(
        "--database",
        default=None,
        help="נתיב ל-SQLite. ברירת מחדל: DATABASE_PATH או data/calendar.db",
    )
    args = parser.parse_args(argv)
    path = database_path(args.database)
    migrate(path)
    migrate(path)
    print(f"shift schema ok: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
