"""מיגרציה אידמפוטנטית לסיכום בוקר בטלגרם.

מוסיפה ``daily_digest_enabled`` (ברירת מחדל 0) ו-``daily_digest_last_sent``
על ``reminder_people``. לא מוחקת שורות. בטוח להריץ שוב.

    python scripts/migrate_digest.py
    python scripts/migrate_digest.py --database /path/to/calendar.db
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
    from app.database import SCHEMA_BUSY_TIMEOUT_MS, apply_pending_migrations

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=SCHEMA_BUSY_TIMEOUT_MS / 1000)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        apply_pending_migrations(conn)
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="מיגרציית סיכום בוקר בטלגרם (אידמפוטנטית)")
    parser.add_argument(
        "--database",
        default=None,
        help="נתיב ל-SQLite. ברירת מחדל: DATABASE_PATH או data/calendar.db",
    )
    args = parser.parse_args(argv)
    path = database_path(args.database)
    migrate(path)
    migrate(path)
    print(f"digest schema ok: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
