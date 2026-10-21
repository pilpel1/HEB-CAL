"""מיגרציה אידמפוטנטית לחזרות אירועים.

מוסיפה עמודות על ``events`` (NULL = בלי חזרה), טבלת ``event_exceptions``
וטבלת ``reminder_sends``. לא משנה שורות קיימות. בטוח להריץ שוב ושוב,
גם על בסיס שכבר שודרג.

    python scripts/migrate_recurrence.py
    python scripts/migrate_recurrence.py --database /path/to/calendar.db

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

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # טבלת reminders חייבת להיות קיימת לפני reminder_sends
        ensure_reminder_schema(conn)
        ensure_recurrence_schema(conn)
        conn.commit()
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="מיגרציית סכמה לחזרות אירועים (אידמפוטנטית)")
    parser.add_argument(
        "--database",
        default=None,
        help="נתיב ל-SQLite. ברירת מחדל: DATABASE_PATH או data/calendar.db",
    )
    args = parser.parse_args(argv)
    path = database_path(args.database)
    migrate(path)
    # הרצה שנייה — אותה פונקציה, בלי לשנות נתונים
    migrate(path)
    print(f"recurrence schema ok: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
