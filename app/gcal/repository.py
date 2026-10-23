"""מקורות iCal. הכתובת המלאה נשארת בטבלה ולא יוצאת מהמודול הזה."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from app.database import get_db
from app.gcal.errors import GcalUserError
from app.gcal.urls import mask_ical_url, require_google_ical_url

LABEL_MAX = 80
SOURCE_LIMIT = 10
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

READONLY_MESSAGE = "האירוע מגיע מיומן גוגל. לעריכה ביומן גוגל"


def is_gcal_event(event: dict | None) -> bool:
    return bool(event and event.get("gcal_source_id"))


def utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_label(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GcalUserError("שם היומן צריך להיות טקסט")
    text = value.strip()
    if not text:
        return None
    if len(text) > LABEL_MAX:
        raise GcalUserError("שם היומן ארוך מדי")
    return text


def clean_color(value) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _HEX.fullmatch(value.strip()):
        raise GcalUserError("צבע לא תקין")
    return value.strip().lower()


def clean_enabled(value, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise GcalUserError("מצב ההפעלה לא תקין")


def annotate_gcal(events: list[dict]) -> list[dict]:
    for event in events:
        event["gcal_readonly"] = is_gcal_event(event)
    return events


def public_source(row, event_count: int = 0) -> dict:
    """בלי ical_url. רק מסכה קבועה."""
    data = dict(row)
    return {
        "id": data["id"],
        "label": data.get("label") or "",
        "url_masked": mask_ical_url(),
        "color": data.get("color") or "",
        "enabled": bool(data.get("enabled")),
        "last_sync_at": data.get("last_sync_at"),
        "last_error": data.get("last_error") or "",
        "event_count": event_count,
    }


def _counts(db) -> dict[int, int]:
    rows = db.execute(
        """
        SELECT gcal_source_id AS id, COUNT(*) AS n
        FROM events
        WHERE gcal_source_id IS NOT NULL
        GROUP BY gcal_source_id
        """
    ).fetchall()
    return {row["id"]: row["n"] for row in rows}


def list_sources() -> list[dict]:
    db = get_db()
    counts = _counts(db)
    rows = db.execute(
        """
        SELECT id, label, color, enabled, last_sync_at, last_error, created_at, updated_at
        FROM gcal_sources
        ORDER BY id
        """
    ).fetchall()
    return [public_source(row, counts.get(row["id"], 0)) for row in rows]


def get_source_public(source_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        """
        SELECT id, label, color, enabled, last_sync_at, last_error, created_at, updated_at
        FROM gcal_sources WHERE id = ?
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        return None
    count = _counts(db).get(source_id, 0)
    return public_source(row, count)


def get_source_row(source_id: int):
    """שורה פנימית, כולל הכתובת. לא להחזיר אותה מה-API."""
    db = get_db()
    return db.execute("SELECT * FROM gcal_sources WHERE id = ?", (source_id,)).fetchone()


def _url_taken(db, url: str, except_id: int | None = None) -> bool:
    if except_id is None:
        row = db.execute(
            "SELECT 1 FROM gcal_sources WHERE ical_url = ? LIMIT 1",
            (url,),
        ).fetchone()
    else:
        row = db.execute(
            "SELECT 1 FROM gcal_sources WHERE ical_url = ? AND id != ? LIMIT 1",
            (url, except_id),
        ).fetchone()
    return row is not None


def create_source(label, ical_url, color, enabled) -> dict:
    url = require_google_ical_url(ical_url)
    label = clean_label(label)
    color = clean_color(color)
    enabled_flag = 1 if clean_enabled(enabled, default=True) else 0
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS n FROM gcal_sources").fetchone()["n"]
    if count >= SOURCE_LIMIT:
        raise GcalUserError("אפשר לחבר עד 10 יומנים")
    if _url_taken(db, url):
        raise GcalUserError("הכתובת הזו כבר מחוברת")
    stamp = utc_now_stamp()
    try:
        cursor = db.execute(
            """
            INSERT INTO gcal_sources (
                label, ical_url, color, enabled, last_sync_at, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (label, url, color, enabled_flag, stamp, stamp),
        )
        db.commit()
    except sqlite3.Error as exc:
        db.rollback()
        raise GcalUserError("לא הצלחנו לשמור את החיבור") from exc
    saved = get_source_public(cursor.lastrowid)
    if saved is None:
        raise GcalUserError("לא הצלחנו לשמור את החיבור")
    return saved


def update_source(source_id: int, payload: dict) -> dict:
    row = get_source_row(source_id)
    if row is None:
        raise GcalUserError("החיבור לא נמצא")
    label = clean_label(payload["label"]) if "label" in payload else row["label"]
    color = clean_color(payload["color"]) if "color" in payload else row["color"]
    if "enabled" in payload:
        enabled_flag = 1 if clean_enabled(payload["enabled"]) else 0
    else:
        enabled_flag = 1 if row["enabled"] else 0
    url = row["ical_url"]
    incoming = payload.get("ical_url") if "ical_url" in payload else None
    if isinstance(incoming, str) and incoming.strip() and "…" not in incoming and "..." not in incoming:
        url = require_google_ical_url(incoming)
    db = get_db()
    if url != row["ical_url"] and _url_taken(db, url, except_id=source_id):
        raise GcalUserError("הכתובת הזו כבר מחוברת")
    stamp = utc_now_stamp()
    try:
        db.execute(
            """
            UPDATE gcal_sources
            SET label = ?, ical_url = ?, color = ?, enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (label, url, color, enabled_flag, stamp, source_id),
        )
        if color != row["color"]:
            db.execute(
                "UPDATE events SET color = ? WHERE gcal_source_id = ?",
                (color, source_id),
            )
        db.commit()
    except sqlite3.Error as exc:
        db.rollback()
        raise GcalUserError("לא הצלחנו לעדכן את החיבור") from exc
    saved = get_source_public(source_id)
    if saved is None:
        raise GcalUserError("החיבור לא נמצא")
    return saved


def delete_source(source_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT 1 FROM gcal_sources WHERE id = ?", (source_id,)).fetchone()
    if row is None:
        return False
    try:
        db.execute("BEGIN")
        ids = [
            item["id"]
            for item in db.execute(
                "SELECT id FROM events WHERE gcal_source_id = ?",
                (source_id,),
            ).fetchall()
        ]
        _delete_event_ids(db, ids)
        db.execute("DELETE FROM gcal_sources WHERE id = ?", (source_id,))
        db.commit()
    except sqlite3.Error as exc:
        db.rollback()
        raise GcalUserError("לא הצלחנו למחוק את החיבור") from exc
    return True


def _delete_event_ids(db, ids: list[int]) -> None:
    if not ids:
        return
    marks = ",".join("?" for _ in ids)
    params = tuple(ids)
    db.execute(
        f"""
        DELETE FROM reminder_sends
        WHERE reminder_id IN (SELECT id FROM reminders WHERE event_id IN ({marks}))
        """,
        params,
    )
    db.execute(f"DELETE FROM reminders WHERE event_id IN ({marks})", params)
    db.execute(f"DELETE FROM event_exceptions WHERE event_id IN ({marks})", params)
    db.execute(f"DELETE FROM events WHERE id IN ({marks})", params)


def mark_sync_success(source_id: int, stamp: str) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE gcal_sources
        SET last_sync_at = ?, last_error = NULL, updated_at = ?
        WHERE id = ?
        """,
        (stamp, stamp, source_id),
    )
    db.commit()


def mark_sync_error(source_id: int, message: str) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE gcal_sources
        SET last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (message[:300], utc_now_stamp(), source_id),
    )
    db.commit()
