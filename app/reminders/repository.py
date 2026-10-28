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
    ("receives_reminders", "INTEGER NOT NULL DEFAULT 0"),
    ("works_shifts", "INTEGER NOT NULL DEFAULT 0"),
    ("daily_digest_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("daily_digest_last_sent", "TEXT"),
)


def ensure_reminder_schema(db) -> None:
    """יוצר את הטבלאות אם חסרות, ומוסיף עמודות חסרות בלי למחוק שורות.

    רץ בתוך BEGIN IMMEDIATE. עמודה שכבר נוספה על ידי תהליך אחר לא מפילה.
    """
    from app.database import (
        _add_column_if_missing,
        _schema_execute,
        exclusive_schema_transaction,
    )

    with exclusive_schema_transaction(db):
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
        _schema_execute(
            db,
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                offset_minutes INTEGER NOT NULL,
                recipient_ids TEXT NOT NULL DEFAULT '[]',
                sent_at TEXT,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            )
            """,
        )
        for name, decl in _PEOPLE_COLUMNS:
            _add_column_if_missing(db, "reminder_people", name, decl)
        for name, decl in _REMINDER_COLUMNS:
            _add_column_if_missing(db, "reminders", name, decl)
        _schema_execute(
            db,
            "CREATE INDEX IF NOT EXISTS idx_reminders_event ON reminders(event_id)",
        )
        _schema_execute(
            db,
            "CREATE INDEX IF NOT EXISTS idx_reminders_unsent ON reminders(sent_at)",
        )


def _clean_chat_id(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _CHAT_ID.fullmatch(text):
        raise ValueError("מזהה הצ׳אט חייב להיות מספר (עם מינוס לקבוצה)")
    return text


def _clean_name(value) -> str:
    name = (value or "").strip()
    if not name:
        raise ValueError("חסר שם")
    if len(name) > 80:
        raise ValueError("השם ארוך מדי")
    return name


def _row_flag(row, key: str, default: bool = False) -> bool:
    if key not in row.keys():
        return default
    try:
        return bool(int(row[key] or 0))
    except (TypeError, ValueError):
        return default


def person_to_dict(row) -> dict:
    from app.services.shifts import parse_shift_allowed

    keys = row.keys()
    raw_allowed = row["shift_allowed"] if "shift_allowed" in keys else None
    return {
        "id": row["id"],
        "name": row["name"],
        "telegram_chat_id": row["telegram_chat_id"],
        "color": row["color"] if "color" in keys else None,
        "shift_allowed": parse_shift_allowed(raw_allowed),
        "receives_reminders": _row_flag(row, "receives_reminders"),
        "works_shifts": _row_flag(row, "works_shifts"),
        "daily_digest_enabled": _row_flag(row, "daily_digest_enabled"),
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


def list_people(*, role: str | None = None) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM reminder_people ORDER BY name, id"
    ).fetchall()
    people = [person_to_dict(row) for row in rows]
    if role == "reminders":
        return [person for person in people if person.get("receives_reminders")]
    if role == "shifts":
        return [person for person in people if person.get("works_shifts")]
    return people


def get_person(person_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        "SELECT * FROM reminder_people WHERE id = ?",
        (person_id,),
    ).fetchone()
    return person_to_dict(row) if row else None


def people_ids(*, role: str | None = None) -> set[int]:
    return {person["id"] for person in list_people(role=role)}


_MISSING = object()


def _clean_flag(value) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (1, 0):
        return int(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "on"):
            return 1
        if text in ("0", "false", "no", "off", ""):
            return 0
    raise ValueError("הדגל חייב להיות true או false")


def _person_color_and_rules(color, shift_allowed):
    from app.services.shifts import clean_person_color, dump_shift_allowed

    color_value = None if color is _MISSING else clean_person_color(color)
    rules_value = None if shift_allowed is _MISSING else dump_shift_allowed(shift_allowed)
    return color_value, rules_value


def _default_role_flags(color, shift_allowed, receives_reminders, works_shifts) -> tuple[int, int]:
    if receives_reminders is _MISSING:
        receives = 1
    else:
        receives = _clean_flag(receives_reminders)
    if works_shifts is _MISSING:
        has_shift_fields = color is not _MISSING or shift_allowed is not _MISSING
        works = 1 if has_shift_fields else 0
    else:
        works = _clean_flag(works_shifts)
    return receives, works


def backfill_people_role_flags(db) -> None:
    """ממלא דגלי תפקיד לאנשים קיימים. רץ פעם אחת בתוך מיגרציית גרסה 4.

    receives_reminders אם יש מזהה צ׳אט או שהאדם נמען לתזכורת.
    works_shifts אם יש shift_allowed שמור או אירוע משמרת.
    שורה בלי אף סימן נשארת איש תזכורות — כך נוצרה הטבלה במקור.
    """
    tables = {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "reminder_people" not in tables:
        return
    columns = {row[1] for row in db.execute("PRAGMA table_info(reminder_people)")}
    if "receives_reminders" not in columns or "works_shifts" not in columns:
        return
    recipient_ids: set[int] = set()
    if "reminders" in tables:
        for row in db.execute("SELECT recipient_ids FROM reminders"):
            try:
                raw = json.loads(row["recipient_ids"] or "[]")
            except (TypeError, json.JSONDecodeError):
                raw = []
            if not isinstance(raw, list):
                continue
            for item in raw:
                try:
                    recipient_ids.add(int(item))
                except (TypeError, ValueError):
                    continue
    shift_ids: set[int] = set()
    if "events" in tables:
        event_cols = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        if "is_shift" in event_cols and "shift_person_id" in event_cols:
            for row in db.execute(
                """
                SELECT DISTINCT shift_person_id
                FROM events
                WHERE is_shift = 1 AND shift_person_id IS NOT NULL
                """
            ):
                try:
                    shift_ids.add(int(row[0]))
                except (TypeError, ValueError):
                    continue
    people_cols = columns
    for row in db.execute("SELECT * FROM reminder_people"):
        keys = row.keys()
        person_id = row["id"]
        chat = str(row["telegram_chat_id"] or "").strip() if "telegram_chat_id" in keys else ""
        allowed = row["shift_allowed"] if "shift_allowed" in keys else None
        receives = 1 if chat or person_id in recipient_ids else 0
        works = 1 if (allowed not in (None, "") or person_id in shift_ids) else 0
        if receives == 0 and works == 0:
            receives = 1
        assignments = []
        params: list = []
        if "receives_reminders" in people_cols:
            assignments.append("receives_reminders = ?")
            params.append(receives)
        if "works_shifts" in people_cols:
            assignments.append("works_shifts = ?")
            params.append(works)
        params.append(person_id)
        db.execute(
            f"UPDATE reminder_people SET {', '.join(assignments)} WHERE id = ?",
            params,
        )


def create_person(
    name,
    telegram_chat_id=None,
    *,
    person_id=None,
    color=_MISSING,
    shift_allowed=_MISSING,
    receives_reminders=_MISSING,
    works_shifts=_MISSING,
    daily_digest_enabled=_MISSING,
) -> dict:
    db = get_db()
    clean_name = _clean_name(name)
    chat_id = _clean_chat_id(telegram_chat_id)
    color_value, rules_value = _person_color_and_rules(color, shift_allowed)
    receives, works = _default_role_flags(
        color, shift_allowed, receives_reminders, works_shifts
    )
    digest = (
        0
        if daily_digest_enabled is _MISSING
        else _clean_flag(daily_digest_enabled)
    )
    if person_id is None:
        cursor = db.execute(
            """
            INSERT INTO reminder_people (
                name, telegram_chat_id, color, shift_allowed,
                receives_reminders, works_shifts, daily_digest_enabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (clean_name, chat_id, color_value, rules_value, receives, works, digest),
        )
    else:
        cursor = db.execute(
            """
            INSERT INTO reminder_people (
                id, name, telegram_chat_id, color, shift_allowed,
                receives_reminders, works_shifts, daily_digest_enabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(person_id),
                clean_name,
                chat_id,
                color_value,
                rules_value,
                receives,
                works,
                digest,
            ),
        )
    db.commit()
    return get_person(cursor.lastrowid)


def update_person(
    person_id: int,
    name,
    telegram_chat_id=None,
    *,
    color=_MISSING,
    shift_allowed=_MISSING,
    receives_reminders=_MISSING,
    works_shifts=_MISSING,
    daily_digest_enabled=_MISSING,
) -> dict | None:
    if get_person(person_id) is None:
        return None
    db = get_db()
    assignments = ["name = ?", "telegram_chat_id = ?"]
    params: list = [_clean_name(name), _clean_chat_id(telegram_chat_id)]
    if color is not _MISSING or shift_allowed is not _MISSING:
        color_value, rules_value = _person_color_and_rules(color, shift_allowed)
        if color is not _MISSING:
            assignments.append("color = ?")
            params.append(color_value)
        if shift_allowed is not _MISSING:
            assignments.append("shift_allowed = ?")
            params.append(rules_value)
    if receives_reminders is not _MISSING:
        assignments.append("receives_reminders = ?")
        params.append(_clean_flag(receives_reminders))
    if works_shifts is not _MISSING:
        assignments.append("works_shifts = ?")
        params.append(_clean_flag(works_shifts))
    if daily_digest_enabled is not _MISSING:
        assignments.append("daily_digest_enabled = ?")
        params.append(_clean_flag(daily_digest_enabled))
    params.append(person_id)
    db.execute(
        f"UPDATE reminder_people SET {', '.join(assignments)} WHERE id = ?",
        params,
    )
    db.commit()
    return get_person(person_id)


def delete_person(person_id: int) -> bool:
    db = get_db()
    rows = db.execute("SELECT id, recipient_ids FROM reminders").fetchall()
    for row in rows:
        try:
            ids = json.loads(row["recipient_ids"] or "[]")
        except (TypeError, json.JSONDecodeError):
            ids = []
        if not isinstance(ids, list):
            ids = []
        leftover = []
        for item in ids:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue
            if number != person_id and number not in leftover:
                leftover.append(number)
        if leftover != ids:
            db.execute(
                "UPDATE reminders SET recipient_ids = ? WHERE id = ?",
                (json.dumps(leftover), row["id"]),
            )
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
                db.execute("DELETE FROM reminder_sends WHERE reminder_id = ?", (primary["id"],))
            for extra in rows[1:]:
                db.execute("DELETE FROM reminder_sends WHERE reminder_id = ?", (extra["id"],))
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
                db.execute("DELETE FROM reminder_sends WHERE reminder_id = ?", (row["id"],))
                db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))

    if commit:
        db.commit()


def delete_reminders_for_event(event_id: int, *, commit: bool = True) -> None:
    db = get_db()
    db.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
    if commit:
        db.commit()


def ensure_reminder_sends_per_chat(db) -> None:
    """מוסיף chat_id ל-reminder_sends. שורה ישנה מקבלת chat_id ריק (= כל הצ'אטים)."""
    from app.database import _schema_execute, exclusive_schema_transaction

    with exclusive_schema_transaction(db):
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "reminder_sends" not in tables:
            return
        cols = {row[1] for row in db.execute("PRAGMA table_info(reminder_sends)")}
        if "chat_id" in cols:
            return
        _schema_execute(db, "ALTER TABLE reminder_sends RENAME TO reminder_sends_legacy")
        _schema_execute(
            db,
            """
            CREATE TABLE reminder_sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder_id INTEGER NOT NULL,
                occurrence_date TEXT NOT NULL,
                chat_id TEXT NOT NULL DEFAULT '',
                sent_at TEXT,
                UNIQUE (reminder_id, occurrence_date, chat_id),
                FOREIGN KEY (reminder_id) REFERENCES reminders(id) ON DELETE CASCADE
            )
            """,
        )
        db.execute(
            """
            INSERT INTO reminder_sends (reminder_id, occurrence_date, chat_id, sent_at)
            SELECT reminder_id, occurrence_date, '', sent_at FROM reminder_sends_legacy
            """
        )
        _schema_execute(db, "DROP TABLE reminder_sends_legacy")
        _schema_execute(
            db,
            "CREATE INDEX IF NOT EXISTS idx_reminder_sends_reminder ON reminder_sends(reminder_id)",
        )


def mark_reminder_sent(
    reminder_id: int,
    sent_at: datetime | None = None,
    *,
    occurrence_date: str | None = None,
    chat_id: str | None = None,
) -> None:
    """חותמת שליחה.

    ``chat_id`` — רק הצ'אט הזה (כשל חלקי לא שולח שוב לאחרים).
    בלי ``occurrence_date`` ובלי צ'אט — ``sent_at`` על שורת התזכורת (חד-פעמי).
    עם תאריך מופע — שורה ב-``reminder_sends``.
    """
    db = get_db()
    stamp = sent_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    text = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if chat_id or occurrence_date:
        db.execute(
            """
            INSERT INTO reminder_sends (reminder_id, occurrence_date, chat_id, sent_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(reminder_id, occurrence_date, chat_id) DO NOTHING
            """,
            (reminder_id, (occurrence_date or "")[:10], str(chat_id or ""), text),
        )
    if not chat_id and not occurrence_date:
        db.execute(
            "UPDATE reminders SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
            (text, reminder_id),
        )
    db.commit()


def sent_occurrence_keys() -> set[tuple[int, str]]:
    db = get_db()
    rows = db.execute(
        "SELECT reminder_id, occurrence_date FROM reminder_sends"
    ).fetchall()
    return {(row["reminder_id"], row["occurrence_date"]) for row in rows}


def sent_chat_keys() -> set[tuple[int, str, str]]:
    db = get_db()
    rows = db.execute(
        "SELECT reminder_id, occurrence_date, chat_id FROM reminder_sends"
    ).fetchall()
    return {
        (row["reminder_id"], row["occurrence_date"], row["chat_id"] or "")
        for row in rows
    }


def clear_reminder_delivery(event_id: int, *, commit: bool = True) -> None:
    """מאפס חותמות שליחה אחרי שינוי שעה/תאריך, כדי שהתזכורת תישלח מחדש."""
    db = get_db()
    db.execute(
        """
        DELETE FROM reminder_sends
        WHERE reminder_id IN (SELECT id FROM reminders WHERE event_id = ?)
        """,
        (event_id,),
    )
    db.execute("UPDATE reminders SET sent_at = NULL WHERE event_id = ?", (event_id,))
    if commit:
        db.commit()


def clear_reminder_sends(reminder_id: int, *, commit: bool = False) -> None:
    db = get_db()
    db.execute("DELETE FROM reminder_sends WHERE reminder_id = ?", (reminder_id,))
    if commit:
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
            e.end_date AS end_date,
            e.recurrence_freq AS recurrence_freq,
            e.recurrence_calendar AS recurrence_calendar,
            e.recurrence_until AS recurrence_until,
            e.recurrence_count AS recurrence_count
        FROM reminders r
        JOIN events e ON e.id = r.event_id
        ORDER BY r.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _apply_imported_person_extras(db, person_id: int, person: dict) -> None:
    """צבע, כללי משמרת ודגלים רק אם המפתח בקובץ — ייבוא ישן לא מוחק אותם."""
    assignments = []
    params: list = []
    if "color" in person:
        color_value, _ignored = _person_color_and_rules(person.get("color"), _MISSING)
        assignments.append("color = ?")
        params.append(color_value)
    if "shift_allowed" in person:
        _ignored, rules_value = _person_color_and_rules(_MISSING, person.get("shift_allowed"))
        assignments.append("shift_allowed = ?")
        params.append(rules_value)
    has_role_keys = "receives_reminders" in person or "works_shifts" in person
    if has_role_keys:
        if "receives_reminders" in person:
            assignments.append("receives_reminders = ?")
            params.append(_clean_flag(person.get("receives_reminders")))
        if "works_shifts" in person:
            assignments.append("works_shifts = ?")
            params.append(_clean_flag(person.get("works_shifts")))
    else:
        works = 1 if ("color" in person or "shift_allowed" in person) else 0
        assignments.append("receives_reminders = ?")
        params.append(1)
        assignments.append("works_shifts = ?")
        params.append(works)
    if "daily_digest_enabled" in person:
        assignments.append("daily_digest_enabled = ?")
        params.append(_clean_flag(person.get("daily_digest_enabled")))
    if not assignments:
        return
    params.append(person_id)
    db.execute(
        f"UPDATE reminder_people SET {', '.join(assignments)} WHERE id = ?",
        params,
    )


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
    saved_id = None
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
            saved_id = person_id
        else:
            db.execute(
                "INSERT INTO reminder_people (id, name, telegram_chat_id) VALUES (?, ?, ?)",
                (person_id, name, chat_id),
            )
            saved_id = person_id
    elif replace_ids:
        cursor = db.execute(
            "INSERT INTO reminder_people (name, telegram_chat_id) VALUES (?, ?)",
            (name, chat_id),
        )
        saved_id = cursor.lastrowid
    else:
        by_name = db.execute(
            "SELECT id FROM reminder_people WHERE name = ? ORDER BY id LIMIT 1",
            (name,),
        ).fetchone()
        if by_name:
            db.execute(
                "UPDATE reminder_people SET telegram_chat_id = ? WHERE id = ?",
                (chat_id, by_name["id"]),
            )
            saved_id = by_name["id"]
        else:
            cursor = db.execute(
                "INSERT INTO reminder_people (name, telegram_chat_id) VALUES (?, ?)",
                (name, chat_id),
            )
            saved_id = cursor.lastrowid
    if saved_id is not None:
        _apply_imported_person_extras(db, saved_id, person)


def delete_all_people() -> None:
    get_db().execute("DELETE FROM reminder_people")


def delete_all_reminders() -> None:
    get_db().execute("DELETE FROM reminders")
