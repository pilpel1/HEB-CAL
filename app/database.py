import os
import re
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from flask import g

from app.services.hebrew_format import normalize_hebrew_date_text
from app.services.recurrence import clean_recurrence, recurrence_fields


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = Path("data/calendar.db")

# גרסה 1: טבלאות בסיס, תזכורות, חזרות, וסכמת משמרות.
# גרסה 2: יישור כותרת וצבע של משמרות קיימות, בתוך אותו מנעול (אידמפוטנטי).
# גרסה 3: reminder_sends לפי צ'אט (כדי שלא יישלח שוב אחרי כשל חלקי).
# גרסה 4: דגלי receives_reminders / works_shifts על reminder_people, עם backfill.
# בסיס ישן נשאר על 0 עד המעבר הראשון. להעלאת גרסה כשמוסיפים מיגרציה חדשה —
# גוף ה-DDL אידמפוטנטי, אז הרצה חוזרת על בסיס שכבר שודרג בטוחה.
SCHEMA_VERSION = 4
# מילישניות. חייב להיות מוגדר לפני BEGIN IMMEDIATE, אחרת החיבור השני
# נכשל מיד ב-database is locked במקום לחכות שהראשון יסיים.
SCHEMA_BUSY_TIMEOUT_MS = 15000

_schema_lock_depth: ContextVar[int] = ContextVar("hebcal_schema_lock_depth", default=0)
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_database_path():
    configured_path = os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    database_path = Path(configured_path)

    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path

    database_path.parent.mkdir(parents=True, exist_ok=True)
    return database_path


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            str(get_database_path()),
            timeout=SCHEMA_BUSY_TIMEOUT_MS / 1000,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute(f"PRAGMA busy_timeout = {SCHEMA_BUSY_TIMEOUT_MS}")
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def _is_benign_schema_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    return "duplicate column name" in message or "already exists" in message


def _schema_execute(db, sql: str, params: tuple = ()):
    """DDL. 'duplicate column name' ו-'already exists' נחשבים הצלחה."""
    try:
        return db.execute(sql, params)
    except sqlite3.OperationalError as exc:
        if _is_benign_schema_error(exc):
            return None
        raise


def _add_column_if_missing(db, table: str, name: str, decl: str) -> None:
    """בודק את העמודה מחדש עכשיו (בתוך המנעול) ורק אז ALTER."""
    if not _IDENT.fullmatch(table) or not _IDENT.fullmatch(name):
        raise ValueError(f"illegal schema identifier: {table}.{name}")
    existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
    if name in existing:
        return
    _schema_execute(db, f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _read_user_version(db) -> int:
    row = db.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    return int(row[0])


def _write_user_version(db, version: int) -> None:
    db.execute(f"PRAGMA user_version = {int(version)}")


@contextmanager
def exclusive_schema_transaction(db):
    """BEGIN IMMEDIATE אחד לכל מיגרציית הסכמה.

    קריאה מקוננת (ensure_* מתוך apply) לא פותחת טרנזקציה שנייה.
    חיבור שכבר באמצע טרנזקציה של הקורא רץ בתוכה בלי BEGIN נוסף.
    """
    db.execute(f"PRAGMA busy_timeout = {SCHEMA_BUSY_TIMEOUT_MS}")
    if _schema_lock_depth.get() > 0:
        yield
        return

    started = False
    if not db.in_transaction:
        db.execute("BEGIN IMMEDIATE")
        started = True
    token = _schema_lock_depth.set(_schema_lock_depth.get() + 1)
    try:
        yield
        if started:
            db.commit()
    except BaseException:
        if started:
            try:
                db.rollback()
            except sqlite3.Error:
                pass
        raise
    finally:
        _schema_lock_depth.reset(token)


def _ensure_base_schema(db) -> None:
    _schema_execute(
        db,
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            gregorian_date TEXT NOT NULL,
            hebrew_date TEXT NOT NULL,
            time TEXT,
            description TEXT,
            end_date TEXT,
            color TEXT
        )
        """,
    )
    _schema_execute(
        db,
        """
        CREATE TABLE IF NOT EXISTS event_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color_code TEXT NOT NULL,
            background_color TEXT NOT NULL
        )
        """,
    )
    # בדיקה מחדש בתוך המנעול — שני תהליכים לא מכניסים את אותם צבעים פעמיים.
    if db.execute("SELECT 1 FROM event_colors LIMIT 1").fetchone():
        return
    default_colors = [
        ("ציאן", "cyan", "rgba(0, 255, 255, 0.2)"),
        ("צהוב", "yellow", "rgba(255, 255, 0, 0.2)"),
        ("כתום", "orange", "rgba(255, 165, 0, 0.2)"),
        ("ירוק", "green", "rgba(0, 128, 0, 0.2)"),
    ]
    db.executemany(
        """
        INSERT INTO event_colors (name, color_code, background_color)
        VALUES (?, ?, ?)
        """,
        default_colors,
    )


def apply_pending_migrations(db) -> None:
    """כל ה-ensure_* בטרנזקציה בלעדית אחת, ואז PRAGMA user_version.

    קוראים את הגרסה שוב אחרי BEGIN IMMEDIATE. מי שחיכה על המנעול
    רואה את הגרסה שכבר נכתבה ויוצא בלי ALTER נוסף.
    """
    from app.reminders.repository import ensure_reminder_schema
    from app.services.shifts import ensure_shift_schema

    db.execute(f"PRAGMA busy_timeout = {SCHEMA_BUSY_TIMEOUT_MS}")
    if _read_user_version(db) >= SCHEMA_VERSION:
        return
    with exclusive_schema_transaction(db):
        if _read_user_version(db) >= SCHEMA_VERSION:
            return
        _ensure_base_schema(db)
        ensure_reminder_schema(db)
        ensure_recurrence_schema(db)
        ensure_shift_schema(db)
        from app.reminders.repository import backfill_people_role_flags

        backfill_people_role_flags(db)
        _write_user_version(db, SCHEMA_VERSION)


def init_db():
    db = get_db()
    apply_pending_migrations(db)
    _migrate_hebrew_years_to_letters(db)


_RECURRENCE_COLUMNS = (
    ("recurrence_freq", "TEXT"),
    ("recurrence_calendar", "TEXT"),
    ("recurrence_until", "TEXT"),
    ("recurrence_count", "INTEGER"),
)


def ensure_recurrence_schema(db) -> None:
    """מוסיף עמודות חזרה וטבלת חריגות. בטוח להרצה חוזרת ולעלייה מקבילית.

    אירוע ישן נשאר בלי recurrence_freq (NULL) — כלומר בלי חזרה.
    """
    with exclusive_schema_transaction(db):
        for name, decl in _RECURRENCE_COLUMNS:
            _add_column_if_missing(db, "events", name, decl)

        _schema_execute(
            db,
            """
            CREATE TABLE IF NOT EXISTS event_exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                original_date TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT,
                gregorian_date TEXT,
                hebrew_date TEXT,
                time TEXT,
                description TEXT,
                end_date TEXT,
                color TEXT,
                UNIQUE (event_id, original_date),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            )
            """,
        )
        _schema_execute(
            db,
            "CREATE INDEX IF NOT EXISTS idx_event_exceptions_event ON event_exceptions(event_id)",
        )
        _schema_execute(
            db,
            """
            CREATE TABLE IF NOT EXISTS reminder_sends (
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
        _schema_execute(
            db,
            "CREATE INDEX IF NOT EXISTS idx_reminder_sends_reminder ON reminder_sends(reminder_id)",
        )
        from app.reminders.repository import ensure_reminder_sends_per_chat

        ensure_reminder_sends_per_chat(db)

def _migrate_hebrew_years_to_letters(db):
    """ממיר שנים מספריות בתאריכים עבריים שמורים לאותיות (פעם אחת לנתונים קיימים)."""
    try:
        rows = db.execute(
            "SELECT id, hebrew_date FROM events WHERE hebrew_date GLOB '* [0-9][0-9][0-9]' "
            "OR hebrew_date GLOB '* [0-9][0-9][0-9][0-9]'"
        ).fetchall()
        updated = 0
        for row in rows:
            old_value = row["hebrew_date"]
            new_value = normalize_hebrew_date_text(old_value)
            if new_value != old_value:
                db.execute(
                    "UPDATE events SET hebrew_date = ? WHERE id = ?",
                    (new_value, row["id"]),
                )
                updated += 1
        if updated:
            db.commit()
            print(f"Migrated {updated} hebrew_date values to letter years")
    except Exception as exc:
        print(f"Hebrew year migration skipped: {exc}")

# פונקציה חדשה להוספת צבע מותאם אישית
def add_custom_color(name, color_code, background_color):
    db = get_db()
    try:
        db.execute('''
            INSERT INTO event_colors (name, color_code, background_color)
            VALUES (?, ?, ?)
        ''', (name, color_code, background_color))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error adding custom color: {e}")
        return False

# פונקציה לקבלת כל הצבעים הזמינים
def get_all_colors():
    db = get_db()
    try:
        colors = db.execute('SELECT * FROM event_colors').fetchall()
        return [dict(color) for color in colors]
    except sqlite3.Error as e:
        print(f"Error getting colors: {e}")
        return []


def export_data():
    from app.reminders.repository import list_people
    from app.services.shifts import shifts_enabled

    return {
        "events": get_all_events(),
        "colors": get_all_colors(),
        "reminder_people": list_people(),
        "shifts_enabled": shifts_enabled(),
    }


def _event_fingerprint(event):
    return (
        (event.get("title") or "").strip(),
        event.get("gregorian_date") or "",
        event.get("time") or "",
        event.get("end_date") or "",
    )


def _event_slot(event):
    """משבצת זמן לזיהוי אותו אירוע גם אחרי שינוי כותרת / החלפת ID."""
    return (
        event.get("gregorian_date") or "",
        event.get("time") or "",
        event.get("end_date") or "",
    )


def _normalize_end_date(gregorian_date, end_date):
    """מבטל end_date מוקדם מההתחלה (נתונים שבורים מייבוא/עריכות ישנות)."""
    if not end_date:
        return None
    if gregorian_date and end_date < gregorian_date:
        return None
    return end_date


def _resolve_merge_target_id(event, fingerprint, existing_by_id, existing_by_fp, existing_by_slot):
    incoming_id = event.get("id")
    if incoming_id is not None:
        try:
            incoming_id = int(incoming_id)
        except (TypeError, ValueError):
            incoming_id = None
    if incoming_id in existing_by_id:
        return incoming_id

    if fingerprint in existing_by_fp:
        return existing_by_fp[fingerprint]["id"]

    # אם יש בדיוק אירוע אחד באותו תאריך+שעה — מניחים שזו עריכה של אותו אירוע
    slot = _event_slot(event)
    candidates = existing_by_slot.get(slot) or []
    if len(candidates) == 1:
        return candidates[0]["id"]

    return None


def _apply_imported_reminders(event_id, raw_reminders):
    """משחזר תזכורות מייבוא. בלי המפתח לא נוגעים בשורות קיימות."""
    from app.reminders.repository import people_ids, replace_event_reminders
    from app.reminders.schedule import OffsetError, parse_reminders_payload

    if not isinstance(raw_reminders, list):
        raise ValueError("'reminders' must be an array")
    try:
        parsed = parse_reminders_payload(raw_reminders, people_ids(role="reminders"))
    except OffsetError as exc:
        raise ValueError(str(exc)) from exc
    sent_by_offset = {}
    for raw in raw_reminders:
        if not isinstance(raw, dict) or not raw.get("sent_at"):
            continue
        if raw.get("offset_minutes") is None:
            continue
        try:
            sent_by_offset[int(raw["offset_minutes"])] = raw["sent_at"]
        except (TypeError, ValueError):
            continue
    for item in parsed:
        if item["offset_minutes"] in sent_by_offset:
            item["sent_at"] = sent_by_offset[item["offset_minutes"]]
    replace_event_reminders(event_id, parsed, commit=False)


def _anchor_date(gregorian_date):
    from datetime import date as date_cls

    return date_cls.fromisoformat(str(gregorian_date)[:10])


def _recurrence_for_write(event, gregorian_date, keep_existing=False):
    """מחזיר dict של הכלל, None אם אין חזרה, או 'keep' אם המפתח לא בייבוא."""
    has_freq = "recurrence_freq" in event
    has_nested = isinstance(event.get("recurrence"), dict)
    if not has_freq and not has_nested:
        return "keep" if keep_existing else None
    source = event["recurrence"] if has_nested and not has_freq else event
    anchor = _anchor_date(gregorian_date)
    return clean_recurrence(
        source.get("recurrence_freq") if has_freq or not has_nested else source.get("freq"),
        source.get("recurrence_calendar") if has_freq or not has_nested else source.get("calendar"),
        source.get("recurrence_until") if has_freq or not has_nested else source.get("until"),
        source.get("recurrence_count") if has_freq or not has_nested else source.get("count"),
        anchor,
    )


def _import_shift_values(event):
    from app.services.shifts import shift_columns_from_payload

    return shift_columns_from_payload(event, missing="defaults")


def _import_shift_sql(event):
    from app.services.shifts import shift_columns_from_payload

    values = shift_columns_from_payload(event, missing="keep")
    if values == "keep":
        return "", ()
    return ", is_shift = ?, shift_person_id = ?, shift_label = ?", values


def _import_recurrence_sql(event, gregorian_date, old):
    del old
    rule = _recurrence_for_write(event, gregorian_date, keep_existing=True)
    if rule == "keep":
        return "", ()
    if not rule:
        return (
            ", recurrence_freq = NULL, recurrence_calendar = NULL, "
            "recurrence_until = NULL, recurrence_count = NULL",
            (),
        )
    return (
        ", recurrence_freq = ?, recurrence_calendar = ?, recurrence_until = ?, recurrence_count = ?",
        (
            rule["recurrence_freq"],
            rule["recurrence_calendar"],
            rule["recurrence_until"],
            rule["recurrence_count"],
        ),
    )


def _apply_imported_exceptions(event_id, raw, *, replace: bool):
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ValueError("'exceptions' must be an array")
    db = get_db()
    if replace:
        db.execute("DELETE FROM event_exceptions WHERE event_id = ?", (event_id,))
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each exception must be an object")
        original = item.get("original_date")
        kind = item.get("kind")
        if not original or kind not in ("deleted", "edited"):
            raise ValueError("Exception needs original_date and kind deleted|edited")
        upsert_exception(
            event_id,
            original_date=str(original)[:10],
            kind=kind,
            fields=item,
            commit=False,
        )


def import_data(payload, mode="replace"):
    if not isinstance(payload, dict):
        raise ValueError("Import payload must be a JSON object")

    events = payload.get("events", [])
    colors = payload.get("colors", [])

    if not isinstance(events, list) or not isinstance(colors, list):
        raise ValueError("'events' and 'colors' must be arrays")

    db = get_db()

    try:
        db.execute("BEGIN")

        if mode == "replace":
            db.execute("DELETE FROM reminder_sends")
            db.execute("DELETE FROM reminders")
            db.execute("DELETE FROM event_exceptions")
            db.execute("DELETE FROM events")
            db.execute("DELETE FROM event_colors")
            if "reminder_people" in payload:
                db.execute("DELETE FROM reminder_people")
        elif mode != "merge":
            raise ValueError("Unsupported import mode")

        if "shifts_enabled" in payload:
            flag = payload.get("shifts_enabled")
            if not isinstance(flag, bool) and flag not in (0, 1):
                raise ValueError("shifts_enabled must be a boolean")
            db.execute(
                """
                INSERT INTO household_settings (id, shifts_enabled) VALUES (1, ?)
                ON CONFLICT(id) DO UPDATE SET shifts_enabled = excluded.shifts_enabled
                """,
                (1 if flag else 0,),
            )

        if "reminder_people" in payload:
            from app.reminders.repository import upsert_person_for_import

            people = payload.get("reminder_people")
            if not isinstance(people, list):
                raise ValueError("'reminder_people' must be an array")
            for person in people:
                upsert_person_for_import(person, replace_ids=(mode == "replace"))

        existing_colors = {
            (row["name"] or "").strip(): row
            for row in get_all_colors()
        }
        imported_colors = 0

        for color in colors:
            if not isinstance(color, dict):
                raise ValueError("Each color must be an object")

            name = (color.get("name") or "").strip()
            color_code = color.get("color_code")
            background_color = color.get("background_color")

            if not name or not color_code or not background_color:
                raise ValueError("Color entries must include name, color_code and background_color")

            if mode == "merge" and name in existing_colors:
                continue

            db.execute(
                '''
                INSERT INTO event_colors (name, color_code, background_color)
                VALUES (?, ?, ?)
                ''',
                (name, color_code, background_color),
            )
            existing_colors[name] = {
                "name": name,
                "color_code": color_code,
                "background_color": background_color,
            }
            imported_colors += 1

        existing_events = get_all_events() if mode == "merge" else []
        existing_by_id = {event["id"]: event for event in existing_events}
        existing_by_fp = {_event_fingerprint(event): event for event in existing_events}
        existing_by_slot = {}
        for event in existing_events:
            existing_by_slot.setdefault(_event_slot(event), []).append(event)

        inserted_events = 0
        updated_events = 0

        for event in events:
            if not isinstance(event, dict):
                raise ValueError("Each event must be an object")

            from app.services.event_payload import EventPayloadError, clean_event_write

            try:
                cleaned = clean_event_write(event)
            except EventPayloadError as exc:
                raise ValueError(str(exc)) from exc

            title = cleaned["title"]
            gregorian_date = cleaned["gregorian_date"]
            hebrew_date = normalize_hebrew_date_text(cleaned["hebrew_date"])
            time_value = cleaned["time"]
            description = cleaned["description"]
            end_date = cleaned["end_date"]
            color_value = cleaned["color"] if "color" in cleaned else event.get("color")
            fingerprint = _event_fingerprint({
                **event,
                "end_date": end_date,
            })
            slot = _event_slot({
                **event,
                "end_date": end_date,
            })

            target_id = None
            if mode == "merge":
                target_id = _resolve_merge_target_id(
                    event,
                    fingerprint,
                    existing_by_id,
                    existing_by_fp,
                    existing_by_slot,
                )

            if target_id is not None:
                old = existing_by_id.get(target_id) or {}
                recurrence_sql, recurrence_params = _import_recurrence_sql(
                    event, gregorian_date, old
                )
                shift_sql, shift_params = _import_shift_sql(event)
                db.execute(
                    f'''
                    UPDATE events
                    SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?,
                        description = ?, end_date = ?, color = ?{recurrence_sql}{shift_sql}
                    WHERE id = ?
                    ''',
                    (
                        title,
                        gregorian_date,
                        hebrew_date,
                        time_value,
                        description,
                        end_date,
                        color_value,
                        *recurrence_params,
                        *shift_params,
                        target_id,
                    ),
                )
                updated = {
                    "id": target_id,
                    "title": title,
                    "gregorian_date": gregorian_date,
                    "hebrew_date": hebrew_date,
                    "time": time_value,
                    "description": description,
                    "end_date": end_date,
                    "color": color_value,
                }
                existing_by_id[target_id] = updated
                existing_by_fp[fingerprint] = updated
                # מעדכנים את מפת המשבצות אחרי שינוי כותרת/שעה
                old_slot = _event_slot(old) if old else None
                if old_slot in existing_by_slot:
                    existing_by_slot[old_slot] = [
                        item for item in existing_by_slot[old_slot] if item.get("id") != target_id
                    ]
                    if not existing_by_slot[old_slot]:
                        del existing_by_slot[old_slot]
                existing_by_slot.setdefault(slot, [])
                existing_by_slot[slot] = [
                    item for item in existing_by_slot[slot] if item.get("id") != target_id
                ]
                existing_by_slot[slot].append(updated)
                updated_events += 1
            else:
                rule = _recurrence_for_write(event, gregorian_date, keep_existing=False)
                is_shift, shift_person_id, shift_label = _import_shift_values(event)
                cursor = db.execute(
                    '''
                    INSERT INTO events (
                        title, gregorian_date, hebrew_date, time, description, end_date, color,
                        recurrence_freq, recurrence_calendar, recurrence_until, recurrence_count,
                        is_shift, shift_person_id, shift_label
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        title,
                        gregorian_date,
                        hebrew_date,
                        time_value,
                        description,
                        end_date,
                        color_value,
                        rule["recurrence_freq"] if rule else None,
                        rule["recurrence_calendar"] if rule else None,
                        rule["recurrence_until"] if rule else None,
                        rule["recurrence_count"] if rule else None,
                        is_shift,
                        shift_person_id,
                        shift_label,
                    ),
                )
                new_id = cursor.lastrowid
                created = {
                    "id": new_id,
                    "title": title,
                    "gregorian_date": gregorian_date,
                    "hebrew_date": hebrew_date,
                    "time": time_value,
                    "description": description,
                    "end_date": end_date,
                    "color": color_value,
                }
                existing_by_id[new_id] = created
                existing_by_fp[fingerprint] = created
                existing_by_slot.setdefault(slot, []).append(created)
                inserted_events += 1

            saved_id = target_id if target_id is not None else new_id
            if "reminders" in event:
                _apply_imported_reminders(saved_id, event.get("reminders"))
            if "exceptions" in event:
                _apply_imported_exceptions(
                    saved_id,
                    event.get("exceptions"),
                    replace=True,
                )

        db.commit()
        return {
            "success": True,
            "imported_events": inserted_events + updated_events,
            "inserted_events": inserted_events,
            "updated_events": updated_events,
            "imported_colors": imported_colors,
            "mode": mode,
        }
    except Exception:
        db.rollback()
        raise

# פונקציות CRUD

def _with_recurrence(data):
    data.update(recurrence_fields(data))
    return data


def _attach_related(events):
    from app.reminders.repository import attach_reminders

    attach_reminders(events)
    grouped = exceptions_for_events([event["id"] for event in events if event.get("id") is not None])
    for event in events:
        event["exceptions"] = grouped.get(event.get("id"), [])
    return events


def create_event(
    title,
    gregorian_date,
    hebrew_date,
    time=None,
    description="",
    end_date=None,
    color=None,
    recurrence=None,
    shift=None,
):
    db = get_db()
    try:
        end_date = _normalize_end_date(gregorian_date, end_date)
        hebrew_date = normalize_hebrew_date_text(hebrew_date)
        rule = recurrence or {}
        is_shift, shift_person_id, shift_label = shift or (0, None, None)
        cursor = db.execute(
            '''
            INSERT INTO events (
                title, gregorian_date, hebrew_date, time, description, end_date, color,
                recurrence_freq, recurrence_calendar, recurrence_until, recurrence_count,
                is_shift, shift_person_id, shift_label
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                title,
                gregorian_date,
                hebrew_date,
                time,
                description,
                end_date,
                color,
                rule.get("recurrence_freq"),
                rule.get("recurrence_calendar"),
                rule.get("recurrence_until"),
                rule.get("recurrence_count"),
                1 if is_shift else 0,
                shift_person_id,
                shift_label,
            ),
        )
        db.commit()
        return cursor.lastrowid
    except sqlite3.Error as e:
        print(f"Error creating event: {e}")
        return None

def get_event(event_id):
    db = get_db()
    try:
        event = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            return None
        data = _with_recurrence(dict(event))
        data["hebrew_date"] = normalize_hebrew_date_text(data.get("hebrew_date"))
        from app.services.shifts import annotate_shift_events

        return annotate_shift_events(_attach_related([data]))[0]
    except sqlite3.Error as e:
        print(f"Error getting event: {e}")
        return None

def get_all_events():
    db = get_db()
    try:
        events = db.execute('SELECT * FROM events ORDER BY gregorian_date, time').fetchall()
        result = []
        for event in events:
            data = _with_recurrence(dict(event))
            data["hebrew_date"] = normalize_hebrew_date_text(data.get("hebrew_date"))
            result.append(data)
        from app.services.shifts import annotate_shift_events

        return annotate_shift_events(_attach_related(result))
    except sqlite3.Error as e:
        print(f"Error getting all events: {e}")
        return []

def update_event(
    event_id,
    title,
    gregorian_date,
    hebrew_date,
    time=None,
    description="",
    end_date=None,
    color=None,
    recurrence="keep",
    clear_exceptions=False,
    shift="keep",
):
    db = get_db()
    try:
        end_date = _normalize_end_date(gregorian_date, end_date)
        hebrew_date = normalize_hebrew_date_text(hebrew_date)
        shift_sql = ""
        shift_params = ()
        if shift != "keep":
            is_shift, shift_person_id, shift_label = shift
            shift_sql = ", is_shift = ?, shift_person_id = ?, shift_label = ?"
            shift_params = (1 if is_shift else 0, shift_person_id, shift_label)
        if recurrence == "keep":
            db.execute(
                f'''
                UPDATE events
                SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?,
                    description = ?, end_date = ?, color = ?{shift_sql}
                WHERE id = ?
                ''',
                (title, gregorian_date, hebrew_date, time, description, end_date, color, *shift_params, event_id),
            )
        else:
            rule = recurrence or {}
            db.execute(
                f'''
                UPDATE events
                SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?,
                    description = ?, end_date = ?, color = ?,
                    recurrence_freq = ?, recurrence_calendar = ?,
                    recurrence_until = ?, recurrence_count = ?{shift_sql}
                WHERE id = ?
                ''',
                (
                    title,
                    gregorian_date,
                    hebrew_date,
                    time,
                    description,
                    end_date,
                    color,
                    rule.get("recurrence_freq"),
                    rule.get("recurrence_calendar"),
                    rule.get("recurrence_until"),
                    rule.get("recurrence_count"),
                    *shift_params,
                    event_id,
                ),
            )
        if clear_exceptions:
            db.execute("DELETE FROM event_exceptions WHERE event_id = ?", (event_id,))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error updating event: {e}")
        return False

def delete_event(event_id):
    db = get_db()
    try:
        db.execute(
            "DELETE FROM reminder_sends WHERE reminder_id IN (SELECT id FROM reminders WHERE event_id = ?)",
            (event_id,),
        )
        db.execute("DELETE FROM reminders WHERE event_id = ?", (event_id,))
        db.execute("DELETE FROM event_exceptions WHERE event_id = ?", (event_id,))
        cursor = db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Error deleting event: {e}")
        return False


def exceptions_for_events(event_ids):
    db = get_db()
    if not event_ids:
        return {}
    marks = ",".join("?" for _ in event_ids)
    rows = db.execute(
        f"""
        SELECT id, event_id, original_date, kind, title, gregorian_date, hebrew_date,
               time, description, end_date, color
        FROM event_exceptions
        WHERE event_id IN ({marks})
        ORDER BY original_date, id
        """,
        tuple(event_ids),
    ).fetchall()
    grouped = {}
    for row in rows:
        grouped.setdefault(row["event_id"], []).append(dict(row))
    return grouped


def list_exceptions(event_id):
    return exceptions_for_events([event_id]).get(event_id, [])


def upsert_exception(event_id, original_date, kind, fields=None, commit=True):
    db = get_db()
    fields = fields or {}
    db.execute(
        """
        INSERT INTO event_exceptions (
            event_id, original_date, kind, title, gregorian_date, hebrew_date,
            time, description, end_date, color
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id, original_date) DO UPDATE SET
            kind = excluded.kind,
            title = excluded.title,
            gregorian_date = excluded.gregorian_date,
            hebrew_date = excluded.hebrew_date,
            time = excluded.time,
            description = excluded.description,
            end_date = excluded.end_date,
            color = excluded.color
        """,
        (
            event_id,
            original_date,
            kind,
            fields.get("title"),
            fields.get("gregorian_date"),
            fields.get("hebrew_date"),
            fields.get("time"),
            fields.get("description"),
            fields.get("end_date"),
            fields.get("color"),
        ),
    )
    if commit:
        db.commit()
    return True

def test_database_connection():
    try:
        # נסיון לקבל את כל האירועים
        events = get_all_events()
        print(f"מספר האירועים בדאטהבייס: {len(events)}")
        return True
    except Exception as e:
        print(f"שגיאה בחיבור לדאטהבייס: {str(e)}")
        return False 