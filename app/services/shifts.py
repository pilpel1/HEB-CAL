"""הזנת משמרות לבית אחד.

האפליקציה היא עותק אחד לבית (לא ריבוי דיירים). המתג ``household_settings``
מדליק או מכבה את הפיצ'ר בכל בסיס הנתונים.

אנשים הם ``reminder_people``. צבע ומשמרות מותרות (בוקר/ערב/לילה, בלי שעות,
אפשר לפי יום בשבוע) יושבים על אותה שורה.

שמירה מהרשת יוצרת אירועי יום שלם עם ``is_shift``. הכותרת היא רק סוג
המשמרת (``בוקר``), והצבע הוא צבע האדם. הרשת מוצאת אותם לפי האדם, התאריך
והתווית. תא חדש מהרשת שלא מותר לאדם נדחה. חריג ידני נשמר מטופס האירוע
הרגיל, גם ביום שלא ברשימה.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from app.services.recurrence import hebrew_display

SHIFT_LABELS = ("בוקר", "ערב", "לילה")
SHIFT_LABEL_MAX = 80
PERSON_COLORS = ("cyan", "yellow", "orange", "green")

# יום ראשון = 0 ... שבת = 6. תואם ל-JS Date.getDay ולכותרת הלוח.
WEEKDAY_NAMES = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת")
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


def shift_title(_name: str, label: str) -> str:
    """הכותרת בלוח היא רק סוג המשמרת. האדם מזוהה לפי הצבע."""
    return label


def hebrew_day_parts(day: date) -> tuple[str, str]:
    """יום וחודש עבריים, בלי שנה. 27 בתשרי → (כ״ז, תשרי)."""
    from hebrew_numbers import int_to_gematria
    from pyluach.dates import GregorianDate

    from app.services.recurrence import HEBREW_MONTHS

    heb = GregorianDate(day.year, day.month, day.day).to_heb()
    day_label = int_to_gematria(int(heb.day), gershayim=True)
    month = HEBREW_MONTHS.get(heb.month, "")
    return day_label, month


def hebrew_day_month(day: date) -> str:
    day_label, month = hebrew_day_parts(day)
    return f"{day_label} {month}".strip()


def week_parasha(saturday: date) -> str | None:
    """פרשת השבת של אותו שבוע (השבת היא היום האחרון, ראשון+6)."""
    from pyluach.dates import GregorianDate

    from app.services.jewish_calendar import get_parasha_hebrew

    name = get_parasha_hebrew(GregorianDate(saturday.year, saturday.month, saturday.day))
    if not name:
        return None
    return str(name)


def week_heading(start: date) -> dict:
    end = start + timedelta(days=6)
    hebrew_range = f"{hebrew_day_month(start)} – {hebrew_day_month(end)}"
    parasha = week_parasha(end)
    title = f"{hebrew_range} · פרשת {parasha}" if parasha else hebrew_range
    return {
        "hebrew_range": hebrew_range,
        "parasha": parasha,
        "week_title": title,
    }


def _allowed_day_set(allowed: dict, label: str) -> set[int]:
    days = allowed.get(label, []) if isinstance(allowed, dict) else []
    result: set[int] = set()
    for day in days or []:
        try:
            number = int(day)
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 6:
            result.add(number)
    return result


def _rules_for(person: dict) -> dict:
    allowed = person.get("shift_allowed")
    if not isinstance(allowed, dict):
        allowed = parse_shift_allowed(allowed)
    return allowed


def resolve_manual_shift(data: dict):
    """משמרת מטופס אירוע בודד.

    ``None`` אם הבקשה לא נוגעת במשמרת (עריכה רגילה משאירה את הדגל).
    אין כאן בדיקה של ``shift_allowed``: חריג ידני מותר בכל יום ובכל משמרת.
    הרשת המרוכזת היא המקום היחיד שדוחה תא אסור.
    """
    keys = ("is_shift", "shift_person_id", "shift_label")
    if not any(key in data for key in keys):
        return None
    if not _truthy_flag(data.get("is_shift")):
        return {"is_shift": 0, "shift_person_id": None, "shift_label": None}

    label = clean_shift_label(data.get("shift_label"))
    try:
        person_id = int(data.get("shift_person_id"))
    except (TypeError, ValueError) as exc:
        raise ShiftError("בחרו למי המשמרת") from exc

    from app.reminders.repository import get_person

    person = get_person(person_id)
    if person is None:
        raise ShiftError("האדם לא נמצא")
    if not person.get("works_shifts"):
        raise ShiftError("האדם לא ברשימת המשמרות")
    return {
        "is_shift": 1,
        "shift_person_id": person_id,
        "shift_label": label,
        "title": shift_title(person.get("name") or "", label),
        "color": person.get("color"),
        "time": None,
        "end_date": None,
    }


def validate_shift_week(person: dict, week_start: date, cells) -> set[tuple[str, str]]:
    """דוחה תא חדש מהרשת שלא מותר לאדם. נקרא מה-API לפני כל כתיבה.

    רק התוויות בוקר/ערב/לילה. טקסט חופשי (יום מחלה) לא עובר כאן.

    משמרת שכבר שמורה באותו תא לא נבדקת כאן: אי אפשר להשאיר אותה מסומנת
    בלי שהשמירה של שאר השבוע תיכשל. יצירה של תא אסור כן נכשלת.
    """
    from app.database import get_db

    end = week_start + timedelta(days=6)
    wanted = _normalize_cells(cells, week_start, end)
    allowed = _rules_for(person)
    existing = {
        (row["gregorian_date"], row["shift_label"])
        for row in _shifts_in_week(get_db(), person["id"], week_start, end)
        if row["shift_label"] in SHIFT_LABELS
    }
    name = (person.get("name") or "").strip() or "האדם"
    for date_str, label in sorted(wanted):
        if (date_str, label) in existing:
            continue
        day = date.fromisoformat(date_str)
        index = weekday_index(day)
        if index not in _allowed_day_set(allowed, label):
            raise ShiftError(
                f"אי אפשר לשמור {label} ב{WEEKDAY_NAMES[index]} — לא מותר ל{name}"
            )
    return wanted


def parse_week_start(value) -> date:
    try:
        day = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise ShiftError("תאריך שבוע לא תקין") from exc
    if weekday_index(day) != 0:
        raise ShiftError("השבוע חייב להתחיל ביום ראשון")
    return day


def default_week_start(today: date | None = None) -> date:
    """השבוע שאחרי השבוע הנוכחי. ראשון עד שבת."""
    today = today or date.today()
    sunday = today - timedelta(days=weekday_index(today))
    return sunday + timedelta(days=7)


def clean_shift_label(value) -> str:
    """תווית חופשית למשמרת ידנית. הרשת עצמה מוגבלת לבוקר/ערב/לילה."""
    label = str(value or "").strip()
    if not label:
        raise ShiftError("כתבו מה המשמרת")
    if len(label) > SHIFT_LABEL_MAX:
        raise ShiftError("התיאור ארוך מדי")
    return label


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
        label = clean_shift_label(raw_label)

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
    """מוסיף עמודות וטבלת מתג. בטוח להרצה חוזרת ולעלייה מקבילית.

    בתוך אותו מנעול, משמרות קיימות מיושרות לכותרת של סוג המשמרת ולצבע האדם.
    אירוע רגיל לא משתנה.
    """
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
            _add_column_if_missing(
                db, "reminder_people", "receives_reminders", "INTEGER NOT NULL DEFAULT 0"
            )
            _add_column_if_missing(
                db, "reminder_people", "works_shifts", "INTEGER NOT NULL DEFAULT 0"
            )

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
        normalize_shift_events(db)


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
    allowed = _rules_for(person)
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
        hebrew_day, hebrew_month = hebrew_day_parts(day)
        days.append({
            "date": key,
            "weekday": offset,
            "hebrew": f"{hebrew_day} {hebrew_month}".strip(),
            "hebrew_day": hebrew_day,
            "hebrew_month": hebrew_month,
            "allowed": [label for label in SHIFT_LABELS if offset in _allowed_day_set(allowed, label)],
            "checked": [label for label in SHIFT_LABELS if label in checked.get(key, [])],
        })
    heading = week_heading(start)
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
        **heading,
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


def _rewrite_shift_row(db, event_id: int, person: dict, label: str) -> None:
    """מיישר כותרת וצבע של משמרת קיימת לאדם, בלי לגעת בשאר השדות."""
    title = shift_title(person.get("name") or "", label)
    if person.get("color"):
        db.execute(
            "UPDATE events SET title = ?, color = ? WHERE id = ? AND is_shift = 1",
            (title, person["color"], event_id),
        )
    else:
        db.execute(
            "UPDATE events SET title = ? WHERE id = ? AND is_shift = 1",
            (title, event_id),
        )


def save_shift_week(person: dict, week_start: date, cells) -> dict:
    """מוסיף תאי רשת ומוחק רק תאים של הרשת שסומנו כבוי.

    לא נוגע באירוע רגיל, ולא במשמרת ידנית עם טקסט חופשי (יום מחלה, יום חופש).
    תא חדש של הרשת חייב להיות מותר לאדם. משמרת רשת שכבר קיימת נשארת גם אם
    הכלל השתנה מאז.
    """
    from app.database import get_db

    wanted = validate_shift_week(person, week_start, cells)
    end = week_start + timedelta(days=6)

    db = get_db()
    existing_rows = _shifts_in_week(db, person["id"], week_start, end)
    by_key: dict[tuple[str, str], list] = {}
    for row in existing_rows:
        if row["shift_label"] not in SHIFT_LABELS:
            continue
        by_key.setdefault((row["gregorian_date"], row["shift_label"]), []).append(row)

    kept: list[int] = []
    deleted: list[int] = []
    created: list[int] = []
    try:
        for key, rows in by_key.items():
            if key in wanted:
                kept.append(rows[0]["id"])
                _rewrite_shift_row(db, rows[0]["id"], person, key[1])
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


def normalize_shift_events(db) -> None:
    """כותרת משמרת קיימת → שם המשמרת, וצבע → צבע האדם.

    נקרא מתוך ensure_shift_schema, בתוך המנעול. אירוע רגיל לא נגע.
    בלי עמודת color על האירוע או על האדם מדלגים על הצבע ומשאירים את השאר.
    """
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "events" not in tables:
        return
    columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
    if "is_shift" not in columns or "shift_label" not in columns or "title" not in columns:
        return
    db.execute(
        """
        UPDATE events
        SET title = shift_label
        WHERE is_shift = 1
          AND shift_label IS NOT NULL
          AND shift_label != ''
          AND title IS NOT shift_label
        """
    )
    if (
        "color" in columns
        and "shift_person_id" in columns
        and "reminder_people" in tables
    ):
        people_columns = {row[1] for row in db.execute("PRAGMA table_info(reminder_people)")}
        if "color" not in people_columns:
            return
        db.execute(
            """
            UPDATE events
            SET color = (
                SELECT reminder_people.color
                FROM reminder_people
                WHERE reminder_people.id = events.shift_person_id
            )
            WHERE is_shift = 1
              AND shift_person_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM reminder_people
                  WHERE reminder_people.id = events.shift_person_id
                    AND reminder_people.color IS NOT NULL
                    AND reminder_people.color != ''
              )
            """
        )


def annotate_shift_events(events: list[dict]) -> list[dict]:
    """בתצוגה, צ'יפ משמרת בצבע האדם ובכותרת של התווית.

    גם טקסט חופשי (``יום מחלה``), וגם שורה ישנה ``אביחי — בוקר``.
    """
    if not events or not any(event.get("is_shift") for event in events):
        return events
    from app.reminders.repository import list_people

    people = {person["id"]: person for person in list_people()}
    for event in events:
        if not event.get("is_shift"):
            continue
        label = str(event.get("shift_label") or "").strip()
        if label:
            event["title"] = label
        person = people.get(event.get("shift_person_id"))
        if person and person.get("color"):
            event["color"] = person["color"]
    return events
