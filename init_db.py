from app import app  # ייבוא האפליקציה הראשית
from app.database import init_db

if __name__ == '__main__':
    with app.app_context():  # יצירת קונטקסט של האפליקציה
        init_db()
        print("Database initialized successfully!") 