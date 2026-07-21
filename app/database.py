import os
import sqlite3
from pathlib import Path

from flask import g

from app.services.hebrew_format import normalize_hebrew_date_text


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = Path("data/calendar.db")


def get_database_path():
    configured_path = os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
    database_path = Path(configured_path)

    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path

    database_path.parent.mkdir(parents=True, exist_ok=True)
    return database_path


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(str(get_database_path()))
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    
    # קצירת טבלת אירועים רק אם היא לא קיימת
    db.execute('''
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
    ''')
    
    # טצירת טבלת צבעים רק אם היא לא קיימת
    db.execute('''
        CREATE TABLE IF NOT EXISTS event_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color_code TEXT NOT NULL,
            background_color TEXT NOT NULL
        )
    ''')
    
    # בדיקה אם יש כבר צבעים בטבלה
    colors = db.execute('SELECT * FROM event_colors').fetchall()
    if not colors:
        # הכנסת צבעים דיפולטיביים רק אם הטבלה ריקה
        default_colors = [
            ('ציאן', 'cyan', 'rgba(0, 255, 255, 0.2)'),
            ('צהוב', 'yellow', 'rgba(255, 255, 0, 0.2)'),
            ('כתום', 'orange', 'rgba(255, 165, 0, 0.2)'),
            ('ירוק', 'green', 'rgba(0, 128, 0, 0.2)')
        ]
        
        db.executemany('''
            INSERT INTO event_colors (name, color_code, background_color)
            VALUES (?, ?, ?)
        ''', default_colors)
        
        db.commit()

    _migrate_hebrew_years_to_letters(db)

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
    return {
        "events": get_all_events(),
        "colors": get_all_colors(),
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
            db.execute("DELETE FROM events")
            db.execute("DELETE FROM event_colors")
        elif mode != "merge":
            raise ValueError("Unsupported import mode")

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

            title = event.get("title")
            gregorian_date = event.get("gregorian_date")
            hebrew_date = event.get("hebrew_date")

            if not title or not gregorian_date or not hebrew_date:
                raise ValueError("Event entries must include title, gregorian_date and hebrew_date")

            hebrew_date = normalize_hebrew_date_text(hebrew_date)
            time_value = event.get("time")
            description = event.get("description", "")
            end_date = _normalize_end_date(gregorian_date, event.get("end_date"))
            color_value = event.get("color")
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
                db.execute(
                    '''
                    UPDATE events
                    SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?,
                        description = ?, end_date = ?, color = ?
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
                cursor = db.execute(
                    '''
                    INSERT INTO events (title, gregorian_date, hebrew_date, time, description, end_date, color)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        title,
                        gregorian_date,
                        hebrew_date,
                        time_value,
                        description,
                        end_date,
                        color_value,
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

def create_event(title, gregorian_date, hebrew_date, time=None, description="", end_date=None, color=None):
    db = get_db()
    try:
        end_date = _normalize_end_date(gregorian_date, end_date)
        hebrew_date = normalize_hebrew_date_text(hebrew_date)
        db.execute('''
            INSERT INTO events (title, gregorian_date, hebrew_date, time, description, end_date, color)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, gregorian_date, hebrew_date, time, description, end_date, color))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error creating event: {e}")
        return False

def get_event(event_id):
    db = get_db()
    try:
        event = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
        if not event:
            return None
        data = dict(event)
        data["hebrew_date"] = normalize_hebrew_date_text(data.get("hebrew_date"))
        return data
    except sqlite3.Error as e:
        print(f"Error getting event: {e}")
        return None

def get_all_events():
    db = get_db()
    try:
        events = db.execute('SELECT * FROM events ORDER BY gregorian_date, time').fetchall()
        result = []
        for event in events:
            data = dict(event)
            data["hebrew_date"] = normalize_hebrew_date_text(data.get("hebrew_date"))
            result.append(data)
        return result
    except sqlite3.Error as e:
        print(f"Error getting all events: {e}")
        return []

def update_event(event_id, title, gregorian_date, hebrew_date, time=None, description="", end_date=None, color=None):
    db = get_db()
    try:
        end_date = _normalize_end_date(gregorian_date, end_date)
        hebrew_date = normalize_hebrew_date_text(hebrew_date)
        db.execute('''
            UPDATE events 
            SET title = ?, gregorian_date = ?, hebrew_date = ?, time = ?, description = ?, end_date = ?, color = ?
            WHERE id = ?
        ''', (title, gregorian_date, hebrew_date, time, description, end_date, color, event_id))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error updating event: {e}")
        return False

def delete_event(event_id):
    db = get_db()
    try:
        db.execute('DELETE FROM events WHERE id = ?', (event_id,))
        db.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error deleting event: {e}")
        return False

def test_database_connection():
    try:
        # נסיון לקבל את כל האירועים
        events = get_all_events()
        print(f"מספר האירועים בדאטהבייס: {len(events)}")
        return True
    except Exception as e:
        print(f"שגיאה בחיבור לדאטהבייס: {str(e)}")
        return False 