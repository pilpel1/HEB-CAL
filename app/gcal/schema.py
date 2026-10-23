"""עמודות וטבלה לסנכרון יומן גוגל. אידמפוטנטי, בלי מחיקת שורות."""
from __future__ import annotations

from app.database import _add_column_if_missing, _schema_execute, exclusive_schema_transaction

_EVENT_COLUMNS = (
    ("gcal_source_id", "INTEGER"),
    ("gcal_uid", "TEXT"),
    ("gcal_recurrence_id", "TEXT NOT NULL DEFAULT ''"),
)


def ensure_gcal_schema(db) -> None:
    """מקורות iCal, ומזהה גוגל על אירוע כדי שסנכרון יעדכן ולא ישכפל.

    שורות קיימות נשארות עם ``gcal_source_id`` ריק. אין כאן DELETE.
    """
    with exclusive_schema_transaction(db):
        _schema_execute(
            db,
            """
            CREATE TABLE IF NOT EXISTS gcal_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                ical_url TEXT NOT NULL,
                color TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_sync_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
        for name, decl in _EVENT_COLUMNS:
            _add_column_if_missing(db, "events", name, decl)
        _schema_execute(
            db,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_gcal_identity
            ON events (gcal_source_id, gcal_uid, gcal_recurrence_id)
            WHERE gcal_source_id IS NOT NULL AND gcal_uid IS NOT NULL
            """,
        )
