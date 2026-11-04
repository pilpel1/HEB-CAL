"""שם טבלת המשתמשים החייה — users אחרי מיגרציה 8, reminder_people לפניה."""
from __future__ import annotations

USERS_TABLE = "users"
LEGACY_PEOPLE_TABLE = "reminder_people"
USERS_BACKUP_TABLE = "users_backup_v8"
USERS_NAME_INDEX = "idx_users_name_norm"
LEGACY_NAME_INDEX = "idx_reminder_people_name_norm"
USERS_EMAIL_INDEX = "idx_users_google_email"

_ALLOWED_PEOPLE_TABLES = frozenset({USERS_TABLE, LEGACY_PEOPLE_TABLE})


def list_tables(db) -> set[str]:
    return {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def resolve_people_table(db) -> str:
    """טבלת האנשים החיה. אחרי גרסה 8 זה תמיד ``users``."""
    tables = list_tables(db)
    if USERS_TABLE in tables:
        return USERS_TABLE
    return LEGACY_PEOPLE_TABLE


def quote_people_table(name: str) -> str:
    if name not in _ALLOWED_PEOPLE_TABLES:
        raise ValueError(f"illegal people table: {name}")
    return name
