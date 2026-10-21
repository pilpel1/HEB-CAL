"""טבלאות התזכורות והאנשים. נקרא מ-init_db — יוצר רק מה שחסר."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from app.database import get_db

_CHAT_ID = re.compile(r"^-?\d{1,20}$")

_REMINDER_COLUMNS = (
    ("event_id", "INTEGER"),
    ("offset_minutes", "INTEGER NOT NULL DEFAULT 0"),
    ("recipient_ids", "TEXT NOT NULL DEFAULT '[]'"),
    ("sent_at", "TEXT"),
)

_PEOPLE_COLUMNS = (
    ("name", "TEXT NOT NULL DEFAULT ''"),
    ("telegram_chat_id", "TEXT"),
)


def ensure_reminder_schema(db) -> None:
    """יוצר את הטבלאות אם חסרות, ומוסיף עמודות חסרות בלי למחוק שורות."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_chat_id TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            offset_minutes INTEGER NOT NULL,
            recipient_ids TEXT NOT NULL DEFAULT '[]',
            sent_at TEXT,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        )
        """
    )
    _add_missing_columns(db, "reminder_people", _PEOPLE_COLUMNS)
    _add_missing_columns(db, "reminders", _REMINDER_COLUMNS)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_event ON reminders(event_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_unsent ON reminders(sent_at)"
    )


def _add_missing_columns(db, table: str, columns) -> None:
    existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns:
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _clean_chat_id(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _CHAT_ID.fullmatch(text):
        raise ValueError("מזהה צ'אט חייב להיות מספר (אפשר עם מינוס לקבוצה)")
    return text


def _clean_name(value) -> str:
    name = (value or "").strip()
    if not name:
        raise ValueError("חסר שם")
    if len(name) > 80:
        raise ValueError("השם ארוך מדי")
    return name


def person_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "telegram_chat_id": row["telegram_chat_id"],
    }


def reminder_to_dict(row) -> dict:
    raw = row["recipient_ids"] if "recipient_ids" in row.keys() else "[]"
    try:
        recipient_ids = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        recipient_ids = []
    if not isinstance(recipient_ids, list):
        recipient_ids = []
    clean_ids = []
    for item in recipient_ids:
        try:
            clean_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return {
        "id": row["id"],
        "event_id": row["event_id"],
        "offset_minutes": row["offset_minutes"],
        "recipient_ids": clean_ids,
        "sent_at": row["sent_at"],
    }


def list_people() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT id, name, telegram_chat_id FROM reminder_people ORDER BY name, id"
    ).fetchall()
    return [person_to_dict(row) for row in rows]


def get_person(person_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        "SELECT id, name, telegram_chat_id FROM reminder_people WHERE id = ?",
        (person_id,),
    ).fetchone()
    return person_to_dict(row) if row else None


def people_ids() -> set[int]:
    return {person["id"] for person in list_people()}


def create_person(name, telegram_chat_id=None, *, person_id=None) -> dict:
    db = get_db()
    clean_name = _clean_name(name)
    chat_id = _clean_chat_id(telegram_chat_id)
    if person_id is None:
        cursor = db.execute(
            "INSERT INTO reminder_people (name, telegram_chat_id) VALUES (?, ?)",
            (clean_name, chat_id),
        )
    else:
        cursor = db.execute(
            "INSERT INTO reminder_people (id, name, telegram_chat_id) VALUES (?, ?, ?)",
            (int(person_id), clean_name, chat_id),
        )
    db.commit()
    return get_person(cursor.lastrowid)


def update_person(person_id: int, name, telegram_chat_id=None) -> dict | None:
    if get_person(person_id) is None:
        return None
    db = get_db()
    db.execute(
        "UPDATE reminder_people SET name = ?, telegram_chat_id = ? WHERE id = ?",
        (_clean_name(name), _clean_chat_id(telegram_chat_id), person_id),
    )
    db.commit()
    return get_person(person_id)


def delete_person(person_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM reminder_people WHERE id = ?", (person_id,))
    db.commit()
    return cursor.rowcount > 0


def reminders_for_events(event_ids: list[int] | None = None) -> dict[int, list[dict]]:
    db = get_db()
    if event_ids is not None and not event_ids:
        return {}
    if event_ids is None:
        rows = db.execute(
            """
            SELECT id, event_id, offset_minutes, recipient_ids, sent_at
            FROM reminders
            ORDER BY offset_minutes, id
            """
        ).fetchall()
    else:
        marks = ",".join("?" for _ in event_ids)
        rows = db.execute(
            f"""
            SELECT id, event_id, offset_minutes, recipient_ids, sent_at
            FROM reminders
            WHERE event_id IN ({marks})
            ORDER BY offset_minutes, id
            """,
            tuple(event_ids),
        ).fetchall()
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["event_id"], []).append(reminder_to_dict(row))
    return grouped


def attach_reminders(events: list[dict]) -> list[dict]:
    grouped = reminders_for_events([event["id"] for event in events if event.get("id") is not None])
    for event in events:
        event["reminders"] = grouped.get(event.get("id"), [])
    return events


def replace_event_reminders(event_id: int, reminders: list[dict], *, commit: bool = True) -> None:
    """מחליף את תזכורות האירוע.

    אותו offset שומר ``sent_at`` כל עוד רשימת הנמענים לא השתנתה, כדי שעריכת
    כותרת לא תשלח שוב. שינוי נמענים מאפס את sent_at.
    ``sent_at`` בפריט (ייבוא) נשמר רק בשורה חדשה.
    """
    db = get_db()
    existing = db.execute(
        "SELECT id, offset_minutes, recipient_ids, sent_at FROM reminders WHERE event_id = ?",
        (event_id,),
    ).fetchall()
    by_offset: dict[int, list] = {}
    for row in existing:
        by_offset.setdefault(row["offset_minutes"], []).append(row)

    seen: set[int] = set()
    for item in reminders:
        offset = int(item["offset_minutes"])
        ids_json = json.dumps(list(item.get("recipient_ids") or []))
        seen.add(offset)
        rows = by_offset.get(offset) or []
        if rows:
            primary = rows[0]
            if (primary["recipient_ids"] or "[]") != ids_json:
                db.execute(
                    "UPDATE reminders SET recipient_ids = ?, sent_at = NULL WHERE id = ?",
                    (ids_json, primary["id"]),
                )
            for extra in rows[1:]:
                db.execute("DELETE FROM reminders WHERE id = ?", (extra["id"],))
        else:
            db.execute(
                """
                INSERT INTO reminders (event_id, offset_minutes, recipient_ids, sent_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, offset, ids_json, item.get("sent_at")),
            )

    for offset, rows in by_offset.items():
        if offset not in seen:
            for row in rows:
                db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))

    if commit:
        db.commit()


def delete_reminders_for_event(event_id: int, *, commit: bool = True) -> None:
    db = get_db()
    db.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
    if commit:
        db.commit()


def mark_reminder_sent(reminder_id: int, sent_at: datetime | None = None) -> None:
    db = get_db()
    stamp = sent_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    text = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "UPDATE reminders SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
        (text, reminder_id),
    )
    db.commit()


def load_reminder_rows() -> list[dict]:
    """שורות גולמיות לחישוב due — אירוע + תזכורת, בלי סינון זמן."""
    db = get_db()
    rows = db.execute(
        """
        SELECT
            r.id AS id,
            r.event_id AS event_id,
            r.offset_minutes AS offset_minutes,
            r.recipient_ids AS recipient_ids,
            r.sent_at AS sent_at,
            e.title AS title,
            e.gregorian_date AS gregorian_date,
            e.hebrew_date AS hebrew_date,
            e.time AS time,
            e.description AS description,
            e.end_date AS end_date
        FROM reminders r
        JOIN events e ON e.id = r.event_id
        ORDER BY r.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def upsert_person_for_import(person: dict, *, replace_ids: bool) -> None:
    """ייבוא אדם. בייבוא replace מזהים נשמרים כדי ש-recipient_ids ימשיכו להתאים."""
    if not isinstance(person, dict):
        raise ValueError("Each reminder person must be an object")
    name = _clean_name(person.get("name"))
    chat_id = _clean_chat_id(person.get("telegram_chat_id"))
    raw_id = person.get("id")
    person_id = None
    if raw_id is not None and raw_id != "":
        try:
            person_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("reminder person id must be an integer") from exc

    db = get_db()
    if person_id is not None:
        existing = db.execute(
            "SELECT id FROM reminder_people WHERE id = ?",
            (person_id,),
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE reminder_people SET name = ?, telegram_chat_id = ? WHERE id = ?",
                (name, chat_id, person_id),
            )
            return
        db.execute(
            "INSERT INTO reminder_people (id, name, telegram_chat_id) VALUES (?, ?, ?)",
            (person_id, name, chat_id),
        )
        return

    if replace_ids:
        db.execute(
            "INSERT INTO reminder_people (name, telegram_chat_id) VALUES (?, ?)",
            (name, chat_id),
        )
        return

    by_name = db.execute(
        "SELECT id FROM reminder_people WHERE name = ? ORDER BY id LIMIT 1",
        (name,),
    ).fetchone()
    if by_name:
        db.execute(
            "UPDATE reminder_people SET telegram_chat_id = ? WHERE id = ?",
            (chat_id, by_name["id"]),
        )
        return
    db.execute(
        "INSERT INTO reminder_people (name, telegram_chat_id) VALUES (?, ?)",
        (name, chat_id),
    )


def delete_all_people() -> None:
    get_db().execute("DELETE FROM reminder_people")


def delete_all_reminders() -> None:
    get_db().execute("DELETE FROM reminders")
