"""צבעי אירועים: ולידציית HEX, רקע בהיר, ו-CRUD על event_colors."""
from __future__ import annotations

import sqlite3

from app.database import get_db

DEFAULT_COLOR_CODES = frozenset({"cyan", "yellow", "orange", "green"})


class ColorError(ValueError):
    """שגיאת קלט או כלל עסקי — הופכת ל-400 ב-API."""


def is_default_color_code(code) -> bool:
    return str(code or "").strip().lower() in DEFAULT_COLOR_CODES


def parse_hex_rgb(value) -> tuple[int, int, int]:
    raw = str(value or "").strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 3 and all(char in "0123456789abcdefABCDEF" for char in raw):
        return tuple(int(char * 2, 16) for char in raw)
    if len(raw) == 6 and all(char in "0123456789abcdefABCDEF" for char in raw):
        return (
            int(raw[0:2], 16),
            int(raw[2:4], 16),
            int(raw[4:6], 16),
        )
    raise ColorError("קוד צבע לא תקין. צריך HEX כמו #ff8800")


def normalize_hex(value) -> str:
    red, green, blue = parse_hex_rgb(value)
    return f"#{red:02x}{green:02x}{blue:02x}"


def light_background_from_hex(value) -> str:
    """רקע שקוף של הצבע — לא `rgba(#rrggbb, 0.2)`."""
    red, green, blue = parse_hex_rgb(value)
    return f"rgba({red}, {green}, {blue}, 0.2)"


def clean_color_name(name) -> str:
    text = str(name or "").strip()
    if not text:
        raise ColorError("חסר שם")
    if len(text) > 40:
        raise ColorError("שם הצבע ארוך מדי")
    return text


def serialize_color(row) -> dict:
    data = dict(row)
    data["is_default"] = is_default_color_code(data.get("color_code"))
    return data


def list_colors() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM event_colors ORDER BY id").fetchall()
    return [serialize_color(row) for row in rows]


def get_color(color_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM event_colors WHERE id = ?", (color_id,)).fetchone()
    return serialize_color(row) if row else None


def canonical_color_code(value) -> str | None:
    """קוד צבע כפי שהוא בפלטה, או None אם הוא לא שם.

    ברירות המחדל (cyan וכו׳) וצבע מותאם (#ffcc88) עוברים באותה בדיקה.
    """
    text = str(value or "").strip()
    if not text:
        return None
    row = get_db().execute(
        "SELECT color_code FROM event_colors WHERE lower(color_code) = lower(?)",
        (text,),
    ).fetchone()
    if row is None:
        return None
    return row["color_code"]


def _color_in_use(db, color_code: str) -> bool:
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    checks = []
    if "events" in tables:
        checks.append(("SELECT COUNT(*) FROM events WHERE color = ?", (color_code,)))
    if "event_exceptions" in tables:
        checks.append(
            ("SELECT COUNT(*) FROM event_exceptions WHERE color = ?", (color_code,))
        )
    if "reminder_people" in tables:
        checks.append(
            ("SELECT COUNT(*) FROM reminder_people WHERE color = ?", (color_code,))
        )
    for sql, params in checks:
        if db.execute(sql, params).fetchone()[0]:
            return True
    return False


def _retarget_color_code(db, old_code: str, new_code: str) -> None:
    if old_code == new_code:
        return
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "events" in tables:
        db.execute("UPDATE events SET color = ? WHERE color = ?", (new_code, old_code))
    if "event_exceptions" in tables:
        db.execute(
            "UPDATE event_exceptions SET color = ? WHERE color = ?",
            (new_code, old_code),
        )
    if "reminder_people" in tables:
        db.execute(
            "UPDATE reminder_people SET color = ? WHERE color = ?",
            (new_code, old_code),
        )


def _require_unique(db, name: str, color_code: str, exclude_id: int | None = None) -> None:
    name_row = db.execute(
        "SELECT id FROM event_colors WHERE name = ? AND (? IS NULL OR id != ?)",
        (name, exclude_id, exclude_id),
    ).fetchone()
    if name_row:
        raise ColorError("כבר יש צבע בשם הזה")
    code_row = db.execute(
        "SELECT id FROM event_colors WHERE lower(color_code) = lower(?) AND (? IS NULL OR id != ?)",
        (color_code, exclude_id, exclude_id),
    ).fetchone()
    if code_row:
        raise ColorError("כבר יש צבע עם הקוד הזה")


def create_color(name, color_code) -> dict:
    cleaned_name = clean_color_name(name)
    hex_code = normalize_hex(color_code)
    background = light_background_from_hex(hex_code)
    db = get_db()
    _require_unique(db, cleaned_name, hex_code)
    try:
        cursor = db.execute(
            """
            INSERT INTO event_colors (name, color_code, background_color)
            VALUES (?, ?, ?)
            """,
            (cleaned_name, hex_code, background),
        )
        db.commit()
    except sqlite3.Error as exc:
        raise ColorError("אי אפשר להוסיף את הצבע") from exc
    created = get_color(cursor.lastrowid)
    if created is None:
        raise ColorError("אי אפשר להוסיף את הצבע")
    return created


def update_color(color_id: int, name, color_code) -> dict:
    existing = get_color(color_id)
    if existing is None:
        raise ColorError("הצבע לא נמצא")
    cleaned_name = clean_color_name(name)
    db = get_db()
    if existing["is_default"]:
        if color_code not in (None, "", existing["color_code"]):
            hex_attempt = str(color_code).strip()
            if hex_attempt.lower() != str(existing["color_code"]).lower():
                raise ColorError("אי אפשר לשנות צבע ברירת מחדל")
        color_code_value = existing["color_code"]
        background = existing["background_color"]
    else:
        color_code_value = normalize_hex(color_code if color_code not in (None, "") else existing["color_code"])
        background = light_background_from_hex(color_code_value)
    _require_unique(db, cleaned_name, color_code_value, exclude_id=color_id)
    try:
        db.execute(
            """
            UPDATE event_colors
            SET name = ?, color_code = ?, background_color = ?
            WHERE id = ?
            """,
            (cleaned_name, color_code_value, background, color_id),
        )
        _retarget_color_code(db, existing["color_code"], color_code_value)
        db.commit()
    except sqlite3.Error as exc:
        raise ColorError("אי אפשר לעדכן את הצבע") from exc
    updated = get_color(color_id)
    if updated is None:
        raise ColorError("הצבע לא נמצא")
    return updated


def delete_color(color_id: int) -> None:
    existing = get_color(color_id)
    if existing is None:
        raise ColorError("הצבע לא נמצא")
    if existing["is_default"]:
        raise ColorError("אי אפשר למחוק צבע ברירת מחדל")
    db = get_db()
    if _color_in_use(db, existing["color_code"]):
        raise ColorError("הצבע בשימוש, אי אפשר למחוק")
    db.execute("DELETE FROM event_colors WHERE id = ?", (color_id,))
    db.commit()
