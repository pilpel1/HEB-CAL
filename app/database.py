import sqlite3
from flask import g
from config import DATABASE_PATH


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
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