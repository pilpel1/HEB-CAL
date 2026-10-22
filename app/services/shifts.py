"""הזנת משמרות לבית אחד.

האפליקציה היא עותק אחד לבית (לא ריבוי דיירים). המתג ``household_settings``
מדליק או מכבה את הפיצ'ר בכל בסיס הנתונים.

אנשים הם ``reminder_people``. צבע ומשמרות מותרות (בוקר/ערב/לילה, בלי שעות,
אפשר לפי יום בשבוע) יושבים על אותה שורה.

שמירה יוצרת אירועי יום שלם רגילים עם ``is_shift``. הרשת מוצאת אותם לפי
האדם, התאריך והתווית — לא לפי הכותרת — כדי שעריכה של הכותרת לא תשבור
טעינה מחדש. כיבוי תא מוחק רק אירועים שסומנו כמשמרת.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from app.services.recurrence import hebrew_display

SHIFT_LABELS = ("בוקר", "ערב", "לילה")
PERSON_COLORS = ("cyan", "yellow", "orange", "green")

# יום ראשון = 0 ... שבת = 6. תואם ל-JS Date.getDay ולכותרת הלוח.
WEEKDAY_INDEX = {
    6: 0,  # Sunday (datetime.weekday)
    0: 1,
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
}


class ShiftError(ValueError):
    """קלט משמרות לא חוקי."""


def weekday_index(day: date) -> int:
    """0 = ראשון ... 6 = שבת."""
    return WEEKDAY_INDEX[day.weekday()]


def default_shift_allowed() -> dict:
    return {label: list(range(7)) for label in SHIFT_LABELS}


def parse_shift_allowed(raw) -> dict:
    """NULL או טקסט שבור = כל המשמרות, כל הימים.

    אובייקט שמור (גם ריק) נשמר כמו שהוא: תווית חסרה = לא מותרת.
    """
    if raw is None or raw == "":
        return default_shift_allowed()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return default_shift_allowed()
    if not isinstance(raw, dict):
        return default_shift_allowed()
    cleaned = {}
    for label in SHIFT_LABELS:
        days = raw.get(label, [])
        if not isinstance(days, list):
            days = []
        norm = []
        for day in days:
            try:
                number = int(day)
            except (TypeError, ValueError):
                continue
            if 0 <= number <= 6 and number not in norm:
                norm.append(number)
        cleaned[label] = norm
    return cleaned


def dump_shift_allowed(value) -> str | None:
    """מאמת ושומר JSON. ``None`` = ברירת המחדל (כל הימים), נשמר כ-NULL."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ShiftError("המשמרות המותרות צריכות להיות אובייקט")
    cleaned = {}
    for label in SHIFT_LABELS:
        days = value.get(label, [])
        if days is None:
            days = []
        if not isinstance(days, list):
            raise ShiftError("ימי המשמרת צריכים להיות רשימה")
        norm = []
        for day in days:
            if isinstance(day, bool):
                raise ShiftError("יום בשבוע לא תקין")
            try:
                number = int(day)
            except (TypeError, ValueError) as exc:
                raise ShiftError("יום בשבוע לא תקין") from exc
            if number < 0 or number > 6:
                raise ShiftError("יום בשבוע לא תקין")
            if number not in norm:
                norm.append(number)
        cleaned[label] = norm
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))


def clean_person_color(value) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text not in PERSON_COLORS:
        raise ShiftError("צבע לא מוכר")
    return text


def shift_title(name: str, label: str) -> str:
    return f"{name} — {label}"


def parse_week_start(value) -> date:
    try:
        day = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise ShiftError("תאריך שבוע לא תקין") from exc
    if weekday_index(day) != 0:
        raise ShiftError("השבוע חייב להתחיל ביום ראשון")
    return day


def default_week_start(today: date | None = None) -> date:
    """השבוע הנוכחי (ראשון–חמישי). בשישי ובשבת — השבוע הבא."""
    today = today or date.today()
    offset = weekday_index(today)
    sunday = today - timedelta(days=offset)
    if offset >= 5:
        return sunday + timedelta(days=7)
    return sunday


def _truthy_flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def shift_columns_from_payload(event: dict, *, missing: str):
    """עמודות משמרת לייבוא.

    ``missing='keep'`` כשהמפתחות לא בקובץ (לא דורסים שורה קיימת).
    ``missing='defaults'`` בהכנסה חדשה: לא משמרת.
    """
    keys = ("is_shift", "shift_person_id", "shift_label")
    if not any(key in event for key in keys):
        if missing == "keep":
            return "keep"
        return (0, None, None)

    is_shift = 1 if _truthy_flag(event.get("is_shift")) else 0
    raw_label = event.get("shift_label")
    label = None
    if raw_label is not None and str(raw_label).strip() != "":
        label = str(raw_label).strip()
        if label not in SHIFT_LABELS:
            raise ShiftError("תווית משמרת לא מוכרת")

    raw_person = event.get("shift_person_id")
    person_id = None
    if raw_person not in (None, ""):
        try:
            person_id = int(raw_person)
        except (TypeError, ValueError) as exc:
            raise ShiftError("מזהה אדם במשמרת חייב להיות מספר") from exc

    if not is_shift:
        return (0, None, None)
    if label is None:
        raise ShiftError("למשמרת חסרה תווית")
    return (1, person_id, label)


def ensure_shift_schema(db) -> None:
    """מוסיף עמודות וטבלת מתג. בטוח להרצה חוזרת ולעלייה מקבילית; לא משנה שורות."""
    from app.database import (
        _add_column_if_missing,
        _schema_execute,
        exclusive_schema_transaction,
    )

    with exclusive_schema_transaction(db):
        # שמות הטבלאות נקראים מחדש בתוך המנעול, לא לפניו.
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "events" in tables:
            _add_column_if_missing(db, "events", "is_shift", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(db, "events", "shift_person_id", "INTEGER")
            _add_column_if_missing(db, "events", "shift_label", "TEXT")
            _schema_execute(
                db,
                """
                CREATE INDEX IF NOT EXISTS idx_events_shift
                ON events(shift_person_id, gregorian_date)
                WHERE is_shift = 1
                """,
            )
        if "reminder_people" in tables:
            _add_column_if_missing(db, "reminder_people", "color", "TEXT")
            _add_column_if_missing(db, "reminder_people", "shift_allowed", "TEXT")

        _schema_execute(
            db,
            """
            CREATE TABLE IF NOT EXISTS household_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                shifts_enabled INTEGER NOT NULL DEFAULT 0
            )
            """,
        )
        db.execute(
            "INSERT OR IGNORE INTO household_settings (id, shifts_enabled) VALUES (1, 0)"
        )


def shifts_enabled() -> bool:
    from app.database import get_db

    row = get_db().execute(
        "SELECT shifts_enabled FROM household_settings WHERE id = 1"
    ).fetchone()
    if row is None:
        return False
    return bool(row["shifts_enabled"])


def set_shifts_enabled(enabled: bool) -> bool:
    from app.database import get_db

    db = get_db()
    db.execute(
        """
        INSERT INTO household_settings (id, shifts_enabled) VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET shifts_enabled = excluded.shifts_enabled
        """,
        (1 if enabled else 0,),
    )
    db.commit()
    return shifts_enabled()


def _normalize_cells(cells, start: date, end: date) -> set[tuple[str, str]]:
    if not isinstance(cells, list):
        raise ShiftError("cells חייב להיות מערך")
    wanted: set[tuple[str, str]] = set()
    for item in cells:
        if not isinstance(item, dict):
            raise ShiftError("כל תא חייב להיות אובייקט")
        raw_date = item.get("date") or item.get("gregorian_date")
        label = item.get("label") if item.get("label") is not None else item.get("shift_label")
        try:
            day = date.fromisoformat(str(raw_date)[:10])
        except (TypeError, ValueError) as exc:
            raise ShiftError("תאריך תא לא תקין") from exc
        if day < start or day > end:
            raise ShiftError("תאריך מחוץ לשבוע שנבחר")
        if label not in SHIFT_LABELS:
            raise ShiftError("תווית משמרת לא מוכרת")
        wanted.add((day.isoformat(), label))
    return wanted


def _shifts_in_week(db, person_id: int, start: date, end: date):
    return db.execute(
        """
        SELECT id, gregorian_date, shift_label
        FROM events
        WHERE is_shift = 1
          AND shift_person_id = ?
          AND gregorian_date >= ?
          AND gregorian_date <= ?
        ORDER BY gregorian_date, id
        """,
        (person_id, start.isoformat(), end.isoformat()),
    ).fetchall()


def week_view(person: dict, start: date) -> dict:
    from app.database import get_db

    end = start + timedelta(days=6)
    allowed = person.get("shift_allowed")
    if not isinstance(allowed, dict):
        allowed = parse_shift_allowed(allowed)
    checked: dict[str, list[str]] = {}
    for row in _shifts_in_week(get_db(), person["id"], start, end):
        label = row["shift_label"]
        if label not in SHIFT_LABELS:
            continue
        checked.setdefault(row["gregorian_date"], []).append(label)
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        days.append({
            "date": key,
            "weekday": offset,
            "allowed": [label for label in SHIFT_LABELS if offset in allowed.get(label, [])],
            "checked": [label for label in SHIFT_LABELS if label in checked.get(key, [])],
        })
    return {
        "enabled": shifts_enabled(),
        "person": {
            "id": person["id"],
            "name": person["name"],
            "color": person.get("color"),
        },
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "labels": list(SHIFT_LABELS),
        "days": days,
    }


def _delete_shift_row(db, event_id: int) -> None:
    db.execute(
        """
        DELETE FROM reminder_sends
        WHERE reminder_id IN (SELECT id FROM reminders WHERE event_id = ?)
        """,
        (event_id,),
    )
    db.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
    db.execute("DELETE FROM event_exceptions WHERE event_id = ?", (event_id,))
    db.execute(
        "DELETE FROM events WHERE id = ? AND is_shift = 1",
        (event_id,),
    )


def save_shift_week(person: dict, week_start: date, cells) -> dict:
    """מוסיף תאים חדשים ומוחק משמרות שסומנו כבוי. לא נוגע באירוע רגיל.

    תא חדש חייב להיות מותר לאדם. משמרת שכבר קיימת נשארת גם אם הכלל השתנה
    מאז (אחרת אי אפשר היה לשמור שבוע בלי למחוק משהו שהמשתמש לא יכול לכבות).
    """
    from app.database import get_db

    end = week_start + timedelta(days=6)
    wanted = _normalize_cells(cells, week_start, end)
    allowed = person.get("shift_allowed")
    if not isinstance(allowed, dict):
        allowed = parse_shift_allowed(allowed)

    db = get_db()
    existing_rows = _shifts_in_week(db, person["id"], week_start, end)
    by_key: dict[tuple[str, str], list] = {}
    for row in existing_rows:
        if row["shift_label"] not in SHIFT_LABELS:
            continue
        by_key.setdefault((row["gregorian_date"], row["shift_label"]), []).append(row)

    for date_str, label in wanted:
        if (date_str, label) in by_key:
            continue
        day = date.fromisoformat(date_str)
        if weekday_index(day) not in allowed.get(label, []):
            raise ShiftError(f"המשמרת {label} לא מותרת ביום הזה")

    kept: list[int] = []
    deleted: list[int] = []
    created: list[int] = []
    try:
        for key, rows in by_key.items():
            if key in wanted:
                kept.append(rows[0]["id"])
                for extra in rows[1:]:
                    _delete_shift_row(db, extra["id"])
                    deleted.append(extra["id"])
            else:
                for row in rows:
                    _delete_shift_row(db, row["id"])
                    deleted.append(row["id"])

        present = set(by_key)
        for date_str, label in sorted(wanted):
            if (date_str, label) in present:
                continue
            day = date.fromisoformat(date_str)
            cursor = db.execute(
                """
                INSERT INTO events (
                    title, gregorian_date, hebrew_date, time, description, end_date, color,
                    recurrence_freq, recurrence_calendar, recurrence_until, recurrence_count,
                    is_shift, shift_person_id, shift_label
                )
                VALUES (?, ?, ?, NULL, '', NULL, ?, NULL, NULL, NULL, NULL, 1, ?, ?)
                """,
                (
                    shift_title(person["name"], label),
                    date_str,
                    hebrew_display(day),
                    person.get("color"),
                    person["id"],
                    label,
                ),
            )
            created.append(cursor.lastrowid)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "success": True,
        "created": created,
        "deleted": deleted,
        "kept": kept,
        "week_start": week_start.isoformat(),
        "person_id": person["id"],
    }
