"""מצב שיחה לכל צ'אט. נשמר ב-SQLite כדי שסבב ה-worker לא שוכח באמצע."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.database import get_db


def ensure_bot_schema(db) -> None:
    """טבלה אחת. בלי העלאת user_version — ה-DDL אידמפוטנטי."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_sessions (
            chat_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
        """
    )
    db.commit()


def load_session(chat_id) -> dict:
    db = get_db()
    row = db.execute(
        "SELECT payload FROM bot_sessions WHERE chat_id = ?",
        (str(chat_id),),
    ).fetchone()
    if row is None:
        return {}
    try:
        data = json.loads(row["payload"] or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_session(chat_id, payload: dict) -> None:
    db = get_db()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        """
        INSERT INTO bot_sessions (chat_id, payload, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            payload = excluded.payload,
            updated_at = excluded.updated_at
        """,
        (str(chat_id), json.dumps(payload, ensure_ascii=False), stamp),
    )
    db.commit()
