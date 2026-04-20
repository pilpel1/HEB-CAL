import os
import sqlite3
from pathlib import Path

from flask import g


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

        for color in colors:
            if not isinstance(color, dict):
                raise ValueError("Each color must be an object")

            name = color.get("name")
            color_code = color.get("color_code")
            background_color = color.get("background_color")

            if not name or not color_code or not background_color:
                raise ValueError("Color entries must include name, color_code and background_color")

            db.execute(
                '''
                INSERT INTO event_colors (name, color_code, background_color)
                VALUES (?, ?, ?)
                ''',
                (name, color_code, background_color),
            )

        for event in events:
            if not isinstance(event, dict):
                raise ValueError("Each event must be an object")

            title = event.get("title")
            gregorian_date = event.get("gregorian_date")
            hebrew_date = event.get("hebrew_date")

            if not title or not gregorian_date or not hebrew_date:
                raise ValueError("Event entries must include title, gregorian_date and hebrew_date")

            db.execute(
                '''
                INSERT INTO events (title, gregorian_date, hebrew_date, time, description, end_date, color)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    title,
                    gregorian_date,
                    hebrew_date,
                    event.get("time"),
                    event.get("description", ""),
                    event.get("end_date"),
                    event.get("color"),
                ),
            )

        db.commit()
        return {
            "success": True,
            "imported_events": len(events),
            "imported_colors": len(colors),
            "mode": mode,
        }
    except Exception:
        db.rollback()
        raise

# פונקציות CRUD

def create_event(title, gregorian_date, hebrew_date, time=None, description="", end_date=None, color=None):
    db = get_db()
    try:
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
        return dict(event) if event else None
    except sqlite3.Error as e:
        print(f"Error getting event: {e}")
        return None

def get_all_events():
    db = get_db()
    try:
        events = db.execute('SELECT * FROM events ORDER BY gregorian_date, time').fetchall()
        return [dict(event) for event in events]
    except sqlite3.Error as e:
        print(f"Error getting all events: {e}")
        return []

def update_event(event_id, title, gregorian_date, hebrew_date, time=None, description="", end_date=None, color=None):
    db = get_db()
    try:
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