"""מיגרציית טבלת ``users`` (גרסה 8).

גיבוי ב-``users_backup_v8`` לפני שינוי. אידמפוטנטי. לא מוחק שורות בלי
לשמור אותן בגיבוי, ולא זורק טבלאות ישנות בשקט.
"""
from __future__ import annotations

from app.users.table import (
    LEGACY_NAME_INDEX,
    LEGACY_PEOPLE_TABLE,
    USERS_BACKUP_TABLE,
    USERS_EMAIL_INDEX,
    USERS_NAME_INDEX,
    USERS_TABLE,
    list_tables,
    quote_people_table,
    resolve_people_table,
)


def ensure_people_base_table(db) -> None:
    """יוצר ``reminder_people`` רק אם ``users`` עוד לא קיימת.

    אחרי המיגרציה אסור ליצור שוב ``reminder_people`` ריקה.
    """
    from app.database import _schema_execute

    tables = list_tables(db)
    if USERS_TABLE in tables:
        return
    _schema_execute(
        db,
        """
        CREATE TABLE IF NOT EXISTS reminder_people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_chat_id TEXT
        )
        """,
    )


def _source_people_table(db) -> str | None:
    tables = list_tables(db)
    if USERS_TABLE in tables:
        return USERS_TABLE
    if LEGACY_PEOPLE_TABLE in tables:
        return LEGACY_PEOPLE_TABLE
    return None


def _ensure_people_backup(db, source: str) -> None:
    """עותק חד-פעמי של טבלת האנשים. לא דורסים גיבוי שיש בו שורות."""
    from app.database import _schema_execute

    tables = list_tables(db)
    source = quote_people_table(source)
    if USERS_BACKUP_TABLE not in tables:
        _schema_execute(
            db,
            f"CREATE TABLE {USERS_BACKUP_TABLE} AS SELECT * FROM {source}",
        )
        return
    backup_count = db.execute(
        f"SELECT COUNT(*) FROM {USERS_BACKUP_TABLE}"
    ).fetchone()[0]
    if backup_count:
        return
    source_count = db.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0]
    if source_count:
        db.execute(
            f"INSERT INTO {USERS_BACKUP_TABLE} SELECT * FROM {source}"
        )


def _copy_legacy_rows_into_users(db) -> None:
    """אם שתי הטבלאות קיימות — מעתיקים שורות חסרות ל-users, בלי למחוק את הישנה."""
    tables = list_tables(db)
    if USERS_TABLE not in tables or LEGACY_PEOPLE_TABLE not in tables:
        return
    user_ids = {
        row[0] for row in db.execute(f"SELECT id FROM {USERS_TABLE}")
    }
    user_names = {
        str(row[0] or "").strip().lower()
        for row in db.execute(f"SELECT name FROM {USERS_TABLE}")
    }
    legacy_cols = {row[1] for row in db.execute(f"PRAGMA table_info({LEGACY_PEOPLE_TABLE})")}
    users_cols = {row[1] for row in db.execute(f"PRAGMA table_info({USERS_TABLE})")}
    shared = [col for col in legacy_cols if col in users_cols]
    if not shared:
        return
    quoted = ", ".join(shared)
    for row in db.execute(f"SELECT * FROM {LEGACY_PEOPLE_TABLE} ORDER BY id"):
        keys = row.keys()
        person_id = row["id"]
        name_key = str(row["name"] or "").strip().lower() if "name" in keys else ""
        if person_id in user_ids or (name_key and name_key in user_names):
            continue
        values = [row[col] for col in shared]
        placeholders = ", ".join("?" for _ in shared)
        db.execute(
            f"INSERT INTO {USERS_TABLE} ({quoted}) VALUES ({placeholders})",
            values,
        )
        user_ids.add(person_id)
        if name_key:
            user_names.add(name_key)


def _rename_legacy_people_table(db) -> None:
    """``reminder_people`` → ``users``. אם שתיהן קיימות, הישנה נשמרת בשם orphan."""
    from app.database import _schema_execute

    tables = list_tables(db)
    if LEGACY_PEOPLE_TABLE not in tables:
        return
    if USERS_TABLE not in tables:
        db.execute(f"ALTER TABLE {LEGACY_PEOPLE_TABLE} RENAME TO {USERS_TABLE}")
        return
    _copy_legacy_rows_into_users(db)
    leftover = db.execute(
        f"SELECT 1 FROM {LEGACY_PEOPLE_TABLE} LIMIT 1"
    ).fetchone()
    if leftover is None:
        db.execute(f"DROP TABLE {LEGACY_PEOPLE_TABLE}")
        return
    orphan = "reminder_people_orphaned_v8"
    if orphan in list_tables(db):
        return
    _schema_execute(
        db,
        f"ALTER TABLE {LEGACY_PEOPLE_TABLE} RENAME TO {orphan}",
    )


def _ensure_google_email_column(db) -> None:
    from app.database import _add_column_if_missing

    table = resolve_people_table(db)
    if table not in list_tables(db):
        return
    _add_column_if_missing(db, table, "google_email", "TEXT")


def _ensure_users_indexes(db) -> None:
    from app.database import _schema_execute

    table = resolve_people_table(db)
    if table not in list_tables(db):
        return
    from app.reminders.repository import _has_normalized_name_duplicates

    if not _has_normalized_name_duplicates(db):
        _schema_execute(
            db,
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {USERS_NAME_INDEX}
            ON {table} (lower(trim(name)))
            """,
        )
        _schema_execute(
            db,
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {LEGACY_NAME_INDEX}
            ON {table} (lower(trim(name)))
            """,
        )
    _schema_execute(
        db,
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {USERS_EMAIL_INDEX}
        ON {table} (google_email)
        WHERE google_email IS NOT NULL AND trim(google_email) != ''
        """,
    )


def ensure_users_schema(db) -> None:
    """גיבוי, מיזוג כפילויות, שינוי שם ל-users, אימייל גוגל. אידמפוטנטי."""
    from app.database import exclusive_schema_transaction
    from app.reminders.repository import (
        ensure_unique_people_names,
        merge_compatible_telegram_duplicates,
    )

    with exclusive_schema_transaction(db):
        ensure_people_base_table(db)
        source = _source_people_table(db)
        if source is None:
            from app.database import _schema_execute

            _schema_execute(
                db,
                f"""
                CREATE TABLE IF NOT EXISTS {USERS_TABLE} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    telegram_chat_id TEXT,
                    google_email TEXT
                )
                """,
            )
            source = USERS_TABLE
        _ensure_people_backup(db, source)
        ensure_unique_people_names(db)
        merge_compatible_telegram_duplicates(db)
        _rename_legacy_people_table(db)
        _ensure_google_email_column(db)
        ensure_unique_people_names(db)
        merge_compatible_telegram_duplicates(db)
        _ensure_users_indexes(db)
